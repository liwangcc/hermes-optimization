"""Dump everything a daily-shape recall rule can look at, per question, for offline replay.

Daily shape = Holographic 0.30.0 prefetch with embeddings off (lexical + entity streams), then the daily
wrapper's semantic step on bge-m3 cosines of `content + " " + tags` (the sidecar's vector text).

Per question: the base block as prefetch returned it (checked against a reconstruction from the components),
the 15 lexical candidates with their scores, coverage-gate admission at several thresholds, the entity facts,
askability, and names_fit for the facts a rule may add. Per fixture: unit vectors of three fact texts and of
every askable question, so rules can be replayed with numpy only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import runpy
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(r"C:\aiprojects\hermes-optimization")
sys.path.insert(0, str(REPO / "memory" / "threshold-calib"))
from calib_answerability import load_plugin  # noqa: E402
from calib_lexical_levers import ID, open_provider, read_json, store_fact  # noqa: E402
from calib_margin_verify import documents_for, public_facts  # noqa: E402
from calib_probes import labelled_probes  # noqa: E402

PLUGIN = REPO / "vendor" / "holographic-0.30.0"
SYNTHETIC = REPO / "issue95-evidence" / "synthetic"
COVERAGES = (0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)
NAMES_TOP = 30


def build(pkg, provider, suite, lang):
    """Store the fixture's facts; return (questions, fact key by id)."""
    keys = {}
    if suite == "synthetic":
        words = read_json(SYNTHETIC / "blind_keywords.json")
        for fact in sorted(read_json(SYNTHETIC / "facts.json"), key=lambda f: f["fact_id"]):
            fid = store_fact(provider, {"action": "add", "origin": "said", "content": fact["content"]},
                             words[str(fact["fact_id"])])
            keys[fid] = str(fact["fact_id"])
        known = set(keys)
        qs = [p for path in (SYNTHETIC / "queries.json", SYNTHETIC / "queries_ext.json")
              for p in labelled_probes(str(path), known)]
        return [{"qid": p["qid"], "q": p["q"], "targets": p["targets"], "category": p.get("category") or "real"}
                for p in qs], keys
    if suite == "household":
        data = runpy.run_path(str(PLUGIN / "tools" / "household.py"))
        words = read_json(PLUGIN / "tools" / "issue95_keywords" / "household.json")[lang]
        ids = {}
        for name, variants in data["FACTS"].items():
            content, entities = variants[lang]
            ids[name] = store_fact(provider, {"action": "add", "content": content, "entities": entities}, words[name])
            keys[ids[name]] = name
        return [{"qid": qid, "q": q[lang], "targets": [ids[n] for n in q.get("targets", [])],
                 "category": q.get("slice") or q.get("cat"), "split": q.get("split"),
                 "confusers": [ids[n] for n in q.get("confused", []) if n in ids]}
                for group in ("QUERIES", "CHITCHAT") for qid, q in data[group].items()], keys
    if suite == "two_topics":
        data = runpy.run_path(str(PLUGIN / "tools" / "two_topics_set.py"), run_name="two_topics_fixture")
        ids = {}
        for name, (content, names) in data["FACTS"].items():
            out = json.loads(provider.handle_tool_call(
                "fact_store", {"action": "add", "content": content, **({"entities": names} if names else {})}))
            ids[name] = int(out["fact_id"])
            keys[ids[name]] = name
        qs = [{"qid": qid, "q": text, "targets": [ids[t] for t in targets], "category": qid[0],
               "confusers": [ids[c] for c in confusers]} for qid, text, targets, confusers in data["QUERIES"]]
        qs += [{"qid": f"chit{i}", "q": text, "targets": [], "category": "chit"}
               for i, text in enumerate(data["CHITCHAT"])]
        return qs, keys
    # contrast_* and multi: the upstream public fixtures with their frozen keywords
    name = "multi" if suite == "multi" else suite
    docs = documents_for(public_facts(PLUGIN, name), name, lang)
    words = read_json(PLUGIN / "tools" / "issue95_keywords" / f"{name}.json")[lang]
    ids = {}
    for k, (content, entities) in docs.items():
        out = json.loads(provider.handle_tool_call(
            "fact_store", {"action": "add", "content": content, "entities": entities, "keywords": words[k]}))
        if out.get("status") != "added" or out.get("keywords", []) != words[k]:
            raise ValueError("a public fixture fact or its keywords did not pass indexing")
        ids[k] = int(out["fact_id"])
        keys[ids[k]] = k
    rows = (PLUGIN / "results" / f"provenance_{name}_m1_on.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [r for line in rows if (r := json.loads(line))["lang"] == lang]
    return [{"qid": r["qid"], "q": r["q"], "targets": [ids[t] for t in r["targets"]],
             "category": r.get("kind") or "real", "split": r.get("split")} for r in rows], keys


def encoder(model_dir, device):
    import torch
    from sentence_transformers import SentenceTransformer

    kw = {"torch_dtype": torch.float16} if device == "cuda" else {}
    model = SentenceTransformer(str(model_dir), device=device, local_files_only=True, model_kwargs=kw)

    def encode(texts, batch=16):
        return np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=batch,
                                       show_progress_bar=False), dtype=np.float32)
    return encode


def numeric(f):
    return {k: float(v) for k, v in f.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def components(pkg, provider, query):
    """The off layout, step by step, for a fresh session (nothing is recent)."""
    eff = pkg._own_words(query, provider._author.get("name", ""))[:pkg._PREFETCH_QUERY_CHARS]
    if not eff.strip():
        return eff, [], {}, [], []
    r = provider._retriever
    cands = r.search(eff, min_trust=provider._min_trust, limit=pkg._PREFETCH_CANDIDATES, meaning=None)
    admitted = {str(c): [f["fact_id"] for f in r.relevant(eff, cands, c)] for c in COVERAGES}
    gate = r.relevant(eff, cands, provider._min_coverage)
    fresh = [f for f in gate if provider._recallable(f)][:pkg._PREFETCH_FACTS]
    have = {f["fact_id"] for f in fresh}
    entity = []
    for entity_id in sorted(provider._store.mentioned_entity_ids(eff)):
        for fact in r.entity_facts(entity_id, min_trust=provider._min_trust, limit=pkg._ENTITY_FACTS * 3):
            if len(entity) < pkg._ENTITY_FACTS and fact["fact_id"] not in have and provider._recallable(fact):
                entity.append(fact)
                have.add(fact["fact_id"])
    lex = [{"id": f["fact_id"], **numeric(f)} for f in cands]
    return eff, lex, admitted, [f["fact_id"] for f in fresh], [f["fact_id"] for f in entity]


def run(args):
    pkg = load_plugin(PLUGIN, args.core_src)
    encode = encoder(args.model, args.device)
    with tempfile.TemporaryDirectory(prefix="recall-dump-") as td:
        home = Path(td)
        os.environ["HERMES_HOME"] = td
        provider = open_provider(pkg, home / "fixture.db", home)
        try:
            questions, keys = build(pkg, provider, args.suite, args.lang)
            facts = [dict(r) for r in provider._store.read(
                "SELECT fact_id, content, tags, trust_score FROM facts ORDER BY fact_id")]
            for f in facts:
                f["recallable"] = bool(provider._recallable(f))
                f["keywords"] = pkg._split_tags(f["tags"] or "")[1]
                f["key"] = keys.get(f["fact_id"])
            daily = [(f["content"] or "") + " " + (f["tags"] or "") for f in facts]
            content = [f["content"] or "" for f in facts]
            tags_only = [", ".join(f["keywords"]) if f["keywords"] else (f["content"] or "") for f in facts]
            mats = {"daily": encode(daily), "content": encode(content), "keywords": encode(tags_only)}
            qvecs = np.zeros((len(questions), mats["daily"].shape[1]), dtype=np.float32)
            mismatches = 0
            for i, q in enumerate(questions):
                text = q["q"]
                q["askable"] = bool(text) and not pkg.text.is_greeting(text) and \
                    pkg.embeddings.worth_asking(text, before_turn=True)
                eff, lex, admitted, fresh, entity = components(pkg, provider, text)
                block = provider.prefetch(text, session_id=f"dump-{i}")  # fresh session per question
                if provider._recall_error:
                    raise RuntimeError("prefetch failed")
                got = [int(x) for x in ID.findall(block)]
                q.update(eff=eff, lex=lex, admitted=admitted, fresh=fresh, entity=entity, block=got)
                mismatches += got != fresh + entity
                if q["askable"]:
                    qvecs[i] = encode([text], 1)[0]  # one by one, as the sidecar's /candidates
                    cos = mats["daily"] @ qvecs[i]
                    top = [int(j) for j in np.argsort(-cos)[:NAMES_TOP]]
                    look = {facts[j]["fact_id"] for j in top} | {c["id"] for c in lex}
                    by_id = {f["fact_id"]: f for f in facts}
                    q["names_fit"] = {str(fid): bool(provider._retriever.names_fit(text, by_id[fid]))
                                      for fid in sorted(look)}
                else:
                    q["names_fit"] = {}
            out = {"suite": args.suite, "lang": args.lang, "device": args.device, "facts": facts,
                   "questions": questions, "min_trust": provider._min_trust,
                   "min_coverage": provider._min_coverage, "reconstruction_mismatches": mismatches}
        finally:
            provider.shutdown()
    stem = args.out / f"{args.suite}-{args.lang}"
    stem.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    np.savez(stem.with_suffix(".npz"), query=qvecs, **mats)
    print(args.suite, args.lang, len(facts), "facts", len(questions), "questions", "mismatches", mismatches)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite", required=True,
                    choices=["synthetic", "household", "contrast_en", "contrast_ru", "contrast_zh", "multi",
                             "two_topics"])
    ap.add_argument("--lang", default="-")
    ap.add_argument("--model", type=Path, default=REPO / "vendor" / "models" / "bge-m3")
    ap.add_argument("--core-src", type=Path, required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.suite.startswith("contrast_"):
        args.lang = args.suite
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    args.out.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
