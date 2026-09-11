"""Accounts, balances and transfers.

The arithmetic is what matters here. A balance that is merely plausible is
the failure this whole feature has to avoid, so every figure below is
checked against rows the test itself planted.
"""

from decimal import Decimal


def accounts(client, archived=False):
    """The account list, keyed by name."""
    query = "/api/v1/accounts" + ("?archived=1" if archived else "")
    return {row["name"]: row for row in client.get(query).get_json()["items"]}


def open_account(client, name, kind="Bank", opening=None):
    body = {"name": name, "kind": kind}
    if opening is not None:
        body["opening_balance"] = opening
    return client.post("/api/v1/accounts", headers=client.headers, json=body)


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def add(client, amount, kind="Expense", account_id=None, date="2026-06-05",
        description="row"):
    body = {"date": date, "category_id": a_category(client, kind),
            "amount": amount, "type": kind, "description": description}
    if account_id is not None:
        body["account_id"] = account_id
    return client.post("/api/v1/transactions", headers=client.headers, json=body)


# --- what a new account starts with -----------------------------------------

def test_a_new_user_already_has_an_account(make_api_account):
    """A ledger that cannot take its first row is not a ledger."""
    client = make_api_account()
    assert list(accounts(client)) == ["Main"]


def test_a_new_account_starts_at_its_opening_balance(make_api_account):
    """Not at zero: an account opened with money already in it is the
    ordinary case, and reading it as empty is simply wrong."""
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    savings = accounts(client)["Savings"]
    assert savings["opening_balance"] == "5000.00"
    assert savings["balance"] == "5000.00"
    assert savings["transactions"] == 0


def test_an_account_can_open_owing_money(make_api_account):
    """A credit card starts negative. Refusing that would force people to
    model a card as something it is not."""
    client = make_api_account()
    assert open_account(client, "Card", "Card", "-2500.00").status_code == 201
    assert accounts(client)["Card"]["balance"] == "-2500.00"


def test_two_accounts_cannot_share_a_name(make_api_account):
    client = make_api_account()
    open_account(client, "Savings")
    assert open_account(client, "Savings").status_code == 422


def test_an_unknown_kind_is_refused(make_api_account):
    client = make_api_account()
    assert open_account(client, "Odd", "Cryptocurrency").status_code == 422


# --- balances ----------------------------------------------------------------

def test_a_balance_is_the_opening_plus_income_less_expense(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "1000.00")
    savings = accounts(client)["Savings"]["id"]

    add(client, "500.00", "Income", savings)
    add(client, "200.00", "Expense", savings)

    row = accounts(client)["Savings"]
    assert row["balance"] == "1300.00"
    assert row["transactions"] == 2


def test_each_account_keeps_its_own_balance(make_api_account):
    client = make_api_account()
    open_account(client, "Savings")
    open_account(client, "Wallet", "Cash")
    ids = accounts(client)

    add(client, "900.00", "Income", ids["Savings"]["id"])
    add(client, "100.00", "Expense", ids["Wallet"]["id"])

    after = accounts(client)
    assert after["Savings"]["balance"] == "900.00"
    assert after["Wallet"]["balance"] == "-100.00"
    assert after["Main"]["balance"] == "0.00", "an untouched account must not move"


def test_a_transaction_with_no_account_lands_on_the_default(make_api_account):
    """Every client that predates accounts still writes a valid row."""
    client = make_api_account()
    add(client, "250.00", "Expense")
    assert accounts(client)["Main"]["transactions"] == 1


def test_a_transaction_cannot_be_filed_on_another_account(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    stranger = accounts(theirs)["Main"]["id"]

    assert add(mine, "100.00", "Expense", stranger).status_code == 422
    assert accounts(theirs)["Main"]["transactions"] == 0


# --- editing, archiving, deleting --------------------------------------------

def test_an_account_can_be_renamed_and_recapitalised(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "100.00")
    account_id = accounts(client)["Savings"]["id"]

    client.patch(f"/api/v1/accounts/{account_id}", headers=client.headers,
                 json={"name": "Emergency fund", "kind": "Bank",
                       "opening_balance": "750.00"})
    after = accounts(client)
    assert "Savings" not in after
    assert after["Emergency fund"]["balance"] == "750.00"


def test_an_archived_account_is_hidden_but_not_gone(make_api_account):
    client = make_api_account()
    open_account(client, "Old current account")
    account_id = accounts(client)["Old current account"]["id"]

    client.post(f"/api/v1/accounts/{account_id}/archive", headers=client.headers,
                json={"archived": "1"})
    assert "Old current account" not in accounts(client)
    assert "Old current account" in accounts(client, archived=True)


def test_archiving_can_be_undone(make_api_account):
    client = make_api_account()
    open_account(client, "Reopened")
    account_id = accounts(client)["Reopened"]["id"]
    for state in ("1", "0"):
        client.post(f"/api/v1/accounts/{account_id}/archive", headers=client.headers,
                    json={"archived": state})
    assert "Reopened" in accounts(client)


def test_an_account_holding_transactions_is_not_deleted_silently(make_api_account):
    """The rows are history. Losing them because an account was tidied away
    is the one outcome that cannot be undone."""
    client = make_api_account()
    open_account(client, "Savings")
    account_id = accounts(client)["Savings"]["id"]
    add(client, "400.00", "Expense", account_id)

    refused = client.delete(f"/api/v1/accounts/{account_id}", headers=client.headers)
    assert refused.status_code == 422
    assert accounts(client)["Savings"]["transactions"] == 1


def test_deleting_an_account_can_move_its_transactions(make_api_account):
    client = make_api_account()
    open_account(client, "Savings")
    ids = accounts(client)
    savings, main = ids["Savings"]["id"], ids["Main"]["id"]
    add(client, "400.00", "Expense", savings)

    gone = client.delete(f"/api/v1/accounts/{savings}?reassign_to={main}",
                         headers=client.headers)
    assert gone.status_code == 200

    after = accounts(client)
    assert "Savings" not in after
    assert after["Main"]["transactions"] == 1, "the row moved rather than vanished"
    assert after["Main"]["balance"] == "-400.00"


def test_the_last_account_cannot_be_deleted(make_api_account):
    """An account list with nothing in it is a ledger that cannot be
    written to."""
    client = make_api_account()
    only = accounts(client)["Main"]["id"]
    assert client.delete(f"/api/v1/accounts/{only}",
                         headers=client.headers).status_code == 422


def test_usage_says_what_a_delete_would_move(make_api_account):
    client = make_api_account()
    open_account(client, "Savings")
    account_id = accounts(client)["Savings"]["id"]
    add(client, "10.00", "Expense", account_id)
    add(client, "20.00", "Expense", account_id)

    use = client.get(f"/api/v1/accounts/{account_id}/usage").get_json()
    assert use == {"transactions": 2, "transfers": 0}


# --- transfers ---------------------------------------------------------------

def transfer(client, source, target, amount="1000.00", date="2026-06-10"):
    return client.post("/api/v1/accounts/transfer", headers=client.headers,
                       json={"from_account_id": source, "to_account_id": target,
                             "amount": amount, "date": date,
                             "description": "Moved across"})


def test_a_transfer_moves_the_money_and_nothing_else(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)

    assert transfer(client, ids["Savings"]["id"], ids["Main"]["id"],
                    "1200.00").status_code == 201

    after = accounts(client)
    assert after["Savings"]["balance"] == "3800.00"
    assert after["Main"]["balance"] == "1200.00"
    # The total across every account is what a transfer must not change.
    assert (Decimal(after["Savings"]["balance"]) + Decimal(after["Main"]["balance"])
            == Decimal("5000.00"))


def test_a_transfer_writes_two_rows_that_know_about_each_other(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    group = transfer(client, ids["Savings"]["id"],
                     ids["Main"]["id"]).get_json()["transfer_group"]

    rows = [row for row in
            client.get("/api/v1/transactions").get_json()["items"]
            if row["transfer_group"] == group]
    assert len(rows) == 2
    assert {row["type"] for row in rows} == {"Income", "Expense"}
    assert {row["account"] for row in rows} == {"Savings", "Main"}


def test_a_transfer_to_the_same_account_is_refused(make_api_account):
    """It would say money left an account and arrived in the same one."""
    client = make_api_account()
    main = accounts(client)["Main"]["id"]
    assert transfer(client, main, main).status_code == 422


def test_a_transfer_cannot_reach_another_persons_account(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    assert transfer(mine, accounts(mine)["Main"]["id"],
                    accounts(theirs)["Main"]["id"]).status_code == 422
    assert accounts(theirs)["Main"]["balance"] == "0.00"


def test_deleting_a_transfer_removes_both_legs(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    group = transfer(client, ids["Savings"]["id"],
                     ids["Main"]["id"]).get_json()["transfer_group"]

    assert client.delete(f"/api/v1/transfers/{group}",
                         headers=client.headers).status_code == 200

    after = accounts(client)
    assert after["Savings"]["balance"] == "5000.00"
    assert after["Main"]["balance"] == "0.00"
    assert after["Main"]["transactions"] == 0


def test_another_account_cannot_delete_your_transfer(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    open_account(mine, "Savings", "Bank", "5000.00")
    ids = accounts(mine)
    group = transfer(mine, ids["Savings"]["id"],
                     ids["Main"]["id"]).get_json()["transfer_group"]

    assert theirs.delete(f"/api/v1/transfers/{group}",
                         headers=theirs.headers).status_code == 404
    assert accounts(mine)["Main"]["balance"] == "1000.00"


# --- the reason transfers are excluded from reports --------------------------

def test_a_transfer_is_not_income_and_not_expenditure(make_api_account):
    """Moving 1,000 between your own accounts is not 1,000 earned and 1,000
    spent. The net is zero either way, so cashflow would survive -- but the
    trend would grow two bars out of money that never entered or left."""
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    transfer(client, ids["Savings"]["id"], ids["Main"]["id"], "1000.00",
             date="2026-06-10")

    summary = client.get("/api/v1/reports/summary?months=24").get_json()
    assert summary["trend"] == [], "a transfer must not appear in the trend"
    assert summary["cashflow"] == []
    assert summary["merchants"] == [], "your own savings is not a payee"


def test_a_transfer_does_not_count_against_a_budget(make_api_account):
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    category = a_category(client, "Expense")
    client.put("/api/v1/budgets", headers=client.headers,
               json={"category_id": category, "month": "2026-06", "limit": "500.00"})
    transfer(client, ids["Savings"]["id"], ids["Main"]["id"], "1000.00",
             date="2026-06-10")

    rows = client.get("/api/v1/reports/budget-vs-actual?month=2026-06").get_json()["items"]
    assert all(row["actual"] == "0.00" for row in rows)


def test_ordinary_rows_still_reach_the_reports(make_api_account):
    """The guard against transfers must not quietly exclude everything."""
    client = make_api_account()
    add(client, "700.00", "Expense", date="2026-06-05", description="Rent")
    trend = client.get("/api/v1/reports/trend?months=24").get_json()["items"]
    assert trend and trend[0]["expense"] == "700.00"


def test_every_account_endpoint_needs_a_session(client):
    assert client.get("/api/v1/accounts").status_code == 401
    assert client.post("/api/v1/accounts").status_code in (401, 403)


# --- the system category transfers are filed under ---------------------------

def test_the_transfer_category_is_not_offered_as_a_kind_of_spending(make_api_account):
    """It exists so both legs of a transfer have somewhere to sit. Offering
    it in the pickers invites filing an ordinary expense as a transfer."""
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    transfer(client, ids["Savings"]["id"], ids["Main"]["id"])

    names = [one["name"] for one in
             client.get("/api/v1/categories").get_json()["items"]]
    assert "Transfer" not in names


def test_the_transfer_category_cannot_be_renamed_or_deleted(make_api_account):
    """Renaming it would make it appear as a kind of spending under another
    name; deleting it would strand the legs that point at it."""
    client = make_api_account()
    open_account(client, "Savings", "Bank", "5000.00")
    ids = accounts(client)
    transfer(client, ids["Savings"]["id"], ids["Main"]["id"])

    rows = client.get("/api/v1/transactions").get_json()["items"]
    leg = next(row for row in rows if row["transfer_group"])
    system_id = client.get(f"/api/v1/transactions/{leg['id']}").get_json()["category_id"]

    assert client.patch(f"/api/v1/categories/{system_id}", headers=client.headers,
                        json={"name": "Shopping", "type": "Expense"}).status_code == 404
    assert client.delete(f"/api/v1/categories/{system_id}",
                         headers=client.headers).status_code == 404
