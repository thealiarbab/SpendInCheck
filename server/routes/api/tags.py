"""Tags: the labels a transaction can carry any number of.

A category says what kind of spending a row is and there is exactly one.
Tags say everything else, and there can be none.
"""

from flask import jsonify, request

from server import money, operations
from server.auth import require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator, json_object

FIELDS = ["id", "name", "uses"]


@api.get("/tags")
def list_tags():
    """Every tag, most used first."""
    user_id = require_user()
    return jsonify({"items": money.rows(FIELDS, operations.list_tags(user_id))})


@api.post("/tags")
def create_tag():
    """Add a tag."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    name = fields.text("name", max_length=operations.MAX_TAG_LENGTH)
    fields.raise_if_invalid()

    tag_id = operations.add_tag(user_id, name)
    if tag_id is None:
        # Matching ignores case, so this fires for "Holiday" when "holiday"
        # exists -- which is the point, not a limitation.
        raise ValidationError({"name": "You already have that tag."})
    return jsonify({"ok": True, "id": tag_id}), 201


@api.patch("/tags/<int:tag_id>")
def rename_tag(tag_id):
    """Rename a tag, keeping every transaction that carries it."""
    user_id = require_user()
    fields = Validator(request.get_json(silent=True) or {})
    name = fields.text("name", max_length=operations.MAX_TAG_LENGTH)
    fields.raise_if_invalid()

    if not operations.tag_exists(user_id, tag_id):
        raise NotFound()
    if not operations.rename_tag(user_id, tag_id, name):
        raise ValidationError({"name": "You already have that tag."})
    return jsonify({"ok": True})


@api.delete("/tags/<int:tag_id>")
def remove_tag(tag_id):
    """Delete a tag.

    No reassignment question, unlike a category: a transaction with no tags
    is perfectly ordinary. The rows keep everything except the label.
    """
    user_id = require_user()
    if not operations.delete_tag(user_id, tag_id):
        raise NotFound()
    return jsonify({"ok": True})


@api.put("/transactions/<int:transaction_id>/tags")
def set_transaction_tags(transaction_id):
    """Replace the set of tags on one transaction.

    PUT rather than POST, and the whole set rather than one tag: the edit
    form shows every tag a row has, so what it submits is the state it wants,
    not an instruction to add. An empty list means "no tags", which has to be
    expressible.
    """
    user_id = require_user()
    payload = json_object(request.get_json(silent=True) or {})
    raw = payload.get("tag_ids")
    if not isinstance(raw, list):
        raise ValidationError({"tag_ids": "Send a list of tag ids."})

    tag_ids = []
    for value in raw:
        try:
            tag_ids.append(int(value))
        except (TypeError, ValueError):
            raise ValidationError({"tag_ids": "Tag ids must be whole numbers."})

    if not operations.set_transaction_tags(user_id, transaction_id, tag_ids):
        raise NotFound()
    return jsonify({"ok": True})
