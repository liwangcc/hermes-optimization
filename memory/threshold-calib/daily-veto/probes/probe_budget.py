"""prefetch_max_tokens on: does the wrapper still append the sidecar's top fact when the budget dropped it from the
base block? argv: plugin_dir scratchpad work_dir max_tokens
Canned answer per question (no sidecar, no model): the top fact is the LAST fact of the unbudgeted base block,
cos 0.9, every base fact at 0.9 (so the veto keeps all), a store of 199 with mean 0.3 / std 0.1.
"""
import io
import json
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

PLUGIN, SCR, WORK, BUDGET = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
sys.path.insert(0, str(SCR))
import daily_eval as d  # noqa: E402
import native_daily as nd  # noqa: E402
import recall_dump as rd  # noqa: E402

logging.disable(logging.CRITICAL)
CUR = {"base": []}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Opener:
    def open(self, req, timeout=None):
        sent = json.loads(req.data)
        last = CUR["base"][-1]
        other = next(f for f in range(1, 500) if f not in CUR["base"])
        answer = {"candidates": [{"fact_id": last, "cos": 0.9}],
                  "scores": {str(i): 0.9 for i in sent.get("ids") or []},
                  "top": [[last, 0.9], [other, 0.5]], "stats": {"n": 199, "mean": 0.3, "std": 0.1}}
        return _Resp(json.dumps(answer).encode())


urllib.request.build_opener = lambda *a, **k: _Opener()
pkg = rd.load_plugin(rd.PLUGIN, SCR / "shim")
mod = nd.load_daily(PLUGIN)
mod.managed_local.wake = lambda *a, **k: None
WORK.mkdir(parents=True, exist_ok=True)
td = Path(tempfile.mkdtemp(prefix="budget-", dir=WORK))
os.environ["HERMES_HOME"] = str(td)
b = rd.open_provider(pkg, td / "f.db", td)
qs, _ = rd.build(pkg, b, "household", "zh")
b.shutdown()
fx = d.Fixture(SCR / "dump" / "dev" / "household-zh")
p = mod.SemanticHolographicProvider(config={
    "db_path": str(td / "f.db"), "embeddings": "off", "semantic_enabled": True, "prefetch_max_tokens": BUDGET,
    "semantic_url": "http://127.0.0.1:9", "semantic_timeout_ms": 400})
p.initialize(session_id="fixture", hermes_home=str(td))
asked = shown_last = 0
for i, q in enumerate(qs):
    base = d.base(fx, i)
    if not fx.q[i]["askable"] or not 2 <= len(base) < 7:
        continue
    CUR["base"] = base
    got = [int(x) for x in rd.ID.findall(p.prefetch(q["q"], session_id=f"b{i}"))]
    asked += 1
    shown_last += base[-1] in got
p.shutdown()
print(f"{PLUGIN.name}: budget {BUDGET}: questions with 2-6 base facts {asked}, final block shows the top fact {shown_last}")
