import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_daily_install as check  # noqa: E402

PROBES = [{"qid": "A", "targets": [1]}, {"qid": "B", "targets": [2, 3]}, {"qid": "N", "targets": []}]


def test_a_question_counts_when_a_target_is_in_its_first_five_and_no_answer_questions_do_not_count():
    rows = [[9, 8, 7, 6, 5, 1], [3, 9], [4]]  # the first target comes sixth, the second question's comes first
    assert check.score(PROBES, rows) == {"hit5": 1, "first": 1, "of": 2, "missed": ["A"]}


def test_what_to_fix_names_the_stemmer_first_and_the_sidecar_the_plugin_gave_up_on():
    words = {"hit5": check.WORDS_UNSTEMMED}
    slow = {"hit5": 26, "gave_up": 12, "budget_ms": 400.0, "ms_max": 950.0}
    found = check.findings(False, words, slow)
    assert "snowballstemmer" in found[0] and "semantic_timeout_ms" in found[1] and len(found) == 2
    assert check.findings(True, {"hit5": check.WORDS}, {"hit5": check.CLOSEST, "gave_up": 0}) == []
    assert "not checked" in check.findings(True, {"hit5": check.WORDS}, None)[0]


def report(stemmer, closest_missed, gave_up=0):
    def step(name, missed):
        return {"hit5": 36 - len(missed), "of": 36, "missed": missed, "first": 0}

    words = check.REFERENCE[stemmer, "words_only"]
    return {"standard": {"name": check.STANDARD, "data": check.data_id()}, "stemmer": stemmer,
            "words_only": step("words_only", words),
            "closest_fact": {**step("closest_fact", closest_missed), "gave_up": gave_up, "budget_ms": 400.0,
                             "ms_max": 950.0}}


def test_a_report_is_a_standard_result_only_when_it_misses_what_the_reference_misses_for_its_machine():
    good = check.verify(report(True, check.REFERENCE[True, "closest_fact"]))
    assert good == {"standard_result": True, "problems": [], "to_fix": []}
    # without the stemmer the report still matches its own reference, and says what the machine has to fix
    unstemmed = check.verify(report(False, check.REFERENCE[False, "closest_fact"]))
    assert unstemmed["standard_result"] and "snowballstemmer" in unstemmed["to_fix"][0]
    # a slow sidecar: one more question missed than the reference, and the timeout is what to fix
    slow = check.verify(report(True, ["P5", "P7", "P10", "C6"], gave_up=3))
    assert not slow["standard_result"] and "['P7']" in slow["problems"][0] and "semantic_timeout_ms" in slow["to_fix"][0]
    # another set of questions, or a count that was typed in rather than measured
    other = report(True, [])
    other["standard"]["data"] = "0" * 12
    assert check.verify(other)["problems"][0].startswith("not daily-check-1")
    typed = report(True, check.REFERENCE[True, "closest_fact"])
    typed["closest_fact"]["hit5"] = 36
    assert "do not add up" in check.verify(typed)["problems"][0]
