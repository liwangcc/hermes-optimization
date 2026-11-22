"""Canned sidecar answers through the wrapper's real _sidecar_candidates (no sidecar, no model).

argv: plugin_dir scratchpad work_dir
urllib's opener is replaced by one that answers every POST with a canned body (and records the request), so the
wrapper's own JSON handling runs. Fixture: household zh (dev), each question in a fresh session, as native_daily.
Per case: questions whose block equals the base block, base blocks emptied, recall errors the base recorded.
"""
import io
import json
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

PLUGIN, SCR, WORK = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(SCR))
import daily_eval as d  # noqa: E402
import native_daily as nd  # noqa: E402
import recall_dump as rd  # noqa: E402

logging.disable(logging.CRITICAL)
BODY = {"value": b""}
SENT = []


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Opener:
    def open(self, req, timeout=None):
        sent = json.loads(req.data)
        SENT.append(sent)
        body = BODY["value"]
        return _Resp(body(sent) if callable(body) else body)


urllib.request.build_opener = lambda *a, **k: _Opener()

pkg = rd.load_plugin(rd.PLUGIN, SCR / "shim")
mod = nd.load_daily(PLUGIN)
mod.managed_local.wake = lambda *a, **k: None
WORK.mkdir(parents=True, exist_ok=True)
td = Path(tempfile.mkdtemp(prefix="probe-", dir=WORK))
os.environ["HERMES_HOME"] = str(td)
b = rd.open_provider(pkg, td / "f.db", td)
qs, _ = rd.build(pkg, b, "household", "zh")
b.shutdown()
fx = d.Fixture(SCR / "dump" / "dev" / "household-zh")


def provider(**extra):
    p = mod.SemanticHolographicProvider(config={
        "db_path": str(td / "f.db"), "embeddings": "off", "semantic_enabled": True,
        "semantic_url": "http://127.0.0.1:9", "semantic_timeout_ms": 400, **extra})
    p.initialize(session_id="fixture", hermes_home=str(td))
    return p


def ids_of(req):
    return req.get("ids") or []


CASES = {
    "control: valid old answer, no candidate": json.dumps({"candidates": []}).encode(),
    "JSON null": b"null",
    "JSON list": b"[]",
    "scores is a list": json.dumps({"candidates": [], "scores": [0.6]}).encode(),
    "scores are strings": lambda r: json.dumps({"candidates": [], "scores": {str(i): "0.6" for i in ids_of(r)}}).encode(),
    "first base fact NaN, rest 0.6": lambda r: json.dumps(
        {"candidates": [], "scores": {str(i): (float("nan") if k == 0 else 0.6) for k, i in enumerate(ids_of(r))}}
    ).encode(),
}

p = provider()
print("plugin:", PLUGIN)
for name, body in CASES.items():
    BODY["value"] = body
    same = emptied = errors = nonempty = 0
    for i, q in enumerate(qs):
        out = p.prefetch(q["q"], session_id=f"{name}-{i}")
        got = [int(x) for x in rd.ID.findall(out)]
        base = d.base(fx, i)
        nonempty += bool(base)
        same += got == base
        emptied += bool(base) and not got
        errors += bool(p._recall_error)
    print(f"  {name:42s} block==base {same:3d}/{len(qs)}  base blocks emptied {emptied:3d}/{nonempty}  "
          f"recall errors {errors}")
p.shutdown()

# Which text the veto embeds: a Telegram-style reply (the base strips the quote, _own_words).
BODY["value"] = json.dumps({"candidates": []}).encode()
p = provider()
i = next(k for k, q in enumerate(qs) if d.base(fx, k) and fx.q[k]["askable"])
quoted = '[Replying to Hermes: "' + "Your cat Barsik had his vaccination in March. " * 6 + '"]\n\n' + qs[i]["q"]
SENT.clear()
out = p.prefetch(quoted, session_id="quote")
got = [int(x) for x in rd.ID.findall(out)]
print("quoted reply: base block", d.base(fx, i), "-> block", got)
for r in SENT:
    print("  sidecar asked with", "ids" if r.get("ids") else "no ids", "| query == own words:", r["query"] == qs[i]["q"],
          "| query chars", len(r["query"]), "vs own words", len(qs[i]["q"]))
p.shutdown()
