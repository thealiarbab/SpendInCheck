"""The opening screen's data, in the shape the client reads it.

Its own module because two endpoints return it and neither should own it:
GET /reports/dashboard, and POST /auth/demo, which folds it into the response
so that opening the demo does not cost a second round trip.

No routes are declared here, so nothing imports the blueprint and there is no
import cycle between the two modules that use it.
"""

from server import money, operations

PNL_FIELDS = ["id", "asset_name", "asset_type", "buy_date", "buy_price",
              "current_price", "quantity", "pnl", "current_value"]
TRANSACTION_FIELDS = ["id", "date", "category", "amount", "type", "description"]

VALUE_AT = PNL_FIELDS.index("current_value")
PNL_AT = PNL_FIELDS.index("pnl")

# How many recent rows the dashboard shows. More than fits on the screen is
# only weight on the wire.
RECENT_LIMIT = 8


def dashboard_payload(user_id, places=2):
    """Holdings, portfolio totals and the latest transactions.

    Both queries run against the request's own connection, so asking for all
    of it at once costs one trip to the database rather than two. Adds no SQL
    -- these are the same operations the separate endpoints call, and the
    ledger one is asked for exactly the rows the screen shows.

    `places` is the account currency's scale, passed in rather than read
    here so this stays a plain function of a user id and can be called
    outside a request.
    """
    holdings = operations.portfolio_pnl(user_id)
    # Asked for eight, not asked for two hundred and sliced to eight. The
    # ledger query carries a tag lookup per row, so the slice was paying for
    # 192 rows of work and wire that nothing ever read.
    recent, _ = operations.search_transactions(user_id, per_page=RECENT_LIMIT)

    return {
        "portfolio": {
            "items": money.rows(PNL_FIELDS, holdings, places),
            "totals": {
                # By name, not by position -- see the same note in reports.py.
                "value": money.serialise(
                    sum((row[VALUE_AT] for row in holdings), start=0), places),
                "pnl": money.serialise(
                    sum((row[PNL_AT] for row in holdings), start=0), places),
                "holdings": len(holdings),
            },
        },
        "recent": money.rows(TRANSACTION_FIELDS, recent, places),
    }
