"""Prices, from StockSaathi's public API.

The one place this application knows anything about that API, so its two
traps are encoded once here rather than rediscovered per caller:

**Two endpoints, two units.** /api/live-quote returns prices as rupee
floats (1274.0); /api/history returns them as integer paise (132200).
Everything below hands back Decimal rupees, because that is what the rest
of this codebase means by an amount. /api/fundamentals is rupees again.

**change_pct is a fraction, not a percentage.** -0.0039 is a fifth of a
percent down, not four. Multiplying it by 100 at the point of display is
the kind of mistake that shows somebody a -0.39% day as -39%.

**A mutual fund is not a symbol.** /api/mf-history takes an AMFI scheme
code -- five or six digits, unrelated to any NSE ticker -- and answers in
paise like /api/history does. fund() below is the whole of it, and it
returns what a scheme is *and* its recent NAVs from one call, because
their proxy slices by timeframe server-side where the upstream it proxies
does not.

Nothing here raises on failure. A price feed is somebody else's server on
the far side of the internet, and a holdings screen that cannot reach it
should show the price it already had -- not an error page. Callers get an
empty result and decide what that means.

No API key, no account, and every call is a public GET. This is the same
data the browser fetches for itself while a screen is open; Flask uses it
for the paths a browser cannot serve -- the nightly snapshot, and anything
that has to be true server-side.
"""

import datetime
import json
import time
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


def instrument(symbol, timeout=TIMEOUT_SECONDS):
    """What this symbol actually is, or None if it is not one.

    The nearest thing to a lookup their API offers. There is no search
    endpoint -- nothing takes "reli" and suggests RELIANCE -- but given a
    symbol this says whose it is, which is most of what the searching was
    for. Somebody who types a ticker into a box has no way to tell a
    correct guess from a wrong one that happens to exist, and RELIANCE,
    RELIABLE and RELINFRA are all real companies.

    Returns {"symbol", "name", "exchange", "sector", "price", "low_52w",
    "high_52w"} with the money as Decimal rupees.

    Slower than a quote -- a symbol the upstream has not cached takes a few
    seconds -- so this belongs on a deliberate act like saving a symbol,
    never in a list or a keystroke handler.
    """
    clean = normalise(symbol)
    if not clean:
        return None

    # An unknown symbol comes back as an HTTP error rather than a body
    # saying so, which _get already turns into None.
    body = _get("/fundamentals", {"symbol": clean}, timeout)
    if not body:
        return None

    name = body.get("name")
    return {
        "symbol": clean,
        # Without a name this is no more use than the symbol itself, which
        # the caller already had.
        "name": name if isinstance(name, str) and name.strip() else None,
        "exchange": body.get("exchange"),
        "sector": body.get("sector"),
        "price": _rupees(body.get("price")),
        "low_52w": _rupees(body.get("fifty_two_week_low")),
        "high_52w": _rupees(body.get("fifty_two_week_high")),
    }


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


# Their mutual fund proxy takes a timeframe from a fixed vocabulary, the
# way /api/history takes a range. Different spellings for the same idea,
# on the same server; _fund_range_for below picks from this one.
FUND_RANGES = ((30, "1M"), (91, "3M"), (182, "6M"),
               (365, "1Y"), (1095, "3Y"), (1825, "5Y"))


def _fund_range_for(days):
    """The nearest timeframe their proxy accepts that covers this many days."""
    for limit, name in FUND_RANGES:
        if days <= limit:
            return name
    return "ALL"


def fund(code, days=30, timeout=TIMEOUT_SECONDS):
    """One mutual fund scheme: what it is, what it is worth, and its NAVs.

    Returns a dict shaped like instrument()'s, so a caller writing an
    instrument row does not have to know whether it is holding a share or
    a scheme, with two additions:

        {"symbol", "name", "sector", "exchange", "fund_house",
         "nav", "closes"}

    `closes` is [(date, Decimal)] oldest first, which is the shape
    operations.record_closes wants. It comes back from the same call as
    the rest because their proxy answers both questions at once -- and
    that is the reason to prefer it over the upstream it proxies, which
    has no timeframe parameter and so ships every NAV since inception
    whatever you wanted. 132KB against 2KB, for one month of a fund.

    `sector` carries the scheme category, because that is what it is:
    "Equity Scheme - Mid Cap Fund" answers for a scheme what "Refineries"
    answers for a share. `exchange` is None -- a fund does not trade on
    one, and writing "AMFI" there would put a word in a column that means
    something else everywhere else it is read.

    None if the scheme is unknown or the proxy is unreachable. Their
    handler answers 502 for a code the upstream will not serve, so an
    unknown scheme arrives here the same way an outage does; the caller
    that needs to tell them apart asks the upstream itself.
    """
    if code is None:
        return None
    clean = str(code).strip()
    if not (clean.isdigit() and 1 <= len(clean) <= 6):
        return None

    body = _get("/mf-history",
                {"code": clean, "tf": _fund_range_for(days)}, timeout)
    if not body or not body.get("scheme_name"):
        return None

    closes = []
    for candle in body.get("ohlc") or []:
        at, close = candle.get("t"), candle.get("c")
        if at is None or close is None:
            continue
        try:
            # Their timestamps are midnight on the NAV's date, and the date
            # is the entire content of a NAV -- there is no intraday. Read
            # back in UTC, because reading in local time is how a NAV
            # lands on the previous day for anyone west of Greenwich.
            on = datetime.datetime.fromtimestamp(
                int(at) / 1000, datetime.timezone.utc).date()
            closes.append((on, Decimal(int(close)) / 100))
        except (TypeError, ValueError, OSError, OverflowError):
            continue

    latest = body.get("latest_nav_paise")
    return {
        "symbol": clean,
        "name": body.get("scheme_name"),
        "sector": body.get("scheme_category") or None,
        "exchange": None,
        "fund_house": body.get("fund_house") or None,
        # Their proxy does not carry it, and instrument()'s dict has the
        # key, so it is present and empty rather than missing. The seeded
        # instruments table has the ISIN anyway -- it comes from the
        # scheme list, which is the upstream's to give.
        "isin": None,
        # Their own field rather than the last candle, so a timeframe that
        # sliced away everything still reports today's NAV.
        "nav": (Decimal(int(latest)) / 100) if latest is not None else None,
        "closes": closes,
    }


# Suggestions run on a keystroke, so they get their own, much shorter
# budget. Somebody typing does not wait six seconds for a list; a list that
# arrives after the next keystroke is worse than no list at all.
SEARCH_TIMEOUT_SECONDS = 1.5

# How long to stop asking after they could not answer.
#
# Their /api/search is written but not deployed -- it 404s today -- and
# without this every keystroke in the app would spend a round trip finding
# that out again. One failure stands down the whole endpoint for five
# minutes, per process, and the next attempt after that either finds it
# deployed or costs one more round trip.
SEARCH_RETRY_SECONDS = 300

# Below two characters every query matches thousands of rows and none of
# them is a suggestion. Their own endpoint draws the line in the same
# place; drawing it here too means the request is never made at all.
SEARCH_MIN = 2

# {"until": monotonic seconds}. A plain dict rather than a lock: the worst
# a race can do is let one extra request through, and paying for a lock on
# every keystroke to prevent that is the wrong trade.
_search_standdown = {"until": 0.0}


def search(term, limit=8, timeout=SEARCH_TIMEOUT_SECONDS):
    """Instruments matching a fragment, from their master. None if they cannot.

    The distinction between None and [] is the whole interface. [] is their
    answer -- they looked and there is nothing called that. None is no
    answer -- not deployed, unreachable, too slow -- and only None should
    send a caller to a different source. A fallback that triggers on [] as
    well would quietly second-guess a search that worked.

    **Equities only.** Their master is dhan_instruments, which is the NSE
    universe; it has no mutual funds in it, so a caller that offers funds
    has to get those from somewhere else.

    Nothing here raises, and a failure stands the endpoint down for
    SEARCH_RETRY_SECONDS rather than being retried on the next keystroke.
    """
    cleaned = (term or "").strip()
    if len(cleaned) < SEARCH_MIN:
        return []

    if time.monotonic() < _search_standdown["until"]:
        return None

    body = _get("/search", {"q": cleaned}, timeout)
    if body is None or not isinstance(body.get("items"), list):
        _search_standdown["until"] = time.monotonic() + SEARCH_RETRY_SECONDS
        return None

    # Cleared explicitly, so the first success after a deployment ends the
    # stand-down rather than waiting the rest of it out.
    _search_standdown["until"] = 0.0

    found = []
    for row in body["items"][:limit]:
        symbol = normalise(row.get("symbol"))
        if not symbol or not row.get("name"):
            continue
        found.append({"symbol": symbol, "name": row.get("name"),
                      "exchange": row.get("exchange"), "sector": row.get("sector"),
                      "isin": row.get("isin"), "kind": "equity"})
    return found
