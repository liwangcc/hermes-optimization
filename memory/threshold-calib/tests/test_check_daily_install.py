import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_daily_install as check  # noqa: E402

PROBES = [{"targets": [1]}, {"targets": [2, 3]}, {"targets": []}]


def test_a_question_counts_when_a_target_is_in_its_first_five_and_no_answer_questions_do_not_count():
    rows = [[9, 8, 7, 6, 5, 1], [3, 9], [4]]  # the first target comes sixth, the second question's comes first
    assert check.score(PROBES, rows) == {"hit5": 1, "first": 1, "of": 2}


def test_what_to_fix_names_the_stemmer_first_and_the_sidecar_the_plugin_gave_up_on():
    words = {"hit5": check.WORDS_UNSTEMMED}
    slow = {"hit5": 26, "gave_up": 12, "budget_ms": 400.0, "ms_max": 950.0}
    found = check.findings(False, words, slow)
    assert "snowballstemmer" in found[0] and "semantic_timeout_ms" in found[1] and len(found) == 2
    assert check.findings(True, {"hit5": check.WORDS}, {"hit5": check.CLOSEST, "gave_up": 0}) == []
    assert "not checked" in check.findings(True, {"hit5": check.WORDS}, None)[0]
