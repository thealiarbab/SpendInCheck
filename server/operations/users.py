"""Account creation and sign-in lookups.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.
"""

from psycopg2 import Error
from .. import db

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


# The account a new user starts with. Named for what it is rather than for
# a bank, because it is renamed the moment anybody cares.
STARTER_ACCOUNT = "Main"


def create_user(username, email, password_hash):
    """Register a new account, its starter categories, and somewhere to put
    the money.

    Both the user row and its categories are written in one transaction, so a
    failure part way through cannot leave an account with no categories.

    Returns the new user_id, or None if the username or email is already taken.
    """
    connection = None
    try:
        connection = db.get_connection()
        with db.transaction(connection):
            cursor = connection.cursor()
            user_id = _create_user_rows(cursor, username, email, password_hash)
        return user_id
    except Error as e:
        print(f"Error creating user: {e}")
        return None
    finally:
        db.close_connection(connection)


def _create_user_rows(cursor, username, email, password_hash):
    """The three inserts a new account needs, on an open cursor."""
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
    # And somewhere to put the money. Every transaction belongs to an
    # account, so a new user with none would be unable to write their
    # first row -- the one moment a ledger must not fail.
    cursor.execute(
        "INSERT INTO accounts (user_id, account_name, account_kind) "
        "VALUES (%s, %s, %s)",
        (user_id, STARTER_ACCOUNT, "Bank"),
    )
    return user_id


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


def get_currency(user_id):
    """The currency this account keeps its ledger in, or None if unknown."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT currency FROM users WHERE user_id = %s", (user_id,))
        found = cursor.fetchone()
        return found[0] if found else None
    except Error as e:
        print(f"Error reading currency: {e}")
        return None
    finally:
        db.close_connection(connection)


def set_currency(user_id, code):
    """Change the currency this account keeps its ledger in.

    Only the label changes. No amount is converted, because the ledger holds
    no exchange rates and inventing one would silently rewrite every figure
    the account has ever recorded.

    Returns True if the account exists and was saved.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET currency = %s WHERE user_id = %s",
                       (code, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error setting currency: {e}")
        return False
    finally:
        db.close_connection(connection)


def user_exists(user_id):
    """True if this account is still there.

    Cheap enough to call on a session read: a primary key lookup returning
    one column. Needed because a session outlives the row it points at --
    demonstration accounts are swept on a schedule, and the cookie in
    somebody's browser knows nothing about that.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
        return cursor.fetchone() is not None
    except Error as e:
        # A database failure must not read as "your account is gone" and sign
        # someone out; assume it is still there and let the real query fail.
        print(f"Error checking user: {e}")
        return True
    finally:
        db.close_connection(connection)
