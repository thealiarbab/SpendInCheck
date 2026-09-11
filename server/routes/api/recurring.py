"""Recurring rules: rent, salary, the subscription nobody wants to retype.

A rule writes ordinary transactions marked with its id. It does not own
them: a materialised row can be edited or deleted like any other, and
changing the rule never rewrites what it already wrote.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "description", "amount", "type", "cadence", "day_of_month",
          "next_run_on", "ends_on", "paused", "category_id", "category",
          "account_id", "account", "written"]
TYPES = ["Income", "Expense"]


def _read_submission(payload):
    """Validate a rule body and return its cleaned fields."""
    fields = Validator(payload)
    values = {
        "description": fields.text("description", max_length=255),
        "category_id": fields.integer("category_id", minimum=1),
        "amount": fields.amount(places=money_places()),
        "txn_type": fields.choice("type", TYPES),
        "cadence": fields.choice("cadence", list(operations.CADENCES)),
        # Not past_date: a rule is usually set up for a date that has not
        # happened yet, which is the one thing a transaction may never be.
        "next_run_on": fields.date("next_run_on"),
        "ends_on": fields.date("ends_on", required=False),
        "day_of_month": fields.integer("day_of_month", required=False,
                                       minimum=1, maximum=31),
        "account_id": fields.integer("account_id", required=False, minimum=1),
    }
    fields.raise_if_invalid()

    if values["ends_on"] and values["ends_on"] < values["next_run_on"]:
        raise ValidationError({"ends_on": "Must be on or after the first run."})

    # A monthly or yearly rule with no day takes it from the first run, so
    # "monthly from the 5th" needs saying only once.
    if values["cadence"] in ("monthly", "yearly") and not values["day_of_month"]:
        values["day_of_month"] = values["next_run_on"].day
    return values


@api.get("/recurring")
def list_rules():
    """Every rule, soonest due first, paused ones last."""
    user_id = require_user()
    rows = operations.list_rules(user_id)
    return jsonify({"items": money.rows(FIELDS, rows, money_places())})


@api.post("/recurring")
def create_rule():
    """Set up a recurring transaction."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    rule_id = operations.add_rule(
        user_id, values["description"], values["category_id"], values["amount"],
        values["txn_type"], values["cadence"], values["next_run_on"],
        values["day_of_month"], values["account_id"], values["ends_on"])
    if rule_id is None:
        raise ValidationError({"category_id": "No such category."})
    return jsonify({"ok": True, "id": rule_id}), 201


@api.patch("/recurring/<int:rule_id>")
def edit_rule(rule_id):
    """Change a rule from here on.

    Rows it has already written keep the figures they were written with.
    The rent that went up in August is a fact about August, and rewriting
    history to match would make every past report disagree with what
    actually happened.
    """
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.rule_exists(user_id, rule_id):
        raise NotFound()
    if not operations.update_rule(
            user_id, rule_id, values["description"], values["category_id"],
            values["amount"], values["txn_type"], values["cadence"],
            values["next_run_on"], values["day_of_month"], values["account_id"],
            values["ends_on"]):
        raise ValidationError({"category_id": "No such category."})
    return jsonify({"ok": True})


@api.post("/recurring/<int:rule_id>/pause")
def pause_rule(rule_id):
    """Stop a rule firing, or start it again."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    paused = fields.choice("paused", ["1", "0"])
    fields.raise_if_invalid()

    if not operations.rule_exists(user_id, rule_id):
        raise NotFound()
    operations.set_rule_paused(user_id, rule_id, paused == "1")
    return jsonify({"ok": True})


@api.delete("/recurring/<int:rule_id>")
def remove_rule(rule_id):
    """Delete a rule. The transactions it wrote stay where they are."""
    user_id = require_user()
    if not operations.delete_rule(user_id, rule_id):
        raise NotFound()
    return jsonify({"ok": True})


@api.post("/recurring/run")
def run_now():
    """Post everything this account's rules currently owe.

    The same sweep the scheduler runs, scoped to one user. It exists
    because waiting until tomorrow to see whether a rule works is a poor
    way to find out that the date was wrong.
    """
    user_id = require_user()
    return jsonify(operations.materialise_due(user_id))
