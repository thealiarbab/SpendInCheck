"""Measure the paths a person actually waits through, and record the result.

    python scripts/benchmark.py

Writes docs/benchmarks.json, which the progress page reads. Kept as a script
rather than a test because it talks to the real database over the real
network: the numbers describe this machine's distance from Supabase as much
as the code, and that is the point -- most of the time goes on the wire.

Each entry carries the figure it started from, so the page can show what
changed rather than a number with no scale.
"""

import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server import operations  # noqa: E402
from server.app import create_app  # noqa: E402

RUNS = 5
OUTPUT = REPO / "docs" / "benchmarks.json"


def measure(fn, runs=RUNS, after=None):
    """Run something repeatedly and return the best and median milliseconds.

    Best matters as much as median here: it is the figure with the least
    network noise in it, so it is the one that moves when the code improves.

    Anything the run leaves behind is cleared through `after`, outside the
    timed section. Tidying up inside it measures the cleanup as well, which
    is how this first reported 772ms for a path that takes 500.
    """
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
        if after is not None:
            after(result)
    return round(min(times)), round(statistics.median(times))


def main():
    app = create_app("benchmark-key")
    app.config["TESTING"] = True
    entries = []

    def record(label, baseline, note, fn, after=None):
        best, median = measure(fn, after=after)
        entries.append({"label": label, "best": best, "median": median,
                        "baseline": baseline, "note": note})
        print(f"  {label:44} {best:5} ms best   {median:5} ms median")

    print("Measuring. Every figure includes the round trip to Supabase.\n")

    # The whole path from a cold visitor to a screen with figures on it.
    def open_the_demo():
        client = app.test_client()
        token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
        return client.post("/api/v1/auth/demo",
                           headers={"X-CSRF-Token": token}).get_json()

    record("Open the demo, to a screen with figures", 3100,
           "Session, account creation, seeding and the dashboard payload.",
           open_the_demo,
           after=lambda body: operations.delete_demo_user(body["user"]["id"]))

    # A signed-in visit needs its own account to read from.
    client = app.test_client()
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    account = client.post("/api/v1/auth/demo",
                          headers={"X-CSRF-Token": token}).get_json()
    user_id = account["user"]["id"]
    try:
        record("Dashboard, already signed in", 489,
               "Holdings and recent rows together, sharing one connection.",
               lambda: client.get("/api/v1/reports/dashboard"))
        record("Transactions list", 234, "A single query.",
               lambda: client.get("/api/v1/transactions"))
        record("Budget vs actual report", 312, "Joins budgets to transactions.",
               lambda: client.get("/api/v1/reports/budget-vs-actual?month=2026-08"))
        record("Session check, touches no database", 6,
               "The floor: what a request costs with no query in it.",
               lambda: client.get("/api/v1/auth/session"))
    finally:
        operations.delete_demo_user(user_id)

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(
        {"measured_at": int(time.time()), "runs": RUNS, "entries": entries},
        indent=2), encoding="utf-8")
    print(f"\nWritten to {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
