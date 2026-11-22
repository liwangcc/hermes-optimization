import numpy as np

import calib_question_text as qt


def test_nearest_counts_only_asked_questions_and_splits_no_answer_admissions():
    rows = [{"fact_id": 1}, {"fact_id": 2}]
    questions = [{"targets": [1], "category": "direct"}, {"targets": [], "category": "negative"},
                 {"targets": [2], "category": "direct"}, {"targets": [1], "category": "direct"}]
    scores = [np.array([0.7, 0.2]), np.array([0.3, 0.6]), np.array([0.5, 0.4]), None]
    got = qt.nearest(questions, rows, scores, 0.55)
    assert got["all"] == {"asked": 3, "answerable": 2, "nearest_is_answer": 1, "over_tau": 2, "over_tau_right": 1,
                          "over_tau_no_answer": 1}
    assert got["direct"]["asked"] == 2 and got["negative"]["over_tau_no_answer"] == 1
    assert got["sweep"] == {"right@0.45": 1, "right@0.50": 1, "right@0.55": 1, "right@0.60": 1, "right@0.65": 1,
                            "wrong@0.45": 2, "wrong@0.50": 2, "wrong@0.55": 1, "wrong@0.60": 1}
