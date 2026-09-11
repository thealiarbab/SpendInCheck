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

from server import db  # noqa: E402
from server import operations  # noqa: E402
from server.app import create_app  # noqa: E402


def delete_user(user_id):
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
        delete_user(user_id)


@pytest.fixture
def client():
    """A test client for the whole app, pages and API alike."""
    app = create_app("test-key")
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def api_account(client):
    """Register an account through the API and clean it up afterwards.

    Yields a dict with the client, the account, and a headers mapping that
    already carries the CSRF token, since every write needs one.
    """
    tag = uuid.uuid4().hex[:10]
    password = "a-long-enough-password"
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.post("/api/v1/auth/register", headers={"X-CSRF-Token": token},
                           json={"username": f"test_{tag}",
                                 "email": f"test_{tag}@example.invalid",
                                 "password": password})
    assert response.status_code == 201, response.get_json()
    body = response.get_json()

    yield {"client": client, "user": body["user"], "password": password,
           "headers": {"X-CSRF-Token": body["csrf_token"]}}

    delete_user(body["user"]["id"])


@pytest.fixture
def make_api_account():
    """Register accounts through the API, each with its own client.

    Separate clients mean separate cookie jars, which is what makes it
    possible to test that one signed-in account cannot reach another's rows.
    """
    app = create_app("test-key")
    app.config["TESTING"] = True
    created = []

    def _make():
        client = app.test_client()
        tag = uuid.uuid4().hex[:10]
        token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        response = client.post("/api/v1/auth/register", headers={"X-CSRF-Token": token},
                               json={"username": f"test_{tag}",
                                     "email": f"test_{tag}@example.invalid",
                                     "password": "a-long-enough-password"})
        assert response.status_code == 201, response.get_json()
        body = response.get_json()
        created.append(body["user"]["id"])
        client.headers = {"X-CSRF-Token": body["csrf_token"]}
        return client

    yield _make

    for user_id in created:
        delete_user(user_id)


@pytest.fixture
def api_user_id():
    """The user id behind a client from make_api_account.

    The recurring sweep is called directly rather than through an endpoint,
    because what is under test is what happens on a given day and the
    endpoint always uses today's. That needs the id, which the fixture that
    made the client deliberately does not expose -- so it is read back from
    the session the client already holds.
    """
    def _id(client):
        return client.get("/api/v1/auth/session").get_json()["user"]["id"]
    return _id
