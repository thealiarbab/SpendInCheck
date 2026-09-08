"""
Connection handling for SpendInCheck (PostgreSQL / Supabase build).

This module only opens and closes the PostgreSQL connection. All actual
queries live in operations.py, keeping this file tiny and easy to
explain in a viva: "this is the one place that knows how to reach
the database."
"""

import psycopg2
from psycopg2 import Error

import config


def get_connection():
    """Open and return a new PostgreSQL connection using settings from config.py.

    Returns a psycopg2 connection object on success, or raises
    psycopg2.Error if the connection cannot be established
    (wrong password, database unreachable, etc.).
    """
    try:
        settings = {
            "host": config.DB_HOST,
            "port": config.DB_PORT,
            "user": config.DB_USER,
            "password": config.DB_PASSWORD,
            "dbname": config.DB_NAME,
        }
        # Supabase only accepts encrypted connections.
        if config.DB_USE_SSL:
            settings["sslmode"] = "require"
        connection = psycopg2.connect(**settings)
        return connection
    except Error as e:
        # Re-raise after printing a clear message so the caller decides what to do next.
        print(f"Could not connect to the database: {e}")
        raise


def close_connection(connection):
    """Close the given PostgreSQL connection if it is open."""
    if connection is not None and not connection.closed:
        connection.close()
