"""Recurring rules, and the sweep that turns them into transactions.

A rule holds a schedule and a template. The sweep writes ordinary rows into
`transactions` marked with rule_id, so everything a materialised row can do
-- be edited, deleted, counted in a report -- it can do like any other.
"""

import calendar
from datetime import date, timedelta

from psycopg2 import Error
from .. import db

CADENCES = ("weekly", "monthly", "yearly")

# How many rows one rule may produce in a single sweep.
#
# A rule left paused for two years would otherwise post a hundred rows the
# moment it is resumed. The cap turns that into "as much as it can, then
# again next time", which is recoverable, rather than a hundred surprise
# transactions, which somebody has to delete by hand.
MAX_CATCHUP = 24


def _clamp_to_month(year, month, day):
    """The given day of that month, or its last day if it has no such day.

    A rule set for the 31st has to mean something in February. Landing on
    the 28th is the answer everybody expects; skipping the month entirely --
    which is what naive date arithmetic does by raising -- would quietly
    lose a month's rent.
    """
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_date_after(current, cadence, day_of_month=None):
    """When a rule fires after `current`.

    Monthly and yearly rules navigate by day_of_month rather than by adding
    days, so a rule on the 31st returns to the 31st in March after landing
    on the 28th in February. Adding "one month" as 30 days would walk the
    date backwards through the year.
    """
    if cadence == "weekly":
        return current + timedelta(days=7)

    day = day_of_month or current.day
    if cadence == "monthly":
        year, month = (current.year + 1, 1) if current.month == 12 else \
                      (current.year, current.month + 1)
        return _clamp_to_month(year, month, day)
    if cadence == "yearly":
        return _clamp_to_month(current.year + 1, current.month, day)
    raise ValueError(f"unknown cadence: {cadence}")


def list_rules(user_id):
    """Every rule with the names behind its ids, soonest due first."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT r.rule_id, r.description, r.amount, r.txn_type, r.cadence, "
            "       r.day_of_month, r.next_run_on, r.ends_on, r.is_paused, "
            "       r.category_id, c.category_name, r.account_id, a.account_name, "
            "       (SELECT COUNT(*) FROM transactions t WHERE t.rule_id = r.rule_id) "
            "  FROM recurring_rules r "
            "  JOIN categories c ON c.category_id = r.category_id "
            "  LEFT JOIN accounts a ON a.account_id = r.account_id "
            " WHERE r.user_id = %s "
            " ORDER BY r.is_paused, r.next_run_on, lower(r.description)",
            (user_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"Error fetching recurring rules: {e}")
        return []
    finally:
        db.close_connection(connection)


def rule_exists(user_id, rule_id):
    """Return True if this rule is this user's."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT rule_id FROM recurring_rules "
                       " WHERE rule_id = %s AND user_id = %s", (rule_id, user_id))
        return cursor.fetchone() is not None
    except Error as e:
        print(f"Error checking rule: {e}")
        return False
    finally:
        db.close_connection(connection)


def add_rule(user_id, description, category_id, amount, txn_type, cadence,
             next_run_on, day_of_month=None, account_id=None, ends_on=None):
    """Create a rule. Returns its id, or None if a referenced id is not theirs.

    Both foreign keys are checked inside the statement rather than before
    it, so there is no gap between checking and inserting.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO recurring_rules (user_id, description, category_id, "
            "        account_id, amount, txn_type, cadence, day_of_month, "
            "        next_run_on, ends_on) "
            "SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s "
            " WHERE EXISTS (SELECT 1 FROM categories "
            "                WHERE category_id = %s AND user_id = %s) "
            "   AND (%s IS NULL OR EXISTS (SELECT 1 FROM accounts "
            "                WHERE account_id = %s AND user_id = %s)) "
            "RETURNING rule_id",
            (user_id, description, category_id, account_id, amount, txn_type,
             cadence, day_of_month, next_run_on, ends_on,
             category_id, user_id, account_id, account_id, user_id))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding recurring rule: {e}")
        return None
    finally:
        db.close_connection(connection)


def update_rule(user_id, rule_id, description, category_id, amount, txn_type,
                cadence, next_run_on, day_of_month=None, account_id=None,
                ends_on=None):
    """Change a rule. Rows it has already written are left exactly as they are.

    That is deliberate: the rent that went up in August is a fact about
    August, and rewriting history to match the new figure would make every
    past report disagree with what actually happened.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE recurring_rules SET description = %s, category_id = %s, "
            "       account_id = %s, amount = %s, txn_type = %s, cadence = %s, "
            "       day_of_month = %s, next_run_on = %s, ends_on = %s "
            " WHERE rule_id = %s AND user_id = %s "
            "   AND EXISTS (SELECT 1 FROM categories "
            "                WHERE category_id = %s AND user_id = %s) "
            "   AND (%s IS NULL OR EXISTS (SELECT 1 FROM accounts "
            "                WHERE account_id = %s AND user_id = %s))",
            (description, category_id, account_id, amount, txn_type, cadence,
             day_of_month, next_run_on, ends_on, rule_id, user_id,
             category_id, user_id, account_id, account_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error updating recurring rule: {e}")
        return False
    finally:
        db.close_connection(connection)


def set_rule_paused(user_id, rule_id, paused):
    """Stop a rule firing, or start it again.

    Resuming does not backfill silently: the sweep catches up from
    next_run_on, capped at MAX_CATCHUP rows per run.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE recurring_rules SET is_paused = %s "
                       " WHERE rule_id = %s AND user_id = %s",
                       (paused, rule_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error pausing rule: {e}")
        return False
    finally:
        db.close_connection(connection)


def delete_rule(user_id, rule_id):
    """Delete a rule. The transactions it wrote stay.

    The foreign key is SET NULL: those rows are money that actually moved,
    and they simply stop knowing which rule produced them.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM recurring_rules "
                       " WHERE rule_id = %s AND user_id = %s", (rule_id, user_id))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting rule: {e}")
        return False
    finally:
        db.close_connection(connection)


def _materialise_one(cursor, rule, today):
    """Write every row a single rule owes, and advance it. Returns the count.

    The insert and the advance are the same database transaction, which is
    what makes a repeated sweep safe: either a row exists and next_run_on
    has moved past it, or neither happened.
    """
    (rule_id, user_id, description, category_id, account_id, amount, txn_type,
     cadence, day_of_month, next_run_on, ends_on) = rule

    written = 0
    due = next_run_on
    finished = False
    while due <= today and written < MAX_CATCHUP:
        if ends_on is not None and due > ends_on:
            finished = True
            break

        # ON CONFLICT DO NOTHING against uniq_rule_run: if a previous sweep
        # already wrote this date and then died before advancing the rule,
        # this run skips the row and advances anyway rather than failing.
        cursor.execute(
            "INSERT INTO transactions (user_id, txn_date, category_id, amount, "
            "        txn_type, description, account_id, rule_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (rule_id, txn_date) WHERE rule_id IS NOT NULL "
            "DO NOTHING",
            (user_id, due, category_id, amount, txn_type, description,
             account_id, rule_id))
        written += cursor.rowcount
        due = next_date_after(due, cadence, day_of_month)

    # A rule past its end date is paused rather than merely advanced. Left
    # unpaused it stays due forever -- next_run_on never passes today --
    # so every sweep from here to eternity would select it, walk the loop
    # once and write nothing.
    if finished:
        cursor.execute("UPDATE recurring_rules SET is_paused = true, "
                       "       next_run_on = %s WHERE rule_id = %s",
                       (due, rule_id))
    elif due != next_run_on:
        cursor.execute("UPDATE recurring_rules SET next_run_on = %s "
                       " WHERE rule_id = %s", (due, rule_id))
    return written


def materialise_due(user_id=None, today=None):
    """Write the transactions every due rule owes.

    Runs for one user when given one, and for everybody when not -- the
    scheduled job passes nothing, and a signed-in visitor who wants their
    rent posted now passes their own id.

    Returns {"rules": n, "transactions": n}.
    """
    today = today or date.today()
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        # One transaction around the whole sweep. FOR UPDATE only holds a
        # lock inside one, and writing a row without advancing its rule --
        # or advancing without writing -- is exactly the split the unique
        # index exists to make harmless. Both together, or neither.
        with db.transaction(connection):
            written = _sweep(cursor, user_id, today)
        return written
    except Error as e:
        print(f"Error materialising recurring rules: {e}")
        return {"rules": 0, "transactions": 0}
    finally:
        db.close_connection(connection)


def _sweep(cursor, user_id, today):
    """Select the due rules and materialise them, inside an open transaction."""
    # FOR UPDATE SKIP LOCKED: two overlapping sweeps take different
    # rules rather than queueing on the same ones, and neither waits.
    # The unique index is what makes a double-write impossible; this is
    # what stops the second run doing the work twice for nothing.
    cursor.execute(
        "SELECT rule_id, user_id, description, category_id, account_id, "
        "       amount, txn_type, cadence, day_of_month, next_run_on, ends_on "
        "  FROM recurring_rules "
        " WHERE NOT is_paused AND next_run_on <= %s "
        "   AND (%s IS NULL OR user_id = %s) "
        " ORDER BY rule_id "
        "   FOR UPDATE SKIP LOCKED",
        (today, user_id, user_id))
    due = cursor.fetchall()

    written = 0
    for rule in due:
        written += _materialise_one(cursor, rule, today)

    return {"rules": len(due), "transactions": written}
