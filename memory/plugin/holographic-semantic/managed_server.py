"""Profile-managed embedding service for one pinned model. It uses the same protocol as the manual sidecar.

Localhost-only HTTP. Read-only on the fact DB. Fail-safe: any error -> HTTP 5xx, and the caller
falls back to lexical recall. No network egress (the model is loaded offline from disk).

Run:
    python server.py

Environment overrides:
    SEMANTIC_DB     path to your holographic fact store (SQLite). REQUIRED in practice —
                    point this at the DB used by the holographic memory provider.
    SEMANTIC_MODEL  path to a local model directory (default: ./models/bge-m3)
    SEMANTIC_PORT   listen port (default: 8791)
    SEMANTIC_CACHE  vector cache directory, one per model and version (default: ./cache)
    SEMANTIC_MODEL_ID, SEMANTIC_MODEL_REV   the model and pinned version /health reports (default: bge-m3)
    SEMANTIC_DIM    the vector size the model must have; another size refuses to serve

Endpoints:
    GET  /health                 readiness, device, indexed fact count, the store's fact count
    POST /sync                   {limit} -> index new/changed facts now (at most limit), drop deleted ones
    POST /candidates             {query, tau, limit, min_trust} -> ranked cosine candidates
    POST /embed                  {texts: [...]} -> normalized vectors
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(k, None)

SVC = Path(__file__).resolve().parent
# Point SEMANTIC_DB at your holographic fact store. The default is a placeholder next to this file.
DB = Path(os.environ["SEMANTIC_DB"]).resolve()
MODEL = Path(os.environ.get("SEMANTIC_MODEL", str(SVC / "models" / "bge-m3")))
CACHE = Path(os.environ.get("SEMANTIC_CACHE", str(SVC / "cache")))
PORT = int(os.environ.get("SEMANTIC_PORT", "8791"))
STORE_ID = os.environ["SEMANTIC_STORE_ID"]
MODEL_ID = os.environ.get("SEMANTIC_MODEL_ID", "bge-m3")
MODEL_REV = os.environ.get("SEMANTIC_MODEL_REV", "")
DIM = int(os.environ.get("SEMANTIC_DIM", "0"))
CACHE.mkdir(parents=True, exist_ok=True)

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

LOCK = threading.RLock()
STATE = {"model": None, "device": "cpu", "dim": 0, "vecs": {}, "hashes": {}, "ready": False, "error": ""}

def load_model():
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    kw = {"torch_dtype": torch.float16} if dev == "cuda" else {}
    t0 = time.time()
    m = SentenceTransformer(str(MODEL), device=dev, model_kwargs=kw, local_files_only=True)
    dim = len(m.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)[0])  # CUDA kernel warmup
    if DIM and dim != DIM:  # not the model this profile deployed: its vectors must never reach the index
        STATE.update(dim=dim, error=f"the model returns {dim}-dimensional vectors, expected {DIM}")
        log(STATE["error"])
        return
    STATE.update(model=m, device=dev, dim=dim, ready=True)
    log(f"model {MODEL_ID} loaded on {dev} in {time.time()-t0:.1f}s")
    vf, hf = CACHE / "vectors.npz", CACHE / "hashes.json"
    if vf.exists() and hf.exists():
        try:
            data = np.load(vf)
            STATE["vecs"] = {int(k): data[k] for k in data.files if data[k].shape == (dim,)}
            hashes = {int(k): v for k, v in json.loads(hf.read_text(encoding="utf-8")).items()}
            STATE["hashes"] = {k: v for k, v in hashes.items() if k in STATE["vecs"]}  # another size: made again
            log(f"cache loaded: {len(STATE['vecs'])} vectors")
        except Exception as e:
            log(f"cache load failed, rebuilding: {e}")
            STATE["vecs"], STATE["hashes"] = {}, {}

def save_cache():
    import numpy as np
    vectors = CACHE / "vectors.npz"
    hashes = CACHE / "hashes.json"
    vector_part = vectors.with_suffix(".partial")
    hash_part = hashes.with_suffix(".partial")
    with vector_part.open("wb") as stream:
        np.savez(stream, **{str(k): v for k, v in STATE["vecs"].items()})
    hash_part.write_text(json.dumps({str(k): v for k, v in STATE["hashes"].items()}), encoding="utf-8")
    vector_part.replace(vectors)
    hash_part.replace(hashes)

def fact_hash(content, tags):
    return hashlib.sha256(((content or "") + "\x00" + (tags or "")).encode("utf-8")).hexdigest()[:16]

def read_facts():
    if not DB.is_file():
        return []
    con = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT fact_id, content, tags, trust_score FROM facts")]
    finally:
        con.close()


def fact_count():
    if not DB.is_file():
        return 0
    con = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    finally:
        con.close()

def sync(limit=None):
    """Embed new or changed facts (at most `limit` of them) and drop deleted ones.
    Returns (facts, embedded, remaining): the store's rows, vectors made now, facts still without a current one."""
    import numpy as np
    with LOCK:
        facts = read_facts()
        live = {f["fact_id"] for f in facts}
        for fid in list(STATE["vecs"]):
            if fid not in live:
                STATE["vecs"].pop(fid, None)
                STATE["hashes"].pop(fid, None)
        stale = [(f, fact_hash(f["content"], f["tags"])) for f in facts]
        stale = [(f, h) for f, h in stale if STATE["hashes"].get(f["fact_id"]) != h or f["fact_id"] not in STATE["vecs"]]
        batch = stale if limit is None else stale[:limit]
        if batch:
            texts = [(f["content"] or "") + " " + (f.get("tags") or "") for f, _ in batch]
            vecs = STATE["model"].encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
            for (f, h), v in zip(batch, vecs):  # the hash only once the vector exists
                STATE["vecs"][f["fact_id"]] = np.asarray(v, dtype=np.float32)
                STATE["hashes"][f["fact_id"]] = h
            save_cache()
        return facts, len(batch), len(stale) - len(batch)


def sync_and_candidates(query, tau, limit, min_trust):
    import numpy as np
    with LOCK:
        facts, embedded, _ = sync()
        m = STATE["model"]
        qv = np.asarray(m.encode([query], normalize_embeddings=True, show_progress_bar=False)[0], dtype=np.float32)
        out = []
        for f in facts:
            fid = f["fact_id"]
            if f["trust_score"] < min_trust or fid not in STATE["vecs"]:
                continue
            cos = float(STATE["vecs"][fid] @ qv)
            if cos >= tau:
                out.append({"fact_id": fid, "cos": round(cos, 4)})
        out.sort(key=lambda x: -x["cos"])
        return out[:limit], embedded, len(facts)

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                facts = fact_count()
            except sqlite3.Error:
                facts = None  # the store is missing or unreadable: say so instead of failing the probe
            self._send(200, {"ok": STATE["ready"], "model": MODEL_ID, "revision": MODEL_REV, "dim": STATE["dim"],
                             "device": STATE["device"], "facts_indexed": len(STATE["vecs"]), "facts": facts,
                             "error": STATE["error"], "store_id": STORE_ID})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 <= n <= 1_048_576:
                return self._send(413, {"error": "request too large"})
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        if not STATE["ready"]:
            return self._send(503, {"error": "model not ready", "detail": STATE["error"]})
        try:
            if self.path == "/candidates":
                t0 = time.time()
                cands, embedded, total = sync_and_candidates(
                    str(req.get("query", "")), float(req.get("tau", 0.55)),
                    int(req.get("limit", 8)), float(req.get("min_trust", 0.3)))
                self._send(200, {"candidates": cands, "embedded": embedded, "facts": total,
                                 "ms": round((time.time() - t0) * 1000, 1)})
            elif self.path == "/sync":
                t0 = time.time()
                limit = req.get("limit")
                facts, embedded, remaining = sync(int(limit) if limit is not None else None)
                self._send(200, {"embedded": embedded, "remaining": remaining, "facts": len(facts),
                                 "facts_indexed": len(STATE["vecs"]), "ms": round((time.time() - t0) * 1000, 1)})
            elif self.path == "/embed":
                import numpy as np
                with LOCK:
                    vs = STATE["model"].encode(req.get("texts", []), normalize_embeddings=True,
                                               batch_size=16, show_progress_bar=False)
                self._send(200, {"vectors": np.asarray(vs).tolist()})
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            log(f"request error: {type(e).__name__}: {e}")
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    log(f"starting: db={DB} model={MODEL} port={PORT}")
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as srv:
        load_model()
        log(f"listening on 127.0.0.1:{srv.server_port}")
        srv.serve_forever()
