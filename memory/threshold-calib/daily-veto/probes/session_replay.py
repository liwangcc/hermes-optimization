"""Every fixture's questions in ONE session (the repeat window and the silent rule meet), sidecar answers computed
from the dump vectors as managed_server does (no model). Writes {fixture: [block per turn]} to out_json.
argv: plugin_dir scratchpad work_dir out_json
"""
import heapq
import io
import json
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

PLUGIN, SCR, WORK, OUT = (Path(a) for a in sys.argv[1:5])
BUDGET = int(sys.argv[5]) if len(sys.argv) > 5 else 0  # prefetch_max_tokens
FRESH = len(sys.argv) > 6 and sys.argv[6] == "fresh"  # a session per question instead of one
sys.path.insert(0, str(SCR))
import daily_eval as d  # noqa: E402
import native_daily as nd  # noqa: E402
import recall_dump as rd  # noqa: E402

logging.disable(logging.CRITICAL)
CUR = {}


def answer(sent):
    fx = CUR["fx"]
    c = fx.mats["daily"] @ fx.qv[CUR["by_text"][sent["query"]]]
    scores = {f["fact_id"]: float(c[j]) for j, f in enumerate(fx.facts) if f["trust_score"] >= sent["min_trust"]}
    out = sorted(({"fact_id": k, "cos": round(v, 4)} for k, v in scores.items() if v >= sent["tau"]),
                 key=lambda x: -x["cos"])
    body = {"candidates": out[:sent["limit"]]}
    if isinstance(sent.get("ids"), list):
        values = np.array(list(scores.values()), dtype=np.float32)
        body.update(scores={str(k): scores[k] for k in sent["ids"] if k in scores},
                    top=[[k, v] for k, v in heapq.nlargest(2, scores.items(), key=lambda kv: kv[1])],
                    stats={"n": len(values), "mean": float(values.mean()), "std": float(values.std())})
    return json.dumps(body).encode()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Opener:
    def open(self, req, timeout=None):
        return _Resp(answer(json.loads(req.data)))


urllib.request.build_opener = lambda *a, **k: _Opener()
pkg = rd.load_plugin(rd.PLUGIN, SCR / "shim")
mod = nd.load_daily(PLUGIN)
mod.managed_local.wake = lambda *a, **k: None
WORK.mkdir(parents=True, exist_ok=True)
result = {}
for split in ("dev", "test"):
    for stem in sorted(p.with_suffix("") for p in (SCR / "dump" / split).glob("*.json")):
        fx = d.Fixture(stem)
        meta = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
        td = Path(tempfile.mkdtemp(prefix="session-", dir=WORK))
        os.environ["HERMES_HOME"] = str(td)
        b = rd.open_provider(pkg, td / "f.db", td)
        qs, _ = rd.build(pkg, b, meta["suite"], meta["lang"])
        b.shutdown()
        by_text = {}
        for k, q in enumerate(fx.q):
            by_text.setdefault(q["q"], k)
        CUR.update(fx=fx, by_text=by_text)
        p = mod.SemanticHolographicProvider(config={
            "db_path": str(td / "f.db"), "embeddings": "off", "semantic_enabled": True,
            "semantic_url": "http://127.0.0.1:9", "semantic_tau": 0.55, "semantic_timeout_ms": 10000, "prefetch_max_tokens": BUDGET})
        p.initialize(session_id="fixture", hermes_home=str(td))
        result[f"{split}/{stem.name}"] = [[int(x) for x in rd.ID.findall(p.prefetch(q["q"], session_id=f"f{k}" if FRESH else "one"))]
                                          for k, q in enumerate(qs)]
        p.shutdown()
OUT.write_text(json.dumps(result), encoding="utf-8")
print(PLUGIN.name, "sessions written:", len(result))
