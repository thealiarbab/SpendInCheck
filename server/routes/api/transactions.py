"""The transaction ledger.

The list and the single-record endpoints deliberately return different
shapes. The list carries category_name, because that is what a table shows;
the single record carries category_id, because that is what an edit form
needs to preselect a dropdown.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator

LIST_FIELDS = ["id", "date", "category", "amount", "type", "description"]
RECORD_FIELDS = ["id", "date", "category_id", "amount", "type", "description"]
TYPES = ["Income", "Expense"]


def _read_submission(payload):
    """Validate a transaction body and return its cleaned fields."""
    fields = Validator(payload)
    places = money_places()
    values = {
        "txn_date": fields.past_date("date"),
        "category_id": fields.integer("category_id", minimum=1),
        "amount": fields.amount(places=places),
        "txn_type": fields.choice("type", TYPES),
        "description": fields.text("description", required=False, max_length=255),
    }
    fields.raise_if_invalid()
    return values


@api.get("/transactions")
def list_transactions():
    """Every transaction, newest first."""
    user_id = require_user()
    rows = operations.get_all_transactions(user_id)
    return jsonify({"items": money.rows(LIST_FIELDS, rows, money_places())})


@api.get("/transactions/<int:transaction_id>")
def read_transaction(transaction_id):
    """One transaction, in the shape an edit form needs."""
    user_id = require_user()
    record = operations.get_transaction_by_id(user_id, transaction_id)
    if record is None:
        raise NotFound()
    return jsonify(money.row(RECORD_FIELDS, record, money_places()))


@api.post("/transactions")
def create_transaction():
    """Record a transaction."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.add_transaction(user_id, values["txn_date"], values["category_id"],
                                      values["amount"], values["txn_type"],
                                      values["description"]):
        # add_transaction only writes when the category belongs to this user,
        # so a false return means the id was not theirs to use.
        raise ValidationError({"category_id": "No such category."})
    return jsonify({"ok": True}), 201


@api.patch("/transactions/<int:transaction_id>")
def edit_transaction(transaction_id):
    """Replace a transaction's fields."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.update_transaction(user_id, transaction_id, values["txn_date"],
                                         values["category_id"], values["amount"],
                                         values["txn_type"], values["description"]):
        # Either the transaction is not theirs or the category is not; both
        # answer the same way, so neither confirms another account's ids.
        raise NotFound()
    return jsonify({"ok": True})


@api.delete("/transactions/<int:transaction_id>")
def remove_transaction(transaction_id):
    """Delete a transaction."""
    user_id = require_user()
    if not operations.delete_transaction(user_id, transaction_id):
        raise NotFound()
    return jsonify({"ok": True})
