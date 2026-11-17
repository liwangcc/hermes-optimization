"""The admission adapters run the plugin's own code: the anchors the brief names, standout, the floor, the walk."""
import math

import numpy as np
import pytest

import calib_vendor


def test_the_vendored_anchors_are_where_the_brief_says(v):
    # stop condition of the brief if these move: RECALL_MARGIN 1.0 (embeddings.py:75), z >= sqrt(2 ln N) + margin
    assert v.emb.RECALL_MARGIN == 1.0 and v.emb.MIN_VECTORS_FOR_Z == 20
    for n in (20, 56, 10_000):
        assert v.emb.z_bar(n, 1.0) == pytest.approx(math.sqrt(2 * math.log(n)) + 1.0)
    assert v.version == "0.27.0"


def _meaning(v, sims, cls=None):
    ids = list(range(1, len(sims) + 1))
    m = (cls or v.emb.Meaning)(ids, np.asarray(sims, dtype=np.float32), 0.0)
    return m, m.ranked(), set(ids)


SIMS = [0.10 + 0.002 * i for i in range(22)] + [0.30, 0.45, 0.80]  # 25 facts: three stand out by degrees


def _expected_zbar(sims, margin, min_score=None):
    """The documented rule, computed independently: z over the whole store against sqrt(2 ln N) + margin."""
    s = np.asarray(sims, dtype=np.float32).astype(float)
    z = (s - s.mean()) / s.std()
    bar = math.sqrt(2 * math.log(len(s))) + margin
    order = sorted(range(len(s)), key=lambda i: (-s[i], i))
    out = []
    for i in order:
        if z[i] < bar or (min_score is not None and s[i] < min_score):
            break
        out.append(i + 1)
    return out


@pytest.mark.parametrize("margin", [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0])
def test_zbar_admits_what_the_documented_rule_admits(v, margin):
    m, ranked, eligible = _meaning(v, SIMS)
    got = calib_vendor.walk(m, ranked, *calib_vendor.standout_args(v, "zbar", margin), keep=25, eligible=eligible)
    assert got == _expected_zbar(SIMS, margin)


def test_zbar_floor_is_embedding_min_score_on_top_of_the_default(v):
    m, ranked, eligible = _meaning(v, SIMS)
    assert calib_vendor.standout_args(v, "zbar_floor", 0.85) == (1.0, 0.85)
    default = calib_vendor.walk(m, ranked, 1.0, None, 25, eligible)
    floored = calib_vendor.walk(m, ranked, *calib_vendor.standout_args(v, "zbar_floor", 0.85), 25, eligible)
    assert default == _expected_zbar(SIMS, 1.0) == [25] and floored == _expected_zbar(SIMS, 1.0, 0.85) == []
    # with enough vectors this floor can only take facts away
    lower = calib_vendor.walk(m, ranked, *calib_vendor.standout_args(v, "zbar_floor", 0.1), 25, eligible)
    assert lower == default


def test_below_twenty_vectors_only_a_floor_admits(v):
    m, ranked, eligible = _meaning(v, [0.1, 0.2, 0.9])
    assert calib_vendor.walk(m, ranked, 1.0, None, 3, eligible) == []
    assert calib_vendor.walk(m, ranked, 1.0, 0.15, 3, eligible) == [3, 2]


def test_floor_admits_on_the_cosine_alone(v):
    m, ranked, eligible = _meaning(v, SIMS, v.FloorMeaning)
    for t, want in ((0.9, []), (0.8, [25]), (0.3, [25, 24, 23]), (0.141, [25, 24, 23, 22])):
        m.floor = t
        assert calib_vendor.walk(m, ranked, 1.0, None, 5, eligible) == want
    m.floor = 0.3  # z_bar refuses fact 23 (z ~ 0.9 against a bar of ~ 3.5); the floor does not consult it
    assert 23 not in _expected_zbar(SIMS, 1.0) and 23 in calib_vendor.walk(m, ranked, 1.0, None, 5, eligible)
    assert issubclass(v.FloorMeaning, v.emb.Meaning)


def test_the_walk_stops_at_the_first_miss_skips_ineligible_facts_and_keeps_at_most_keep(v):
    m, ranked, _ = _meaning(v, SIMS, v.FloorMeaning)
    m.floor = 0.2  # 25, 24, 23 pass; 22 (0.142) is the first miss
    assert calib_vendor.walk(m, ranked, 1.0, None, 3, {25, 23, 22}) == [25, 23]
    assert calib_vendor.walk(m, ranked, 1.0, None, 1, {24, 23}) == [24]
    m.floor = 0.79  # 25 passes, 24 misses: the list ends there, eligible or not
    assert calib_vendor.walk(m, ranked, 1.0, None, 3, {23, 24, 25}) == [25]


def test_prefetch_takes_keep_plus_three_candidates_then_keep_recallable_ones(v):
    m, ranked, eligible = _meaning(v, SIMS, v.FloorMeaning)
    m.floor = 0.1  # every fact passes: the candidates are the closest keep + 3 = 4
    assert calib_vendor.walk(m, ranked, 1.0, None, 1, eligible, recallable={22, 21}) == [22]
    assert calib_vendor.walk(m, ranked, 1.0, None, 1, eligible, recallable={21}) == []  # fifth: never a candidate
    assert calib_vendor.walk(m, ranked, 1.0, None, 2, eligible, recallable={25, 23, 21}) == [25, 23]


def test_an_unknown_rule_is_refused(v):
    with pytest.raises(SystemExit, match="unknown rule"):
        calib_vendor.standout_args(v, "cosine", 0.5)
