"""Tags: many per transaction, and none is normal.

The join table has no user_id of its own, so every query has to reach user
scope through `transactions`. Half the tests here exist to prove that
reaching actually happens -- a missing filter on a link table is invisible
in Python and only misbehaves against another account's rows.
"""


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def add_transaction(client, description="row", amount="100.00"):
    client.post("/api/v1/transactions", headers=client.headers,
                json={"date": "2026-06-05", "category_id": a_category(client),
                      "amount": amount, "type": "Expense",
                      "description": description})
    rows = client.get("/api/v1/transactions").get_json()["items"]
    return next(row["id"] for row in rows if row["description"] == description)


def add_tag(client, name):
    return client.post("/api/v1/tags", headers=client.headers, json={"name": name})


def tag_id(client, name):
    return next(one["id"] for one in client.get("/api/v1/tags").get_json()["items"]
                if one["name"] == name)


def set_tags(client, transaction_id, tag_ids):
    return client.put(f"/api/v1/transactions/{transaction_id}/tags",
                      headers=client.headers, json={"tag_ids": tag_ids})


def tags_on(client, transaction_id):
    rows = client.get("/api/v1/transactions").get_json()["items"]
    row = next(one for one in rows if one["id"] == transaction_id)
    return sorted(tag["name"] for tag in row["tags"])


# --- the tags themselves -----------------------------------------------------

def test_a_tag_can_be_created_and_listed(make_api_account):
    client = make_api_account()
    assert add_tag(client, "holiday").status_code == 201
    items = client.get("/api/v1/tags").get_json()["items"]
    assert [one["name"] for one in items] == ["holiday"]
    assert items[0]["uses"] == 0


def test_case_does_not_make_a_second_tag(make_api_account):
    """Nobody means Holiday and holiday to be two different labels, and a
    list containing both is a mess that only grows."""
    client = make_api_account()
    add_tag(client, "Holiday")
    assert add_tag(client, "holiday").status_code == 422
    assert len(client.get("/api/v1/tags").get_json()["items"]) == 1


def test_two_accounts_can_use_the_same_tag_name(make_api_account):
    """Uniqueness is per user. Sharing a namespace across accounts would be
    a leak dressed up as a constraint."""
    mine, theirs = make_api_account(), make_api_account()
    assert add_tag(mine, "holiday").status_code == 201
    assert add_tag(theirs, "holiday").status_code == 201


def test_a_tag_can_be_renamed_without_losing_its_rows(make_api_account):
    client = make_api_account()
    add_tag(client, "hols")
    transaction = add_transaction(client)
    set_tags(client, transaction, [tag_id(client, "hols")])

    client.patch(f"/api/v1/tags/{tag_id(client, 'hols')}", headers=client.headers,
                 json={"name": "holiday"})
    assert tags_on(client, transaction) == ["holiday"]


def test_deleting_a_tag_keeps_the_transaction(make_api_account):
    """A transaction with no tags is perfectly ordinary. A transaction that
    vanished with its label would not be."""
    client = make_api_account()
    add_tag(client, "holiday")
    transaction = add_transaction(client)
    set_tags(client, transaction, [tag_id(client, "holiday")])

    client.delete(f"/api/v1/tags/{tag_id(client, 'holiday')}", headers=client.headers)

    rows = client.get("/api/v1/transactions").get_json()["items"]
    assert any(row["id"] == transaction for row in rows)
    assert tags_on(client, transaction) == []


def test_the_list_counts_how_many_rows_carry_each_tag(make_api_account):
    client = make_api_account()
    add_tag(client, "holiday")
    add_tag(client, "unused")
    holiday = tag_id(client, "holiday")
    for note in ("one", "two"):
        set_tags(client, add_transaction(client, note), [holiday])

    counts = {one["name"]: one["uses"]
              for one in client.get("/api/v1/tags").get_json()["items"]}
    assert counts == {"holiday": 2, "unused": 0}


def test_an_unused_tag_still_appears(make_api_account):
    """It is exactly the tag most likely to want deleting."""
    client = make_api_account()
    add_tag(client, "never used")
    assert [one["name"] for one in
            client.get("/api/v1/tags").get_json()["items"]] == ["never used"]


# --- putting them on transactions --------------------------------------------

def test_a_transaction_can_carry_several_tags(make_api_account):
    client = make_api_account()
    for name in ("holiday", "work", "reimbursed"):
        add_tag(client, name)
    transaction = add_transaction(client)
    set_tags(client, transaction,
             [tag_id(client, "holiday"), tag_id(client, "reimbursed")])
    assert tags_on(client, transaction) == ["holiday", "reimbursed"]


def test_setting_tags_replaces_rather_than_adds(make_api_account):
    """The form shows the whole set, so what it submits is the whole set.
    Adding would mean a tag could never be taken off."""
    client = make_api_account()
    for name in ("holiday", "work"):
        add_tag(client, name)
    transaction = add_transaction(client)

    set_tags(client, transaction, [tag_id(client, "holiday")])
    set_tags(client, transaction, [tag_id(client, "work")])
    assert tags_on(client, transaction) == ["work"]


def test_an_empty_list_takes_every_tag_off(make_api_account):
    client = make_api_account()
    add_tag(client, "holiday")
    transaction = add_transaction(client)
    set_tags(client, transaction, [tag_id(client, "holiday")])

    assert set_tags(client, transaction, []).status_code == 200
    assert tags_on(client, transaction) == []


def test_the_same_tag_twice_lands_once(make_api_account):
    client = make_api_account()
    add_tag(client, "holiday")
    transaction = add_transaction(client)
    holiday = tag_id(client, "holiday")
    assert set_tags(client, transaction, [holiday, holiday]).status_code == 200
    assert tags_on(client, transaction) == ["holiday"]


def test_a_page_of_rows_carries_its_tags(make_api_account):
    """Fetched for the whole page in one query rather than per row."""
    client = make_api_account()
    add_tag(client, "holiday")
    holiday = tag_id(client, "holiday")
    tagged = add_transaction(client, "tagged")
    add_transaction(client, "untagged")
    set_tags(client, tagged, [holiday])

    rows = {row["description"]: row["tags"]
            for row in client.get("/api/v1/transactions").get_json()["items"]}
    assert [tag["name"] for tag in rows["tagged"]] == ["holiday"]
    assert rows["untagged"] == []


def test_the_edit_shape_carries_its_tags_too(make_api_account):
    client = make_api_account()
    add_tag(client, "holiday")
    transaction = add_transaction(client)
    set_tags(client, transaction, [tag_id(client, "holiday")])

    body = client.get(f"/api/v1/transactions/{transaction}").get_json()
    assert [tag["name"] for tag in body["tags"]] == ["holiday"]


# --- filtering ---------------------------------------------------------------

def test_the_ledger_can_be_filtered_to_one_tag(make_api_account):
    client = make_api_account()
    add_tag(client, "holiday")
    holiday = tag_id(client, "holiday")
    set_tags(client, add_transaction(client, "in Goa"), [holiday])
    add_transaction(client, "at home")

    found = client.get(f"/api/v1/transactions?tag_id={holiday}").get_json()
    assert [row["description"] for row in found["items"]] == ["in Goa"]
    assert found["page"]["total"] == 1


def test_a_row_with_three_tags_appears_once(make_api_account):
    """A join to the link table would multiply the row by its tag count and
    show the same transaction three times for having three labels."""
    client = make_api_account()
    for name in ("a", "b", "c"):
        add_tag(client, name)
    transaction = add_transaction(client, "thrice tagged")
    set_tags(client, transaction, [tag_id(client, n) for n in ("a", "b", "c")])

    found = client.get("/api/v1/transactions").get_json()
    assert sum(1 for row in found["items"] if row["id"] == transaction) == 1
    assert found["page"]["total"] == 1


# --- reaching user scope through transactions --------------------------------

def test_a_tag_cannot_be_put_on_another_persons_transaction(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    add_tag(mine, "holiday")
    stranger = add_transaction(theirs, "not yours")

    assert set_tags(mine, stranger, [tag_id(mine, "holiday")]).status_code == 404
    assert tags_on(theirs, stranger) == []


def test_another_persons_tag_cannot_be_attached(make_api_account):
    """The ownership filter lives inside the insert, so a stale or hostile
    id matches no row rather than being attached."""
    mine, theirs = make_api_account(), make_api_account()
    add_tag(theirs, "theirs")
    stranger_tag = tag_id(theirs, "theirs")
    transaction = add_transaction(mine)

    assert set_tags(mine, transaction, [stranger_tag]).status_code == 200
    assert tags_on(mine, transaction) == []


def test_another_persons_tag_cannot_be_renamed_or_deleted(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    add_tag(theirs, "theirs")
    stranger_tag = tag_id(theirs, "theirs")

    assert mine.patch(f"/api/v1/tags/{stranger_tag}", headers=mine.headers,
                      json={"name": "mine now"}).status_code == 404
    assert mine.delete(f"/api/v1/tags/{stranger_tag}",
                       headers=mine.headers).status_code == 404
    assert [one["name"] for one in
            theirs.get("/api/v1/tags").get_json()["items"]] == ["theirs"]


def test_tags_are_not_visible_across_accounts(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    add_tag(theirs, "theirs")
    assert mine.get("/api/v1/tags").get_json()["items"] == []


def test_every_tag_endpoint_needs_a_session(client):
    assert client.get("/api/v1/tags").status_code == 401
    assert client.post("/api/v1/tags").status_code in (401, 403)


# --- validation --------------------------------------------------------------

def test_a_blank_tag_is_refused(make_api_account):
    client = make_api_account()
    assert add_tag(client, "   ").status_code == 422


def test_tag_ids_must_be_a_list_of_numbers(make_api_account):
    client = make_api_account()
    transaction = add_transaction(client)
    assert client.put(f"/api/v1/transactions/{transaction}/tags",
                      headers=client.headers,
                      json={"tag_ids": "holiday"}).status_code == 422
    assert client.put(f"/api/v1/transactions/{transaction}/tags",
                      headers=client.headers,
                      json={"tag_ids": ["nope"]}).status_code == 422
