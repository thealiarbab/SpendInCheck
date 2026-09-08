"""
Connection handling for FinTrack.

This module only opens and closes the MySQL connection. All actual
queries live in operations.py, keeping this file tiny and easy to
explain in a viva: "this is the one place that knows how to reach
the database."
"""

import mysql.connector
from mysql.connector import Error

import config


def get_connection():
    """Open and return a new MySQL connection using settings from config.py.

    Returns a mysql.connector connection object on success, or raises
    mysql.connector.Error if the connection cannot be established
    (wrong password, MySQL server not running, etc.).
    """
    try:
        connection = mysql.connector.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
        )
        return connection
    except Error as e:
        # Re-raise after printing a clear message so the caller decides what to do next.
        print(f"Could not connect to MySQL database: {e}")
        raise


def close_connection(connection):
    """Close the given MySQL connection if it is open."""
    if connection is not None and connection.is_connected():
        connection.close()
