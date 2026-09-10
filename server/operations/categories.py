"""Spending and income categories.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

def add_category(user_id, category_name, category_type):
    """Insert a new category. category_type must be 'Income' or 'Expense'.

    Returns True on success, False if the insert failed (e.g. duplicate name).
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = ("INSERT INTO categories (user_id, category_name, category_type) "
                 "VALUES (%s, %s, %s)")
        cursor.execute(query, (user_id, category_name, category_type))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding category: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_categories(user_id):
    """Return every category as a list of (category_id, category_name, category_type) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT category_id, category_name, category_type FROM categories "
                       "WHERE user_id = %s ORDER BY category_name", (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching categories: {e}")
        return []
    finally:
        db.close_connection(connection)


def category_exists(user_id, category_id):
    """Return True if a category with this category_id exists, else False."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT category_id FROM categories "
                       "WHERE category_id = %s AND user_id = %s", (category_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking category: {e}")
        return False
    finally:
        db.close_connection(connection)


def rename_category(user_id, category_id, category_name, category_type):
    """Change a category's name and type.

    Returns True if the category is this user's and was saved, False if it
    is not theirs or the new name collides with one they already have. As in
    update_transaction, a rowcount of 0 can simply mean nothing changed, so
    it is followed by an existence check rather than reported as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE categories SET category_name = %s, category_type = %s "
                       "WHERE category_id = %s AND user_id = %s",
                       (category_name, category_type, category_id, user_id))
        connection.commit()
        if cursor.rowcount > 0:
            return True
        return category_exists(user_id, category_id)
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error renaming category: {e}")
        return False
    finally:
        db.close_connection(connection)


def count_category_use(user_id, category_id):
    """How many transactions and budgets point at this category.

    The delete screen asks first, so it can say what will move rather than
    offering a choice and then refusing it on a foreign key error.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT (SELECT COUNT(*) FROM transactions "
                       "         WHERE user_id = %s AND category_id = %s), "
                       "       (SELECT COUNT(*) FROM budgets "
                       "         WHERE user_id = %s AND category_id = %s)",
                       (user_id, category_id, user_id, category_id))
        transactions, budgets = cursor.fetchone()
        return {"transactions": transactions, "budgets": budgets}
    except Error as e:
        print(f"Error counting category use: {e}")
        return {"transactions": 0, "budgets": 0}
    finally:
        db.close_connection(connection)


def delete_category(user_id, category_id, reassign_to=None):
    """Delete a category, optionally moving what points at it somewhere else.

    Transactions and budgets both reference categories, so a category in use
    cannot simply be dropped -- the foreign key would refuse it. With
    reassign_to given, everything is moved to that category first and the
    whole thing happens in one transaction: either the rows move and the
    category goes, or nothing changes at all.

    Budgets need more than an UPDATE. A category has at most one budget per
    month, so moving August's budget onto a category that already has one
    would break that constraint. The two limits are added together instead,
    which is what merging two categories means for a monthly allowance.

    Returns True on success, False if the category is not this user's.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        if reassign_to is not None:
            cursor.execute(
                "INSERT INTO budgets (user_id, category_id, month_year, budget_limit) "
                "SELECT user_id, %s, month_year, budget_limit FROM budgets "
                " WHERE user_id = %s AND category_id = %s "
                "ON CONFLICT (user_id, category_id, month_year) "
                "DO UPDATE SET budget_limit = budgets.budget_limit + EXCLUDED.budget_limit",
                (reassign_to, user_id, category_id))
            cursor.execute("DELETE FROM budgets WHERE user_id = %s AND category_id = %s",
                           (user_id, category_id))
            cursor.execute("UPDATE transactions SET category_id = %s "
                           "WHERE user_id = %s AND category_id = %s",
                           (reassign_to, user_id, category_id))

        cursor.execute("DELETE FROM categories WHERE category_id = %s AND user_id = %s",
                       (category_id, user_id))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting category: {e}")
        return False
    finally:
        db.close_connection(connection)
