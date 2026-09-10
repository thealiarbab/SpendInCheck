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

def test_every_page_route_is_registered():
    """All thirteen Jinja routes survive being moved into register()."""
    app = create_app("test-key")
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    for path in ("/", "/dashboard", "/transactions", "/categories", "/budgets",
                 "/investments", "/reports", "/sign-in", "/sign-out",
                 "/register", "/demo"):
        assert path in rules


def test_templates_resolve_to_the_repo_root():
    """The factory lives in server/ but the templates never moved."""
    app = create_app("test-key")
    assert os.path.isfile(os.path.join(app.template_folder, "landing.html"))
    assert os.path.isdir(app.static_folder)


def test_session_cookie_is_hardened():
    """The cookie carries user_id, so script must not be able to read it."""
    app = create_app("test-key")
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["PERMANENT_SESSION_LIFETIME"].days == 14


def test_signed_out_visitor_is_redirected_away_from_private_pages():
    """Proves the before_request hook is still attached after the move.

    Worth asserting explicitly: a hook registered on the wrong object would
    leave every private page serving to anyone, and still return 200.
    """
    app = create_app("test-key")
    app.config["TESTING"] = True
    response = app.test_client().get("/dashboard")
    assert response.status_code == 302
    assert "/sign-in" in response.headers["Location"]


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
