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

    # Werkzeug refuses an oversized body before reading it, which matters
    # because the avatar route's own 5MB check happens after the upload is in
    # memory - nginx allows 20m, so without this a request could put 20MB there
    # just to be told no. A little over the avatar limit, so the friendly
    # message is what people actually see and this is only the backstop.
    from .avatars import MAX_UPLOAD
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD + 1024 * 1024

    from werkzeug.exceptions import RequestEntityTooLarge

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(_e):
        # Flask's own page for this says "413 Request Entity Too Large", which
        # is true and is no help to somebody who picked a photo.
        from flask import render_template, request
        if request.path.startswith("/accounts/"):
            return render_template(
                "accounts/message.html", title="That file is too big",
                body="Profile pictures have to be under 5MB. Try a smaller one.",
                link="/accounts/settings", link_text="Back to settings"), 413
        return "That upload is too large.", 413

    # Who may read /admin. A comma-separated list of usernames, defaulting to
    # the one account that would ever be on it - which matters operationally,
    # because the deploy never touches the box's .env, so a console that
    # *required* a new variable there would be dark until somebody SSHed in.
    # In config rather than read at import so a test can move it: the app is
    # built once per test session, long before any individual test runs.
    app.config["ADMIN_USERNAMES"] = os.environ.get("ADMIN_USERNAMES", "chinmay")

    _configure_sqlite(app, database_url)
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    # The admin console. Its own blueprint rather than more routes on the one
    # above, for two reasons: it mounts at /admin rather than under /accounts,
    # and a blueprint is what lets one `before_request` gate every route on it
    # by construction instead of by a decorator somebody has to remember. See
    # `accounts/admin.py`.
    from .admin import bp as admin_bp
    app.register_blueprint(admin_bp)

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
