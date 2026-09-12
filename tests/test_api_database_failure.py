"""A database that cannot answer must say so.

Every read in server.operations used to end in

    except Error as e:
        print(...)
        return []

so a failed query left the route holding an empty list, which it served as a
perfectly successful 200. A signed-in account with four hundred transactions
was told it had none. That is the worst shape this failure can take: a 500 is
loud and gets reported, but a confident empty ledger teaches somebody their
data is gone.

The blueprint has always had a handler turning psycopg2.Error into 503
DatabaseUnavailable, with a docstring explaining that the usual cause is the
pooled connection limit and the honest answer is "try again". It was
unreachable code -- nothing ever let an error get that far.

These tests break the database on purpose and assert the answer is 503.
"""

import pytest
from psycopg2 import OperationalError

from server import db


@pytest.fixture
def broken_db(monkeypatch):
    """Make every new connection fail the way an exhausted pool does."""
    def refuse(*args, **kwargs):
        raise OperationalError("connection pool exhausted")

    monkeypatch.setattr(db, "get_connection", refuse)


@pytest.mark.parametrize("path", [
    "/api/v1/transactions",
    "/api/v1/accounts",
    "/api/v1/categories",
    "/api/v1/goals",
    "/api/v1/tags",
    "/api/v1/investments",
    "/api/v1/reports/net-worth?months=6",
    "/api/v1/reports/trend",
    "/api/v1/reports/dashboard",
    "/api/v1/reports/summary",
])
def test_a_failed_read_is_503_not_an_empty_200(api_account, broken_db, path):
    """An empty list is not "no answer". It is the claim that there is
    nothing there, which is a different and much more alarming statement."""
    response = api_account["client"].get(path)

    assert response.status_code == 503, (
        f"{path} answered {response.status_code}: "
        f"{response.get_data(as_text=True)[:200]}")
    assert response.is_json
    assert response.get_json()["error"]["code"] == "database_unavailable"


@pytest.mark.parametrize("method,path", [
    ("delete", "/api/v1/categories/1"),
    ("delete", "/api/v1/accounts/1"),
    ("delete", "/api/v1/goals/1"),
    ("delete", "/api/v1/tags/1"),
    ("delete", "/api/v1/investments/1"),
    ("get", "/api/v1/transactions/1"),
])
def test_a_failed_ownership_check_is_503_not_404(api_account, broken_db,
                                                 method, path):
    """An existence check answering False because the database was briefly
    unreachable is not "you do not own that" -- but it reached the route as
    exactly that, and the route answered 404.

    Which is the same lie as the empty ledger wearing a different hat: the
    record is there, the request was fine, and the app said otherwise with
    no indication that anything had gone wrong.
    """
    client = api_account["client"]
    call = getattr(client, method)
    response = (call(path, headers=api_account["headers"])
                if method != "get" else call(path))

    assert response.status_code == 503, (
        f"{method.upper()} {path} answered {response.status_code}")
    assert response.get_json()["error"]["code"] == "database_unavailable"


def test_the_failure_says_to_try_again_rather_than_that_it_is_broken(
        api_account, broken_db):
    """A pool that is momentarily full is not a broken application, and the
    message is the difference between somebody retrying and somebody
    concluding their ledger has been lost."""
    body = api_account["client"].get("/api/v1/transactions").get_json()
    assert "try again" in body["error"]["message"].lower()
