"""The opening screen's data, in the shape the client reads it.

Its own module because two endpoints return it and neither should own it:
GET /reports/dashboard, and POST /auth/demo, which folds it into the response
so that opening the demo does not cost a second round trip.

No routes are declared here, so nothing imports the blueprint and there is no
import cycle between the two modules that use it.
"""

from server import money, operations

# The shape of a holdings row, everywhere one is serialised. reports.py
# imports it from here rather than keeping a second copy: the two drifted
# apart once already, and a FIELDS list that is short by a column does not
# fail -- zip() just drops the column on the floor.
PNL_FIELDS = ["id", "asset_name", "asset_type", "buy_date", "buy_price",
              "current_price", "quantity", "pnl", "current_value",
              "ticker", "exchange", "auto_price", "price_updated_at"]
TRANSACTION_FIELDS = ["id", "date", "category", "amount", "type", "description"]

VALUE_AT = PNL_FIELDS.index("current_value")
PNL_AT = PNL_FIELDS.index("pnl")

# How many recent rows the dashboard shows. More than fits on the screen is
# only weight on the wire.
RECENT_LIMIT = 8


def dashboard_payload(user_id, places=2):
    """Holdings, portfolio totals and the latest transactions.

    One round trip for the whole payload. The two lists are fetched by a
    single statement composed from the same pieces the separate endpoints
    use, and it asks for exactly the eight rows the screen shows rather than
    two hundred to be sliced.

    `places` is the account currency's scale, passed in rather than read
    here so this stays a plain function of a user id and can be called
    outside a request.
    """
    # One statement for both lists. They are independent, which is exactly
    # why they can share a round trip -- and a round trip to Mumbai costs
    # more than either query does.
    recent, holdings = operations.recent_and_holdings(user_id, RECENT_LIMIT)

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
