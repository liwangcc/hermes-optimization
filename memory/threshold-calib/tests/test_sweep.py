"""The sweep: every point admits exactly what its value allows, the floor grid, holdouts, monotone curves."""
import numpy as np
import pytest

import calib_run

IDS = list(range(1, 26))
SIMS = np.asarray([0.10 + 0.002 * i for i in range(22)] + [0.30, 0.45, 0.80], dtype=np.float32)


def test_every_point_of_every_rule_admits_exactly_what_its_value_allows(v):
    probes = [{"qid": "P", "meaning_call": "ok"}, {"qid": "S", "meaning_call": "skipped"}]
    grids = {"zbar": [0.0, 1.0, 3.0], "zbar_floor": [0.5, 0.85], "floor": [0.141, 0.3, 0.9]}
    rows = calib_run.sweep(v, probes, [(IDS, SIMS), None], grids, keep=3, eligible=set(IDS))
    got = {(r["rule"], r["value"], r["qid"]): r["keys"] for r in rows}
    # z of fact 25 ~ 4.3, of fact 24 ~ 1.9; the bar of 25 facts is ~ 2.54 + margin
    assert got[("zbar", 0.0, "P")] == [25] and got[("zbar", 1.0, "P")] == [25] and got[("zbar", 3.0, "P")] == []
    assert got[("zbar_floor", 0.5, "P")] == [25] and got[("zbar_floor", 0.85, "P")] == []
    assert got[("floor", 0.9, "P")] == [] and got[("floor", 0.3, "P")] == [25, 24, 23]
    assert got[("floor", 0.141, "P")] == [25, 24, 23]  # four pass, keep is 3
    assert all(got[(rule, x, "S")] == [] for rule, xs in grids.items() for x in xs)  # never embedded: nothing
    # rows come point by point in grid order, probes in their order inside a point
    assert [(r["rule"], r["value"], r["qid"]) for r in rows] == [
        (rule, x, q) for rule, xs in grids.items() for x in xs for q in ("P", "S")]


def test_keep_and_trust_follow_the_plugin(v):
    probes = [{"qid": "P", "meaning_call": "ok"}]
    rows = calib_run.sweep(v, probes, [(IDS, SIMS)], {"floor": [0.2]}, keep=2, eligible=set(IDS) - {24})
    assert rows[0]["keys"] == [25, 23]  # 24 is below min_trust: skipped, not counted, not the end of the list


def test_a_holdout_is_asked_against_the_store_without_its_fact():
    probes = [{"qid": "a", "meaning_call": "ok", "holdout": None}, {"qid": "b", "meaning_call": "ok", "holdout": 3},
              {"qid": "c", "meaning_call": "skipped", "holdout": None}]
    q = np.asarray([[0.1, 0.2, 0.9, 0.3], [0.1, 0.2, 0.9, 0.3]], dtype=np.float32)
    got = calib_run.similarities(probes, [1, 2, 3, 4], np.eye(4, dtype=np.float32), q)
    assert got[0][0] == [1, 2, 3, 4] and np.allclose(got[0][1], q[0])
    assert got[1][0] == [1, 2, 4] and np.allclose(got[1][1], [0.1, 0.2, 0.3])
    assert got[2] is None


def test_embedding_goes_in_bounded_requests_and_a_failure_stops_the_run():
    class Fake:
        def __init__(self, fail_at=None):
            self.calls, self.fail_at = [], fail_at

        def embed(self, texts, budget=None):
            self.calls.append((len(texts), budget))
            return None if len(self.calls) == self.fail_at else [np.ones(2, dtype=np.float32)] * len(texts)

        def status(self):
            return "paused after an error (HTTP 503)"

    fake = Fake()
    assert calib_run.embed(fake, ["t"] * 70, 32).shape == (70, 2)
    assert fake.calls == [(32, calib_run.REQUEST_SECONDS), (32, calib_run.REQUEST_SECONDS), (6, calib_run.REQUEST_SECONDS)]
    assert calib_run.embed(Fake(), [], 1) == []
    with pytest.raises(SystemExit, match="embedding failed: paused after an error"):
        calib_run.embed(Fake(fail_at=2), ["t"] * 3, 1)


def test_the_floor_grid_spans_the_closest_similarities_rounded_down():
    sims = [([1, 2], np.asarray([t, 0.0], dtype=np.float32)) for t in (0.2, 0.4, 0.6, 0.8, 0.95)] + [None]
    grid = calib_run.floor_grid(sims, keep=1)
    assert grid == sorted(set(grid)) and len(grid) <= calib_run.FLOOR_POINTS
    # float32 0.95 is 0.94999998...: rounded down, so the top value still admits that probe
    assert grid[0] == 0.2 and grid[-1] == 0.949
    assert all(x <= float(np.float32(0.95)) for x in grid)
    assert calib_run.floor_grid(sims, keep=2)[0] == 0.0  # the second closest of each probe joins the pool


def test_curves_are_monotone_on_a_random_store(v):
    rng = np.random.default_rng(7)
    ids = list(range(1, 41))
    sims = [(ids, rng.normal(0.5, 0.1, 40).astype(np.float32)) for _ in range(30)]
    probes = [{"qid": f"P{k}", "meaning_call": "ok"} for k in range(30)]
    grid = calib_run.floor_grid(sims, 1)
    grids = {"zbar": [-0.5, 0.0, 1.0, 2.0], "zbar_floor": grid, "floor": grid}
    rows = calib_run.sweep(v, probes, sims, grids, 1, set(ids))
    for rule, values in grids.items():
        admitted = [sum(len(r["keys"]) for r in rows if r["rule"] == rule and r["value"] == x) for x in values]
        assert admitted == sorted(admitted, reverse=True), rule
    floor = [sum(len(r["keys"]) for r in rows if r["rule"] == "floor" and r["value"] == x) for x in grid]
    assert floor[0] == 30 and floor[-1] >= 1  # the lowest value admits every probe's closest fact
