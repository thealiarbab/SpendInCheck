"""Aggregate queries that summarise a month.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

def category_wise_spend(user_id, month_year):
    """Report: total Expense amount per category for the given 'YYYY-MM' month.

    Returns a list of (category_name, total_spent) tuples, highest spend first.
    The GROUP BY collapses every transaction row in a category into one row
    so SUM(amount) can add up all of them together.
    """
    # Split 'YYYY-MM' and match the year and month separately with EXTRACT,
    # avoiding any date-format string containing '%' that would clash with
    # the %s placeholders the driver substitutes.
    year_part, month_part = month_year.split("-")
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT c.category_name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s AND t.txn_type = 'Expense'
              AND EXTRACT(YEAR FROM t.txn_date) = %s
              AND EXTRACT(MONTH FROM t.txn_date) = %s
            GROUP BY c.category_name
            ORDER BY total_spent DESC
        """
        cursor.execute(query, (user_id, year_part, month_part))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating category-wise spend report: {e}")
        return []
    finally:
        db.close_connection(connection)


def budget_vs_actual(user_id, month_year):
    """Report: for each budgeted category in the given month, compare the
    budget limit against the actual amount spent.

    Returns a list of (category_name, budget_limit, actual_spent, difference)
    tuples, where difference = budget_limit - actual_spent (positive means
    under budget, negative means over budget).
    """
    # Same reasoning as category_wise_spend: EXTRACT keeps '%' out of the SQL.
    # The WHERE clause already pins every budget row to the requested month, so
    # matching transactions on that same year/month lines the two tables up.
    year_part, month_part = month_year.split("-")
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                c.category_name,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS actual_spent,
                b.budget_limit - COALESCE(SUM(t.amount), 0) AS difference
            FROM budgets b
            JOIN categories c ON b.category_id = c.category_id
            LEFT JOIN transactions t
                ON t.category_id = b.category_id
                AND t.txn_type = 'Expense'
                AND EXTRACT(YEAR FROM t.txn_date) = %s
                AND EXTRACT(MONTH FROM t.txn_date) = %s
            WHERE b.user_id = %s AND b.month_year = %s
            GROUP BY c.category_name, b.budget_limit
            ORDER BY difference ASC
        """
        cursor.execute(query, (year_part, month_part, user_id, month_year))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating budget-vs-actual report: {e}")
        return []
    finally:
        db.close_connection(connection)
