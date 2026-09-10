"""Savings goals and what has been put towards them.

Progress is summed on every read rather than stored, so a goal can never
report a total its contributions do not add up to.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "name", "target", "target_date", "account_id", "account",
          "saved", "contributions", "archived"]
CONTRIBUTION_FIELDS = ["id", "date", "amount", "note"]


def _read_submission(payload):
    """Validate a goal body and return its cleaned fields."""
    fields = Validator(payload)
    values = {
        "goal_name": fields.text("name", max_length=60),
        "target_amount": fields.amount("target", places=money_places()),
        # Both optional. A goal with no deadline is a real goal, and one
        # with no account is a goal you have not decided where to keep yet.
        "target_date": fields.date("target_date", required=False),
        "account_id": fields.integer("account_id", required=False, minimum=1),
    }
    fields.raise_if_invalid()
    return values


@api.get("/goals")
def list_goals():
    """Every goal with its progress, unreached ones first."""
    user_id = require_user()
    include = request.args.get("archived") == "1"
    rows = operations.list_goals(user_id, include_archived=include)
    return jsonify({"items": money.rows(FIELDS, rows, money_places())})


@api.post("/goals")
def create_goal():
    """Set a goal."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    goal_id = operations.add_goal(user_id, values["goal_name"],
                                  values["target_amount"], values["target_date"],
                                  values["account_id"])
    if goal_id is None:
        # Either the name is taken or the account was not theirs. The name is
        # by far the likelier of the two from a form that only offers their
        # own accounts, so it is what the message names.
        raise ValidationError({"name": "You already have a goal with that name."})
    return jsonify({"ok": True, "id": goal_id}), 201


@api.patch("/goals/<int:goal_id>")
def edit_goal(goal_id):
    """Change a goal's name, target, deadline or account."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.goal_exists(user_id, goal_id):
        raise NotFound()
    if not operations.update_goal(user_id, goal_id, values["goal_name"],
                                  values["target_amount"], values["target_date"],
                                  values["account_id"]):
        raise ValidationError({"name": "You already have a goal with that name."})
    return jsonify({"ok": True})


@api.post("/goals/<int:goal_id>/archive")
def archive_goal(goal_id):
    """Put a goal aside, or bring it back."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    archived = fields.choice("archived", ["1", "0"])
    fields.raise_if_invalid()

    if not operations.goal_exists(user_id, goal_id):
        raise NotFound()
    operations.set_goal_archived(user_id, goal_id, archived == "1")
    return jsonify({"ok": True})


@api.delete("/goals/<int:goal_id>")
def remove_goal(goal_id):
    """Delete a goal and everything put towards it.

    No reassignment question, unlike a category or an account: a
    contribution towards a goal that no longer exists means nothing.
    """
    user_id = require_user()
    if not operations.delete_goal(user_id, goal_id):
        raise NotFound()
    return jsonify({"ok": True})


@api.get("/goals/<int:goal_id>/contributions")
def list_contributions(goal_id):
    """What has been put towards one goal, newest first."""
    user_id = require_user()
    if not operations.goal_exists(user_id, goal_id):
        raise NotFound()
    rows = operations.list_contributions(user_id, goal_id)
    return jsonify({"items": money.rows(CONTRIBUTION_FIELDS, rows, money_places())})


@api.post("/goals/<int:goal_id>/contributions")
def add_contribution(goal_id):
    """Set money aside towards a goal, or take some back out.

    A negative amount is a withdrawal, which is why this accepts one where
    a transaction would not: a transaction carries its direction in its
    type, and a contribution carries it in its sign.
    """
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    values = {
        "amount": fields.amount(places=money_places(), allow_negative=True),
        "contributed_on": fields.past_date("date"),
        "note": fields.text("note", required=False, max_length=255),
    }
    fields.raise_if_invalid()

    if values["amount"] == 0:
        raise ValidationError({"amount": "Must not be zero."})

    contribution_id = operations.add_contribution(
        user_id, goal_id, values["amount"], values["contributed_on"], values["note"])
    if contribution_id is None:
        raise NotFound()
    return jsonify({"ok": True, "id": contribution_id}), 201


@api.delete("/contributions/<int:contribution_id>")
def remove_contribution(contribution_id):
    """Remove one contribution. The goal keeps everything else."""
    user_id = require_user()
    if not operations.delete_contribution(user_id, contribution_id):
        raise NotFound()
    return jsonify({"ok": True})
