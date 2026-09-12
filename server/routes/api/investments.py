"""Holdings, their current prices, and where those prices come from."""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ApiError, NotFound, ValidationError
from server.routes.api import api
from server.services import amfi, quote_snapshot, stocksaathi
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
    # The last resort, not the intent. A holding with a symbol is priced
    # from StockSaathi a few lines below and this is overwritten before the
    # response; a holding without one has nothing else to be worth. What
    # this must not become again is an assumption: the app has no idea when
    # anybody bought, so "you bought it today" is wrong for every holding
    # entered from a statement, and it was wrong silently.
    current_price = fields.amount("current_price", required=False,
                                  places=places) or buy_price
    ticker = fields.text("ticker", required=False, max_length=32)
    exchange = fields.choice("exchange", EXCHANGES, required=False)
    isin = fields.text("isin", required=False, max_length=12)
    requested_auto = fields.choice("auto_price", ["1", "0"], required=False)
    fields.raise_if_invalid()

    # **A symbol is the opt-in.** There is no other reason to attach one:
    # nothing else in this app reads a ticker, so a holding that carries one
    # and is not priced by it is a stale number sitting next to the means of
    # correcting itself. The form used to send auto_price="0" always, which
    # is exactly the holding that produced -- somebody typed RELIANCE, saved,
    # and was still shown what they paid for it.
    #
    # Absent is distinguished from "0" on purpose. An explicit "0" is
    # somebody saying no, and still means no.
    auto = requested_auto != "0" if ticker else requested_auto == "1"

    symbol, found, kind = (_resolve_symbol(ticker, auto) if ticker
                           else (None, None, "equity"))
    if symbol is None:
        auto = False
    # The exchange the upstream names beats the one a form guessed at, and a
    # fund has none at all.
    exchange = None if kind == "fund" else ((found or {}).get("exchange") or exchange)
    isin = (found or {}).get("isin") or isin

    if not operations.add_investment(user_id, name, asset_type, buy_date,
                                     buy_price, quantity, current_price,
                                     ticker=symbol, exchange=exchange,
                                     isin=isin or None, auto_price=auto,
                                     kind=kind):
        raise ApiError("Could not add that holding.", code="create_failed")

    # Everything set_pricing does when a symbol is attached to a holding
    # that already exists. These were two ways to do one thing and only one
    # of them worked: attaching a symbol here left the holding undescribed,
    # with no history to draw and priced at what it cost, until somebody
    # noticed and clicked the button that does it properly.
    if symbol:
        quote_snapshot.ensure_history(symbol, kind=kind)
        quote_snapshot.describe(symbol, found)

    return jsonify({"ok": True, "ticker": symbol, "kind": kind,
                    "auto_price": auto,
                    "priced": _refresh(user_id) if auto else 0,
                    "instrument": _described(found)}), 201


def _resolve_symbol(ticker, must_quote):
    """The symbol as the API wants it, and what it turns out to be.

    Returns (symbol, instrument-or-None, kind).

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
    # Our own table first, and this is what makes saving a symbol fast.
    #
    # It used to ask StockSaathi's fundamentals endpoint whether the symbol
    # existed, which their own docstring calls "up to three seconds cold",
    # on the path somebody is watching a spinner on. That was the right
    # design when this database knew nothing about symbols. It now holds
    # every NSE equity and every AMFI scheme -- 40,174 rows, seeded from the
    # exchange and from AMFI -- so the question "is this a real symbol, and
    # whose is it" is a primary key lookup against a table in the same
    # region, not a round trip to somebody else's server.
    #
    # The upstream is still asked for anything the seed does not cover, so a
    # symbol listed this morning still works; it is just no longer the
    # common path.
    known = operations.instruments_for([str(ticker).strip().upper()])
    local = known.get(str(ticker).strip().upper())
    if local and local.get("name"):
        return local["symbol"], local, local.get("kind") or "equity"

    # A fund next, because the two namespaces cannot overlap: no NSE
    # equity ticker is purely numeric and no AMFI code is anything else.
    # Checked against both lists rather than assumed -- see migration 016.
    code = amfi.normalise(ticker)
    if code is not None:
        scheme = amfi.scheme(code)
        if scheme:
            return code, scheme, "fund"
        if not must_quote:
            return code, None, "fund"
        raise ValidationError(
            {"ticker": "No fund found with code " + code + ". Pick one from "
                       "the suggestions, or leave automatic pricing off."})

    symbol = stocksaathi.normalise(ticker)
    if symbol is None:
        raise ValidationError(
            {"ticker": "That does not look like a symbol. Use the NSE code, "
                       "like RELIANCE, or an AMFI scheme code for a fund."})

    found = stocksaathi.instrument(symbol)
    if found or not must_quote:
        return symbol, found, "equity"

    # The lookup is the slower, richer endpoint, so a symbol it cannot
    # answer for might still be quotable -- their own outage should not
    # stop somebody switching on a symbol that works. Asking the quote
    # endpoint is the cheaper second opinion.
    if symbol not in stocksaathi.live_quotes([symbol]):
        raise ValidationError(
            {"ticker": "No price found for " + symbol + ". Check the symbol, "
                       "or leave automatic pricing off."})
    return symbol, None, "equity"


def _described(found):
    """The instrument as the client shows it back, or None.

    Money as strings, like everywhere else. This is confirmation, not
    record: none of it is stored, because the name belongs to the company
    and asset_name belongs to whoever wrote it down.
    """
    if not found:
        return None
    places = money_places()
    # .get throughout, not indexing: a fund and a share are described by
    # overlapping but different facts. A scheme has a fund house and a NAV
    # and no 52-week range; a share has the range and no house. Indexing
    # would make every fund a KeyError on the screen that confirms it.
    return {
        "name": found.get("name"),
        "sector": found.get("sector"),
        "exchange": found.get("exchange"),
        "fund_house": found.get("fund_house"),
        "low_52w": money.serialise(found.get("low_52w"), places),
        "high_52w": money.serialise(found.get("high_52w"), places),
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

    symbol, found, kind = (_resolve_symbol(ticker, auto) if ticker
                           else (None, None, "equity"))
    if symbol is None:
        auto = False
    exchange = (found or {}).get("exchange") or exchange
    # A fund has no exchange and never will. Left as whatever was submitted
    # it would put "NSE" beside a scheme that does not trade on one.
    if kind == "fund":
        exchange = None
    isin = (found or {}).get("isin") or isin

    if not operations.set_investment_pricing(user_id, investment_id, symbol,
                                             exchange, isin or None, auto,
                                             kind):
        raise ApiError("Could not save that.", code="update_failed")

    if symbol:
        # So the holding has a line to draw from the moment it is tracked,
        # rather than being flat until tonight's run. A no-op for a symbol
        # somebody else already tracks, which is most of them.
        quote_snapshot.ensure_history(symbol, kind=kind)
        # The lookup has already happened -- it is how the symbol was
        # accepted -- so keeping its answer costs nothing and saves every
        # later screen from asking.
        quote_snapshot.describe(symbol, found)

    return jsonify({"ok": True, "ticker": symbol, "kind": kind,
                    "auto_price": auto,
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
    tracked = operations.symbols_to_price(user_id)
    if not tracked:
        return 0

    # Split by feed before asking either. A share is quoted intraday by
    # StockSaathi; a fund has a NAV published once each evening by AMFI, and
    # sending one to the other's endpoint gets a confident nothing back.
    shares = [ticker for ticker, kind in tracked if kind != "fund"]
    funds = [ticker for ticker, kind in tracked if kind == "fund"]

    prices = {}
    if shares:
        prices.update({symbol: quote["price"]
                       for symbol, quote in stocksaathi.live_quotes(shares).items()})
    if funds:
        prices.update(amfi.latest_navs(funds))

    return operations.apply_prices(prices, user_id) if prices else 0


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

    **The list is StockSaathi's**, and that is now literally rather than
    aspirationally true. scripts/sync_instruments.py seeds this table from
    the universe they publish -- 4,367 shares and ETFs with sectors, and
    13,969 curated schemes with fund houses -- so what this serves is their
    list, ranked and served from our own region.

    This briefly asked their /api/search per keystroke instead, and that was
    the wrong shape three times over: the endpoint is written but never
    deployed, it selects a column their table does not have, and the table
    it reads is empty because their own sync has never filled it. Their
    product does not use it either -- it loads the same published files this
    seeds from. A daily seed of their canonical list beats a live call to a
    path nothing maintains.

    Behind require_user for the reason their own search guards the master:
    an instrument list is worth scraping, and an endpoint that hands it out
    two letters at a time to anybody is how it leaves. A signed-in account,
    a two-character minimum and eight rows is the controlled way through.

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
        # kind rides along because the client cannot tell from the
        # identifier alone: "118989" is a fund and "RELIANCE" is a share,
        # and guessing that from whether it is all digits is exactly the
        # inference migration 016 added the column to avoid.
        {"symbol": ticker, "name": name, "exchange": exchange,
         "sector": sector, "isin": isin, "kind": kind}
        for ticker, name, exchange, sector, isin, kind in rows
    ]})


@api.get("/symbols/interpret")
def interpret_symbol():
    """Which instrument a phrase probably means, in words, from StockSaathi's AI.

    A second, slower opinion on the same query /symbols/search just
    answered. Separate endpoint on purpose: the list has to be instant
    because it renders under a cursor, and this takes 1.5 to 4 seconds
    because there is a language model behind it. One endpoint doing both
    would make every keystroke wait for the slow half.

    So the client shows the ranked list immediately and asks this
    afterwards, and the answer arrives as a sentence confirming which one
    it thinks was meant. Nothing depends on it: if it never answers, the
    list is exactly what it was.

    **The database proposes and the model only chooses.** Candidates come
    from our own ranked search and their endpoint can only return symbols
    it was given -- checked again on this side. An instrument search that
    asked a model to recall tickers unaided would be a machine for
    inventing plausible wrong ones, and a holding pointed at a plausible
    wrong ticker prices itself convincingly every day.
    """
    require_user()
    term = (request.args.get("q") or "").strip()
    if len(term) < MIN_SEARCH:
        return jsonify({"symbols": [], "why": ""})

    rows = operations.search_instruments(term, limit=MAX_SUGGESTIONS)
    if not rows:
        return jsonify({"symbols": [], "why": ""})

    offered = [row[0] for row in rows]
    read = stocksaathi.recognise(term, [
        {"symbol": ticker, "name": name, "sector": sector}
        for ticker, name, _exchange, sector, _isin, _kind in rows])
    if not read:
        return jsonify({"symbols": [], "why": ""})

    # Filtered here as well as in the service. Both sides check the same
    # thing on purpose: the rule is that only a symbol this database
    # proposed may be named, and a rule enforced in exactly one place is one
    # refactor away from being enforced nowhere.
    known = [symbol for symbol in read["symbols"] if symbol in offered]
    if not known:
        return jsonify({"symbols": [], "why": ""})
    return jsonify({"symbols": known, "why": read["why"]})
