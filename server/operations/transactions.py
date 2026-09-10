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


# The only places a caller may sort by, and the only directions. Both are
# looked up here rather than interpolated, because a sort field arrives from
# a query string and ORDER BY cannot take a parameter -- it is the one part
# of this query that has to be built from text, so the text can only ever
# come from this dictionary.
SORT_COLUMNS = {
    "date": "t.txn_date",
    "amount": "t.amount",
    "category": "c.category_name",
    "type": "t.txn_type",
}

SORT_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}

# transaction_id breaks ties so that paging is stable: without it two rows
# on the same date can swap places between page 1 and page 2, and one of
# them is then never seen at all.
TIEBREAK = "t.transaction_id DESC"

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200


def _where(user_id, filters):
    """Build the WHERE clause and its values from a filter dictionary.

    Every fragment below is a constant string; every value goes through %s.
    Nothing a caller submits is ever concatenated into SQL -- filter names
    are checked by being read explicitly rather than looped over, so an
    unexpected key simply has no effect.
    """
    clauses = ["t.user_id = %s"]
    values = [user_id]

    text = (filters.get("q") or "").strip()
    if text:
        # Matched against the description and the category name, because
        # "groceries" is as likely to be a category as a note.
        clauses.append("(t.description ILIKE %s OR c.category_name ILIKE %s)")
        pattern = f"%{text}%"
        values.extend([pattern, pattern])

    if filters.get("date_from"):
        clauses.append("t.txn_date >= %s")
        values.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("t.txn_date <= %s")
        values.append(filters["date_to"])
    if filters.get("txn_type"):
        clauses.append("t.txn_type = %s")
        values.append(filters["txn_type"])
    if filters.get("category_id"):
        clauses.append("t.category_id = %s")
        values.append(filters["category_id"])
    if filters.get("min_amount") is not None:
        clauses.append("t.amount >= %s")
        values.append(filters["min_amount"])
    if filters.get("max_amount") is not None:
        clauses.append("t.amount <= %s")
        values.append(filters["max_amount"])

    return " AND ".join(clauses), values


def search_transactions(user_id, filters=None, page=1, per_page=DEFAULT_PER_PAGE):
    """Search, filter, sort and page the ledger.

    Replaces get_all_transactions, which is now this with no filters.

    Returns (rows, total), where each row is
    (transaction_id, txn_date, category_name, amount, txn_type, description)
    and total is how many rows match before paging -- the client needs it to
    know whether there is another page.

    The count runs as a second statement on the same connection rather than
    a window function, so the row query stays the plain readable JOIN it was
    and neither statement pays for the other's work.
    """
    filters = filters or {}
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        where, values = _where(user_id, filters)

        column = SORT_COLUMNS.get(filters.get("sort"), SORT_COLUMNS["date"])
        direction = SORT_DIRECTIONS.get(filters.get("direction"), "DESC")

        cursor.execute(
            f"SELECT COUNT(*) FROM transactions t "
            f"JOIN categories c ON t.category_id = c.category_id WHERE {where}",
            values)
        total = cursor.fetchone()[0]

        per_page = max(1, min(int(per_page), MAX_PER_PAGE))
        page = max(1, int(page))

        cursor.execute(
            f"SELECT t.transaction_id, t.txn_date, c.category_name, t.amount, "
            f"       t.txn_type, t.description "
            f"FROM transactions t "
            f"JOIN categories c ON t.category_id = c.category_id "
            f"WHERE {where} "
            f"ORDER BY {column} {direction}, {TIEBREAK} "
            f"LIMIT %s OFFSET %s",
            values + [per_page, (page - 1) * per_page])
        return cursor.fetchall(), total
    except Error as e:
        print(f"Error searching transactions: {e}")
        return [], 0
    finally:
        db.close_connection(connection)


def get_all_transactions(user_id):
    """Every transaction, newest first.

    Kept as the no-filter case of search_transactions so the Jinja pages and
    the dashboard have one query between them rather than a second copy that
    can drift. MAX_PER_PAGE is the cap: the old query had none, which was
    only ever safe because no account has yet grown large enough to notice.
    """
    rows, _ = search_transactions(user_id, per_page=MAX_PER_PAGE)
    return rows


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
