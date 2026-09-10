"""Spending and income categories.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
import db

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
