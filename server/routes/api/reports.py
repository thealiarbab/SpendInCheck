"""The three aggregate reports.

Each takes the month as a query parameter rather than a path segment, since
the month is a filter on a report rather than an identifier for one.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.routes.api import api
from server.routes.api.dashboard_payload import dashboard_payload
from server.validators import Validator

SPEND_FIELDS = ["category", "total"]
BUDGET_FIELDS = ["category", "limit", "actual", "difference"]
PNL_FIELDS = ["asset_name", "asset_type", "buy_price", "current_price", "quantity",
              "pnl", "current_value"]



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

    total_value = sum((row[6] for row in rows), start=0)
    total_pnl = sum((row[5] for row in rows), start=0)
    return jsonify({
        "items": items,
        "totals": {
            "value": money.serialise(total_value, places),
            "pnl": money.serialise(total_pnl, places),
            "holdings": len(items),
        },
    })
