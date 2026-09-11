"""What things used to be worth.

quote_history is the one table here that is not user-scoped. A closing
price is a fact about the market, not about a person: twenty accounts
holding RELIANCE share one set of closes, and a copy each would be twenty
rows saying the same thing and twenty chances to disagree. Every function
below is therefore missing the user_id filter that every other operation
has, deliberately.

Nothing here is reachable without an account -- the endpoints that call it
still require one -- but what comes back is public information either way.
"""

from psycopg2 import Error

from .. import db


def record_closes(ticker, closes):
    """Write daily closes for one symbol. Returns how many rows landed.

    `closes` is [(date, Decimal)]. Existing rows are left alone rather than
    overwritten: a close is final once the day is over, and a feed that
    revises one later is likelier to be having a bad day than to be right.
    The exception would be today's row, which is not a close until the
    market shuts -- see the DO UPDATE below.
    """
    rows = [(ticker, on_date, close) for on_date, close in (closes or [])
            if on_date is not None and close is not None]
    if not ticker or not rows:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # unnest of three arrays rather than a row per statement: a year of
        # history is 250 rows, and 250 round trips to Mumbai is seven
        # seconds to write something nobody is waiting for.
        cursor.execute("""
            INSERT INTO quote_history (ticker, on_date, close)
            SELECT * FROM unnest(%s::varchar[], %s::date[], %s::numeric[])
            ON CONFLICT (ticker, on_date) DO UPDATE
                -- Only today's row is allowed to move. Yesterday's close
                -- is settled, and a feed revising it is more likely to be
                -- wrong than the record is.
                SET close = EXCLUDED.close
                WHERE quote_history.on_date >= CURRENT_DATE
        """, ([ticker] * len(rows),
              [on_date for _, on_date, _ in rows],
              [close for _, _, close in rows]))
        connection.commit()
        return cursor.rowcount
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error recording closes for {ticker}: {e}")
        return 0
    finally:
        db.close_connection(connection)


def symbols_with_history():
    """Every symbol that already has at least one close recorded.

    The snapshot job asks this to decide what it is doing per symbol: a
    symbol it has never seen needs a year fetched, one it knows needs only
    the last few days. Without the distinction, either every run pulls a
    year for everything or a newly tracked holding charts as a flat line
    until a year has passed.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT ticker FROM quote_history")
        return {row[0] for row in cursor.fetchall()}
    except Error as e:
        print(f"Error listing symbols with history: {e}")
        return set()
    finally:
        db.close_connection(connection)


def close_on(ticker, on_date):
    """The last close at or before this date, or None.

    Used by tests and by hand. The reports do this as a lateral join rather
    than by calling here per holding per month, which would be a round trip
    each.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT close FROM quote_history
             WHERE ticker = %s AND on_date <= %s
             ORDER BY on_date DESC LIMIT 1
        """, (ticker, on_date))
        row = cursor.fetchone()
        return row[0] if row else None
    except Error as e:
        print(f"Error reading close for {ticker}: {e}")
        return None
    finally:
        db.close_connection(connection)


def recent_closes(tickers, days=30):
    """Recent closes for several symbols at once, as {ticker: [(date, close)]}.

    One statement for the whole screen rather than one per holding: six
    holdings would otherwise be six round trips to Mumbai for a chart the
    width of a thumbnail.

    Oldest first per symbol, so a caller can draw it without sorting.
    """
    wanted = sorted({t for t in (tickers or []) if t})
    if not wanted:
        return {}

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ticker, on_date, close
              FROM quote_history
             WHERE ticker = ANY(%s::varchar[])
               AND on_date > CURRENT_DATE - make_interval(days => %s)
             ORDER BY ticker, on_date
        """, (wanted, days))
        series = {}
        for ticker, on_date, close in cursor.fetchall():
            series.setdefault(ticker, []).append((on_date, close))
        return series
    except Error as e:
        print(f"Error reading recent closes: {e}")
        return {}
    finally:
        db.close_connection(connection)


def record_instrument(found):
    """Write down what a symbol is. Returns True when a row landed.

    `found` is what services.stocksaathi.instrument returns. Overwrites on
    conflict, unlike a close: a company's sector can be reclassified and
    its 52-week range moves every day, so the newest answer is the right
    one. That is the opposite rule from quote_history, and the difference
    is that one records what happened on a day and this records what is
    true now.
    """
    if not found or not found.get("symbol"):
        return False

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO instruments (ticker, name, sector, exchange,
                                     low_52w, high_52w)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE
               SET name = COALESCE(EXCLUDED.name, instruments.name),
                   sector = COALESCE(EXCLUDED.sector, instruments.sector),
                   exchange = COALESCE(EXCLUDED.exchange, instruments.exchange),
                   -- COALESCE throughout so a partial answer tops up what
                   -- is known rather than blanking it. A feed that has
                   -- momentarily lost the sector should not erase it.
                   low_52w = COALESCE(EXCLUDED.low_52w, instruments.low_52w),
                   high_52w = COALESCE(EXCLUDED.high_52w, instruments.high_52w),
                   updated_at = now()
        """, (found["symbol"], found.get("name"), found.get("sector"),
              found.get("exchange"), found.get("low_52w"),
              found.get("high_52w")))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error recording instrument {found.get('symbol')}: {e}")
        return False
    finally:
        db.close_connection(connection)


def instruments_for(tickers):
    """What these symbols are, as {ticker: row}. One statement, not one each."""
    wanted = sorted({t for t in (tickers or []) if t})
    if not wanted:
        return {}

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ticker, name, sector, exchange, low_52w, high_52w
              FROM instruments
             WHERE ticker = ANY(%s::varchar[])
        """, (wanted,))
        return {row[0]: {"name": row[1], "sector": row[2], "exchange": row[3],
                         "low_52w": row[4], "high_52w": row[5]}
                for row in cursor.fetchall()}
    except Error as e:
        print(f"Error reading instruments: {e}")
        return {}
    finally:
        db.close_connection(connection)
