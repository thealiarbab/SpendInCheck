"""The transaction ledger: the core create/read/update/delete.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

def add_transaction(user_id, txn_date, category_id, amount, txn_type, description):
    """Insert a new transaction row.

    Caller (main.py) is expected to have already validated amount > 0,
    that category_id exists, and that txn_date is not in the future --
    this function focuses only on the SQL insert and error handling.
    Returns True on success, False on failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # Same ownership guard as set_budget: the insert only happens if the
        # category is this user's.
        query = """
            INSERT INTO transactions (user_id, txn_date, category_id, amount,
                                      txn_type, description)
            SELECT %s, %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
            )
        """
        cursor.execute(query, (user_id, txn_date, category_id, amount, txn_type,
                               description, category_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_transactions(user_id):
    """Return every transaction joined with its category name.

    Each row is (transaction_id, txn_date, category_name, amount, txn_type, description),
    ordered by most recent date first.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT t.transaction_id, t.txn_date, c.category_name, t.amount, t.txn_type, t.description
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s
            ORDER BY t.txn_date DESC, t.transaction_id DESC
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching transactions: {e}")
        return []
    finally:
        db.close_connection(connection)


def get_transaction_by_id(user_id, transaction_id):
    """Return a single transaction row as a tuple, or None if it does not exist."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT transaction_id, txn_date, category_id, amount, txn_type, description
            FROM transactions WHERE transaction_id = %s AND user_id = %s
        """
        cursor.execute(query, (transaction_id, user_id))
        return cursor.fetchone()
    except Error as e:
        print(f"Error fetching transaction: {e}")
        return None
    finally:
        db.close_connection(connection)


def update_transaction(user_id, transaction_id, txn_date, category_id, amount,
                       txn_type, description):
    """Update every field of an existing transaction.

    Returns True if the transaction exists and was saved, False if no
    transaction has that id.

    A rowcount of 0 is followed by an existence check so that "nothing
    needed changing" is not reported as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            UPDATE transactions
            SET txn_date = %s, category_id = %s, amount = %s, txn_type = %s, description = %s
            WHERE transaction_id = %s AND user_id = %s
              AND EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
              )
        """
        cursor.execute(query, (txn_date, category_id, amount, txn_type, description,
                               transaction_id, user_id, category_id, user_id))
        connection.commit()
        if cursor.rowcount > 0:
            return True
        cursor.execute("SELECT transaction_id FROM transactions "
                       "WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


def delete_transaction(user_id, transaction_id):
    """Delete a transaction by its id. Returns True if a row was removed."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM transactions "
                       "WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting transaction: {e}")
        return False
    finally:
        db.close_connection(connection)
