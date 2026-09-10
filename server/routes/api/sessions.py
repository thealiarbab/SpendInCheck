"""Sign in, sign out, and report who is signed in.

GET /auth/session is the call the client makes first, on every load. Without
it a freshly opened page cannot tell "signed out" from "still checking", and
would flash the sign-in screen at someone who is already signed in.
"""

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from server import operations
from server.auth import (csrf_token, current_user_id, is_demo, require_user,
                         sign_in, sign_out)
from server.errors import ApiError, ValidationError
from server.routes.api import api
from server.routes.api.dashboard_payload import dashboard_payload
from server.validators import Validator

# Any name starting with this is reserved for demonstration accounts, which
# are created by the server. Registering one would let a visitor take a name
# the demo flow expects to own.
DEMO_NAME_PREFIX = "demo"


def _account_body():
    """The signed-in account as the client wants to see it, or None."""
    user_id = current_user_id()
    if user_id is None:
        return None
    return {"id": user_id, "username": session.get("username"), "is_demo": is_demo()}


@api.get("/auth/session")
def read_session():
    """Report the current account and hand out a CSRF token.

    Always 200, never 401: "nobody is signed in" is a fact about the session,
    not a failure of the request. A 401 here would make every first load look
    like an error to the client's own error handling.
    """
    return jsonify({"user": _account_body(), "csrf_token": csrf_token()})


@api.post("/auth/register")
def register():
    """Create an account and sign it in."""
    payload = request.get_json(silent=True) or {}
    fields = Validator(payload)

    username = fields.text("username", max_length=30)
    email = fields.text("email", max_length=255)
    password = payload.get("password") or ""

    if username is not None:
        if len(username) < 3:
            fields.fail("username", "Use at least 3 characters.")
        elif not username.replace("_", "").isalnum():
            fields.fail("username", "Letters, digits and underscores only.")
        elif username.lower().startswith(DEMO_NAME_PREFIX):
            fields.fail("username", "That name is reserved.")
    if email is not None and ("@" not in email or "." not in email.split("@")[-1]):
        fields.fail("email", "Enter a valid email address.")
    if len(password) < 8:
        fields.fail("password", "Use at least 8 characters.")

    fields.raise_if_invalid()

    taken = operations.username_taken(username, email.lower())
    if taken:
        # username_taken returns the human sentence describing which one
        # clashed, so it is reported against the field it belongs to.
        field = "email" if "email" in taken.lower() else "username"
        raise ValidationError({field: taken})

    user_id = operations.create_user(
        username, email.lower(), generate_password_hash(password))
    if user_id is None:
        raise ApiError("Could not create that account.", code="create_failed")

    token = sign_in(user_id, username)
    return jsonify({"user": _account_body(), "csrf_token": token}), 201


@api.post("/auth/sign-in")
def sign_in_route():
    """Exchange a username or email plus password for a session."""
    payload = request.get_json(silent=True) or {}
    fields = Validator(payload)
    login = fields.text("login", label="username or email")
    password = payload.get("password") or ""
    if not password:
        fields.fail("password", "Enter a password.")
    fields.raise_if_invalid()

    account = operations.get_user_by_login(login)
    # One message whether the name is unknown or the password is wrong, so
    # this cannot be used to discover which accounts exist.
    if not account or not check_password_hash(account[3], password):
        raise ApiError("Incorrect username or password.",
                       code="invalid_credentials", status=401)

    token = sign_in(account[0], account[1])
    return jsonify({"user": _account_body(), "csrf_token": token})


@api.post("/auth/demo")
def start_demo():
    """Create a private demonstration account and sign into it.

    A POST because it creates a row. Each visitor gets their own ledger, so
    two people trying the app at once cannot edit or reset each other's
    data -- and nobody needs to register to look around.

    The password is set to an unguessable value nobody is told, since the
    only way into these accounts is through this endpoint.
    """
    user_id, username = operations.create_demo_user()
    if user_id is None:
        raise ApiError("The demo is unavailable right now.",
                       code="demo_unavailable", status=503)

    token = sign_in(user_id, username, demo=True)
    # The dashboard rides along. This request already holds an open
    # connection, so reading the seeded rows costs a few milliseconds here
    # against a further two hundred for a separate round trip -- and the
    # visitor is staring at a button the whole time.
    return jsonify({
        "user": _account_body(),
        "csrf_token": token,
        "dashboard": dashboard_payload(user_id),
    }), 201


@api.post("/auth/sign-out")
def sign_out_route():
    """Abandon the session.

    A POST, not a GET. As a GET this destroys data on any prefetch, link
    scan or <img src> pointed at it -- which is exactly how the Jinja version
    can currently be triggered by something that never meant to.
    """
    require_user()
    sign_out()
    return jsonify({"user": None, "csrf_token": csrf_token()})
