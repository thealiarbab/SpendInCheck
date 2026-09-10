"""The JSON API blueprint.

Everything shared by every endpoint lives here: the error shape, the CSRF
check, and the JSON 404. Individual route modules below only describe their
own resource, so no route can forget to guard itself.

Mounted at /api/v1 alongside the Jinja pages rather than replacing them. Both
read the same session, so a screen can move to the client one at a time.
"""

from flask import Blueprint, jsonify, request
from psycopg2 import Error as PostgresError

from server import auth
from server.errors import ApiError, DatabaseUnavailable

api = Blueprint("api", __name__, url_prefix="/api/v1")

# Methods that must carry a CSRF token. GET and HEAD are excluded because they
# are not supposed to change anything; OPTIONS is the browser's own preflight
# and never carries application headers.
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@api.before_request
def require_csrf_token():
    """Reject any state-changing request that cannot prove it was intended.

    The session cookie is SameSite=Lax, which already blocks a cross-site form
    POST. This covers what Lax does not: the double-submit token has to be
    read out of a response body and echoed in a header, which same-origin
    policy prevents another site's script from doing.

    Returning csrf_failed rather than a generic 403 lets the client tell "your
    token went stale, fetch a new one and retry" apart from "you may not do
    this at all".
    """
    if request.method not in UNSAFE_METHODS:
        return None
    # Scheduled jobs are called by the platform, not a browser: there is no
    # session to hold a token, and they authenticate with a secret instead.
    if request.path.startswith("/api/v1/cron/"):
        return None
    if auth.csrf_is_valid(request.headers.get(auth.CSRF_HEADER)):
        return None
    return jsonify({"error": {
        "code": "csrf_failed",
        "message": "Your session token is stale. Reload and try again.",
    }}), 403


@api.errorhandler(ApiError)
def handle_api_error(error):
    """Render any deliberate failure as the documented error body."""
    return jsonify(error.to_dict()), error.status


@api.errorhandler(PostgresError)
def handle_database_error(error):
    """Turn a database failure into 503 rather than a bare 500.

    Under a serverless deployment the common cause is the pooled connection
    limit, which is temporary -- so the honest answer to the client is "try
    again", not "something is broken".
    """
    unavailable = DatabaseUnavailable()
    return jsonify(unavailable.to_dict()), unavailable.status


def handle_unknown_path(error):
    """Answer an unknown API path in JSON, never in Flask's HTML page.

    Registered on the app rather than the blueprint: when no route matches,
    Flask has not chosen a blueprint, so a blueprint-level 404 handler never
    runs. The path check is what keeps this from stealing the HTML 404 that
    the pages should still serve.
    """
    if not request.path.startswith("/api/"):
        return error
    return jsonify({"error": {
        "code": "not_found",
        "message": "No such endpoint.",
    }}), 404


# Imported last, and only for the side effect of registering their routes on
# `api`. Each imports `api` from this module, so they cannot be imported at
# the top without a circular import. Note the route modules are named for
# their resource, never after a module in server/ -- `sessions` rather than
# `auth`, because `from ... import auth` inside this package resolves to
# server.auth and the routes then attach to nothing.
from server.routes.api import accounts  # noqa: E402,F401
from server.routes.api import budgets  # noqa: E402,F401
from server.routes.api import cron  # noqa: E402,F401
from server.routes.api import categories  # noqa: E402,F401
from server.routes.api import goals  # noqa: E402,F401
from server.routes.api import investments  # noqa: E402,F401
from server.routes.api import reports  # noqa: E402,F401
from server.routes.api import sessions  # noqa: E402,F401
from server.routes.api import settings  # noqa: E402,F401
from server.routes.api import tags  # noqa: E402,F401
from server.routes.api import transactions  # noqa: E402,F401
