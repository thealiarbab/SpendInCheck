"""Holdings and the portfolio profit-and-loss report.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

def add_investment(user_id, asset_name, asset_type, buy_date, buy_price,
                   quantity, current_price, ticker=None, exchange=None,
                   isin=None, auto_price=False):
    """Insert a new investment. Returns True on success, False on failure.

    The pricing arguments default to a holding nobody prices automatically,
    which is what every holding was before they existed and what a fixed
    deposit stays.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            INSERT INTO investments (user_id, asset_name, asset_type, buy_date,
                                     buy_price, quantity, current_price,
                                     ticker, exchange, isin, auto_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (user_id, asset_name, asset_type, buy_date, buy_price,
                               quantity, current_price, ticker, exchange, isin,
                               auto_price))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding investment: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_investments(user_id):
    """Return every investment as (investment_id, asset_name, asset_type,
    buy_date, buy_price, quantity, current_price, ticker, exchange, isin,
    auto_price, price_source, price_updated_at) tuples.

    The pricing columns are appended rather than interleaved, so a caller
    reading the first seven by position reads exactly what it did before.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT investment_id, asset_name, asset_type, buy_date, buy_price,
                   quantity, current_price,
                   ticker, exchange, isin, auto_price, price_source,
                   price_updated_at
            FROM investments
            WHERE user_id = %s
            ORDER BY asset_name
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def update_investment_price(user_id, investment_id, new_current_price):
    """Update only the current_price of an investment (e.g. after checking
    today's market price).

    Returns True if the investment is this user's and was saved, False if no
    investment of theirs has that id.

    No existence check on a rowcount of 0: see update_transaction. A new
    price equal to the old one still reports 1 on Postgres, which counts
    matched rows rather than changed ones.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = ("UPDATE investments SET current_price = %s "
                 "WHERE investment_id = %s AND user_id = %s")
        cursor.execute(query, (new_current_price, investment_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating investment price: {e}")
        return False
    finally:
        db.close_connection(connection)


def investment_exists(user_id, investment_id):
    """Return True if this user owns an investment with this investment_id.

    Both halves of the WHERE clause matter. Without the user_id the function
    answers about anyone's investment, which would let a caller treat another
    account's row as a legitimate target to act on.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT investment_id FROM investments "
                       "WHERE investment_id = %s AND user_id = %s", (investment_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking investment: {e}")
        return False
    finally:
        db.close_connection(connection)


def portfolio_pnl(user_id):
    """Report: profit/loss for every investment.

    For each row, (current_price - buy_price) * quantity gives the gain or
    loss on that holding. Returns a list of
    (investment_id, asset_name, asset_type, buy_date, buy_price, current_price,
    quantity, pnl, current_value, ticker, exchange, auto_price,
    price_updated_at) tuples ordered by pnl descending.

    The id and the buy date are carried so this answers everything the
    holdings screen shows. Without them the screen had to fetch the
    editable rows separately and pair the two lists up by asset name --
    a second round trip, and wrong the moment an account holds two things
    with the same name.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                investment_id,
                asset_name,
                asset_type,
                buy_date,
                buy_price,
                current_price,
                quantity,
                (current_price - buy_price) * quantity AS pnl,
                current_price * quantity AS current_value,
                ticker,
                exchange,
                auto_price,
                price_updated_at
            FROM investments
            WHERE user_id = %s
            ORDER BY pnl DESC
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def delete_investment(user_id, investment_id):
    """Delete a holding.

    Nothing references investments, so unlike a category this is a plain
    delete. The user_id in the WHERE clause is what stops one account
    deleting another's row by guessing an id.

    Returns True if a row was deleted, False if none matched.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM investments "
                       "WHERE investment_id = %s AND user_id = %s",
                       (investment_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting investment: {e}")
        return False
    finally:
        db.close_connection(connection)


def set_investment_pricing(user_id, investment_id, ticker, exchange, isin,
                           auto_price):
    """Point a holding at a market symbol, or stop pointing it at one.

    Clearing the ticker also clears auto_price, because the two are not
    independent -- the database refuses the combination, and returning a
    constraint violation to somebody who ticked one box is a worse answer
    than doing the obvious thing.

    Turning automatic pricing *off* deliberately leaves current_price where
    it is. The last fetched price is still the best number anybody has, and
    resetting it to whatever was typed in months ago would be a silent
    revaluation of the portfolio.

    Returns True if a row was updated, False if this user has no such
    holding.
    """
    if not ticker:
        ticker, exchange, isin, auto_price = None, None, None, False

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE investments
               SET ticker = %s, exchange = %s, isin = %s, auto_price = %s,
                   -- A holding that is no longer fetched is manual again,
                   -- so the label never claims a price came from a feed
                   -- that is switched off.
                   price_source = CASE WHEN %s THEN price_source ELSE 'manual' END
             WHERE investment_id = %s AND user_id = %s
        """, (ticker, exchange, isin, auto_price, auto_price,
              investment_id, user_id))
        connection.commit()
        # As in update_investment_price: no existence check behind a rowcount
        # of 0. Values already equal to what was asked for still match, and
        # Postgres counts matched rows.
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error setting investment pricing: {e}")
        return False
    finally:
        db.close_connection(connection)


def symbols_to_price(user_id=None):
    """Every symbol somebody holds with automatic pricing on.

    Scoped to one user when given one -- a signed-in visitor refreshing
    their own holdings -- and to everybody when not, which is what the
    nightly snapshot wants. Distinct, because twenty accounts holding
    RELIANCE is one symbol to ask about, not twenty.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT DISTINCT ticker
              FROM investments
             WHERE auto_price AND ticker IS NOT NULL
               AND (%s::int IS NULL OR user_id = %s)
             ORDER BY ticker
        """, (user_id, user_id))
        return [row[0] for row in cursor.fetchall()]
    finally:
        db.close_connection(connection)


def symbols_held(user_id):
    """Every symbol this account holds, whether or not it is priced from one.

    Distinct from symbols_to_price, which asks a narrower question: what
    the refresh is allowed to overwrite. Somebody who recorded a ticker
    without switching on automatic pricing still wants to see what it has
    been doing, so the chart reads from here.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT DISTINCT ticker FROM investments
             WHERE user_id = %s AND ticker IS NOT NULL
             ORDER BY ticker
        """, (user_id,))
        return [row[0] for row in cursor.fetchall()]
    finally:
        db.close_connection(connection)


def apply_prices(prices, user_id=None):
    """Write fetched prices onto every holding that asked for them.

    `prices` is {symbol: Decimal}. Returns the number of holdings updated.

    One statement for the whole batch rather than one per holding: the
    round trip to Mumbai costs more than the update does, and a hundred
    holdings would otherwise be a hundred of them.

    Only rows with auto_price still on are touched, re-checked here rather
    than trusted from whenever the symbol list was read -- somebody can
    switch it off between the fetch and the write, and the whole point of
    the flag is that it is the last word on whether a price is overwritten.
    """
    written = [(symbol, price) for symbol, price in (prices or {}).items()
               if price is not None]
    if not written:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # unnest of two arrays rather than execute_values, which accepts
        # exactly one placeholder and so cannot also carry the user filter.
        # The casts are not decoration: an array arrives untyped and
        # Postgres would otherwise compare varchar to unknown.
        cursor.execute("""
            UPDATE investments AS held
               SET current_price = fetched.price,
                   price_source = 'stocksaathi',
                   price_updated_at = now()
              FROM unnest(%s::varchar[], %s::numeric[])
                   AS fetched (ticker, price)
             WHERE held.auto_price
               AND held.ticker = fetched.ticker
               AND (%s::int IS NULL OR held.user_id = %s)
        """, ([symbol for symbol, _ in written],
              [price for _, price in written],
              user_id, user_id))
        connection.commit()
        return cursor.rowcount
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error applying prices: {e}")
        return 0
    finally:
        db.close_connection(connection)
