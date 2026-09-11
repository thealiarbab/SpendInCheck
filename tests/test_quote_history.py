"""Net worth valued at what things were worth then, not at what they cost now.

No network here. Closes are written directly, so the figures under test are
arithmetic against known inputs rather than against whatever the market did
this morning.

The bug these exist to prevent is a quiet one. Valuing every month at
today's price does not look broken -- the chart draws, the numbers are
plausible, and the line even goes up. It just describes the portfolio's
composition changing and nothing about the market, which is the opposite of
what somebody reads it for.
"""

from datetime import date
from decimal import Decimal

import pytest

from server import db, operations


TICKER = "TESTCO"


@pytest.fixture
def clean_history():
    """Remove this symbol's rows before and after.

    quote_history is shared -- a price is a fact about the market, not about
    a user -- so it is the one table a test cannot clean up by deleting its
    user. TESTCO is not a real NSE symbol, so nothing else can be using it.
    """
    def wipe():
        connection = db.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM quote_history WHERE ticker = %s", (TICKER,))
            connection.commit()
        finally:
            db.close_connection(connection)

    wipe()
    yield
    wipe()


def add_holding(client, **overrides):
    body = {"asset_name": "Test Holding", "asset_type": "Stock",
            "buy_date": "2026-01-02", "buy_price": "100.00",
            "quantity": "10", "current_price": "500.00"}
    body.update(overrides)
    response = client.post("/api/v1/investments", headers=client.headers, json=body)
    assert response.status_code == 201, response.get_json()
    return client.get("/api/v1/investments").get_json()["items"][0]


def holdings_line(client, months=3):
    """The holdings value per month, as strings, oldest first."""
    body = client.get(f"/api/v1/reports/summary?months={months}").get_json()
    return [row["holdings"] for row in body["net_worth"]]


# --- recording --------------------------------------------------------------

def test_closes_are_written_once_and_a_repeat_changes_nothing(clean_history):
    """The scheduler is at-least-once, so a second run has to be harmless
    rather than merely unlikely."""
    closes = [(date(2026, 6, 30), Decimal("100.00")),
              (date(2026, 7, 31), Decimal("110.00"))]
    assert operations.record_closes(TICKER, closes) == 2
    assert operations.record_closes(TICKER, closes) == 0
    assert operations.close_on(TICKER, date(2026, 7, 31)) == Decimal("110.000")


def test_a_settled_close_is_not_revised_by_a_later_feed(clean_history):
    """Yesterday's close is final. A feed sending a different one is more
    likely to be having a bad day than the record is to be wrong."""
    operations.record_closes(TICKER, [(date(2026, 6, 30), Decimal("100.00"))])
    operations.record_closes(TICKER, [(date(2026, 6, 30), Decimal("999.00"))])
    assert operations.close_on(TICKER, date(2026, 6, 30)) == Decimal("100.000")


def test_todays_row_may_still_move(clean_history):
    """It is not a close until the market shuts, so a later fetch on the
    same day is a better figure, not a contradiction."""
    operations.record_closes(TICKER, [(date.today(), Decimal("100.00"))])
    operations.record_closes(TICKER, [(date.today(), Decimal("123.00"))])
    assert operations.close_on(TICKER, date.today()) == Decimal("123.000")


def test_the_last_close_at_or_before_a_date_is_what_comes_back(clean_history):
    """Markets shut at weekends, so "the close on the 5th" usually means
    the close on the most recent day that traded."""
    operations.record_closes(TICKER, [(date(2026, 6, 1), Decimal("10.00")),
                                      (date(2026, 6, 10), Decimal("20.00"))])
    assert operations.close_on(TICKER, date(2026, 6, 5)) == Decimal("10.000")
    assert operations.close_on(TICKER, date(2026, 6, 30)) == Decimal("20.000")
    assert operations.close_on(TICKER, date(2026, 5, 1)) is None


# --- what the chart is valued at --------------------------------------------

def test_each_month_is_valued_at_that_months_close(make_api_account, clean_history):
    """The whole point. Ten shares, three months, three different closes."""
    client = make_api_account()
    holding = add_holding(client, current_price="500.00")
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})

    today = date.today()
    # The series values each month at the last close *before* the next
    # month begins, so a close dated the 1st of a month lands in that month.
    for months_back, price in ((2, "100.00"), (1, "200.00"), (0, "300.00")):
        year = today.year
        month = today.month - months_back
        while month < 1:
            month += 12
            year -= 1
        operations.record_closes(TICKER, [(date(year, month, 1), Decimal(price))])

    assert holdings_line(client) == ["1000.00", "2000.00", "3000.00"]


def test_a_holding_with_no_history_still_uses_its_stored_price(
        make_api_account, clean_history):
    """A deposit has no ticker and never will. The old behaviour is kept as
    the fallback rather than removed with the rule."""
    client = make_api_account()
    add_holding(client, asset_name="A Deposit", asset_type="FD",
                current_price="500.00")
    assert set(holdings_line(client)) == {"5000.00"}


def test_months_before_the_history_starts_fall_back_too(
        make_api_account, clean_history):
    """A symbol tracked from today has no closes for March, and March still
    has to be worth something. Falling back beats drawing a hole."""
    client = make_api_account()
    holding = add_holding(client, current_price="500.00")
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})
    operations.record_closes(TICKER, [(date.today(), Decimal("300.00"))])

    line = holdings_line(client)
    assert line[0] == "5000.00", "an unpriced month keeps the stored price"
    assert line[-1] == "3000.00", "the priced month uses the close"


def test_both_query_paths_give_the_same_answer(make_api_account, clean_history):
    """net_worth_series and the combined summary statement had this
    valuation copied out between them. They share one fragment now, and
    this is what would notice if a copy came back."""
    client = make_api_account()
    holding = add_holding(client, current_price="500.00")
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})
    operations.record_closes(TICKER, [(date.today(), Decimal("250.00"))])

    user_id = client.get("/api/v1/auth/session").get_json()["user"]["id"]
    separate = operations.net_worth_series(user_id, months=3)
    combined = operations.dashboard_summary(user_id, months=3)["net_worth"]

    assert [tuple(str(value) for value in row) for row in separate] == \
           [tuple(str(value) for value in row) for row in combined]
