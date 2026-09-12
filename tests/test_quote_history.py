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

# A stand-in for the benchmark. The real one, NIFTYBEES, is a live symbol
# whose closes every account's comparison chart reads -- deleting it in
# teardown wiped that chart for everybody until the next nightly run,
# which is what these tests did before this constant existed.
TEST_BENCHMARK = "TESTBM"

# A second synthetic symbol, for the case where one holding has a
# shorter price history than another.
LATECO = "TESTLATE"


@pytest.fixture
def clean_history():
    """Remove this symbol's rows before and after.

    quote_history and instruments are both shared -- a price and a company
    name are facts about the market, not about a user -- so they are the
    two tables a test cannot clean up by deleting its user. Every symbol
    touched here is synthetic for that reason: deleting rows for a symbol
    somebody's screen actually reads is how a test breaks production.
    """
    def wipe():
        connection = db.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM quote_history WHERE ticker = %s", (TICKER,))
            cursor.execute("DELETE FROM instruments WHERE ticker = %s", (TICKER,))
            # The stand-in, never the real benchmark. Both are synthetic
            # symbols no exchange lists, so nothing outside these tests
            # can be using either.
            cursor.execute("DELETE FROM quote_history WHERE ticker = %s",
                           (TEST_BENCHMARK,))
            cursor.execute("DELETE FROM quote_history WHERE ticker = %s",
                           (LATECO,))
            cursor.execute("DELETE FROM instruments WHERE ticker = %s",
                           (LATECO,))
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


# --- what the sparkline reads -----------------------------------------------

def test_the_history_endpoint_reads_our_own_records(make_api_account, clean_history):
    """Not StockSaathi. The snapshot has already written these down, so a
    chart must not depend on their server being up."""
    client = make_api_account()
    holding = add_holding(client)
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})
    operations.record_closes(TICKER, [(date(2026, 9, 1), Decimal("10.00")),
                                      (date(2026, 9, 2), Decimal("11.00"))])

    items = client.get("/api/v1/investments/history").get_json()["items"]
    assert TICKER in items
    assert [point["close"] for point in items[TICKER]] == ["10.00", "11.00"]
    assert [point["date"] for point in items[TICKER]] == ["2026-09-01", "2026-09-02"]


def test_a_symbol_recorded_but_not_priced_still_gets_a_chart(
        make_api_account, clean_history):
    """symbols_held, not symbols_to_price. Somebody who wrote down a ticker
    without switching on automatic pricing still wants to see it."""
    client = make_api_account()
    holding = add_holding(client)
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})
    operations.record_closes(TICKER, [(date.today(), Decimal("10.00"))])

    held = client.get("/api/v1/investments").get_json()["items"][0]
    assert held["auto_price"] is False, "the point of the test"
    assert TICKER in client.get("/api/v1/investments/history").get_json()["items"]


def test_an_account_of_deposits_asks_for_nothing(make_api_account, clean_history):
    client = make_api_account()
    add_holding(client, asset_name="A Deposit", asset_type="FD")
    assert client.get("/api/v1/investments/history").get_json()["items"] == {}


def test_one_account_cannot_read_which_symbols_another_holds(
        make_api_account, clean_history):
    """The closes themselves are public -- a price is a fact about the
    market. Which symbols somebody holds is not."""
    owner, stranger = make_api_account(), make_api_account()
    holding = add_holding(owner)
    owner.patch(f"/api/v1/investments/{holding['id']}/pricing",
                headers=owner.headers, json={"ticker": TICKER, "auto_price": "0"})
    operations.record_closes(TICKER, [(date.today(), Decimal("10.00"))])

    assert TICKER in owner.get("/api/v1/investments/history").get_json()["items"]
    assert stranger.get("/api/v1/investments/history").get_json()["items"] == {}


# --- what a symbol is -------------------------------------------------------

def test_a_partial_answer_tops_up_rather_than_blanks(clean_history):
    """The opposite rule from a close, and for a reason.

    A close records what happened on a day and is settled. This records
    what is true now -- a sector gets reclassified, and the 52-week range
    moves daily -- so the newest answer wins. But a feed that has
    momentarily lost the sector must not erase the one already known.
    """
    operations.record_instrument({
        "symbol": TICKER, "name": "Test Co Ltd", "sector": "Energy",
        "exchange": "NSE", "low_52w": Decimal("10.00"),
        "high_52w": Decimal("20.00")})
    operations.record_instrument({
        "symbol": TICKER, "name": None, "sector": None, "exchange": None,
        "low_52w": None, "high_52w": Decimal("25.00")})

    facts = operations.instruments_for([TICKER])[TICKER]
    assert facts["name"] == "Test Co Ltd", "not erased by a blank"
    assert facts["sector"] == "Energy"
    assert facts["high_52w"] == Decimal("25.000"), "but a new figure wins"


def test_nothing_is_recorded_for_a_symbol_that_resolved_to_nothing():
    assert operations.record_instrument(None) is False
    assert operations.record_instrument({}) is False


def test_the_history_endpoint_carries_what_each_symbol_is(
        make_api_account, clean_history):
    """From the same request as the closes. A separate endpoint for four
    fields that change once a day would be a third round trip on a screen
    that already justifies its second."""
    client = make_api_account()
    holding = add_holding(client)
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})
    operations.record_instrument({
        "symbol": TICKER, "name": "Test Co Ltd", "sector": "Energy",
        "exchange": "NSE", "low_52w": Decimal("10.00"),
        "high_52w": Decimal("20.00")})

    body = client.get("/api/v1/investments/history").get_json()
    assert body["instruments"][TICKER]["name"] == "Test Co Ltd"
    assert body["instruments"][TICKER]["low_52w"] == "10.00", "money as a string"


# --- against the market -----------------------------------------------------

@pytest.fixture
def stand_in_benchmark(monkeypatch):
    """Point the benchmark at a synthetic symbol for the duration.

    Patched in both modules because operations re-exports the name by
    value, so the package attribute and the one the query reads are two
    separate bindings.
    """
    from server.operations import quotes
    monkeypatch.setattr(quotes, "BENCHMARK", TEST_BENCHMARK)
    monkeypatch.setattr(operations, "BENCHMARK", TEST_BENCHMARK)
    return TEST_BENCHMARK


def seed_benchmark(closes):
    """Give the stand-in benchmark a price history."""
    operations.record_closes(TEST_BENCHMARK, closes)


def test_the_basket_holds_quantities_constant(make_api_account, clean_history, stand_in_benchmark):
    """The whole reason this is not just the portfolio's value.

    Buying more of something raises what the holdings are worth without
    the market having moved at all, so charting real value against an
    index would make a month of heavy saving read as a month of
    spectacular returns.
    """
    client = make_api_account()
    holding = add_holding(client, quantity="10", current_price="100.00")
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})

    today = date.today()
    months = []
    for back in (2, 1, 0):
        year, month = today.year, today.month - back
        while month < 1:
            month += 12
            year -= 1
        months.append(date(year, month, 1))

    # The price doubles; the quantity never changes.
    operations.record_closes(TICKER, [(months[0], Decimal("100.00")),
                                      (months[1], Decimal("150.00")),
                                      (months[2], Decimal("200.00"))])
    seed_benchmark([(months[0], Decimal("50.00")),
                    (months[1], Decimal("55.00")),
                    (months[2], Decimal("60.00"))])

    rows = operations.basket_against_benchmark(
        client.get("/api/v1/auth/session").get_json()["user"]["id"], months=3)
    assert [month for month, _, _ in rows] == [d.strftime("%Y-%m") for d in months]
    # Ten shares at each month's close.
    assert [value for _, value, _ in rows] == [
        Decimal("1000.000"), Decimal("1500.000"), Decimal("2000.000")]
    assert [close for _, _, close in rows] == [
        Decimal("50.000"), Decimal("55.000"), Decimal("60.000")]


def test_a_holding_that_listed_late_does_not_read_as_a_market_gain(
        make_api_account, clean_history, stand_in_benchmark):
    """The basket has to be the same basket in every month it is charted.

    JOIN LATERAL ... ON TRUE is an inner join, so a holding with no close
    before a given month is dropped from that month -- while the month
    itself survives on the strength of the other holdings. The basket
    silently changes membership partway along, and when the late arrival's
    history begins, its whole value appears at once.

    Both symbols are flat here on purpose. Nothing about the market moves,
    so any movement in the basket line is this bug and nothing else.
    """
    client = make_api_account()
    today = date.today()
    months = []
    for back in (2, 1, 0):
        year, month = today.year, today.month - back
        while month < 1:
            month += 12
            year -= 1
        months.append(date(year, month, 1))

    steady = add_holding(client, asset_name="Steady", quantity="10",
                         current_price="100.00")
    client.patch(f"/api/v1/investments/{steady['id']}/pricing",
                 headers=client.headers, json={"ticker": TICKER, "auto_price": "0"})

    client.post("/api/v1/investments", headers=client.headers,
                json={"asset_name": "Latecomer", "asset_type": "Stock",
                      "buy_date": "2026-01-02", "buy_price": "100.00",
                      "quantity": "10", "current_price": "100.00"})
    late = next(one for one in
                client.get("/api/v1/investments").get_json()["items"]
                if one["asset_name"] == "Latecomer")
    client.patch(f"/api/v1/investments/{late['id']}/pricing",
                 headers=client.headers, json={"ticker": LATECO, "auto_price": "0"})

    # Flat throughout. The latecomer simply has no history until the last month.
    operations.record_closes(TICKER, [(m, Decimal("100.00")) for m in months])
    operations.record_closes(LATECO, [(months[2], Decimal("100.00"))])
    seed_benchmark([(m, Decimal("50.00")) for m in months])

    user_id = client.get("/api/v1/auth/session").get_json()["user"]["id"]
    values = [value for _, value, _ in
              operations.basket_against_benchmark(user_id, months=3)]

    assert len(set(values)) == 1, (
        f"nothing moved, so the basket must not have: {values}")


def test_a_deposit_takes_no_part(make_api_account, clean_history, stand_in_benchmark):
    """It has no market return to compare, and including it at a flat
    price would drag the line toward no movement at all."""
    client = make_api_account()
    add_holding(client, asset_name="A Deposit", asset_type="FD")
    seed_benchmark([(date.today(), Decimal("50.00"))])

    body = client.get("/api/v1/reports/benchmark").get_json()
    assert body["items"] == []
    assert body["benchmark"] == TEST_BENCHMARK


def test_both_sides_are_rebased_to_a_hundred(make_api_account, clean_history, stand_in_benchmark):
    """A basket worth 180,000 and an ETF unit worth 267 share no axis
    until both are expressed as what a hundred became."""
    client = make_api_account()
    holding = add_holding(client, quantity="10", current_price="100.00")
    client.patch(f"/api/v1/investments/{holding['id']}/pricing",
                 headers=client.headers,
                 json={"ticker": TICKER, "auto_price": "0"})

    today = date.today()
    earlier = date(today.year - 1, today.month, 1) if today.month else today
    operations.record_closes(TICKER, [(earlier, Decimal("100.00")),
                                      (date(today.year, today.month, 1),
                                       Decimal("50.00"))])
    seed_benchmark([(earlier, Decimal("200.00")),
                    (date(today.year, today.month, 1), Decimal("300.00"))])

    items = client.get("/api/v1/reports/benchmark").get_json()["items"]
    assert items[0]["basket"] == "100.0" or items[0]["basket"] == "100.00"
    assert items[0]["market"] == "100.0" or items[0]["market"] == "100.00"
    # Halved against the start; the market half again as much.
    assert float(items[-1]["basket"]) == 50.0
    assert float(items[-1]["market"]) == 150.0
