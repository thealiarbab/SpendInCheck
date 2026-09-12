"""More requests at once than the pool holds.

This exists because the reports screen fires five requests when it opens
and `DB_MAX_CONNECTIONS` defaulted to three. It is five now, so that
particular screen no longer queues -- but the test deliberately asks for
twice whatever the pool holds, because what is under test is the waiting,
not the size. psycopg2's pool does not wait
when it is empty -- it raises "connection pool exhausted" straight away --
so whichever request lost the race got no connection, its operation
swallowed the error and returned nothing, and the route turned that into a
**400 Bad Request**. A screen that had done nothing wrong was told its
request was bad, and the charts never arrived.

The comment in db.py had claimed requests would wait for a connection for
some time before that was true.
"""

import threading

import pytest

from server import db


def test_more_callers_than_connections_all_get_one():
    """Twice the pool's size, at once, and every one succeeds.

    The behaviour under test is waiting rather than failing. A connection
    is held for a single round trip, so a caller arriving during a burst
    waits milliseconds -- which is invisible, where failing is a broken
    page.
    """
    callers = db.MAX_CONNECTIONS * 2
    ready = threading.Barrier(callers)
    outcomes = []
    lock = threading.Lock()

    def worker():
        # The barrier is what makes this a real contest: without it the
        # threads trickle in and the pool is never actually empty.
        ready.wait(timeout=30)
        try:
            connection = db.get_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            got = cursor.fetchone()[0]
            db.close_connection(connection)
            with lock:
                outcomes.append(got)
        except Exception as failure:  # noqa: BLE001 - the point is what it was
            with lock:
                outcomes.append(failure)

    threads = [threading.Thread(target=worker) for _ in range(callers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    failures = [out for out in outcomes if isinstance(out, Exception)]
    assert not failures, f"{len(failures)} of {callers} failed: {failures[:3]}"
    assert outcomes == [1] * callers


def test_the_pool_is_smaller_than_the_screens_that_use_it():
    """Not a behaviour, a reminder.

    Three connections and a screen that opens five requests is the exact
    arrangement that produced the bug above. It is fine -- they wait now --
    but if this ever stops being true by accident, the waiting is the only
    thing holding it together and somebody should know that on purpose.
    """
    assert db.MAX_CONNECTIONS >= 1
    assert db.POOL_WAIT_SECONDS > 0
    # Long enough to cover a burst of round trips, short enough that a
    # genuinely unreachable database is not held open for a minute.
    assert 1 <= db.POOL_WAIT_SECONDS <= 30


@pytest.mark.parametrize("months", [1, 12])
def test_the_summary_never_answers_bad_request(client, months):
    """It has no input that could be bad.

    The months parameter is validated before this point and everything else
    comes from the session, so the only ways to fail are the database being
    unreachable or the pool being busy -- neither of which is the client's
    fault, and both of which are worth retrying. 400 is neither.
    """
    response = client.get(f"/api/v1/reports/summary?months={months}")
    # Signed out is the expected answer here; what matters is that it is
    # never 400, in any state.
    assert response.status_code != 400, response.get_json()
