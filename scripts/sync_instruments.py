"""
Seed the instrument master from StockSaathi's published universe.

    python scripts/sync_instruments.py            fetch and upsert
    python scripts/sync_instruments.py --dry      fetch, report, write nothing
    python scripts/sync_instruments.py --prune    also drop dormant schemes
    python scripts/sync_instruments.py --equities-only
    python scripts/sync_instruments.py --funds-only

Why this exists
---------------
`instruments` (migration 013) is written by the nightly pricing job, which
only ever visits symbols somebody here already holds. For a search box that
is exactly backwards: the table is empty at the moment somebody needs to be
told that RELIANCE exists, and holds only the symbols they could already
name.

Where the list comes from
-------------------------
StockSaathi publishes its own universe as static JSON, built by its own
pipeline and served from its edge:

    https://stocksaathi.co.in/js/data/universeFull.<sha8>.json   4,367 rows
    https://stocksaathi.co.in/js/data/mfFull.<sha8>.json        13,969 rows

Public, CORS-open, no key and no function invocation -- it is how their own
site loads the universe. The filenames are content-hashed and discovered
through an unhashed `<name>.meta.json` sidecar; services/stocksaathi.py
owns that protocol.

**This used to read NSE and AMFI directly**, on the reasoning that their
instrument master was `dhan_instruments`, which sits behind row level
security with no anon policy. The reasoning was sound and the conclusion
was wrong twice over: `dhan_instruments` is empty -- their own sync has
never filled it -- and the list their product actually uses was published
all along. Reading NSE instead left the suggestion box crediting StockSaathi
for a list that had never once been theirs.

It is also better data, which is what makes this more than bookkeeping:

  - 4,367 shares against NSE's 2,292, with ETFs and the BSE and SME boards
    included, and a **sector** on each -- NSE's CSV has no sector column.
  - 13,969 schemes against AMFI's 37,882, filtered to the ones with a
    current NAV that somebody could actually buy. The raw list is mostly
    dormant and closed-ended plans, and a shorter list is a better search.
  - A fund house and a scheme category on every fund.

What it writes
--------------
The published universe now wins for anything that identifies an instrument
-- name, sector, exchange, ISIN, fund house -- because it is the better
source for all five. It never touches what only the price feed can know:
`priced`, the 52-week range and `listed_on` are left exactly as they are.

That inverts the rule this file used to state, "a seed is the floor, not
the truth", which COALESCEd every column to whatever was already stored.
That was right when the seed was a raw exchange dump and the feed was the
richer side. It is backwards now.

`--prune` is the one destructive thing here, which is why it is a flag and
not the default: it removes fund rows StockSaathi does not carry. It cannot
remove anything anybody holds -- that is a condition inside the statement
rather than a check run before it -- because a test in this repository once
deleted real instruments and nobody noticed until the live search stopped
offering Reliance.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg2.extras import execute_values  # noqa: E402

from server import db  # noqa: E402
from server.services import stocksaathi  # noqa: E402


def upsert(rows):
    """Write the shares in. Returns how many were offered.

    One statement: 4,367 single-row inserts is 4,367 round trips to Mumbai,
    which is several minutes of doing nothing.
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
                INSERT INTO instruments (ticker, name, sector, exchange, isin, kind)
                VALUES %s
                ON CONFLICT (ticker) DO UPDATE
                   SET name = COALESCE(EXCLUDED.name, instruments.name),
                       sector = COALESCE(EXCLUDED.sector, instruments.sector),
                       exchange = COALESCE(EXCLUDED.exchange, instruments.exchange),
                       isin = COALESCE(EXCLUDED.isin, instruments.isin),
                       kind = EXCLUDED.kind
                """,
                [(r["ticker"], r["name"], r["sector"], r["exchange"],
                  r["isin"], "equity") for r in rows],
                page_size=500,
            )
        return len(rows)
    finally:
        db.close_connection(connection)


def upsert_funds(rows):
    """Write the schemes in, with the house and category they arrive with."""
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
                INSERT INTO instruments
                       (ticker, name, sector, isin, fund_house, kind)
                VALUES %s
                ON CONFLICT (ticker) DO UPDATE
                   SET name = COALESCE(EXCLUDED.name, instruments.name),
                       sector = COALESCE(EXCLUDED.sector, instruments.sector),
                       isin = COALESCE(EXCLUDED.isin, instruments.isin),
                       fund_house = COALESCE(EXCLUDED.fund_house,
                                             instruments.fund_house),
                       kind = EXCLUDED.kind
                """,
                [(r["ticker"], r["name"], r["sector"], r["isin"],
                  r["fund_house"], "fund") for r in rows],
                page_size=1000,
            )
        return len(rows)
    finally:
        db.close_connection(connection)


def prune_funds(keep):
    """Remove schemes StockSaathi does not carry. Returns how many went.

    The two conditions that make this safe are in the statement rather than
    in a check run beforehand, because a check run beforehand is a race and
    a condition is not. Nothing anybody holds is removed, and nothing that
    is not a fund is touched at all.
    """
    if not keep:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        with db.transaction(connection):
            cursor.execute(
                """
                DELETE FROM instruments
                 WHERE kind = 'fund'
                   AND ticker <> ALL(%s::varchar[])
                   AND ticker NOT IN (SELECT ticker FROM investments
                                       WHERE ticker IS NOT NULL)
                """,
                (list(keep),))
            return cursor.rowcount
    finally:
        db.close_connection(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true",
                        help="fetch and report, write nothing")
    parser.add_argument("--prune", action="store_true",
                        help="remove fund rows StockSaathi does not carry")
    parser.add_argument("--equities-only", action="store_true",
                        help="skip the mutual fund schemes")
    parser.add_argument("--funds-only", action="store_true",
                        help="skip the shares")
    args = parser.parse_args()

    shares = []
    if not args.funds_only:
        shares = stocksaathi.universe()
        print(f"{len(shares)} shares and ETFs in StockSaathi's universe")
        if shares:
            with_sector = sum(1 for r in shares if r["sector"])
            print(f"  {with_sector} of them carry a sector")
            print("  first three:", ", ".join(r["ticker"] for r in shares[:3]))

    funds = []
    if not args.equities_only:
        funds = stocksaathi.fund_universe()
        print(f"{len(funds)} schemes in StockSaathi's fund universe")
        if funds:
            print("  first three:", ", ".join(r["ticker"] for r in funds[:3]))

    if args.dry:
        print("--dry: nothing written.")
        return

    if shares:
        print(f"{upsert(shares)} shares offered to instruments")
    if funds:
        print(f"{upsert_funds(funds)} funds offered to instruments")
    if args.prune and funds:
        gone = prune_funds({r["ticker"] for r in funds})
        print(f"{gone} dormant schemes removed (none of them held by anybody)")
    print("(prices, 52-week ranges and listing dates left as they were)")


if __name__ == "__main__":
    main()
