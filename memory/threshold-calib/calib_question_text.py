"""Short questions written with each fact: in the vector text only, or also stored as keywords.
See QUESTION-TEXT-RESULTS.md.

The base runs with embeddings off, as in the daily local mode; one fact is then appended on local cosines, either
by the daily rule (the closest fact, cosine >= tau, not shown) or by the two-margin z rule. Vector texts follow the
sidecar: content + " " + tags. Frozen questions come from --questions ({fact key: [question, ...]}).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import runpy
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from calib_answerability import load_plugin
from calib_lexical_levers import ID, REPO, backup, build, open_provider, read_json, record, store_fact

TEXTS = ("keywords", "keywords+questions", "questions-as-keywords")
RULES = ("top1", "two-margin")
SWEEP = (0.45, 0.50, 0.55, 0.60, 0.65)


def encoder(model_dir):
    """The sidecar's own loading: fp16 on CUDA, local files only, float32 unit vectors."""
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(model_dir.resolve(strict=True)), device=device, local_files_only=True,
                                model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {})

    def encode(texts, batch=16):
        return np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=batch,
                                       show_progress_bar=False), dtype=np.float32)
    return encode


def facts_of(provider):
    return [dict(r) for r in provider._store.read("SELECT fact_id, content, tags, trust_score FROM facts ORDER BY fact_id")]


def questions_by_id(pkg, args, facts, frozen):
    """Frozen questions keyed by fact_id. Household files are keyed by fact name: match on the text."""
    if args.suite == "household":
        data = runpy.run_path(str(args.plugin_src / "tools" / "household.py"))
        names = {variants[args.lang][0]: name for name, variants in data["FACTS"].items()}
        frozen = {f["fact_id"]: frozen[names[f["content"]]] for f in facts}
    else:
        frozen = {int(k): v for k, v in frozen.items()}
    if set(frozen) != {f["fact_id"] for f in facts} or not all(frozen.values()):
        raise ValueError("every fact needs its own frozen question")
    return frozen


def as_keywords(pkg, source, target, home, frozen):
    """A copy of the store whose facts also carry their questions as keywords. Returns keywords displaced by the
    plugin's limit of 12 per fact."""
    backup(source, target)
    provider = open_provider(pkg, target, home)
    displaced = 0
    try:
        for fact in facts_of(provider):
            own, mine = pkg._split_tags(fact["tags"] or "")[1], frozen[fact["fact_id"]]
            kept = own[:max(0, 12 - len(mine))]
            displaced += len(own) - len(kept)
            store_fact(provider, {"action": "update", "fact_id": fact["fact_id"]}, kept + mine)
        return facts_of(provider), displaced
    finally:
        provider.shutdown()


def askable(pkg, text):
    return bool(text) and not pkg.text.is_greeting(text) and pkg.embeddings.worth_asking(text, before_turn=True)


def append(pkg, provider, session, query, have, scores, rows, rule, tau):
    """The one fact to add after the base's block, or None."""
    if scores is None or len(have) >= 7:  # semantic_total_cap
        return None
    key = f"{session}|{provider._scope_key or ''}"
    turn = provider._turns.get(key, 0)

    def fits(fact):
        return (provider._not_recent(key, fact, turn) and provider._recallable(fact)
                and provider._retriever.names_fit(query, fact))

    trusted = [(f["fact_id"], s) for f, s in zip(rows, scores) if f["trust_score"] >= provider._min_trust]
    if rule == "top1":  # the daily wrapper: only the closest fact is examined, no replacement
        fact_id, score = max(trusted, key=lambda item: item[1], default=(None, 0.0))
        fact = next((f for f in rows if f["fact_id"] == fact_id), None)
        return fact_id if fact and score >= tau and fact_id not in have and fits(fact) else None
    meaning = pkg.embeddings.Meaning([f["fact_id"] for f in rows], scores.tolist(), 0.0)
    offered = provider._retriever.by_meaning(meaning, exclude=have, min_trust=provider._min_trust, limit=4,
                                             margin=0.5 if have else 0.7)
    return next((f["fact_id"] for f in offered if fits(f)), None)


def ask(pkg, source, home, tag, questions, rows=None, scores=None, rule=None, tau=0.55):
    db = home / f"{tag}.db"
    backup(source, db)
    provider = open_provider(pkg, db, home)
    out = []
    try:
        for i, q in enumerate(questions):
            session = f"{tag}-{i}"
            block = provider.prefetch(q["q"], session_id=session)
            if provider._recall_error:
                raise RuntimeError("prefetch failed")
            got = [int(x) for x in ID.findall(block)]
            if rule:
                extra = append(pkg, provider, session, q["q"], set(got), scores[i], rows, rule, tau)
                got += [] if extra is None else [extra]
            out.append(got)
        return out
    finally:
        provider.shutdown()


def nearest(questions, rows, scores, tau):
    """Threshold-free view: is the closest fact an answer, per question type."""
    groups = defaultdict(Counter)
    for q, s in zip(questions, scores):
        if s is None:
            continue
        top = int(np.argmax(s))
        right = rows[top]["fact_id"] in q["targets"]
        for name in ("all", q.get("category") or "real"):
            groups[name].update(asked=1, answerable=bool(q["targets"]), nearest_is_answer=right,
                                over_tau=bool(s[top] >= tau), over_tau_right=bool(right and s[top] >= tau),
                                over_tau_no_answer=bool(not q["targets"] and s[top] >= tau))
        for point in SWEEP:  # a text changes the score scale: compare the texts at every threshold, not at one
            if s[top] >= point:
                groups["sweep"][f"{'right' if right else 'wrong'}@{point:.2f}"] += 1
    return {k: dict(v) for k, v in groups.items()}


def totals(questions, base, got):
    groups = defaultdict(Counter)
    for q, before, after in zip(questions, base, got, strict=True):
        counts = record(q, before, after)
        groups["all"].update(counts)
        groups[q.get("category") or "real"].update(counts)
    return {k: dict(v) for k, v in groups.items()}


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    encode = encoder(args.model)
    with tempfile.TemporaryDirectory(prefix="recall-questions-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        plain = home / "source-plain.db"
        questions, size = build(pkg, args, plain, home, None)
        provider = open_provider(pkg, plain, home)
        try:
            rows = facts_of(provider)
        finally:
            provider.shutdown()
        frozen = questions_by_id(pkg, args, rows, read_json(args.questions))
        stored = home / "source-questions.db"
        stored_rows, displaced = as_keywords(pkg, plain, stored, home, frozen)
        if [f["fact_id"] for f in stored_rows] != [f["fact_id"] for f in rows]:
            raise ValueError("the two stores hold different facts")

        def sidecar_text(fact):
            return (fact["content"] or "") + " " + (fact["tags"] or "")

        texts = {
            "keywords": [sidecar_text(f) for f in rows],
            "keywords+questions": [sidecar_text(f) + " " + " ".join(frozen[f["fact_id"]]) for f in rows],
            "questions-as-keywords": [sidecar_text(f) for f in stored_rows],
        }
        asked = [askable(pkg, q["q"]) for q in questions]
        vectors = {i: encode([q["q"]], 1)[0] for i, q in enumerate(questions) if asked[i]}  # one by one, as /candidates
        base = ask(pkg, plain, home, "off", questions)
        out = {"suite": args.suite, "lang": args.lang, "plugin": args.plugin_src.name, "tau": args.tau,
               "facts": size["facts"], "questions": len(questions), "asked": sum(asked),
               "frozen_questions": sum(len(v) for v in frozen.values()), "displaced_keywords": displaced,
               "nearest": {}, "arms": {"off": totals(questions, base, base)}}
        # What storing the questions as keywords does to the word stream alone.
        out["arms"]["off/questions-as-keywords"] = totals(questions, base, ask(pkg, stored, home, "off-stored", questions))
        for name in TEXTS:
            matrix = encode(texts[name])
            scores = [matrix @ vectors[i] if asked[i] else None for i in range(len(questions))]
            source, facts = (stored, stored_rows) if name == "questions-as-keywords" else (plain, rows)
            out["nearest"][name] = nearest(questions, facts, scores, args.tau)
            for rule in RULES:
                got = ask(pkg, source, home, f"{name}-{rule}".replace("+", "_"), questions, facts, scores, rule, args.tau)
                out["arms"][f"{name}/{rule}"] = totals(questions, base, got)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True, choices=["synthetic", "household", "real"])
    ap.add_argument("--lang", default="zh", help="household language")
    ap.add_argument("--store", type=Path, help="frozen SQLite copy for --suite real, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labels for --suite real")
    ap.add_argument("--questions", type=Path, required=True, help="frozen {fact key: [question, ...]}")
    ap.add_argument("--model", type=Path, required=True, help="local bge-m3 directory")
    ap.add_argument("--tau", type=float, default=0.55)
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
