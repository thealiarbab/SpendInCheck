"""Holdings and their current prices."""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ApiError, NotFound
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "asset_name", "asset_type", "buy_date", "buy_price", "quantity",
          "current_price"]
ASSET_TYPES = ["Stock", "Mutual Fund", "FD"]


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
    fields.raise_if_invalid()

    if not operations.add_investment(user_id, name, asset_type, buy_date,
                                     buy_price, quantity, current_price):
        raise ApiError("Could not add that holding.", code="create_failed")
    return jsonify({"ok": True}), 201


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
