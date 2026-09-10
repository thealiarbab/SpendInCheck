"""The application factory.

Building the app inside a function rather than at import time is what lets
tests construct an app with their own settings, and keeps importing this
module free of side effects. The Vercel entrypoint and the local dev server
both call create_app(); neither owns configuration.

Since Phase 8 this app answers /api/v1 and nothing else. The site itself is
the built React bundle in web/dist, which Vercel serves from the edge
without troubling Python -- see vercel.json.
"""

from datetime import timedelta

from flask import Flask

from server import config, db
from server.routes.api import api, handle_unknown_path


def create_app(secret_key=None):
    """Build and return a configured Flask application.

    Passing secret_key overrides the configured one, which is how tests get a
    stable signing key without touching the environment.
    """
    # No templates and no static folder: this app serves JSON and nothing
    # else. The client is a built bundle the CDN serves, and static_folder
    # left at its default would register a /static route for a directory
    # that does not exist.
    app = Flask(__name__, static_folder=None)
    app.secret_key = secret_key or config.SECRET_KEY

    app.config.update(
        # The session cookie is the credential here, so script must never be
        # able to read it. Secure is conditional because local dev is plain
        # HTTP and the browser would otherwise drop the cookie entirely.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.IS_PRODUCTION,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    )

    _check_production_config(app)

    # One connection per request rather than one per query. Without the
    # teardown the connection would outlive the request and, on a reused
    # serverless container, never be given back to the pool.
    app.teardown_appcontext(db.close_request_connection)

    app.register_blueprint(api)

    # See handle_unknown_path: a routing miss belongs to no blueprint, so this
    # has to be registered here rather than on it.
    app.register_error_handler(404, handle_unknown_path)

    return app


def _check_production_config(app):
    """Refuse or warn about settings that are unsafe once deployed.

    Runs on every boot. Only meaningful when config.IS_PRODUCTION is true --
    local development is expected to use the defaults.
    """
    if not config.IS_PRODUCTION:
        return

    if app.secret_key == config.DEV_SECRET_KEY:
        # The session cookie carries user_id and is signed with this key, so a
        # key that is published in this repository is an authentication bypass:
        # anyone can mint a cookie for any account. Serving nothing is strictly
        # better than serving forgeable sessions, so this refuses to boot.
        raise RuntimeError(
            "SECRET_KEY is not set. Refusing to start in production: the "
            "fallback key is public, so any session signed with it can be "
            "forged. Set SECRET_KEY in the environment."
        )

    # DATABASE_URL is optional as long as the individual DB_* settings point
    # somewhere real, so only the combination is wrong: no URL and a host still
    # on its localhost default means nothing was configured at all. Left alone
    # it would surface as a connection error on every request rather than once
    # here, which is the same outage diagnosed the slow way.
    if not config.DATABASE_URL and config.DB_HOST == "localhost":
        raise RuntimeError(
            "No database is configured. Set DATABASE_URL to the Supabase "
            "pooler URL (port 6543), or set the DB_* variables."
        )
