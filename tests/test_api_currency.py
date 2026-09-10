"""Keeping the ledger in a currency other than the rupee.

The interesting cases are not the 156 currencies divided into hundredths --
those behave exactly as the rupee always did. They are the 39 that do not:
the yen and its kind, which have no minor unit at all, and the six dinars
divided into thousandths, which DECIMAL(10,2) could not hold before
migration 002 widened the columns.
"""

from server import currency


def a_category(client):
    return client.get("/api/v1/categories").get_json()["items"][0]["id"]


def add(client, amount):
    """Record a transaction and return the amount as the API gives it back."""
    client.post("/api/v1/transactions", headers=client.headers,
                json={"date": "2026-08-01", "category_id": a_category(client),
                      "amount": amount, "type": "Expense", "description": "probe"})
    rows = client.get("/api/v1/transactions").get_json()["items"]
    return next(row["amount"] for row in rows if row["description"] == "probe")


def switch(client, code):
    return client.put("/api/v1/settings/currency", headers=client.headers,
                      json={"currency": code})


# --- the table itself -------------------------------------------------------

def test_every_iso_currency_is_offered(make_api_account):
    body = make_api_account().get("/api/v1/settings/currencies").get_json()
    assert len(body["items"]) == len(currency.ALL) >= 150
    for code in ("INR", "USD", "EUR", "JPY", "KWD", "VND"):
        assert code in body["items"]


def test_the_scales_match_what_iso_4217_says():
    """Spot checks against the standard, so a regenerated table cannot
    quietly change a currency's meaning."""
    assert currency.decimals("INR") == 2
    assert currency.decimals("USD") == 2
    assert currency.decimals("JPY") == 0    # no sen in circulation
    assert currency.decimals("KRW") == 0
    assert currency.decimals("KWD") == 3    # 1000 fils to the dinar
    assert currency.decimals("BHD") == 3
    assert len(currency.THREE_DECIMAL) == 6
    assert len(currency.ZERO_DECIMAL) == 33


# --- setting it -------------------------------------------------------------

def test_a_new_account_keeps_its_ledger_in_rupees(make_api_account):
    client = make_api_account()
    assert client.get("/api/v1/settings/currencies").get_json()["current"] == "INR"


def test_changing_the_currency(make_api_account):
    client = make_api_account()
    assert switch(client, "USD").get_json() == {"currency": "USD", "decimals": 2}
    assert client.get("/api/v1/auth/session").get_json()["user"]["currency"] == "USD"


def test_a_lowercase_code_is_accepted(make_api_account):
    assert switch(make_api_account(), "eur").get_json()["currency"] == "EUR"


def test_an_unknown_code_is_refused(make_api_account):
    client = make_api_account()
    response = switch(client, "ZZZ")
    assert response.status_code == 422
    assert "currency" in response.get_json()["error"]["fields"]
    assert client.get("/api/v1/settings/currencies").get_json()["current"] == "INR"


def test_a_write_with_no_token_is_refused_before_anything_else(client):
    """CSRF is checked in before_request, so it answers first -- earlier
    than the session check, which is the right order."""
    response = client.put("/api/v1/settings/currency", json={"currency": "USD"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "csrf_failed"


def test_changing_the_currency_needs_a_session(client):
    """Past CSRF, a signed-out caller still has no account to change."""
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    response = client.put("/api/v1/settings/currency",
                          headers={"X-CSRF-Token": token}, json={"currency": "USD"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "not_signed_in"


# --- what the scale actually does -------------------------------------------

def test_a_dinar_keeps_its_fils(make_api_account):
    """1.234 KWD could not be stored at all in DECIMAL(10,2)."""
    client = make_api_account()
    switch(client, "KWD")
    assert add(client, "1.234") == "1.234"


def test_a_dinar_rounds_at_the_fourth_place_not_the_third(make_api_account):
    client = make_api_account()
    switch(client, "KWD")
    assert add(client, "1.2345") == "1.235"


def test_yen_has_no_minor_unit(make_api_account):
    """¥1234 is not ¥1234.00, and a decimal point in a yen figure is wrong."""
    client = make_api_account()
    switch(client, "JPY")
    assert add(client, "1234.56") == "1235"


def test_the_rupee_is_unchanged(make_api_account):
    """The currency work must not move the figures for the default."""
    client = make_api_account()
    assert add(client, "1234.567") == "1234.57"


def test_switching_currency_relabels_and_never_converts(make_api_account):
    """There are no exchange rates here. A figure must keep its magnitude."""
    client = make_api_account()
    assert add(client, "1000.00") == "1000.00"
    switch(client, "USD")
    rows = client.get("/api/v1/transactions").get_json()["items"]
    assert next(r["amount"] for r in rows if r["description"] == "probe") == "1000.00"


def test_a_budget_in_a_three_decimal_currency(make_api_account):
    """Not only transactions: every money column was widened."""
    client = make_api_account()
    switch(client, "BHD")
    client.put("/api/v1/budgets", headers=client.headers,
               json={"category_id": a_category(client), "month": "2026-08",
                     "limit": "12.345"})
    assert client.get("/api/v1/budgets").get_json()["items"][0]["limit"] == "12.345"


def test_a_holding_priced_in_a_three_decimal_currency(make_api_account):
    client = make_api_account()
    switch(client, "OMR")
    client.post("/api/v1/investments", headers=client.headers,
                json={"asset_name": "Probe", "asset_type": "Stock",
                      "buy_date": "2026-01-01", "buy_price": "1.111",
                      "quantity": "10", "current_price": "2.222"})
    holding = client.get("/api/v1/investments").get_json()["items"][0]
    assert holding["buy_price"] == "1.111"
    assert holding["current_price"] == "2.222"


def test_the_currency_does_not_leak_between_accounts(make_api_account):
    """The scale is cached on the session, so it must be cleared with it."""
    mine, theirs = make_api_account(), make_api_account()
    switch(mine, "JPY")
    assert theirs.get("/api/v1/settings/currencies").get_json()["current"] == "INR"
    assert theirs.get("/api/v1/auth/session").get_json()["user"]["currency"] == "INR"
