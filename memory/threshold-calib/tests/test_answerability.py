import pytest

import calib_answerability as local
import calib_margin_verify as public


def test_trace_maps_fact_ids_without_depending_on_json_object_order():
    docs = dict.fromkeys(('old', 'extra'))
    before = {'keys': ['old'], 'sources': {'1': ['entity']}}
    wide = {'keys': ['extra', 'old'], 'sources': {'1': ['entity'], '2': ['meaning', 'entity']}}
    assert public.new_candidate(before, wide, docs) == 'extra'
    assert public.new_candidate({**before, 'sources': {'1': ['meaning']}}, wide, docs) is None
    assert public.new_candidate(before, {**wide, 'sources': {'1': ['meaning'], '2': ['entity']}}, docs) is None
    assert public.new_candidate(before, {**wide, 'sources': {'1': ['meaning'], '2': ['meaning']}}, docs) is None
    with pytest.raises(ValueError, match='fact IDs'):
        public.new_candidate(before, {**wide, 'sources': {'2': ['meaning']}}, docs)


def test_trace_requires_old_order_and_space_in_top_five():
    before = {'keys': [1, 2], 'sources': {}}
    assert public.new_candidate(before, {'keys': [2, 1, 3]}, {}) is None
    assert public.new_candidate({'keys': [1, 2, 3, 4, 5], 'sources': {}}, {'keys': [1, 2, 3, 4, 5, 6]}, {}) is None


def test_gate_counts_partial_target_loss_and_a_non_target_on_an_already_mixed_row(v):
    rows = [{'probe': {'targets': [1, 2]}}, {'probe': {'targets': [3]}}]
    result = local.summarize(rows, [[1, 2], [3, 4]], [[1], [3, 4, 5]], v.mcnemar_gate)
    assert (result['c'], result['lost_targets']) == (0, 1)
    assert (result['confusion'], result['new_confusion'], result['added_other']) == (1, 0, 1)


def test_public_confuser_and_any_non_target_are_measured_separately(v):
    base = {'kind': 'real', 'set': 'household', 'targets': ['a'], 'keys': ['a'], 'out_n': 1, 'confused': []}
    result = public.count(v.mcnemar_gate, base, {**base, 'keys': ['a', 'b'], 'out_n': 2})
    assert not result['new_confusion'] and result['new_any_other_top5'] and result['added_other'] == 1
