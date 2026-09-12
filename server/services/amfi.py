"""Mutual fund NAVs, from AMFI's published data via mfapi.in.

The counterpart to services/stocksaathi.py, and it exists for the same
reason that module does: one place that knows the shape of somebody else's
feed, so its quirks are encoded once rather than rediscovered per caller.

**A fund is identified by an AMFI scheme code, not a ticker.** Five or six
digits, unique across every scheme, and unrelated to any NSE symbol. Nothing
here accepts a name, because two schemes from one house differ only by words
at the end -- "Direct Plan - Growth Option" against "Regular Plan - IDCW
Option" -- and matching a fund by name is how somebody ends up tracking the
wrong one of a pair they cannot tell apart.

**A NAV is daily, not live.** AMFI publishes once each evening, so there is
no intraday price and asking for one more often than daily gets the same
number back. This is the whole difference from an equity: an unchanged NAV
at four in the afternoon is correct, not stale.

**mfapi.in returns NAV as a decimal string in rupees** ("1274.5382"), to
four places, which is more precision than a price column holds. Everything
below hands back Decimal rupees, as the rest of this codebase means by an
amount, quantised where it is stored rather than here.

Free, no key, no account, CORS-open. StockSaathi proxies this same upstream
at /api/mf-history for its own front end; this goes direct, so a fund's
price does not wait on another product's deployment -- the same reasoning
that took the instrument list from NSE rather than from their database.

Nothing here raises on failure, for the reason stocksaathi.py gives: a feed
is somebody else's server, and a holdings screen that cannot reach one
should show the price it already had.
"""

import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

BASE = "https://api.mfapi.in/mf"

# Long enough for the scheme list, which is 5.7MB of JSON and the only call
# here that is ever large. A single fund's history is a few hundred KB.
TIMEOUT_SECONDS = 30

# The nightly job has nobody waiting on it and can afford to be patient;
# a request on a screen cannot. Callers pass their own.
REQUEST_TIMEOUT_SECONDS = 6

USER_AGENT = "SpendInCheck/1.0 (+https://spendincheck.com)"


def normalise(code):
    """The scheme code as the API wants it, or None if it is not one.

    Digits only, one to six of them. Anything else is not a scheme code and
    asking the upstream about it is a round trip to be told so.
    """
    if code is None:
        return None
    text = str(code).strip()
    return text if text.isdigit() and 1 <= len(text) <= 6 else None


def _rupees(value):
    """A NAV string as Decimal rupees, or None if it is not a number."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    # NaN and Infinity parse as Decimal perfectly happily and then detonate
    # at the first comparison. The same guard validators.py carries.
    return amount if amount.is_finite() else None


def _get(path, timeout):
    """A GET against mfapi, decoded, or None if anything at all went wrong."""
    request = urllib.request.Request(BASE + path,
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, OSError) as e:
        print(f"mfapi {path} failed: {e}")
        return None


def every_scheme(timeout=TIMEOUT_SECONDS):
    """Every scheme AMFI lists, as (code, name, isin) tuples.

    Roughly 37,000 of them, in one 5.7MB response. Used by the seeding
    script and by nothing on a request path -- this is a once-a-day answer
    at most, and it is the whole universe rather than a search.
    """
    body = _get("", timeout)
    if not isinstance(body, list):
        return []

    schemes = []
    for row in body:
        code = normalise(row.get("schemeCode"))
        name = (row.get("schemeName") or "").strip()
        if not code or not name:
            continue
        schemes.append((code, name, (row.get("isinGrowth") or "").strip() or None))
    return schemes


def scheme(code, timeout=REQUEST_TIMEOUT_SECONDS):
    """What one scheme is and what it is worth now.

    Returns a dict shaped like services.stocksaathi.instrument's, so a
    caller writing an instrument row does not have to know which feed the
    answer came from:

        {"symbol", "name", "sector", "exchange", "fund_house", "nav"}

    `sector` carries the scheme category, because that is what it is: "Equity
    Scheme - Mid Cap Fund" answers the same question for a fund that
    "Refineries" answers for a share. `exchange` is None -- a fund does not
    trade on one, and inventing "AMFI" there would put a word in a column
    that means something else everywhere it is read.
    """
    code = normalise(code)
    if not code:
        return None

    body = _get("/" + code, timeout)
    if not isinstance(body, dict):
        return None

    meta = body.get("meta") or {}
    history = body.get("data") or []
    if not meta.get("scheme_name"):
        return None

    return {
        "symbol": code,
        "name": meta.get("scheme_name"),
        "sector": meta.get("scheme_category"),
        "exchange": None,
        "fund_house": meta.get("fund_house"),
        "isin": meta.get("isin_growth"),
        # The most recent published NAV. First in the list: mfapi returns
        # newest first, which is the opposite of closing_prices below.
        "nav": _rupees(history[0].get("nav")) if history else None,
    }


def latest_navs(codes, timeout=REQUEST_TIMEOUT_SECONDS):
    """{code: Decimal} for each scheme that answered.

    One request per fund, because mfapi has no batch endpoint. That is the
    reason this is not called from a screen: the nightly job pays it once
    for every tracked fund, and everything else reads what it wrote.
    """
    found = {}
    for code in {normalise(c) for c in (codes or []) if normalise(c)}:
        answer = scheme(code, timeout=timeout)
        if answer and answer.get("nav") is not None:
            found[code] = answer["nav"]
    return found


def closing_prices(code, days=30, timeout=TIMEOUT_SECONDS):
    """[(date, Decimal)] for the last `days` of NAVs, oldest first.

    Oldest first, and as dates rather than timestamps, so this drops into
    operations.record_closes exactly as the equity feed's version does.
    """
    from datetime import datetime, timedelta

    code = normalise(code)
    if not code:
        return []

    body = _get("/" + code, timeout)
    if not isinstance(body, dict):
        return []

    cutoff = datetime.now().date() - timedelta(days=days)
    closes = []
    for row in (body.get("data") or []):
        nav = _rupees(row.get("nav"))
        if nav is None:
            continue
        try:
            # mfapi dates are DD-MM-YYYY, which strptime will otherwise
            # read as the American order and silently mis-date every row
            # before the thirteenth of a month.
            on = datetime.strptime(row.get("date", ""), "%d-%m-%Y").date()
        except ValueError:
            continue
        if on >= cutoff:
            closes.append((on, nav))

    closes.reverse()
    return closes
