"""Per-category monthly spending limits.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
import db

def set_budget(user_id, category_id, month_year, budget_limit):
    """Create or update the budget limit for a category in a given month.

    Uses INSERT ... ON CONFLICT ... DO UPDATE against the uniq_cat_month
    constraint, so calling this twice for the same category/month simply
    overwrites the limit instead of raising a duplicate-key error.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # The SELECT ... WHERE EXISTS means the row is only written when the
        # category belongs to this user, so a guessed category_id from another
        # account inserts nothing rather than silently attaching to it.
        query = """
            INSERT INTO budgets (user_id, category_id, month_year, budget_limit)
            SELECT %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
            )
            ON CONFLICT (category_id, month_year)
            DO UPDATE SET budget_limit = EXCLUDED.budget_limit
        """
        cursor.execute(query, (user_id, category_id, month_year, budget_limit,
                               category_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error setting budget: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_budgets(user_id):
    """Return every budget joined with its category name, as
    (budget_id, category_name, month_year, budget_limit) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT b.budget_id, c.category_name, b.month_year, b.budget_limit
            FROM budgets b
            JOIN categories c ON b.category_id = c.category_id
            WHERE b.user_id = %s
            ORDER BY b.month_year DESC, c.category_name
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching budgets: {e}")
        return []
    finally:
        db.close_connection(connection)
