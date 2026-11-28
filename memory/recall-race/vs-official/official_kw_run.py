"""The official probe's main arm (embeddings on, margin 1.0, check off) on six sets, without and with the frozen
blind keywords, from the plugin checkout as it is. Starts the loopback bge-m3 endpoint itself and stops it after.
Usage: python -X utf8 -B memory/recall-race/vs-official/official_kw_run.py REPO_ROOT OUT_DIR
OUT_DIR gets nokw/ and kw/ (the probe's rows) and the logs; rows/ here is one such run.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
PLUGIN = ROOT / "vendor" / "holo-check" / "plugin"
KW = PLUGIN / "tools" / "issue95_keywords"
PORT = 12371
RUNS = [(["--set", "contrast_en"], "contrast_en.json"), (["--set", "contrast_ru"], "contrast_ru.json"),
        (["--set", "contrast_zh"], "contrast_zh.json"), (["--set", "household", "--split", "test"], "household.json"),
        (["--set", "household", "--split", "dev"], "household.json"), (["--set", "synthetic_zh"], "synthetic_zh.json")]
env = dict(os.environ, PYTHONIOENCODING="utf-8", HERMES_HOME=str(ROOT / "vendor/holo-check/sandbox-home"),
           HERMES_AGENT_REPO=str(ROOT / "vendor/holo-check/core-e8a31a1/memory/keyword-gate/core_shim"),
           EMB_URL=f"http://127.0.0.1:{PORT}/v1", EMB_MODEL="bge-m3")
OUT.mkdir(parents=True, exist_ok=True)
head = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=PLUGIN, capture_output=True, text=True)
sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PLUGIN, capture_output=True, text=True).stdout.strip()
print("plugin", sha[:12], "tracked files changed:", len(head.stdout.splitlines()), flush=True)

with (OUT / "endpoint.log").open("wb") as elog:
    endpoint = subprocess.Popen([sys.executable, "-E", "-B", str(ROOT / "memory/threshold-calib/embed_endpoint.py"),
                                 str(ROOT / "vendor/models/bge-m3"), str(PORT)], stdout=elog, stderr=subprocess.STDOUT)
    try:
        until = time.time() + 240
        while time.time() < until and endpoint.poll() is None:
            if b"ready" in (OUT / "endpoint.log").read_bytes():
                break
            time.sleep(1)
        else:
            raise SystemExit("the embedding endpoint did not get ready: " + str(OUT / "endpoint.log"))
        with socket.create_connection(("127.0.0.1", PORT), timeout=5):
            pass
        for arm in ("nokw", "kw"):
            (OUT / arm).mkdir(exist_ok=True)
            for args, kw in RUNS:
                cmd = [sys.executable, "-B", "tools/provenance_probe.py", "--emb", "on", "--modes", "off", "--repeats", "1",
                       "--endpoint", "http://127.0.0.1:12372/v1/rerank", "--out", str(OUT / arm), *args,
                       "--recall-check-margin", "off"] + (["--keywords", str(KW / kw)] if arm == "kw" else [])
                t = time.time()
                with (OUT / f"{arm}.log").open("ab") as log:
                    code = subprocess.run(cmd, cwd=PLUGIN, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
                print(arm, " ".join(args), "exit", code, f"{time.time() - t:.0f}s", flush=True)
                if code:
                    raise SystemExit(f"probe failed: see {OUT / (arm + '.log')}")
    finally:
        endpoint.terminate()
        endpoint.wait(timeout=30)
print("rows:", sorted(p.name for arm in ("nokw", "kw") for p in (OUT / arm).glob("*.jsonl")))
