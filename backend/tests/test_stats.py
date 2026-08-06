"""The median, and why it needed its own home.

Index and peer medians each carried their own `sorted(values)[len(values) // 2]`,
which is the upper of the two middle values, not the midpoint. The bias is always
upward and only appears on even-length groups, so it hides on any odd-length one.
"""

from __future__ import annotations

from app.services.stats import median_of


def test_an_even_group_averages_the_two_middle_values() -> None:
    # Reliance's four refiner peers. The old code returned 23.99 - Reliance's
    # own P/E - putting it at the middle of a group it sits at the expensive
    # end of. Three of the four are cheaper than it.
    assert median_of([6.00, 8.24, 23.99, 50.45]) == 16.115


def test_an_odd_group_takes_the_middle_value() -> None:
    assert median_of([6.00, 23.99, 50.45]) == 23.99


def test_order_does_not_matter() -> None:
    assert median_of([50.45, 6.00, 23.99, 8.24]) == median_of([6.00, 8.24, 23.99, 50.45])


def test_a_pair_averages() -> None:
    assert median_of([10.0, 20.0]) == 15.0


def test_a_single_value_is_its_own_median() -> None:
    assert median_of([42.0]) == 42.0


def test_nothing_to_average_is_none_not_zero() -> None:
    # Zero would read as a real median of zero on a valuation column.
    assert median_of([]) is None


def test_negatives_are_ordered_numerically() -> None:
    assert median_of([-15.0, -5.0, 5.0, 15.0]) == 0.0
