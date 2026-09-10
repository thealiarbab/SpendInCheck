"""Tests for session handling and CSRF tokens.

These run inside a test request context because Flask's session only exists
during a request. No database is involved -- none of this reaches one.
"""

import os
import sys

import pytest
from flask import session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import auth  # noqa: E402
from server.app import create_app  # noqa: E402
from server.errors import NotSignedIn  # noqa: E402


@pytest.fixture
def ctx():
    """A request context, so session reads and writes work."""
    app = create_app("test-key")
    with app.test_request_context():
        yield


def test_require_user_rejects_a_signed_out_visitor(ctx):
    with pytest.raises(NotSignedIn) as raised:
        auth.require_user()
    assert raised.value.status == 401
    assert raised.value.to_dict()["error"]["code"] == "not_signed_in"


def test_sign_in_records_the_account_and_returns_a_token(ctx):
    token = auth.sign_in(7, "ali")
    assert session["user_id"] == 7
    assert session["username"] == "ali"
    assert auth.require_user() == 7
    assert token and session[auth.CSRF_SESSION_KEY] == token


def test_signing_in_clears_a_stale_demo_marker(ctx):
    """A real account must never inherit demo_id from a previous session.

    Without the clear, the next sign-out would wipe that account's data as
    though it were the demo.
    """
    auth.sign_in(1, "demo_abc", demo=True)
    assert auth.is_demo() is True

    auth.sign_in(2, "ali")
    assert auth.is_demo() is False
    assert "demo_id" not in session


def test_sign_out_abandons_everything(ctx):
    auth.sign_in(7, "ali")
    auth.sign_out()
    assert auth.current_user_id() is None
    assert auth.csrf_token() != ""


def test_csrf_accepts_only_the_session_token(ctx):
    token = auth.sign_in(7, "ali")
    assert auth.csrf_is_valid(token) is True
    assert auth.csrf_is_valid(token + "x") is False
    assert auth.csrf_is_valid("") is False
    assert auth.csrf_is_valid(None) is False


def test_rotating_replaces_the_previous_token(ctx):
    first = auth.sign_in(7, "ali")
    second = auth.rotate_csrf_token()
    assert first != second
    assert auth.csrf_is_valid(first) is False
    assert auth.csrf_is_valid(second) is True
