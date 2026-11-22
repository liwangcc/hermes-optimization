"""The three recall pieces stacked, on recall_dump.py output: the frozen veto (daily-veto/frozen_rules.py), the
daily cosine append, and the upstream meaning stream with its checked margin. See STACK-RESULTS.md.

Everything is replayed offline from a dump directory (daily-veto/recall_dump.py, or dump_real.py for a real store):
the base block comes from the dump, the veto and the daily append are the frozen rules as they stand, and the
meaning stream is upstream's own admission on the content view (z against sqrt(2 ln N) + margin over every fact,
the closest four eligible facts), with a fact between the checked margin and RECALL_MARGIN kept only when the local
cross-encoder says it answers the question, one question a turn. Counts only leave the process.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "daily-veto"))
import daily_eval as d  # noqa: E402
import frozen_rules as fr  # noqa: E402

RECALL_MARGIN, CHECK_MARGIN, OFFERED = 1.0, 0.5, 4  # upstream: before a turn; the patch; recall_facts + 3
MIN_VECTORS_FOR_Z = 20
KEYS = ("labelled", "hit", "hit5", "rescued", "lost_targets", "negatives", "noise", "confusion", "shown_other",
        "added_wrong", "added_right", "removed_other", "shown")


class Check:
    """The cross-encoder's verdicts, cached; counts what it was asked and what it let in."""

    def __init__(self, verifier_dir):
        from calib_answerability import INSTRUCTION, AnswerVerifier
        self.model = AnswerVerifier(verifier_dir, INSTRUCTION)
        self.seen, self.counts = {}, Counter()

    def __call__(self, fx, i, fact_id):
        key = (fx.name, i, fact_id)
        if key not in self.seen:
            content = " ".join((fx.facts[fx.pos[fact_id]]["content"] or "").split())
            line = content if len(content) <= 300 else content[:299] + "…"
            self.seen[key] = self.model.score(fx.q[i]["q"], line) > 0
            right = fact_id in fx.q[i]["targets"]
            self.counts.update(asked=1, asked_targets=right, approved=self.seen[key],
                               approved_targets=self.seen[key] and right)
        return self.seen[key]


def meaning_fact(fx, i, shown, check, missing):
    """The fact upstream's meaning stream adds after *shown*, or None. *check*: the verdict on a fact that stands
    out at CHECK_MARGIN only; None leaves the admission at RECALL_MARGIN."""
    c = fx.cos(i, "content")
    if c is None or len(c) < MIN_VECTORS_FOR_Z or float(c.std()) <= 1e-9:
        return None
    margin = (c - c.mean()) / c.std() - math.sqrt(2.0 * math.log(len(c)))
    lowest = RECALL_MARGIN if check is None else CHECK_MARGIN
    offered = asked = 0
    for j in np.argsort(-c, kind="stable"):
        if margin[j] < lowest:
            break
        fact_id = int(fx.ids[j])
        if fact_id in shown or not fx.trusted[j]:
            continue
        offered += 1
        if offered > OFFERED:
            break
        try:
            if not fx.fits(i, fact_id):
                continue
        except KeyError:  # names_fit was dumped for the daily view's closest thirty only
            missing.update(names_fit_missing=1)
            continue
        if margin[j] >= RECALL_MARGIN:
            return fact_id
        if asked:
            continue
        asked = 1
        if check(fx, i, fact_id):
            return fact_id
    return None


def veto_only(fx, i):
    """The frozen veto on the base block alone: no cosine append."""
    block = d.base(fx, i)
    return fr.veto(fx, i, block, False) if fx.q[i]["askable"] else block


def with_meaning(rule, check, missing):
    def stacked(fx, i):
        block = rule(fx, i)
        if not fx.q[i]["askable"]:
            return block
        fact_id = meaning_fact(fx, i, set(block), check, missing)
        return block if fact_id is None else block + [fact_id]
    return stacked


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dump", type=Path, required=True, nargs="+", help="directories of recall_dump.py output")
    ap.add_argument("--verifier", type=Path, required=True, help="local Qwen3-Reranker-0.6B directory")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    check, missing = Check(args.verifier), Counter()
    rules = {
        "words and entities only": d.base,
        "daily 0.6.0 (cosine append at 0.55)": d.daily,
        "daily + veto (P1)": fr.RULES["P1"],
        "veto only": veto_only,
        "upstream meaning stream, default margin": with_meaning(d.base, None, missing),
        "upstream meaning stream, checked margin": with_meaning(d.base, check, missing),
        "veto + checked margin": with_meaning(veto_only, check, missing),
        "daily + veto (P1) + checked margin": with_meaning(fr.RULES["P1"], check, missing),
    }
    out = {}
    for directory in args.dump:
        fixtures = d.load(directory)
        before = Counter(check.counts)
        result = {name: d.evaluate(fixtures, rule, ref=d.base) for name, rule in rules.items()}
        out[directory.name] = {"fixtures": [fx.name for fx in fixtures],
                               "rules": {name: {k: r["ALL"].get(k, 0) for k in KEYS} for name, r in result.items()},
                               "per_fixture": {name: {fx: {k: c.get(k, 0) for k in KEYS} for fx, c in r.items()
                                                      if fx != "ALL"} for name, r in result.items()},
                               "check": dict(check.counts - before)}
        print(f"== {directory.name}: {len(fixtures)} fixtures")
        print("rule".ljust(42) + "".join(k[:11].rjust(12) for k in KEYS[:10]))
        for name, r in result.items():
            print(name.ljust(42) + "".join(str(r["ALL"].get(k, 0)).rjust(12) for k in KEYS[:10]))
        print("check:", out[directory.name]["check"])
    out["names_fit_missing"] = missing["names_fit_missing"]
    print("names_fit missing for a meaning candidate:", missing["names_fit_missing"])
    if args.out:
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
