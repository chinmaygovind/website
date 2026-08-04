"""cgovind.com's account pages: one profile per person, across all four games.

Everything here hangs off the fact that the four games have always shared a
``users`` table and a session cookie. Nothing on this site is a fifth account
system - it is the pages that were missing from the one that already existed:
somewhere to see who somebody is, somewhere to change your own details, and
somewhere the four login screens can send you when you have forgotten your
password.

Registered onto the main website app by ``init_app``, which is a no-op when
there is no database configured. That matters: the website's whole job is
serving a static tree, and a missing ``DATABASE_URL`` in a checkout that only
wants to look at the landing page must not stop it booting. In that state the
account routes simply are not there.
"""

import os

from flask import Flask

from .models import db


def init_app(app: Flask):
    """Attach the accounts pages to ``app``. Returns True if they were attached.

    The caller (``app.py``) does not have to care whether this worked - a site
    with no database serves its static pages exactly as before, and the only
    difference is that ``/accounts`` 404s into the Mario game like any other
    address that isn't there.
    """
    database_url = _database_url()
    if not database_url:
        app.logger.info("accounts: no DATABASE_URL, account pages are off")
        return False

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # The session cookie *is* the single sign-on. Same secret and same domain as
    # the games, so a login anywhere under cgovind.com is a login here, and the
    # accounts pages never have to ask again for a password the visitor has
    # already typed into Drive.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
    if cookie_domain:
        app.config["SESSION_COOKIE_DOMAIN"] = cookie_domain
    if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    app.config["AVATAR_DIR"] = os.environ.get(
        "AVATAR_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "instance", "avatars"))

    _configure_sqlite(app, database_url)
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        # Creates `user_profiles` and nothing else that isn't already there -
        # CREATE TABLE IF NOT EXISTS, so the shared `users` table is untouched,
        # exactly as in the four games.
        db.create_all()

    return True


def _database_url():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _configure_sqlite(app, url):
    """WAL and a busy timeout, the same settings the four games open it with.

    Five processes share one SQLite file; without WAL a reader blocks a writer
    and a profile page can stall a live game. The pragmas are per-connection, so
    every one of them has to ask.
    """
    if not url.startswith("sqlite:"):
        return
    path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else ""
    if path and path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def _pragmas(dbapi_conn, _record):                   # pragma: no cover - driver hook
        try:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()
        except Exception:                                # noqa: BLE001
            pass
