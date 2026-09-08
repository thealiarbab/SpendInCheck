"""
Database configuration for SpendInCheck.

Values are read from environment variables when they exist, falling back to
local development defaults. That way the same code runs on this machine and
on a hosted server, where the real credentials are supplied as environment
variables instead of being written into the file.
"""

import os

# Load a local .env file when python-dotenv is installed. On a hosted server
# the variables are supplied by the platform instead, so this is optional.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# "or" rather than a get() default, so a variable that exists but is left
# blank still falls back instead of producing an empty host or port.
DB_HOST = os.environ.get("DB_HOST") or "localhost"
DB_PORT = int(os.environ.get("DB_PORT") or 3306)
DB_USER = os.environ.get("DB_USER") or "root"
DB_PASSWORD = os.environ.get("DB_PASSWORD") or "root"
DB_NAME = os.environ.get("DB_NAME") or "spendincheck"

# Hosted MySQL providers require an encrypted connection; a local server does not.
DB_USE_SSL = os.environ.get("DB_USE_SSL", "").lower() in ("1", "true", "yes")
