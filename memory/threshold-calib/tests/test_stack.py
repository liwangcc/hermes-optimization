from collections import Counter

import numpy as np

import calib_stack as stack


class _Fixture:
    """Forty facts; fact 1 is the closest at *top*, fact 2 next, the rest spread between 0.10 and 0.21."""

    def __init__(self, top, second=0.2):
        self.ids = np.arange(1, 41)
        self.trusted = np.ones(40, dtype=bool)
        self._c = np.array([top, second] + [0.10 + 0.01 * (k % 12) for k in range(38)])

    def cos(self, i, view="daily"):
        return self._c

    def fits(self, i, fact_id):
        return True


def test_a_fact_between_the_margins_needs_a_yes_and_one_above_them_does_not():
    asked = []

    def check(answer):
        return lambda fx, i, fact_id: asked.append(fact_id) or answer

    between, above = _Fixture(0.30), _Fixture(0.60)
    margin = (between._c - between._c.mean()) / between._c.std() - np.sqrt(2 * np.log(40))
    assert stack.CHECK_MARGIN <= margin[0] < stack.RECALL_MARGIN  # the fixture is where the test needs it
    assert stack.meaning_fact(between, 0, set(), None, Counter()) is None  # default margin: not offered
    assert stack.meaning_fact(between, 0, set(), check(True), Counter()) == 1
    assert stack.meaning_fact(between, 0, set(), check(False), Counter()) is None
    assert stack.meaning_fact(between, 0, {1}, check(True), Counter()) is None  # shown already: nothing else stands out
    assert asked == [1, 1]
    assert stack.meaning_fact(above, 0, set(), check(False), Counter()) == 1 and asked == [1, 1]  # not asked about
