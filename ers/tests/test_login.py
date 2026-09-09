"""The way out of being a guest.

A guest who clicked the nav used to be redirected straight back to the lobbies:
`login_page` counted a guest name as "already signed in", so the one link
offering an account was the one link that did nothing. These pin the shape that
replaced it - the guest stays a guest until they finish a form, and the link
lands them on the tab that makes an account.
"""

import os
import tempfile

import pytest


@pytest.fixture(scope="module")
def app_mod():
    """Import app.py against a throwaway database."""
    db_path = os.path.join(tempfile.mkdtemp(), "ers-login-test.db")
    os.environ["DATABASE_URL"] = "sqlite:///" + db_path
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import app as mod
    return mod


@pytest.fixture()
def client(app_mod):
    return app_mod.app.test_client()


def _guest(client, name="Quickdraw"):
    assert client.post("/guest", json={"name": name}).get_json()["ok"]


def test_a_guest_can_reach_the_login_page(client):
    _guest(client)
    resp = client.get("/login")
    assert resp.status_code == 200, \
        "a guest was redirected away from the page that makes accounts"


def test_the_nav_offers_a_guest_a_sign_up(client):
    """The nav only exists on the signed-in pages, so a guest is who sees this."""
    _guest(client)
    html = client.get("/lobbies").get_data(as_text=True)
    assert '<a href="/login?signup=1">Sign up</a>' in html
    assert '<a href="/login">Log in</a>' not in html


def test_the_page_opens_on_log_in_by_default(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'class="tab active" data-tab="login"' in html
    assert 'class="tabform active" id="f-login"' in html


def test_the_signup_link_opens_the_signup_tab(client):
    _guest(client)
    html = client.get("/login?signup=1").get_data(as_text=True)
    assert 'class="tab active" data-tab="register"' in html
    assert 'class="tabform active" id="f-register"' in html
    assert 'class="tabform active" id="f-login"' not in html


def test_a_guest_is_told_why_to_bother(client):
    _guest(client, "Quickdraw")
    assert "Quickdraw" in client.get("/login").get_data(as_text=True)


def test_an_account_is_still_sent_to_the_lobbies(client):
    made = client.post("/register", json={"username": "loginfixer",
                                          "email": "loginfixer@example.com",
                                          "password": "Password1!"})
    assert made.get_json()["ok"], made.get_json()
    resp = client.get("/login")
    assert resp.status_code == 302
    assert "/lobbies" in resp.headers["Location"]
