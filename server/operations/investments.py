"""Holdings and the portfolio profit-and-loss report.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
import db

def add_investment(user_id, asset_name, asset_type, buy_date, buy_price,
                   quantity, current_price):
    """Insert a new investment. Returns True on success, False on failure."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            INSERT INTO investments (user_id, asset_name, asset_type, buy_date,
                                     buy_price, quantity, current_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (user_id, asset_name, asset_type, buy_date, buy_price,
                               quantity, current_price))
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
    buy_date, buy_price, quantity, current_price) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT investment_id, asset_name, asset_type, buy_date, buy_price, quantity, current_price
            FROM investments
            WHERE user_id = %s
            ORDER BY asset_name
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching investments: {e}")
        return []
    finally:
        db.close_connection(connection)


def update_investment_price(user_id, investment_id, new_current_price):
    """Update only the current_price of an investment (e.g. after checking
    today's market price).

    Returns True if the investment exists and was saved, False if no
    investment has that id. As in update_transaction, a rowcount of 0 can
    simply mean the new price equalled the old one, so it is followed by an
    existence check instead of being treated as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = ("UPDATE investments SET current_price = %s "
                 "WHERE investment_id = %s AND user_id = %s")
        cursor.execute(query, (new_current_price, investment_id, user_id))
        connection.commit()
        if cursor.rowcount > 0:
            return True
        cursor.execute("SELECT investment_id FROM investments "
                       "WHERE investment_id = %s AND user_id = %s", (investment_id, user_id))
        return cursor.fetchone() is not None
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
    (asset_name, asset_type, buy_price, current_price, quantity, pnl, current_value)
    tuples ordered by pnl descending (best performers first).
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                asset_name,
                asset_type,
                buy_price,
                current_price,
                quantity,
                (current_price - buy_price) * quantity AS pnl,
                current_price * quantity AS current_value
            FROM investments
            WHERE user_id = %s
            ORDER BY pnl DESC
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating portfolio P&L report: {e}")
        return []
    finally:
        db.close_connection(connection)
