"""Accounts, their balances, and transfers between them.

A balance is never stored. Every function that reports one derives it from
the account's opening balance and the rows filed against it, so the figure
cannot drift away from the transactions that produced it.
"""

from psycopg2 import Error
from .. import db

# What an account can be. Kept short on purpose: the kind only changes how
# an account is grouped and iconed, and a long list of near-synonyms makes
# people stop to choose rather than get on with it.
ACCOUNT_KINDS = ("Bank", "Cash", "Card", "Wallet", "Other")

# The per-user category both legs of a transfer are filed under. Reports
# exclude it, so moving money between your own accounts does not read as
# income and expenditure.
TRANSFER_CATEGORY = "Transfer"

# The balance of an account: what it opened with, plus what arrived, less
# what left. Written once here because four different callers need it and a
# second copy is a second chance to get the signs the wrong way round.
BALANCE = ("a.opening_balance"
           " + COALESCE(SUM(t.amount) FILTER (WHERE t.txn_type = 'Income'), 0)"
           " - COALESCE(SUM(t.amount) FILTER (WHERE t.txn_type = 'Expense'), 0)")


def list_accounts(user_id, include_archived=False):
    """Every account with its derived balance and how many rows it holds.

    Returns a list of (account_id, account_name, account_kind, opening_balance,
    balance, transactions, is_archived) tuples, live accounts first and each
    group by name.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # LEFT JOIN, so an account with no transactions still appears -- at
        # its opening balance, which is the correct answer and not zero.
        cursor.execute(
            "SELECT a.account_id, a.account_name, a.account_kind, a.opening_balance, "
            f"       {BALANCE} AS balance, "
            "        COUNT(t.transaction_id) AS transactions, a.is_archived "
            "  FROM accounts a "
            "  LEFT JOIN transactions t "
            "    ON t.account_id = a.account_id AND t.user_id = a.user_id "
            " WHERE a.user_id = %s AND (%s OR NOT a.is_archived) "
            " GROUP BY a.account_id "
            " ORDER BY a.is_archived, a.account_name",
            (user_id, include_archived))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching accounts: {e}")
        return []
    finally:
        db.close_connection(connection)


def account_exists(user_id, account_id):
    """Return True if this account is this user's."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT account_id FROM accounts "
                       " WHERE account_id = %s AND user_id = %s",
                       (account_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking account: {e}")
        return False
    finally:
        db.close_connection(connection)


def default_account_id(user_id):
    """Where a transaction goes when the caller did not say.

    Every user has at least one account -- migration 003 gave everyone a
    'Main' -- so this is about not making the older write paths, and the
    quick-add form, demand a choice nobody wants to make. Returns None only
    if every account has been archived.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT account_id FROM accounts "
                       " WHERE user_id = %s AND NOT is_archived "
                       " ORDER BY account_id LIMIT 1", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Error as e:
        print(f"Error finding the default account: {e}")
        return None
    finally:
        db.close_connection(connection)


def add_account(user_id, account_name, account_kind, opening_balance=0):
    """Create an account. Returns its id, or None if the name is taken."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO accounts (user_id, account_name, account_kind, opening_balance) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (user_id, account_name) DO NOTHING "
            "RETURNING account_id",
            (user_id, account_name, account_kind, opening_balance))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding account: {e}")
        return None
    finally:
        db.close_connection(connection)


def update_account(user_id, account_id, account_name, account_kind, opening_balance):
    """Rename an account, change its kind, or correct its opening balance.

    Returns True if it is this user's and was saved, False if the new name
    collides with another of their accounts. As in rename_category, a
    rowcount of 0 can simply mean nothing changed, so it is followed by an
    existence check rather than reported as a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE accounts SET account_name = %s, account_kind = %s, "
                       "       opening_balance = %s "
                       " WHERE account_id = %s AND user_id = %s",
                       (account_name, account_kind, opening_balance,
                        account_id, user_id))
        connection.commit()
        if cursor.rowcount > 0:
            return True
        return account_exists(user_id, account_id)
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating account: {e}")
        return False
    finally:
        db.close_connection(connection)


def set_archived(user_id, account_id, archived):
    """Hide an account from the pickers, or bring it back.

    Archiving is the answer to "I closed this account": the history stays
    readable and the account stops being offered for new rows.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE accounts SET is_archived = %s "
                       " WHERE account_id = %s AND user_id = %s",
                       (archived, account_id, user_id))
        connection.commit()
        return cursor.rowcount > 0 or account_exists(user_id, account_id)
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error archiving account: {e}")
        return False
    finally:
        db.close_connection(connection)


def count_account_use(user_id, account_id):
    """How many transactions sit on this account, and how many are transfers.

    The delete screen asks first so it can say what will move. Transfers are
    counted separately because moving them elsewhere can leave a transfer
    whose two legs are on the same account, which is not a transfer at all.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*), "
                       "       COUNT(*) FILTER (WHERE transfer_group_id IS NOT NULL) "
                       "  FROM transactions "
                       " WHERE user_id = %s AND account_id = %s",
                       (user_id, account_id))
        transactions, transfers = cursor.fetchone()
        return {"transactions": transactions, "transfers": transfers}
    except Error as e:
        print(f"Error counting account use: {e}")
        return {"transactions": 0, "transfers": 0}
    finally:
        db.close_connection(connection)


def delete_account(user_id, account_id, reassign_to=None):
    """Delete an account, optionally moving its transactions elsewhere first.

    The foreign key is RESTRICT, so an account holding history cannot simply
    be dropped. With reassign_to given the rows move and the account goes,
    both in one transaction.

    Moving rows can strand a transfer: if both legs end up on the same
    account, the pair says money left an account and arrived in the same
    one. Those legs keep their rows -- they are still real movements of
    money -- but lose their transfer_group_id, so nothing later tries to
    present them as a pair.

    Returns True on success, False if the account is not this user's.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        with db.transaction(connection):
            if reassign_to is not None:
                cursor.execute("UPDATE transactions SET account_id = %s "
                               " WHERE user_id = %s AND account_id = %s",
                               (reassign_to, user_id, account_id))
                cursor.execute(
                    "UPDATE transactions SET transfer_group_id = NULL "
                    " WHERE user_id = %s AND transfer_group_id IN ("
                    "       SELECT transfer_group_id FROM transactions "
                    "        WHERE user_id = %s AND transfer_group_id IS NOT NULL "
                    "        GROUP BY transfer_group_id "
                    "       HAVING COUNT(DISTINCT account_id) < 2)",
                    (user_id, user_id))

            cursor.execute("DELETE FROM accounts WHERE account_id = %s AND user_id = %s",
                           (account_id, user_id))
            deleted = cursor.rowcount > 0
        return deleted
    except Error as e:
        print(f"Error deleting account: {e}")
        return False
    finally:
        db.close_connection(connection)


def _transfer_category_id(cursor, user_id):
    """The user's system Transfer category, made on first use.

    Created on demand rather than seeded for everyone, because most users
    never transfer anything and a row per user that nothing points at is
    clutter in every category list.

    The fallback name exists because a user may already have an ordinary
    category called Transfer. Taking it over would silently drop their
    existing rows out of every report, so it is left alone and the system
    one is named around it.
    """
    cursor.execute("SELECT category_id FROM categories "
                   " WHERE user_id = %s AND is_system AND category_type = 'Transfer'",
                   (user_id,))
    found = cursor.fetchone()
    if found:
        return found[0]

    for name in (TRANSFER_CATEGORY, TRANSFER_CATEGORY + " (system)"):
        cursor.execute(
            "INSERT INTO categories (user_id, category_name, category_type, is_system) "
            "VALUES (%s, %s, 'Transfer', true) "
            "ON CONFLICT (user_id, category_name) DO NOTHING "
            "RETURNING category_id", (user_id, name))
        made = cursor.fetchone()
        if made:
            return made[0]
    return None


class _NoTransferCategory(Exception):
    """Raised inside the transaction to undo a transfer that cannot stand.

    A return would commit what had already been written; raising is what
    makes db.transaction roll it back. Private, and caught immediately.
    """


def transfer(user_id, from_account_id, to_account_id, amount, txn_date,
             description=None):
    """Move money between two of this user's accounts.

    Written as two ordinary transactions sharing a transfer_group_id: an
    Expense leaving one account and an Income arriving in the other. That is
    what each account actually sees, so balances need no special case, and
    the shared id is what lets the pair be shown and deleted together.

    Both rows are inserted by a single statement, so there is no window in
    which one leg exists without the other and no way for them to disagree
    about the group id.

    Returns the transfer_group_id, or None if anything was wrong.
    """
    if from_account_id == to_account_id:
        return None

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        # The category may have to be created, and the two legs must not
        # exist without each other, so the lot is one transaction.
        with db.transaction(connection):
            category_id = _transfer_category_id(cursor, user_id)
            if category_id is None:
                raise _NoTransferCategory()

            cursor.execute(
                "WITH pair AS (SELECT gen_random_uuid() AS group_id) "
                "INSERT INTO transactions (user_id, txn_date, category_id, amount, "
                "                          txn_type, description, account_id, "
                "                          transfer_group_id) "
                "SELECT %s, %s, %s, %s, leg.txn_type, %s, leg.account_id, "
                "       pair.group_id "
                "  FROM pair, (VALUES ('Expense', %s::int), ('Income', %s::int)) "
                "         AS leg(txn_type, account_id) "
                "  JOIN accounts a ON a.account_id = leg.account_id "
                "                 AND a.user_id = %s "
                "RETURNING transfer_group_id",
                (user_id, txn_date, category_id, amount, description,
                 from_account_id, to_account_id, user_id))
            rows = cursor.fetchall()
            # The join to accounts drops a leg whose account is not this
            # user's, so anything other than two rows means the transfer was
            # not what it claimed to be -- and raising is what undoes the
            # leg that did land.
            if len(rows) != 2:
                raise _NoTransferCategory()

        return str(rows[0][0])
    except _NoTransferCategory:
        return None
    except Error as e:
        print(f"Error transferring between accounts: {e}")
        return None
    finally:
        db.close_connection(connection)


def delete_transfer(user_id, transfer_group_id):
    """Remove both legs of a transfer at once.

    Deleting one leg alone would leave money that arrived from nowhere, so
    the group is the unit of deletion.

    Returns the number of rows removed, which is 2 on success and 0 if the
    group is not this user's.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM transactions "
                       " WHERE user_id = %s AND transfer_group_id = %s",
                       (user_id, transfer_group_id))
        removed = cursor.rowcount
        connection.commit()
        return removed
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting transfer: {e}")
        return 0
    finally:
        db.close_connection(connection)
