"""Pick model thresholds on the built-in natural questions, then test transfer through wrapper prefetch.

Use the 0.6.0 wrapper and a daily Holographic/Core checkout. The frozen real store and the query
file are first opened after every model's thresholds have been selected on the synthetic corpus.
The managed sidecar runs offline on loopback with the files pinned by the wrapper. JSON lines contain
only model metadata, thresholds, and aggregate counts. Stores and vector indexes live in a temporary profile.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from operator import itemgetter
from pathlib import Path
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

import numpy as np

from calib_probes import labelled_probes

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC = REPO / "issue95-evidence" / "synthetic"
WRAPPER = REPO / "memory" / "plugin" / "holographic-semantic"
GRID = range(5, 100)
FACT_LINE = re.compile(r"^- #(\d+) \[", re.MULTILINE)
HTTP = build_opener(ProxyHandler({}))


def emit(**data):
    print(json.dumps(data, allow_nan=False), flush=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def backup(source, target):
    with closing(sqlite3.connect(source.resolve(strict=True).as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def synthetic_store(wrapper, home, target):
    provider = wrapper._orig.HolographicMemoryProvider(config={"db_path": str(target), "embeddings": False})
    provider.initialize(session_id="fixture", hermes_home=str(home))
    try:
        keywords = read_json(SYNTHETIC / "blind_keywords.json")
        for fact in sorted(read_json(SYNTHETIC / "facts.json"), key=itemgetter("fact_id")):
            words = keywords[str(fact["fact_id"])]
            result = json.loads(provider.handle_tool_call("fact_store", {
                "action": "add", "origin": "said", "content": fact["content"], "keywords": words,
            }))
            if result.get("fact_id") != fact["fact_id"] or result.get("keywords") != words:
                raise ValueError("the synthetic store differs from the labelled fixture")
    finally:
        provider.shutdown()


def frozen_store(source, target):
    # Copy the frozen WAL with the main file so even SQLite's shared-memory files stay in the sandbox.
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        copy = Path(tmp) / "frozen.db"
        for suffix in ("", "-wal", "-journal"):
            file = source.with_name(source.name + suffix)
            if not suffix or file.is_file():
                shutil.copyfile(file, copy.with_name(copy.name + suffix))
        backup(copy, target)


def load_queries(db, query_files, expected):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        ids = {row[0] for row in conn.execute("SELECT fact_id FROM facts")}
    try:
        probes = [p for file in query_files for p in labelled_probes(str(file), ids)]
    except SystemExit:
        raise ValueError("query labels don't match the fixture") from None
    actual = (len(ids), len(probes), sum(bool(p["targets"]) for p in probes))
    if actual != expected or len({p["qid"] for p in probes}) != len(probes):
        raise ValueError(f"unexpected fixture counts {actual}, expected {expected}")
    return probes, ids


def askable(wrapper, query):
    return (bool(query) and not wrapper._orig_text.is_greeting(query)
            and wrapper._orig.embeddings.worth_asking(query, before_turn=True))


def call(url, endpoint, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    request = Request(url + endpoint, data=data, headers={"Content-Type": "application/json"})
    with HTTP.open(request, timeout=timeout) as response:
        return json.load(response)


@contextmanager
def sidecar(wrapper, root, db, weights, model, count):
    root.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = wrapper.local_artifacts.runtime_env(root)
    env.update(SEMANTIC_DB=str(db), SEMANTIC_MODEL=str(weights), SEMANTIC_CACHE=str(root / "vectors"),
               SEMANTIC_PORT=str(port), SEMANTIC_STORE_ID="sandbox", SEMANTIC_MODEL_ID=model.id,
               SEMANTIC_MODEL_REV=model.rev, SEMANTIC_DIM=str(model.dim), HF_HUB_OFFLINE="1",
               TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    server = Path(wrapper.__file__).with_name("managed_server.py")
    with (root / "sidecar.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(server)], env=env, cwd=root, stdout=log,
                                   stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 120
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    health = call(url, "/health", timeout=1)
                except OSError:
                    time.sleep(0.25)
                    continue
                break
            else:
                raise RuntimeError(f"{model.id} sandbox sidecar did not start")
            if not health["ok"] or (health["model"], health["revision"], health["dim"]) != (model.id, model.rev, model.dim):
                raise RuntimeError(f"{model.id} sandbox sidecar failed its pinned-model check")
            index = call(url, "/sync", {}, timeout=600)
            if index["embedded"] != count or index["facts_indexed"] != count:
                raise RuntimeError(f"{model.id} sandbox sidecar did not index the fixture")
            yield url, root / "vectors" / "vectors.npz", health["device"]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def top_scores(wrapper, url, cache, facts, probes):
    # /sync indexed the actual content + " " + tags. Ask /embed one question at a time
    # and compare full float32 cosines, as /candidates does before rounding its response.
    with np.load(cache) as stored:
        vectors = {int(key): stored[key] for key in stored.files}
    if vectors.keys() != facts:
        raise ValueError("the synthetic vector index does not cover every fact")
    scores = []
    for probe in probes:
        text, targets = probe["q"], probe["targets"]
        if askable(wrapper, text):
            query = np.asarray(call(url, "/embed", {"texts": [text]})["vectors"][0], dtype=np.float32)
            fact, cosine = max(((fact_id, float(vector @ query)) for fact_id, vector in vectors.items()),
                               key=itemgetter(1))
            if not math.isfinite(cosine):
                raise ValueError("non-finite cosine")
            scores.append((cosine, fact in targets, not targets))
    return scores


def select(scores):
    grid = {}
    for point in GRID:
        tau = point / 100
        admitted = [(correct, unanswerable) for cosine, correct, unanswerable in scores if cosine >= tau]
        true = sum(correct for correct, _ in admitted)
        false = len(admitted) - true
        grid[point] = {"tau": tau, "correct": true, "incorrect": false, "unanswerable": sum(u for _, u in admitted)}
    gain = max(c["correct"] - c["incorrect"] for c in grid.values())
    bands = []
    for point, counts in grid.items():
        if counts["correct"] - counts["incorrect"] != gain:
            continue
        if bands and bands[-1][-1] + 1 == point:
            bands[-1].append(point)
        else:
            bands.append([point])
    # Use the longest tied interval. Equal lengths and half-step midpoints round toward the higher threshold.
    band = max(bands, key=lambda b: (len(b), b[0]))
    n = grid[band[len(band) // 2]]
    z = next((counts for counts in grid.values() if counts["unanswerable"] == 0), None)
    return {"N": n, "Z": z}, gain, [[b[0] / 100, b[-1] / 100] for b in bands]


def prefetch(wrapper, db, home, probes, url, tau, eligible):
    provider = wrapper.SemanticHolographicProvider(config={
        "db_path": str(db), "embeddings": False, "rerank": False,
        "semantic_enabled": tau is not None, "semantic_tau": tau if tau is not None else 0.55, "semantic_url": url,
    })
    provider.initialize(session_id="fixture", hermes_home=str(home))
    rows = []
    try:
        if provider._store is None or provider._embedding or provider._rescorer:
            raise RuntimeError("could not initialize the sandbox provider in local mode")
        with patch.object(provider, "_sidecar_candidates", wraps=provider._sidecar_candidates) as requests:
            for i, probe in enumerate(probes):
                block = provider.prefetch(probe["q"], session_id=f"fixture-{i}")
                if provider._recall_error or provider._sem_warned:
                    raise RuntimeError("sandbox prefetch failed")
                rows.append([int(i) for i in FACT_LINE.findall(block)])
        if requests.call_count != (eligible if tau is not None else 0):
            raise RuntimeError("sandbox prefetch did not exercise the expected sidecar requests")
    finally:
        provider.shutdown()
    return rows


def summarize(probes, baseline, rows):
    out = dict(hit=0, rescued=0, lost=0, lost_targets=0, noise=0, confusion=0, extra_other=0)
    for probe, before, after in zip(probes, baseline, rows, strict=True):
        targets = set(probe["targets"])
        left, current = set(before[:5]), set(after[:5])
        had, has = bool(targets & left), bool(targets & current)
        out["hit"] += has
        out["rescued"] += has and not had
        out["lost"] += had and not has
        out["lost_targets"] += len((targets & left) - current)
        out["noise"] += not targets and bool(after)
        out["confusion"] += bool(targets and current - targets)
        out["extra_other"] += len(set(after) - set(before) - targets)
    return out


def evaluate(wrapper, model, db, root, probes, url, device, chosen):
    eligible = sum(askable(wrapper, p["q"]) for p in probes)
    arms = {"off": None, **{rule: counts["tau"] for rule, counts in chosen.items() if counts is not None}}
    results = {}
    for arm, tau in arms.items():
        store = root / f"{arm}.db"
        backup(db, store)
        rows = prefetch(wrapper, store, root, probes, url, tau, eligible)
        if arm == "off":
            baseline = rows
        results[arm] = summarize(probes, baseline, rows)
        emit(phase="prefetch", dataset=db.parent.name, model=model.id, device=device, rule=arm, tau=tau,
             questions=len(probes), answerable=sum(bool(p["targets"]) for p in probes),
             query_gate_skips=len(probes) - eligible if tau is not None else None, **results[arm])
    return results


def prepare_weights(wrapper, reuse_home, cache, model, target):
    steps = wrapper.local_artifacts.prepare_model(reuse_home, cache, model)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            source = done.value
            break
    # Give the loader only the verified files, including when the source is an existing installation.
    for name in model.files:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)


def run(args, home):
    os.environ["HERMES_HOME"] = str(home)
    sys.path.insert(0, str(args.core_src.resolve(strict=True)))
    logging.disable(logging.CRITICAL)
    plugins = home / "plugins"
    ignore = shutil.ignore_patterns("__pycache__", ".git", "tests", "docs", "results", "diagram")
    shutil.copytree(args.base_src, plugins / "holographic", ignore=ignore)
    shutil.copytree(WRAPPER, plugins / "holographic-semantic", ignore=ignore)
    (home / "config.yaml").write_text("memory:\n  provider: holographic-semantic\n", encoding="utf-8")
    from plugins.memory import import_provider_module

    wrapper = import_provider_module("holographic-semantic")
    if (Path(wrapper.__file__).parent != plugins / "holographic-semantic"
            or Path(wrapper._orig.__file__).parent != plugins / "holographic"):
        raise RuntimeError("the provider loader escaped the sandbox")
    models = wrapper.local_models.MODELS
    weights = {m.id: home / "models" / m.id for m in models}
    for model in models:
        prepare_weights(wrapper, args.reuse_home or home, args.weights_dir or home / "weights", model, weights[model.id])

    synth = home / "synthetic" / "source.db"
    synth.parent.mkdir()
    synthetic_store(wrapper, home, synth)
    probes, facts = load_queries(synth, [SYNTHETIC / "queries.json", SYNTHETIC / "queries_ext.json"], (30, 48, 36))
    chosen = {}
    for model in models:
        root = synth.parent / model.id
        with sidecar(wrapper, root, synth, weights[model.id], model, len(facts)) as (url, cache, device):
            scores = top_scores(wrapper, url, cache, facts, probes)
            chosen[model.id], gain, bands = select(scores)
            emit(phase="selection", model=model.id, revision=model.rev, pinned_files=len(model.files),
                 device=device, eligible=len(scores), eligible_unanswerable=sum(u for _, _, u in scores),
                 choices=chosen[model.id], n_net=gain, n_bands=bands)
            evaluate(wrapper, model, synth, root, probes, url, device, chosen[model.id])

    emit(phase="thresholds_fixed", models=len(chosen))
    real = home / "real" / "source.db"
    real.parent.mkdir()
    frozen_store(args.store, real)
    probes, facts = load_queries(real, [args.queries], (54, 54, 44))
    results = {}
    for model in models:
        root = real.parent / model.id
        with sidecar(wrapper, root, real, weights[model.id], model, len(facts)) as (url, _, device):
            results[model.id] = evaluate(wrapper, model, real, root, probes, url, device, chosen[model.id])
    for rule in ("N", "Z"):
        counts = [result[rule] for result in results.values() if rule in result]
        passed = sum(0 < c["rescued"] and not c["lost_targets"] and c["extra_other"] <= c["rescued"] for c in counts)
        emit(phase="judgement", rule=rule, passed_models=passed, total_models=len(models))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--core-src", type=Path, required=True, help="Hermes Core checkout for the plugin loader")
    parser.add_argument("--base-src", type=Path, required=True, help="daily Holographic base provider directory")
    parser.add_argument("--store", type=Path, required=True, help="frozen real SQLite copy")
    parser.add_argument("--queries", type=Path, required=True, help="labels for that frozen real copy")
    parser.add_argument("--weights-dir", type=Path, help="optional directory for the verified pinned weights")
    parser.add_argument("--reuse-home", type=Path, help="look here for an existing pinned BGE-M3, read-only")
    sys.dont_write_bytecode = True
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-builtin-questions-") as root:
        run(args, Path(root).resolve())


if __name__ == "__main__":
    main()
