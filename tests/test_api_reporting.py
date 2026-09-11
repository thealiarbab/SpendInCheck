"""The deeper reports: trend, cashflow, net worth, merchants, summary.

These are aggregates, so the tests that matter are the ones that check the
arithmetic against rows the test itself planted. A report that returns
plausible-looking figures nobody has added up is worse than no report.
"""

from decimal import Decimal


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def add(client, date, amount, kind="Expense", description="row"):
    return client.post("/api/v1/transactions", headers=client.headers,
                       json={"date": date, "category_id": a_category(client, kind),
                             "amount": amount, "type": kind,
                             "description": description})


def month_of(rows, month):
    return next((row for row in rows if row["month"] == month), None)


def ledger(client):
    """Two months of known figures, so every total below can be checked."""
    add(client, "2026-06-05", "1000.00", "Income", "june pay")
    add(client, "2026-06-10", "400.00", "Expense", "june rent")
    add(client, "2026-07-05", "2000.00", "Income", "july pay")
    add(client, "2026-07-10", "500.00", "Expense", "july rent")
    add(client, "2026-07-20", "100.00", "Expense", "july rent")


# --- trend ------------------------------------------------------------------

def test_the_trend_separates_income_from_expense(make_api_account):
    client = make_api_account()
    ledger(client)
    rows = client.get("/api/v1/reports/trend?months=24").get_json()["items"]

    june = month_of(rows, "2026-06")
    assert june["income"] == "1000.00"
    assert june["expense"] == "400.00"

    july = month_of(rows, "2026-07")
    assert july["income"] == "2000.00"
    assert july["expense"] == "600.00", "two July expenses must be summed"


def test_the_trend_runs_oldest_first(make_api_account):
    """A chart draws left to right, so the rows must already be in that order."""
    client = make_api_account()
    ledger(client)
    months = [row["month"] for row in
              client.get("/api/v1/reports/trend?months=24").get_json()["items"]]
    assert months == sorted(months)


def test_a_month_with_no_rows_is_absent_rather_than_zero(make_api_account):
    """Filling gaps is the caller's job: a chart wants a continuous axis and
    a table does not, and only the caller knows which it is."""
    client = make_api_account()
    add(client, "2026-06-05", "100.00")
    months = [row["month"] for row in
              client.get("/api/v1/reports/trend?months=24").get_json()["items"]]
    assert months == ["2026-06"]


# --- cashflow ---------------------------------------------------------------

def test_cashflow_nets_each_month_and_accumulates(make_api_account):
    client = make_api_account()
    ledger(client)
    rows = client.get("/api/v1/reports/cashflow?months=24").get_json()["items"]

    june = month_of(rows, "2026-06")
    july = month_of(rows, "2026-07")
    # June: 1000 in, 400 out. July: 2000 in, 600 out.
    assert june["net"] == "600.00"
    assert july["net"] == "1400.00"
    assert june["cumulative"] == "600.00"
    assert july["cumulative"] == "2000.00", "the running total must carry June forward"


def test_a_month_that_spends_more_than_it_earns_goes_negative(make_api_account):
    client = make_api_account()
    add(client, "2026-06-05", "100.00", "Income", "small pay")
    add(client, "2026-06-10", "400.00", "Expense", "big bill")
    june = month_of(client.get("/api/v1/reports/cashflow?months=24").get_json()["items"],
                    "2026-06")
    assert june["net"] == "-300.00"


# --- net worth --------------------------------------------------------------

def test_net_worth_is_holdings_plus_accumulated_cash(make_api_account):
    client = make_api_account()
    add(client, "2026-06-05", "1000.00", "Income", "pay")
    client.post("/api/v1/investments", headers=client.headers,
                json={"asset_name": "Probe", "asset_type": "Stock",
                      "buy_date": "2026-06-01", "buy_price": "100",
                      "quantity": "2", "current_price": "150"})

    rows = client.get("/api/v1/reports/net-worth?months=24").get_json()["items"]
    june = month_of(rows, "2026-06")
    assert june["cash"] == "1000.00"
    assert june["holdings"] == "300.00", "2 units at the current 150, not the 100 paid"
    assert june["net_worth"] == "1300.00"
    assert Decimal(june["net_worth"]) == Decimal(june["cash"]) + Decimal(june["holdings"])


def test_net_worth_cash_counts_what_the_accounts_opened_with(make_api_account):
    """The two screens have to agree, and they did not.

    Net worth summed transactions only, so an account opened with money
    already in it showed that money on the Accounts screen and none of it
    here. Anybody reconciling the two found a gap exactly the size of every
    opening balance they had ever entered -- and the Accounts screen was the
    one telling the truth.
    """
    client = make_api_account()
    client.post("/api/v1/accounts", headers=client.headers,
                json={"name": "Savings", "kind": "Bank",
                      "opening_balance": "50000.00"})
    add(client, "2026-06-05", "1000.00", "Income", "pay")

    across = sum(Decimal(one["balance"])
                 for one in client.get("/api/v1/accounts").get_json()["items"])
    assert across == Decimal("51000.00")

    rows = client.get("/api/v1/reports/net-worth?months=24").get_json()["items"]
    assert Decimal(month_of(rows, "2026-06")["cash"]) == across


def test_a_holding_is_not_counted_before_it_was_bought(make_api_account):
    client = make_api_account()
    client.post("/api/v1/investments", headers=client.headers,
                json={"asset_name": "Probe", "asset_type": "Stock",
                      "buy_date": "2026-07-01", "buy_price": "100",
                      "quantity": "2", "current_price": "150"})
    add(client, "2026-06-05", "10.00", "Income", "pay")

    rows = client.get("/api/v1/reports/net-worth?months=24").get_json()["items"]
    assert month_of(rows, "2026-06")["holdings"] == "0.00"
    assert month_of(rows, "2026-07")["holdings"] == "300.00"


def test_net_worth_covers_every_month_including_empty_ones(make_api_account):
    """Unlike the trend, this series is generated from a calendar, because a
    net worth of nothing is still a fact about that month."""
    client = make_api_account()
    rows = client.get("/api/v1/reports/net-worth?months=6").get_json()["items"]
    assert len(rows) == 6
    assert [row["month"] for row in rows] == sorted(row["month"] for row in rows)


# --- merchants --------------------------------------------------------------

def test_merchants_group_by_description_and_count(make_api_account):
    client = make_api_account()
    add(client, "2026-08-01", "100.00", "Expense", "Corner Shop")
    add(client, "2026-08-02", "150.00", "Expense", "corner shop")
    add(client, "2026-08-03", "900.00", "Expense", "Landlord")

    rows = client.get("/api/v1/reports/summary").get_json()["merchants"]
    by_payee = {row["payee"]: row for row in rows}
    assert by_payee["corner shop"]["times"] == 2, "case must not split a payee"
    assert by_payee["corner shop"]["total"] == "250.00"
    assert rows[0]["payee"] == "landlord", "biggest total first"


def test_income_is_not_a_merchant(make_api_account):
    client = make_api_account()
    add(client, "2026-08-01", "5000.00", "Income", "salary")
    rows = client.get("/api/v1/reports/summary").get_json()["merchants"]
    assert all(row["payee"] != "salary" for row in rows)


def test_a_blank_description_is_not_a_merchant(make_api_account):
    """It would usually be the largest bar on the chart and say nothing."""
    client = make_api_account()
    add(client, "2026-08-01", "9999.00", "Expense", "")
    rows = client.get("/api/v1/reports/summary").get_json()["merchants"]
    assert all(row["payee"].strip() for row in rows)


# --- the summary ------------------------------------------------------------

def test_the_summary_carries_every_series(make_api_account):
    body = make_api_account().get("/api/v1/reports/summary").get_json()
    assert set(body) == {"this_month", "trend", "cashflow", "net_worth",
                         "merchants", "spend_by_category"}
    assert set(body["this_month"]) == {"income", "expense", "net", "transactions"}


def test_the_summary_agrees_with_the_endpoints_it_replaces(make_api_account):
    """It exists to save round trips, not to answer differently."""
    client = make_api_account()
    ledger(client)
    summary = client.get("/api/v1/reports/summary?months=24").get_json()

    assert summary["trend"] == client.get(
        "/api/v1/reports/trend?months=24").get_json()["items"]
    assert summary["cashflow"] == client.get(
        "/api/v1/reports/cashflow?months=24").get_json()["items"]
    assert summary["net_worth"] == client.get(
        "/api/v1/reports/net-worth?months=24").get_json()["items"]


def test_this_month_counts_only_this_month(make_api_account):
    """Dated in the past, so it must not appear in the current month's figures."""
    client = make_api_account()
    ledger(client)
    this_month = client.get("/api/v1/reports/summary").get_json()["this_month"]
    assert this_month["income"] == "0.00"
    assert this_month["expense"] == "0.00"
    assert this_month["transactions"] == 0


def test_the_month_range_is_clamped_rather_than_refused(make_api_account):
    """This only decides how much history a chart shows, and a chart is a
    poor place to answer a typo with an error message."""
    client = make_api_account()
    for query in ("?months=0", "?months=9999", "?months=abc", "?months=-4"):
        response = client.get("/api/v1/reports/net-worth" + query)
        assert response.status_code == 200, query
        assert 1 <= len(response.get_json()["items"]) <= 60, query


def test_every_report_needs_a_session(client):
    for path in ("/api/v1/reports/summary", "/api/v1/reports/trend",
                 "/api/v1/reports/cashflow", "/api/v1/reports/net-worth"):
        assert client.get(path).status_code == 401, path


def test_reports_cannot_see_another_account(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    ledger(theirs)
    assert mine.get("/api/v1/reports/trend?months=24").get_json()["items"] == []
    assert mine.get("/api/v1/reports/summary").get_json()["merchants"] == []
