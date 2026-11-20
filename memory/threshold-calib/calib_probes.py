"""Where a calibration's facts and probes come from, and which of them the plugin would ever send.

Facts: a JSON list (the synthetic set of ../eval) or a COPY of a holographic SQLite store, opened read-only.
Probes, one of
  labelled  a query file someone wrote: ../eval/queries.json ({id, category, query, expected}) or KG-1's unified
            format ({qid, kind, category, lang, q, targets});
  auto      made from the store itself, no LLM and no labelling. Facts are drawn in a seeded order; each gives the
            middle half of its text. Three in four such probes keep their fact in the store ("fragment": a positive,
            the fact is its target); one in four is asked with its fact held out ("holdout": in-domain, and nothing
            left in the store answers it). Ten built-in chit-chat lines are added ("chit").
A fact the plugin would never send (screen._sendable) gets no vector, as in the plugin. A probe the plugin would not
embed before a turn (_secret_in, worth_asking) is dropped from an auto set and kept as a skipped row in a labelled one.
"""
from __future__ import annotations

import itertools
import json
import random
import re
import sqlite3
from pathlib import Path

from calib_cost import CJK

# Generic chat that must recall nothing; each passes worth_asking (no greeting, long enough).
CHIT = ("今天天气怎么样，要不要带伞", "推荐一部最近好看的电影", "帮我写一首关于春天的短诗", "周末去哪里爬山比较好",
        "红烧肉怎么做才好吃", "what should I cook for dinner tonight", "tell me a joke about cats",
        "how tall is the highest mountain in the world", "recommend a good science fiction novel",
        "who won the football match last night")

_UNIT = re.compile(rf"{CJK.pattern}|[^\s{CJK.pattern[1:-1]}]+")


def lang_of(text: str) -> str:
    return "zh" if CJK.search(text) else "en"


def load_facts(facts: str | None = None, store: str | None = None) -> list[dict]:
    """[{fact_id, content, trust_score}] by fact_id, as the plugin's vector index orders them. A store's NULL trust
    stays None (the plugin's `trust_score >= ?` never admits it); a JSON fact without one gets the default 0.5."""
    if store:
        con = sqlite3.connect(Path(store).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT fact_id, content, trust_score FROM facts ORDER BY fact_id").fetchall()
        finally:
            con.close()
    else:
        rows = [(f["fact_id"], f["content"], f.get("trust_score", 0.5))
                for f in json.loads(Path(facts).read_text(encoding="utf-8"))]
    out = [{"fact_id": int(i), "content": c or "", "trust_score": None if t is None else float(t)} for i, c, t in rows]
    if len({f["fact_id"] for f in out}) != len(out):
        raise SystemExit("two facts share a fact_id: the store is not one the plugin could hold")
    return sorted(out, key=lambda f: f["fact_id"])


def fragment(text: str) -> str:
    """The middle half of *text*, counted in units of one CJK character or one other word, cut from the text as it
    is (its own spaces and punctuation inside)."""
    spans = [m.span() for m in _UNIT.finditer(text)]
    if not spans:
        return ""
    k = -(-len(spans) // 2)
    start = (len(spans) - k) // 2
    return text[spans[start][0]:spans[start + k - 1][1]]


def _probe(qid, kind, category, text, targets, holdout=None) -> dict:
    return {"qid": qid, "kind": kind, "category": category, "lang": lang_of(text), "q": text, "targets": targets,
            "holdout": holdout}


def auto_probes(facts: list[dict], n: int, seed: int, embeddable) -> list[dict]:
    """Up to *n* probes from *facts* (a quarter of them holdouts) plus the chit-chat lines; *embeddable(text)* is
    the plugin's own test of a message."""
    by_id = {f["fact_id"]: f for f in facts}
    order = random.Random(seed).sample(sorted(by_id), len(by_id))
    usable = ((i, t) for i in order if embeddable(t := fragment(by_id[i]["content"])))
    drawn = list(itertools.islice(usable, n))
    n_pos = len(drawn) - len(drawn) // 4  # a store smaller than n still gets its holdouts
    out = [_probe(f"frag-{i}", "real", "fragment", t, [i]) for i, t in drawn[:n_pos]]
    out += [_probe(f"hold-{i}", "real", "holdout", t, [], holdout=i) for i, t in drawn[n_pos:]]
    out += [_probe(f"chit-{k}", "chit", "chit", t, []) for k, t in enumerate(CHIT, 1) if embeddable(t)]
    return out


def labelled_probes(path: str, fact_ids: set[int]) -> list[dict]:
    """The probes of a query file; a target that is not a fact of the store refuses the file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for q in data["queries"] if isinstance(data, dict) else data:
        qid, text = str(q.get("qid", q.get("id"))), q.get("q", q.get("query")) or ""
        targets = sorted(int(t) for t in (q.get("targets", q.get("expected")) or []))
        if set(targets) - fact_ids:
            raise SystemExit(f"query {qid}: target {sorted(set(targets) - fact_ids)} is not a fact of this store")
        category = q.get("category") or "real"
        probe = _probe(qid, q.get("kind") or ("chit" if category == "negative" else "real"), category, text, targets)
        probe["lang"] = q.get("lang") or probe["lang"]
        out.append(probe)
    if len({p["qid"] for p in out}) != len(out):  # refused here, before anything is sent
        raise SystemExit("two queries share a qid: give every query its own (a multilingual set: e.g. zh-P1, en-P1)")
    return out
