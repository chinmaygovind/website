"""`/j/<code>`: the link a chat invite carries. Opening it seats you in the
room, private or not, the way Drive's share link always has."""

import os
import tempfile

import pytest


@pytest.fixture(scope="module")
def app_mod():
    db_path = os.path.join(tempfile.mkdtemp(), "join-link-test.db")
    os.environ["DATABASE_URL"] = "sqlite:///" + db_path
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import app as mod
    return mod


def _guest(app_mod, name):
    c = app_mod.app.test_client()
    assert c.post("/guest", json={"name": name}).get_json()["ok"]
    return c


def test_the_link_seats_you_in_a_private_room(app_mod):
    host = _guest(app_mod, "Host")
    code = host.post("/create", json={"is_private": True, "passcode": "sekrit"}).get_json()["code"]
    friend = _guest(app_mod, "Friend")
    resp = friend.get("/j/" + code.lower())
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/lobby/" + code)
    assert friend.get("/lobby/" + code).status_code == 200


def test_a_dead_code_goes_to_the_lobbies(app_mod):
    resp = _guest(app_mod, "Lost").get("/j/NOPE00")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/lobbies")
