"""The transaction ledger: the core create/read/update/delete.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db
from .accounts import default_account_id

def add_transaction(user_id, txn_date, category_id, amount, txn_type, description,
                    account_id=None):
    """Insert a new transaction row.

    Caller (main.py) is expected to have already validated amount > 0,
    that category_id exists, and that txn_date is not in the future --
    this function focuses only on the SQL insert and error handling.
    Returns the new transaction_id, or None on failure. An id rather than a
    bare success, because tagging a row needs one and asking for it back in
    a second query would be a second round trip for something the insert
    already knows. Callers that only care whether it worked still read it as
    a truth value.

    account_id may be omitted, in which case the row lands on the user's
    first live account. Every caller that predates accounts relies on that,
    and so does the quick-add form, where making somebody choose an account
    before they can note down a coffee is a worse ledger than one that
    assumes the obvious answer.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        if account_id is None:
            account_id = default_account_id(user_id)
        # Same ownership guard as set_budget, now covering both foreign
        # keys: the insert only happens if the category and the account are
        # both this user's.
        query = """
            INSERT INTO transactions (user_id, txn_date, category_id, amount,
                                      txn_type, description, account_id)
            SELECT %s, %s, %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
            ) AND (%s IS NULL OR EXISTS (
                SELECT 1 FROM accounts WHERE account_id = %s AND user_id = %s
            ))
            RETURNING transaction_id
        """
        cursor.execute(query, (user_id, txn_date, category_id, amount, txn_type,
                               description, account_id, category_id, user_id,
                               account_id, account_id, user_id))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding transaction: {e}")
        return None
    finally:
        db.close_connection(connection)


# The columns the result carries, named once so the sort can refer to them
# by output name rather than by which table they came from -- the search
# below is a UNION, and inside one a column has no table any more.
COLUMNS = ("t.transaction_id, t.txn_date, c.category_name AS category_name, "
           "t.amount, t.txn_type, t.description, "
           "a.account_name AS account_name, "
           # ::text because psycopg2 hands a uuid column back as a UUID
           # object, which json cannot serialise and which nothing on the
           # client wants as anything but an opaque string anyway.
           "t.transfer_group_id::text AS transfer_group")

# LEFT JOIN on accounts, not an inner one. account_id is still nullable at
# the database level until every write path supplies it, and a row that has
# not been given an account must not vanish from the ledger because of it.
FROM_JOIN = ("FROM transactions t "
             "JOIN categories c ON t.category_id = c.category_id "
             "LEFT JOIN accounts a ON a.account_id = t.account_id")

# The only places a caller may sort by, and the only directions. Both are
# looked up here rather than interpolated, because a sort field arrives from
# a query string and ORDER BY cannot take a parameter -- it is the one part
# of this query that has to be built from text, so the text can only ever
# come from this dictionary.
SORT_COLUMNS = {
    "date": "txn_date",
    "amount": "amount",
    "category": "category_name",
    "type": "txn_type",
    "account": "account_name",
}

SORT_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}

# transaction_id breaks ties so that paging is stable: without it two rows
# on the same date can swap places between page 1 and page 2, and one of
# them is then never seen at all.
TIEBREAK = "transaction_id DESC"

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200


def _where(user_id, filters):
    """Build the shared WHERE clause and its values from a filter dictionary.

    Every fragment below is a constant string; every value goes through %s.
    Nothing a caller submits is ever concatenated into SQL -- filter names
    are checked by being read explicitly rather than looped over, so an
    unexpected key simply has no effect.

    The text search is not here: it needs two branches of its own, for the
    reason explained in _matching().
    """
    clauses = ["t.user_id = %s"]
    values = [user_id]

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
    if filters.get("account_id"):
        clauses.append("t.account_id = %s")
        values.append(filters["account_id"])
    if filters.get("tag_id"):
        # EXISTS rather than a join: a join to transaction_tags would
        # multiply a row by the number of its tags, and the page would then
        # show the same transaction three times for having three tags.
        clauses.append("EXISTS (SELECT 1 FROM transaction_tags tt "
                       "         WHERE tt.transaction_id = t.transaction_id "
                       "           AND tt.tag_id = %s)")
        values.append(filters["tag_id"])
    if filters.get("min_amount") is not None:
        clauses.append("t.amount >= %s")
        values.append(filters["min_amount"])
    if filters.get("max_amount") is not None:
        clauses.append("t.amount <= %s")
        values.append(filters["max_amount"])

    return " AND ".join(clauses), values


def _matching(user_id, filters):
    """The set of rows a search matches, as SQL and its values.

    A search looks in both the description and the category name, because
    "groceries" is as likely to be a category as a note. Written as one
    predicate -- `description ILIKE %s OR category_name ILIKE %s` -- that
    reads well and cannot be indexed: the OR spans two tables, so Postgres
    has to join first and test every one of the account's rows afterwards.

    Written as a UNION of two branches, each branch is a plain condition on
    one table, so the trigram index on description can serve the first and
    the ordinary index can serve the second. Measured on one account with
    20,000 rows: 54ms as a single OR, 4ms as a UNION. UNION rather than
    UNION ALL, so a row matching both branches appears once.

    With no search text there is one branch and no union at all.
    """
    where, values = _where(user_id, filters)
    base = f"SELECT {COLUMNS} {FROM_JOIN} WHERE {where}"

    text = (filters.get("q") or "").strip()
    if not text:
        return base, values

    pattern = f"%{text}%"
    return (f"{base} AND t.description ILIKE %s"
            f" UNION "
            f"{base} AND c.category_name ILIKE %s"), values + [pattern] + values + [pattern]


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

        inner, values = _matching(user_id, filters)

        column = SORT_COLUMNS.get(filters.get("sort"), SORT_COLUMNS["date"])
        direction = SORT_DIRECTIONS.get(filters.get("direction"), "DESC")

        cursor.execute(f"SELECT COUNT(*) FROM ({inner}) AS matched", values)
        total = cursor.fetchone()[0]

        per_page = max(1, min(int(per_page), MAX_PER_PAGE))
        page = max(1, int(page))

        cursor.execute(
            f"SELECT * FROM ({inner}) AS matched "
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
            SELECT transaction_id, txn_date, category_id, amount, txn_type,
                   description, account_id, transfer_group_id::text
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
                       txn_type, description, account_id=None):
    """Update every field of an existing transaction.

    Returns True if the transaction exists and was saved, False if no
    transaction has that id.

    A rowcount of 0 is followed by an existence check so that "nothing
    needed changing" is not reported as a failure.

    account_id of None leaves the row where it is rather than clearing it,
    so a caller that knows nothing about accounts cannot move a row out of
    one by omission.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            UPDATE transactions
            SET txn_date = %s, category_id = %s, amount = %s, txn_type = %s,
                description = %s, account_id = COALESCE(%s, account_id)
            WHERE transaction_id = %s AND user_id = %s
              AND EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
              )
              AND (%s IS NULL OR EXISTS (
                SELECT 1 FROM accounts WHERE account_id = %s AND user_id = %s
              ))
        """
        cursor.execute(query, (txn_date, category_id, amount, txn_type, description,
                               account_id, transaction_id, user_id,
                               category_id, user_id,
                               account_id, account_id, user_id))
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
