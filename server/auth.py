"""Who is signed in, and proof that a request meant to be sent.

The session is a Flask signed cookie, not a token in localStorage. The client
and the API are the same origin, so there is nothing a token would buy that
the cookie does not already do -- and a token readable by script is a
credential any cross-site scripting flaw can steal, which an HttpOnly cookie
is not.

The Jinja pages and the JSON API share these same session keys deliberately.
That is what lets both run at once while screens are ported one at a time:
sign in through either, and the other already knows who you are.
"""

import hmac
import secrets

from flask import session

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
