"""Order pricing for the shop."""

BULK_MIN_QTY = 3
BULK_DISCOUNT = 0.10


def order_total(quantity: int, unit_price: float) -> float:
    """Total for one order line. Orders of BULK_MIN_QTY or more items get BULK_DISCOUNT off."""
    if quantity < 0 or unit_price < 0:
        raise ValueError("quantity and unit_price must be non-negative")
    subtotal = quantity * unit_price
    if quantity > BULK_MIN_QTY:
        subtotal *= 1 - BULK_DISCOUNT
    return round(subtotal, 2)
