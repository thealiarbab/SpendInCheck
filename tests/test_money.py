"""
The server half of the money contract. web/src/lib/money.test.ts is the other.
"""

import datetime
from decimal import Decimal

from server import money


def test_parses_the_shapes_people_actually_submit():
    assert money.to_decimal("1234.50") == Decimal("1234.50")
    assert money.to_decimal("₹1,234.50") == Decimal("1234.50")
    assert money.to_decimal(" 99 ") == Decimal("99")


def test_unusable_input_is_none_rather_than_zero():
    """Zero would be indistinguishable from someone genuinely entering 0."""
    assert money.to_decimal("abc") is None
    assert money.to_decimal("") is None
    assert money.to_decimal(None) is None


def test_parses_through_str_so_float_error_is_not_inherited():
    """Decimal(0.1) keeps the float's error; Decimal("0.1") does not."""
    assert money.to_decimal(0.1) == Decimal("0.1")
    assert Decimal(0.1) != Decimal("0.1")


def test_rounds_half_away_from_zero_not_to_even():
    """A ledger reader expects 0.005 to round up every time."""
    assert money.quantise(Decimal("0.005")) == Decimal("0.01")
    assert money.quantise(Decimal("0.015")) == Decimal("0.02")
    # Decimal's own default would have given 0.00 and 0.02.


def test_serialises_to_a_fixed_two_place_string():
    assert money.serialise(Decimal("1234.5")) == "1234.50"
    assert money.serialise(Decimal("7")) == "7.00"
    assert money.serialise(Decimal("-0.05")) == "-0.05"
    assert money.serialise(None) is None


def test_row_names_fields_and_converts_values():
    named = money.row(
        ("transaction_id", "amount", "txn_date"),
        (1, Decimal("9.5"), datetime.date(2026, 3, 1)),
    )
    assert named == {"transaction_id": 1, "amount": "9.50", "txn_date": "2026-03-01"}


def test_a_column_of_amounts_totals_exactly():
    """The reason this module exists, stated as a test."""
    total = Decimal("0")
    drifting = 0.0
    for _ in range(200):
        total += money.to_decimal("0.10")
        drifting += 0.1

    assert money.serialise(total) == "20.00"

    # The float path does not. Note that Python's built-in sum() would have
    # hidden this -- since 3.12 it uses compensated summation and returns
    # exactly 20.0 -- but accumulating in a loop, which is what aggregating
    # rows actually looks like, drifts to 20.000000000000014.
    assert drifting != 20
