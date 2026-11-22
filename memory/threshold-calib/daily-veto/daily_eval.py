"""Offline replay of daily-shape recall rules on recall_dump.py output.

A rule is a function rule(fx, i) -> list of fact ids (the injected block, in order) for question i.
`daily` is the shipped 0.6.0 local rule: the base block, then the closest fact (bge-m3 cosine of
content + " " + tags) when it reaches tau, is not shown, the block holds fewer than 7, and it passes
recallable and names_fit (the wrapper's repeat check never fires in a fresh session).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

TAU = 0.55
CAP = 7


class Fixture:
    def __init__(self, stem):
        stem = Path(stem)
        data = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
        arrays = np.load(stem.with_suffix(".npz"))
        self.name = f"{data['suite']}-{data['lang']}"
        self.facts = data["facts"]
        self.q = data["questions"]
        self.min_trust = data["min_trust"]
        self.ids = np.array([f["fact_id"] for f in self.facts])
        self.pos = {int(f): j for j, f in enumerate(self.ids)}
        self.mats = {k: arrays[k] for k in ("daily", "content", "keywords")}
        self.qv = arrays["query"]
        self.trusted = np.array([f["trust_score"] >= self.min_trust for f in self.facts])
        self.recallable = np.array([f["recallable"] for f in self.facts])
        self._cos = {}

    def cos(self, i, view="daily"):
        """Cosines of question i to every fact (None when the question is not askable)."""
        if not self.q[i]["askable"]:
            return None
        key = (i, view)
        if key not in self._cos:
            self._cos[key] = self.mats[view] @ self.qv[i]
        return self._cos[key]

    def fits(self, i, fact_id):
        """recallable and names_fit (names_fit was dumped for the top-30 by daily cosine and the lexical pool)."""
        j = self.pos[int(fact_id)]
        nf = self.q[i]["names_fit"].get(str(int(fact_id)))
        if nf is None:
            raise KeyError(f"names_fit not dumped for fact {fact_id} on {self.name} q{i}")
        return bool(self.recallable[j]) and nf

    def ranked(self, i, view="daily"):
        """Trusted fact ids by descending cosine, with their cosines."""
        c = self.cos(i, view)
        if c is None:
            return [], []
        order = [j for j in np.argsort(-c, kind="stable") if self.trusted[j]]
        return [int(self.ids[j]) for j in order], [float(c[j]) for j in order]


def base(fx, i):
    return list(fx.q[i]["block"])


def daily(fx, i, tau=TAU):
    block = base(fx, i)
    ids, cs = fx.ranked(i)
    if not ids or len(block) >= CAP:
        return block
    top, c = ids[0], cs[0]
    if top in block or c < tau or not fx.fits(i, top):
        return block
    return block + [top]


def row_counts(q, before, after):
    gold = set(q["targets"])
    b, a, a5 = set(before), set(after), set(after[:5])
    return Counter(
        rows=1,
        labelled=bool(gold),
        negatives=not gold,
        hit5=bool(a5 & gold),
        hit=bool(a & gold),
        base_hit=bool(b & gold),
        rescued=bool(a & gold) and not (b & gold),
        lost_rows=bool(b & gold) and not (a & gold),
        lost_targets=len((b & gold) - a),
        noise=not gold and bool(a),
        base_noise=not gold and bool(b),
        confusion=bool(gold) and bool(a - gold),
        confusion5=bool(gold) and bool(a5 - gold),
        shown_other=len(a - gold),
        base_shown_other=len(b - gold),
        added_wrong=len(a - b - gold),
        added_right=len((a - b) & gold),
        removed_other=len(b - a - gold),
        shown=len(a),
        targets_total=len(gold),
        targets_shown=len(a & gold),
    )


def evaluate(fxs, rule, ref=daily, **kw):
    """Counts of `rule` against `ref` over fixtures; per fixture and pooled."""
    out, total = {}, Counter()
    for fx in fxs:
        c = Counter()
        for i, q in enumerate(fx.q):
            c.update(row_counts(q, ref(fx, i), rule(fx, i, **kw) if kw else rule(fx, i)))
        out[fx.name] = dict(c)
        total.update(c)
    out["ALL"] = dict(total)
    return out


def load(directory, names=None):
    stems = sorted(p.with_suffix("") for p in Path(directory).glob("*.json"))
    return [Fixture(s) for s in stems if names is None or s.name in names]


SHOW = ("labelled", "hit", "hit5", "rescued", "lost_targets", "negatives", "noise", "confusion",
        "shown_other", "added_wrong", "removed_other")


def table(result, keys=SHOW):
    lines = ["fixture".ljust(22) + "".join(k[:12].rjust(13) for k in keys)]
    for name, c in result.items():
        lines.append(name.ljust(22) + "".join(str(c.get(k, 0)).rjust(13) for k in keys))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    fxs = load(sys.argv[1])
    print("semantic off -> daily 0.6.0 (reference: semantic off)")
    print(table(evaluate(fxs, daily, ref=base)))
