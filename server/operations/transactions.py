"""The transaction ledger: the core create/read/update/delete.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from decimal import Decimal

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
# The tags on one row, as a column.
#
# Applied to the page rather than inside the search, for two reasons. A
# json value has no equality operator, so it cannot appear in a UNION -- and
# the search is a UNION. And correlated per page means twenty-five lookups
# rather than one per matching row, which on a large account is the whole
# ledger.
#
# COALESCE, so a row with no tags is [] rather than null.
TAGS = ("COALESCE((SELECT json_agg(json_build_object('id', g.tag_id, "
        "                                            'name', g.tag_name) "
        "                          ORDER BY lower(g.tag_name)) "
        "            FROM transaction_tags tt "
        "            JOIN tags g ON g.tag_id = tt.tag_id "
        "           WHERE tt.transaction_id = page.transaction_id), '[]'::json)"
        " AS tags")

# The tag subquery without its alias: inside json_build_array an "AS name"
# is a syntax error, and the value is all that is wanted there.
_TAGS_VALUE = TAGS[:TAGS.rindex(" AS tags")]

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

    Returns (rows, total), where total is how many rows match before paging
    -- the client needs it to know whether there is another page.

    One statement, not two. The count used to run separately so that each
    query stayed simple and neither paid for the other's work, which was the
    right trade when a round trip looked free. It is not: a trip to Mumbai
    is about 29ms and these queries take single figures, so the second
    statement cost more than the work it saved. COUNT(*) OVER () is computed
    before LIMIT, so it counts every match rather than the page.
    """
    filters = filters or {}
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        inner, values = _matching(user_id, filters)

        column = SORT_COLUMNS.get(filters.get("sort"), SORT_COLUMNS["date"])
        direction = SORT_DIRECTIONS.get(filters.get("direction"), "DESC")

        per_page = max(1, min(int(per_page), MAX_PER_PAGE))
        page = max(1, int(page))

        # Innermost: what matches. Then the page, with the total riding
        # along on every row of it. Then the tags, which are looked up only
        # for the rows that survived the LIMIT.
        cursor.execute(
            f"SELECT page.*, {TAGS} FROM ("
            f"    SELECT *, COUNT(*) OVER () AS matching FROM ({inner}) AS matched "
            f"    ORDER BY {column} {direction}, {TIEBREAK} "
            f"    LIMIT %s OFFSET %s"
            f") AS page "
            f"ORDER BY page.{column} {direction}, page.{TIEBREAK}",
            values + [per_page, (page - 1) * per_page])
        rows = cursor.fetchall()

        # Each row is the columns, then the total, then the tags. The count
        # rides on every row; no rows means nothing matched.
        total = rows[0][-2] if rows else 0
        return [row[:-2] + (row[-1],) for row in rows], total
    except Error as e:
        print(f"Error searching transactions: {e}")
        return [], 0
    finally:
        db.close_connection(connection)


def recent_and_holdings(user_id, limit):
    """The two lists the opening screen shows, in one statement.

    They are independent, which is exactly why they can share a statement:
    two SELECTs in one round trip rather than two round trips for queries
    that take single figures to run.

    Composed from the same COLUMNS, FROM_JOIN and TAGS this module already
    defines, so the ledger half stays one definition rather than a second
    copy that can drift.

    Returns (recent_rows, holding_rows) in the shapes search_transactions
    and portfolio_pnl return, so callers cannot tell the difference.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "WITH page AS ("
            f"   SELECT {COLUMNS} {FROM_JOIN} "
            "     WHERE t.user_id = %s "
            f"    ORDER BY t.txn_date DESC, t.{TIEBREAK} "
            "     LIMIT %s), "
            "held AS ("
            "   SELECT investment_id, asset_name, asset_type, buy_date::text, "
            "          buy_price::text, current_price::text, quantity::text, "
            "          ((current_price - buy_price) * quantity)::text AS pnl, "
            "          (current_price * quantity)::text AS current_value "
            "     FROM investments WHERE user_id = %s "
            "    ORDER BY (current_price - buy_price) * quantity DESC) "
            "SELECT "
            f"  (SELECT json_agg(json_build_array(transaction_id, txn_date::text, "
            "        category_name, amount::text, txn_type, description, "
            f"       account_name, transfer_group, {_TAGS_VALUE})) FROM page), "
            "  (SELECT json_agg(json_build_array(investment_id, asset_name, "
            "        asset_type, buy_date, buy_price, current_price, quantity, "
            "        pnl, current_value)) FROM held)",
            (user_id, limit, user_id))
        recent, held = cursor.fetchone()
        return (_revive(recent, {3}), _revive(held, {4, 5, 6, 7, 8}))
    except Error as e:
        print(f"Error fetching the opening screen: {e}")
        return [], []
    finally:
        db.close_connection(connection)


def _revive(carried, money_columns):
    """Turn a JSON array-of-arrays back into the tuples callers expect.

    Money travels as text -- a JSON number is a float, and 1200.50 is not
    one -- so the columns holding it become Decimals again here.
    """
    if not carried:
        return []
    return [tuple(Decimal(value) if index in money_columns and value is not None
                  else value
                  for index, value in enumerate(row))
            for row in carried]


def get_all_transactions(user_id):
    """Every transaction, newest first.

    Kept as the no-filter case of search_transactions so the CSV export and
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
