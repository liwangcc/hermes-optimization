import numpy as np

from calib_consensus import record
from calib_consensus_rule import KeywordIndex, background_floors


def index():
    return KeywordIndex([(1, "清理临时产物", ["编译缓存", "编译缓存"]),
                         (2, "database rollback", ["rollback"]),
                         (3, "report format", ["summary"]),
                         (4, "web server", ["network"])])


def test_shown_needs_two_unique_outliers_and_room():
    idx = index()
    joined = [.88, .10, .15, .12]
    keys = [.84, .21, .18, .19]
    assert idx.choose("anything", joined, keys, [2], None, arm="shown") == 1
    for wrong_keys in ([.84, .84, .18, .19], [.2, .9, .3, .4], [.60, .59, .57, .55]):
        assert idx.choose("anything", joined, wrong_keys, [2], None, arm="shown") is None
    assert idx.choose("anything", joined, keys, [1], None, arm="shown") is None
    assert idx.choose("anything", joined, keys, [], None, arm="shown") is None
    assert idx.choose("anything", joined, keys, [2,3,4,5,6], None, arm="shown") is None


def test_silent_needs_question_and_corpus_floor():
    idx = index()
    joined = [.88, .10, .15, .12]
    floors = [.7] * 4
    assert idx.choose("编译缓存在哪", joined, None, [], floors, arm="silent") == 1
    assert idx.choose("编译缓存", joined, None, [], floors, arm="silent") is None
    assert idx.choose("编译缓存在哪", joined, None, [], [.9]*4, arm="silent") is None
    assert idx.choose("编译缓存在哪", [.88, .88, .15, .12], None, [], floors, arm="silent") is None


def test_silent_agreement_requires_keyword_evidence_and_two_rankings():
    idx = index()
    joined = [.88, .10, .15, .12]
    keys = [.84, .21, .18, .19]
    assert idx.choose("编译缓存在哪", joined, keys, [], None) == 1
    assert idx.choose("编译缓存在哪", joined, [.84, .85, .1, .2], [], None) is None
    assert idx.choose("在哪里买东西", joined, keys, [], None) is None
    assert idx.choose("编译缓存", joined, keys, [], None) is None


def test_floor_uses_foreign_facts_only_and_is_independent_of_block_size():
    content = np.array([[1,0,0],[0,1,0],[0,0,1]],dtype=float)
    joined = np.array([[.9,.2,.1],[.3,.8,.2],[.4,.2,.7]])
    floors = background_floors(content, joined, block_size=1)
    np.testing.assert_allclose(floors, [.195, .295, .39])
    np.testing.assert_allclose(floors, background_floors(content, joined, block_size=2))


def test_counts_wrong_fact_even_on_a_row_that_was_already_confused():
    counts = record({"targets": [1, 2]}, [1, 3], [1, 3, 4])
    assert counts["new_confusion"] == 0
    assert counts["added_wrong"] == 1
    assert record({"targets": [1, 2]}, [1,2], [1])["lost_targets"] == 1

