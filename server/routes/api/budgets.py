"""Monthly spending limits, one per category per month."""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import ValidationError
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "category", "month", "limit", "rollover", "rollover_in",
          "category_id"]


@api.get("/budgets")
def list_budgets():
    """Every budget the account has set, across all months."""
    user_id = require_user()
    return jsonify({"items": money.rows(FIELDS, operations.get_all_budgets(user_id),
                                    money_places())})


@api.put("/budgets")
def set_budget():
    """Create or replace the limit for one category in one month.

    PUT rather than POST: a category has at most one budget per month, so
    sending the same body twice must leave the same single row rather than
    adding a second. The underlying query upserts on that pair.
    """
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    category_id = fields.integer("category_id", minimum=1)
    month = fields.month()
    limit = fields.amount("limit", places=money_places())
    # Off unless asked for. Rollover changes what a limit means, and a
    # budget that quietly carried last month's overspend into this one
    # would be a limit nobody set.
    rollover = fields.choice("rollover", ["1", "0"], required=False) == "1"
    fields.raise_if_invalid()

    if not operations.set_budget(user_id, category_id, month, limit, rollover):
        raise ValidationError({"category_id": "No such category."})
    return jsonify({"ok": True})
