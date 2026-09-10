"""Accounts, their balances, and transfers between them.

Balances are computed by the query that lists the accounts, never stored,
so nothing here can hand back a figure that disagrees with the rows behind
it.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import money_places, require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator

FIELDS = ["id", "name", "kind", "opening_balance", "balance", "transactions",
          "archived"]


def _read_submission(payload):
    """Validate an account body and return its cleaned fields."""
    fields = Validator(payload)
    values = {
        "account_name": fields.text("name", max_length=60),
        "account_kind": fields.choice("kind", list(operations.ACCOUNT_KINDS)),
        # Zero is allowed and negative is meaningful: a credit card opens
        # owing money, and refusing that would force people to model a card
        # as something it is not.
        "opening_balance": fields.amount("opening_balance", required=False,
                                         allow_zero=True, allow_negative=True,
                                         places=money_places()),
    }
    fields.raise_if_invalid()
    if values["opening_balance"] is None:
        values["opening_balance"] = 0
    return values


@api.get("/accounts")
def list_accounts():
    """Every account with its balance.

    Archived accounts are included only when asked for, because the common
    case is a picker and a closed account is exactly what should not be
    offered there.
    """
    user_id = require_user()
    include = request.args.get("archived") == "1"
    rows = operations.list_accounts(user_id, include_archived=include)
    return jsonify({"items": money.rows(FIELDS, rows, money_places())})


@api.post("/accounts")
def create_account():
    """Open an account."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    account_id = operations.add_account(user_id, values["account_name"],
                                        values["account_kind"],
                                        values["opening_balance"])
    if account_id is None:
        raise ValidationError({"name": "You already have an account with that name."})
    return jsonify({"ok": True, "id": account_id}), 201


@api.patch("/accounts/<int:account_id>")
def edit_account(account_id):
    """Rename an account, change its kind, or correct its opening balance."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.account_exists(user_id, account_id):
        raise NotFound()
    if not operations.update_account(user_id, account_id, values["account_name"],
                                     values["account_kind"],
                                     values["opening_balance"]):
        raise ValidationError({"name": "You already have an account with that name."})
    return jsonify({"ok": True})


@api.post("/accounts/<int:account_id>/archive")
def archive_account(account_id):
    """Close an account, or reopen it.

    Separate from PATCH because it is a different act: editing an account is
    correcting a detail, archiving it is saying the money has gone somewhere
    else. Sending them through one endpoint means a form that forgets to
    include the flag silently reopens a closed account.
    """
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    archived = fields.choice("archived", ["1", "0"])
    fields.raise_if_invalid()

    if not operations.account_exists(user_id, account_id):
        raise NotFound()
    operations.set_archived(user_id, account_id, archived == "1")
    return jsonify({"ok": True})


@api.get("/accounts/<int:account_id>/usage")
def account_usage(account_id):
    """What sits on this account, so a delete can say what it will move."""
    user_id = require_user()
    if not operations.account_exists(user_id, account_id):
        raise NotFound()
    return jsonify(operations.count_account_use(user_id, account_id))


@api.delete("/accounts/<int:account_id>")
def remove_account(account_id):
    """Delete an account, moving its transactions first if asked.

    As with categories, the target rides in the query string rather than a
    body, and an account still holding rows is refused rather than silently
    taking its history with it.
    """
    user_id = require_user()
    if not operations.account_exists(user_id, account_id):
        raise NotFound()

    reassign_to = request.args.get("reassign_to")
    if reassign_to is not None:
        fields = Validator({"reassign_to": reassign_to})
        reassign_to = fields.integer("reassign_to", minimum=1)
        fields.raise_if_invalid()
        if reassign_to == account_id:
            raise ValidationError({"reassign_to": "Pick a different account."})
        if not operations.account_exists(user_id, reassign_to):
            raise ValidationError({"reassign_to": "No such account."})
    else:
        use = operations.count_account_use(user_id, account_id)
        if use["transactions"]:
            raise ValidationError(
                {"reassign_to": "Choose where to move what is filed here."},
                message=f"{use['transactions']} transactions still sit on this "
                        "account.")

    # The last account cannot go: every transaction needs somewhere to live,
    # and an account list with nothing in it is a ledger that cannot be
    # written to.
    if len(operations.list_accounts(user_id, include_archived=True)) <= 1:
        raise ValidationError({"account": "This is your only account."},
                              message="Keep at least one account.")

    if not operations.delete_account(user_id, account_id, reassign_to):
        raise NotFound()
    return jsonify({"ok": True})


@api.post("/accounts/transfer")
def create_transfer():
    """Move money between two of your own accounts.

    Answers with the transfer_group_id, which is what identifies the pair
    afterwards -- neither leg's transaction id means anything on its own.
    """
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    values = {
        "from_account_id": fields.integer("from_account_id", minimum=1),
        "to_account_id": fields.integer("to_account_id", minimum=1),
        "amount": fields.amount(places=money_places()),
        "txn_date": fields.past_date("date"),
        "description": fields.text("description", required=False, max_length=255),
    }
    fields.raise_if_invalid()

    if values["from_account_id"] == values["to_account_id"]:
        raise ValidationError({"to_account_id": "Pick a different account."})

    group = operations.transfer(user_id, values["from_account_id"],
                                values["to_account_id"], values["amount"],
                                values["txn_date"], values["description"])
    if group is None:
        # transfer() only writes when both accounts are this user's, so a
        # None return means one of the ids was not theirs to use. Both are
        # reported the same way, so neither confirms another account's ids.
        raise ValidationError({"from_account_id": "No such account."})
    return jsonify({"ok": True, "transfer_group": group}), 201


@api.delete("/transfers/<transfer_group>")
def remove_transfer(transfer_group):
    """Delete both legs of a transfer.

    Keyed by the group rather than by either transaction id: deleting one
    leg on its own would leave money that arrived from nowhere.
    """
    user_id = require_user()
    if operations.delete_transfer(user_id, transfer_group) == 0:
        raise NotFound()
    return jsonify({"ok": True})
