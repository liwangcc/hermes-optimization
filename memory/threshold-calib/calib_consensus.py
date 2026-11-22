"""CPU-only paired recall experiment. See CONSENSUS-RESULTS.md for commands and data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import re
import runpy
import tempfile
import time
from types import SimpleNamespace

import numpy as np

from calib_answerability import load_plugin, open_fixture
from calib_consensus_rule import KeywordIndex, background_floors
from calib_margin_verify import public_facts, documents_for
from calib_probes import labelled_probes
from calib_squad_fixture import squad_fixture


REPO = Path(__file__).resolve().parents[2]
ARMS = ("agreement", "both", "shown", "silent")
ID = re.compile(r"^- #(\d+) ", re.MULTILINE)


def public_data(root, suite, lang, squad):
    if suite == "squad":
        return squad_fixture(squad)
    keywords = json.loads((root / "tools" / "issue95_keywords" / f"{suite}.json").read_text(encoding="utf-8"))[lang]
    if suite == "household":
        data = runpy.run_path(str(root / "tools" / "household.py"))
        documents = {k: v[lang] for k, v in data["FACTS"].items()}
        questions = [{"q": q[lang], "qid": i, "targets": q.get("targets", []), "split": q["split"]}
                     for group in ("QUERIES", "CHITCHAT") for i, q in data[group].items()]
    else:
        documents = documents_for(public_facts(root, suite), suite, lang)
        rows = (root / "results" / f"provenance_{suite}_m1_on.jsonl").read_text(encoding="utf-8").splitlines()
        questions = [r for line in rows if (r := json.loads(line))["lang"] == lang]
    return documents, keywords, questions


def build_fixture(pkg, args, tmp):
    synthetic = REPO / "issue95-evidence" / "synthetic"
    cfg = SimpleNamespace(store=args.store, facts=None)
    if args.suite == "synthetic":
        cfg.facts = synthetic / "facts.json"
        cfg.keywords = synthetic / "blind_keywords.json"
    provider = open_fixture(pkg, cfg, tmp)
    try:
        if args.suite in ("synthetic", "real"):
            paths = [synthetic/"queries.json", synthetic/"queries_ext.json"] if cfg.facts else args.queries
            ids = {i for (i,) in provider._store.read("SELECT fact_id FROM facts")}
            questions = [{**q, "split": "all"} for path in paths for q in labelled_probes(path, ids)]
        else:
            docs, keywords, questions = public_data(args.plugin_src, args.suite, args.lang, args.squad)
            stored = {}
            for name, (content, entities) in docs.items():
                call = dict(action="add", content=content, entities=entities, keywords=keywords[name])
                result = json.loads(provider.handle_tool_call("fact_store", call))
                if (result.get("status") != "added" or result.get("keywords", []) != keywords[name]
                        or not pkg._sendable(content)):
                    raise ValueError("a public fixture fact or its keywords did not pass indexing")
                stored[name] = result["fact_id"]
            questions = [{**q, "targets": [stored[k] for k in q["targets"]]} for q in questions]
        return provider, questions
    except Exception:
        provider.shutdown()
        raise


def data_from_store(pkg, provider):
    facts, raw, joined, keys = [], [], [], []
    for r in provider._store.read("SELECT fact_id, content, tags FROM facts ORDER BY fact_id"):
        i, text, tags = r
        if not pkg._sendable(text):
            continue
        words = pkg._split_tags(tags or "")[1]
        expanded = f"{text}\nkeywords: {', '.join(words)}"
        if not words or not pkg._sendable(expanded):
            words, expanded = [], text
        facts.append((i, text, words))
        raw.append(text)
        joined.append(expanded)
        keys.append(", ".join(words) if words else text)
    return facts, raw, joined, keys


def record(q, base, point):
    gold, before, after = set(q["targets"]), set(base[:5]), set(point[:5])
    had, has = bool(before & gold), bool(after & gold)
    added = set(point) - set(base)
    return Counter(rows=1, labelled=bool(gold), negatives=not gold, base_hit=had, hit=has, rescued=has and not had,
                   lost_targets=len((before & gold) - after), base_noise=not gold and bool(base),
                   noise=not gold and bool(point), new_noise=not gold and not base and bool(point),
                   base_confusion=bool(gold and before-gold), confusion=bool(gold and after-gold),
                   new_confusion=bool(gold and after-gold and not (before-gold)),
                   added_right=len(added & gold), added_wrong=len(added-gold))


def timing(values):
    return {k: round(float(np.percentile(values, p)), 2)
            for k, p in (("p50_ms", 50), ("p95_ms", 95), ("p99_ms", 99), ("max_ms", 100))} if values else {}


class CpuEncoder:
    def __init__(self, model_path, threads):
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(threads)
        self.model = SentenceTransformer(str(model_path.resolve(strict=True)), device="cpu", local_files_only=True)

    def encode(self, texts):
        return self.model.encode([t[:2000] for t in texts], normalize_embeddings=True, batch_size=12,
                                 show_progress_bar=False)


def benchmark_without_vectors(provider, queries):
    """Time the ready SQLite path while the encoder/index is unavailable."""
    original = provider._meaning_of
    provider._meaning_of = lambda text, *, before_turn: None
    times, metrics = [], Counter()
    try:
        for i, q in enumerate(queries):
            start = time.perf_counter()
            got = prefetch(provider, q["q"], f"without-vectors-{i}")
            times.append((time.perf_counter() - start) * 1000)
            metrics.update(record(q, got, got))
    finally:
        provider._meaning_of = original
    return {"calls": len(times), "hit": metrics["hit"], "labelled": metrics["labelled"],
            "over_3000_ms": sum(ms > 3000 for ms in times), **timing(times)}


def encode_store(encoder, columns):
    unique = list(dict.fromkeys(s for col in columns for s in col))
    embedded = dict(zip(unique, encoder.encode(unique), strict=True))
    return [np.stack([embedded[s] for s in col]) for col in columns]


@contextmanager
def retrieval(pkg, provider, index, matrices, floors, lookup, arm):
    """Inject native Meaning and append through _off_layout before budget, receipts and recent tracking."""
    raw, joined, keywords = matrices
    original_lookup = provider._meaning_of
    original_layout = provider._off_layout
    latest = None

    def meaning(text, *, before_turn):
        nonlocal latest
        latest = None
        if pkg._secret_in(text) or not pkg.embeddings.worth_asking(text, before_turn=before_turn):
            return None
        vector = lookup(text)
        latest = (text, vector)
        return pkg.embeddings.Meaning(index.ids, (raw @ vector).tolist(), provider._embedding.weight)

    def layout(text, vector, key, turn, candidates=None):
        facts, semantic = original_layout(text, vector, key, turn, candidates)
        if arm == "baseline" or latest is None or latest[0] != text or len(facts) >= 5:
            return facts, semantic
        qv = latest[1]
        shown = [f["fact_id"] for f in facts]
        key_scores = keywords @ qv if shown or arm == "agreement" else None
        winner = index.choose(text, joined @ qv, key_scores, shown, floors, arm=arm)
        if winner is None:
            return facts, semantic
        rows = provider._retriever._rows([winner], None, provider._min_trust)
        if not rows:
            return facts, semantic
        fact = rows[0]
        if not (provider._recallable(fact) and provider._not_recent(key, fact, turn)
                and provider._retriever.names_fit(text, fact)):
            return facts, semantic
        return [*facts, fact], semantic | {winner}

    provider._meaning_of, provider._off_layout = meaning, layout
    try:
        yield
    finally:
        provider._meaning_of, provider._off_layout = original_lookup, original_layout


def prefetch(provider, text, session):
    output = provider.prefetch(text, session_id=session)
    if provider._recall_error:
        raise RuntimeError("provider prefetch failed")
    return [int(i) for i in ID.findall(output)]


def masked_targets(pkg, fixture, questions, facts, matrices, vectors):
    """Remove every labelled answer from a disposable store and repeat the paired query."""
    groups = defaultdict(list)
    for q in questions:
        if q["targets"]:
            groups[tuple(sorted(q["targets"]))].append(q)
    totals = {arm: Counter() for arm in ARMS}
    for targets, queries in groups.items():
        with tempfile.TemporaryDirectory(prefix="recall-masked-") as td:
            provider = open_fixture(pkg, SimpleNamespace(facts=None, store=fixture), Path(td))
            try:
                for target in targets:
                    provider.handle_tool_call("fact_store", {"action": "forget", "fact_id": target})
                remaining = {i for i, in provider._store.read("SELECT fact_id FROM facts")}
                if remaining.intersection(targets):
                    raise ValueError("a masked target is still present")
                kept = [i for i, (fid, _, _) in enumerate(facts) if fid in remaining]
                selected = [m[kept] for m in matrices]
                index = KeywordIndex([facts[i] for i in kept])
                floors = background_floors(*selected[:2])
                base = []
                for arm in ("baseline", *ARMS):
                    with retrieval(pkg, provider, index, selected, floors, vectors.__getitem__, arm):
                        for i, q in enumerate(queries):
                            got = prefetch(provider, q["q"], f"{arm}-{i}")
                            if arm == "baseline":
                                base.append(got)
                            else:
                                totals[arm].update(record({"targets": []}, base[i], got))
            finally:
                provider.shutdown()
    return totals


def run(args):
    pkg = load_plugin(args.plugin_src, args.core_src)
    t0 = time.perf_counter()
    encoder = CpuEncoder(args.model, args.threads)
    boot = time.perf_counter() - t0
    with tempfile.TemporaryDirectory(prefix="recall-consensus-") as td:
        os.environ["HERMES_HOME"] = td
        provider, queries = build_fixture(pkg, args, Path(td))
        try:
            facts, raw, joined, keys = data_from_store(pkg, provider)
            index = KeywordIndex(facts)
            start = time.perf_counter()
            matrices = encode_store(encoder, [raw, joined, keys])
            floors = background_floors(*matrices[:2])
            build = time.perf_counter() - start
            def live(text):
                return encoder.encode([text])[0]
            # Ask the same cleaned text that prefetch passes to _meaning_of, even for quoted messages.
            own_words = getattr(pkg, "_own_words", None)
            texts = [own_words(q["q"], "") if own_words else q["q"] for q in queries]
            texts = list(dict.fromkeys(t[:pkg._PREFETCH_QUERY_CHARS] for t in texts))
            approved = [t for t in texts if not pkg._secret_in(t) and pkg.embeddings.worth_asking(t,before_turn=True)]
            vecs = dict(zip(approved, encoder.encode(approved), strict=True)) if approved else {}
            baseline = []
            with retrieval(pkg, provider, index, matrices, floors, vecs.__getitem__, "baseline"):
                for i, q in enumerate(queries):
                    baseline.append(prefetch(provider, q["q"], f"baseline-{i}"))
            totals = {}
            outputs = {"baseline": baseline}
            for arm in ARMS:
                outputs[arm] = []
                groups = defaultdict(Counter)
                with retrieval(pkg, provider, index, matrices, floors, vecs.__getitem__, arm):
                    for i, (q, base) in enumerate(zip(queries, baseline, strict=True)):
                        got = prefetch(provider, q["q"], f"{arm}-{i}")
                        outputs[arm].append(got)
                        groups[q.get("split", "all")].update(record(q, base, got))
                totals[arm] = dict(groups)
            speed = {}
            if args.benchmark:
                speed["without_vectors"] = benchmark_without_vectors(provider, queries)
                for arm in ("baseline", "agreement", "both", "shown"):
                    times, agreements = [], 0
                    with retrieval(pkg, provider, index, matrices, floors, live, arm):
                        for i, q in enumerate(queries):
                            start = time.perf_counter()
                            got = prefetch(provider, q["q"], f"timed-{arm}-{i}")
                            times.append((time.perf_counter()-start)*1000)
                            agreements += got == outputs[arm][i]
                    speed[arm] = {"calls":len(times), "serial_matches_batched":agreements,
                                  "over_3000_ms":sum(ms>3000 for ms in times), **timing(times)}
            masked = (masked_targets(pkg, Path(td) / "fixture.db", queries, facts, matrices, vecs)
                      if args.mask_targets else {})
            return {"suite":args.suite,"lang":args.lang,"facts":len(facts),"questions":len(queries),
                    "plugin":args.plugin_src.name,"threads":args.threads,"device":"cpu",
                    "model_load_s":round(boot,2),"fact_index_s":round(build,2),
                    "arms":totals,"latency":speed,"masked":masked}
        finally:
            provider.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suite", required=True, choices=["real","synthetic","household","squad","multi",
                                                       "contrast_en","contrast_ru","contrast_zh"])
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--plugin-src", type=Path, required=True)
    ap.add_argument("--core-src", type=Path, required=True)
    ap.add_argument("--lang")
    ap.add_argument("--squad",type=Path)
    ap.add_argument("--store", type=Path, help="Frozen read-only copy for --suite real")
    ap.add_argument("--queries", type=Path, nargs="+")
    ap.add_argument("--threads",type=int,default=4)
    ap.add_argument("--benchmark",action="store_true")
    ap.add_argument("--mask-targets",action="store_true")
    ap.add_argument("--out",type=Path)
    args = ap.parse_args()
    if args.suite=="real" and not (args.store and args.queries):
        ap.error("real requires --store and --queries")
    if args.suite=="squad" and not args.squad:
        ap.error("squad requires --squad")
    if args.suite.startswith("contrast_"):
        args.lang=args.suite
    if args.suite in ("household","multi") and not args.lang:
        ap.error("this suite requires --lang")
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1",HF_HUB_DISABLE_PROGRESS_BARS="1")
    result=run(args)
    payload=json.dumps(result, ensure_ascii=True, indent=2)
    if args.out:
        args.out.write_text(payload+"\n",encoding="utf-8")
    else:
        print(payload)


if __name__=="__main__":
    main()

