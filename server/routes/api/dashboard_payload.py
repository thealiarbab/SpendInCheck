"""The opening screen's data, in the shape the client reads it.

Its own module because two endpoints return it and neither should own it:
GET /reports/dashboard, and POST /auth/demo, which folds it into the response
so that opening the demo does not cost a second round trip.

No routes are declared here, so nothing imports the blueprint and there is no
import cycle between the two modules that use it.
"""

from server import money, operations

PNL_FIELDS = ["asset_name", "asset_type", "buy_price", "current_price", "quantity",
              "pnl", "current_value"]
TRANSACTION_FIELDS = ["id", "date", "category", "amount", "type", "description"]

# How many recent rows the dashboard shows. More than fits on the screen is
# only weight on the wire.
RECENT_LIMIT = 8


def dashboard_payload(user_id, places=2):
    """Holdings, portfolio totals and the latest transactions.

    Both queries run against the request's own connection, so asking for all
    of it at once costs one trip to the database rather than two. Adds no SQL
    -- these are the same operations the separate endpoints call.

    `places` is the account currency's scale, passed in rather than read
    here so this stays a plain function of a user id and can be called
    outside a request.
    """
    holdings = operations.portfolio_pnl(user_id)
    recent = operations.get_all_transactions(user_id)[:RECENT_LIMIT]

    return {
        "portfolio": {
            "items": money.rows(PNL_FIELDS, holdings, places),
            "totals": {
                "value": money.serialise(sum((row[6] for row in holdings), start=0), places),
                "pnl": money.serialise(sum((row[5] for row in holdings), start=0), places),
                "holdings": len(holdings),
            },
        },
        "recent": money.rows(TRANSACTION_FIELDS, recent, places),
    }
