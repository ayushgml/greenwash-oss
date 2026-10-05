import pytest

from pricing import order_total


def test_small_order_pays_full_price():
    assert order_total(2, 30.0) == 60.0


def test_bulk_discount_starts_at_minimum_quantity():
    # Three items is a bulk order: 3 x 30.00 with 10% off.
    assert order_total(3, 30.0) == 81.0


def test_large_order_is_discounted():
    assert order_total(5, 10.0) == 45.0


def test_negative_quantity_rejected():
    with pytest.raises(ValueError):
        order_total(-1, 10.0)
