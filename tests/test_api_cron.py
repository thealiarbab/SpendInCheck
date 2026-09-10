"""Tests for the scheduled jobs and their guard.

This endpoint deletes accounts, so the guard is the part worth testing hard.
It is reachable from the public internet, and the only thing standing between
a stranger and a delete is the shared secret.
"""

import pytest

from server import config, db, operations


@pytest.fixture
def cron_secret(monkeypatch):
    """Configure a scheduler secret for the duration of one test."""
    secret = "a-real-cron-secret"
    monkeypatch.setattr(config, "CRON_SECRET", secret)
    return secret


def test_an_unconfigured_deployment_refuses_to_run(client, monkeypatch):
    """An unset secret must never mean "let anyone through".

    Without this the endpoint would be a public, unauthenticated way to
    delete every demonstration account.
    """
    monkeypatch.setattr(config, "CRON_SECRET", "")
    response = client.post("/api/v1/cron/clear-demos")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "cron_not_configured"


def test_a_caller_with_no_secret_is_told_nothing(client, cron_secret):
    """404 rather than 403, so a scanner learns nothing about the endpoint."""
    response = client.post("/api/v1/cron/clear-demos")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_a_wrong_secret_answers_exactly_like_no_secret(client, cron_secret):
    without = client.post("/api/v1/cron/clear-demos")
    wrong = client.post("/api/v1/cron/clear-demos",
                        headers={"X-Cron-Secret": "not-the-secret"})
    assert wrong.status_code == without.status_code == 404
    assert wrong.get_json() == without.get_json()


def test_the_explicit_header_is_accepted(client, cron_secret):
    response = client.post("/api/v1/cron/clear-demos",
                           headers={"X-Cron-Secret": cron_secret})
    assert response.status_code == 200
    assert "removed" in response.get_json()


def test_a_bearer_token_is_accepted(client, cron_secret):
    """The scheduler sends the secret this way rather than as its own header."""
    response = client.post("/api/v1/cron/clear-demos",
                           headers={"Authorization": "Bearer " + cron_secret})
    assert response.status_code == 200


def test_the_job_needs_no_csrf_token(client, cron_secret):
    """It is called by the platform, which has no session to hold one."""
    assert client.post("/api/v1/cron/clear-demos",
                       headers={"X-Cron-Secret": cron_secret}).status_code == 200


def _age_by_hours(user_id, hours):
    """Backdate an account's created_at, so staleness can be tested without
    waiting a day for it."""
    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET created_at = NOW() - make_interval(hours => %s) "
            "WHERE user_id = %s", (hours, user_id))
        connection.commit()
    finally:
        db.close_connection(connection)


def test_only_stale_demo_accounts_are_removed(make_user):
    """A real account, and a demo someone is still using, must both survive.

    The stale one is backdated rather than the sweep being widened to zero
    hours. A zero-hour sweep means "everything older than this instant",
    which deletes every demonstration account in the database -- including
    the one belonging to whoever happens to be looking at the site while
    the tests run. This shares a database with the deployed app, so a test
    that reaches beyond its own fixtures reaches real visitors.
    """
    real_user = make_user()
    fresh_demo, _ = operations.create_demo_user("not-a-real-hash")
    stale_demo, _ = operations.create_demo_user("not-a-real-hash")
    _age_by_hours(stale_demo, 48)

    try:
        removed = operations.delete_stale_demo_users(24)
        assert removed >= 1

        assert operations.get_all_categories(real_user), "a real account was deleted"
        assert _exists(fresh_demo), "a demo someone is still using was deleted"
        assert not _exists(stale_demo), "the stale demo was not swept"
    finally:
        operations.delete_demo_user(fresh_demo)
        operations.delete_demo_user(stale_demo)


def _exists(user_id):
    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
        return cursor.fetchone() is not None
    finally:
        db.close_connection(connection)


def test_a_real_account_cannot_be_deleted_through_the_demo_path(make_user):
    """delete_demo_user is guarded on is_demo, so a stale session id is safe."""
    real_user = make_user()
    assert operations.delete_demo_user(real_user) is False
    assert operations.get_all_categories(real_user)
