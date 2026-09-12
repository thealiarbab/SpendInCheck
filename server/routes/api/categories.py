"""Categories: the list every other resource points at."""

from flask import jsonify, request

from server import money, operations
from server.auth import require_user
from server.errors import NotFound, ValidationError
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


@api.get("/categories/<int:category_id>/usage")
def category_usage(category_id):
    """How much points at this category, so a delete can say what it moves."""
    user_id = require_user()
    if not operations.category_exists(user_id, category_id):
        raise NotFound()
    return jsonify(operations.count_category_use(user_id, category_id))


@api.patch("/categories/<int:category_id>")
def rename_category(category_id):
    """Rename a category, or change whether it is income or expense."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    name = fields.text("name", max_length=50)
    kind = fields.choice("type", TYPES)
    fields.raise_if_invalid()

    if not operations.category_exists(user_id, category_id):
        raise NotFound()
    if not operations.rename_category(user_id, category_id, name, kind):
        raise ValidationError({"name": "You already have a category with that name."})
    return jsonify({"ok": True})


@api.delete("/categories/<int:category_id>")
def remove_category(category_id):
    """Delete a category, moving anything that points at it if asked.

    The target comes from the query string rather than a body: a DELETE with
    a body is poorly supported by enough intermediaries to be worth avoiding
    for one integer.
    """
    user_id = require_user()
    if not operations.category_exists(user_id, category_id):
        raise NotFound()

    reassign_to = request.args.get("reassign_to")
    if reassign_to is not None:
        fields = Validator({"reassign_to": reassign_to})
        reassign_to = fields.integer("reassign_to", minimum=1)
        fields.raise_if_invalid()
        _check_reassignment(user_id, category_id, reassign_to)
    else:
        use = operations.count_category_use(user_id, category_id)
        if use["transactions"] or use["budgets"]:
            raise ValidationError(
                {"reassign_to": "Choose where to move what is already filed here."},
                message=f"{use['transactions']} transactions and {use['budgets']} "
                        "budgets still point at this category.")

    if not operations.delete_category(user_id, category_id, reassign_to):
        raise NotFound()

    # Reassigning moves spending in and adds the two monthly limits together,
    # so the target's carried-in figures are derived from something that has
    # just changed twice over. The category being deleted needs nothing: its
    # budgets went with it.
    if reassign_to is not None:
        operations.refresh_rollover_for(user_id, reassign_to)
    return jsonify({"ok": True})


def _check_reassignment(user_id, category_id, reassign_to):
    """Refuse a target that would corrupt the rows being moved."""
    if reassign_to == category_id:
        raise ValidationError({"reassign_to": "Pick a different category."})

    categories = {row[0]: row[2] for row in operations.get_all_categories(user_id)}
    if reassign_to not in categories:
        raise ValidationError({"reassign_to": "No such category."})
    # A transaction carries its own Income/Expense marker, so moving expense
    # rows under an income category would leave every spend report counting
    # money that was never spent.
    if categories[reassign_to] != categories[category_id]:
        raise ValidationError(
            {"reassign_to": f"Must also be an {categories[category_id].lower()} category."})
