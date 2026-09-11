"""Holdings priced from the market rather than from memory.

The price feed is stubbed in every test. What is worth asserting here is
the application's own rules -- who may be repriced, what happens when a
symbol is wrong, what a switched-off holding is protected from -- and none
of that should depend on whether somebody else's server is up this minute.
tests/test_stocksaathi.py covers the translation, and one test there talks
to the real API.
"""

import pytest

from server.routes.api import investments as investments_route
from server.services import stocksaathi


HOLDING = {"asset_name": "Reliance Industries", "asset_type": "Stock",
           "buy_date": "2026-01-02", "buy_price": "1200.00",
           "quantity": "10", "current_price": "1200.00"}


@pytest.fixture
def feed(monkeypatch):
    """Stand in for StockSaathi, and record what was asked for.

    Patched on the service module, which is the single place both the route
    and the refresh reach it through.
    """
    class Feed:
        def __init__(self):
            self.prices = {"RELIANCE": "1274.00", "TCS": "2204.10"}
            self.asked = []
            self.reachable = True

        def __call__(self, symbols, timeout=None):
            self.asked.append(list(symbols))
            if not self.reachable:
                return {}
            from decimal import Decimal
            return {symbol: {"price": Decimal(self.prices[symbol]),
                             "prev_close": Decimal("1279.00"),
                             "change": -0.0039, "as_of": 1789033500000,
                             "source": "yahoo"}
                    for symbol in symbols if symbol in self.prices}

    stub = Feed()
    monkeypatch.setattr(stocksaathi, "live_quotes", stub)
    monkeypatch.setattr(investments_route.stocksaathi, "live_quotes", stub)
    return stub


def add_holding(client, **overrides):
    """Post a valid holding, letting a test override any single field."""
    body = dict(HOLDING)
    body.update(overrides)
    return client.post("/api/v1/investments", headers=client.headers, json=body)


def holdings_of(client):
    return client.get("/api/v1/investments").get_json()["items"]


def only_holding(client):
    items = holdings_of(client)
    assert len(items) == 1, items
    return items[0]


# --- a holding without a symbol is unchanged --------------------------------

def test_a_holding_added_without_a_symbol_is_priced_by_hand(make_api_account, feed):
    """The default, and what every holding was before this existed.

    Asserted explicitly because the failure it guards against is the worst
    kind: a migration or a default that quietly starts overwriting numbers
    people typed.
    """
    client = make_api_account()
    assert add_holding(client).status_code == 201

    holding = only_holding(client)
    assert holding["ticker"] is None
    assert holding["auto_price"] is False
    assert holding["price_source"] == "manual"
    assert holding["current_price"] == "1200.00"
    assert feed.asked == [], "a holding with no symbol must cost no fetch"


def test_a_fixed_deposit_can_never_be_priced_automatically(make_api_account, feed):
    """Not a special case in the code -- a consequence of the ticker being
    the opt-in. There is no symbol for a deposit, so there is nothing to
    turn on."""
    client = make_api_account()
    add_holding(client, asset_name="SBI Deposit", asset_type="FD")
    holding = only_holding(client)

    response = client.patch(
        f"/api/v1/investments/{holding['id']}/pricing",
        headers=client.headers, json={"ticker": "", "auto_price": "1"})
    assert response.status_code == 200
    assert response.get_json()["auto_price"] is False
    assert only_holding(client)["auto_price"] is False


# --- turning it on ----------------------------------------------------------

def test_turning_it_on_prices_the_holding_immediately(make_api_account, feed):
    """Waiting until tonight to discover whether it worked is not feedback."""
    client = make_api_account()
    add_holding(client)
    holding = only_holding(client)

    response = client.patch(
        f"/api/v1/investments/{holding['id']}/pricing", headers=client.headers,
        json={"ticker": "reliance", "exchange": "NSE", "auto_price": "1"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["ticker"] == "RELIANCE", "stored as the API wants it"
    assert body["priced"] == 1

    after = only_holding(client)
    assert after["current_price"] == "1274.00"
    assert after["price_source"] == "stocksaathi"
    assert after["priced_at"] is not None


def test_a_symbol_that_returns_no_price_is_refused_with_the_field_named(
        make_api_account, feed):
    """Rather than saved and then silently never updated.

    A holding that believes it is being priced and is not is worse than one
    that was never switched on: the number on the screen looks live.
    """
    client = make_api_account()
    add_holding(client)
    holding = only_holding(client)

    response = client.patch(
        f"/api/v1/investments/{holding['id']}/pricing", headers=client.headers,
        json={"ticker": "NOSUCHCO", "auto_price": "1"})
    assert response.status_code == 422, response.get_json()
    assert "ticker" in response.get_json()["error"]["fields"]
    assert only_holding(client)["auto_price"] is False


def test_something_that_is_not_a_symbol_never_reaches_the_feed(
        make_api_account, feed):
    """Refused on shape, so a typed sentence does not cost a round trip."""
    client = make_api_account()
    add_holding(client)
    holding = only_holding(client)

    response = client.patch(
        f"/api/v1/investments/{holding['id']}/pricing", headers=client.headers,
        json={"ticker": "my shares", "auto_price": "1"})
    assert response.status_code == 422
    assert feed.asked == []


def test_a_symbol_can_be_recorded_without_being_fetched(make_api_account, feed):
    """The looser of the two standards: storing a ticker for reference is
    not the same as asking to be priced from it, and must not be blocked by
    a feed that happens to be down."""
    client = make_api_account()
    add_holding(client)
    holding = only_holding(client)
    feed.reachable = False

    response = client.patch(
        f"/api/v1/investments/{holding['id']}/pricing", headers=client.headers,
        json={"ticker": "RELIANCE", "auto_price": "0"})
    assert response.status_code == 200

    after = only_holding(client)
    assert after["ticker"] == "RELIANCE"
    assert after["auto_price"] is False
    assert after["current_price"] == "1200.00", "nothing was fetched"


# --- refreshing -------------------------------------------------------------

def switch_on(client, holding_id, ticker="RELIANCE"):
    response = client.patch(f"/api/v1/investments/{holding_id}/pricing",
                            headers=client.headers,
                            json={"ticker": ticker, "auto_price": "1"})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_refreshing_reprices_every_automatic_holding_at_once(
        make_api_account, feed):
    client = make_api_account()
    add_holding(client)
    add_holding(client, asset_name="TCS", current_price="2000.00")
    first, second = sorted(holdings_of(client), key=lambda h: h["asset_name"])
    switch_on(client, first["id"], "RELIANCE")
    switch_on(client, second["id"], "TCS")

    response = client.post("/api/v1/investments/refresh-prices",
                           headers=client.headers)
    assert response.status_code == 200
    assert response.get_json()["priced"] == 2

    prices = {h["asset_name"]: h["current_price"] for h in holdings_of(client)}
    assert prices == {"Reliance Industries": "1274.00", "TCS": "2204.10"}


def test_one_symbol_is_asked_for_once_however_many_hold_it(
        make_api_account, feed):
    """Two holdings of the same company are one question to the market."""
    client = make_api_account()
    add_holding(client)
    add_holding(client, asset_name="Reliance, second lot")
    for holding in holdings_of(client):
        switch_on(client, holding["id"], "RELIANCE")

    feed.asked.clear()
    assert client.post("/api/v1/investments/refresh-prices",
                       headers=client.headers).get_json()["priced"] == 2
    assert feed.asked == [["RELIANCE"]]


def test_a_feed_that_is_down_changes_nothing_and_says_so(
        make_api_account, feed):
    """Not an error. Somebody else's outage must not damage a portfolio or
    take a screen down; the holding keeps the last price it had."""
    client = make_api_account()
    add_holding(client)
    switch_on(client, only_holding(client)["id"])
    assert only_holding(client)["current_price"] == "1274.00"

    feed.reachable = False
    response = client.post("/api/v1/investments/refresh-prices",
                           headers=client.headers)
    assert response.status_code == 200
    assert response.get_json()["priced"] == 0
    assert only_holding(client)["current_price"] == "1274.00"


def test_refreshing_with_nothing_automatic_costs_no_fetch(
        make_api_account, feed):
    client = make_api_account()
    add_holding(client)
    assert client.post("/api/v1/investments/refresh-prices",
                       headers=client.headers).get_json()["priced"] == 0
    assert feed.asked == []


# --- turning it off ---------------------------------------------------------

def test_switching_off_keeps_the_last_fetched_price(make_api_account, feed):
    """It is still the best number anybody has.

    Reverting to whatever was typed in months ago would be a silent
    revaluation of the portfolio, performed by a checkbox.
    """
    client = make_api_account()
    add_holding(client)
    switch_on(client, only_holding(client)["id"])

    client.patch(f"/api/v1/investments/{only_holding(client)['id']}/pricing",
                 headers=client.headers, json={"ticker": "", "auto_price": "0"})

    after = only_holding(client)
    assert after["current_price"] == "1274.00"
    assert after["ticker"] is None
    assert after["auto_price"] is False
    assert after["price_source"] == "manual", \
        "the label must not still claim a feed that is switched off"


def test_a_switched_off_holding_is_not_repriced(make_api_account, feed):
    client = make_api_account()
    add_holding(client)
    holding_id = only_holding(client)["id"]
    switch_on(client, holding_id)
    client.patch(f"/api/v1/investments/{holding_id}/pricing",
                 headers=client.headers, json={"ticker": "", "auto_price": "0"})

    feed.prices["RELIANCE"] = "9999.00"
    assert client.post("/api/v1/investments/refresh-prices",
                       headers=client.headers).get_json()["priced"] == 0
    assert only_holding(client)["current_price"] == "1274.00"


# --- other people's holdings ------------------------------------------------

def test_one_account_cannot_reprice_another_accounts_holding(
        make_api_account, feed):
    """The property this whole suite exists for. A holding id is a small
    integer and guessing one is not difficult."""
    owner, stranger = make_api_account(), make_api_account()
    add_holding(owner)
    holding_id = only_holding(owner)["id"]

    response = stranger.patch(f"/api/v1/investments/{holding_id}/pricing",
                              headers=stranger.headers,
                              json={"ticker": "RELIANCE", "auto_price": "1"})
    assert response.status_code == 404
    assert only_holding(owner)["auto_price"] is False


def test_a_refresh_only_touches_the_account_that_asked(make_api_account, feed):
    owner, stranger = make_api_account(), make_api_account()
    add_holding(owner)
    switch_on(owner, only_holding(owner)["id"])
    add_holding(stranger)
    switch_on(stranger, only_holding(stranger)["id"])

    feed.prices["RELIANCE"] = "1500.00"
    assert owner.post("/api/v1/investments/refresh-prices",
                      headers=owner.headers).get_json()["priced"] == 1
    assert only_holding(owner)["current_price"] == "1500.00"
    assert only_holding(stranger)["current_price"] == "1274.00"


# --- the quotes endpoint ----------------------------------------------------

def test_quotes_needs_a_session(client):
    assert client.get("/api/v1/quotes?symbols=RELIANCE").status_code == 401


def test_quotes_sends_money_as_a_string_and_change_as_a_fraction(
        make_api_account, feed):
    """Money as a string for the same reason it is everywhere else, and the
    change untouched so it is turned into a percentage exactly once."""
    client = make_api_account()
    body = client.get("/api/v1/quotes?symbols=RELIANCE,TCS").get_json()
    assert body["items"]["RELIANCE"]["price"] == "1274.00"
    assert body["items"]["RELIANCE"]["change"] == -0.0039
    assert body["items"]["TCS"]["price"] == "2204.10"


def test_quotes_refuses_an_empty_or_oversized_request(make_api_account, feed):
    """Their ceiling is 80 a request, over which the response is not an
    error -- it is quietly short."""
    client = make_api_account()
    assert client.get("/api/v1/quotes?symbols=").status_code == 422
    too_many = ",".join(f"SYM{n}" for n in range(stocksaathi.MAX_SYMBOLS + 1))
    assert client.get(f"/api/v1/quotes?symbols={too_many}").status_code == 422
