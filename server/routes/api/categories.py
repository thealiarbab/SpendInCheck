"""Categories: the list every other resource points at."""

from flask import jsonify, request

from server import money, operations
from server.auth import require_user
from server.errors import ValidationError
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "name", "type"]
TYPES = ["Income", "Expense"]


@api.get("/categories")
def list_categories():
    """Every category belonging to the signed-in account."""
    user_id = require_user()
    return jsonify({"items": money.rows(FIELDS, operations.get_all_categories(user_id))})


@api.post("/categories")
def create_category():
    """Add a category."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    name = fields.text("name", max_length=50)
    kind = fields.choice("type", TYPES)
    fields.raise_if_invalid()

    if not operations.add_category(user_id, name, kind):
        # The unique constraint is per user, so the only ordinary reason to
        # land here is that this account already has a category by this name.
        raise ValidationError({"name": "You already have a category with that name."})
    return jsonify({"ok": True}), 201
