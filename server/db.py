"""
Connection handling for SpendInCheck (PostgreSQL / Supabase).

This module only opens and closes the PostgreSQL connection. All actual
queries live under server/operations/, keeping this file small: it is the
one place that knows how to reach the database.
"""

import atexit
import os
import threading
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import Error, pool as psycopg2_pool
from psycopg2.pool import PoolError

from . import config

# Key under which the current request's connection is cached. Flask's g is
# per request and per thread, so two requests never share one.
_REQUEST_KEY = "_spendincheck_connection"

# How many connections this process may hold open at once.
#
# Three, because the shared ceiling is far lower than it looks. Measured
# against this project's pooler: the seventeenth concurrent client
# connection fails, so the whole budget across every process that talks to
# this database is sixteen. A serverless deployment is many containers each
# holding their own pool, so a generous number here is how five containers
# exhaust everything.
#
# The failure mode is worth knowing because it is not the obvious one: past
# the limit, connecting appears to succeed and the connection then dies on
# first use with "SSL connection has been closed unexpectedly". _checkout
# below survives that -- it uses each connection before handing it on and
# discards the ones that fail -- but the ceiling is still real.
#
# A process that serves one request at a time needs one; three is headroom
# for a threaded local server. Raise DB_MAX_CONNECTIONS if the database
# plan changes, since this limit comes with the tier.
#
# Requests beyond this wait for a connection to come back, which is still
# far cheaper than the 180ms of handshake they would otherwise each pay.
# The waiting is done in _checkout below: psycopg2's pool does not wait, it
# raises "connection pool exhausted" the instant every connection is out.
# This comment described the intended behaviour and not the actual one for
# long enough that the reports screen -- five requests fired at once
# against three connections -- served a 400 to whichever lost the race.
MAX_CONNECTIONS = max(1, int(os.environ.get("DB_MAX_CONNECTIONS", "3")))

# How long a request will wait for somebody else's connection before giving
# up. Generous against a query, because the thing being waited for is
# another request finishing, and those are tens of milliseconds; short
# against a person, who is watching a screen. A request that waits 40ms and
# succeeds is invisible; one that fails immediately is a broken page.
POOL_WAIT_SECONDS = 5.0

# Polled rather than signalled, because psycopg2's pool offers no way to be
# woken when a connection is returned. 10ms is well under the round trip it
# is waiting on, so the polling costs nothing measurable.
POOL_POLL_SECONDS = 0.01

_pool = None
_pool_lock = threading.Lock()


def _connection_settings():
    """The keyword arguments psycopg2 needs to reach the database.

    Prefers config.DATABASE_URL when set, since that is the single value
    Supabase hands out; falls back to the individual DB_* settings.
    """
    if config.DATABASE_URL:
        # sslmode inside the URL wins; this only supplies a default.
        return {"dsn": config.DATABASE_URL, "sslmode": "require"}

    settings = {
        "host": config.DB_HOST,
        "port": config.DB_PORT,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
        "dbname": config.DB_NAME,
    }
    if config.DB_USE_SSL:
        settings["sslmode"] = "require"
    return settings


def _get_pool():
    """The process-wide connection pool, opened on first use.

    Reaching the database costs about 180ms of TLS handshake and
    authentication, measured against the Mumbai pooler. Without a pool that
    is paid on every single request, and it dwarfs the queries -- a
    four-query dashboard is 180ms of handshake and 108ms of actual work.

    Double-checked locking, because two threads can arrive here at once on a
    cold process and one pool is the entire point.
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # minconn = maxconn, which is not a typo and not paranoia.
                #
                # psycopg2's pool keeps exactly minconn idle connections and
                # CLOSES every one returned beyond that. At minconn=1 the
                # second and third connections of every burst were closed on
                # release and handshaked again on the next one -- measured
                # at 397ms, 370ms, 399ms to acquire three connections on
                # three consecutive bursts, never warming up, because there
                # was nothing to warm.
                #
                # The reports screen fires five requests at once against
                # three connections, so it paid that on every visit.
                #
                # The cost is moved rather than removed: the pool now opens
                # MAX_CONNECTIONS at construction instead of one. That is
                # paid once per process, and a Vercel function is warm
                # across invocations, so it is paid once rather than on
                # every burst for the life of the instance.
                _pool = psycopg2_pool.ThreadedConnectionPool(
                    minconn=MAX_CONNECTIONS, maxconn=MAX_CONNECTIONS,
                    **_connection_settings())
    return _pool


def _checkout():
    """A usable connection from the pool, in autocommit mode.

    A pooled connection can have died while it sat idle -- the pooler drops
    them, networks drop them -- and psycopg2 does not notice until the next
    statement fails. So a connection that comes back closed is thrown away
    and another taken, and anything left in a failed or open transaction is
    rolled back before it is handed on. Without that, one request's aborted
    transaction becomes the next request's mysterious InternalError.

    Autocommit, because otherwise psycopg2 opens a transaction on the first
    statement of every request -- including a read -- and that transaction
    then has to be closed with a ROLLBACK, which is a full round trip to
    Mumbai. Measured: 28ms, on every request that reads anything, purely to
    end a transaction nothing asked for. Under autocommit a read leaves the
    connection idle and the rollback costs nothing at all.

    Anything that needs several statements to succeed or fail together says
    so explicitly, with transaction() below.

    Waits when the pool is empty rather than failing. A connection is held
    for one round trip, so a request that arrives during a burst waits
    milliseconds; psycopg2's own pool raises instead, which is how five
    simultaneous requests against three connections produced a 400 on a
    request that was in no way bad.
    """
    pool = _get_pool()
    deadline = time.monotonic() + POOL_WAIT_SECONDS
    attempts = 0

    while True:
        try:
            connection = pool.getconn()
        except PoolError:
            # Every connection is out with another request. Wait for one:
            # they are held for a single round trip, so the wait is
            # normally a few milliseconds. Failing here instead is what
            # turned a busy screen into an error page.
            if time.monotonic() >= deadline:
                raise
            time.sleep(POOL_POLL_SECONDS)
            continue

        if connection.closed:
            pool.putconn(connection, close=True)
        else:
            try:
                connection.rollback()
                connection.autocommit = True
            except Error:
                pool.putconn(connection, close=True)
            else:
                return connection

        # A dead connection was discarded rather than waited for, so this
        # is bounded by how many the pool holds rather than by the clock:
        # if every one of them is dead the database is unreachable, and one
        # fresh connection will say so faster than retrying the pool.
        attempts += 1
        if attempts >= MAX_CONNECTIONS:
            return _open()


def _release(connection):
    """Give a connection back to the pool, or close it if it is not ours."""
    if connection is None or connection.closed:
        return
    pool = _pool
    if pool is None:
        connection.close()
        return
    try:
        pool.putconn(connection)
    except (KeyError, psycopg2_pool.PoolError):
        # Not a pooled connection -- something opened it with _open().
        connection.close()


@contextmanager
def transaction(connection):
    """Run several statements so that they all happen or none of them do.

    Connections are in autocommit mode, so each statement stands alone --
    which is right for a read and for a single insert, and wrong for
    anything that has to move rows before deleting what they pointed at.

    Turning autocommit off costs nothing: it is a client-side flag, and the
    transaction itself begins on the next statement. The only round trip
    added is the COMMIT, which such an operation had to pay anyway.

        with db.transaction(connection):
            cursor.execute(...)
            cursor.execute(...)

    Leaving the block commits. Raising rolls back and re-raises, so a
    failure cannot leave half the work behind.
    """
    connection.autocommit = False
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        # Safe here: both paths above end the transaction, so the connection
        # is idle and psycopg2 will accept the flag.
        if not connection.closed:
            connection.autocommit = True


@atexit.register
def _close_pool():
    """Close every pooled connection when the process ends."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Error:
            pass
        _pool = None


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

    Outside a request -- the migration runner, the tests, a script -- a
    connection still comes from the pool; it is simply released as soon as
    the caller is done with it rather than at the end of a request.

    One consequence worth knowing: callers within a single request now share
    a transaction, so a rollback in one undoes uncommitted work from another.
    Every route performs at most one write, which is what makes that safe.

    Returns a psycopg2 connection, or raises psycopg2.Error if the connection
    cannot be established (wrong password, database unreachable, and so on).
    """
    store = _request_store()
    if store is not None:
        existing = getattr(store, _REQUEST_KEY, None)
        if existing is not None and not existing.closed:
            return existing

    connection = _checkout()
    if store is not None:
        setattr(store, _REQUEST_KEY, connection)
    return connection


def _open():
    """Open a genuinely new connection, bypassing the pool.

    Used by the pool itself and by anything that must not share -- and as
    the last resort when every pooled connection turns out to be dead.
    """
    try:
        settings = _connection_settings()
        dsn = settings.pop("dsn", None)
        if dsn is not None:
            return psycopg2.connect(dsn, **settings)
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

    _release(connection)


def close_request_connection(_exception=None):
    """Return this request's connection to the pool, if it took one.

    Registered as a teardown hook by the application factory. It no longer
    closes: closing is what the handshake is for, and the whole point of
    the pool is that the next request finds the connection already open.
    What it must still do is let go of it, so a container that is reused
    does not hold one per request it has ever served.
    """
    store = _request_store()
    if store is None:
        return
    connection = getattr(store, _REQUEST_KEY, None)
    if connection is not None:
        setattr(store, _REQUEST_KEY, None)
        _release(connection)
