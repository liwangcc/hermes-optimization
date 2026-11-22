"""Run the real daily plugin against the real sidecar service on a fixture, and compare with the offline replay.

The fixture store is built exactly as recall_dump.py builds it (so fact ids match the dump). The sidecar is
managed_server.py started as a child process on a free localhost port (CUDA when available unless --cpu).
The wrapper is SemanticHolographicProvider loaded from --plugin-dir; Hermes core is the KG-1 shim plus two stubs.
Reports per-question equality with the offline rule, prefetch latency, sidecar time and the sidecar's GPU memory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recall_dump as rd  # noqa: E402
import daily_eval as d  # noqa: E402

REPO = rd.REPO
DAILY = REPO / "memory" / "plugin" / "holographic-semantic"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(url, path, body=None, timeout=60):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def gpu_used_mib():
    """Whole-GPU memory in use (Windows WDDM does not report per-process use)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def load_daily(plugin_dir):
    spec = importlib.util.spec_from_file_location("holographic_semantic", plugin_dir / "__init__.py",
                                                  submodule_search_locations=[str(plugin_dir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(args):
    pkg = rd.load_plugin(rd.PLUGIN, args.shim)
    daily_mod = load_daily(args.plugin_dir)
    daily_mod.managed_local.wake = lambda *a, **k: None
    if args.no_rescue:  # P1: the silent-block rescue never fires
        daily_mod._Z_RESCUE = float("inf")
    td = Path(tempfile.mkdtemp(prefix="native-daily-", dir=args.work))
    os.environ["HERMES_HOME"] = str(td)
    db = td / "fixture.db"
    builder = rd.open_provider(pkg, db, td)
    try:
        questions, _ = rd.build(pkg, builder, args.suite, args.lang)
    finally:
        builder.shutdown()
    port = free_port()
    env = {**os.environ, "SEMANTIC_DB": str(db), "SEMANTIC_MODEL": str(args.model), "SEMANTIC_PORT": str(port),
           "SEMANTIC_CACHE": str(td / "cache"), "SEMANTIC_STORE_ID": "native-test", "SEMANTIC_DIM": "1024",
           "SEMANTIC_MODEL_ID": args.model_id,
           "PYTHONIOENCODING": "utf-8"}
    if args.cpu:
        env["CUDA_VISIBLE_DEVICES"] = "-1"  # Windows drops empty variables
    log = open(td / "sidecar.log", "w", encoding="utf-8")
    gpu_before = gpu_used_mib()
    server = subprocess.Popen([sys.executable, "-B", str(args.server)], env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        t0 = time.perf_counter()
        while True:
            try:
                if call(url, "/health", timeout=2).get("ok"):
                    break
            except OSError:
                pass
            if server.poll() is not None or time.perf_counter() - t0 > 300:
                raise RuntimeError("sidecar did not start; see " + str(td / "sidecar.log"))
            time.sleep(0.5)
        boot = time.perf_counter() - t0
        t1 = time.perf_counter()
        synced = call(url, "/sync", {}, timeout=600)
        index_s = time.perf_counter() - t1
        cfg = {"db_path": str(db), "embeddings": "off", "semantic_enabled": True, "semantic_url": url,
               "semantic_tau": args.tau, "semantic_timeout_ms": args.timeout_ms}
        provider = daily_mod.SemanticHolographicProvider(config=cfg)
        provider.initialize(session_id="fixture", hermes_home=str(td))
        sidecar_ms = []
        original = provider._sidecar_candidates

        def timed(*a):
            s = time.perf_counter()
            try:
                return original(*a)
            finally:
                sidecar_ms.append((time.perf_counter() - s) * 1000)
        provider._sidecar_candidates = timed
        blocks, times = [], []
        try:
            for i, q in enumerate(questions):
                s = time.perf_counter()
                out = provider.prefetch(q["q"], session_id=f"native-{i}")
                times.append((time.perf_counter() - s) * 1000)
                blocks.append([int(x) for x in rd.ID.findall(out)])
        finally:
            provider.shutdown()
        after = gpu_used_mib()
        mem = None if gpu_before is None or after is None else after - gpu_before
    finally:
        server.terminate()
        server.wait(timeout=30)
        log.close()
    result = {"suite": args.suite, "lang": args.lang, "device": "cpu" if args.cpu else "cuda",
              "questions": len(questions), "sidecar_boot_s": round(boot, 2), "index_s": round(index_s, 2),
              "indexed": synced.get("facts_indexed"), "sidecar_gpu_mib": mem}
    for name, vals in (("prefetch_ms", times), ("sidecar_call_ms", sidecar_ms)):
        if vals:
            result[name] = {k: round(float(np.percentile(vals, p)), 1) for k, p in
                            (("p50", 50), ("p95", 95), ("max", 100))}
    result["over_3000_ms"] = sum(t > 3000 for t in times)
    result["sidecar_over_400_ms"] = sum(t > 400 for t in sidecar_ms)
    if args.compare:
        fx = d.Fixture(args.compare)
        rule = d.daily
        if args.rule_file:
            spec = importlib.util.spec_from_file_location("frozen_rule", args.rule_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            rule = mod.rule
        if [q["qid"] for q in fx.q] != [q["qid"] for q in questions]:
            raise ValueError("dump and native fixture hold different questions")
        offline = [rule(fx, i) for i in range(len(fx.q))]
        diff = [i for i, (a, b) in enumerate(zip(offline, blocks)) if a != b]
        result["offline_equal"] = len(questions) - len(diff)
        result["offline_diff"] = [{"qid": questions[i]["qid"], "offline": offline[i], "native": blocks[i]}
                                  for i in diff[:20]]
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "offline_diff"}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True)
    ap.add_argument("--lang", default="-")
    ap.add_argument("--shim", type=Path, default=HERE / "shim", help="core_shim of e8a31a1 plus shim-extra/")
    ap.add_argument("--plugin-dir", type=Path, default=DAILY)
    ap.add_argument("--server", type=Path, default=DAILY / "managed_server.py")
    ap.add_argument("--model", type=Path, default=REPO / "vendor" / "models" / "bge-m3")
    ap.add_argument("--tau", type=float, default=0.55)
    ap.add_argument("--timeout-ms", type=int, default=10000)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--model-id", default="bge-m3", help="the id the sidecar reports (gates the new fields)")
    ap.add_argument("--no-rescue", action="store_true", help="patched plugin with the rescue off (rule P1)")
    ap.add_argument("--compare", type=Path, help="dump stem to compare with, e.g. dump/dev/household-zh")
    ap.add_argument("--rule-file", type=Path, help="offline rule to compare with (default: daily 0.6.0)")
    ap.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()), help="temporary stores (outside the repo)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.suite.startswith("contrast_"):
        args.lang = args.suite
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    args.work.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
