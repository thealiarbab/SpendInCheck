"""Tests for the /api/v1/auth endpoints.

These go through the real client and the real database, because what is
under test is the whole path: CSRF gate, validation, session, and the shape
of the body that comes back.
"""

from server import auth, operations


def test_session_reports_a_signed_out_visitor_without_failing(client):
    """200 with a null user, not 401.

    A first load has to be able to tell "signed out" from "request failed".
    If this were a 401 the client's error handling would treat every fresh
    visit as a fault.
    """
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    body = response.get_json()
    assert body["user"] is None
    assert body["csrf_token"]


def test_writes_without_a_csrf_token_are_refused(client):
    response = client.post("/api/v1/auth/sign-in",
                           json={"login": "someone", "password": "whatever"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "csrf_failed"


def test_a_forged_csrf_token_is_refused(client):
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.post("/api/v1/auth/sign-in",
                           headers={"X-CSRF-Token": token + "tampered"},
                           json={"login": "someone", "password": "whatever"})
    assert response.status_code == 403


def test_registration_reports_every_bad_field_at_once(client):
    """One round trip should surface all the problems, not the first."""
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.post("/api/v1/auth/register", headers={"X-CSRF-Token": token},
                           json={"username": "ab", "email": "not-an-email", "password": "123"})
    assert response.status_code == 422
    fields = response.get_json()["error"]["fields"]
    assert set(fields) == {"username", "email", "password"}


def test_the_demo_name_prefix_cannot_be_registered(client):
    """Demo accounts are created by the server; a visitor holding one would
    let them occupy a name the demo flow expects to own."""
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.post("/api/v1/auth/register", headers={"X-CSRF-Token": token},
                           json={"username": "demo_stealer", "email": "a@b.co",
                                 "password": "a-long-enough-password"})
    assert response.status_code == 422
    assert "username" in response.get_json()["error"]["fields"]


def test_registering_signs_the_new_account_in(api_account):
    response = api_account["client"].get("/api/v1/auth/session")
    assert response.get_json()["user"]["id"] == api_account["user"]["id"]


def test_a_wrong_password_is_indistinguishable_from_a_missing_account(client, api_account):
    """Both answers must match, or this enumerates which accounts exist."""
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    headers = {"X-CSRF-Token": token}

    wrong_password = client.post("/api/v1/auth/sign-in", headers=headers,
                                 json={"login": api_account["user"]["username"],
                                       "password": "definitely-wrong"})
    no_such_account = client.post("/api/v1/auth/sign-in", headers=headers,
                                  json={"login": "nobody_at_all", "password": "whatever"})

    assert wrong_password.status_code == no_such_account.status_code == 401
    assert wrong_password.get_json() == no_such_account.get_json()


def test_sign_out_ends_the_session(api_account):
    client = api_account["client"]
    assert client.post("/api/v1/auth/sign-out",
                       headers=api_account["headers"]).status_code == 200
    assert client.get("/api/v1/auth/session").get_json()["user"] is None


def test_signing_back_in_works_after_signing_out(api_account):
    client = api_account["client"]
    client.post("/api/v1/auth/sign-out", headers=api_account["headers"])

    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.post("/api/v1/auth/sign-in", headers={"X-CSRF-Token": token},
                           json={"login": api_account["user"]["username"],
                                 "password": api_account["password"]})
    assert response.status_code == 200
    assert response.get_json()["user"]["id"] == api_account["user"]["id"]


def test_an_unknown_api_path_answers_in_json(client):
    """Never Flask's HTML error page -- a client parsing JSON would choke."""
    response = client.get("/api/v1/no-such-thing")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_the_pages_still_redirect_rather_than_returning_json(client):
    """The API exemption must not have loosened the page guard."""
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/sign-in" in response.headers["Location"]


def test_a_session_whose_demo_account_was_swept_reports_signed_out(client, monkeypatch):
    """Demonstration accounts are deleted on a schedule, but the cookie in
    somebody's browser knows nothing about that. Reporting them as signed
    in and then showing an empty ledger reads as data loss.

    The recheck window is set to zero here so the check runs on the next
    request rather than an hour later.
    """
    monkeypatch.setattr(auth, "DEMO_RECHECK_SECONDS", 0)

    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    body = client.post("/api/v1/auth/demo",
                       headers={"X-CSRF-Token": token}).get_json()
    assert client.get("/api/v1/auth/session").get_json()["user"] is not None

    operations.delete_demo_user(body["user"]["id"])

    assert client.get("/api/v1/auth/session").get_json()["user"] is None


def test_a_fresh_demo_session_is_not_re_checked(client, monkeypatch):
    """The check costs a round trip to Supabase, and GET /auth/session runs
    on every page load. Doing it every time put 260ms on the most frequent
    request in the app to catch something that happens once a day."""
    reads = []
    real = operations.user_exists
    monkeypatch.setattr(operations, "user_exists",
                        lambda user_id: (reads.append(user_id), real(user_id))[1])

    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    body = client.post("/api/v1/auth/demo",
                       headers={"X-CSRF-Token": token}).get_json()
    try:
        for _ in range(5):
            assert client.get("/api/v1/auth/session").get_json()["user"] is not None
        assert reads == [], "the account was re-checked inside the trusted window"
    finally:
        operations.delete_demo_user(body["user"]["id"])
