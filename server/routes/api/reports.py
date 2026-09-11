"""The three aggregate reports.

Each takes the month as a query parameter rather than a path segment, since
the month is a filter on a report rather than an identifier for one.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ApiError
from server.routes.api import api
from server.routes.api.dashboard_payload import PNL_FIELDS, dashboard_payload
from server.validators import Validator

SPEND_FIELDS = ["category", "total"]
BUDGET_FIELDS = ["category", "limit", "actual", "difference",
                 "rollover_in", "rollover"]


def _requested_month():
    """The validated 'month' query parameter."""
    fields = Validator({"month": request.args.get("month")})
    month = fields.month()
    fields.raise_if_invalid()
    return month


@api.get("/reports/category-spend")
def category_spend():
    """Total expense per category for one month, biggest first."""
    user_id = require_user()
    rows = operations.category_wise_spend(user_id, _requested_month())
    return jsonify({"items": money.rows(SPEND_FIELDS, rows, money_places())})


@api.get("/reports/budget-vs-actual")
def budget_vs_actual():
    """Every budgeted category for one month, with the over/under difference."""
    user_id = require_user()
    rows = operations.budget_vs_actual(user_id, _requested_month())
    return jsonify({"items": money.rows(BUDGET_FIELDS, rows, money_places())})


@api.get("/reports/dashboard")
def dashboard():
    """Everything the opening screen shows, in one request.

    The client used to ask for the portfolio and the transactions separately.
    Both queries are quick; what is not quick is reaching the database, at
    roughly 200ms of handshake per request.
    """
    return jsonify(dashboard_payload(require_user(), money_places()))


@api.get("/reports/portfolio")
def portfolio():
    """Profit and loss per holding, plus the portfolio totals.

    The totals are summed here rather than in SQL because the rows are
    already being fetched -- a second aggregate query would be a second
    round trip to say something the client can already see.
    """
    user_id = require_user()
    rows = operations.portfolio_pnl(user_id)
    places = money_places()
    items = money.rows(PNL_FIELDS, rows, places)

    # By name, not by position: these indices shifted silently when the
    # query gained two columns, which is the exact failure money.row()
    # exists to avoid.
    value_at = PNL_FIELDS.index("current_value")
    pnl_at = PNL_FIELDS.index("pnl")
    total_value = sum((row[value_at] for row in rows), start=0)
    total_pnl = sum((row[pnl_at] for row in rows), start=0)
    return jsonify({
        "items": items,
        "totals": {
            "value": money.serialise(total_value, places),
            "pnl": money.serialise(total_pnl, places),
            "holdings": len(items),
        },
    })


TREND_FIELDS = ["month", "income", "expense"]
CASHFLOW_FIELDS = ["month", "net", "cumulative"]
NET_WORTH_FIELDS = ["month", "holdings", "cash", "net_worth"]
MERCHANT_FIELDS = ["payee", "times", "total"]


def _months():
    """The 'months' query parameter, bounded to something drawable.

    Out of range is clamped rather than refused: this only decides how much
    history a chart shows, and a chart is a poor place to answer a typo with
    an error message.
    """
    raw = (request.args.get("months") or "").strip()
    months = int(raw) if raw.isdigit() else operations.SERIES_MONTHS
    return max(1, min(months, 60))


@api.get("/reports/summary")
def summary():
    """Every figure the reporting screen draws, in one request.

    Seven queries, one connection, one round trip. Each query is quick;
    reaching Supabase at all is what costs, so asking separately would be
    most of a second and a half of waiting for the same answer.
    """
    user_id = require_user()
    places = money_places()
    found = operations.dashboard_summary(user_id, _months())
    if not found:
        # 503, not the 400 this used to be. Nothing about the request can
        # cause this -- the months parameter is validated above and every
        # other input is the session's -- so the only ways here are the
        # database being unreachable or the connection pool being busy.
        # Telling a client its request was bad when the server was simply
        # out of connections sends everybody looking in the wrong place,
        # and it is not retryable, which this is.
        raise ApiError("Could not build the summary.", code="summary_failed",
                       status=503)

    return jsonify({
        "this_month": {
            "income": money.serialise(found["this_month"]["income"], places),
            "expense": money.serialise(found["this_month"]["expense"], places),
            "net": money.serialise(found["this_month"]["net"], places),
            "transactions": found["this_month"]["transactions"],
        },
        "trend": money.rows(TREND_FIELDS, found["trend"], places),
        "cashflow": money.rows(CASHFLOW_FIELDS, found["cashflow"], places),
        "net_worth": money.rows(NET_WORTH_FIELDS, found["net_worth"], places),
        "merchants": money.rows(MERCHANT_FIELDS, found["merchants"], places),
        "spend_by_category": money.rows(SPEND_FIELDS, found["spend_by_category"],
                                        places),
    })


@api.get("/reports/trend")
def trend():
    """Income against expense, month by month."""
    user_id = require_user()
    rows = operations.monthly_trend(user_id, _months())
    return jsonify({"items": money.rows(TREND_FIELDS, rows, money_places())})


@api.get("/reports/cashflow")
def cashflow():
    """What was left over each month, and the running total of it."""
    user_id = require_user()
    rows = operations.cashflow_series(user_id, _months())
    return jsonify({"items": money.rows(CASHFLOW_FIELDS, rows, money_places())})


@api.get("/reports/net-worth")
def net_worth():
    """Holdings plus accumulated cash, at the end of each month."""
    user_id = require_user()
    rows = operations.net_worth_series(user_id, _months())
    return jsonify({"items": money.rows(NET_WORTH_FIELDS, rows, money_places())})


# How far back the comparison runs. A year, like every other series on the
# reporting screen, and as far as the upstream serves history anyway.
BENCHMARK_MONTHS = 12


@api.get("/reports/benchmark")
def benchmark():
    """This account's holdings against the market, both rebased to 100.

    Rebasing is what makes the two comparable at all: a basket worth
    180,000 and an ETF unit worth 267 share no axis until both are
    expressed as "what a hundred rupees became".

    The basket is valued at today's quantities in every month. Charting
    the portfolio's real value against an index would compare two
    different things -- buying more of something raises the value without
    the market moving, so a month of heavy saving reads as a month of
    spectacular returns.

    Answers with an empty series rather than an error when there is
    nothing to compare: an account holding only deposits has no market
    return, and that is a fact about the account, not a failure.
    """
    user_id = require_user()
    rows = operations.basket_against_benchmark(user_id, BENCHMARK_MONTHS)
    if len(rows) < 2:
        # One point is not a comparison, and zero is not a chart.
        return jsonify({"items": [], "benchmark": operations.BENCHMARK,
                        "benchmark_name": _benchmark_name()})

    first_basket = rows[0][1]
    first_market = rows[0][2]
    if not first_basket or not first_market:
        return jsonify({"items": [], "benchmark": operations.BENCHMARK,
                        "benchmark_name": _benchmark_name()})

    items = [{
        "month": month,
        # Two decimal places on an index, not on money: these are ratios,
        # and money.serialise would round them to the currency's scale --
        # which is zero places in yen, turning every point into 100.
        "basket": str(round(basket / first_basket * 100, 2)),
        "market": str(round(market / first_market * 100, 2)),
    } for month, basket, market in rows]

    return jsonify({"items": items, "benchmark": operations.BENCHMARK,
                    "benchmark_name": _benchmark_name()})


def _benchmark_name():
    """The ETF's own name, so no screen can call it "the NIFTY"."""
    known = operations.instruments_for([operations.BENCHMARK])
    return (known.get(operations.BENCHMARK) or {}).get("name")
