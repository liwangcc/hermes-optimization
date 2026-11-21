"""Pick a recall threshold for one embedding model on one fact store, from the store's own facts.

The probes and how they are read follow memory/threshold-calib (calib_probes.py, calib_gate.py): the middle half of a
stored fact, asked with the fact kept (a positive: that fact is its target) or held out (in-domain, and nothing left
answers it), plus chit-chat that must recall nothing. No labelling, no LLM. That tool draws a curve and picks nothing;
this picks one value: the loosest that lets no unanswerable probe in, on each of two draws of probes (a fact is a
fragment in one and held out in the other), and of the two the stricter. One draw's own value is the highest of some
fifteen similarities, too jumpy to hold a second draw to; what refuses a suggestion is the dependable-side failure,
fragments no longer recalled at that value.

Pure: vectors in, a verdict out. How a rule admits facts is the caller's (threshold_job.py).
"""
from __future__ import annotations

import itertools
import operator
import random
import re

MIN_FACTS = 20  # fewer recallable facts say nothing about a store (the base judges similarity from 20 vectors on)
MIN_POSITIVES, MIN_NEGATIVES = 10, 5  # per draw, or a single probe decides the verdict
PROBES = 40  # facts drawn per probe set, a quarter of them held out
SEEDS = (20261117, 7)  # two draws: which facts are fragments and which are held out differs
MIN_RECALL = 0.8  # of fragments, which share words with their fact: below this the model cannot tell them apart
GRID = tuple(round(0.05 + 0.01 * step, 2) for step in range(95))  # 0.05 .. 0.99

# Generic chat that must recall nothing; each is long enough to be embedded before a turn.
CHIT = ("今天天气怎么样，要不要带伞", "推荐一部最近好看的电影", "帮我写一首关于春天的短诗", "周末去哪里爬山比较好",
        "红烧肉怎么做才好吃", "what should I cook for dinner tonight", "tell me a joke about cats",
        "how tall is the highest mountain in the world", "recommend a good science fiction novel",
        "who won the football match last night")

_CJK = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff"  # CJK ideographs, kana, hangul
_UNIT = re.compile(rf"[{_CJK}]|[^\s{_CJK}]+")


def fragment(text: str) -> str:
    """The middle half of *text*, counted in units of one CJK character or one other word, cut from the text as it
    is (its own spaces and punctuation inside)."""
    spans = [m.span() for m in _UNIT.finditer(text)]
    if not spans:
        return ""
    k = -(-len(spans) // 2)
    start = (len(spans) - k) // 2
    return text[spans[start][0]:spans[start + k - 1][1]]


def probe_sets(facts: dict[int, str], askable) -> list[list[dict]]:
    """Two draws of probes from *facts* ({fact_id: text}): each up to PROBES fragments, a quarter of them asked with
    their fact held out, plus half of the chit-chat. *askable(text)*: the provider would embed this message."""
    sets = []
    for seed, chit in zip(SEEDS, (CHIT[::2], CHIT[1::2])):
        order = random.Random(seed).sample(sorted(facts), len(facts))
        drawn = list(itertools.islice(((i, t) for i in order if askable(t := fragment(facts[i]))), PROBES))
        kept = len(drawn) - len(drawn) // 4
        sets.append([{"q": t, "target": i, "holdout": None} for i, t in drawn[:kept]]
                    + [{"q": t, "target": None, "holdout": i} for i, t in drawn[kept:]]
                    + [{"q": t, "target": None, "holdout": None} for t in chit if askable(t)])
    return sets


def enough(sets: list[list[dict]]) -> bool:
    return all(sum(p["target"] is not None for p in probes) >= MIN_POSITIVES
               and sum(p["target"] is None for p in probes) >= MIN_NEGATIVES for probes in sets)


def ranked(vector, ids: list[int], vectors: list, holdout: int | None = None) -> list[tuple[int, float]]:
    """(fact_id, cosine) of unit vectors, closest first, over the store without the held-out fact."""
    # shortcut: pure Python (a bare Hermes has no numpy), about 8 s per 1000 facts at 1024 dimensions; move to
    # numpy when stores pass a few thousand facts.
    scored = [(i, sum(map(operator.mul, v, vector))) for i, v in zip(ids, vectors) if i != holdout]
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def measure(rows: list[tuple[dict, object]], admit, value) -> dict:
    """*rows*: (probe, what the rule scores it on); *admit(scored, value)*: the fact ids the rule lets in. hits:
    fragments whose own fact is let in. noise: probes nothing answers (held out, chit-chat) that let a fact in."""
    out = {"hits": 0, "positives": 0, "noise": 0, "negatives": 0}
    for probe, scored in rows:
        admitted = admit(scored, value)
        if probe["target"] is None:
            out["negatives"] += 1
            out["noise"] += bool(admitted)
        else:
            out["positives"] += 1
            out["hits"] += probe["target"] in admitted
    return out


def pick(draws: list[list], admit, candidates) -> dict | None:
    """The value to offer: on each of *draws* the first of *candidates* (loosest first) that lets no unanswerable
    probe in, and of those the strictest. None when a draw has no such candidate. each: the value of every draw; at:
    what the offered value does on every draw; ok: it still recalls MIN_RECALL of the fragments on each. Every draw
    must be enough()."""
    order = list(candidates)
    firsts = [next((k for k, value in enumerate(order) if measure(rows, admit, value)["noise"] == 0), None)
              for rows in draws]
    if None in firsts:
        return None
    value = order[max(firsts)]
    at = [measure(rows, admit, value) for rows in draws]
    return {"value": value, "each": [order[k] for k in firsts], "at": at,
            "ok": all(m["hits"] >= MIN_RECALL * m["positives"] for m in at)}


if __name__ == "__main__":  # python threshold_calib.py: a store a threshold separates, then one it cannot
    def floor(scored, tau):
        return [i for i, s in scored[:1] if s >= tau]

    def rows(lean: float) -> list:
        """40 orthogonal facts; a probe is its own fact leaning *lean* towards the next one."""
        ids = list(range(40))
        vectors = [[float(i == k) for k in range(41)] for i in ids]
        norm = (1 + lean * lean) ** 0.5

        def probe(i):
            return [(float(i == k) + lean * float(i + 1 == k)) / norm for k in range(41)]

        return ([({"target": i, "holdout": None}, ranked(probe(i), ids, vectors)) for i in ids[:20]]
                + [({"target": None, "holdout": i}, ranked(probe(i), ids, vectors, i)) for i in ids[20:39]])

    assert fragment("one two three four") == "two three" and fragment("今天天气很好") == "天天气"
    sets = probe_sets({i: f"fact number {i} says something long enough" for i in range(1, 31)}, bool)
    assert enough(sets) and sets[0] != sets[1] and not enough(probe_sets({1: "a b c d"}, bool))
    found = pick([rows(0.3), rows(0.5)], floor, GRID)  # own fact 0.96 / 0.89, the next one 0.29 / 0.45
    assert found and found["ok"] and found["each"] == [0.29, 0.45] and found["value"] == 0.45, found
    assert [m["hits"] for m in found["at"]] == [20, 20] and [m["noise"] for m in found["at"]] == [0, 0], found
    lost = pick([rows(0.3), rows(3.0)], floor, GRID)  # the next fact is closer than the probe's own
    assert lost and not lost["ok"] and lost["at"][1]["hits"] == 0, lost
    assert pick([rows(0.3)], floor, (0.05, 0.1)) is None  # nothing on offer keeps the next fact out
    print("ok")
