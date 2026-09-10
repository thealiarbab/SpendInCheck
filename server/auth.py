"""Who is signed in, and proof that a request meant to be sent.

The session is a Flask signed cookie, not a token in localStorage. The client
and the API are the same origin, so there is nothing a token would buy that
the cookie does not already do -- and a token readable by script is a
credential any cross-site scripting flaw can steal, which an HttpOnly cookie
is not.

One set of session keys, read by every endpoint. Nothing here is specific
to a screen: the session says who is signed in and whether this is a
demonstration account, and the API decides the rest.
"""

import hmac
import secrets
import time

from flask import session

from server import currency as currencies
from server.errors import NotSignedIn

CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def current_user_id():
    """The signed-in account's id, or None when nobody is signed in."""
    return session.get("user_id")


def require_user():
    """Return the signed-in account's id, or raise NotSignedIn.

    Routes call this instead of checking the session themselves, so the 401
    body is identical everywhere and no route can forget to check.
    """
    user_id = current_user_id()
    if user_id is None:
        raise NotSignedIn()
    return user_id


def current_currency():
    """The currency this account keeps its ledger in.

    Cached on the session after the first read. It is wanted on nearly every
    response -- money is serialised to its scale -- and re-reading it would
    add a round trip to Supabase to each one, for a value that changes on a
    settings screen almost nobody visits twice.
    """
    held = session.get("currency")
    if held:
        return held

    user_id = current_user_id()
    if user_id is None:
        return currencies.DEFAULT

    # Imported here rather than at module level: operations imports the
    # database layer, and auth is imported by parts of the app that must
    # stay usable without one.
    from server import operations
    code = operations.get_currency(user_id) or currencies.DEFAULT
    session["currency"] = code
    return code


def remember_currency(code):
    """Update the cached currency after it has been changed.

    Also called the moment an account is created. A brand new account keeps
    its ledger in the default currency by definition, so reading that back
    out of the row that was just written is a round trip to Mumbai to learn
    something already known -- and it landed on the demo path, where a
    visitor is watching a button.
    """
    session["currency"] = code


def money_places():
    """How many decimal places this account's money is written to."""
    return currencies.decimals(current_currency())


# How long a demonstration session is trusted before its account is checked
# for again. The sweep runs daily, so an hour is far more often than it can
# possibly matter -- and it keeps the check off the path of somebody who is
# simply using the app.
DEMO_RECHECK_SECONDS = 3600


def demo_account_is_gone():
    """True when this demo session points at an account that no longer exists.

    Confirming an account exists costs a round trip to Supabase, and
    GET /auth/session is called on every single page load, so doing it every
    time put 260ms on the most frequent request in the app to catch
    something that can only happen once a day.

    So a session is trusted for an hour after it was last confirmed. A demo
    swept overnight is still caught the next morning, which is the case that
    actually occurs; an account deleted in the last hour shows an empty
    ledger until the next check, which is what happened before this existed
    at all.
    """
    if not is_demo():
        return False

    checked = session.get("verified_at")
    if checked is not None and time.time() - checked < DEMO_RECHECK_SECONDS:
        return False

    from server import operations
    if operations.user_exists(current_user_id()):
        session["verified_at"] = time.time()
        return False
    return True


def is_demo():
    """True when this session is using a demonstration account."""
    user_id = current_user_id()
    return user_id is not None and user_id == session.get("demo_id")


def sign_in(user_id, username, *, demo=False):
    """Record the account in the session and issue a fresh CSRF token.

    The session is cleared first so that signing in never inherits state --
    notably demo_id, which would otherwise mark a real account as the demo
    and let its data be wiped.

    Returns the new CSRF token for the client to echo back.
    """
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    if demo:
        session["demo_id"] = user_id
        # Just created, so it certainly exists.
        session["verified_at"] = time.time()
    session.permanent = True
    return rotate_csrf_token()


def sign_out():
    """Abandon the session entirely."""
    session.clear()


# --- CSRF -------------------------------------------------------------------

def rotate_csrf_token():
    """Generate a new CSRF token, store it in the session, and return it.

    Issued on sign-in and read back through GET /auth/session, so a client
    that was left open overnight can recover without a full reload.
    """
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def csrf_token():
    """The session's current CSRF token, creating one if absent."""
    return session.get(CSRF_SESSION_KEY) or rotate_csrf_token()


def csrf_is_valid(submitted):
    """True when the submitted token matches the one held in the session.

    compare_digest rather than == because a plain comparison returns as soon
    as two bytes differ, and that timing difference is measurable.
    """
    expected = session.get(CSRF_SESSION_KEY)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(str(expected), str(submitted))
