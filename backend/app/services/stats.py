"""Summary statistics used by more than one service."""

from __future__ import annotations

from statistics import median


def median_of(values: list[float]) -> float | None:
    """The median, averaging the two middle values on an even count.

    Both index and peer medians used to take `sorted(values)[len(values) // 2]`,
    which is the upper of the two middle values rather than the midpoint. On
    Reliance's four refiner peers - P/Es of 6.00, 8.24, 23.99 and 50.45 - that
    reported 23.99 where the median is 16.12, putting Reliance itself at the
    middle of a group it sits at the expensive end of.

    The bias is always upward and only shows on even-length groups, so it hides
    on any list with an odd number of members.
    """
    return median(values) if values else None
