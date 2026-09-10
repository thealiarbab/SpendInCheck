"""
Shared fixtures for the operations tests.

These run against the real PostgreSQL database rather than a mock, because
the behaviour under test is the SQL itself. A query that forgets its user_id
filter looks perfectly correct in Python and only misbehaves in the database,
so a mocked cursor would report success on exactly the bug worth catching.

Every fixture cleans up after itself: users are deleted on teardown and every
data table cascades from users, so a failed run leaves nothing behind.
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from server import operations  # noqa: E402


def _delete_user(user_id):
    """Remove a user and, by cascade, everything they own."""
    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        connection.commit()
    finally:
        db.close_connection(connection)


@pytest.fixture
def make_user():
    """Create throwaway users, deleting them all when the test finishes."""
    created = []

    def _make():
        # A random suffix keeps concurrent runs and leftovers from colliding
        # with the UNIQUE constraints on username and email.
        tag = uuid.uuid4().hex[:10]
        user_id = operations.create_user(
            f"test_{tag}", f"test_{tag}@example.invalid", "not-a-real-hash"
        )
        assert user_id is not None, "could not create a test user"
        created.append(user_id)
        return user_id

    yield _make

    for user_id in created:
        _delete_user(user_id)
