"""Renaming and deleting categories, and what happens to what points at them.

Deleting a category is the only destructive operation in the app that can
silently take other rows with it. Transactions and budgets both reference
categories, so the interesting cases are not the happy path but the ones
where the database would otherwise refuse, or worse, quietly accept
something wrong: merging two months' budgets into one row, and moving
expense rows under an income category.
"""


def categories_of(client):
    return client.get("/api/v1/categories").get_json()["items"]


def named(client, name):
    """The account's category with this name, or None."""
    return next((one for one in categories_of(client) if one["name"] == name), None)


def make_category(client, name, kind="Expense"):
    client.post("/api/v1/categories", headers=client.headers,
                json={"name": name, "type": kind})
    return named(client, name)["id"]


# --- renaming ---------------------------------------------------------------

def test_renaming_a_category(make_api_account):
    client = make_api_account()
    category_id = make_category(client, "Books")

    response = client.patch(f"/api/v1/categories/{category_id}",
                            headers=client.headers,
                            json={"name": "Reading", "type": "Expense"})
    assert response.status_code == 200
    assert named(client, "Books") is None
    assert named(client, "Reading")["id"] == category_id


def test_renaming_onto_an_existing_name_is_reported_on_the_field(make_api_account):
    client = make_api_account()
    make_category(client, "Books")
    other = make_category(client, "Gadgets")

    response = client.patch(f"/api/v1/categories/{other}", headers=client.headers,
                            json={"name": "Books", "type": "Expense"})
    assert response.status_code == 422
    assert "name" in response.get_json()["error"]["fields"]


def test_renaming_someone_elses_category(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    target = make_category(theirs, "Books")

    response = mine.patch(f"/api/v1/categories/{target}", headers=mine.headers,
                          json={"name": "Stolen", "type": "Expense"})
    assert response.status_code == 404
    assert named(theirs, "Books") is not None


# --- deleting ---------------------------------------------------------------

def test_deleting_an_unused_category(make_api_account):
    client = make_api_account()
    category_id = make_category(client, "Books")

    response = client.delete(f"/api/v1/categories/{category_id}", headers=client.headers)
    assert response.status_code == 200
    assert named(client, "Books") is None


def test_deleting_a_category_in_use_without_a_target_is_refused(make_api_account):
    """The refusal must arrive as a field error, not a foreign key crash."""
    client = make_api_account()
    category_id = make_category(client, "Books")
    client.post("/api/v1/transactions", headers=client.headers,
                json={"date": "2026-08-01", "category_id": category_id,
                      "amount": "100.00", "type": "Expense", "description": "a book"})

    response = client.delete(f"/api/v1/categories/{category_id}", headers=client.headers)
    assert response.status_code == 422
    assert "reassign_to" in response.get_json()["error"]["fields"]
    assert named(client, "Books") is not None


def test_deleting_moves_transactions_to_the_named_category(make_api_account):
    client = make_api_account()
    going = make_category(client, "Books")
    staying = make_category(client, "Shopping")
    client.post("/api/v1/transactions", headers=client.headers,
                json={"date": "2026-08-01", "category_id": going,
                      "amount": "100.00", "type": "Expense", "description": "a book"})

    response = client.delete(f"/api/v1/categories/{going}?reassign_to={staying}",
                             headers=client.headers)
    assert response.status_code == 200

    rows = client.get("/api/v1/transactions").get_json()["items"]
    moved = [row for row in rows if row["description"] == "a book"]
    assert len(moved) == 1, "the transaction was deleted rather than moved"
    assert moved[0]["category"] == "Shopping"


def test_budgets_for_the_same_month_are_added_together(make_api_account):
    """Two limits cannot both survive: one category has one budget per month."""
    client = make_api_account()
    going = make_category(client, "Books")
    staying = make_category(client, "Shopping")
    for category_id, limit in ((going, "300.00"), (staying, "700.00")):
        client.put("/api/v1/budgets", headers=client.headers,
                   json={"category_id": category_id, "month": "2026-08", "limit": limit})

    response = client.delete(f"/api/v1/categories/{going}?reassign_to={staying}",
                             headers=client.headers)
    assert response.status_code == 200

    budgets = client.get("/api/v1/budgets").get_json()["items"]
    august = [row for row in budgets if row["month"] == "2026-08"]
    assert len(august) == 1
    assert august[0]["limit"] == "1000.00"


def test_a_budget_with_no_counterpart_simply_moves(make_api_account):
    client = make_api_account()
    going = make_category(client, "Books")
    staying = make_category(client, "Shopping")
    client.put("/api/v1/budgets", headers=client.headers,
               json={"category_id": going, "month": "2026-08", "limit": "300.00"})

    client.delete(f"/api/v1/categories/{going}?reassign_to={staying}",
                  headers=client.headers)

    budgets = client.get("/api/v1/budgets").get_json()["items"]
    assert [(row["category"], row["limit"]) for row in budgets
            if row["month"] == "2026-08"] == [("Shopping", "300.00")]


def test_the_target_must_be_the_same_kind(make_api_account):
    """An expense row filed under an income category corrupts every report."""
    client = make_api_account()
    going = make_category(client, "Books", "Expense")
    income = make_category(client, "Bonus", "Income")

    response = client.delete(f"/api/v1/categories/{going}?reassign_to={income}",
                             headers=client.headers)
    assert response.status_code == 422
    assert "reassign_to" in response.get_json()["error"]["fields"]
    assert named(client, "Books") is not None


def test_the_target_cannot_be_the_category_being_deleted(make_api_account):
    client = make_api_account()
    category_id = make_category(client, "Books")

    response = client.delete(f"/api/v1/categories/{category_id}?reassign_to={category_id}",
                             headers=client.headers)
    assert response.status_code == 422


def test_the_target_cannot_belong_to_another_account(make_api_account):
    """Otherwise a delete becomes a way to push rows into someone else's ledger."""
    mine, theirs = make_api_account(), make_api_account()
    going = make_category(mine, "Books")
    elsewhere = make_category(theirs, "Shopping")

    response = mine.delete(f"/api/v1/categories/{going}?reassign_to={elsewhere}",
                           headers=mine.headers)
    assert response.status_code == 422
    assert named(mine, "Books") is not None


def test_deleting_someone_elses_category(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    target = make_category(theirs, "Books")

    response = mine.delete(f"/api/v1/categories/{target}", headers=mine.headers)
    assert response.status_code == 404
    assert named(theirs, "Books") is not None


# --- usage counts -----------------------------------------------------------

def test_usage_counts_what_would_move(make_api_account):
    client = make_api_account()
    category_id = make_category(client, "Books")
    client.post("/api/v1/transactions", headers=client.headers,
                json={"date": "2026-08-01", "category_id": category_id,
                      "amount": "100.00", "type": "Expense", "description": "a book"})
    client.put("/api/v1/budgets", headers=client.headers,
               json={"category_id": category_id, "month": "2026-08", "limit": "300.00"})

    body = client.get(f"/api/v1/categories/{category_id}/usage").get_json()
    assert body == {"transactions": 1, "budgets": 1}


def test_usage_of_someone_elses_category(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    target = make_category(theirs, "Books")

    assert mine.get(f"/api/v1/categories/{target}/usage").status_code == 404
