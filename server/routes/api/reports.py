"""The three aggregate reports.

Each takes the month as a query parameter rather than a path segment, since
the month is a filter on a report rather than an identifier for one.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ApiError
from server.routes.api import api
from server.routes.api.dashboard_payload import dashboard_payload
from server.validators import Validator

SPEND_FIELDS = ["category", "total"]
BUDGET_FIELDS = ["category", "limit", "actual", "difference"]
PNL_FIELDS = ["id", "asset_name", "asset_type", "buy_date", "buy_price",
              "current_price", "quantity", "pnl", "current_value"]



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
        raise ApiError("Could not build the summary.", code="summary_failed")

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
