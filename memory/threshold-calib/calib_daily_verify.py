"""Daily shape, with the small cross-encoder on the one fact the sidecar would append.
See UPSTREAM-VERIFY-GATE-RESULTS.md, the section on the daily shape.

The base runs with embeddings off; the closest fact by cosine of content + " " + tags that is not shown yet is the
candidate (calib_cloud_floor.walk, local shape). Each candidate gets its cosine and the verifier's yes-minus-no
logit on the fact line as prefetch shows it, so any rule over the two can be counted afterwards.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from calib_answerability import INSTRUCTION, AnswerVerifier, load_plugin
from calib_cloud_floor import events, walk
from calib_lexical_levers import REPO, build, open_provider
from calib_question_text import encoder, facts_of


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    encode = encoder(args.model)
    with tempfile.TemporaryDirectory(prefix="recall-daily-verify-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        source = home / "source.db"
        questions, _ = build(pkg, args, source, home, None)
        provider = open_provider(pkg, source, home)
        try:
            rows = facts_of(provider)
        finally:
            provider.shutdown()
        matrix = encode([(f["content"] or "") + " " + (f["tags"] or "") for f in rows])
        cache = {}

        def qvec(text):
            if text not in cache:
                cache[text] = encode([text], 1)[0]
            return cache[text]

        walked = walk(pkg, source, home, "off", questions, top1=(rows, matrix, qvec))
    text = {f["fact_id"]: pkg._one_line(f["content"] or "") for f in rows}
    verifier = AnswerVerifier(args.verifier, INSTRUCTION)
    pairs = [(q, w) for q, w in zip(questions, walked) if w["candidate"]]
    out = []
    for (q, w), (cos, kind) in zip(pairs, events(questions, walked), strict=True):
        out.append({"cos": round(cos, 4), "kind": kind, "answerable": bool(q["targets"]),
                    "silent": not w["ids"], "logit": round(verifier.score(q["q"], text[w["candidate"][0]]), 3)})
    return {"suite": args.suite, "lang": args.lang, "questions": len(questions),
            "answerable": sum(bool(q["targets"]) for q in questions), "candidates": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True, choices=["synthetic", "household", "real"])
    ap.add_argument("--lang", default="zh", help="household language")
    ap.add_argument("--store", type=Path, help="frozen SQLite copy for --suite real, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labels for --suite real")
    ap.add_argument("--model", type=Path, required=True, help="local bge-m3 directory")
    ap.add_argument("--verifier", type=Path, required=True, help="local Qwen3-Reranker-0.6B directory")
    ap.add_argument("--plugin-src", type=Path, default=REPO / "vendor" / "holographic-0.30.0")
    ap.add_argument("--core-src", type=Path, required=True, help="Hermes core or the KG-1 core_shim")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.suite == "real" and not (args.store and args.queries):
        ap.error("real requires --store and --queries")
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    payload = json.dumps(run(args), ensure_ascii=True, indent=1)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
