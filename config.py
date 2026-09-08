"""
Database configuration for SpendInCheck.

Values are read from environment variables when they exist, falling back to
local development defaults. That way the same code runs on this machine and
on a hosted server, where the real credentials are supplied as environment
variables instead of being written into the file.
"""

import os

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
DB_NAME = os.environ.get("DB_NAME", "spendincheck")

# Hosted MySQL providers require an encrypted connection; a local server does not.
DB_USE_SSL = os.environ.get("DB_USE_SSL", "").lower() in ("1", "true", "yes")
