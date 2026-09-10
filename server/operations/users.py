"""Account creation and sign-in lookups.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
import db

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
