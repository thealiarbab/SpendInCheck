"""
Apply the SQL migrations in db/migrations, in order, once each.

    python scripts/migrate.py --dry     show what would run, change nothing
    python scripts/migrate.py           apply everything outstanding
    python scripts/migrate.py --status  list applied and pending

Each file runs inside a single transaction together with the row that records
it, so a migration either lands completely and is marked applied, or rolls
back entirely and stays pending. There is no state where a half-applied file
is recorded as done.

Files are also written to be re-runnable on their own (IF NOT EXISTS, guarded
DO blocks), because in practice these get pasted into the Supabase SQL editor
as well, and the two paths must not disagree about what happened.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import db  # noqa: E402

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "migrations"
)

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    VARCHAR(200) PRIMARY KEY,
    checksum    VARCHAR(64)  NOT NULL,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""


def migration_files():
    """Return the migration filenames in the order they must be applied.

    Ordering is by filename, which is why they are numbered: 002 creates the
    table 004 and 005 point their foreign keys at.
    """
    if not os.path.isdir(MIGRATIONS_DIR):
        return []
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))


def read_migration(filename):
    """Return the text of one migration file."""
    with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as handle:
        return handle.read()


def checksum(text):
    """Fingerprint a migration so an edit after the fact can be reported."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def applied_migrations(connection):
    """Return {filename: checksum} for everything already applied."""
    cursor = connection.cursor()
    cursor.execute(LEDGER)
    connection.commit()
    cursor.execute("SELECT filename, checksum FROM schema_migrations")
    return dict(cursor.fetchall())


def apply_migration(connection, filename, text):
    """Run one migration and record it, both inside a single transaction."""
    cursor = connection.cursor()
    try:
        cursor.execute(text)
        cursor.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
            (filename, checksum(text)),
        )
        connection.commit()
    except Exception:
        # Leave the database exactly as it was, and the file still pending.
        connection.rollback()
        raise


def main(argv):
    dry_run = "--dry" in argv
    status_only = "--status" in argv

    files = migration_files()
    if not files:
        print("No migrations found in db/migrations.")
        return 0

    connection = db.get_connection()
    try:
        already = applied_migrations(connection)

        pending = []
        for filename in files:
            text = read_migration(filename)
            if filename in already:
                if already[filename] != checksum(text):
                    # Not fatal: an applied migration may have been reworded.
                    # Worth saying out loud, because it means the file on disk
                    # is no longer what the database actually ran.
                    print(f"  changed since applied  {filename}")
                else:
                    print(f"  applied                {filename}")
                continue
            pending.append((filename, text))
            print(f"  pending                {filename}")

        if status_only:
            return 0

        if not pending:
            print("\nNothing to do - the database is up to date.")
            return 0

        if dry_run:
            print(f"\n--dry: {len(pending)} migration(s) would be applied, nothing changed.")
            return 0

        print()
        for filename, text in pending:
            print(f"applying {filename} ...", end=" ", flush=True)
            apply_migration(connection, filename, text)
            print("done")

        print(f"\nApplied {len(pending)} migration(s).")
        return 0
    finally:
        db.close_connection(connection)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
