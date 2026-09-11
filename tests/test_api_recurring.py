"""Recurring rules, and the sweep that materialises them.

The sweep is the dangerous part. The scheduler is at-least-once, so a run
that times out after writing may be retried and two can overlap. Most of
these tests exist to prove that running it again changes nothing.
"""

from datetime import date

from server import operations


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def rules(client):
    return {row["description"]: row
            for row in client.get("/api/v1/recurring").get_json()["items"]}


def set_rule(client, description="Rent", first="2026-06-01", **extra):
    body = {"description": description, "category_id": a_category(client),
            "amount": "15000.00", "type": "Expense", "cadence": "monthly",
            "next_run_on": first}
    body.update(extra)
    return client.post("/api/v1/recurring", headers=client.headers, json=body)


def written_by(client, description="Rent"):
    return [row for row in
            client.get("/api/v1/transactions?per_page=200").get_json()["items"]
            if row["description"] == description]


def sweep(user_id, today):
    """The scheduled sweep, for one account, on a given day."""
    return operations.materialise_due(user_id, today)


# --- the date arithmetic -----------------------------------------------------

def test_a_monthly_rule_on_the_31st_lands_on_the_28th_in_february():
    """Naive date arithmetic raises on 31 February; skipping the month would
    quietly lose a month's rent."""
    assert operations.next_date_after(date(2026, 1, 31), "monthly", 31) \
        == date(2026, 2, 28)


def test_it_returns_to_the_31st_the_month_after():
    """The clamp must not be sticky. Navigating by day_of_month is what
    stops a rule walking backwards through the year."""
    assert operations.next_date_after(date(2026, 2, 28), "monthly", 31) \
        == date(2026, 3, 31)


def test_a_monthly_rule_crosses_the_year():
    assert operations.next_date_after(date(2026, 12, 31), "monthly", 31) \
        == date(2027, 1, 31)


def test_a_weekly_rule_adds_seven_days():
    assert operations.next_date_after(date(2026, 6, 29), "weekly") \
        == date(2026, 7, 6)


def test_a_yearly_rule_on_the_29th_of_february_clamps():
    assert operations.next_date_after(date(2028, 2, 29), "yearly", 29) \
        == date(2029, 2, 28)


# --- what the sweep writes ---------------------------------------------------

def test_a_rule_writes_nothing_before_it_is_due(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    assert sweep(api_user_id(client), date(2026, 5, 20))["transactions"] == 0
    assert written_by(client) == []


def test_a_due_rule_writes_one_row(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    assert sweep(api_user_id(client), date(2026, 6, 1))["transactions"] == 1

    rows = written_by(client)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-01"
    assert rows[0]["amount"] == "15000.00"


def test_the_sweep_catches_up_every_month_it_missed(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    assert sweep(api_user_id(client), date(2026, 8, 15))["transactions"] == 3
    assert sorted(row["date"] for row in written_by(client)) == \
        ["2026-06-01", "2026-07-01", "2026-08-01"]


def test_running_the_sweep_again_writes_nothing(make_api_account, api_user_id):
    """The whole point of the unique index. The scheduler is at-least-once,
    so a repeat run must be a no-op rather than a duplicate rent."""
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    user_id = api_user_id(client)

    first = sweep(user_id, date(2026, 8, 15))
    second = sweep(user_id, date(2026, 8, 15))

    assert first["transactions"] == 3
    assert second["transactions"] == 0
    assert len(written_by(client)) == 3


def test_a_rule_advances_past_what_it_wrote(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    sweep(api_user_id(client), date(2026, 6, 1))
    assert rules(client)["Rent"]["next_run_on"] == "2026-07-01"


def test_a_paused_rule_writes_nothing(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    rule_id = rules(client)["Rent"]["id"]
    client.post(f"/api/v1/recurring/{rule_id}/pause", headers=client.headers,
                json={"paused": "1"})

    assert sweep(api_user_id(client), date(2026, 8, 15))["transactions"] == 0
    assert written_by(client) == []


def test_a_rule_stops_at_its_end_date(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01", ends_on="2026-07-15")
    assert sweep(api_user_id(client), date(2026, 12, 1))["transactions"] == 2
    assert sorted(row["date"] for row in written_by(client)) == \
        ["2026-06-01", "2026-07-01"]


def test_a_finished_rule_is_retired_rather_than_left_due(make_api_account,
                                                         api_user_id):
    """Left unpaused it stays due forever, and every future sweep selects it
    to do nothing."""
    client = make_api_account()
    set_rule(client, first="2026-06-01", ends_on="2026-07-15")
    user_id = api_user_id(client)
    sweep(user_id, date(2026, 12, 1))

    assert rules(client)["Rent"]["paused"] is True
    assert sweep(user_id, date(2027, 1, 1))["rules"] == 0


def test_catching_up_is_capped(make_api_account, api_user_id):
    """A rule resumed after two years must not post a hundred rows at once.
    It does as much as it can and picks the rest up next time."""
    client = make_api_account()
    set_rule(client, first="2020-01-01")
    written = sweep(api_user_id(client), date(2026, 6, 1))["transactions"]
    assert written == operations.MAX_CATCHUP


def test_the_rows_carry_the_account_the_rule_names(make_api_account, api_user_id):
    client = make_api_account()
    client.post("/api/v1/accounts", headers=client.headers,
                json={"name": "Savings", "kind": "Bank"})
    savings = next(one["id"] for one in
                   client.get("/api/v1/accounts").get_json()["items"]
                   if one["name"] == "Savings")
    set_rule(client, first="2026-06-01", account_id=savings)
    sweep(api_user_id(client), date(2026, 6, 1))
    assert written_by(client)[0]["account"] == "Savings"


# --- what a rule does not own ------------------------------------------------

def test_editing_a_rule_leaves_what_it_already_wrote(make_api_account, api_user_id):
    """The rent that went up in August is a fact about August."""
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    user_id = api_user_id(client)
    sweep(user_id, date(2026, 6, 1))

    rule_id = rules(client)["Rent"]["id"]
    client.patch(f"/api/v1/recurring/{rule_id}", headers=client.headers,
                 json={"description": "Rent", "category_id": a_category(client),
                       "amount": "17000.00", "type": "Expense",
                       "cadence": "monthly", "next_run_on": "2026-07-01"})

    assert written_by(client)[0]["amount"] == "15000.00"
    sweep(user_id, date(2026, 7, 1))
    assert sorted(row["amount"] for row in written_by(client)) == \
        ["15000.00", "17000.00"]


def test_deleting_a_rule_keeps_the_money_that_moved(make_api_account, api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    sweep(api_user_id(client), date(2026, 6, 1))

    rule_id = rules(client)["Rent"]["id"]
    assert client.delete(f"/api/v1/recurring/{rule_id}",
                         headers=client.headers).status_code == 200
    assert len(written_by(client)) == 1, "the rent was really paid"


def test_a_materialised_row_can_be_deleted_like_any_other(make_api_account,
                                                          api_user_id):
    client = make_api_account()
    set_rule(client, first="2026-06-01")
    sweep(api_user_id(client), date(2026, 6, 1))

    row = written_by(client)[0]
    assert client.delete(f"/api/v1/transactions/{row['id']}",
                         headers=client.headers).status_code == 200
    assert written_by(client) == []


# --- scope and validation ----------------------------------------------------

def test_a_sweep_for_one_account_leaves_another_alone(make_api_account,
                                                      api_user_id):
    mine, theirs = make_api_account(), make_api_account()
    set_rule(mine, first="2026-06-01")
    set_rule(theirs, first="2026-06-01")

    sweep(api_user_id(mine), date(2026, 6, 1))
    assert len(written_by(mine)) == 1
    assert written_by(theirs) == []


def test_a_rule_cannot_use_another_persons_category(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    response = mine.post("/api/v1/recurring", headers=mine.headers,
                         json={"description": "Rent",
                               "category_id": a_category(theirs),
                               "amount": "100.00", "type": "Expense",
                               "cadence": "monthly", "next_run_on": "2026-06-01"})
    assert response.status_code == 422


def test_another_persons_rule_cannot_be_touched(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    set_rule(theirs)
    stranger = rules(theirs)["Rent"]["id"]

    assert mine.delete(f"/api/v1/recurring/{stranger}",
                       headers=mine.headers).status_code == 404
    assert mine.post(f"/api/v1/recurring/{stranger}/pause", headers=mine.headers,
                     json={"paused": "1"}).status_code == 404
    assert rules(theirs)["Rent"]["paused"] is False


def test_an_end_date_before_the_first_run_is_refused(make_api_account):
    client = make_api_account()
    assert set_rule(client, first="2026-06-01",
                    ends_on="2026-05-01").status_code == 422


def test_an_unknown_cadence_is_refused(make_api_account):
    client = make_api_account()
    assert set_rule(client, cadence="fortnightly").status_code == 422


def test_a_rule_may_start_in_the_future(make_api_account):
    """Unlike a transaction, which may never be dated forward."""
    client = make_api_account()
    assert set_rule(client, first="2030-01-01").status_code == 201


def test_running_now_needs_a_session(client):
    assert client.post("/api/v1/recurring/run").status_code in (401, 403)


def test_the_scheduled_sweep_needs_the_secret(client):
    assert client.post("/api/v1/cron/recurring").status_code in (404, 503)


def test_resetting_a_demo_survives_everything_a_visitor_can_make(client):
    """A demo that grew a recurring rule used to refuse to reset: rules
    reference categories with RESTRICT, so deleting the categories failed
    and the visitor was left with a half-wiped account.

    Exercised through the demo account rather than a test user, because the
    reset is only ever run against one.
    """
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    body = client.post("/api/v1/auth/demo",
                       headers={"X-CSRF-Token": token}).get_json()
    user_id = body["user"]["id"]
    headers = {"X-CSRF-Token": body["csrf_token"]}

    try:
        category = a_category(client)
        # Named so it is distinguishable from the rule the demo seeds.
        client.post("/api/v1/recurring", headers=headers,
                    json={"description": "Gym membership", "category_id": category,
                          "amount": "1500.00", "type": "Expense",
                          "cadence": "monthly", "next_run_on": "2026-06-01"})
        client.post("/api/v1/tags", headers=headers, json={"name": "holiday"})
        client.post("/api/v1/goals", headers=headers,
                    json={"name": "Laptop", "target": "40000.00"})

        assert operations.reset_demo_data(user_id) is True

        # And it is genuinely back to the seed afterwards: what the visitor
        # made is gone, and what the demo ships with is there.
        after = [row["description"] for row in
                 client.get("/api/v1/recurring").get_json()["items"]]
        assert "Gym membership" not in after, "the visitor's rule should be gone"
        assert after == ["Rent"], "and the seeded one rebuilt"
        assert client.get("/api/v1/tags").get_json()["items"] == []
        assert client.get("/api/v1/goals").get_json()["items"] == []
        assert len(client.get("/api/v1/accounts").get_json()["items"]) == 3
    finally:
        operations.delete_demo_user(user_id)
