"""
Connection handling for SpendInCheck (PostgreSQL / Supabase).

This module only opens and closes the PostgreSQL connection. All actual
queries live under server/operations/, keeping this file small: it is the
one place that knows how to reach the database.
"""

import psycopg2
from psycopg2 import Error

from . import config


def get_connection():
    """Open and return a new PostgreSQL connection using settings from config.

    Prefers config.DATABASE_URL when set, since that is the single value
    Supabase hands out. Falls back to the individual DB_* settings for a
    local server.

    Returns a psycopg2 connection, or raises psycopg2.Error if the connection
    cannot be established (wrong password, database unreachable, and so on).
    """
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
    """Close the given PostgreSQL connection if it is open."""
    if connection is not None and not connection.closed:
        connection.close()
