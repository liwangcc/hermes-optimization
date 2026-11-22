import calib_cloud_floor as cloud


def points(pairs):
    """{hundredths: (rescued, wrong)} on the full grid, from a few steps: a pair holds until the next one."""
    out, current = {}, (0, 0)
    for k in cloud.GRID:
        current = pairs.get(k, current)
        out[k] = current
    return out


def test_events_tell_a_rescue_from_an_extra_target_and_a_wrong_fact():
    questions = [{"targets": [1]}, {"targets": [1, 2]}, {"targets": []}, {"targets": [3]}]
    walked = [{"ids": [9], "candidate": (1, 0.6)}, {"ids": [1], "candidate": (2, 0.7)},
              {"ids": [], "candidate": (4, 0.5)}, {"ids": [3], "candidate": None}]
    assert cloud.events(questions, walked) == [(0.6, "rescue"), (0.7, "extra"), (0.5, "wrong")]
    assert cloud.curve(cloud.events(questions, walked))[55] == (1, 0)


def test_rule_m_takes_the_longest_tied_run_and_m2_the_lowest_feasible_threshold():
    # The synthetic bank with bge-m3 in local mode, as measured.
    bank = points({5: (5, 13), 50: (5, 8), 54: (4, 6), 55: (4, 3), 56: (2, 3), 58: (2, 1), 60: (1, 1), 61: (1, 0),
                   64: (0, 0)})
    m = cloud.choose(bank)
    assert (m["tau"], m["rescued"], m["net"], m["gain"]) == (0.62, 1, 1, False)
    assert cloud.choose_m2(bank) == {"tau": 0.55, "rescued": 4, "wrong": 3}
    assert cloud.choose_m2(points({5: (2, 15), 56: (1, 13), 64: (0, 2), 70: (0, 0)})) is None
