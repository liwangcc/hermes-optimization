"""The upstream check switch (embeddings.RECALL_CHECK_MARGIN) on a frozen store with labelled questions: counts only.
See upstream-check/README.md.

The patched plugin runs its own embeddings path (vectors from EMB_URL / EMB_MODEL, as tools/provenance_probe.py
reads them) with rerank off. The second arm sets the switch: a fact offered below RECALL_MARGIN is kept only when
the cross-encoder at --endpoint says it answers the message. Both endpoints must be on this machine: a real store
is never sent elsewhere.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from calib_lexical_levers import ID, backup, record
from calib_probes import labelled_probes

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def ask(pp, store, queries, home, tag, check):
    pp._holographic_embeddings.RECALL_CHECK_MARGIN = check
    db = home / f"{tag}.db"
    backup(store.resolve(strict=True).as_uri() + "?mode=ro", db)
    provider = pp.make_provider(db, "off", "on")
    try:
        coverage = pp.catch_up_vectors(provider)
        known = {i for (i,) in provider._store.read("SELECT fact_id FROM facts")}
        questions = [p for path in queries for p in labelled_probes(str(path), known)]
        rows = []
        for i, q in enumerate(questions):
            block = provider.prefetch(q["q"], session_id=f"{tag}-{i}")
            if provider._recall_error:
                raise RuntimeError("prefetch failed")
            lines = [ln for ln in block.splitlines() if ID.match(ln)]
            rows.append(([int(ID.match(ln).group(1)) for ln in lines],
                         [int(ID.match(ln).group(1)) for ln in lines if "(by meaning)" in ln]))
        checker = provider._recall_check
        return questions, rows, coverage, (checker.calls, checker.failures) if checker else (0, 0)
    finally:
        provider.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plugin", type=Path, required=True, help="plugin checkout with the switch")
    ap.add_argument("--core-src", type=Path, required=True, help="Hermes core or the KG-1 core_shim")
    ap.add_argument("--store", type=Path, required=True, help="frozen SQLite copy, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", required=True, help="labelled questions for that copy")
    ap.add_argument("--endpoint", required=True, help="the cross-encoder's /v1/rerank address, on this machine")
    ap.add_argument("--scale", default="logit", choices=["logit", "unit"])
    ap.add_argument("--check-margin", type=float, default=0.5)
    args = ap.parse_args()
    for address in (os.environ.get("EMB_URL", ""), args.endpoint):
        if urlparse(address).hostname not in LOOPBACK:
            raise SystemExit("EMB_URL and --endpoint must both be loopback addresses: this store stays on the machine")
    logging.disable(logging.CRITICAL)
    sys.dont_write_bytecode = True
    os.environ["HERMES_AGENT_REPO"] = str(args.core_src.resolve(strict=True))
    sys.path.insert(0, str((args.plugin / "tools").resolve(strict=True)))
    with tempfile.TemporaryDirectory(prefix="recall-check-real-") as td:
        os.environ["HERMES_HOME"] = td
        import provenance_probe as pp  # after the environment it reads at import

        pp.ENDPOINT, pp.SCALE = args.endpoint, args.scale
        saved = pp._holographic_embeddings.RECALL_CHECK_MARGIN
        try:
            questions, base, coverage, _ = ask(pp, args.store, args.queries, Path(td), "default", None)
            _, got, _, calls = ask(pp, args.store, args.queries, Path(td), "checked", args.check_margin)
        finally:
            pp._holographic_embeddings.RECALL_CHECK_MARGIN = saved
    totals = {name: Counter() for name in ("default", "checked")}
    meaning = {name: Counter(right=0, wrong=0) for name in totals}
    for q, (before, meant_before), (after, meant_after) in zip(questions, base, got, strict=True):
        totals["default"].update(record(q, before, before))
        totals["checked"].update(record(q, before, after))
        for name, meant in (("default", meant_before), ("checked", meant_after)):
            meaning[name].update(right=len(set(meant) & set(q["targets"])), wrong=len(set(meant) - set(q["targets"])))
    print(json.dumps({"facts_with_vectors": coverage.get("vectors"), "questions": len(questions),
                      "check_margin": args.check_margin, "checker_calls": calls[0], "checker_failures": calls[1],
                      "default": dict(totals["default"]), "checked": dict(totals["checked"]),
                      "by_meaning": {k: dict(v) for k, v in meaning.items()}}, indent=1))


if __name__ == "__main__":
    main()
