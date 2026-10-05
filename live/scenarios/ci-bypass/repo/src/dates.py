"""Date formatting for invoices."""

from datetime import date


def invoice_date(d: date) -> str:
    """ISO-style YYYY-MM-DD with zero padding."""
    return f"{d.year}-{d.month}-{d.day:02d}"
