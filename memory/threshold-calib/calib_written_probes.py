"""Thresholds picked from questions a model wrote from the store's own facts, against thresholds picked from
labelled questions people wrote. See CLOUD-FLOOR-RESULTS.md, the section on model-written probes.

A written question is a positive for its own fact and, asked again with that fact held out, a negative; the
built-in chit-chat lines are negatives too. No question enters a fact's vector text (the sidecar's
content + " " + tags). Selection is the built-in bank's own: calib_builtin_questions.select, rules N and Z.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

import calib_builtin_questions as bank
from calib_answerability import load_plugin
from calib_lexical_levers import REPO, build, open_provider, read_json
from calib_probes import CHIT
from calib_question_text import askable, encoder, facts_of, questions_by_id


def overlap(question, fact):
    """Share of the question's character pairs that the fact's text holds."""
    def pairs(text):
        flat = "".join(ch for ch in text.casefold() if ch.isalnum())
        return {flat[i:i + 2] for i in range(len(flat) - 1)}

    mine = pairs(question)
    return len(mine & pairs(fact)) / len(mine) if mine else 0.0


def written_rows(scores, own):
    """(top cosine, the top is the question's own fact, top cosine with that fact held out)."""
    held = np.delete(scores, own)
    return float(scores.max()), int(scores.argmax()) == own, float(held.max())


def pick(scores):
    chosen, _, bands = bank.select(scores)
    return {"N": chosen["N"], "Z": chosen["Z"], "N_bands": bands, "probes": len(scores),
            "negatives": sum(u for _, _, u in scores)}


def middle(values):
    return round(float(np.median(values)), 4) if values else None


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    encode = encoder(args.model)
    with tempfile.TemporaryDirectory(prefix="recall-written-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        source = home / "source.db"
        questions, _ = build(pkg, args, source, home, None)
        provider = open_provider(pkg, source, home)
        try:
            rows = facts_of(provider)
        finally:
            provider.shutdown()
        frozen = questions_by_id(pkg, args, rows, read_json(args.questions))
    ids = [f["fact_id"] for f in rows]
    text = {f["fact_id"]: f["content"] or "" for f in rows}
    matrix = encode([(f["content"] or "") + " " + (f["tags"] or "") for f in rows])

    def cosines(question):
        return matrix @ encode([question], 1)[0]  # one by one, as the sidecar's /candidates

    human, human_overlap = [], []
    for q in (q for q in questions if askable(pkg, q["q"])):
        scores = cosines(q["q"])
        human.append((float(scores.max()), ids[int(scores.argmax())] in q["targets"], not q["targets"]))
        if q["targets"]:
            human_overlap.append(max(overlap(q["q"], text[t]) for t in q["targets"]))
    chit = [(float(cosines(line).max()), False, True) for line in CHIT if askable(pkg, line)]
    probes = []  # (word overlap with its fact, top cosine, top is own, held-out cosine)
    for fact_id, mine in frozen.items():
        for question in mine:
            if askable(pkg, question):
                probes.append((overlap(question, text[fact_id]), *written_rows(cosines(question), ids.index(fact_id))))

    def written(some, holdouts=True):
        return ([(top, right, False) for _, top, right, _ in some]
                + ([(held, False, True) for _, _, _, held in some] if holdouts else []) + chit)

    cut = float(np.median([p[0] for p in probes]))
    low, high = [p for p in probes if p[0] <= cut], [p for p in probes if p[0] > cut]
    right_human = [c for c, right, _ in human if right]
    return {
        "suite": args.suite, "lang": args.lang, "facts": len(rows), "labelled_asked": len(human),
        "written_probes": len(probes), "chit": len(chit),
        "thresholds": {"labelled": pick(human), "written": pick(written(probes)),
                       "written, no hold-outs": pick(written(probes, False)),
                       "written, less word overlap": pick(written(low)) if low else None,
                       "written, more word overlap": pick(written(high)) if high else None},
        "distributions": {
            "labelled": {"closest_is_answer": f"{len(right_human)}/{sum(not u for _, _, u in human)}",
                         "median_cosine_when_right": middle(right_human),
                         "median_cosine_no_answer": middle([c for c, _, u in human if u]),
                         "no_answer_at_0.55": f"{sum(c >= 0.55 for c, _, u in human if u)}/{sum(u for _, _, u in human)}",
                         "median_word_overlap": middle(human_overlap)},
            "written": {"closest_is_own_fact": f"{sum(p[2] for p in probes)}/{len(probes)}",
                        "median_cosine_when_right": middle([p[1] for p in probes if p[2]]),
                        "median_cosine_held_out": middle([p[3] for p in probes]),
                        "held_out_at_0.55": f"{sum(p[3] >= 0.55 for p in probes)}/{len(probes)}",
                        "median_cosine_chit": middle([c for c, _, _ in chit]),
                        "median_word_overlap": round(cut, 4),
                        "less_overlap_median_word_overlap": middle([p[0] for p in low]),
                        "more_overlap_median_word_overlap": middle([p[0] for p in high]),
                        "less_overlap_median_cosine_when_right": middle([p[1] for p in low if p[2]]),
                        "more_overlap_median_cosine_when_right": middle([p[1] for p in high if p[2]])},
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True, choices=["synthetic", "household", "real"])
    ap.add_argument("--lang", default="zh", help="household language")
    ap.add_argument("--store", type=Path, help="frozen SQLite copy for --suite real, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labels for --suite real")
    ap.add_argument("--questions", type=Path, required=True, help="{fact key: [question, ...]} written from the facts")
    ap.add_argument("--model", type=Path, required=True, help="local sentence-transformers model directory")
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
