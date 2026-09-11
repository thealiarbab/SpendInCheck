"""Importing a CSV of transactions.

Two endpoints, and the split between them is the whole safety story.
/import/examine parses and reports without writing anything;
/import/commit writes what the reader has seen and approved.
"""

from flask import jsonify, request

from server import operations
from server.auth import require_user
from server.errors import ValidationError
from server.routes.api import api
from server.validators import Validator

# Enough for a few thousand rows of statement, small enough that a
# mistyped upload cannot occupy the request for long.
MAX_BYTES = 2 * 1024 * 1024


def _known_categories(user_id):
    """{lowercased name: (id, type)} for matching names out of a file."""
    return {name.strip().lower(): (category_id, kind)
            for category_id, name, kind in operations.get_all_categories(user_id)}


def _read_text(payload):
    """The CSV text from the request body, validated for size."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError({"text": "Paste or upload a CSV first."})
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValidationError(
            {"text": f"Too large. The limit is {MAX_BYTES // (1024 * 1024)}MB."})
    return text


@api.post("/import/examine")
def examine_import():
    """Say what a CSV would import. Writes nothing.

    Answers with every row, importable or not, and the reason for each one
    that is not -- somebody deciding whether to import three hundred rows
    needs to see the four that will be skipped before they decide, not
    afterwards.
    """
    user_id = require_user()
    payload = request.get_json(silent=True) or {}
    text = _read_text(payload)

    fields = Validator(payload)
    fallback = fields.integer("default_category_id", required=False, minimum=1)
    fields.raise_if_invalid()

    categories = _known_categories(user_id)
    if fallback is not None and fallback not in {c[0] for c in categories.values()}:
        raise ValidationError({"default_category_id": "No such category."})

    found = operations.examine(text, categories, fallback)
    usable = [row for row in found["rows"] if "skip" not in row]
    return jsonify({
        "columns": sorted(found["columns"]),
        "rows": found["rows"],
        "problems": found["problems"],
        "summary": {
            "readable": len(usable),
            "skipped": len(found["rows"]) - len(usable),
        },
    })


@api.post("/import/commit")
def commit_import():
    """Write the rows an examine returned.

    Takes the examined rows back rather than re-parsing the file. That
    keeps what is written identical to what was shown -- re-parsing could
    quietly produce something else if the two calls ever disagreed.

    The rows have been through the browser, so every category id is checked
    against this account again before anything is inserted.
    """
    user_id = require_user()
    payload = request.get_json(silent=True) or {}

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"rows": "Nothing to import."})
    if len(rows) > operations.MAX_IMPORT_ROWS:
        raise ValidationError(
            {"rows": f"At most {operations.MAX_IMPORT_ROWS} rows at a time."})

    fields = Validator(payload)
    account_id = fields.integer("account_id", required=False, minimum=1)
    fields.raise_if_invalid()

    clean = []
    for row in rows:
        if not isinstance(row, dict) or "skip" in row:
            continue
        try:
            clean.append({
                "date": str(row["date"]),
                "amount": str(row["amount"]),
                "type": row["type"] if row.get("type") in ("Income", "Expense")
                        else None,
                "description": str(row.get("description") or "")[:255],
                "category_id": int(row["category_id"]),
            })
        except (KeyError, TypeError, ValueError):
            raise ValidationError({"rows": "One of the rows is not importable."})
        if clean[-1]["type"] is None:
            raise ValidationError({"rows": "One of the rows has no type."})

    if not clean:
        raise ValidationError({"rows": "Nothing to import."})

    written = operations.commit_import(user_id, clean, account_id)

    # Rollover is derived from spending, so an import of three hundred rows
    # moves every carried-in figure it touches.
    for category_id in {row["category_id"] for row in clean} \
            & operations.categories_with_rollover(user_id):
        operations.refresh_rollover(user_id, category_id)

    return jsonify({"ok": True, "written": written}), 201
