"""
All business logic and SQL for FinTrack lives in this module.

Every function here opens its own connection, runs one or more
parameterized queries, and returns plain Python data (tuples, lists
of tuples, dictionaries). Nothing in this file prints anything to
the screen -- that is main.py's job. Keeping the split this way means
a Flask frontend (or any other frontend) can reuse every function
here without touching a single line of SQL.
"""

from mysql.connector import Error

import db


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

def add_category(category_name, category_type):
    """Insert a new category. category_type must be 'Income' or 'Expense'.

    Returns True on success, False if the insert failed (e.g. duplicate name).
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = "INSERT INTO categories (category_name, category_type) VALUES (%s, %s)"
        cursor.execute(query, (category_name, category_type))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding category: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_categories():
    """Return every category as a list of (category_id, category_name, category_type) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT category_id, category_name, category_type FROM categories ORDER BY category_name")
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching categories: {e}")
        return []
    finally:
        db.close_connection(connection)


def category_exists(category_id):
    """Return True if a category with this category_id exists, else False."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT category_id FROM categories WHERE category_id = %s", (category_id,))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking category: {e}")
        return False
    finally:
        db.close_connection(connection)
