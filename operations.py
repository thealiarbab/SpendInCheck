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


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------

def add_transaction(txn_date, category_id, amount, txn_type, description):
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
        query = """
            INSERT INTO transactions (txn_date, category_id, amount, txn_type, description)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (txn_date, category_id, amount, txn_type, description))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_transactions():
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
            ORDER BY t.txn_date DESC, t.transaction_id DESC
        """
        cursor.execute(query)
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching transactions: {e}")
        return []
    finally:
        db.close_connection(connection)


def get_transaction_by_id(transaction_id):
    """Return a single transaction row as a tuple, or None if it does not exist."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT transaction_id, txn_date, category_id, amount, txn_type, description
            FROM transactions WHERE transaction_id = %s
        """
        cursor.execute(query, (transaction_id,))
        return cursor.fetchone()
    except Error as e:
        print(f"Error fetching transaction: {e}")
        return None
    finally:
        db.close_connection(connection)


def update_transaction(transaction_id, txn_date, category_id, amount, txn_type, description):
    """Update every field of an existing transaction.

    Returns True if a row was actually changed (rowcount > 0), False otherwise.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            UPDATE transactions
            SET txn_date = %s, category_id = %s, amount = %s, txn_type = %s, description = %s
            WHERE transaction_id = %s
        """
        cursor.execute(query, (txn_date, category_id, amount, txn_type, description, transaction_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


def delete_transaction(transaction_id):
    """Delete a transaction by its id. Returns True if a row was removed."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM transactions WHERE transaction_id = %s", (transaction_id,))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


# ---------------------------------------------------------------------------
# BUDGETS
# ---------------------------------------------------------------------------

def set_budget(category_id, month_year, budget_limit):
    """Create or update the budget limit for a category in a given month.

    Uses INSERT ... ON DUPLICATE KEY UPDATE against the uniq_cat_month
    constraint, so calling this twice for the same category/month simply
    overwrites the limit instead of raising a duplicate-key error.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            INSERT INTO budgets (category_id, month_year, budget_limit)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE budget_limit = VALUES(budget_limit)
        """
        cursor.execute(query, (category_id, month_year, budget_limit))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error setting budget: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_budgets():
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
            ORDER BY b.month_year DESC, c.category_name
        """
        cursor.execute(query)
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching budgets: {e}")
        return []
    finally:
        db.close_connection(connection)


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

def category_wise_spend(month_year):
    """Report: total Expense amount per category for the given 'YYYY-MM' month.

    Returns a list of (category_name, total_spent) tuples, highest spend first.
    The GROUP BY collapses every transaction row in a category into one row
    so SUM(amount) can add up all of them together.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT c.category_name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.txn_type = 'Expense' AND DATE_FORMAT(t.txn_date, '%%Y-%%m') = %s
            GROUP BY c.category_name
            ORDER BY total_spent DESC
        """
        cursor.execute(query, (month_year,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating category-wise spend report: {e}")
        return []
    finally:
        db.close_connection(connection)


def budget_vs_actual(month_year):
    """Report: for each budgeted category in the given month, compare the
    budget limit against the actual amount spent.

    Returns a list of (category_name, budget_limit, actual_spent, difference)
    tuples, where difference = budget_limit - actual_spent (positive means
    under budget, negative means over budget).
    """
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
                AND DATE_FORMAT(t.txn_date, '%%Y-%%m') = b.month_year
            WHERE b.month_year = %s
            GROUP BY c.category_name, b.budget_limit
            ORDER BY difference ASC
        """
        cursor.execute(query, (month_year,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating budget-vs-actual report: {e}")
        return []
    finally:
        db.close_connection(connection)


# ---------------------------------------------------------------------------
# INVESTMENTS
# ---------------------------------------------------------------------------

def add_investment(asset_name, asset_type, buy_date, buy_price, quantity, current_price):
    """Insert a new investment. Returns True on success, False on failure."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            INSERT INTO investments (asset_name, asset_type, buy_date, buy_price, quantity, current_price)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (asset_name, asset_type, buy_date, buy_price, quantity, current_price))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding investment: {e}")
        return False
    finally:
        db.close_connection(connection)
