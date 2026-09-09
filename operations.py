"""
All business logic and SQL for SpendInCheck (PostgreSQL / Supabase build).

Every function here opens its own connection, runs one or more
parameterized queries, and returns plain Python data (tuples, lists
of tuples, dictionaries). Nothing in this file prints anything to
the screen -- that is main.py's job. Keeping the split this way means
a Flask frontend (or any other frontend) can reuse every function
here without touching a single line of SQL.
"""

from psycopg2 import Error

import db


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

# Categories every new account starts with, so the app is usable immediately
# instead of presenting empty dropdowns on the first visit.
STARTER_CATEGORIES = [
    ("Salary", "Income"),
    ("Freelance", "Income"),
    ("Groceries", "Expense"),
    ("Rent", "Expense"),
    ("Transport", "Expense"),
    ("Entertainment", "Expense"),
    ("Utilities", "Expense"),
    ("Dining Out", "Expense"),
]


def create_user(username, email, password_hash):
    """Register a new account and give it the starter categories.

    Both the user row and its categories are written in one transaction, so a
    failure part way through cannot leave an account with no categories.

    Returns the new user_id, or None if the username or email is already taken.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) "
            "VALUES (%s, %s, %s) RETURNING user_id",
            (username, email, password_hash),
        )
        user_id = cursor.fetchone()[0]
        for name, kind in STARTER_CATEGORIES:
            cursor.execute(
                "INSERT INTO categories (user_id, category_name, category_type) "
                "VALUES (%s, %s, %s)",
                (user_id, name, kind),
            )
        connection.commit()
        return user_id
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error creating user: {e}")
        return None
    finally:
        db.close_connection(connection)


def get_user_by_login(login):
    """Look up an account by either username or email.

    Returns (user_id, username, email, password_hash) or None. The caller
    checks the password; this function only fetches the stored hash.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT user_id, username, email, password_hash FROM users "
            "WHERE username = %s OR email = %s",
            (login, login),
        )
        return cursor.fetchone()
    except Error as e:
        print(f"Error fetching user: {e}")
        return None
    finally:
        db.close_connection(connection)


def username_taken(username, email):
    """Return a message naming whichever field is already registered, else None."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return "That username is already taken."
        cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return "That email address is already registered."
        return None
    except Error as e:
        print(f"Error checking account: {e}")
        return "Could not check that account right now."
    finally:
        db.close_connection(connection)


# ---------------------------------------------------------------------------
# DEMO ACCOUNT
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------

def add_transaction(user_id, txn_date, category_id, amount, txn_type, description):
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
        # Same ownership guard as set_budget: the insert only happens if the
        # category is this user's.
        query = """
            INSERT INTO transactions (user_id, txn_date, category_id, amount,
                                      txn_type, description)
            SELECT %s, %s, %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
            )
        """
        cursor.execute(query, (user_id, txn_date, category_id, amount, txn_type,
                               description, category_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding transaction: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_transactions(user_id):
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
            WHERE t.user_id = %s
            ORDER BY t.txn_date DESC, t.transaction_id DESC
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching transactions: {e}")
        return []
    finally:
        db.close_connection(connection)


def get_transaction_by_id(user_id, transaction_id):
    """Return a single transaction row as a tuple, or None if it does not exist."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT transaction_id, txn_date, category_id, amount, txn_type, description
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
                       txn_type, description):
    """Update every field of an existing transaction.

    Returns True if the transaction exists and was saved, False if no
    transaction has that id.

    A rowcount of 0 is followed by an existence check so that "nothing
    needed changing" is not reported as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            UPDATE transactions
            SET txn_date = %s, category_id = %s, amount = %s, txn_type = %s, description = %s
            WHERE transaction_id = %s AND user_id = %s
              AND EXISTS (
                SELECT 1 FROM categories WHERE category_id = %s AND user_id = %s
              )
        """
        cursor.execute(query, (txn_date, category_id, amount, txn_type, description,
                               transaction_id, user_id, category_id, user_id))
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


# ---------------------------------------------------------------------------
# BUDGETS
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# INVESTMENTS
# ---------------------------------------------------------------------------

def add_investment(user_id, asset_name, asset_type, buy_date, buy_price,
                   quantity, current_price):
    """Insert a new investment. Returns True on success, False on failure."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            INSERT INTO investments (user_id, asset_name, asset_type, buy_date,
                                     buy_price, quantity, current_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (user_id, asset_name, asset_type, buy_date, buy_price,
                               quantity, current_price))
        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding investment: {e}")
        return False
    finally:
        db.close_connection(connection)


def get_all_investments(user_id):
    """Return every investment as (investment_id, asset_name, asset_type,
    buy_date, buy_price, quantity, current_price) tuples."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT investment_id, asset_name, asset_type, buy_date, buy_price, quantity, current_price
            FROM investments
            WHERE user_id = %s
            ORDER BY asset_name
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching investments: {e}")
        return []
    finally:
        db.close_connection(connection)


def update_investment_price(user_id, investment_id, new_current_price):
    """Update only the current_price of an investment (e.g. after checking
    today's market price).

    Returns True if the investment exists and was saved, False if no
    investment has that id. As in update_transaction, a rowcount of 0 can
    simply mean the new price equalled the old one, so it is followed by an
    existence check instead of being treated as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = ("UPDATE investments SET current_price = %s "
                 "WHERE investment_id = %s AND user_id = %s")
        cursor.execute(query, (new_current_price, investment_id, user_id))
        connection.commit()
        if cursor.rowcount > 0:
            return True
        cursor.execute("SELECT investment_id FROM investments "
                       "WHERE investment_id = %s AND user_id = %s", (investment_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating investment price: {e}")
        return False
    finally:
        db.close_connection(connection)


def investment_exists(user_id, investment_id):
    """Return True if an investment with this investment_id exists."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT investment_id FROM investments WHERE investment_id = %s", (investment_id,))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking investment: {e}")
        return False
    finally:
        db.close_connection(connection)


def portfolio_pnl(user_id):
    """Report: profit/loss for every investment.

    For each row, (current_price - buy_price) * quantity gives the gain or
    loss on that holding. Returns a list of
    (asset_name, asset_type, buy_price, current_price, quantity, pnl, current_value)
    tuples ordered by pnl descending (best performers first).
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                asset_name,
                asset_type,
                buy_price,
                current_price,
                quantity,
                (current_price - buy_price) * quantity AS pnl,
                current_price * quantity AS current_value
            FROM investments
            WHERE user_id = %s
            ORDER BY pnl DESC
        """
        cursor.execute(query, (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating portfolio P&L report: {e}")
        return []
    finally:
        db.close_connection(connection)
