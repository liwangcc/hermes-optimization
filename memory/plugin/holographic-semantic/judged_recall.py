"""Judged recall: from the sidecar's /judge answer, which facts a turn shows in full and which it only lists.

Three readings of a (message, fact) pair that fail in different places are combined into one probability:
  strict   the cross-encoder's yes-minus-no logit that the note is needed for the message (it reads both texts)
  words    the base's word stream admitted the fact
  closest  the fact is the closest of the store by cosine
A fact the present recall would show (the base's block, or the sidecar's closest fact at tau) stays from KEEP;
any other candidate is added from ADD when the message is worth asking about and the base's own checks pass.

The pointers come from two readings the strict one does not decide: the judge's generic reading (it ranks a
convention a task needs without asking for it) and plain cosine (it catches what both readings reject). They are
left out when a shown fact already reaches ANSWERED.

Every constant was measured with BGE-M3 and Qwen3-Reranker-0.6B on the official probe sets
(memory/recall-race/round2: fitted on its dev pool, judged once on the held-out pool). Another embedding model
keeps the judge's readings but changes what "closest at tau" admits; another judge model needs a new fit.
"""
from __future__ import annotations

import math

_STRICT, _WORDS, _CLOSEST, _BIAS = 0.5502, 0.5578, 2.3547, -2.1772  # round2/model.json
ADD, KEEP, ANSWERED = 0.2, 0.03, 0.9
POINTER_JUDGE, POINTER_COS = (2, -5.0), (2, 0.40)  # (how many, the floor) by the generic reading, then by cosine
TOP_K = 10  # how many of the closest facts the judge reads beside the base's block
MAX_QUERY_CHARS = 500  # a longer message is not judged: the pair would be read by its first lines


def probability(strict: float, words: bool, closest: bool) -> float:
    return 1.0 / (1.0 + math.exp(-(_STRICT * strict + _WORDS * words + _CLOSEST * closest + _BIAS)))


def decide(facts: list, base: list, words: set, ask: bool, tau: float, cap: int, addable) -> tuple[list, list]:
    """(fact ids shown in full, best first; fact ids listed as pointers).

    *facts*: /judge rows (fact_id, cos, rank; strict where the judge read the fact; generic from a CUDA sidecar)
    of the base's block and the closest facts, in that order; *base*: the block's ids; *words*: the ids the word stream admitted; *ask*: the
    message is worth a semantic look; *addable(fact_id)*: the base's checks for a fact it did not show (asked only
    when needed)."""
    block, room = set(base), len(base) < cap
    shown = []
    for f in facts:
        # A sidecar off CUDA has its judge read the block and the closest fact only (round 2's rows: a quarter of
        # the pairs, the recall within a few facts of reading all ten): the other close facts are pointers at most.
        if "strict" not in f and f["fact_id"] not in block:
            continue
        p = probability(f["strict"], f["fact_id"] in words, f.get("rank") == 0)
        if f["fact_id"] in block:
            keep = p >= KEEP
        else:
            today = room and f.get("rank") == 0 and (f.get("cos") or 0.0) >= tau  # what recall appends unjudged
            keep = ask and (p >= ADD or (today and p >= KEEP)) and addable(f["fact_id"])
        if keep:
            shown.append((p, f["fact_id"]))
    shown.sort(key=lambda item: -item[0])
    del shown[cap:]
    ids = [fact_id for _, fact_id in shown]
    if not ask or (shown and shown[0][0] >= ANSWERED):
        return ids, []
    rest = [f for f in facts if f["fact_id"] not in ids]
    listed, by_cosine = [], POINTER_JUDGE[0] + POINTER_COS[0]
    # A sidecar off CUDA sends no generic reading (it is half the judge's time): every pointer is then by cosine.
    # Measured on round 2's rows: the same missed answers listed (37 of 38), 0.4 more lines a turn.
    if all("generic" in f for f in rest):
        listed = [f for f in sorted(rest, key=lambda f: -f["generic"]) if f["generic"] >= POINTER_JUDGE[1]]
        listed, by_cosine = listed[:POINTER_JUDGE[0]], POINTER_COS[0]
    close = [f for f in sorted(rest, key=lambda f: -(f.get("cos") or -1.0))
             if (f.get("cos") or -1.0) >= POINTER_COS[1] and f not in listed]
    return ids, [f["fact_id"] for f in listed + close[:by_cosine]]
