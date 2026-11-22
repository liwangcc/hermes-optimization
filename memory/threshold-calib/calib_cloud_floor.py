"""Cloud mode on natural questions: what the official admission lets in without a floor, what the fragment
job would suggest, and a marginal-gain rule for the closest-fact admission. See CLOUD-FLOOR-RESULTS.md.

Vectors come from a local model or, after an estimate and --yes, from an OpenAI-compatible endpoint
(calib_dump.vectors_by). They are injected at the base's _meaning_of, so its word blend, z gate, entity stream
and name checks run as shipped. A real store is never sent to a remote endpoint.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

import calib_dump
import calib_vendor
from calib_answerability import load_plugin
from calib_lexical_levers import ID, REPO, backup, build, open_provider
from calib_question_text import append, askable, facts_of, totals

JOB = REPO / "memory" / "plugin" / "holographic-semantic" / "threshold_calib.py"
GRID = range(5, 100)  # hundredths


def walk(pkg, source, home, tag, questions, official=None, top1=None):
    """One fresh session per question. *official* (ids, matrix, qvec, min_score) turns the base's own embeddings
    path on with injected vectors. *top1* (rows, matrix, qvec) also names the closest fact the daily rule would
    append at any threshold, with its cosine."""
    db = home / f"{tag}.db"
    backup(source, db)
    provider = open_provider(pkg, db, home)
    if official:
        ids, matrix, qvec, min_score = official
        provider._embedding = pkg.embeddings.Settings(
            {"embeddings": "on", **({} if min_score is None else {"embedding_min_score": min_score})})

        def lookup(text, *, before_turn):
            if pkg._secret_in(text or "") or not pkg.embeddings.worth_asking(text, before_turn=before_turn):
                return None
            return pkg.embeddings.Meaning(ids, (matrix @ qvec(text)).tolist(), provider._embedding.weight)

        provider._meaning_of = lookup
    out = []
    try:
        for i, q in enumerate(questions):
            session = f"{tag}-{i}"
            block = provider.prefetch(q["q"], session_id=session)
            if provider._recall_error:
                raise RuntimeError("prefetch failed")
            lines = [ln for ln in block.splitlines() if ID.match(ln)]
            got = [int(ID.match(ln).group(1)) for ln in lines]
            row = {"ids": got, "meant": [g for g, ln in zip(got, lines) if "(by meaning)" in ln], "candidate": None}
            if top1 and askable(pkg, q["q"]):
                rows, vectors, qvec1 = top1
                scores = vectors @ qvec1(q["q"])
                fact_id = append(pkg, provider, session, q["q"], set(got), scores, rows, "top1", -1.0)
                if fact_id is not None:
                    row["candidate"] = (fact_id, float(scores[[f["fact_id"] for f in rows].index(fact_id)]))
            out.append(row)
        return out
    finally:
        provider.shutdown()


def meaning_counts(questions, walked):
    """What the base's own meaning stream added: per fact, and per no-answer question."""
    counts = Counter(by_meaning=0, by_meaning_right=0, by_meaning_wrong=0, no_answer_rows_with_meaning=0,
                     no_answer_rows_only_meaning=0)
    for q, w in zip(questions, walked):
        gold, meant = set(q["targets"]), set(w["meant"])
        counts.update(by_meaning=len(meant), by_meaning_right=len(meant & gold), by_meaning_wrong=len(meant - gold),
                      no_answer_rows_with_meaning=bool(not gold and meant),
                      no_answer_rows_only_meaning=bool(not gold and meant and meant == set(w["ids"])))
    return dict(counts)


def fragment_probes(v, job, sendable):
    eligible = {f["fact_id"] for f in sendable if f["trust_score"] is not None and f["trust_score"] >= 0.3}
    recallable = {f["fact_id"] for f in sendable if not v.screen._role_prompt(f["content"] or "")}
    pool = {f["fact_id"]: f["content"] or "" for f in sendable if f["fact_id"] in eligible & recallable}
    sets = job.probe_sets(pool, lambda t: not v.screen._secret_in(t) and v.emb.worth_asking(t, before_turn=True))
    return pool, sets, eligible, recallable


def fragment_job(v, job, sendable, matrix, qvec, probes):
    """threshold_job._cloud_rule and run() of the wrapper, with the vectors supplied here."""
    pool, sets, eligible, recallable = probes
    if len(pool) < job.MIN_FACTS or not job.enough(sets):
        return {"status": "too few facts", "pool": len(pool)}
    keep = v.emb.Settings({}).recall_facts
    ids, vectors = [f["fact_id"] for f in sendable], [row.tolist() for row in matrix]

    def scored(vector, holdout):
        ranked = job.ranked(vector, ids, vectors, holdout)
        return v.emb.Meaning([i for i, _ in ranked], [s for _, s in ranked], 0.0), ranked

    def admit(scored_, min_score):
        meaning, ranked = scored_
        picked = []
        for fact_id, _ in ranked:
            if not meaning.standout(fact_id, v.emb.RECALL_MARGIN, min_score):
                break
            if fact_id in eligible:
                picked.append(fact_id)
                if len(picked) >= keep + 3:
                    break
        return [i for i in picked if i in recallable][:keep]

    draws = [[(p, scored(qvec(p["q"]).tolist(), p["holdout"])) for p in group] for group in sets]
    found = job.pick(draws, admit, (None, *job.GRID))
    return {"pool": len(pool), "found": found, "no_floor": [job.measure(d, admit, None) for d in draws],
            "at_0.55": [job.measure(d, admit, 0.55) for d in draws]}


def events(questions, walked):
    """(cosine, kind) of every question whose closest fact is not shown yet: a rescue (the row had no target in its
    five), an extra target, or a wrong fact."""
    out = []
    for q, w in zip(questions, walked):
        if w["candidate"] is None:
            continue
        fact_id, cos = w["candidate"]
        gold = set(q["targets"])
        kind = "wrong" if fact_id not in gold else "extra" if gold & set(w["ids"][:5]) or len(w["ids"]) >= 5 else "rescue"
        out.append((cos, kind))
    return out


def curve(found):
    return {k: (sum(c >= k / 100 and kind == "rescue" for c, kind in found),
                sum(c >= k / 100 and kind == "wrong" for c, kind in found)) for k in GRID}


def choose(points):
    """Rule M, frozen in cloud-floor-freeze.json: the threshold with the most rescued questions minus wrong facts
    added. Ties: the longest run of grid points, the higher run among equals, its midpoint (the higher of two).
    The model adds something only when that net is at least 1 on at least 2 rescued questions."""
    best = max(r - w for r, w in points.values())
    bands = []
    for k, (r, w) in points.items():
        if r - w != best:
            continue
        if bands and bands[-1][-1] + 1 == k:
            bands[-1].append(k)
        else:
            bands.append([k])
    band = max(bands, key=lambda b: (len(b), b[0]))
    k = band[len(band) // 2]
    r, w = points[k]
    return {"tau": k / 100, "rescued": r, "wrong": w, "net": best, "gain": best >= 1 and r >= 2,
            "bands": [[b[0] / 100, b[-1] / 100] for b in bands]}


def choose_m2(points):
    """Rule M2, written after M failed its check on the bank and before any household run: the lowest threshold
    where the wrong facts added do not outnumber the rescued questions and at least 2 are rescued. None: the
    model adds nothing."""
    for k, (r, w) in points.items():
        if r >= 2 and w <= r:
            return {"tau": k / 100, "rescued": r, "wrong": w}
    return None


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    v = calib_vendor.load(args.plugin_src)
    spec = importlib.util.spec_from_file_location("wrapper_threshold_calib", JOB)
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    with tempfile.TemporaryDirectory(prefix="recall-cloud-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        source = home / "source.db"
        questions, size = build(pkg, args, source, home, None)
        provider = open_provider(pkg, source, home)
        try:
            rows = facts_of(provider)
        finally:
            provider.shutdown()
        sendable = [f for f in rows if pkg._sendable(f["content"] or "")]
        cloud_texts = [pkg.embeddings.vector_text(f["content"], f["tags"]) for f in sendable]  # the base's own text
        local_texts = [(f["content"] or "") + " " + (f["tags"] or "") for f in rows]  # the sidecar's
        probes = fragment_probes(v, job, sendable)
        asked = list(dict.fromkeys(t for q in questions
                                   for t in (q["q"], pkg._own_words(q["q"], "")[:pkg._PREFETCH_QUERY_CHARS])))
        fragments = [p["q"] for group in probes[1] for p in group]
        local = "local" in args.modes
        encode, model, where = calib_dump.vectors_by(
            v, args, cloud_texts + (local_texts if local else []) + asked + fragments)
        if where == "remote" and args.suite == "real":
            raise SystemExit("a real store is not sent to a remote endpoint")
        cache = {}

        def qvec(text):
            if text not in cache:
                cache[text] = encode([text], 1)[0]
            return cache[text]

        cloud = encode(cloud_texts, pkg.embeddings.BATCH)
        ids = [f["fact_id"] for f in sendable]
        off = walk(pkg, source, home, "off", questions, top1=(rows, encode(local_texts, 16), qvec) if local else None)
        official = walk(pkg, source, home, "official", questions, (ids, cloud, qvec, None), (sendable, cloud, qvec))
        base = [w["ids"] for w in off]
        out = {"suite": args.suite, "lang": args.lang, "plugin": args.plugin_src.name, "model": model,
               "endpoint": where, "facts": size["facts"], "vectors": len(sendable), "questions": len(questions),
               "step1": {"off": totals(questions, base, base)["all"],
                         "official": totals(questions, base, [w["ids"] for w in official])["all"],
                         "by_meaning": meaning_counts(questions, official)},
               "step2": fragment_job(v, job, sendable, cloud, qvec, probes), "step3": {}}
        suggested = (out["step2"].get("found") or {}).get("value")
        if suggested is not None:
            floored = walk(pkg, source, home, "floor", questions, (ids, cloud, qvec, suggested))
            out["step1"]["official_with_suggested_floor"] = {
                **totals(questions, base, [w["ids"] for w in floored])["all"], **meaning_counts(questions, floored)}
        for floor in args.floors:  # embedding_min_score on natural questions: which admissions a floor removes
            floored = walk(pkg, source, home, f"floor-{floor}", questions, (ids, cloud, qvec, floor))
            out["step1"].setdefault("floors", {})[f"{floor:.2f}"] = meaning_counts(questions, floored)
        for mode, walked in (("cloud", official), *((("local", off),) if local else ())):
            found = events(questions, walked)
            points = curve(found)
            asked_of = [q for q, w in zip(questions, walked) if w["candidate"]]
            quiet = [cos for (cos, kind), q in zip(found, asked_of) if kind == "wrong" and not q["targets"]]
            out["step3"][mode] = {"candidates": dict(Counter(kind for _, kind in found)), "choice": choose(points),
                                  "choice_m2": choose_m2(points),
                                  # per question, for rates by message mix; a real store gives counts only
                                  "events": [] if args.suite == "real" else [
                                      [round(cos, 4), kind, bool(q["targets"])] for (cos, kind), q in zip(found, asked_of)],
                                  "curve": {f"{k / 100:.2f}": list(rw) for k, rw in points.items()},
                                  # wrong facts on no-answer questions, for calib_model_tau's check on a store
                                  "wrong_no_answer": {f"{k / 100:.2f}": sum(c >= k / 100 for c in quiet) for k in GRID}}
    return out


def main():
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True, choices=["synthetic", "household", "real"])
    ap.add_argument("--lang", default="zh", help="household language")
    ap.add_argument("--store", type=Path, help="frozen SQLite copy for --suite real, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labels for --suite real")
    ap.add_argument("--modes", nargs="+", choices=["cloud", "local"], default=["cloud", "local"],
                    help="rule M on the base's vectors (cloud) and on the sidecar's text (local)")
    ap.add_argument("--floors", type=float, nargs="*", default=[0.50, 0.55, 0.60, 0.65],
                    help="embedding_min_score values to try on the official path")
    ap.add_argument("--st-model", default=env("BGE_MODEL"), help="a local sentence-transformers model (env BGE_MODEL)")
    ap.add_argument("--embed-url", default=env("EMBED_URL"), help="the /v1 base address (env EMBED_URL)")
    ap.add_argument("--embed-model", default=env("EMBED_MODEL"), help="the model id (env EMBED_MODEL)")
    ap.add_argument("--embed-key-env", default=env("EMBED_KEY_ENV"), help="the NAME of the variable holding the key")
    ap.add_argument("--embed-dimensions", default=env("EMBED_DIMENSIONS"), help="the plugin's embedding_dimensions")
    ap.add_argument("--price-per-mtok", type=float, help="USD per million tokens, for a remote model not listed")
    ap.add_argument("--yes", action="store_true", help="send to a remote endpoint after the estimate")
    ap.add_argument("--stub", action="store_true", help="the offline deterministic embedder: plumbing only")
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
