"""Per-category monthly spending limits.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import IntegrityError
from .. import db

def set_budget(user_id, category_id, month_year, budget_limit, rollover=False):
    """Create or update the budget limit for a category in a given month.

    Uses INSERT ... ON CONFLICT ... DO UPDATE against uniq_user_cat_month,
    so calling this twice for the same category and month overwrites the
    limit instead of raising a duplicate-key error.

    The conflict target must name that constraint's columns exactly. Naming
    a set Postgres has no unique index for is not a no-op -- the statement
    fails outright, which is how this silently stopped saving budgets when
    the constraint gained user_id.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # The SELECT ... WHERE EXISTS means the row is only written when the
        # category belongs to this user, so a guessed category_id from another
        # account inserts nothing rather than silently attaching to it.
        query = """
            INSERT INTO budgets (user_id, category_id, month_year, budget_limit,
                                 rollover)
            SELECT %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
            )
            ON CONFLICT (user_id, category_id, month_year)
            DO UPDATE SET budget_limit = EXCLUDED.budget_limit,
                          rollover = EXCLUDED.rollover
        """
        cursor.execute(query, (user_id, category_id, month_year, budget_limit,
                               rollover, category_id, user_id))
        connection.commit()
        written = cursor.rowcount > 0
    except IntegrityError as e:
        if connection:
            connection.rollback()
        print(f"Error setting budget: {e}")
        return False
    finally:
        db.close_connection(connection)

    # After the commit, not inside it. The carried-in figures are derived
    # from what was just written, so recomputing first would rebuild them
    # from the old numbers.
    if written:
        refresh_rollover(user_id, category_id)
    return written


def get_all_budgets(user_id):
    """Return every budget joined with its category name, as
    (budget_id, category_name, month_year, budget_limit) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT b.budget_id, c.category_name, b.month_year, b.budget_limit,
                   b.rollover, b.rollover_in, b.category_id
            FROM budgets b
            JOIN categories c ON b.category_id = c.category_id
            WHERE b.user_id = %s
            ORDER BY b.month_year DESC, c.category_name
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


# What a category actually spent in each month it has a budget for.
#
# Transfers are excluded for the same reason every report excludes them:
# money moved between your own accounts was not spent. The join is on the
# month string rather than on dates, because that is the shape budgets are
# keyed by and it keeps the comparison exact.
_SPEND_BY_MONTH = """
    SELECT to_char(t.txn_date, 'YYYY-MM') AS month_year, SUM(t.amount) AS total
      FROM transactions t
     WHERE t.user_id = %s AND t.category_id = %s
       AND t.txn_type = 'Expense' AND t.transfer_group_id IS NULL
     GROUP BY to_char(t.txn_date, 'YYYY-MM')
"""


def refresh_rollover(user_id, category_id):
    """Recompute the carried-in figure for every budget of one category.

    Rollover is recursive: June's carry-in depends on May's, which depends
    on April's. Deriving it at read time would mean walking that chain on
    every report, forever. So it is materialised, and this is what keeps it
    honest -- it rebuilds the whole of one category's history from the
    budgets and transactions it is derived from.

    One recursive statement rather than a loop in Python. The chain is
    inherently sequential, so the work is the same either way; doing it in
    the database makes it one round trip instead of one per month.

    A month whose budget has rollover switched off carries nothing in, and
    passes nothing on -- turning it off is a line under the past, not a
    pause.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            WITH RECURSIVE spend AS (""" + _SPEND_BY_MONTH + """),
            months AS (
                SELECT b.budget_id, b.month_year, b.budget_limit, b.rollover,
                       COALESCE(s.total, 0) AS spent,
                       ROW_NUMBER() OVER (ORDER BY b.month_year) AS n
                  FROM budgets b
                  LEFT JOIN spend s ON s.month_year = b.month_year
                 WHERE b.user_id = %s AND b.category_id = %s
            ),
            walk AS (
                -- The first month a category was ever budgeted for has
                -- nothing behind it, so it carries in nothing.
                SELECT budget_id, budget_limit, rollover, spent, n,
                       0::numeric AS carry_in
                  FROM months WHERE n = 1
                UNION ALL
                SELECT m.budget_id, m.budget_limit, m.rollover, m.spent, m.n,
                       CASE WHEN m.rollover
                            THEN w.carry_in + w.budget_limit - w.spent
                            ELSE 0 END
                  FROM walk w JOIN months m ON m.n = w.n + 1
            )
            UPDATE budgets SET rollover_in = walk.carry_in
              FROM walk
             WHERE budgets.budget_id = walk.budget_id
               AND budgets.rollover_in IS DISTINCT FROM walk.carry_in
        """, (user_id, category_id, user_id, category_id))
        connection.commit()
        return cursor.rowcount
    finally:
        db.close_connection(connection)


def categories_with_rollover(user_id):
    """Which categories have any budget with rollover switched on.

    The transaction write paths call this before recomputing: most accounts
    use rollover on nothing, and this turns "recompute on every write" into
    a single cheap question that is usually answered no.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT category_id FROM budgets "
                       " WHERE user_id = %s AND rollover", (user_id,))
        return {row[0] for row in cursor.fetchall()}
    finally:
        db.close_connection(connection)


def refresh_rollover_for(user_id, *category_ids):
    """Recompute carry-in for whichever of these categories use rollover.

    rollover_in is a stored derived value, so every write that changes what
    it was derived from has to follow it. That rule was written down in the
    transactions route and then observed in three places out of five: the
    recurring sweep and category reassignment both move spending between
    months and categories and neither recomputed anything, so a budget's
    carried-in figure silently described a ledger that no longer existed.

    It lives here now, beside the column it maintains, so the next writer
    has one obvious thing to call rather than a loop to copy.

    Most accounts use rollover on nothing, so the set is asked for once and
    is usually empty -- which is what keeps this cheap enough to call after
    every write.
    """
    wanted = {one for one in category_ids if one}
    if not wanted:
        return
    for category_id in wanted & categories_with_rollover(user_id):
        refresh_rollover(user_id, category_id)
