"""Scheduled jobs.

These are called by the platform's scheduler, not by a browser, so they
authenticate with a shared secret instead of a session. Everything here
deletes or writes data on nobody's behalf, which is why the guard refuses to
run at all when the secret is missing: an unset environment variable must
never mean "let anyone through".
"""

import hmac

from flask import jsonify, request

from server import config, operations
from server.errors import ApiError
from server.routes.api import api

# Vercel sends the secret as a bearer token. The explicit header is accepted
# too so the job can be triggered by hand with curl while testing.
BEARER_PREFIX = "Bearer "
CRON_HEADER = "X-Cron-Secret"

# Demonstration accounts are per visitor and short-lived. A day is long enough
# that nobody loses a session they are still using, and short enough that
# abandoned ones do not accumulate.
DEMO_MAX_AGE_HOURS = 24


def _require_cron_secret():
    """Raise unless the caller proved it is the scheduler."""
    if not config.CRON_SECRET:
        # Refusing is the safe default. Running would mean an unconfigured
        # deployment exposes a public endpoint that deletes accounts.
        raise ApiError("Scheduled jobs are not configured.",
                       code="cron_not_configured", status=503)

    supplied = request.headers.get(CRON_HEADER, "")
    authorization = request.headers.get("Authorization", "")
    if not supplied and authorization.startswith(BEARER_PREFIX):
        supplied = authorization[len(BEARER_PREFIX):]

    if not supplied or not hmac.compare_digest(supplied, config.CRON_SECRET):
        # 404, not 403: an endpoint that answers differently to a wrong secret
        # tells a scanner it exists and is worth attacking.
        raise ApiError("Not found.", code="not_found", status=404)


@api.post("/cron/clear-demos")
def clear_demos():
    """Delete demonstration accounts nobody signed out of.

    Signing out removes the account already, so this only catches the ones
    abandoned by closing the tab. Every data table cascades from the user
    row, so one statement clears each account entirely.
    """
    _require_cron_secret()
    removed = operations.delete_stale_demo_users(DEMO_MAX_AGE_HOURS)
    return jsonify({"removed": removed, "older_than_hours": DEMO_MAX_AGE_HOURS})
