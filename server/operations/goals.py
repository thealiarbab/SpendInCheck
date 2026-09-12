"""Savings goals and the contributions towards them.

Progress is always summed from `goal_contributions`, never stored on the
goal. The same rule as account balances: a stored total is a second copy of
a fact that already exists, and the two disagree the first time a
contribution is edited or removed.
"""

from psycopg2 import IntegrityError
from .. import db

# What has been put in, less what has been taken back out. Negative
# contributions are how a withdrawal is recorded, so a plain SUM is already
# the right answer.
SAVED = "COALESCE(SUM(c.amount), 0)"


def list_goals(user_id, include_archived=False):
    """Every goal with what has been saved towards it.

    Returns (goal_id, goal_name, target_amount, target_date, account_id,
    account_name, saved, contributions, is_archived) tuples, unfinished
    goals first and then by target date -- what is still being saved for is
    what somebody came to look at.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT g.goal_id, g.goal_name, g.target_amount, g.target_date, "
            "       g.account_id, a.account_name, "
            f"      {SAVED} AS saved, "
            "       COUNT(c.contribution_id) AS contributions, g.is_archived "
            "  FROM goals g "
            "  LEFT JOIN goal_contributions c ON c.goal_id = g.goal_id "
            "  LEFT JOIN accounts a ON a.account_id = g.account_id "
            " WHERE g.user_id = %s AND (%s OR NOT g.is_archived) "
            " GROUP BY g.goal_id, a.account_name "
            # Reached goals sink below unreached ones; within each, the
            # soonest deadline first, and undated goals last rather than
            # first, which is what NULLS LAST buys.
            f" ORDER BY g.is_archived, ({SAVED} >= g.target_amount), "
            "          g.target_date NULLS LAST, lower(g.goal_name)",
            (user_id, include_archived))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def goal_exists(user_id, goal_id):
    """Return True if this goal is this user's."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT goal_id FROM goals WHERE goal_id = %s AND user_id = %s",
                       (goal_id, user_id))
        return cursor.fetchone() is not None
    finally:
        db.close_connection(connection)


def add_goal(user_id, goal_name, target_amount, target_date=None, account_id=None):
    """Create a goal. Returns its id, or None if the name is taken.

    The account, when given, must be this user's -- checked in the statement
    rather than beforehand, so there is no gap between the check and the
    insert.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO goals (user_id, goal_name, target_amount, target_date, "
            "                   account_id) "
            "SELECT %s, %s, %s, %s, %s "
            " WHERE %s IS NULL OR EXISTS ("
            "       SELECT 1 FROM accounts WHERE account_id = %s AND user_id = %s) "
            "ON CONFLICT (user_id, goal_name) DO NOTHING "
            "RETURNING goal_id",
            (user_id, goal_name, target_amount, target_date, account_id,
             account_id, account_id, user_id))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    finally:
        db.close_connection(connection)


def update_goal(user_id, goal_id, goal_name, target_amount, target_date=None,
                account_id=None):
    """Change a goal's name, target, deadline or account.

    Returns True only if a row was written. False covers "no goal of theirs
    has that id" and "that account_id was not theirs to attach it to", since
    the WHERE clause refuses both the same way.

    No existence check on a rowcount of 0: see update_transaction. Postgres
    counts matched rows, not changed ones, so the check could not fire for
    the reason it was written -- and because it looked the goal up without
    the account guard, it turned a refused write into True.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE goals SET goal_name = %s, target_amount = %s, "
            "       target_date = %s, account_id = %s "
            " WHERE goal_id = %s AND user_id = %s "
            "   AND (%s IS NULL OR EXISTS ("
            "        SELECT 1 FROM accounts WHERE account_id = %s AND user_id = %s))",
            (goal_name, target_amount, target_date, account_id, goal_id, user_id,
             account_id, account_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except IntegrityError as e:
        if connection:
            connection.rollback()
        print(f"Error updating goal: {e}")
        return False
    finally:
        db.close_connection(connection)


def set_goal_archived(user_id, goal_id, archived):
    """Put a goal aside, or bring it back.

    Reached goals are worth keeping: "we saved for this and did it" is the
    part of a ledger people actually enjoy.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE goals SET is_archived = %s "
                       " WHERE goal_id = %s AND user_id = %s",
                       (archived, goal_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        db.close_connection(connection)


def delete_goal(user_id, goal_id):
    """Delete a goal and its contributions.

    No reassignment question: a contribution towards a goal that no longer
    exists means nothing, so the cascade is the right answer rather than an
    orphan to rehome.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM goals WHERE goal_id = %s AND user_id = %s",
                       (goal_id, user_id))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    finally:
        db.close_connection(connection)


def list_contributions(user_id, goal_id):
    """What has been put towards one goal, newest first.

    Returns (contribution_id, contributed_on, amount, note) tuples. Scope
    comes through the goal, since the contributions table has no user_id.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT c.contribution_id, c.contributed_on, c.amount, c.note "
            "  FROM goal_contributions c "
            "  JOIN goals g ON g.goal_id = c.goal_id "
            " WHERE g.user_id = %s AND c.goal_id = %s "
            " ORDER BY c.contributed_on DESC, c.contribution_id DESC",
            (user_id, goal_id))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def add_contribution(user_id, goal_id, amount, contributed_on, note=None):
    """Record money set aside towards a goal, or taken back out of one.

    A negative amount is a withdrawal. There is no separate table and no
    direction column, so the running total is a plain SUM and cannot be
    computed with the sign the wrong way round.

    Returns the new contribution_id, or None if the goal is not this user's.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO goal_contributions (goal_id, contributed_on, amount, note) "
            "SELECT %s, %s, %s, %s "
            " WHERE EXISTS (SELECT 1 FROM goals "
            "                WHERE goal_id = %s AND user_id = %s) "
            "RETURNING contribution_id",
            (goal_id, contributed_on, amount, note, goal_id, user_id))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    finally:
        db.close_connection(connection)


def delete_contribution(user_id, contribution_id):
    """Remove one contribution. Returns True if a row was removed."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM goal_contributions c "
            " USING goals g "
            " WHERE g.goal_id = c.goal_id AND g.user_id = %s "
            "   AND c.contribution_id = %s",
            (user_id, contribution_id))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    finally:
        db.close_connection(connection)
