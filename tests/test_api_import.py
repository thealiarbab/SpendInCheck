"""Importing a CSV.

This is the feature that can create hundreds of wrong rows from one click,
so most of these tests are about what it refuses, what it skips, and what
it reports before writing anything at all.
"""


def a_category(client, name=None, kind="Expense"):
    items = client.get("/api/v1/categories").get_json()["items"]
    if name:
        return next(one["id"] for one in items if one["name"] == name)
    return next(one["id"] for one in items if one["type"] == kind)


def examine(client, text, **extra):
    return client.post("/api/v1/import/examine", headers=client.headers,
                       json={"text": text, **extra})


def commit(client, rows, **extra):
    return client.post("/api/v1/import/commit", headers=client.headers,
                       json={"rows": rows, **extra})


def ledger(client):
    return client.get("/api/v1/transactions?per_page=200").get_json()["items"]


def usable(body):
    return [row for row in body["rows"] if "skip" not in row]


# --- reading a file ----------------------------------------------------------

def test_a_plain_file_is_read(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Description,Amount,Category\n"
                           "2026-06-01,Weekly shop,1200.00,Groceries\n").get_json()
    assert body["summary"] == {"readable": 1, "skipped": 0}
    row = usable(body)[0]
    assert row["date"] == "2026-06-01"
    assert row["amount"] == "1200.00"
    assert row["description"] == "Weekly shop"


def test_examining_writes_nothing(make_api_account):
    """The whole reason there are two endpoints."""
    client = make_api_account()
    examine(client, "Date,Amount,Category\n2026-06-01,1200.00,Groceries\n")
    assert ledger(client) == []


def test_column_names_are_matched_not_demanded(make_api_account):
    """Every bank names them differently and none of them asks first."""
    client = make_api_account()
    body = examine(client, "Value Date,Narration,Withdrawal,Category\n"
                           "01/06/2026,Rent paid,15000.00,Rent\n").get_json()
    assert body["summary"]["readable"] == 1
    assert usable(body)[0]["type"] == "Expense"


def test_columns_it_does_not_understand_are_ignored(make_api_account):
    """A statement carries balances and reference numbers. Refusing the file
    over them would refuse every real file."""
    client = make_api_account()
    body = examine(client, "Date,Chq No,Description,Amount,Balance,Category\n"
                           "2026-06-01,000123,Shop,500.00,42000.00,Groceries\n"
                           ).get_json()
    assert body["summary"]["readable"] == 1


def test_a_semicolon_file_is_read(make_api_account):
    client = make_api_account()
    body = examine(client, "Date;Description;Amount;Category\n"
                           "2026-06-01;Shop;500.00;Groceries\n").get_json()
    assert body["summary"]["readable"] == 1


def test_several_date_formats_are_understood(make_api_account):
    client = make_api_account()
    text = ("Date,Amount,Category\n"
            "2026-06-01,100.00,Groceries\n"
            "02/06/2026,100.00,Groceries\n"
            "03-Jun-2026,100.00,Groceries\n")
    body = examine(client, text).get_json()
    assert [row["date"] for row in usable(body)] == \
        ["2026-06-01", "2026-06-02", "2026-06-03"]


def test_amounts_survive_what_banks_put_around_them(make_api_account):
    client = make_api_account()
    text = ("Date,Amount,Type,Category\n"
            "2026-06-01,\"1,200.50\",Expense,Groceries\n"
            "2026-06-02,₹900.00,Expense,Groceries\n"
            "2026-06-03,(450.00),Expense,Groceries\n")
    body = examine(client, text).get_json()
    assert [row["amount"] for row in usable(body)] == \
        ["1200.50", "900.00", "450.00"]


def test_debit_and_credit_columns_decide_the_direction(make_api_account):
    """More reliable than any sign convention."""
    client = make_api_account()
    text = ("Date,Description,Debit,Credit,Category\n"
            "2026-06-01,Shop,1200.00,,Groceries\n"
            "2026-06-02,Pay,,55000.00,Salary\n")
    body = examine(client, text).get_json()
    assert [row["type"] for row in usable(body)] == ["Expense", "Income"]


def test_a_bracketed_amount_is_money_out(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-01,(450.00),Groceries\n").get_json()
    assert usable(body)[0]["type"] == "Expense"


def test_the_category_decides_the_direction(make_api_account):
    """A file claiming an Expense under Salary disagrees with itself, and
    the category is what every other screen believes."""
    client = make_api_account()
    body = examine(client, "Date,Amount,Type,Category\n"
                           "2026-06-01,55000.00,Expense,Salary\n").get_json()
    assert usable(body)[0]["type"] == "Income"


# --- what it refuses and what it skips ---------------------------------------

def test_a_file_with_no_date_column_is_refused_whole(make_api_account):
    client = make_api_account()
    body = examine(client, "Description,Amount\nShop,500.00\n").get_json()
    assert body["rows"] == []
    assert any("date" in problem.lower() for problem in body["problems"])


def test_a_file_with_no_amount_column_is_refused_whole(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Description\n2026-06-01,Shop\n").get_json()
    assert any("amount" in problem.lower() for problem in body["problems"])


def test_an_empty_file_is_refused(make_api_account):
    client = make_api_account()
    assert examine(client, "   ").status_code == 422


def test_a_bad_row_is_skipped_and_says_why(make_api_account):
    """The reader has to see the four rows that will not import before
    deciding, not afterwards."""
    client = make_api_account()
    text = ("Date,Amount,Category\n"
            "2026-06-01,500.00,Groceries\n"
            "not a date,500.00,Groceries\n"
            "2026-06-03,not a number,Groceries\n")
    body = examine(client, text).get_json()
    assert body["summary"] == {"readable": 1, "skipped": 2}
    skipped = [row for row in body["rows"] if "skip" in row]
    assert all(row["skip"] for row in skipped)
    assert [row["line"] for row in skipped] == [3, 4], "line numbers, for finding them"


def test_an_unknown_category_is_skipped_unless_a_fallback_is_given(make_api_account):
    client = make_api_account()
    text = "Date,Amount,Category\n2026-06-01,500.00,Fireworks\n"

    body = examine(client, text).get_json()
    assert body["summary"]["skipped"] == 1

    with_fallback = examine(client, text,
                            default_category_id=a_category(client)).get_json()
    assert with_fallback["summary"]["readable"] == 1


def test_blank_lines_are_not_rows(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-01,500.00,Groceries\n"
                           "\n"
                           ",,\n").get_json()
    assert len(body["rows"]) == 1


def test_a_fallback_from_another_account_is_refused(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    assert examine(mine, "Date,Amount\n2026-06-01,500.00\n",
                   default_category_id=a_category(theirs)).status_code == 422


# --- writing ------------------------------------------------------------------

def test_committing_writes_what_was_examined(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Description,Amount,Category\n"
                           "2026-06-01,Weekly shop,1200.00,Groceries\n"
                           "2026-06-02,Rent,15000.00,Rent\n").get_json()

    response = commit(client, usable(body))
    assert response.status_code == 201
    assert response.get_json()["written"] == 2

    rows = ledger(client)
    assert sorted(row["description"] for row in rows) == ["Rent", "Weekly shop"]


def test_skipped_rows_are_not_written(make_api_account):
    client = make_api_account()
    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-01,500.00,Groceries\n"
                           "not a date,500.00,Groceries\n").get_json()
    # The whole examined set is sent back, skips included, as a careless
    # client would.
    assert commit(client, body["rows"]).get_json()["written"] == 1


def test_rows_can_be_filed_on_an_account(make_api_account):
    client = make_api_account()
    account = client.get("/api/v1/accounts").get_json()["items"][0]["id"]
    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-01,500.00,Groceries\n").get_json()
    commit(client, usable(body), account_id=account)
    assert ledger(client)[0]["account"] == "Main"


def test_a_category_from_another_account_is_never_written(make_api_account):
    """The examined rows came back through the browser, so what returns is
    not necessarily what was sent."""
    mine, theirs = make_api_account(), make_api_account()
    body = examine(mine, "Date,Amount,Category\n"
                         "2026-06-01,500.00,Groceries\n").get_json()
    tampered = usable(body)
    tampered[0]["category_id"] = a_category(theirs)

    assert commit(mine, tampered).get_json()["written"] == 0
    assert ledger(mine) == []


def test_an_empty_commit_is_refused(make_api_account):
    client = make_api_account()
    assert commit(client, []).status_code == 422


def test_a_row_without_a_type_is_refused(make_api_account):
    client = make_api_account()
    assert commit(client, [{"date": "2026-06-01", "amount": "10.00",
                            "category_id": a_category(client)}]).status_code == 422


def test_import_updates_rollover(make_api_account):
    """An import of three hundred rows moves every carried-in figure it
    touches, so the stored value has to follow it."""
    client = make_api_account()
    groceries = a_category(client, "Groceries")
    for month in ("2026-06", "2026-07"):
        client.put("/api/v1/budgets", headers=client.headers,
                   json={"category_id": groceries, "month": month,
                         "limit": "5000.00", "rollover": "1"})

    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-10,2000.00,Groceries\n").get_json()
    commit(client, usable(body))

    july = client.get("/api/v1/reports/budget-vs-actual?month=2026-07").get_json()
    assert july["items"][0]["rollover_in"] == "3000.00"


def test_both_import_endpoints_need_a_session(client):
    assert client.post("/api/v1/import/examine").status_code in (401, 403)
    assert client.post("/api/v1/import/commit").status_code in (401, 403)


def test_rows_with_no_account_chosen_land_on_the_default(make_api_account):
    """Otherwise they belong to no account and appear in no balance: money
    in the ledger that none of the accounts can see."""
    client = make_api_account()
    body = examine(client, "Date,Amount,Category\n"
                           "2026-06-01,500.00,Groceries\n").get_json()
    commit(client, usable(body))

    assert ledger(client)[0]["account"] == "Main"
    balances = {one["name"]: one["balance"] for one in
                client.get("/api/v1/accounts").get_json()["items"]}
    assert balances["Main"] == "-500.00", "and it moves the balance"
