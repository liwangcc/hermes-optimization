"""One-condition omissions on the original 1,770 rows, holding native admission fixed.

Every omission still considers only the unique joined-vector winner and never replaces
it. Ask the real provider once whether that particular ID fits; a condition can only
choose between that append and the original output. Verify this identity against every
frozen output ID before counting any omissions.
"""

import math
from collections import Counter

import numpy as np

import calib_consensus as native
from calib_consensus_rule import KeywordIndex, _QUESTION, dominant, separation, terms


# Removing a whole gate and removing just its numerical offset are different
# one-at-a-time interventions. Report the literal gate deletions as diagnostics.
# Only the six omissions in the freeze file feed the prespecified simplification.
WHOLE_GATE_CHECKS = ("no_rank_agreement", "no_lexical_lead", "no_shown_z_gate", "no_silent_keyword_z_gate")
SIMPLIFIED_OMISSIONS = ["no_question_cue", "no_1_5"]


class SimplifiedIndex(KeywordIndex):
    """novel_terms_simplified, for a native replay on the development pool only."""

    def choose(self, query, joined, keyword, shown, floors, *, arm):
        n = len(self.ids)
        if len(shown) >= 5 or n < 3:
            return None
        if any(v.shape != (n,) or not np.isfinite(v).all() for v in (joined, keyword)):
            return None
        i = int(np.argmax(joined))
        winner = self.ids[i]
        if winner in shown or not self.has_keywords[i] or self.new_terms[i].isdisjoint(terms(query)):
            return None
        if np.count_nonzero(joined == joined[i]) != 1 or np.count_nonzero(keyword >= keyword[i]) != 1:
            return None
        b = math.sqrt(2 * math.log(n))
        j, k = separation(joined, i), separation(keyword, i)
        if shown:
            return winner if min(j, k) >= b + 1 else None
        if j >= b and k >= b + 2:
            aliases = self.scores(query)[1]
            if aliases[i] > 0 and sum(value >= aliases[i] for value in aliases) == 1:
                return winner
        return None


class CandidateIndex(KeywordIndex):
    def choose(self, query, joined, keyword, shown, floors, *, arm):
        n = len(self.ids)
        if len(shown) >= 5 or n < 3 or not np.isfinite(joined).all():
            return None
        i = int(np.argmax(joined))
        winner = self.ids[i]
        if not self.has_keywords[i] or winner in shown or np.count_nonzero(joined == joined[i]) != 1:
            return None
        b = math.sqrt(2 * math.log(n))
        j = separation(joined, i)
        valid_kw = np.isfinite(keyword).all()
        k = separation(keyword, i) if valid_kw else -math.inf
        aliases = self.scores(query)[1] if not shown else []
        self.evidence = dict(
            shown=bool(shown), novel=not self.new_terms[i].isdisjoint(terms(query)),
            question=bool(_QUESTION.search(query)), joined_b=j >= b, joined_plus1=j >= b + 1,
            kw_winner=bool(valid_kw and np.count_nonzero(keyword >= keyword[i]) == 1),
            kw_b=k >= b, kw_plus1=k >= b + 1, kw_plus2=k >= b + 2,
            unique_alias=bool(shown) or dominant(aliases, i, 1.0),
            leading_alias=bool(shown) or dominant(aliases, i, 1.5),
        )
        self.winner = winner
        return winner


def accepts(e, omit):
    if not e["novel"] and "no_novel_terms" not in omit:
        return False
    skip_shown_z = e["shown"] and "no_shown_z_gate" in omit
    if not skip_shown_z and not e["joined_b"]:
        return False
    if e["shown"]:
        if not skip_shown_z and "no_plus_1" not in omit and not e["joined_plus1"]:
            return False
        keyword_threshold = "kw_b" if "no_plus_1" in omit else "kw_plus1"
    else:
        if "no_question_cue" not in omit and not e["question"]:
            return False
        if ("no_lexical_lead" not in omit
                and (not e["unique_alias"] or ("no_1_5" not in omit and not e["leading_alias"]))):
            return False
        keyword_threshold = "kw_b" if "no_plus_2" in omit else "kw_plus2"
    if "no_second_view" in omit:
        return True
    if "no_rank_agreement" not in omit and not e["kw_winner"]:
        return False
    return skip_shown_z or (not e["shown"] and "no_silent_keyword_z_gate" in omit) or e[keyword_threshold]


def ablate_fixture(pkg, provider, facts, matrices, vectors, queries, baseline, frozen):
    from calib_novel_decision import metrics

    idx = CandidateIndex(facts)
    totals, alternatives = Counter(), []
    with native.retrieval(pkg, provider, idx, matrices, None, vectors.__getitem__, "novel_terms"):
        for n, (q, base, old) in enumerate(zip(queries, baseline, frozen, strict=True)):
            idx.evidence = None
            offered = native.prefetch(provider, q["q"], f"ablation-admission-{n}")
            default = metrics(q, base, base)
            totals.update(default)
            if offered != base:
                if idx.evidence is None or offered != [*base, idx.winner]:
                    raise ValueError("native admission changed more than the final ID")
                predicted = offered if accepts(idx.evidence, ()) else base
                delta = metrics(q, base, offered)
                delta.subtract(default)
                alternatives.append((idx.evidence, {k: v for k, v in delta.items() if v}))
            else:
                predicted = base
            if predicted != old:
                raise ValueError("full predicate and frozen output differ")
    return totals, alternatives


def aggregate(traces, omit):
    total = Counter()
    for baseline, offers in traces.values():
        total.update(baseline)
        for e, delta in offers:
            if accepts(e, omit):
                total.update(delta)
    return total


def finish(traces, names):
    full = aggregate(traces, ())
    singles = {k: aggregate(traces, {k}) for k in names}
    removable = [k for k in names if singles[k]["added_wrong"] == singles[k]["lost_targets"] == 0]
    joint = aggregate(traces, removable)
    deleted = removable
    attempts = {"joint": dict(omitted=removable, counts=joint)}
    if joint["added_wrong"] or joint["lost_targets"]:
        deleted = []
        for k in removable:
            subset = [*deleted, k]
            measured = aggregate(traces, subset)
            attempts[k] = dict(omitted=subset, counts=measured)
            if measured["added_wrong"] == measured["lost_targets"] == 0:
                deleted = subset
    diagnostics = {k: aggregate(traces, {k}) for k in WHOLE_GATE_CHECKS}
    return dict(full=full, single=singles, whole_gate=diagnostics, deletion_checks=attempts,
                novel_terms_simplified=dict(omitted=deleted, counts=aggregate(traces, deleted)))
