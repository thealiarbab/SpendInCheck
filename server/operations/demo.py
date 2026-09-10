"""The throwaway demonstration account and its seed data.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

from .users import get_user_by_login

# A shared, public account. Anything a visitor does to it is wiped and rebuilt
# the next time somebody signs in or out of it, so it can never be left in a
# broken state and nothing typed into it survives.
DEMO_CATEGORIES = [
    ("Salary", "Income"), ("Freelance", "Income"), ("Groceries", "Expense"),
    ("Rent", "Expense"), ("Transport", "Expense"), ("Entertainment", "Expense"),
    ("Utilities", "Expense"), ("Dining Out", "Expense"),
]

# (date, category name, amount, type, description)
DEMO_TRANSACTIONS = [
    ("2026-06-01", "Salary", 55000.00, "Income", "June salary"),
    ("2026-06-02", "Rent", 15000.00, "Expense", "June rent"),
    ("2026-06-05", "Groceries", 3200.50, "Expense", "Weekly groceries"),
    ("2026-06-10", "Transport", 1200.00, "Expense", "Fuel and cab rides"),
    ("2026-06-15", "Entertainment", 800.00, "Expense", "Movie night"),
    ("2026-06-20", "Utilities", 2100.00, "Expense", "Electricity bill"),
    ("2026-06-25", "Freelance", 8000.00, "Income", "Freelance web project"),
    ("2026-07-01", "Salary", 55000.00, "Income", "July salary"),
    ("2026-07-02", "Rent", 15000.00, "Expense", "July rent"),
    ("2026-07-06", "Groceries", 2900.00, "Expense", "Weekly groceries"),
    ("2026-07-11", "Transport", 1500.00, "Expense", "Metro pass"),
    ("2026-07-14", "Dining Out", 1100.00, "Expense", "Dinner with friends"),
    ("2026-07-18", "Entertainment", 600.00, "Expense", "Streaming subscription"),
    ("2026-07-22", "Utilities", 2300.00, "Expense", "Electricity bill"),
    ("2026-08-01", "Salary", 56000.00, "Income", "August salary"),
    ("2026-08-02", "Rent", 15000.00, "Expense", "August rent"),
    ("2026-08-05", "Groceries", 3400.00, "Expense", "Weekly groceries"),
    ("2026-08-09", "Transport", 1300.00, "Expense", "Fuel"),
    ("2026-08-12", "Entertainment", 950.00, "Expense", "Concert ticket"),
    ("2026-08-19", "Dining Out", 1400.00, "Expense", "Weekend brunch"),
]

# Chosen so the budget report shows all three states at once: Rent lands
# exactly on its limit, Utilities goes over, Groceries stays under.
DEMO_BUDGETS = [
    ("Groceries", "2026-06", 4000.00), ("Rent", "2026-06", 15000.00),
    ("Entertainment", "2026-06", 1000.00), ("Groceries", "2026-07", 4000.00),
    ("Utilities", "2026-07", 2000.00), ("Rent", "2026-07", 15000.00),
    ("Dining Out", "2026-07", 1000.00), ("Groceries", "2026-08", 3500.00),
    ("Entertainment", "2026-08", 1000.00),
]

DEMO_INVESTMENTS = [
    ("Tata Motors", "Stock", "2026-02-10", 650.00, 20.0000, 720.50),
    ("Infosys", "Stock", "2026-03-15", 1450.00, 10.0000, 1390.00),
    ("HDFC Flexi Cap Fund", "Mutual Fund", "2026-01-20", 45.20, 500.0000, 48.75),
    ("SBI Bluechip Fund", "Mutual Fund", "2026-04-05", 62.10, 300.0000, 60.90),
    ("SBI Fixed Deposit", "FD", "2026-01-01", 100000.00, 1.0000, 104500.00),
    ("Reliance Industries", "Stock", "2026-05-12", 2450.00, 8.0000, 2510.75),
]


def reset_demo_data(user_id):
    """Wipe this account's rows and rebuild the demonstration data.

    Everything happens in one transaction, so a visitor can never catch the
    demo account half-emptied. Returns True on success.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # Children first: transactions and budgets both point at categories.
        cursor.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM budgets WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM investments WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM categories WHERE user_id = %s", (user_id,))

        category_ids = {}
        for name, kind in DEMO_CATEGORIES:
            cursor.execute(
                "INSERT INTO categories (user_id, category_name, category_type) "
                "VALUES (%s, %s, %s) RETURNING category_id",
                (user_id, name, kind))
            category_ids[name] = cursor.fetchone()[0]

        for txn_date, name, amount, kind, description in DEMO_TRANSACTIONS:
            cursor.execute(
                "INSERT INTO transactions (user_id, txn_date, category_id, amount, "
                "txn_type, description) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, txn_date, category_ids[name], amount, kind, description))

        for name, month_year, limit in DEMO_BUDGETS:
            cursor.execute(
                "INSERT INTO budgets (user_id, category_id, month_year, budget_limit) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, category_ids[name], month_year, limit))

        for row in DEMO_INVESTMENTS:
            cursor.execute(
                "INSERT INTO investments (user_id, asset_name, asset_type, buy_date, "
                "buy_price, quantity, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id,) + row)

        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error resetting demo data: {e}")
        return False
    finally:
        db.close_connection(connection)


def ensure_demo_user(username, email, password_hash):
    """Return the demo account's user_id, creating the row if it is missing.

    The stored password is rewritten to the supplied hash every time, so the
    credentials are whatever the application declares them to be. That is what
    makes them unresettable: nothing that happens to the row can leave the
    published demo password not working.
    """
    existing = get_user_by_login(username)
    if existing:
        connection = None
        try:
            connection = db.get_connection()
            cursor = connection.cursor()
            cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s",
                           (password_hash, existing[0]))
            connection.commit()
        except Error as e:
            if connection:
                connection.rollback()
            print(f"Error refreshing demo password: {e}")
        finally:
            db.close_connection(connection)
        return existing[0]
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) "
            "RETURNING user_id",
            (username, email, password_hash))
        user_id = cursor.fetchone()[0]
        connection.commit()
        return user_id
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error creating demo user: {e}")
        return None
    finally:
        db.close_connection(connection)
