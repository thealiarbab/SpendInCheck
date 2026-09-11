"""
Money on the way in and out of the API.

The database stores DECIMAL and psycopg2 returns Decimal, which is exactly
right and must survive the trip to the client. The tempting shortcut is
float(), and it is where rupees go missing: 0.1 has no exact binary
representation, so a column of amounts drifts a paisa at a time and a report
total quietly stops matching the rows above it.

So money crosses the wire as a STRING, never a JSON number. The client parses
it to integer paise, does its arithmetic there, and formats once at render --
see web/src/lib/money.ts, which is the other half of this contract.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import currency

# Two decimal places, matching DECIMAL(10,2) in the schema.
PAISA = Decimal("0.01")

# The scale for a currency with `places` decimals: Decimal("0.01") for two,
# Decimal("1") for a currency with no minor unit, Decimal("0.001") for the
# dinars. Built once rather than from a string each call.
_SCALES = {places: Decimal(1).scaleb(-places) for places in (0, 2, 3)}

# Four, matching DECIMAL(10,4) -- the scale investments.quantity is stored at.
UNIT = Decimal("0.0001")

# Columns that are counts of units rather than sums of money. Quantising one
# of these to paise loses real precision: a mutual fund holding of 12.3456
# units would leave the database as "12.35" and never come back.
QUANTITY_FIELDS = frozenset({"quantity"})


def to_decimal(raw_value):
    """Parse submitted input into a Decimal, or return None if unusable.

    Decimal(str) rather than Decimal(float): Decimal(0.1) preserves the
    float's error and produces 0.1000000000000000055511151231257827, which
    defeats the point of using Decimal at all.

    Accepts a rupee sign and digit grouping, since a pasted figure often
    carries them.
    """
    if raw_value is None:
        return None

    text = str(raw_value).strip().replace("₹", "").replace(",", "").replace(" ", "")
    if not text:
        return None

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None

    # "NaN" and "Infinity" are valid Decimal syntax and parse without error,
    # then blow up the moment anything compares or quantises them -- which is
    # a 500, deep in a query, on input that should have been refused at the
    # door. is_finite() is false for both, and for sNaN. A 400-digit integer
    # is finite and legitimate as syntax, but it is not a sum of money; the
    # scale of the largest real balance is comfortably inside fifteen digits,
    # so anything past that is a fuzzing payload, not an amount.
    if not value.is_finite() or abs(value.adjusted()) > 15:
        return None
    return value


def quantise(amount, places=2):
    """Round a Decimal to a currency's own number of places, half away from zero.

    ROUND_HALF_UP rather than Decimal's ROUND_HALF_EVEN default: bankers'
    rounding is correct for statistics and surprising in a ledger, where a
    person expects 0.005 to become 0.01 every time.

    `places` defaults to two because most currencies have two, but it is not
    universal -- the yen has no minor unit and the dinars have three -- so
    callers holding an account's currency pass its own scale.
    """
    if amount is None:
        return None
    return amount.quantize(_SCALES[places], rounding=ROUND_HALF_UP)


def serialise(amount, places=2):
    """Render a Decimal as the fixed-place string the API sends.

    None becomes None so a genuinely absent amount stays absent rather than
    arriving as "0.00" and being read as a real zero.
    """
    if amount is None:
        return None
    return f"{quantise(Decimal(amount), places):.{places}f}"


def serialise_quantity(amount):
    """Render a Decimal at the four places investments.quantity is stored at."""
    if amount is None:
        return None
    return f"{Decimal(amount).quantize(UNIT, rounding=ROUND_HALF_UP):.4f}"


def jsonify_value(value, field_name=None, places=2):
    """Convert one value into something json can serialise.

    Decimal becomes a string, dates become ISO-8601, and anything else is
    returned untouched. Applied by row(), below, which passes the column
    name so a quantity is not rounded to paise like an amount.
    """
    if isinstance(value, Decimal):
        if field_name in QUANTITY_FIELDS:
            return serialise_quantity(value)
        return serialise(value, places)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def row(field_names, values, places=2):
    """Zip a database row into a dict, converting each value for JSON.

    The operations layer returns tuples, which is fine for SQL and wrong for
    an API: a client reading result[4] breaks the moment a column is added.
    Naming the fields at the route boundary keeps the SQL layer unchanged
    while the JSON stays stable.
    """
    return {name: jsonify_value(value, name, places)
            for name, value in zip(field_names, values)}


def rows(field_names, values_list, places=2):
    """Apply row() to a list of database rows."""
    return [row(field_names, values, places) for values in values_list]


def places_for(code):
    """How many decimal places money in this currency is written to."""
    return currency.decimals(code or currency.DEFAULT)
