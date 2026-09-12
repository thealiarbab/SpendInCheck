"""Holdings, their current prices, and where those prices come from."""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ApiError, NotFound, ValidationError
from server.routes.api import api
from server.services import quote_snapshot, stocksaathi
from server.validators import Validator

FIELDS = ["id", "asset_name", "asset_type", "buy_date", "buy_price", "quantity",
          "current_price",
          # What the price can be fetched with, and whether it is being
          # fetched. ticker is null for anything nobody can quote -- a
          # deposit, an unlisted holding -- and that is the opt-in.
          "ticker", "exchange", "isin", "auto_price", "price_source",
          "priced_at"]
ASSET_TYPES = ["Stock", "Mutual Fund", "FD"]
EXCHANGES = ["NSE", "BSE"]


@api.get("/investments")
def list_investments():
    """Every holding, with the prices it was last valued at."""
    user_id = require_user()
    return jsonify({"items": money.rows(FIELDS, operations.get_all_investments(user_id),
                                    money_places())})


@api.post("/investments")
def create_investment():
    """Add a holding."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    places = money_places()
    name = fields.text("asset_name", max_length=100)
    asset_type = fields.choice("asset_type", ASSET_TYPES)
    buy_date = fields.past_date("buy_date")
    buy_price = fields.amount("buy_price", places=places)
    quantity = fields.quantity()
    # A holding entered before its first revaluation is worth what it cost.
    current_price = fields.amount("current_price", required=False,
                                  places=places) or buy_price
    ticker = fields.text("ticker", required=False, max_length=32)
    exchange = fields.choice("exchange", EXCHANGES, required=False)
    isin = fields.text("isin", required=False, max_length=12)
    auto = fields.choice("auto_price", ["1", "0"], required=False) == "1"
    fields.raise_if_invalid()

    symbol, found = _resolve_symbol(ticker, auto) if ticker else (None, None)
    if symbol is None:
        auto = False
    # The exchange the upstream names beats the one a form guessed at.
    exchange = (found or {}).get("exchange") or exchange

    if not operations.add_investment(user_id, name, asset_type, buy_date,
                                     buy_price, quantity, current_price,
                                     ticker=symbol, exchange=exchange,
                                     isin=isin or None, auto_price=auto):
        raise ApiError("Could not add that holding.", code="create_failed")
    return jsonify({"ok": True}), 201


def _resolve_symbol(ticker, must_quote):
    """The symbol as the API wants it, and what it turns out to be.

    Returns (symbol, instrument-or-None).

    The lookup is the closest this integration gets to the symbol search
    the plan wanted: their API has no endpoint that takes "reli" and
    suggests RELIANCE, but given a symbol it will say whose it is. That
    matters because somebody typing a ticker has no way to tell a correct
    guess from a wrong one that also exists -- RELIANCE, RELIABLE and
    RELINFRA are three different companies -- and a holding quietly
    tracking the wrong one still shows a plausible price every day.

    Two different standards, on purpose. A symbol stored but not fetched
    only has to look like one: somebody recording a ticker for their own
    reference should not be blocked because a feed is down. A symbol the
    holding is about to be *priced* from has to resolve to something,
    because the alternative is a holding that silently never updates and an
    owner who believes it does.
    """
    symbol = stocksaathi.normalise(ticker)
    if symbol is None:
        raise ValidationError(
            {"ticker": "That does not look like a symbol. Use the NSE code, "
                       "like RELIANCE."})

    found = stocksaathi.instrument(symbol)
    if found or not must_quote:
        return symbol, found

    # The lookup is the slower, richer endpoint, so a symbol it cannot
    # answer for might still be quotable -- their own outage should not
    # stop somebody switching on a symbol that works. Asking the quote
    # endpoint is the cheaper second opinion.
    if symbol not in stocksaathi.live_quotes([symbol]):
        raise ValidationError(
            {"ticker": "No price found for " + symbol + ". Check the symbol, "
                       "or leave automatic pricing off."})
    return symbol, None


def _described(found):
    """The instrument as the client shows it back, or None.

    Money as strings, like everywhere else. This is confirmation, not
    record: none of it is stored, because the name belongs to the company
    and asset_name belongs to whoever wrote it down.
    """
    if not found:
        return None
    places = money_places()
    return {
        "name": found["name"],
        "sector": found["sector"],
        "exchange": found["exchange"],
        "low_52w": money.serialise(found["low_52w"], places),
        "high_52w": money.serialise(found["high_52w"], places),
    }


@api.patch("/investments/<int:investment_id>/price")
def reprice_investment(investment_id):
    """Revalue one holding."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    price = fields.amount("current_price", places=money_places())
    fields.raise_if_invalid()

    if not operations.update_investment_price(user_id, investment_id, price):
        raise NotFound()
    return jsonify({"ok": True})


@api.delete("/investments/<int:investment_id>")
def remove_investment(investment_id):
    """Delete a holding."""
    user_id = require_user()
    if not operations.delete_investment(user_id, investment_id):
        raise NotFound()
    return jsonify({"ok": True})


@api.patch("/investments/<int:investment_id>/pricing")
def set_pricing(investment_id):
    """Point a holding at a market symbol, or stop pointing it at one.

    Its own endpoint rather than part of editing a holding, because it is a
    different act: an edit corrects what was bought, this decides whether a
    number on the screen is allowed to change without anybody touching it.

    Turning it on prices the holding immediately. Waiting until tonight to
    find out whether it worked is not feedback.
    """
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    ticker = fields.text("ticker", required=False, max_length=32)
    exchange = fields.choice("exchange", EXCHANGES, required=False)
    isin = fields.text("isin", required=False, max_length=12)
    auto = fields.choice("auto_price", ["1", "0"], required=False) == "1"
    fields.raise_if_invalid()

    if not operations.investment_exists(user_id, investment_id):
        raise NotFound()

    symbol, found = _resolve_symbol(ticker, auto) if ticker else (None, None)
    if symbol is None:
        auto = False
    exchange = (found or {}).get("exchange") or exchange

    if not operations.set_investment_pricing(user_id, investment_id, symbol,
                                             exchange, isin or None, auto):
        raise ApiError("Could not save that.", code="update_failed")

    if symbol:
        # So the holding has a line to draw from the moment it is tracked,
        # rather than being flat until tonight's run. A no-op for a symbol
        # somebody else already tracks, which is most of them.
        quote_snapshot.ensure_history(symbol)
        # The lookup has already happened -- it is how the symbol was
        # accepted -- so keeping its answer costs nothing and saves every
        # later screen from asking.
        quote_snapshot.describe(symbol, found)

    return jsonify({"ok": True, "ticker": symbol, "auto_price": auto,
                    "priced": _refresh(user_id) if auto else 0,
                    # So the screen can say which company that symbol turned
                    # out to be, rather than echoing back what was typed.
                    "instrument": _described(found)})


@api.post("/investments/refresh-prices")
def refresh_prices():
    """Fetch today's price for every holding that asked for one.

    A POST because it writes. It reports how many holdings were repriced,
    which is what lets the client say "4 updated" rather than silently
    redrawing and leaving somebody to compare figures they never memorised.
    """
    user_id = require_user()
    return jsonify({"priced": _refresh(user_id)})


def _refresh(user_id):
    """Price this account's automatic holdings. Returns how many changed.

    Deliberately forgiving: an unreachable feed returns no quotes, which
    writes nothing and reports zero. Nobody's portfolio is damaged by
    somebody else's outage, and each holding keeps the last price it had.
    """
    symbols = operations.symbols_to_price(user_id)
    if not symbols:
        return 0
    quotes = stocksaathi.live_quotes(symbols)
    return operations.apply_prices(
        {symbol: quote["price"] for symbol, quote in quotes.items()}, user_id)


@api.get("/quotes")
def quotes():
    """Current prices for the symbols asked for.

    The client fetches StockSaathi directly while a screen is open -- their
    API is CORS-open, and keeping Flask out of the tick path means a
    ticking screen does not bill a serverless invocation every few seconds.
    This is for what the browser cannot cover: a client whose direct call a
    network in the middle blocks, and anything that has to see the same
    number the server will write.
    """
    require_user()
    asked = [part for part in (request.args.get("symbols") or "").split(",")
             if part.strip()]
    if not asked:
        raise ValidationError({"symbols": "Name at least one symbol."})
    if len(asked) > stocksaathi.MAX_SYMBOLS:
        raise ValidationError(
            {"symbols": "At most " + str(stocksaathi.MAX_SYMBOLS) +
                        " at a time."})

    places = money_places()
    return jsonify({"items": {
        symbol: {
            "price": money.serialise(quote["price"], places),
            # serialise already maps None to None, so an absent previous
            # close stays absent rather than arriving as "0.00".
            "prev_close": money.serialise(quote["prev_close"], places),
            # The fraction, untouched. The client turns it into a
            # percentage, in one place.
            "change": quote["change"],
            "as_of": quote["as_of"],
            "source": quote["source"],
        }
        for symbol, quote in stocksaathi.live_quotes(asked).items()
    }})


# How much of a holding's recent past the sparkline shows. Thirty days is
# about a month of trading, which is enough to read a direction from and
# short enough that a thumbnail is not a smear.
SPARK_DAYS = 30


@api.get("/investments/history")
def holdings_history():
    """Recent closes, and what each symbol is.

    Both from this app's own tables, which means no call to StockSaathi at
    all: the nightly snapshot has already written them down, and drawing a
    chart should not depend on somebody else's server being up. Two
    statements for every symbol on the screen, rather than two requests per
    holding -- and the instrument lookup in particular takes three seconds
    cold, which is why no screen may make it.

    Money as strings, like everywhere else.
    """
    user_id = require_user()
    places = money_places()
    held = operations.symbols_held(user_id)
    series = operations.recent_closes(held, days=SPARK_DAYS)
    known = operations.instruments_for(held)
    return jsonify({
        "items": {
            ticker: [{"date": on_date.isoformat(),
                      "close": money.serialise(close, places)}
                     for on_date, close in closes]
            for ticker, closes in series.items()
        },
        # What each symbol is, from the same request. A separate endpoint
        # for four fields that change once a day would be a third round
        # trip on a screen that already justifies its second.
        "instruments": {
            ticker: {"name": facts["name"], "sector": facts["sector"],
                     "exchange": facts["exchange"],
                     "low_52w": money.serialise(facts["low_52w"], places),
                     "high_52w": money.serialise(facts["high_52w"], places)}
            for ticker, facts in known.items()
        },
    })


# How many suggestions a list under a text box can usefully hold. Beyond
# about this many nobody reads them, and the point is to save a guess, not
# to offer a directory.
MAX_SUGGESTIONS = 8

# Below two characters every fragment matches hundreds of rows and none of
# them is a suggestion.
MIN_SEARCH = 2


@api.get("/symbols/search")
def search_symbols():
    """Suggest a symbol from a fragment somebody is typing.

    Served from our own instruments table rather than from StockSaathi.
    Their instrument master is the same NSE list, but it sits behind row
    level security with no anon policy -- correct of them, since an
    anon-readable master is a scrape waiting to happen -- so reading it
    would have meant a new endpoint in a different product's repository and
    a second production deploy to keep in step with this one.

    scripts/sync_instruments.py seeds the same universe from NSE's own
    published list instead, which leaves this app owning its own
    autocomplete and waiting on nobody.

    Behind require_user for the same reason their version guards the table:
    2,292 rows of instrument master is worth scraping, and an endpoint that
    hands it out two letters at a time to anybody is how it leaves. A
    signed-in account, a two-character minimum and eight rows is the
    controlled way through.

    A fragment shorter than the minimum is an empty list, not a 422. This
    runs on a keystroke, and the first letter of every search is not a
    client error.
    """
    require_user()
    term = (request.args.get("q") or "").strip()
    if len(term) < MIN_SEARCH:
        return jsonify({"items": []})

    rows = operations.search_instruments(term, limit=MAX_SUGGESTIONS)
    return jsonify({"items": [
        {"symbol": ticker, "name": name, "exchange": exchange,
         "sector": sector, "isin": isin}
        for ticker, name, exchange, sector, isin in rows
    ]})
