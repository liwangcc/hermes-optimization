import calib_lexical_levers as levers


def test_non_targets_are_counted_per_fact_and_a_partial_target_loss_is_seen():
    q = {"targets": [1, 2]}
    got = levers.record(q, [1, 2, 7], [1, 8, 9])
    assert (got["hit"], got["lost_rows"], got["lost_targets"]) == (True, False, 1)
    assert (got["shown_other"], got["added_other"], got["removed_other"], got["confusion"]) == (2, 2, 1, True)


def test_a_no_answer_row_is_noise_only_while_it_shows_something():
    assert levers.record({"targets": []}, [4], [])["noise"] == 0
    row = levers.record({"targets": []}, [], [4, 5])
    assert (row["noise"], row["shown_other"], row["added_other"], row["labelled"]) == (True, 2, 2, False)
