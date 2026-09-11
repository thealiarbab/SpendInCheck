"""Budget rollover: what is left over (or overspent) carries into next month.

rollover_in is a stored derived value, which is the one thing this project
otherwise refuses to do -- balances and goal totals are both summed on
read. It is stored here because deriving it means walking back through
every month a category has ever been budgeted for, on every report.

That makes "the stored figure equals what it would be if recomputed from
scratch" the property worth testing hardest, and the last test in this file
does exactly that.
"""

from decimal import Decimal

from server import operations


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def budget(client, month, limit, rollover=True, category_id=None):
    body = {"category_id": category_id or a_category(client),
            "month": month, "limit": limit}
    if rollover:
        body["rollover"] = "1"
    return client.put("/api/v1/budgets", headers=client.headers, json=body)


def spend(client, date, amount, category_id=None):
    return client.post("/api/v1/transactions", headers=client.headers,
                       json={"date": date, "category_id": category_id or a_category(client),
                             "amount": amount, "type": "Expense",
                             "description": "spending"})


def report(client, month):
    rows = client.get(f"/api/v1/reports/budget-vs-actual?month={month}").get_json()
    return {row["category"]: row for row in rows["items"]}


def only(client, month):
    """The one budgeted category's row for that month."""
    return next(iter(report(client, month).values()))


# --- carrying forward --------------------------------------------------------

def test_the_first_budgeted_month_carries_nothing_in(make_api_account):
    """There is nothing behind it to carry."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    assert only(client, "2026-06")["rollover_in"] == "0.00"


def test_an_underspent_month_widens_the_next(make_api_account):
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00")
    spend(client, "2026-06-10", "3000.00")

    july = only(client, "2026-07")
    assert july["rollover_in"] == "2000.00", "the 2,000 unspent in June"
    # Nothing spent in July yet, so the whole allowance is left.
    assert july["difference"] == "7000.00"


def test_an_overspent_month_narrows_the_next(make_api_account):
    """The other half of the bargain. A rollover that only ever gave money
    back would be a reward for overspending."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00")
    spend(client, "2026-06-10", "8000.00")

    july = only(client, "2026-07")
    assert july["rollover_in"] == "-3000.00"
    assert july["difference"] == "2000.00"


def test_it_compounds_across_three_months(make_api_account):
    client = make_api_account()
    for month in ("2026-06", "2026-07", "2026-08"):
        budget(client, month, "5000.00")
    spend(client, "2026-06-10", "3000.00")   # 2,000 left
    spend(client, "2026-07-10", "4000.00")   # 5,000 + 2,000 - 4,000 = 3,000 left

    assert only(client, "2026-07")["rollover_in"] == "2000.00"
    assert only(client, "2026-08")["rollover_in"] == "3000.00"


def test_rollover_off_carries_nothing_and_passes_nothing_on(make_api_account):
    """Turning it off is a line under the past, not a pause."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00", rollover=False)
    budget(client, "2026-08", "5000.00")
    spend(client, "2026-06-10", "1000.00")   # 4,000 would have carried

    assert only(client, "2026-07")["rollover_in"] == "0.00"
    # August follows a month that carried nothing in and spent nothing, so
    # it inherits that month's whole limit and no more.
    assert only(client, "2026-08")["rollover_in"] == "5000.00"


def test_a_month_with_no_budget_is_not_a_gap_in_the_chain(make_api_account):
    """The chain runs over budgeted months, not over the calendar. A
    category nobody budgeted in July does not reset August."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-08", "5000.00")
    spend(client, "2026-06-10", "1000.00")

    assert only(client, "2026-08")["rollover_in"] == "4000.00"


# --- staying honest after a write --------------------------------------------

def test_adding_a_transaction_moves_the_next_month(make_api_account):
    """The stored figure has to follow every write that changes what it was
    derived from."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00")
    assert only(client, "2026-07")["rollover_in"] == "5000.00"

    spend(client, "2026-06-10", "1500.00")
    assert only(client, "2026-07")["rollover_in"] == "3500.00"


def test_deleting_a_transaction_moves_it_back(make_api_account):
    client = make_api_account()
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00")
    spend(client, "2026-06-10", "1500.00")

    row = client.get("/api/v1/transactions").get_json()["items"][0]
    client.delete(f"/api/v1/transactions/{row['id']}", headers=client.headers)
    assert only(client, "2026-07")["rollover_in"] == "5000.00"


def test_moving_a_transaction_out_of_a_category_updates_both(make_api_account):
    """A row leaving Groceries changes what Groceries carried forward just
    as much as it changes where it landed."""
    client = make_api_account()
    categories = client.get("/api/v1/categories").get_json()["items"]
    first, second = [one["id"] for one in categories if one["type"] == "Expense"][:2]

    for category in (first, second):
        budget(client, "2026-06", "5000.00", category_id=category)
        budget(client, "2026-07", "5000.00", category_id=category)
    spend(client, "2026-06-10", "2000.00", category_id=first)

    names = {one["id"]: one["name"] for one in categories}
    july = report(client, "2026-07")
    assert july[names[first]]["rollover_in"] == "3000.00"
    assert july[names[second]]["rollover_in"] == "5000.00"

    row = client.get("/api/v1/transactions").get_json()["items"][0]
    client.patch(f"/api/v1/transactions/{row['id']}", headers=client.headers,
                 json={"date": "2026-06-10", "category_id": second,
                       "amount": "2000.00", "type": "Expense",
                       "description": "spending"})

    july = report(client, "2026-07")
    assert july[names[first]]["rollover_in"] == "5000.00", "the row left"
    assert july[names[second]]["rollover_in"] == "3000.00", "and arrived"


def test_changing_a_limit_moves_every_month_after_it(make_api_account):
    client = make_api_account()
    for month in ("2026-06", "2026-07", "2026-08"):
        budget(client, month, "5000.00")
    spend(client, "2026-06-10", "1000.00")
    assert only(client, "2026-08")["rollover_in"] == "9000.00"

    budget(client, "2026-06", "3000.00")
    assert only(client, "2026-07")["rollover_in"] == "2000.00"
    assert only(client, "2026-08")["rollover_in"] == "7000.00"


def test_a_transfer_does_not_eat_a_budget(make_api_account):
    """Transfers are excluded from the spend behind rollover, exactly as
    they are from every other report."""
    client = make_api_account()
    client.post("/api/v1/accounts", headers=client.headers,
                json={"name": "Savings", "kind": "Bank"})
    accounts = {one["name"]: one["id"] for one in
                client.get("/api/v1/accounts").get_json()["items"]}
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "5000.00")
    client.post("/api/v1/accounts/transfer", headers=client.headers,
                json={"from_account_id": accounts["Main"],
                      "to_account_id": accounts["Savings"],
                      "amount": "4000.00", "date": "2026-06-10"})

    assert only(client, "2026-07")["rollover_in"] == "5000.00"


# --- the property that makes storing it safe ---------------------------------

def test_the_stored_figure_equals_a_recompute_from_scratch(make_api_account,
                                                           api_user_id):
    """The whole justification for materialising it.

    Several writes in a deliberately awkward order -- a later month budgeted
    before an earlier one, spending added after the budgets, a limit changed
    afterwards -- then the figures are rebuilt from the budgets and
    transactions alone and compared with what is stored.
    """
    client = make_api_account()
    user_id = api_user_id(client)
    category = a_category(client)

    budget(client, "2026-08", "4000.00")
    budget(client, "2026-06", "5000.00")
    budget(client, "2026-07", "6000.00")
    spend(client, "2026-06-10", "3000.00")
    spend(client, "2026-07-10", "9000.00")
    spend(client, "2026-08-10", "500.00")
    budget(client, "2026-07", "7000.00")

    before = {month: only(client, month)["rollover_in"]
              for month in ("2026-06", "2026-07", "2026-08")}

    # Rebuild every figure from the underlying rows.
    operations.refresh_rollover(user_id, category)

    after = {month: only(client, month)["rollover_in"]
             for month in ("2026-06", "2026-07", "2026-08")}
    assert before == after

    # And check the arithmetic by hand, so a recompute that is consistently
    # wrong cannot pass by agreeing with itself.
    #   June:  carries in 0,    limit 5,000, spent 3,000 -> 2,000 out
    #   July:  carries in 2,000, limit 7,000, spent 9,000 -> 0 out
    #   Aug:   carries in 0
    assert after == {"2026-06": "0.00", "2026-07": "2000.00", "2026-08": "0.00"}
    assert Decimal(after["2026-07"]) == Decimal("5000.00") - Decimal("3000.00")


def test_rollover_is_off_unless_asked_for(make_api_account):
    """It changes what a limit means, so it cannot be the default."""
    client = make_api_account()
    budget(client, "2026-06", "5000.00", rollover=False)
    budget(client, "2026-07", "5000.00", rollover=False)
    assert only(client, "2026-06")["rollover"] is False
    assert only(client, "2026-07")["rollover_in"] == "0.00"
