import pytest

from stats import median


def test_odd_length():
    assert median([3, 1, 2]) == 2


def test_even_length_averages_middle_pair():
    assert median([4, 1, 3, 2]) == 2.5


def test_empty_rejected():
    with pytest.raises(ValueError):
        median([])
