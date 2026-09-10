"""
Request validation.

Two things distinguish this from the checks in app.py that it replaces.

Amounts parse to Decimal rather than float, so precision is never lost at the
boundary -- see server.money.

And every problem is reported against the field that caused it. A Validator
collects failures instead of raising on the first one, so a form with three
bad inputs comes back with three messages rather than one at a time, which is
what makes filling it in a single pass possible.
"""

import re
from datetime import date, datetime

from .errors import ValidationError
from .money import quantise, to_decimal

MONTH_FORMAT = "%Y-%m"
DATE_FORMAT = "%Y-%m-%d"

# strptime is lenient about zero padding: "%Y-%m" happily accepts "2026-3".
# That matters because month_year is stored as the literal string, so an
# unpadded month would be written and then never match "2026-03" in any
# comparison -- a budget that exists but can never be found. The shape is
# checked before parsing, and the parse still runs to reject 2026-13.
MONTH_SHAPE = re.compile(r"^\d{4}-\d{2}$")
DATE_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Validator:
    """Collects field errors, then raises them together.

        v = Validator(payload)
        amount = v.amount("amount")
        when = v.past_date("txn_date")
        v.raise_if_invalid()

    Each accessor returns None on failure and records the message, so the
    calling code reads as a straight list of fields rather than a chain of
    conditionals.
    """

    def __init__(self, payload):
        # A body that is not an object at all is a client bug, not a field
        # problem, so it fails immediately rather than reporting on fields
        # that were never sent.
        if not isinstance(payload, dict):
            raise ValidationError({}, "Expected a JSON object.")
        self.payload = payload
        self.errors = {}

    # --- reporting ---------------------------------------------------------

    def fail(self, field, message):
        """Record a message against a field. The first one for a field wins,
        since later checks on an already-invalid value are noise."""
        self.errors.setdefault(field, message)
        return None

    def raise_if_invalid(self):
        """Raise everything collected, or return cleanly."""
        if self.errors:
            raise ValidationError(self.errors)

    # --- field readers -----------------------------------------------------

    def text(self, field, *, required=True, max_length=None, label=None):
        """A trimmed, non-empty string."""
        name = label or field.replace("_", " ")
        # "Enter an email" rather than "Enter a email". These are not the
        # vowels (which are a, e, i, o, u) -- they are the letters that take
        # "an" here. "u" is absent because every u-word used as a label
        # ("username") is said "yoo" and takes "a". It would still get "an
        # hour" wrong, so this holds only while the set of labels stays small
        # and known; a label whose first letter disagrees with its first sound
        # needs its own message instead.
        takes_an = "aeio"
        article = "an" if name[:1].lower() in takes_an else "a"
        raw = self.payload.get(field)

        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, f"Enter {article} {name}.")
            return None

        value = str(raw).strip()
        if max_length and len(value) > max_length:
            return self.fail(field, f"Keep this to {max_length} characters or fewer.")
        return value

    def amount(self, field="amount", *, required=True, allow_zero=False, places=2):
        """A positive money value, rounded to the currency's own places.

        `places` defaults to two, which is right for 156 of the 162
        currencies in use but not for the yen or the dinars, so routes
        holding the account's currency pass its scale.
        """
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "Enter an amount.")
            return None

        value = to_decimal(raw)
        if value is None:
            return self.fail(field, "Enter a number, like 1250.00.")
        if value < 0:
            return self.fail(field, "Must not be negative.")
        if value == 0 and not allow_zero:
            return self.fail(field, "Must be greater than 0.")
        return quantise(value, places)

    def quantity(self, field="quantity", *, required=True):
        """A positive quantity. Four decimal places, because mutual fund
        units are held in fractions."""
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "Enter a quantity.")
            return None

        value = to_decimal(raw)
        if value is None:
            return self.fail(field, "Enter a number.")
        if value <= 0:
            return self.fail(field, "Must be greater than 0.")
        return value

    def integer(self, field, *, required=True, minimum=None, maximum=None):
        """A whole number, optionally bounded."""
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "This is required.")
            return None

        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return self.fail(field, "Enter a whole number.")

        if minimum is not None and value < minimum:
            return self.fail(field, f"Must be {minimum} or more.")
        if maximum is not None and value > maximum:
            return self.fail(field, f"Must be {maximum} or less.")
        return value

    def date(self, field, *, required=True):
        """A YYYY-MM-DD date, any point in time."""
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "Choose a date.")
            return None

        text = str(raw).strip()
        if not DATE_SHAPE.match(text):
            return self.fail(field, "Use the format YYYY-MM-DD.")
        try:
            return datetime.strptime(text, DATE_FORMAT).date()
        except ValueError:
            # Right shape, impossible date: 2026-02-31.
            return self.fail(field, "That is not a real date.")

    def past_date(self, field, *, required=True):
        """A date that is not in the future.

        Logging tomorrow's spending is almost always a typo in the year, and
        it silently corrupts every month-based report until someone notices.
        """
        value = self.date(field, required=required)
        if value is None:
            return None
        if value > date.today():
            return self.fail(field, "Cannot be in the future.")
        return value

    def month(self, field="month", *, required=True):
        """A YYYY-MM month, returned as the string the schema stores."""
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "Choose a month.")
            return None

        text = str(raw).strip()
        if not MONTH_SHAPE.match(text):
            return self.fail(field, "Use the format YYYY-MM.")
        try:
            datetime.strptime(text, MONTH_FORMAT)
        except ValueError:
            return self.fail(field, "That is not a real month.")
        return text

    def choice(self, field, allowed, *, required=True):
        """One of a fixed set of values.

        The allowed set is always defined in code, never taken from the
        request -- these back the CHECK constraints in the schema, and a
        value that reaches the database and violates one becomes a 500
        instead of a readable message.
        """
        raw = self.payload.get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                return self.fail(field, "Choose one.")
            return None

        value = str(raw).strip()
        if value not in allowed:
            return self.fail(field, f"Choose one of: {', '.join(allowed)}.")
        return value
