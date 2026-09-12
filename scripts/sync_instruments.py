"""
Seed the instrument master from NSE's own published equity list.

    python scripts/sync_instruments.py           fetch and upsert
    python scripts/sync_instruments.py --dry     fetch, report, write nothing
    python scripts/sync_instruments.py --file X  parse a local CSV instead

Why this exists
---------------
`instruments` (migration 013) is written by the nightly pricing job, which
only ever visits symbols somebody here already holds. For a search box that
is exactly backwards: the table is empty at the moment somebody needs to be
told that RELIANCE exists, and holds only the symbols they could already
name.

The obvious source was StockSaathi's `dhan_instruments`, which is the same
list. It is behind row level security with no anon policy -- correct of
them, since an anon-readable instrument master is a scrape waiting to
happen -- so reading it would mean a new endpoint in their repository and a
second production deploy of a different product.

NSE publishes the list itself. Taking it from the exchange means this app
owns its own universe, waits on nobody, and has one less cross-product
dependency at runtime.

What it writes
--------------
A seeded row is a ticker, a company name, an exchange and an ISIN, and
nothing else. Sector and the 52-week range stay null until the nightly job
fetches the real ones. Every column is COALESCEd on conflict, exactly as
record_instrument does, so running this can never blank a figure the price
feed has already answered -- the seed is the floor, not the truth.
"""

import argparse
import csv
import io
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg2.extras import execute_values  # noqa: E402

from server import db  # noqa: E402
from server.services import amfi  # noqa: E402

NSE_EQUITY_LIST = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

# NSE answers a bare urllib request with a block page rather than the file.
# A browser user agent is what it wants; nothing here is authenticated and
# nothing is being worked around -- the file is published for the public.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
}

TIMEOUT_SECONDS = 30

# "EQ" is ordinary equity, settled rolling. The other series are the ones a
# personal ledger has no business autocompleting: BE is trade-for-trade
# surveillance, and the rest are rights, partly-paid and warrants.
WANTED_SERIES = {"EQ"}


def fetch(url=NSE_EQUITY_LIST):
    """The equity list as text, straight from NSE's public archive."""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _listed_on(raw):
    """NSE's "29-NOV-1995" as a date, or None if it is not one.

    Worth having rather than skipping: it is what lets the search rank
    RELIANCE above RELIABLE, which are the same length and would otherwise
    be separated by nothing but the alphabet.
    """
    try:
        return datetime.strptime(raw.strip(), "%d-%b-%Y").date()
    except (ValueError, AttributeError):
        return None


def parse(text):
    """(ticker, name, isin, listed_on) for every ordinary equity in the list.

    The header row carries leading spaces on most columns -- " SERIES", not
    "SERIES" -- so every key is stripped before it is read. Reading them
    positionally instead would break the first time NSE adds a column.
    """
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        row = {(key or "").strip().upper(): (value or "").strip()
               for key, value in raw.items()}
        if row.get("SERIES") not in WANTED_SERIES:
            continue
        ticker = row.get("SYMBOL", "").upper()
        if not ticker:
            continue
        rows.append((ticker, row.get("NAME OF COMPANY") or None,
                     row.get("ISIN NUMBER") or None,
                     _listed_on(row.get("DATE OF LISTING"))))
    return rows


def upsert_funds(schemes):
    """Write every AMFI scheme in, as instruments of kind 'fund'.

    Same COALESCE rule as the equities: a seed is the floor, never the
    truth. It cannot blank a fund house or a category the nightly NAV job
    has already written, and it cannot un-price a fund somebody holds.
    """
    if not schemes:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        with db.transaction(connection):
            execute_values(
                cursor,
                """
                INSERT INTO instruments (ticker, name, isin, kind)
                VALUES %s
                ON CONFLICT (ticker) DO UPDATE
                   SET name = COALESCE(instruments.name, EXCLUDED.name),
                       isin = COALESCE(instruments.isin, EXCLUDED.isin),
                       kind = EXCLUDED.kind
                """,
                [(code, name, isin, "fund") for code, name, isin in schemes],
                page_size=1000,
            )
        return len(schemes)
    finally:
        db.close_connection(connection)


def upsert(rows):
    """Write the list in, without overwriting anything the feed knows.

    Returns how many rows were offered. One statement: 2,500 single-row
    inserts is 2,500 round trips to Mumbai, which is a minute and a half of
    doing nothing.
    """
    if not rows:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        with db.transaction(connection):
            execute_values(
                cursor,
                """
                INSERT INTO instruments (ticker, name, isin, exchange, listed_on, kind)
                VALUES %s
                ON CONFLICT (ticker) DO UPDATE
                   SET name = COALESCE(instruments.name, EXCLUDED.name),
                       isin = COALESCE(instruments.isin, EXCLUDED.isin),
                       exchange = COALESCE(instruments.exchange, EXCLUDED.exchange),
                       -- Not COALESCEd to the existing value: the listing
                       -- date is a fact NSE owns and nothing else here
                       -- writes it, so the newest answer is the right one.
                       listed_on = COALESCE(EXCLUDED.listed_on, instruments.listed_on),
                       kind = EXCLUDED.kind
                """,
                [(ticker, name, isin, "NSE", listed, "equity")
                 for ticker, name, isin, listed in rows],
                page_size=500,
            )
        return len(rows)
    finally:
        db.close_connection(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true",
                        help="fetch and report, write nothing")
    parser.add_argument("--file", help="parse a local CSV instead of fetching")
    parser.add_argument("--equities-only", action="store_true",
                        help="skip the mutual fund schemes")
    parser.add_argument("--funds-only", action="store_true",
                        help="skip the NSE equities")
    args = parser.parse_args()

    rows = []
    if not args.funds_only:
        text = (open(args.file, encoding="utf-8").read() if args.file else fetch())
        rows = parse(text)
        print(f"{len(rows)} ordinary equities in NSE's list")
        if rows:
            print("  first three:", ", ".join(t for t, _, _, _ in rows[:3]))

    schemes = []
    if not args.equities_only:
        schemes = amfi.every_scheme()
        print(f"{len(schemes)} mutual fund schemes in AMFI's list")
        if schemes:
            print("  first three:", ", ".join(c for c, _, _ in schemes[:3]))

    if args.dry:
        print("--dry: nothing written.")
        return

    if rows:
        print(f"{upsert(rows)} equities offered to instruments")
    if schemes:
        print(f"{upsert_funds(schemes)} funds offered to instruments")
    print("(existing names, ISINs and prices left as they were)")


if __name__ == "__main__":
    main()
