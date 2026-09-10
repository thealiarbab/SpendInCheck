"""Goals, and the contributions that make them more than a note.

Progress is summed on every read. The tests that matter are the ones that
add up known contributions by hand and check the total against them --
including the negative ones, which are how taking money back out is
recorded.
"""

from decimal import Decimal


def goals(client, archived=False):
    query = "/api/v1/goals" + ("?archived=1" if archived else "")
    return {row["name"]: row for row in client.get(query).get_json()["items"]}


def set_goal(client, name, target="40000.00", **extra):
    return client.post("/api/v1/goals", headers=client.headers,
                       json={"name": name, "target": target, **extra})


def contribute(client, goal_id, amount, date="2026-06-05", note=None):
    return client.post(f"/api/v1/goals/{goal_id}/contributions",
                       headers=client.headers,
                       json={"amount": amount, "date": date, "note": note})


def an_account(client):
    return client.get("/api/v1/accounts").get_json()["items"][0]["id"]


# --- setting a goal ----------------------------------------------------------

def test_a_new_goal_starts_at_nothing_saved(make_api_account):
    client = make_api_account()
    assert set_goal(client, "Laptop").status_code == 201
    laptop = goals(client)["Laptop"]
    assert laptop["target"] == "40000.00"
    assert laptop["saved"] == "0.00"
    assert laptop["contributions"] == 0


def test_a_goal_does_not_need_a_deadline(make_api_account):
    """"Save 200,000 eventually" is a real goal. Demanding a date would make
    people invent one."""
    client = make_api_account()
    set_goal(client, "Emergency fund", "200000.00")
    assert goals(client)["Emergency fund"]["target_date"] is None


def test_a_goal_can_name_the_account_it_is_kept_in(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop", account_id=an_account(client))
    assert goals(client)["Laptop"]["account"] == "Main"


def test_a_goal_cannot_point_at_another_persons_account(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    assert set_goal(mine, "Laptop", account_id=an_account(theirs)).status_code == 422


def test_two_goals_cannot_share_a_name(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop")
    assert set_goal(client, "Laptop").status_code == 422


def test_a_target_of_zero_is_refused(make_api_account):
    """A goal of nothing is already reached and means nothing."""
    client = make_api_account()
    assert set_goal(client, "Nothing", "0").status_code == 422


# --- contributions -----------------------------------------------------------

def test_saved_is_the_sum_of_what_was_put_in(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]

    contribute(client, laptop, "5000.00")
    contribute(client, laptop, "2500.50")

    after = goals(client)["Laptop"]
    assert after["saved"] == "7500.50"
    assert after["contributions"] == 2


def test_a_negative_contribution_takes_money_back_out(make_api_account):
    """Recording a withdrawal as a negative keeps the running total honest
    without a second table or a direction column."""
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]

    contribute(client, laptop, "5000.00")
    assert contribute(client, laptop, "-2000.00").status_code == 201
    assert goals(client)["Laptop"]["saved"] == "3000.00"


def test_a_contribution_of_zero_is_refused(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop")
    assert contribute(client, goals(client)["Laptop"]["id"], "0").status_code == 422


def test_contributions_are_listed_newest_first(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]
    for date in ("2026-06-01", "2026-07-01", "2026-05-01"):
        contribute(client, laptop, "1000.00", date=date)

    dates = [row["date"] for row in
             client.get(f"/api/v1/goals/{laptop}/contributions").get_json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_removing_a_contribution_moves_the_total_back(make_api_account):
    """The total is summed on every read, so it cannot be left standing at a
    figure its contributions no longer add up to."""
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]
    contribute(client, laptop, "5000.00")
    made = contribute(client, laptop, "1500.00").get_json()["id"]

    assert goals(client)["Laptop"]["saved"] == "6500.00"
    client.delete(f"/api/v1/contributions/{made}", headers=client.headers)
    assert goals(client)["Laptop"]["saved"] == "5000.00"


def test_a_goal_can_be_saved_past_its_target(make_api_account):
    """Overshooting is not an error, and clamping would hide it."""
    client = make_api_account()
    set_goal(client, "Laptop", "1000.00")
    laptop = goals(client)["Laptop"]["id"]
    contribute(client, laptop, "1500.00")
    assert goals(client)["Laptop"]["saved"] == "1500.00"


def test_the_sum_matches_the_listed_contributions(make_api_account):
    """The list and the total come from different queries; they must agree."""
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]
    for amount in ("1000.00", "2500.50", "-300.25"):
        contribute(client, laptop, amount)

    listed = client.get(f"/api/v1/goals/{laptop}/contributions").get_json()["items"]
    assert sum(Decimal(row["amount"]) for row in listed) == \
        Decimal(goals(client)["Laptop"]["saved"])


# --- editing, archiving, deleting --------------------------------------------

def test_a_goal_can_be_retargeted_without_losing_progress(make_api_account):
    client = make_api_account()
    set_goal(client, "Laptop", "40000.00")
    laptop = goals(client)["Laptop"]["id"]
    contribute(client, laptop, "5000.00")

    client.patch(f"/api/v1/goals/{laptop}", headers=client.headers,
                 json={"name": "Laptop and desk", "target": "55000.00"})

    after = goals(client)["Laptop and desk"]
    assert after["target"] == "55000.00"
    assert after["saved"] == "5000.00"


def test_an_archived_goal_is_hidden_but_not_gone(make_api_account):
    """Reached goals are worth keeping -- "we saved for this and did it" is
    the part of a ledger people enjoy."""
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]

    client.post(f"/api/v1/goals/{laptop}/archive", headers=client.headers,
                json={"archived": "1"})
    assert "Laptop" not in goals(client)
    assert "Laptop" in goals(client, archived=True)


def test_deleting_a_goal_takes_its_contributions(make_api_account):
    """A contribution towards a goal that no longer exists means nothing."""
    client = make_api_account()
    set_goal(client, "Laptop")
    laptop = goals(client)["Laptop"]["id"]
    contribute(client, laptop, "5000.00")

    assert client.delete(f"/api/v1/goals/{laptop}",
                         headers=client.headers).status_code == 200
    assert goals(client, archived=True) == {}
    assert client.get(f"/api/v1/goals/{laptop}/contributions").status_code == 404


def test_closing_the_account_leaves_the_goal_standing(make_api_account):
    """SET NULL, not CASCADE: closing the account you were saving into does
    not abandon the goal, it just stops saying where the money sits."""
    client = make_api_account()
    client.post("/api/v1/accounts", headers=client.headers,
                json={"name": "Savings", "kind": "Bank"})
    savings = next(one["id"] for one in
                   client.get("/api/v1/accounts").get_json()["items"]
                   if one["name"] == "Savings")
    set_goal(client, "Laptop", account_id=savings)
    contribute(client, goals(client)["Laptop"]["id"], "5000.00")

    main = next(one["id"] for one in
                client.get("/api/v1/accounts").get_json()["items"]
                if one["name"] == "Main")
    client.delete(f"/api/v1/accounts/{savings}?reassign_to={main}",
                  headers=client.headers)

    laptop = goals(client)["Laptop"]
    assert laptop["account"] is None
    assert laptop["saved"] == "5000.00", "progress must survive the account"


# --- reaching scope through the goal -----------------------------------------

def test_a_contribution_cannot_be_added_to_another_persons_goal(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    set_goal(theirs, "Theirs")
    stranger = goals(theirs)["Theirs"]["id"]

    assert contribute(mine, stranger, "1000.00").status_code == 404
    assert goals(theirs)["Theirs"]["saved"] == "0.00"


def test_another_persons_contribution_cannot_be_deleted(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    set_goal(theirs, "Theirs")
    made = contribute(theirs, goals(theirs)["Theirs"]["id"],
                      "1000.00").get_json()["id"]

    assert mine.delete(f"/api/v1/contributions/{made}",
                       headers=mine.headers).status_code == 404
    assert goals(theirs)["Theirs"]["saved"] == "1000.00"


def test_goals_are_not_visible_across_accounts(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    set_goal(theirs, "Theirs")
    assert mine.get("/api/v1/goals").get_json()["items"] == []


def test_every_goal_endpoint_needs_a_session(client):
    assert client.get("/api/v1/goals").status_code == 401
    assert client.post("/api/v1/goals").status_code in (401, 403)
