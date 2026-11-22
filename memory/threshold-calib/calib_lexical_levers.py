"""Lexical-only prefetch: sweep prefetch_min_coverage and compare keyword sets. See LEXICAL-LEVERS-RESULTS.md.

Embeddings stay off, so every displayed fact comes from the word and entity streams. Each arm runs on its own
copy of the fixture, with a fresh session per question. For --suite real only counts leave the process.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import runpy
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from calib_answerability import load_plugin
from calib_probes import labelled_probes

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC = REPO / "issue95-evidence" / "synthetic"
ID = re.compile(r"^- #(\d+) ", re.MULTILINE)
DEFAULT_COVERAGE = 0.30


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def backup(source, target):
    with closing(sqlite3.connect(source, uri=str(source).startswith("file:"))) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def open_provider(pkg, db, home, **config):
    provider = pkg.HolographicMemoryProvider(config={"db_path": str(db), "embeddings": "off", **config})
    provider.initialize(session_id="fixture", hermes_home=str(home))
    if provider._store is None or provider._embedder is not None:
        raise ValueError("could not open the fixture with embeddings off")
    return provider


def store_fact(provider, call, words):
    result = json.loads(provider.handle_tool_call("fact_store", {**call, "keywords": words}))
    if result.get("keywords", []) != words or not (result.get("fact_id") or result.get("updated")):
        raise ValueError("the plugin did not keep a fact or its keywords as written")
    return result.get("fact_id")


def build(pkg, args, db, home, keywords):
    """Fill *db* with the suite's facts carrying *keywords* (None: the suite's own) and return its questions."""
    if args.suite == "real":
        backup(args.store.resolve(strict=True).as_uri() + "?mode=ro", db)
    provider = open_provider(pkg, db, home)
    try:
        if args.suite == "household":
            data = runpy.run_path(str(args.plugin_src / "tools" / "household.py"))
            words = keywords or read_json(args.plugin_src / "tools" / "issue95_keywords" / "household.json")[args.lang]
            ids = {}
            for name, variants in data["FACTS"].items():
                content, entities = variants[args.lang]
                ids[name] = store_fact(provider, {"action": "add", "content": content, "entities": entities},
                                       words[name])
            questions = [{"qid": qid, "category": q.get("slice") or q.get("cat"), "q": q[args.lang],
                          "targets": [ids[n] for n in q.get("targets", [])]}
                         for group in ("QUERIES", "CHITCHAT") for qid, q in data[group].items()]
        else:
            if args.suite == "synthetic":
                words = keywords or read_json(SYNTHETIC / "blind_keywords.json")
                for fact in sorted(read_json(SYNTHETIC / "facts.json"), key=lambda f: f["fact_id"]):
                    call = {"action": "add", "origin": "said", "content": fact["content"]}
                    if store_fact(provider, call, words[str(fact["fact_id"])]) != fact["fact_id"]:
                        raise ValueError("the synthetic store differs from the labelled fixture")
                files = [SYNTHETIC / "queries.json", SYNTHETIC / "queries_ext.json"]
            else:
                for fact_id, mine in (keywords or {}).items():
                    store_fact(provider, {"action": "update", "fact_id": int(fact_id)}, mine)
                files = args.queries
            known = {i for (i,) in provider._store.read("SELECT fact_id FROM facts")}
            questions = [p for path in files for p in labelled_probes(str(path), known)]
        counts = [len(pkg._split_tags(tags or "")[1]) for (tags,) in provider._store.read("SELECT tags FROM facts")]
        return questions, {"facts": len(counts), "keywords": sum(counts)}
    finally:
        provider.shutdown()


def ask(pkg, source, home, tag, coverage, questions):
    db = home / f"{tag}.db"
    backup(source, db)  # recall writes counters: no arm reads another arm's
    provider = open_provider(pkg, db, home, prefetch_min_coverage=coverage)
    try:
        if provider._min_coverage != coverage:
            raise ValueError("the plugin did not take prefetch_min_coverage")
        rows = []
        for i, q in enumerate(questions):
            block = provider.prefetch(q["q"], session_id=f"{tag}-{i}")
            if provider._recall_error:
                raise RuntimeError("prefetch failed")
            rows.append([int(x) for x in ID.findall(block)])
        return rows
    finally:
        provider.shutdown()


def record(q, base, got):
    """One row against the default arm. Non-targets are counted per displayed fact, not per row."""
    gold, before, after = set(q["targets"]), set(base[:5]), set(got[:5])
    had, has = bool(before & gold), bool(after & gold)
    return Counter(
        rows=1,
        labelled=bool(gold),
        hit=has,
        rescued=has and not had,
        lost_rows=had and not has,
        lost_targets=len((before & gold) - after),
        noise=not gold and bool(got),
        confusion=bool(gold and after - gold),
        shown_other=len(set(got) - gold),
        added_other=len(set(got) - set(base) - gold),
        removed_other=len(set(base) - set(got) - gold),
    )


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    sets = [("current", None)] + ([("alt", read_json(args.keywords_alt))] if args.keywords_alt else [])
    out = {"suite": args.suite, "lang": args.lang, "plugin": args.plugin_src.name, "arms": []}
    with tempfile.TemporaryDirectory(prefix="recall-lexical-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        results = {}
        for name, keywords in sets:
            source = home / f"source-{name}.db"
            questions, size = build(pkg, args, source, home, keywords)
            out[f"{name}_keywords"] = size
            for coverage in args.coverage:
                results[name, coverage] = ask(pkg, source, home, f"{name}-{coverage}", coverage, questions)
        base = results["current", DEFAULT_COVERAGE]
        for (name, coverage), rows in results.items():
            groups = defaultdict(Counter)
            lost = []
            for q, before, got in zip(questions, base, rows, strict=True):
                counts = record(q, before, got)
                groups["all"].update(counts)
                groups[q.get("category") or "real"].update(counts)
                if counts["lost_targets"] and args.suite != "real":
                    lost.append(q["qid"])
            total = groups["all"]
            # Decided before any run: worth having = fewer displayed non-targets and no target lost.
            worth = total["shown_other"] < sum(len(set(b) - set(q["targets"])) for q, b in zip(questions, base)) \
                and not total["lost_targets"]
            out["arms"].append({"keywords": name, "coverage": coverage, "worth_having": worth, "lost_qids": lost,
                                "groups": {k: dict(v) for k, v in groups.items()}})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True, choices=["synthetic", "household", "real"])
    ap.add_argument("--lang", default="zh", help="household language")
    ap.add_argument("--store", type=Path, help="frozen SQLite copy for --suite real, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labels for --suite real")
    ap.add_argument("--keywords-alt", type=Path, help="{fact key: [keyword, ...]} that replaces every fact's keywords")
    ap.add_argument("--coverage", type=float, nargs="+", default=[0.30, 0.35, 0.40, 0.45, 0.50])
    ap.add_argument("--plugin-src", type=Path, default=REPO / "vendor" / "holographic-0.30.0")
    ap.add_argument("--core-src", type=Path, required=True, help="Hermes core or the KG-1 core_shim")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.suite == "real" and not (args.store and args.queries):
        ap.error("real requires --store and --queries")
    if DEFAULT_COVERAGE not in args.coverage:
        ap.error("the default coverage 0.30 is the reference arm")
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    payload = json.dumps(run(args), ensure_ascii=True, indent=1)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
