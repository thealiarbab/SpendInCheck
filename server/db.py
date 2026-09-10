"""
Connection handling for SpendInCheck (PostgreSQL / Supabase).

This module only opens and closes the PostgreSQL connection. All actual
queries live under server/operations/, keeping this file small: it is the
one place that knows how to reach the database.
"""

import psycopg2
from psycopg2 import Error

from . import config

# Key under which the current request's connection is cached. Flask's g is
# per request and per thread, so two requests never share one.
_REQUEST_KEY = "_spendincheck_connection"


def _request_store():
    """Flask's per-request store, or None when running outside a request.

    Imported lazily and guarded, because the migration runner and the tests
    use this module with no application around it at all.
    """
    try:
        from flask import g, has_app_context
    except ImportError:
        return None
    return g if has_app_context() else None


def get_connection():
    """Return a PostgreSQL connection, reusing the request's own where possible.

    Reaching Supabase costs roughly 200ms of TLS handshake, which was about
    85% of the time spent answering a typical request -- the queries
    themselves are quick. Inside a request the first caller opens a
    connection and every later one gets the same object back, so a route that
    reads two tables pays that cost once instead of twice.

    Outside a request -- the migration runner, the tests, a script -- this
    opens a fresh connection exactly as it always did.

    One consequence worth knowing: callers within a single request now share
    a transaction, so a rollback in one undoes uncommitted work from another.
    Every route performs at most one write, which is what makes that safe.

    Prefers config.DATABASE_URL when set, since that is the single value
    Supabase hands out. Falls back to the individual DB_* settings for a
    local server.

    Returns a psycopg2 connection, or raises psycopg2.Error if the connection
    cannot be established (wrong password, database unreachable, and so on).
    """
    store = _request_store()
    if store is not None:
        existing = getattr(store, _REQUEST_KEY, None)
        if existing is not None and not existing.closed:
            return existing

    connection = _open()
    if store is not None:
        setattr(store, _REQUEST_KEY, connection)
    return connection


def _open():
    """Open a genuinely new connection from the configured settings."""
    try:
        if config.DATABASE_URL:
            # sslmode inside the URL wins; this only supplies a default.
            return psycopg2.connect(config.DATABASE_URL, sslmode="require")

        settings = {
            "host": config.DB_HOST,
            "port": config.DB_PORT,
            "user": config.DB_USER,
            "password": config.DB_PASSWORD,
            "dbname": config.DB_NAME,
        }
        if config.DB_USE_SSL:
            settings["sslmode"] = "require"
        return psycopg2.connect(**settings)
    except Error as e:
        # Re-raise after a clear message so the caller decides what to do next.
        print(f"Could not connect to the database: {e}")
        raise


def close_connection(connection):
    """Close the connection, unless it belongs to the current request.

    Operations functions close what they opened, which is right when each of
    them owns its connection. Now that a request shares one, closing here
    would pull it out from under whatever runs next in the same request, so
    the request's own connection is left for the teardown hook to close.
    """
    if connection is None or connection.closed:
        return

    store = _request_store()
    if store is not None and getattr(store, _REQUEST_KEY, None) is connection:
        return

    connection.close()


def close_request_connection(_exception=None):
    """Close the connection this request opened, if it opened one.

    Registered as a teardown hook by the application factory. Serverless
    containers are reused, so a connection left open here would be leaked for
    the life of the container and count against Supabase's pool.
    """
    store = _request_store()
    if store is None:
        return
    connection = getattr(store, _REQUEST_KEY, None)
    if connection is not None:
        setattr(store, _REQUEST_KEY, None)
        if not connection.closed:
            connection.close()
