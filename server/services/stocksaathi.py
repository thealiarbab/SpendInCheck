"""Prices, from StockSaathi's public API.

The one place this application knows anything about that API, so its two
traps are encoded once here rather than rediscovered per caller:

**Two endpoints, two units.** /api/live-quote returns prices as rupee
floats (1274.0); /api/history returns them as integer paise (132200).
Everything below hands back Decimal rupees, because that is what the rest
of this codebase means by an amount.

**change_pct is a fraction, not a percentage.** -0.0039 is a fifth of a
percent down, not four. Multiplying it by 100 at the point of display is
the kind of mistake that shows somebody a -0.39% day as -39%.

Nothing here raises on failure. A price feed is somebody else's server on
the far side of the internet, and a holdings screen that cannot reach it
should show the price it already had -- not an error page. Callers get an
empty result and decide what that means.

No API key, no account, and every call is a public GET. This is the same
data the browser fetches for itself while a screen is open; Flask uses it
for the paths a browser cannot serve -- the nightly snapshot, and anything
that has to be true server-side.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

BASE = "https://stocksaathi.co.in/api"

# Their documented ceiling per request. Asking for more is not an error --
# it is a slower request that may be truncated, which is worse.
MAX_SYMBOLS = 80

# Short on purpose. This runs inside a request somebody is waiting on, and
# a stale price shown instantly beats a fresh one shown in twenty seconds.
# The snapshot cron, which nobody is waiting on, passes its own.
TIMEOUT_SECONDS = 6

# Sent so the far side can tell this traffic apart from a browser's. It is
# the same product family, and an unidentified scraper is what rate limits
# are invented for.
USER_AGENT = "SpendInCheck/1.0 (+https://spendincheck.com)"


def normalise(symbol):
    """The symbol as the API wants it, or None if it is not usable.

    Bare uppercase is NSE (RELIANCE); a .BO suffix is BSE-only. Anything
    else -- spaces, slashes, an empty string -- is not a symbol, and
    sending it costs a round trip to be told nothing.
    """
    if not symbol:
        return None
    cleaned = str(symbol).strip().upper()
    if not cleaned:
        return None
    body, _, suffix = cleaned.partition(".")
    if suffix and suffix != "BO":
        return None
    # & and - are both real: M&M, BAJAJ-AUTO.
    if not body or not body.replace("&", "").replace("-", "").isalnum():
        return None
    return cleaned


def _rupees(value):
    """A price the API sent as a float, as a Decimal that did not go via one.

    Decimal(1274.1) is 1274.09999...; Decimal("1274.1") is 1274.1. The
    string is the whole point.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _get(path, params, timeout):
    """Fetch and parse one JSON response, or return None.

    Every failure a network call has -- refused, timed out, 500, HTML from
    a proxy, valid JSON of the wrong shape -- arrives here as None. The
    caller cannot tell them apart and does not need to: there is no price,
    and the answer to that is the same either way.
    """
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return None
    return body if isinstance(body, dict) and body.get("ok") else None


def _chunks(items, size):
    """Split a list into runs of at most `size`."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def live_quotes(symbols, timeout=TIMEOUT_SECONDS):
    """Current prices for these symbols, as {symbol: quote}.

    A quote is {"price", "prev_close", "change", "as_of", "source"}, with
    the money as Decimal rupees, `change` as the fraction the API sends,
    and `as_of` in milliseconds since the epoch.

    Symbols with no price are left out rather than mapped to None, so
    `symbol in quotes` is the whole test a caller needs. An unreachable
    API is the same as every symbol being unknown: an empty dict.
    """
    wanted = []
    for symbol in symbols:
        clean = normalise(symbol)
        # A list rather than a set: asking in the order the caller asked
        # keeps a batch reproducible, and a symbol listed twice is still
        # only fetched once.
        if clean and clean not in wanted:
            wanted.append(clean)
    if not wanted:
        return {}

    found = {}
    for batch in _chunks(wanted, MAX_SYMBOLS):
        body = _get("/live-quote", {"symbols": ",".join(batch)}, timeout)
        if not body:
            continue
        for symbol, quote in (body.get("quotes") or {}).items():
            # A symbol the upstream does not know comes back as an explicit
            # null rather than being absent.
            if not isinstance(quote, dict):
                continue
            price = _rupees(quote.get("price"))
            if price is None or price <= 0:
                continue
            found[symbol] = {
                "price": price,
                "prev_close": _rupees(quote.get("prev_close")),
                # Left exactly as sent: a fraction. See the module docstring.
                "change": quote.get("change_pct"),
                "as_of": quote.get("ts_ms"),
                "source": quote.get("source"),
            }
    return found


def closing_prices(symbol, days=30, timeout=TIMEOUT_SECONDS):
    """Daily closes for one symbol, oldest first, as [(ts_ms, price)].

    The prices arrive as integer paise and leave as Decimal rupees, which
    is the conversion this module exists to own. Returns an empty list for
    anything that did not work.
    """
    clean = normalise(symbol)
    if not clean:
        return []

    body = _get("/history",
                {"symbol": clean, "range": _range_for(days), "interval": "1d"},
                timeout)
    if not body:
        return []

    closes = []
    for candle in body.get("ohlc") or []:
        at, close = candle.get("t"), candle.get("c")
        if at is None or close is None:
            continue
        try:
            # Paise to rupees by exact arithmetic, not by dividing a float:
            # Decimal(132200) / 100 is 1322.00 and 132200 / 100 is not.
            closes.append((int(at), Decimal(int(close)) / 100))
        except (TypeError, ValueError):
            continue
    return closes


def _range_for(days):
    """The nearest range the API accepts that covers this many days.

    It takes a fixed vocabulary rather than a number, so asking for 45 days
    means asking for three months and using the part that was wanted.
    """
    for limit, name in ((5, "5d"), (30, "1mo"), (90, "3mo"), (180, "6mo"),
                        (365, "1y"), (730, "2y")):
        if days <= limit:
            return name
    return "5y"
