from datetime import date

from dates import invoice_date


def test_two_digit_month():
    assert invoice_date(date(2026, 11, 20)) == "2026-11-20"


def test_single_digit_month_is_padded():
    assert invoice_date(date(2026, 9, 7)) == "2026-09-07"
