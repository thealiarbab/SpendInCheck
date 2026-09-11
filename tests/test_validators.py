"""
Validation reports every bad field at once, and reports it usefully.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from server.errors import ValidationError
from server.validators import Validator


def collect(payload, read):
    """Run `read` against a validator and return the field errors it raised."""
    validator = Validator(payload)
    read(validator)
    try:
        validator.raise_if_invalid()
    except ValidationError as error:
        return error.fields
    return {}


def test_reports_every_bad_field_in_one_response():
    """The point of collecting rather than raising on the first failure: a
    form with three problems is fixable in one pass, not three."""
    errors = collect(
        {"amount": "0", "txn_date": "2099-01-01", "txn_type": "Nope"},
        lambda v: (
            v.amount("amount"),
            v.past_date("txn_date"),
            v.choice("txn_type", ("Income", "Expense")),
        ),
    )
    assert set(errors) == {"amount", "txn_date", "txn_type"}


def test_amounts_arrive_as_decimal_never_float():
    validator = Validator({"amount": "1234.567"})
    amount = validator.amount("amount")
    validator.raise_if_invalid()
    assert isinstance(amount, Decimal)
    assert amount == Decimal("1234.57")


def test_amount_rejects_zero_and_negatives_with_distinct_messages():
    assert collect({"amount": "0"}, lambda v: v.amount())["amount"] == "Must be greater than 0."
    assert collect({"amount": "-5"}, lambda v: v.amount())["amount"] == "Must not be negative."
    assert "1250.00" in collect({"amount": "abc"}, lambda v: v.amount())["amount"]


def test_future_dates_are_rejected():
    """A date in the future is nearly always a mistyped year, and it corrupts
    every month-based report until somebody notices."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert collect({"d": tomorrow}, lambda v: v.past_date("d"))["d"] == "Cannot be in the future."

    today = date.today().isoformat()
    assert collect({"d": today}, lambda v: v.past_date("d")) == {}


def test_quantity_keeps_fractional_units():
    """Mutual fund holdings are not whole numbers."""
    validator = Validator({"quantity": "12.3456"})
    assert validator.quantity() == Decimal("12.3456")
    validator.raise_if_invalid()


def test_month_must_be_zero_padded():
    """strptime accepts "2026-3" for %Y-%m. month_year is stored as the
    literal string, so an unpadded month would be written and then never
    match "2026-03" in any comparison -- a budget that exists but can never
    be found."""
    assert collect({"month": "2026-3"}, lambda v: v.month())["month"] == "Use the format YYYY-MM."
    assert collect({"month": "2026-13"}, lambda v: v.month())["month"] == "That is not a real month."

    validator = Validator({"month": "2026-03"})
    assert validator.month() == "2026-03"
    validator.raise_if_invalid()


def test_dates_must_be_zero_padded_and_real():
    assert collect({"d": "2026-3-1"}, lambda v: v.date("d"))["d"] == "Use the format YYYY-MM-DD."
    assert collect({"d": "2026-02-31"}, lambda v: v.date("d"))["d"] == "That is not a real date."


def test_optional_fields_may_be_absent():
    validator = Validator({})
    assert validator.text("description", required=False) is None
    assert validator.amount("amount", required=False) is None
    validator.raise_if_invalid()


def test_a_non_object_body_fails_immediately():
    """Reporting on fields that were never sent would be misleading."""
    with pytest.raises(ValidationError):
        Validator(["not", "an", "object"])


# --- crashes found by fuzzing the live API ----------------------------------
#
# Every one of these returned a 500 with an empty body in production, deep in
# a query or in psycopg2, on input a client could send. A validator's whole
# job is to turn bad input into a named 422 at the door, so each is now a
# clean rejection rather than a stack trace.

@pytest.mark.parametrize("evil", ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity",
                                  "inf", "-inf", "1e309"])
def test_amount_rejects_non_finite_values(evil):
    """Decimal("NaN") and Decimal("1e309") parse without error and then blow
    up the moment anything compares or quantises them. is_finite() is the
    guard; without it these reach money.quantise() as a 500."""
    assert collect({"amount": evil},
                   lambda v: v.amount())["amount"] == "Enter a number, like 1250.00."


def test_amount_rejects_an_absurdly_large_number():
    """A 400-digit integer is valid Decimal syntax and a fuzzing payload, not
    a sum of money. Rejected before it can overflow anything downstream."""
    assert collect({"amount": "9" * 400},
                   lambda v: v.amount())["amount"] == "Enter a number, like 1250.00."


def test_amount_still_accepts_real_figures():
    """The guard must not cost legitimate money. Large but real values pass."""
    for good, expected in [("1250.00", "1250.00"), ("-99", "-99.00"),
                           ("1e6", "1000000.00"), ("999999999999.99", "999999999999.99")]:
        validator = Validator({"amount": good})
        result = validator.amount(allow_negative=True)
        validator.raise_if_invalid()
        assert str(result) == expected


def test_text_strips_nul_bytes_before_the_database_sees_them():
    """PostgreSQL cannot store a NUL in a text column; it arrives as a
    ValueError from psycopg2, which is a 500 on a name a person could paste.
    str.strip() does not remove NUL, so text() does it explicitly."""
    nul = chr(0)
    validator = Validator({"name": "a" + nul + "b" + nul + "c"})
    assert validator.text("name") == "abc"
    validator.raise_if_invalid()


def test_a_name_that_is_only_nul_counts_as_empty():
    """The strip runs before the required check, so NUL-only input is refused
    as empty rather than reaching the database as an empty string."""
    nul = chr(0)
    assert collect({"name": nul + nul},
                   lambda v: v.text("name"))["name"] == "Enter a name."


def test_text_keeps_ordinary_unicode():
    """The NUL strip must not touch legitimate multibyte characters -- an
    emoji category name is fine, and started this whole investigation."""
    validator = Validator({"name": "\U0001f4b8 Fun Money"})
    assert validator.text("name") == "\U0001f4b8 Fun Money"
    validator.raise_if_invalid()
