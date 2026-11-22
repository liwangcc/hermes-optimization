import numpy as np

import calib_written_probes as written


def test_a_held_out_probe_is_scored_on_the_closest_remaining_fact():
    assert written.written_rows(np.array([0.2, 0.9, 0.6]), 1) == (0.9, True, 0.6)
    assert written.written_rows(np.array([0.7, 0.3, 0.6]), 1) == (0.7, False, 0.7)


def test_word_overlap_is_the_share_of_the_questions_own_pairs():
    assert written.overlap("缓存用什么", "用 Redis 做缓存") == 0.25
    assert written.overlap("?", "anything") == 0.0
