"""Semantic memory sidecar: a local bge-m3 embedding service for the holographic-semantic wrapper.

Localhost-only HTTP. Read-only on the fact DB. Fail-safe: any error -> HTTP 5xx, and the caller
falls back to lexical recall. No network egress (the model is loaded offline from disk).

Run:
    python server.py

Environment overrides:
    SEMANTIC_DB     path to your holographic fact store (SQLite). REQUIRED in practice —
                    point this at the DB used by the holographic memory provider.
    SEMANTIC_MODEL  path to a local bge-m3 model directory (default: ./models/bge-m3)
    SEMANTIC_PORT   listen port (default: 8791)

Endpoints:
    GET  /health                 readiness, device, indexed fact count
    POST /candidates             {query, tau, limit, min_trust} -> ranked cosine candidates
    POST /embed                  {texts: [...]} -> normalized vectors
"""
import hashlib, json, os, sqlite3, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(k, None)

SVC = Path(__file__).resolve().parent
# Point SEMANTIC_DB at your holographic fact store. The default is a placeholder next to this file.
DB = Path(os.environ.get("SEMANTIC_DB", str(SVC / "memory_store.db")))
MODEL = Path(os.environ.get("SEMANTIC_MODEL", str(SVC / "models" / "bge-m3")))
CACHE = SVC / "cache"
PORT = int(os.environ.get("SEMANTIC_PORT", "8791"))
CACHE.mkdir(exist_ok=True)

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

LOCK = threading.RLock()
STATE = {"model": None, "device": "cpu", "vecs": {}, "hashes": {}, "ready": False, "error": ""}

def load_model():
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    kw = {"torch_dtype": torch.float16} if dev == "cuda" else {}
    t0 = time.time()
    m = SentenceTransformer(str(MODEL), device=dev, model_kwargs=kw)
    m.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)  # CUDA kernel warmup
    STATE.update(model=m, device=dev, ready=True)
    log(f"model loaded on {dev} in {time.time()-t0:.1f}s")
    vf, hf = CACHE / "vectors.npz", CACHE / "hashes.json"
    if vf.exists() and hf.exists():
        try:
            data = np.load(vf)
            STATE["vecs"] = {int(k): data[k] for k in data.files}
            STATE["hashes"] = {int(k): v for k, v in json.loads(hf.read_text(encoding="utf-8")).items()}
            log(f"cache loaded: {len(STATE['vecs'])} vectors")
        except Exception as e:
            log(f"cache load failed, rebuilding: {e}")
            STATE["vecs"], STATE["hashes"] = {}, {}

def save_cache():
    import numpy as np
    np.savez(CACHE / "vectors.npz", **{str(k): v for k, v in STATE["vecs"].items()})
    (CACHE / "hashes.json").write_text(json.dumps({str(k): v for k, v in STATE["hashes"].items()}), encoding="utf-8")

def fact_hash(content, tags):
    return hashlib.sha256(((content or "") + "\x00" + (tags or "")).encode("utf-8")).hexdigest()[:16]

def read_facts():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT fact_id, content, tags, trust_score FROM facts")]
    finally:
        con.close()

def sync_and_candidates(query, tau, limit, min_trust):
    import numpy as np
    with LOCK:
        facts = read_facts()
        m = STATE["model"]
        texts, ids = [], []
        live = set()
        for f in facts:
            fid = f["fact_id"]; live.add(fid)
            h = fact_hash(f["content"], f["tags"])
            if STATE["hashes"].get(fid) != h or fid not in STATE["vecs"]:
                texts.append((f["content"] or "") + " " + (f.get("tags") or ""))
                ids.append(fid)
                STATE["hashes"][fid] = h
        for fid in list(STATE["vecs"]):
            if fid not in live:
                STATE["vecs"].pop(fid, None); STATE["hashes"].pop(fid, None)
        embedded = 0
        if texts:
            vecs = m.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
            for fid, v in zip(ids, vecs):
                STATE["vecs"][fid] = np.asarray(v, dtype=np.float32)
            embedded = len(texts)
            save_cache()
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
            self._send(200, {"ok": STATE["ready"], "model": "bge-m3", "device": STATE["device"],
                             "facts_indexed": len(STATE["vecs"]), "error": STATE["error"]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
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
    try:
        load_model()
    except Exception as e:
        STATE["error"] = f"{type(e).__name__}: {e}"
        log(f"MODEL LOAD FAILED: {STATE['error']}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"listening on 127.0.0.1:{PORT}")
    srv.serve_forever()