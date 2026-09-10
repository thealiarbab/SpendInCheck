"""
Database and application configuration for SpendInCheck.

Values come from environment variables, falling back to local development
defaults. The same code therefore runs on this machine and on Vercel, where
the real credentials are supplied by the platform.

Two ways to point at Postgres, in priority order:

1. DATABASE_URL  - a single libpq connection string. This is what Supabase
   hands you, and it is the preferred form because it carries host, port,
   user, password and database in one value.
2. The individual DB_* variables below, for a local server.

On Supabase, use the CONNECTION POOLER host (port 6543, transaction mode),
not the direct database host on 5432. Every serverless request opens its own
connection, so the direct endpoint runs out of connections under load.
"""

import os

# Load a local .env file when python-dotenv is installed. On a hosted server
# the variables are supplied by the platform instead, so this is optional.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(name, default=""):
    """Return an environment variable, treating blank as absent.

    A variable that exists but is empty (a common accident when pasting into
    a hosting dashboard) falls back to the default rather than producing an
    empty host or port.
    """
    return os.environ.get(name) or default


# --- Database ---------------------------------------------------------------

DATABASE_URL = _env("DATABASE_URL")

DB_HOST = _env("DB_HOST", "localhost")
DB_PORT = int(_env("DB_PORT", "5432"))
DB_USER = _env("DB_USER", "postgres")
DB_PASSWORD = _env("DB_PASSWORD", "postgres")
DB_NAME = _env("DB_NAME", "spendincheck")

# Supabase only accepts encrypted connections; a local server usually does not.
DB_USE_SSL = _env("DB_USE_SSL").lower() in ("1", "true", "yes")


# --- Application ------------------------------------------------------------

# Signs the session cookie. A random value on each boot would log everyone out
# on every deploy, so this must be set in production.
SECRET_KEY = _env("SECRET_KEY", "dev-only-not-for-production")

# Guards the scheduled endpoints. Vercel cron requests are unauthenticated by
# default, so /api/v1/cron/* refuses to run without this matching.
CRON_SECRET = _env("CRON_SECRET")

# Fernet key encrypting StockSaathi tokens at rest. Absent means account
# linking is disabled rather than storing tokens in plain text.
LINK_ENC_KEY = _env("LINK_ENC_KEY")

# Base URL of the StockSaathi API used for live quotes and instrument search.
STOCKSAATHI_BASE_URL = _env("STOCKSAATHI_BASE_URL", "https://stocksaathi.co.in")

IS_PRODUCTION = _env("VERCEL_ENV") == "production"
