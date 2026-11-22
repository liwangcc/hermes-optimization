import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calib_model_tau as tau  # noqa: E402


def bank(wrong_b):
    """Two sets of 10 no-answer questions each: 'a' has rescues at 0.70, 'b' has wrong facts at the given cosines."""
    return {"a": {"events": [[0.70, "rescue", True]] * 6, "answerable": 10, "no_answer": 10},
            "b": {"events": [[c, "wrong", False] for c in wrong_b] + [[0.9, "wrong", True]],
                  "answerable": 10, "no_answer": 10}}


def store(curve, quiet, own):
    """A frozen store's run: 10 answerable and 10 no-answer questions, counts per threshold only."""
    return {"step1": {"off": {"rows": 20, "labelled": 10}},
            "step3": {"local": {"curve": curve, "wrong_no_answer": quiet, "choice_m2": own}}}


def test_the_lowest_threshold_within_the_cap_is_taken_over_the_bank_or_over_every_set():
    parts = bank([0.40, 0.50, 0.60])  # the bank's cap is 2 of 20, one set's is 1 of 10
    pooled, each = tau.pick(parts), tau.pick(parts, every_set=True)
    assert (pooled["tau"], pooled["rescued"], pooled["wrong_no_answer"]) == (0.41, 6, 2)
    assert (each["tau"], each["wrong_no_answer"], each["per_set"]) == (0.51, 1, {"a": [6, 0], "b": [0, 1]})
    assert tau.report("m", parts)["semantic_tau"] == 0.51  # every set within the cap is the value


def test_a_model_that_rescues_too_few_gets_no_threshold():
    parts = bank([0.80, 0.81, 0.82])  # one set's cap takes 0.82, above every rescue
    report = tau.report("m", parts)
    assert report["every_set"]["tau"] == 0.82 and not report["every_set"]["adds_something"]
    assert report["semantic_tau"] is None and report["bank"] == {"answerable": 20, "no_answer": 20}


def test_the_value_is_read_on_a_store_against_its_own_labels():
    picked = tau.report("m", bank([0.40, 0.50, 0.60]))
    held = tau.on_store(store({"0.51": [3, 2], "0.41": [4, 5]}, {"0.51": 1, "0.41": 3}, {"tau": 0.5}), picked)
    assert held["every_set"] == {"tau": 0.51, "rescued": 3, "wrong": 2, "wrong_no_answer": 1}
    assert held["cap_holds"] and held["verdict_holds"] and held["pooled"]["wrong_no_answer"] == 3
    worse = tau.on_store(store({"0.51": [1, 2], "0.41": [1, 2]}, {"0.51": 2, "0.41": 2}, None), picked)
    assert not worse["cap_holds"] and not worse["verdict_holds"]  # 2 of 10 is over the cap, wrong outnumbers rescued
    nothing = tau.report("m", bank([0.80, 0.81, 0.82]))  # the bank says the model adds nothing
    agreed = tau.on_store(store({"0.82": [0, 0], "0.81": [0, 0]}, {"0.82": 0, "0.81": 0}, None), nothing)
    assert agreed["verdict_holds"]
    assert not tau.on_store(store({"0.82": [0, 0], "0.81": [0, 0]}, {"0.82": 0, "0.81": 0}, {"tau": 0.6}),
                            nothing)["verdict_holds"]  # the store's own labels found a usable threshold
