"""The price service, mostly without the network.

Every test but the last stubs the HTTP call. That is deliberate: what is
worth testing here is the translation -- rupee floats one way, integer
paise the other, a fraction that is not a percentage -- and none of that
needs somebody else's server to be up. A suite that fails when an upstream
is slow teaches people to ignore it.

The last test does make one real call, and skips rather than fails when it
cannot. Its job is the thing stubs cannot do: notice the day the response
changes shape.
"""

from decimal import Decimal

import pytest

from server.services import stocksaathi


# --- symbols ----------------------------------------------------------------

@pytest.mark.parametrize("given, expected", [
    ("reliance", "RELIANCE"),
    ("  TCS  ", "TCS"),
    ("INFY.BO", "INFY.BO"),
    # Real symbols that are not plain letters.
    ("M&M", "M&M"),
    ("BAJAJ-AUTO", "BAJAJ-AUTO"),
])
def test_a_usable_symbol_is_normalised(given, expected):
    assert stocksaathi.normalise(given) == expected


@pytest.mark.parametrize("given", [
    None, "", "   ",
    "a b",          # a phrase, not a symbol
    "RELIANCE.XX",  # only .BO means anything
    ".BO",          # a suffix with nothing in front of it
    "MF_12345",     # mutual fund codes are not quotable here
])
def test_anything_that_is_not_a_symbol_is_refused(given):
    """Refused here rather than sent, because the round trip would only
    come back empty and a person would be waiting on it."""
    assert stocksaathi.normalise(given) is None


# --- the units --------------------------------------------------------------

def test_a_price_does_not_pass_through_a_binary_float(monkeypatch):
    """The whole reason _rupees goes via str().

    Decimal(1274.1) is 1274.0999999999999090505298227071762084960937500.
    Money that has been through a float cannot be made exact again, so it
    must never become one.
    """
    monkeypatch.setattr(stocksaathi, "_get", lambda *a, **k: {
        "ok": True, "quotes": {"X": {"price": 1274.1, "prev_close": 0.1}}})
    quote = stocksaathi.live_quotes(["X"])["X"]
    assert quote["price"] == Decimal("1274.1")
    assert str(quote["price"]) == "1274.1"
    assert quote["prev_close"] == Decimal("0.1")


def test_history_is_paise_and_comes_back_as_rupees(monkeypatch):
    """The trap this module exists to own: /live-quote sends rupees and
    /history sends paise, for the same instrument on the same day."""
    monkeypatch.setattr(stocksaathi, "_get", lambda *a, **k: {
        "ok": True,
        "ohlc": [{"t": 1788493500000, "c": 132200},
                 {"t": 1788752700000, "c": 130950},
                 {"t": 1788839100000, "c": 1}],
    })
    closes = stocksaathi.closing_prices("RELIANCE", days=5)
    assert [price for _, price in closes] == [
        Decimal("1322"), Decimal("1309.5"), Decimal("0.01")]
    # Oldest first, so a caller can chart it without sorting.
    assert [at for at, _ in closes] == sorted(at for at, _ in closes)


def test_the_change_is_left_as_the_fraction_it_arrives_as(monkeypatch):
    """Not multiplied by 100 here.

    Doing it in two places is how a -0.39% day gets rendered as -39%. The
    client formats it, once.
    """
    monkeypatch.setattr(stocksaathi, "_get", lambda *a, **k: {
        "ok": True, "quotes": {"X": {"price": 10, "change_pct": -0.0039}}})
    assert stocksaathi.live_quotes(["X"])["X"]["change"] == -0.0039


# --- failure ----------------------------------------------------------------

def test_an_unreachable_api_is_an_empty_result_not_an_exception(monkeypatch):
    """A holdings screen whose price feed is down shows the prices it
    already had. It does not show an error page."""
    monkeypatch.setattr(stocksaathi, "_get", lambda *a, **k: None)
    assert stocksaathi.live_quotes(["RELIANCE"]) == {}
    assert stocksaathi.closing_prices("RELIANCE") == []


def test_a_symbol_with_no_price_is_absent_rather_than_null(monkeypatch):
    """So `symbol in quotes` is the whole test a caller needs.

    The upstream sends an explicit null for a symbol it does not know, and
    passing that through would make every caller check for two things.
    """
    monkeypatch.setattr(stocksaathi, "_get", lambda *a, **k: {
        "ok": True, "quotes": {"RELIANCE": {"price": 1274.0},
                               "NOSUCHTHING": None,
                               "DELISTED": {"price": 0}}})
    quotes = stocksaathi.live_quotes(["RELIANCE", "NOSUCHTHING", "DELISTED"])
    assert set(quotes) == {"RELIANCE"}


def test_nothing_is_fetched_for_a_list_with_no_usable_symbol(monkeypatch):
    """Every holding being a fixed deposit must not cost a round trip."""
    def fail(*args, **kwargs):
        raise AssertionError("should not have called the API")
    monkeypatch.setattr(stocksaathi, "_get", fail)
    assert stocksaathi.live_quotes(["", None, "not a symbol"]) == {}


def test_a_long_list_is_split_into_batches(monkeypatch):
    """Their ceiling is 80 a request. Over it, the response is not an error
    -- it is quietly short, which is worse."""
    batches = []

    def record(path, params, timeout):
        batches.append(params["symbols"].split(","))
        return {"ok": True, "quotes": {}}

    monkeypatch.setattr(stocksaathi, "_get", record)
    stocksaathi.live_quotes([f"SYM{n}" for n in range(175)])
    assert [len(batch) for batch in batches] == [80, 80, 15]


def test_the_same_symbol_twice_is_asked_for_once(monkeypatch):
    asked = []
    monkeypatch.setattr(stocksaathi, "_get", lambda path, params, timeout: (
        asked.append(params["symbols"]) or {"ok": True, "quotes": {}}))
    stocksaathi.live_quotes(["TCS", "tcs", " TCS "])
    assert asked == ["TCS"]


# --- the one that talks to the internet -------------------------------------

def test_the_live_response_still_has_the_shape_this_module_expects():
    """Skipped, never failed, when the API cannot be reached.

    Everything above proves this module handles a response correctly. Only
    this can notice that the response stopped looking like that -- and it
    must not be able to turn somebody else's outage into a red suite.
    """
    quotes = stocksaathi.live_quotes(["RELIANCE"], timeout=10)
    if not quotes:
        pytest.skip("StockSaathi unreachable, or RELIANCE unquotable")

    quote = quotes["RELIANCE"]
    assert isinstance(quote["price"], Decimal) and quote["price"] > 0
    assert isinstance(quote["as_of"], int)
    # A fraction, not a percentage: a stock that moved less than 100% in a
    # day -- which is all of them, most days -- is well inside 1.
    assert quote["change"] is None or abs(quote["change"]) < 1
