"""Malformed requests must be refused, not crash the request.

Every case here returned a 500 with an HTML body before the fix. None of
them could corrupt data -- each one died before any write -- but a 500 on
input the client can plainly send is a bug, and an HTML error page reaches
a JSON client as an unparseable response rather than a message it can show.

The shape of the mistake is the same in all of them: a guard that checks a
value's size or emptiness without first settling its type.
"""


def _csrf(client):
    """A token from the session endpoint, which hands one to anybody."""
    return client.get("/api/v1/auth/session").get_json()["csrf_token"]


def test_a_non_object_body_is_refused_not_crashed(api_account):
    """`[1]` as a body used to reach .get() and raise AttributeError.

    request.get_json returns whatever was sent, and the usual `or {}` does
    not catch a list, because a non-empty list is truthy. Routes that build
    a Validator were already safe -- its constructor checks -- so these are
    the three that read the body directly.
    """
    client, headers = api_account["client"], api_account["headers"]

    for method, path in [(client.put, "/api/v1/settings/currency"),
                         (client.put, "/api/v1/transactions/1/tags"),
                         (client.post, "/api/v1/import/commit")]:
        response = method(path, headers=headers, json=[1])
        assert response.status_code == 422, (path, response.status_code)
        assert response.is_json, f"{path} answered HTML, not JSON"
        assert response.get_json()["error"]["message"] == "Expected a JSON object."


def test_a_non_string_password_is_refused_on_register(client):
    """A list of eight has a len() of eight, so it passed the length check
    and then raised inside generate_password_hash."""
    response = client.post("/api/v1/auth/register",
                           headers={"X-CSRF-Token": _csrf(client)},
                           json={"username": "probe_user",
                                 "email": "probe@example.invalid",
                                 "password": [1, 2, 3, 4, 5, 6, 7, 8]})
    assert response.status_code == 422
    assert response.is_json
    assert response.get_json()["error"]["fields"]["password"]


def test_a_non_string_password_is_refused_on_sign_in(api_account):
    """Sign-in needs a login that resolves to a real account to reach the
    hash comparison at all, which is why an unknown name answers 401 and
    hides this. The account from the fixture is a real one.
    """
    client = api_account["client"]
    response = client.post("/api/v1/auth/sign-in",
                           headers=api_account["headers"],
                           json={"login": api_account["user"]["username"],
                                 "password": [1, 2, 3, 4, 5, 6, 7, 8]})
    assert response.status_code == 422
    assert response.is_json
    assert response.get_json()["error"]["fields"]["password"]


def test_an_unreadable_page_number_is_ignored_not_fatal(api_account):
    """A page number comes off a URL somebody may have edited or shared.

    _read_filters already drops an unreadable filter rather than rejecting
    it, for exactly that reason; the page number now follows the same rule.
    The long run of digits is not idle: since Python 3.11 int() refuses a
    string of more than 4300 digits, so isdigit() alone is not enough.
    """
    client = api_account["client"]

    for query in ["page=abc", "page=", "page=2a", "page=-1", "page=last",
                  "page=" + "9" * 5000, "per_page=abc", "per_page=" + "9" * 5000]:
        response = client.get("/api/v1/transactions?" + query)
        assert response.status_code == 200, (query, response.status_code)
        assert response.get_json()["page"]["number"] >= 1


def test_a_readable_page_number_is_still_honoured(api_account):
    """The guard must not have flattened every page to 1."""
    client = api_account["client"]
    body = client.get("/api/v1/transactions?page=3&per_page=10").get_json()
    assert body["page"]["number"] == 3
    assert body["page"]["per_page"] == 10
