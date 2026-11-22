"""Paired measurements of the locked novel_terms rule. Run stages in the order below.

freeze, ceiling, controls, independent, ablate, simplified. Supply --work outside the repository
for short-lived row IDs and shared embeddings, --squad-dir with squad2-{train,dev}.json,
--model, --core-src, --store and --queries. The optional --public-cache is the original
CPU public/ cache. Without it the same local CPU encoder supplies those vectors.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import calib_consensus as replay
from calib_answerability import prepare
from calib_consensus_rule import KeywordIndex, terms

HERE = Path(__file__).resolve().parent
RULE = "novel_terms"
STAGES = ("freeze", "ceiling", "controls", "independent", "ablate", "simplified")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(value):
    return digest(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii"))


def verify_lock():
    lock = read(HERE / "novel-decision-freeze.json")
    for name, expected in lock["files"].items():
        if digest((HERE / name).read_bytes().replace(b"\r\n", b"\n")) != expected:
            raise ValueError(f"changed since freeze: {name}")
    return lock


def plugin(version, args):
    # The two vendored releases use the same Python package name.
    for module in tuple(sys.modules):
        if module == "hermes_plugin_holographic" or module.startswith("hermes_plugin_holographic."):
            del sys.modules[module]
    root = replay.REPO / "vendor" / f"holographic-{version}"
    return root, replay.load_plugin(root, args.core_src)


def query_text(pkg, text):
    if hasattr(pkg, "_own_words"):
        text = pkg._own_words(text, "")
    return text[:pkg._PREFETCH_QUERY_CHARS]


def metrics(q, before, after):
    result = replay.record(q, before, after)
    result["lost"] = int(result["base_hit"] and not result["hit"])
    result["neg_rows_with_added_wrong"] = int(not q["targets"] and result["added_wrong"] > 0)
    return result


def ceiling(queries, baseline, new_terms):
    counts = Counter(missed=0, overlap=0)
    for q, before in zip(queries, baseline, strict=True):
        targets = set(q["targets"])
        if targets and targets.isdisjoint(before[:5]):
            counts["missed"] += 1
            query_terms = terms(q["q"])
            counts["overlap"] += any(query_terms & new_terms[i] for i in targets)
    return counts


def stored_new_terms(pkg, provider):
    result = {}
    for fact_id, body, tags in provider._store.read("SELECT fact_id, content, tags FROM facts"):
        words = pkg._split_tags(tags or "")[1]
        result[fact_id] = set().union(*(terms(word) for word in words)) - terms(body)
    return result


def collect(queries, baseline, output):
    counts = defaultdict(Counter)
    for q, before, after in zip(queries, baseline, output, strict=True):
        counts[q.get("split", "all")].update(metrics(q, before, after))
    return dict(counts)


def old_public_vectors(cache, root, run, raw, joined, keys, questions, approved):
    suite, lang = run["suite"], run["lang"]
    stem = f"{suite}-{lang}"
    docs, words, qs = replay.public_data(root, suite, lang, None)
    with np.load(cache / (stem + ".npz"), allow_pickle=False) as arr:
        if (list(arr["keys"]) != list(docs)
                or list(arr["qid"]) != [str(q["qid"]) for q in qs]
                or list(arr["qid"]) != [str(q["qid"]) for q in questions]
                or raw != [text for text, entities in docs.values()]
                or keys != [", ".join(words[k]) for k in docs]
                or joined != [f"{text}\nkeywords: {k}" for text, k in zip(raw, keys, strict=True)]):
            raise ValueError(f"archived public vectors do not match {stem}")
        table = dict(zip([q["q"] for q in qs], arr["query"], strict=True))
        return (arr["content"], arr["joined"], np.load(cache / (stem + "-keywords.npy")),
                np.stack([table[t] for t in approved]))


class VectorBank:
    def __init__(self, args):
        self.args = args
        self.encoder = None

    def get(self, name, root, run, pkg, facts, columns, queries, *, create):
        texts = list(dict.fromkeys(query_text(pkg, q["q"]) for q in queries))
        approved = [s for s in texts if not pkg._secret_in(s) and pkg.embeddings.worth_asking(s, before_turn=True)]
        key = signature([name, facts, columns, queries, approved])
        path = self.args.work / f"{name}-{key}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as data:
                values = [data[k] for k in ("raw", "joined", "keywords", "query")]
        elif create:
            if self.args.public_cache and run["suite"] not in ("real", "synthetic", "squad", "independent"):
                values = old_public_vectors(self.args.public_cache, root, run, *columns, queries, approved)
            else:
                if self.encoder is None:
                    self.encoder = replay.CpuEncoder(self.args.model, 4)
                matrices = replay.encode_store(self.encoder, columns)
                qv = self.encoder.encode(approved) if approved else np.empty((0, 1024), dtype=np.float32)
                values = [*matrices, qv]
            tmp = path.with_suffix(".tmp.npz")
            np.savez(tmp, **dict(zip(("raw", "joined", "keywords", "query"), values, strict=True)))
            tmp.replace(path)
        else:
            raise ValueError(f"missing shared frozen vectors for {name}")
        for matrix, size in zip(values, [len(facts)] * 3 + [len(approved)], strict=True):
            if matrix.dtype != np.float32 or matrix.shape != (size, 1024) or not np.isfinite(matrix).all():
                raise ValueError("invalid vector cache")
        return values[:3], dict(zip(approved, values[3], strict=True))


def native_arm(pkg, provider, index, matrices, vectors, queries, arm):
    with replay.retrieval(pkg, provider, index, matrices, None, vectors.__getitem__, arm):
        return [replay.prefetch(provider, q["q"], f"{arm}-{i}") for i, q in enumerate(queries)]


def control_arms(pkg, provider, index, matrices, vectors, queries, directory):
    # Adapt to the original H1/H3 harness without rounding the shared CPU cosines.
    # Both releases use the same effective text for these fixtures.
    labelled = []
    probes = []
    for n, q in enumerate(queries):
        text = query_text(pkg, q["q"])
        if text != q["q"] and query_text(pkg, text) != text:
            raise ValueError("control requires idempotent prefetch text")
        row = dict(qid=str(n), q=text, targets=q["targets"], kind="real" if q["targets"] else "chit")
        labelled.append(row)
        v = vectors.get(text)
        cos = {} if v is None else {"content": (matrices[0] @ v).tolist(),
                                    "content+keywords": (matrices[1] @ v).tolist()}
        probes.append(dict(qid=str(n), kind=row["kind"], targets=row["targets"],
                           meaning_call="skip" if v is None else "ok", cos=cos))
    fixture_ids = provider._store.read("SELECT fact_id FROM facts WHERE trust_score >= ?", [provider._min_trust])
    dump = dict(fact_ids=index.ids, eligible={r[0] for r in fixture_ids}, probes=probes)
    path = directory / "controls-queries.json"
    save(path, labelled)
    # Also compare this adapter's baseline output ID-for-ID with the frozen native path.
    dump["recallable"] = set(index.ids)
    result = prepare(pkg, provider, dump, [path], arms=("baseline", "H1", "H3"))
    return {arm: [r[arm] for r in result] for arm in ("baseline", "H1", "H3")}


def one_old_run(args, stage, name, run, root, pkg, bank, td):
    suite = run["suite"]
    cfg = SimpleNamespace(
        suite=suite, lang=run["lang"], plugin_src=root, store=args.store if suite == "real" else None,
        queries=[args.queries], squad=args.squad_dir / ("squad2-dev.json" if name == "novel-squad-dev" else "squad2-train.json"),
        article_offset=run.get("article_offset", 0), support_keywords=run.get("support_keywords", False),
    )
    provider, queries = replay.build_fixture(pkg, cfg, td)
    try:
        facts, *columns = replay.data_from_store(pkg, provider)
        index = KeywordIndex(facts)
        if (len(facts), len(queries)) != (run["facts"], run["questions"]):
            raise ValueError(f"fixture size differs: {name}")
        row_path = args.work / (name + "-baseline.json")
        fixture_key = signature([facts, queries])
        if stage != "freeze":
            saved = read(row_path)
            if saved["fixture"] != fixture_key:
                raise ValueError("fixture or gold changed")
            base = saved["baseline"]
        if stage == "ceiling":
            return ceiling(queries, base, stored_new_terms(pkg, provider))
        matrices, vectors = bank.get(name, root, run, pkg, facts, columns, queries, create=stage == "freeze")
        if stage == "freeze":
            base = native_arm(pkg, provider, index, matrices, vectors, queries, "baseline")
            chosen = native_arm(pkg, provider, index, matrices, vectors, queries, RULE)
            counted = collect(queries, base, chosen)
            reference = run["arms"][RULE]
            if (counted.keys() != reference.keys()
                    or any(counted[s][k] != v for s in reference for k, v in reference[s].items())):
                raise ValueError(f"original split counts differ: {name}")
            save(row_path, dict(fixture=fixture_key, baseline=base, frozen=chosen))
            return {RULE: counted}
        if stage == "controls":
            controls = control_arms(pkg, provider, index, matrices, vectors, queries, td)
            if controls["baseline"] != base:
                raise ValueError(f"baseline control adapter mismatch: {name}")
            return {a: collect(queries, base, rows) for a, rows in controls.items()}
        if stage == "simplified":
            from calib_novel_ablation import SimplifiedIndex
            chosen = native_arm(pkg, provider, SimplifiedIndex(facts), matrices, vectors, queries, RULE)
            return dict(counts=collect(queries, base, chosen),
                        same_as_frozen=sum(a == b for a, b in zip(chosen, saved["frozen"], strict=True)))
        from calib_novel_ablation import ablate_fixture
        return ablate_fixture(pkg, provider, facts, matrices, vectors, queries, base, saved["frozen"])
    finally:
        provider.shutdown()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=STAGES)
    for arg in ("work", "squad-dir", "model", "core-src", "store", "queries"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--public-cache", type=Path)
    args = p.parse_args()
    args.work = args.work.resolve()
    if args.work.is_relative_to(replay.REPO):
        p.error("use an external scratch directory for private fixture data")
    args.work.mkdir(parents=True, exist_ok=True)
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_PROGRESS_BARS="1", HF_HUB_DISABLE_TELEMETRY="1")
    lock = verify_lock()
    if args.stage == "freeze":
        with (args.model / "pytorch_model.bin").open("rb") as weights:
            if hashlib.file_digest(weights, "sha256").hexdigest() != lock["model_weights_sha256"]:
                raise ValueError("model weights differ")
    stage_no = STAGES.index(args.stage)
    if stage_no and not (args.work / (STAGES[stage_no - 1] + ".json")).is_file():
        p.error("complete preceding measurement stage first")
    bank = VectorBank(args)
    if args.stage == "independent":
        from calib_novel_independent import run_once
        run_once(args, bank)
        return
    report = read(HERE / "consensus-results.json")
    results = {}
    for version in ("0.27.0", "0.30.0"):
        root, pkg = plugin(version, args)
        for name, run in report["runs"].items():
            small = run["suite"] in ("real", "synthetic")
            if small != (version == "0.27.0"):
                continue
            with tempfile.TemporaryDirectory(prefix="novel-eval-") as td:
                os.environ["HERMES_HOME"] = td
                results[name] = one_old_run(args, args.stage, name, run, root, pkg, bank, Path(td))
            print(args.stage, name, flush=True)
    if args.stage == "ablate":
        from calib_novel_ablation import finish
        results = finish(results, lock["ablations_on_original_pool_only"])
        prior = report["totals"]["agreement"]
        if any(results["single"]["no_novel_terms"][k] != v for k, v in prior.items()):
            raise ValueError("omitting novelty differs from the published agreement arm")
    if args.stage == "simplified":
        from calib_novel_ablation import SIMPLIFIED_OMISSIONS
        expected = read(args.work / "ablate.json")["novel_terms_simplified"]
        total = Counter()
        for point in results.values():
            for counts in point["counts"].values():
                total.update(counts)
        if expected["omitted"] != SIMPLIFIED_OMISSIONS or dict(total) != expected["counts"]:
            raise ValueError("named simplified rule differs from the deletion experiment")
    save(args.work / (args.stage + ".json"), results)


if __name__ == "__main__":
    main()
