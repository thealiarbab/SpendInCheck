"""Write down what everything closed at today.

The nightly job. It exists because a close that nobody recorded on the day
is gone: the upstream serves roughly a year of history and no more, so the
first year comes free and every year after that only exists if this runs.

Two modes per symbol, decided by whether this database has ever seen it:

  never seen  -> fetch a year, so a holding tracked today charts against
                 its own past rather than starting as a flat line.
  seen before -> fetch the last few days, which costs almost nothing and
                 quietly repairs a run that was missed or that failed
                 halfway.

Safe to run twice. Writes are upserts keyed on (ticker, on_date), and only
today's row is allowed to move -- yesterday's close is settled. The
platform's scheduler is at-least-once, so this has to be true rather than
hoped for.
"""

from datetime import datetime, timedelta, timezone

from server import operations
from server.services import stocksaathi

# The exchange's day, not the server's. A close stamped 15:30 in Mumbai is
# 10:00 UTC, so both agree today -- but a feed that ever stamps a candle
# after 18:30 UTC would file it under tomorrow, and a chart with a phantom
# Saturday in it is a bug nobody finds for months.
IST = timezone(timedelta(hours=5, minutes=30))

# A year for a symbol never seen. The upstream will not serve much more,
# and it is roughly what the net-worth chart draws.
BACKFILL_DAYS = 365

# Enough to cover a long weekend plus a missed run.
TOPUP_DAYS = 5

# Nobody is waiting on this, so it can afford to be patient where a request
# on a screen cannot.
TIMEOUT_SECONDS = 20


def _as_date(ts_ms):
    """A candle's millisecond timestamp as the trading date it belongs to."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=IST).date()


def take_snapshot():
    """Record closes for every symbol somebody prices automatically.

    Returns {"symbols", "closes", "backfilled", "described"} -- the counts
    the endpoint reports, so a run that silently did nothing is visible as
    a run that did nothing rather than as a 200.

    The benchmark is always among the symbols, whether or not anybody holds
    it: nothing else would ever fetch it, and the comparison chart needs
    its side of the line.
    """
    # The benchmark is always in the list, even when nobody holds it.
    # Nothing else would ever fetch it -- it is not anybody's holding --
    # and a comparison chart with one side missing is not a chart.
    symbols = operations.symbols_to_price()
    if operations.BENCHMARK not in symbols:
        symbols = symbols + [operations.BENCHMARK]

    known = operations.symbols_with_history()
    written = 0
    backfilled = 0
    described = 0

    for symbol in symbols:
        first_time = symbol not in known
        days = BACKFILL_DAYS if first_time else TOPUP_DAYS
        closes = stocksaathi.closing_prices(symbol, days=days,
                                            timeout=TIMEOUT_SECONDS)
        if not closes:
            # One symbol the feed cannot answer for must not abandon the
            # rest. The next run picks it up.
            continue

        landed = operations.record_closes(
            symbol, [(_as_date(at), price) for at, price in closes])
        written += landed
        if first_time and landed:
            backfilled += 1

        # And what the symbol is. The lookup takes up to three seconds cold,
        # which is why no screen may call it per holding -- but nobody is
        # waiting on this job, and the 52-week range it carries moves every
        # day. Writing it here is what lets a screen show the range without
        # asking anybody.
        if operations.record_instrument(
                stocksaathi.instrument(symbol, timeout=TIMEOUT_SECONDS)):
            described += 1

    return {"symbols": len(symbols), "closes": written,
            "backfilled": backfilled, "described": described}


def ensure_history(symbol):
    """Fetch a year for a symbol this database has never seen. Returns rows.

    Called when somebody first points a holding at a symbol, so the chart
    for it has something to draw immediately rather than being a flat line
    until the next nightly run. A year of closes costs about four hundred
    milliseconds -- less than the lookup that has already happened in the
    same request -- so it is not worth deferring.

    Does nothing for a symbol already on record: the nightly job keeps
    those up to date, and re-fetching a year on every save would be four
    hundred milliseconds to write nothing.
    """
    if not symbol or symbol in operations.symbols_with_history():
        return 0

    closes = stocksaathi.closing_prices(symbol, days=BACKFILL_DAYS,
                                        timeout=TIMEOUT_SECONDS)
    if not closes:
        return 0
    return operations.record_closes(
        symbol, [(_as_date(at), price) for at, price in closes])


def describe(symbol, found=None):
    """Write down what a symbol is, now rather than tonight.

    Called when somebody first points a holding at one, so the 52-week
    range and the company name are on the screen immediately instead of
    after the next nightly run. `found` is passed in when the caller has
    already done the lookup, which the pricing route has -- it is how a
    symbol gets accepted at all -- so this normally costs nothing.
    """
    if not symbol:
        return False
    return operations.record_instrument(
        found or stocksaathi.instrument(symbol, timeout=TIMEOUT_SECONDS))
