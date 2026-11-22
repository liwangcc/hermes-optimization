"""Build the blind labelled fixture and seal it before any retrieval.

Put comqa_train.json and train-v2.0-es.json in --work, and the two official English
files in --squad-dir (URLs and SHA-256s in novel-independent-plan.json). Before
the independent stage, run this file with --work, --squad-dir and --queries as in
calib_novel_decision.py. The fixture is entirely derived from published annotations.
"""

import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

from calib_squad_fixture import first_excerpt, squad_fixture

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / "novel-independent-plan.json").read_text(encoding="utf-8"))
STOP = set(("the a an who which how where when whose why what does did had have has that "
            "are was were would could should and this with from for its into about name "
            "qué que cuál quién cómo dónde cuándo los las del por una unos unas sus con "
            "entre el la se en es un fue son para años año").split())


def norm(s):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", s).casefold()))


def order(s):
    return hashlib.sha256((PLAN["seed"] + "\n" + s).encode("utf-8")).digest()


def support_terms(s, limit):
    return list(dict.fromkeys(w for w in norm(s).split() if 2 < len(w) <= 40 and w not in STOP))[:limit]


def source(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN["sources"][path.name][1]:
        raise ValueError(f"published source changed: {path.name}")
    return json.loads(raw)


def old_pool(squad_dir, real_labels):
    from calib_consensus import REPO, public_data
    from calib_answerability import read_json

    titles, ids, text = set(), set(), set()
    for name, offset, support in (("dev", 0, False), ("train", 0, False),
                                  ("train", 50, False), ("train", 100, True)):
        docs, _, qs = squad_fixture(squad_dir / f"squad2-{name}.json", article_offset=offset,
                                    support_keywords=support)
        titles.update(docs)
        ids.update(q["qid"] for q in qs)
        text.update(norm(q["q"]) for q in qs)
    for file in (real_labels, *[(REPO / "issue95-evidence/synthetic" / n)
                                for n in ("queries.json", "queries_ext.json")]):
        data = read_json(file)
        for q in (data["queries"] if isinstance(data, dict) else data):
            text.add(norm(q.get("q") or q["query"]))
    root = REPO / "vendor/holographic-0.30.0"
    for suite in ("household", "contrast_en", "contrast_ru", "contrast_zh", "multi"):
        languages = read_json(root / "tools/issue95_keywords" / (suite + ".json"))
        for lang in languages:
            _, _, qs = public_data(root, suite, lang, None)
            text.update(norm(q["q"]) for q in qs)
    return titles, ids, text


def comqa(clusters, blocked, size):
    bank, queries, used_answers = {}, [], set()
    used_text = set(blocked)
    ordered = sorted(clusters, key=lambda g: order(g["cluster_id"]))
    for row in ordered:
        name = row["cluster_id"]
        variants = {norm(q): q.strip() for q in row["questions"] if norm(q) not in used_text}
        # Distinct surface forms, excluding contractions/punctuation/capitalization-only duplicates.
        if len(variants) < 3 or len(row["answers"]) != 1 or not row["answers"][0].strip():
            continue
        first, support, query = [variants[t] for t in sorted(variants, key=order)[:3]]
        answer = unquote(row["answers"][0].removeprefix("https://en.wikipedia.org/wiki/")).replace("_", " ")
        fact = f"{first.rstrip('?')}? {answer}."
        words = support_terms(support, 8)
        if len(fact) > 295 or not words or norm(answer) in used_answers:
            continue
        bank[name] = [fact, words]
        queries.append(dict(qid=name, q=query, targets=[name]))
        used_answers.add(norm(answer))
        used_text.update(map(norm, (first, support, query)))
        if len(bank) == size:
            break
    corpus = " " + " | ".join(norm(text) for text, _ in bank.values()) + " "
    for row in ordered:
        name = row["cluster_id"]
        if name in bank or len(row["answers"]) != 1:
            continue
        url = row["answers"][0]
        if not url.startswith("https://en.wikipedia.org/wiki/"):
            continue
        answer = norm(unquote(url.rsplit("/", 1)[-1]).split("(")[0].replace("_", " "))
        if not answer or answer in used_answers or f" {answer} " in corpus:
            continue
        variants = [q for q in row["questions"] if norm(q) not in used_text]
        if variants:
            question = min(variants, key=order)
            queries.append(dict(qid=name, q=question, targets=[]))
            used_text.add(norm(question))
            used_answers.add(answer)
        if len(queries) == 2 * size:
            break
    return dict(facts=bank, queries=queries)


def squad_spanish(english, spanish, old, size):
    titles, used_ids, blocked = old
    used_text = set(blocked)
    es = {q["id"]: q for a in spanish["data"] for p in a["paragraphs"] for q in p["qas"]}
    bank, queries = {}, []
    for article in sorted(english["data"], key=lambda a: order(a["title"])):
        name = article["title"]
        if name in titles:
            continue
        for paragraph in sorted(article["paragraphs"], key=lambda p: order(p["context"])):
            fact = first_excerpt(paragraph)
            if len(fact) < 50:
                continue
            positive, negative = [], []
            local = set()
            for q in sorted(paragraph["qas"], key=lambda q: order(q["id"])):
                translation = es.get(q["id"])
                if not translation or q["id"] in used_ids or q["is_impossible"] != translation["is_impossible"]:
                    continue
                forms = {norm(q["question"]), norm(translation["question"])}
                if len(forms) < 2 or forms & (used_text | local):
                    continue
                if q["is_impossible"]:
                    negative.append(q)
                elif any(fact[a["answer_start"]:a["answer_start"] + len(a["text"])] == a["text"]
                         for a in q["answers"] if a["text"]):
                    positive.append(q)
                else:
                    continue
                local.update(forms)
            if len(positive) < 2 or not negative:
                continue
            support, pos = positive[:2]
            neg = negative[0]
            words = list(dict.fromkeys(support_terms(support["question"], 4) +
                                       support_terms(es[support["id"]]["question"], 4)))
            if not words:
                continue
            bank[name] = [fact, words]
            for q, targets in ((pos, [name]), (neg, [])):
                queries.append(dict(qid=q["id"], q=es[q["id"]]["question"], targets=targets))
            used_text.update(local)
            break
        if len(bank) == size:
            break
    return dict(facts=bank, queries=queries)


def pack(args):
    from calib_novel_decision import save, signature

    files = [args.work / "comqa_train.json", args.work / "train-v2.0-es.json",
             args.squad_dir / "squad2-train.json", args.squad_dir / "squad2-dev.json"]
    clusters, spanish, english, _ = [source(p) for p in files]
    old = old_pool(args.squad_dir, args.queries)
    fixtures = {"comqa": comqa(clusters, old[2], PLAN["strata"]["comqa"]["facts"]),
                "squad_es": squad_spanish(english, spanish, old, PLAN["strata"]["squad_es"]["facts"])}
    all_questions = []
    for name, data in fixtures.items():
        qs = data["queries"]
        positive = [q["targets"][0] for q in qs if q["targets"]]
        expected = PLAN["strata"][name]
        if (len(data["facts"]), len(positive), len(qs) - len(positive)) != tuple(expected[k] for k in
                                                                                 ("facts", "positive", "negative")):
            raise ValueError(f"incomplete blind stratum: {name}")
        if len(set(positive)) != len(positive) or len({q["qid"] for q in qs}) != len(qs):
            raise ValueError("duplicate fact or question")
        all_questions.extend(norm(q["q"]) for q in qs)
    if len(set(all_questions)) != len(all_questions) or set(all_questions) & old[2]:
        raise ValueError("repeated test question")
    path = HERE / "novel-independent-seal.json"
    seal = {"fixture_sha256": signature(fixtures), "plan_sha256": signature(PLAN)}
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != seal:
            raise ValueError("independent fixture differs from pre-scoring seal")
    else:
        with path.open("x", encoding="utf-8") as f:
            f.write(json.dumps(seal, indent=2) + "\n")
    save(args.work / "independent-fixture.json", fixtures)


def run_once(args, bank):
    from calib_novel_decision import RULE, ceiling, collect, native_arm, plugin, read, save, signature
    from calib_consensus import KeywordIndex, data_from_store, open_fixture

    data = read(args.work / "independent-fixture.json")
    seal = read(HERE / "novel-independent-seal.json")
    if (signature(data), signature(PLAN)) != (seal["fixture_sha256"], seal["plan_sha256"]):
        raise ValueError("fixture, gold or quotas changed after sealing")
    root, pkg = plugin("0.30.0", args)
    results = {}
    # 'x' makes the one paired pass explicit, including if a run is interrupted.
    with (args.work / "independent-started").open("x", encoding="ascii") as receipt:
        receipt.write(seal["fixture_sha256"] + "\n")
    for name, fixture in data.items():
        with tempfile.TemporaryDirectory(prefix="blind-novel-") as directory:
            os.environ["HERMES_HOME"] = directory
            p = open_fixture(pkg, SimpleNamespace(store=None, facts=None), Path(directory))
            try:
                ids = {}
                for label, (body, words) in fixture["facts"].items():
                    out = json.loads(p.handle_tool_call("fact_store", dict(action="add", content=body, keywords=words)))
                    if out.get("status") != "added" or out.get("keywords") != words:
                        raise ValueError(f"indexing changed independent fixture: {name}/{label}")
                    ids[label] = out["fact_id"]
                qs = [{**q, "targets": [ids[k] for k in q["targets"]]} for q in fixture["queries"]]
                facts, *columns = data_from_store(pkg, p)
                index = KeywordIndex(facts)
                if set(index.ids) != set(ids.values()):
                    raise ValueError("sendable facts differ from sealed fixture")
                m, v = bank.get("blind-" + name, root, {"suite": "independent"}, pkg, facts, columns, qs, create=True)
                base = native_arm(pkg, p, index, m, v, qs, "baseline")
                frozen = native_arm(pkg, p, index, m, v, qs, RULE)
                results[name] = dict(counts=collect(qs, base, frozen)["all"],
                                     ceiling=ceiling(qs, base, dict(zip(index.ids, index.new_terms, strict=True))))
            finally:
                p.shutdown()
    save(args.work / "independent.json", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "squad-dir", "queries"):
        parser.add_argument("--" + name, type=Path, required=True)
    pack(parser.parse_args())
