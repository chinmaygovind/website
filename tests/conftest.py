"""Fixtures for the accounts pages.

The app is a module-level object built at import time - ``accounts.init_app``
runs while ``app.py`` is being imported - so the environment has to be right
*before* the import rather than after it. That is why this sets the variables
and then imports, and why the app is built once for the session and pointed at
one throwaway SQLite file.

There is deliberately no SMTP here. ``accounts.mail`` treats "no mail server" as
a supported state and prints the letter instead, so the reset flow is walkable
in a test exactly as it is in a development checkout, and ``capsys`` is how a
test gets hold of the link.
"""

import os
import re
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def flask_app():
    tmp = tempfile.mkdtemp(prefix="accounts-test-")
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "test.db")
    os.environ["SECRET_KEY"] = "test-secret"
    os.environ["AVATAR_DIR"] = os.path.join(tmp, "avatars")
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("SESSION_COOKIE_DOMAIN", None)

    import app as app_module
    assert app_module.accounts_enabled, "accounts did not attach - check DATABASE_URL"
    app_module.app.config["TESTING"] = True
    app_module.app.config["SERVER_NAME"] = "cgovind.test"
    return app_module.app


@pytest.fixture
def db(flask_app):
    """A clean database per test, so no test can depend on another's users."""
    from accounts.models import db as _db
    with flask_app.app_context():
        _db.drop_all()
        _db.create_all()
        yield _db
        _db.session.remove()


@pytest.fixture
def client(flask_app, db):
    return flask_app.test_client()


@pytest.fixture
def make_user(flask_app, db):
    """Create an account. Returns the user id rather than the object, since the
    session is closed between the fixture and the assertions that use it."""
    def _make(username="tester", email=None, password="hunter2hunter2"):
        from accounts.models import User
        user = User(username=username, email=email or (username + "@example.com"))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id
    return _make


@pytest.fixture
def logged_in(client, make_user):
    """A client with a session cookie, and the id of who it belongs to."""
    def _login(username="tester", password="hunter2hunter2"):
        uid = make_user(username, password=password)
        resp = client.post("/accounts/login",
                           data={"username": username, "password": password})
        assert resp.status_code == 302, resp.data[:400]
        return uid
    return _login


def link_from_log(captured, kind):
    """Pull the one link out of the email that ``mail.send`` printed.

    With no SMTP configured the letter goes to stderr, link and all, which is
    both how a development checkout stays usable and how a test reads it
    without standing up a mail server.
    """
    found = re.findall(r"https?://\S*/accounts/%s\?t=[A-Za-z0-9_.\-]+" % kind,
                       captured.err + captured.out)
    assert found, "no %s link in the sent mail:\n%s" % (kind, captured.err[-2000:])
    return found[-1]
