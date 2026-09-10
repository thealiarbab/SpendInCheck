"""Tests for the application factory and its startup checks.

None of these touch the database. The factory's job is to assemble an app and
refuse unsafe configuration, and both are decided before a single query runs.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import config  # noqa: E402
from server.app import create_app  # noqa: E402


@pytest.fixture
def in_production(monkeypatch):
    """Pretend this boot is a production deploy with a valid database.

    monkeypatch restores every attribute afterwards, which matters because
    config is a module: a plain assignment would leak into later tests.
    """
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(
        config, "DATABASE_URL", "postgresql://u:p@pooler.supabase.com:6543/postgres")
    monkeypatch.setattr(config, "SECRET_KEY", "a-real-production-key")


# --- assembly ---------------------------------------------------------------

def test_the_app_serves_the_api_and_nothing_else():
    """Every route is under /api/v1 since Phase 8 deleted the pages.

    Worth asserting rather than assuming: a route added at "/" here would
    not fail anything, it would simply never be reached in production --
    the edge serves the client's index.html for that path and this server
    never sees the request. The failure would be a page that works locally
    and 404s once deployed.
    """
    app = create_app("test-key")
    served = [rule.rule for rule in app.url_map.iter_rules()]
    assert served, "no routes registered at all"
    assert all(rule.startswith("/api/v1/") for rule in served), served


def test_the_auth_endpoints_are_registered():
    """The four the client cannot start without."""
    app = create_app("test-key")
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    for path in ("/api/v1/auth/session", "/api/v1/auth/sign-in",
                 "/api/v1/auth/register", "/api/v1/auth/sign-out",
                 "/api/v1/auth/demo"):
        assert path in rules


def test_there_is_no_static_route():
    """static_folder is off deliberately.

    Flask registers /static/<path> by default, pointing at a directory that
    no longer exists -- an endpoint that can only ever 404, on a server that
    answers in JSON.
    """
    app = create_app("test-key")
    assert app.static_folder is None
    assert "static" not in app.view_functions


def test_session_cookie_is_hardened():
    """The cookie carries user_id, so script must not be able to read it."""
    app = create_app("test-key")
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["PERMANENT_SESSION_LIFETIME"].days == 14


def test_an_unknown_path_answers_in_json():
    """Including one that is not under /api.

    Flask's own 404 is a styled HTML page. Nothing here serves HTML any
    more, and a fetch() handed a page instead of a body fails somewhere
    less obvious than the request that caused it.
    """
    app = create_app("test-key")
    app.config["TESTING"] = True
    for path in ("/api/v1/nothing-here", "/dashboard"):
        response = app.test_client().get(path)
        assert response.status_code == 404, path
        assert response.is_json, path
        assert response.get_json()["error"]["code"], path


# --- startup checks ---------------------------------------------------------

def test_development_boots_on_defaults():
    """The checks must not fire locally, where the defaults are expected."""
    assert create_app() is not None


def test_production_refuses_the_published_secret_key(in_production, monkeypatch):
    """A known signing key lets anyone forge a session for any account."""
    monkeypatch.setattr(config, "SECRET_KEY", config.DEV_SECRET_KEY)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_production_refuses_an_unconfigured_database(in_production, monkeypatch):
    """No URL and a localhost host means nothing was configured at all."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "DB_HOST", "localhost")
    with pytest.raises(RuntimeError, match="No database"):
        create_app()


def test_production_accepts_db_settings_without_a_url(in_production, monkeypatch):
    """DATABASE_URL is one of two valid ways to point at Postgres."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "DB_HOST", "db.internal")
    assert create_app() is not None
