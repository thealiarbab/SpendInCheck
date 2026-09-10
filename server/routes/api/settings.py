"""Account preferences.

Currently one: the currency the ledger is kept in. It lives on the account
rather than in the browser because it decides how amounts are *rounded* on
the way in, not merely how they are shown -- a limit entered in yen must be
stored as a whole number, and the server is the only place that can enforce
that.
"""

from flask import jsonify, request

from server import currency, operations
from server.auth import current_currency, remember_currency, require_user
from server.errors import ValidationError
from server.routes.api import api


@api.get("/settings/currencies")
def list_currencies():
    """Every currency the ledger can be kept in.

    Sent as codes only. The client turns each into a name and a symbol with
    Intl, which already has that in the reader's own language -- shipping
    162 English names would be both larger and wrong for most readers.
    """
    return jsonify({
        "items": list(currency.ALL),
        "current": current_currency(),
    })


@api.put("/settings/currency")
def set_currency():
    """Change the currency this account keeps its ledger in.

    A PUT: sending the same body twice leaves the same single value.

    Nothing is converted. The ledger holds no exchange rates, and inventing
    one would silently rewrite every figure the account has ever recorded,
    so this changes what the figures are labelled and how new ones are
    rounded -- and the screen that offers it says exactly that.
    """
    user_id = require_user()
    code = str((request.get_json(silent=True) or {}).get("currency") or "").upper()

    if not currency.is_known(code):
        raise ValidationError({"currency": "Not a currency this app knows."})

    if not operations.set_currency(user_id, code):
        raise ValidationError({"currency": "Could not save that."})

    remember_currency(code)
    return jsonify({"currency": code, "decimals": currency.decimals(code)})
