"""Small statistics helpers for the metrics dashboard."""


def median(values: list[float]) -> float:
    """Median of a non-empty list."""
    if not values:
        raise ValueError("median of empty list")
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle]
