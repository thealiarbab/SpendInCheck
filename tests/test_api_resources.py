"""Tests for the category, transaction, budget, investment and report endpoints.

Every test signs in as a real account against the real database. The property
that matters most here is not that a route returns 200 -- it is that one
account can never see or touch another's rows, and that only shows up when
two accounts genuinely exist.
"""

import pytest


def categories_of(client):
    """The signed-in account's categories."""
    return client.get("/api/v1/categories").get_json()["items"]


def add_transaction(client, category_id, **overrides):
    """Post a valid transaction, letting a test override any single field."""
    body = {"date": "2026-08-01", "category_id": category_id, "amount": "1000.00",
            "type": "Expense", "description": "test row"}
    body.update(overrides)
    return client.post("/api/v1/transactions", headers=client.headers, json=body)


# --- everything needs a session ---------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/v1/categories", "/api/v1/transactions", "/api/v1/budgets",
    "/api/v1/investments", "/api/v1/reports/portfolio",
])
def test_every_resource_requires_signing_in(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "not_signed_in"


# --- categories -------------------------------------------------------------

def test_a_new_account_starts_with_usable_categories(make_api_account):
    """Empty dropdowns on a first sign-in would make the app look broken."""
    items = categories_of(make_api_account())
    assert len(items) >= 8
    assert {item["type"] for item in items} == {"Income", "Expense"}


def test_adding_a_category(make_api_account):
    client = make_api_account()
    before = len(categories_of(client))
    response = client.post("/api/v1/categories", headers=client.headers,
                           json={"name": "Books", "type": "Expense"})
    assert response.status_code == 201
    assert len(categories_of(client)) == before + 1


def test_a_duplicate_category_name_is_reported_on_the_field(make_api_account):
    client = make_api_account()
    client.post("/api/v1/categories", headers=client.headers,
                json={"name": "Books", "type": "Expense"})
    response = client.post("/api/v1/categories", headers=client.headers,
                           json={"name": "Books", "type": "Expense"})
    assert response.status_code == 422
    assert "name" in response.get_json()["error"]["fields"]


def test_two_accounts_may_use_the_same_category_name(make_api_account):
    """Uniqueness is per account, not global."""
    for client in (make_api_account(), make_api_account()):
        assert client.post("/api/v1/categories", headers=client.headers,
                           json={"name": "Books", "type": "Expense"}).status_code == 201


def test_an_unknown_category_type_is_refused(make_api_account):
    client = make_api_account()
    response = client.post("/api/v1/categories", headers=client.headers,
                           json={"name": "Books", "type": "Liability"})
    assert response.status_code == 422
    assert "type" in response.get_json()["error"]["fields"]


# --- transactions -----------------------------------------------------------

def test_a_transaction_round_trips(make_api_account):
    client = make_api_account()
    category = categories_of(client)[0]
    assert add_transaction(client, category["id"], type=category["type"],
                           amount="1234.56").status_code == 201

    items = client.get("/api/v1/transactions").get_json()["items"]
    assert len(items) == 1
    # Money is a string the whole way out, never a float that has been rounded.
    assert items[0]["amount"] == "1234.56"
    assert items[0]["category"] == category["name"]


def test_the_single_record_carries_the_category_id(make_api_account):
    """A table shows the name; an edit form needs the id to preselect."""
    client = make_api_account()
    category = categories_of(client)[0]
    add_transaction(client, category["id"], type=category["type"])
    transaction_id = client.get("/api/v1/transactions").get_json()["items"][0]["id"]

    record = client.get("/api/v1/transactions/" + str(transaction_id)).get_json()
    assert record["category_id"] == category["id"]


@pytest.mark.parametrize("field,value", [
    ("date", "2099-01-01"),
    ("amount", "0"),
    ("amount", "-5"),
    ("amount", "not a number"),
    ("type", "Transfer"),
])
def test_bad_fields_are_reported_against_themselves(make_api_account, field, value):
    client = make_api_account()
    response = add_transaction(client, categories_of(client)[0]["id"], **{field: value})
    assert response.status_code == 422
    assert field in response.get_json()["error"]["fields"]


def test_editing_and_deleting(make_api_account):
    client = make_api_account()
    category = categories_of(client)[0]
    add_transaction(client, category["id"], type=category["type"])
    transaction_id = client.get("/api/v1/transactions").get_json()["items"][0]["id"]

    edited = client.patch("/api/v1/transactions/" + str(transaction_id),
                          headers=client.headers,
                          json={"date": "2026-08-02", "category_id": category["id"],
                                "amount": "77.00", "type": category["type"],
                                "description": "edited"})
    assert edited.status_code == 200
    assert client.get("/api/v1/transactions").get_json()["items"][0]["amount"] == "77.00"

    assert client.delete("/api/v1/transactions/" + str(transaction_id),
                         headers=client.headers).status_code == 200
    assert client.get("/api/v1/transactions").get_json()["items"] == []


def test_deleting_the_same_row_twice_is_not_found(make_api_account):
    client = make_api_account()
    category = categories_of(client)[0]
    add_transaction(client, category["id"], type=category["type"])
    transaction_id = client.get("/api/v1/transactions").get_json()["items"][0]["id"]
    client.delete("/api/v1/transactions/" + str(transaction_id), headers=client.headers)
    assert client.delete("/api/v1/transactions/" + str(transaction_id),
                         headers=client.headers).status_code == 404


# --- one account must never reach another's rows ----------------------------

def test_another_accounts_transaction_is_simply_not_found(make_api_account):
    """404, not 403. Telling them apart would confirm the row exists."""
    owner, stranger = make_api_account(), make_api_account()
    category = categories_of(owner)[0]
    add_transaction(owner, category["id"], type=category["type"])
    transaction_id = owner.get("/api/v1/transactions").get_json()["items"][0]["id"]

    assert stranger.get("/api/v1/transactions/" + str(transaction_id)).status_code == 404
    assert stranger.delete("/api/v1/transactions/" + str(transaction_id),
                           headers=stranger.headers).status_code == 404
    assert len(owner.get("/api/v1/transactions").get_json()["items"]) == 1


def test_a_transaction_cannot_be_filed_under_another_accounts_category(make_api_account):
    owner, stranger = make_api_account(), make_api_account()
    foreign_category = categories_of(owner)[0]["id"]

    response = add_transaction(stranger, foreign_category)
    assert response.status_code == 422
    assert "category_id" in response.get_json()["error"]["fields"]
    assert owner.get("/api/v1/transactions").get_json()["items"] == []


def test_a_budget_cannot_be_set_on_another_accounts_category(make_api_account):
    owner, stranger = make_api_account(), make_api_account()
    response = stranger.put("/api/v1/budgets", headers=stranger.headers,
                            json={"category_id": categories_of(owner)[0]["id"],
                                  "month": "2026-08", "limit": "500"})
    assert response.status_code == 422
    assert owner.get("/api/v1/budgets").get_json()["items"] == []


def test_another_accounts_holding_cannot_be_repriced(make_api_account):
    owner, stranger = make_api_account(), make_api_account()
    owner.post("/api/v1/investments", headers=owner.headers,
               json={"asset_name": "Probe", "asset_type": "Stock",
                     "buy_date": "2026-01-01", "buy_price": "100",
                     "quantity": "10", "current_price": "150"})
    holding = owner.get("/api/v1/investments").get_json()["items"][0]["id"]

    assert stranger.patch("/api/v1/investments/" + str(holding) + "/price",
                          headers=stranger.headers,
                          json={"current_price": "1"}).status_code == 404
    assert owner.get("/api/v1/investments").get_json()["items"][0]["current_price"] == "150.00"


# --- budgets ----------------------------------------------------------------

def test_setting_a_budget_twice_replaces_it(make_api_account):
    """PUT, so the same body sent twice leaves one row rather than two."""
    client = make_api_account()
    category = categories_of(client)[0]["id"]
    for limit in ("5000", "6000"):
        assert client.put("/api/v1/budgets", headers=client.headers,
                          json={"category_id": category, "month": "2026-08",
                                "limit": limit}).status_code == 200

    items = client.get("/api/v1/budgets").get_json()["items"]
    assert len(items) == 1
    assert items[0]["limit"] == "6000.00"


@pytest.mark.parametrize("month", ["2026-8", "2026", "august", "2026-13"])
def test_a_malformed_month_is_refused(make_api_account, month):
    """The unpadded one is the dangerous case: it parses, then never matches."""
    client = make_api_account()
    response = client.put("/api/v1/budgets", headers=client.headers,
                          json={"category_id": categories_of(client)[0]["id"],
                                "month": month, "limit": "100"})
    assert response.status_code == 422
    assert "month" in response.get_json()["error"]["fields"]


# --- investments ------------------------------------------------------------

def test_a_holding_without_a_current_price_is_worth_what_it_cost(make_api_account):
    client = make_api_account()
    response = client.post("/api/v1/investments", headers=client.headers,
                           json={"asset_name": "Fixed Deposit", "asset_type": "FD",
                                 "buy_date": "2026-01-01", "buy_price": "100000",
                                 "quantity": "1"})
    assert response.status_code == 201
    holding = client.get("/api/v1/investments").get_json()["items"][0]
    assert holding["current_price"] == holding["buy_price"] == "100000.00"


def test_repricing_a_holding(make_api_account):
    client = make_api_account()
    client.post("/api/v1/investments", headers=client.headers,
                json={"asset_name": "Probe", "asset_type": "Stock",
                      "buy_date": "2026-01-01", "buy_price": "100",
                      "quantity": "10", "current_price": "150"})
    holding = client.get("/api/v1/investments").get_json()["items"][0]["id"]
    assert client.patch("/api/v1/investments/" + str(holding) + "/price",
                        headers=client.headers,
                        json={"current_price": "200"}).status_code == 200
    assert client.get("/api/v1/investments").get_json()["items"][0]["current_price"] == "200.00"


# --- reports ----------------------------------------------------------------

def test_the_portfolio_totals_match_the_rows(make_api_account):
    """Totals are summed from the rows, so they have to agree with them."""
    client = make_api_account()
    for price, quantity in (("150", "10"), ("50", "4")):
        client.post("/api/v1/investments", headers=client.headers,
                    json={"asset_name": "Probe " + price, "asset_type": "Stock",
                          "buy_date": "2026-01-01", "buy_price": "100",
                          "quantity": quantity, "current_price": price})

    body = client.get("/api/v1/reports/portfolio").get_json()
    # (150-100)*10 = +500 and (50-100)*4 = -200, so +300 on 1500 + 200 = 1700.
    assert body["totals"]["pnl"] == "300.00"
    assert body["totals"]["value"] == "1700.00"
    assert body["totals"]["holdings"] == 2
    # Ordered best first, which is what the report promises.
    assert body["items"][0]["pnl"] == "500.00"


def test_an_empty_portfolio_totals_zero_rather_than_failing(make_api_account):
    body = make_api_account().get("/api/v1/reports/portfolio").get_json()
    assert body["items"] == []
    assert body["totals"] == {"value": "0.00", "pnl": "0.00", "holdings": 0}


def test_category_spend_sums_one_month(make_api_account):
    client = make_api_account()
    expense = next(c for c in categories_of(client) if c["type"] == "Expense")
    for amount in ("100.50", "200.25"):
        add_transaction(client, expense["id"], amount=amount, type="Expense")
    # A different month must not be counted.
    add_transaction(client, expense["id"], amount="999", type="Expense",
                    date="2026-07-01")

    items = client.get("/api/v1/reports/category-spend?month=2026-08").get_json()["items"]
    assert len(items) == 1
    assert items[0]["total"] == "300.75"


def test_budget_vs_actual_reports_the_difference(make_api_account):
    client = make_api_account()
    expense = next(c for c in categories_of(client) if c["type"] == "Expense")
    client.put("/api/v1/budgets", headers=client.headers,
               json={"category_id": expense["id"], "month": "2026-08", "limit": "1000"})
    add_transaction(client, expense["id"], amount="1250.00", type="Expense")

    row = client.get("/api/v1/reports/budget-vs-actual?month=2026-08").get_json()["items"][0]
    assert row["limit"] == "1000.00"
    assert row["actual"] == "1250.00"
    # Negative means over budget, which is the point of the report.
    assert row["difference"] == "-250.00"


def test_a_report_without_a_month_says_which_field_is_missing(make_api_account):
    response = make_api_account().get("/api/v1/reports/category-spend")
    assert response.status_code == 422
    assert "month" in response.get_json()["error"]["fields"]
