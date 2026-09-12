"""Tags: the labels a transaction can carry any number of.

Every query here reaches user scope through `transactions`, because
`transaction_tags` deliberately has no user_id of its own. See migration
004 for why.
"""

from psycopg2 import IntegrityError
from .. import db

# Long enough for "reimbursed by work", short enough that a tag stays a
# label rather than becoming a note.
MAX_TAG_LENGTH = 40


def list_tags(user_id):
    """Every tag with how many transactions carry it, most used first.

    Returns (tag_id, tag_name, uses) tuples. The count is what makes the
    list navigable once there are thirty of them: alphabetical order buries
    the tag used on half the ledger between two used once each.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # LEFT JOIN so a tag nothing carries still appears -- it is exactly
        # the tag most likely to want deleting.
        cursor.execute(
            "SELECT t.tag_id, t.tag_name, COUNT(tt.transaction_id) AS uses "
            "  FROM tags t "
            "  LEFT JOIN transaction_tags tt ON tt.tag_id = t.tag_id "
            " WHERE t.user_id = %s "
            " GROUP BY t.tag_id "
            " ORDER BY uses DESC, lower(t.tag_name)",
            (user_id,))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def tag_exists(user_id, tag_id):
    """Return True if this tag is this user's."""
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT tag_id FROM tags WHERE tag_id = %s AND user_id = %s",
                       (tag_id, user_id))
        return cursor.fetchone() is not None
    finally:
        db.close_connection(connection)


def add_tag(user_id, tag_name):
    """Create a tag. Returns its id, or None if the user already has it.

    Matching is case-insensitive, so adding "Holiday" when "holiday" exists
    is a no-op rather than a second tag that means the same thing.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO tags (user_id, tag_name) VALUES (%s, %s) "
            "ON CONFLICT (user_id, lower(tag_name)) DO NOTHING "
            "RETURNING tag_id",
            (user_id, tag_name))
        row = cursor.fetchone()
        connection.commit()
        return row[0] if row else None
    finally:
        db.close_connection(connection)


def rename_tag(user_id, tag_id, tag_name):
    """Change a tag's name, keeping every transaction that carries it.

    Returns True if saved, False if it is not theirs or the new name collides
    with another of this user's tags.

    No existence check on a rowcount of 0: see update_transaction. Renaming a
    tag to the name it already has still reports 1 on Postgres, which counts
    matched rows rather than changed ones.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE tags SET tag_name = %s "
                       " WHERE tag_id = %s AND user_id = %s",
                       (tag_name, tag_id, user_id))
        connection.commit()
        return cursor.rowcount > 0
    except IntegrityError as e:
        if connection:
            connection.rollback()
        print(f"Error renaming tag: {e}")
        return False
    finally:
        db.close_connection(connection)


def delete_tag(user_id, tag_id):
    """Delete a tag. The transactions carrying it keep everything else.

    No reassignment question, unlike a category: a transaction with no tags
    is perfectly ordinary, whereas a transaction with no category is not a
    transaction. The links go by cascade.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM tags WHERE tag_id = %s AND user_id = %s",
                       (tag_id, user_id))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    finally:
        db.close_connection(connection)


def tags_for_transactions(user_id, transaction_ids):
    """The tags on each of these transactions, as {transaction_id: [names]}.

    Takes the whole page at once rather than being called per row: a ledger
    of twenty-five rows would otherwise be twenty-five more round trips to
    the database, which on a hosted one costs more than the page.
    """
    if not transaction_ids:
        return {}
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT tt.transaction_id, t.tag_id, t.tag_name "
            "  FROM transaction_tags tt "
            "  JOIN tags t ON t.tag_id = tt.tag_id "
            # Scope comes through the transaction, since the link table has
            # no user_id of its own.
            "  JOIN transactions x ON x.transaction_id = tt.transaction_id "
            " WHERE x.user_id = %s AND tt.transaction_id = ANY(%s) "
            " ORDER BY lower(t.tag_name)",
            (user_id, list(transaction_ids)))
        found = {}
        for transaction_id, tag_id, tag_name in cursor.fetchall():
            found.setdefault(transaction_id, []).append(
                {"id": tag_id, "name": tag_name})
        return found
    finally:
        db.close_connection(connection)


def set_transaction_tags(user_id, transaction_id, tag_ids):
    """Replace the set of tags on one transaction.

    Replace rather than add: the edit form shows the whole set, so what it
    submits is the whole set. Adding would mean the form could never take a
    tag off.

    Both statements are one transaction, so a failure part way cannot leave
    a row with its old tags removed and its new ones unwritten.

    Returns True if the transaction is this user's, False otherwise -- an
    empty tag_ids list on a row that is theirs is a success, not a failure.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT transaction_id FROM transactions "
                       " WHERE transaction_id = %s AND user_id = %s",
                       (transaction_id, user_id))
        if cursor.fetchone() is None:
            return False

        # The delete and the insert are one unit: between them the row has
        # no tags at all, and a failure in the middle would leave it that
        # way rather than as it was.
        with db.transaction(connection):
            cursor.execute("DELETE FROM transaction_tags WHERE transaction_id = %s",
                           (transaction_id,))

            if tag_ids:
                # One statement, and the ownership filter lives inside it: a
                # tag id that is not this user's simply matches no row, so a
                # hostile or stale id is dropped rather than attached or
                # raised over.
                cursor.execute(
                    "INSERT INTO transaction_tags (transaction_id, tag_id) "
                    "SELECT %s, tag_id FROM tags "
                    " WHERE user_id = %s AND tag_id = ANY(%s)",
                    (transaction_id, user_id, list(tag_ids)))
        return True
    finally:
        db.close_connection(connection)
