"""Is the daily version working on this machine? The synthetic set through the installed plugins, counts only.

Run it with the Python Hermes itself runs in (after `source ./activate` in the Hermes checkout): recall uses that
interpreter's packages. It reports whether the stemmer is there and hit@5 on words and entities alone: 29 of 36 is
the reference, 26 means snowballstemmer is missing. With --sidecar-python and --model-dir it also starts a copy of
the manual sidecar (memory/sidecar/server.py) on the same 30 facts and reports its device, how long it takes
against the plugin's budget, how often recall gave up on it, and hit@5 with the closest fact appended: 33 of 36 is
the reference for BGE-M3 at 0.55 on CUDA. Everything runs in a temporary home: the user's store and settings are
not read. --out writes the report to a file; --verify reads such a report and says whether it counts as a
standard result and matches the reference. See docs/test-standard.md.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import platform
import re
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from calib_probes import labelled_probes

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC = REPO / "issue95-evidence" / "synthetic"
WRAPPER = REPO / "memory" / "plugin" / "holographic-semantic"
SERVER = REPO / "memory" / "sidecar" / "server.py"
FACT_LINE = re.compile(r"^- #(\d+) \[", re.MULTILINE)
HTTP = build_opener(ProxyHandler({}))  # a local address never goes through a proxy
WORDS, WORDS_UNSTEMMED, CLOSEST = 29, 26, 33  # hit@5 of 36: the references in docs/test-standard.md
STANDARD = "daily-check-1"  # a new name whenever the facts, the questions or the references below change
FILES = ("facts.json", "blind_keywords.json", "queries.json", "queries_ext.json")
REFERENCE = {  # the questions with no target in the first five, by (stemmer, step): the same with or without numpy
    (True, "words_only"): ["P5", "P7", "P10", "C1", "C5", "C6", "C10"],
    (False, "words_only"): ["P5", "P7", "P10", "X4", "X5", "X7", "C1", "C5", "C6", "C10"],
    (True, "closest_fact"): ["P5", "P10", "C6"],
    (False, "closest_fact"): ["P5", "P10", "X4", "C6"],
}


def data_id() -> str:
    """The facts, their keywords and the questions as parsed: the same whatever the checkout's line endings."""
    parsed = [json.loads((SYNTHETIC / name).read_text(encoding="utf-8")) for name in FILES]
    return hashlib.sha256(json.dumps(parsed, sort_keys=True, ensure_ascii=True).encode()).hexdigest()[:12]


def load_wrapper(core: Path, base: Path, home: Path):
    """The wrapper as Hermes loads it, from copies of the two plugins in a temporary home."""
    os.environ["HERMES_HOME"] = str(home)
    sys.path.insert(0, str(core.resolve(strict=True)))
    ignore = shutil.ignore_patterns("__pycache__", ".git", "tests", "docs", "results", "diagram")
    shutil.copytree(base, home / "plugins" / "holographic", ignore=ignore)
    shutil.copytree(WRAPPER, home / "plugins" / "holographic-semantic", ignore=ignore)
    (home / "config.yaml").write_text("memory:\n  provider: holographic-semantic\n", encoding="utf-8")
    from plugins.memory import import_provider_module

    return import_provider_module("holographic-semantic")


def build_store(wrapper, home: Path, target: Path) -> None:
    """The 30 synthetic facts with their frozen keywords, written through the base's own tool."""
    provider = wrapper._orig.HolographicMemoryProvider(config={"db_path": str(target), "embeddings": False})
    provider.initialize(session_id="check", hermes_home=str(home))
    try:
        keywords = json.loads((SYNTHETIC / "blind_keywords.json").read_text(encoding="utf-8"))
        facts = json.loads((SYNTHETIC / "facts.json").read_text(encoding="utf-8"))
        for fact in sorted(facts, key=lambda f: f["fact_id"]):
            call = {"action": "add", "origin": "said", "content": fact["content"],
                    "keywords": keywords[str(fact["fact_id"])]}
            if json.loads(provider.handle_tool_call("fact_store", call)).get("fact_id") != fact["fact_id"]:
                raise RuntimeError("the synthetic store differs from the labelled set")
    finally:
        provider.shutdown()


def copy(source: Path, target: Path) -> Path:
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    return target


def ask(wrapper, db: Path, home: Path, probes: list[dict], url: str | None = None):
    """(the fact ids each question gets in a session of its own, how often the sidecar was given up on, the
    plugin's budget for it in milliseconds)."""
    provider = wrapper.SemanticHolographicProvider(config={
        "db_path": str(db), "embeddings": False, "rerank": False, "semantic_enabled": url is not None,
        **({"semantic_url": url} if url else {})})
    provider.initialize(session_id="check", hermes_home=str(home))
    rows, gave_up = [], 0
    try:
        for i, probe in enumerate(probes):
            provider._sem_warned = False  # set when a request fails or runs over the budget
            block = provider.prefetch(probe["q"], session_id=f"check-{i}")
            if provider._recall_error:
                raise RuntimeError("prefetch failed")
            gave_up += provider._sem_warned
            rows.append([int(n) for n in FACT_LINE.findall(block)])
        return rows, gave_up, provider._sem_timeout * 1000
    finally:
        provider.shutdown()


def score(probes: list[dict], rows: list[list[int]]) -> dict:
    answerable = [(p["qid"], set(p["targets"]), got) for p, got in zip(probes, rows) if p["targets"]]
    missed = [qid for qid, gold, got in answerable if not gold & set(got[:5])]
    return {"hit5": len(answerable) - len(missed), "of": len(answerable), "missed": missed,
            "first": sum(bool(got) and got[0] in gold for _, gold, got in answerable)}


def findings(stemmer: bool, words: dict, closest: dict | None) -> list[str]:
    """What to fix, in the order to fix it. Empty: nothing found."""
    out = []
    if not stemmer:
        out.append("snowballstemmer is missing from this Python: install snowballstemmer==3.1.1 into it, or run "
                   f"Hermes's own Python. Words alone then reach {WORDS} of 36 instead of {WORDS_UNSTEMMED}.")
    elif words["hit5"] != WORDS:
        out.append(f"words alone give {words['hit5']} of 36, not {WORDS}: the base plugin differs from 0.30.0.")
    if closest is None:
        out.append("the closest-fact step was not checked: pass --sidecar-python and --model-dir.")
    elif closest["gave_up"]:
        out.append(f"recall gave up on the sidecar for {closest['gave_up']} questions (budget "
                   f"{closest['budget_ms']:.0f} ms, slowest answer {closest['ms_max']:.0f} ms): raise "
                   "plugins.hermes-memory-store.semantic_timeout_ms above the slowest answer.")
    elif closest["hit5"] <= words["hit5"]:
        out.append("the sidecar answered but added no hit: check the model directory is BGE-M3.")
    return out


def verify(report: dict) -> dict:
    """Whether a report is a standard result that matches the reference for its machine (with or without the
    stemmer), what keeps it from being one, and what that machine has to fix."""
    if report.get("standard") != {"name": STANDARD, "data": data_id()}:
        return {"standard_result": False, "to_fix": [], "problems": [
            f"not {STANDARD}: made by another version of this script, or on other facts and questions."]}
    out = []
    for step in ("words_only", "closest_fact"):
        got = report[step]
        if got is None:
            continue  # findings() says the step was not run
        if got["of"] != 36 or got["hit5"] + len(got["missed"]) != got["of"]:
            out.append(f"{step}: the counts do not add up.")
        want = set(REFERENCE[bool(report["stemmer"]), step])
        more, fewer = sorted(set(got["missed"]) - want), sorted(want - set(got["missed"]))
        if more or fewer:
            out.append(f"{step}: misses {more} that the reference finds, finds {fewer} that the reference misses.")
    return {"standard_result": not out, "problems": out,
            "to_fix": findings(report["stemmer"], report["words_only"], report["closest_fact"])}


def post(url: str, route: str, body: dict | None = None, timeout: float = 60):
    data = None if body is None else json.dumps(body).encode()
    with HTTP.open(Request(url + route, data=data, headers={"Content-Type": "application/json"}),
                   timeout=timeout) as response:
        return json.load(response)


@contextmanager
def sidecar(python: Path, model_dir: Path, db: Path, root: Path):
    """The manual sidecar on *db*, ready and indexed: its address and /health."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "SEMANTIC_DB": str(db), "SEMANTIC_MODEL": str(model_dir), "SEMANTIC_PORT": str(port),
           "SEMANTIC_CACHE": str(root / "cache")}
    (root / "cache").mkdir()
    with (root / "sidecar.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(python), "-B", str(SERVER)], env=env, cwd=root, stdout=log,
                                   stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 600  # loading BGE-M3 on a CPU takes a while
            while True:
                try:
                    health = post(url, "/health", timeout=2)
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        tail = (root / "sidecar.log").read_text(encoding="utf-8", errors="replace")[-600:]
                        raise SystemExit(f"the sidecar did not start with {python}:\n{tail}") from None
                    time.sleep(0.5)
            if not health["ok"]:
                raise SystemExit(f"the sidecar could not load the model at {model_dir}: {health['error']}")
            post(url, "/sync", {}, timeout=600)
            yield url, post(url, "/health")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def run(args, home: Path) -> dict:
    stemmer = importlib.util.find_spec("snowballstemmer") is not None
    wrapper = load_wrapper(args.core_src, args.base_src, home)
    source = home / "source.db"
    build_store(wrapper, home, source)
    with closing(sqlite3.connect(source)) as conn:
        known = {i for (i,) in conn.execute("SELECT fact_id FROM facts")}
    probes = [p for name in ("queries.json", "queries_ext.json") for p in labelled_probes(str(SYNTHETIC / name), known)]
    rows, _, budget = ask(wrapper, copy(source, home / "words.db"), home, probes)
    words = score(probes, rows)
    closest = None
    if args.sidecar_python:
        db = copy(source, home / "closest.db")
        with sidecar(args.sidecar_python, args.model_dir, db, home) as (url, health):
            asked = [p["q"] for p in probes if not wrapper._orig_text.is_greeting(p["q"])
                     and wrapper._orig.embeddings.worth_asking(p["q"], before_turn=True)]
            times = []
            for query in asked:  # the request the plugin sends, timed from this side
                start = time.perf_counter()
                post(url, "/candidates", {"query": query, "tau": 0.55, "limit": 1, "min_trust": 0.3})
                times.append((time.perf_counter() - start) * 1000)
            got, gave_up, budget = ask(wrapper, db, home, probes, url)
        closest = {**score(probes, got), "device": health["device"], "facts_indexed": health["facts_indexed"],
                   "requests": len(asked), "ms_median": round(statistics.median(times), 1),
                   "ms_max": round(max(times), 1), "budget_ms": budget, "gave_up": gave_up,
                   "appended": sum(len(after) > len(before) for before, after in zip(rows, got))}
    return {"standard": {"name": STANDARD, "data": data_id()},
            "platform": platform.platform(), "python": platform.python_version(), "stemmer": stemmer,
            # with numpy the base plugin also ranks by structure: hit@5 is the same, first place moves by one question
            "numpy": importlib.util.find_spec("numpy") is not None,
            "wrapper": re.search(r"^version:\s*(\S+)", (WRAPPER / "plugin.yaml").read_text(encoding="utf-8"),
                                 re.MULTILINE).group(1),
            "words_only": words, "closest_fact": closest, "to_fix": findings(stemmer, words, closest)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--core-src", type=Path, help="the patched Hermes checkout")
    ap.add_argument("--base-src", type=Path, help="the Holographic 0.30.0 checkout")
    ap.add_argument("--sidecar-python", type=Path, help="the Python of the sidecar's environment (it has torch)")
    ap.add_argument("--model-dir", type=Path, help="the local BGE-M3 directory the sidecar loads")
    ap.add_argument("--out", type=Path, help="also write the report to this file, to send it as it is")
    ap.add_argument("--verify", type=Path, help="check a report made with --out instead of running anything")
    args = ap.parse_args()
    if args.verify:
        print(json.dumps(verify(json.loads(args.verify.read_text(encoding="utf-8"))), indent=1))
        return
    if not (args.core_src and args.base_src):
        ap.error("--core-src and --base-src are required")
    if bool(args.sidecar_python) != bool(args.model_dir):
        ap.error("--sidecar-python and --model-dir go together")
    if args.model_dir:
        args.model_dir = args.model_dir.resolve(strict=True)  # the sidecar starts in the temporary home
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="hermes-daily-check-") as td:
        report = json.dumps(run(args, Path(td).resolve()), ensure_ascii=True, indent=1)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
