"""The gate on hand-made rows: upstream's McNemar values, the four PR #17 conditions one at a time, the refusals."""
import pytest

import calib_gate
from conftest import MANIFEST, rows_of

LABELLED = 12


def probes():
    lab = [{"qid": f"L{i}", "kind": "real", "category": "paraphrase", "targets": [i]} for i in range(1, LABELLED + 1)]
    hold = [{"qid": f"H{i}", "kind": "real", "category": "holdout", "targets": []} for i in (1, 2)]
    chit = [{"qid": f"C{i}", "kind": "chit", "category": "chit", "targets": []} for i in (1, 2)]
    return lab + hold + chit


def keys(**given):
    return {p["qid"]: given.get(p["qid"], []) for p in probes()}


BASE = keys(L1=[1])
RESCUE6 = {f"L{i}": [i] for i in range(1, 8)}  # L1 kept, L2..L7 rescued


@pytest.mark.parametrize("b, c, p", [(0, 0, 1.0), (5, 0, 0.0625), (6, 0, 0.03125), (10, 2, 158 / 4096),
                                     (9, 1, 22 / 1024), (3, 3, 1.0)])
def test_mcnemar_is_upstreams_exact_two_sided_binomial(v, b, c, p):
    assert v.mcnemar_gate.mcnemar(b, c) == pytest.approx(p)
    assert v.mcnemar_gate.mcnemar(c, b) == pytest.approx(p)


def test_six_rescued_none_lost_passes(v):
    got = calib_gate.judge(v, probes(), BASE, keys(**RESCUE6))
    assert (got["b_rescued"], got["c_lost"], got["p"]) == (6, 0, 0.03125)
    assert (got["hit5"], got["labelled"], got["recall5"]) == (7, LABELLED, round(7 / LABELLED, 4))
    assert got["gained_targets"] == [f"L{i}:{i}" for i in range(2, 8)] and got["lost_targets"] == []
    assert got["passes"] and all(got["conditions"].values())


def test_five_rescued_is_not_significant(v):
    got = calib_gate.judge(v, probes(), BASE, keys(**{f"L{i}": [i] for i in range(1, 7)}))
    assert got["conditions"] == {"no_target_lost": True, "noise_not_higher": True, "confusion_not_higher": True,
                                 "mcnemar_p_below_0.05": False}


def test_chit_with_output_is_noise_and_fails_only_that(v):
    got = calib_gate.judge(v, probes(), BASE, keys(**RESCUE6, C1=[3]))
    assert got["noise"] == {"base": 0, "point": 1, "added": ["C1"], "removed": [], "net": 1}
    assert [k for k, ok in got["conditions"].items() if not ok] == ["noise_not_higher"]


def test_holdout_with_output_is_noise_not_confusion(v):
    got = calib_gate.judge(v, probes(), BASE, keys(**RESCUE6, H2=[5]))
    assert got["noise"]["added"] == ["H2"] and got["confusion"]["point"] == 0


def test_a_wrong_fact_on_a_labelled_probe_is_confusion_not_noise(v):
    got = calib_gate.judge(v, probes(), BASE, keys(**RESCUE6, L12=[3]))
    assert got["confusion"] == {"base": 0, "point": 1, "added": ["L12"], "removed": [], "net": 1}
    assert got["noise"]["point"] == 0
    assert [k for k, ok in got["conditions"].items() if not ok] == ["confusion_not_higher"]


def test_a_lost_target_fails_even_when_p_is_below_005(v):
    point = keys(**{f"L{i}": [i] for i in range(2, 11)})  # nine rescued, L1 lost
    got = calib_gate.judge(v, probes(), BASE, point)
    assert (got["b_rescued"], got["c_lost"]) == (9, 1) and got["p"] < 0.05
    assert got["lost_targets"] == ["L1:1"] and not got["passes"]
    assert [k for k, ok in got["conditions"].items() if not ok] == ["no_target_lost"]


def test_a_multi_target_probe_keeping_one_target_still_loses_the_other(v):
    ps = probes() + [{"qid": "M1", "kind": "real", "category": "multi", "targets": [1, 2]}]
    base = {**{p["qid"]: [] for p in ps}, "M1": [1, 2]}
    point = {**base, "M1": [1]}
    got = calib_gate.judge(v, ps, base, point)
    assert got["c_lost"] == 0 and got["lost_targets"] == ["M1:2"] and not got["conditions"]["no_target_lost"]


def test_only_the_first_five_count(v):
    ps = [{"qid": "L1", "kind": "real", "category": "x", "targets": [6]}]
    got = calib_gate.judge(v, ps, {"L1": []}, {"L1": [1, 2, 3, 4, 5, 6]})
    assert got["hit5"] == 0 and got["confusion"]["point"] == 1 and got["extra_admitted"]["point"] == 5


def test_confusion_is_a_wrong_closest_fact_and_extras_below_a_right_one_are_only_shown(v):
    ps = [{"qid": f"L{i}", "kind": "real", "category": "x", "targets": [i]} for i in (1, 2, 3)]
    base = {"L1": [], "L2": [], "L3": []}
    point = {"L1": [1, 9], "L2": [9, 2], "L3": [9]}  # right then wrong; wrong above right; wrong alone
    got = calib_gate.judge(v, ps, base, point)
    assert got["hit5"] == 2 and got["confusion"]["added"] == ["L2", "L3"]
    assert got["extra_admitted"] == {"base": 0, "point": 3}


def test_summary_judges_every_point_against_the_default(v):
    pts = {("zbar", 1.0): BASE, ("zbar", 0.5): keys(**RESCUE6), ("floor", 0.4): keys(**RESCUE6, C2=[9])}
    s = calib_gate.summary(v, MANIFEST, probes(), rows_of(pts))
    assert s["passing"] == {"zbar": [0.5], "floor": []}
    assert [pt["value"] for pt in s["rules"]["zbar"]] == [1.0, 0.5]
    assert not s["rules"]["zbar"][0]["passes"]  # the default against itself: nothing rescued


@pytest.mark.parametrize("break_it, says", [
    (lambda ps, rows: (ps + [ps[0]], rows), "duplicate probes"),
    (lambda ps, rows: (ps, rows + [rows[0]]), "duplicate rows"),
    (lambda ps, rows: (ps, rows[:-1]), "unpaired"),
    (lambda ps, rows: (ps, [r for r in rows if r["value"] != 1.0]), "default point"),
    (lambda ps, rows: (ps, rows + [{**rows[0], "rule": "cosine"}]), "row off the run"),
    (lambda ps, rows: (ps, rows + [{**rows[0], "qid": "Z9"}]), "row off the run"),
])
def test_what_cannot_be_compared_is_refused(v, break_it, says):
    ps, rows = break_it(probes(), rows_of({("zbar", 1.0): BASE, ("zbar", 0.5): keys(**RESCUE6)}))
    with pytest.raises(SystemExit, match=says):
        calib_gate.summary(v, MANIFEST, ps, rows)
