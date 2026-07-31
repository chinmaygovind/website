"""The routes and APIs behind the switcher, the board and a guest's times.

These run against a throwaway SQLite file with the real app on top of it, so
they exercise the actual routes rather than a description of them. Everything
that talks to the database gets its own empty one per test.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def env():
    """A fresh app + database, and a client for it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path
    for mod in ("app", "models"):
        sys.modules.pop(mod, None)
    import app as A
    A.app.config["TESTING"] = True
    with A.app.app_context():
        A.db.drop_all()
        A.db.create_all()
    yield A
    os.unlink(path)


def _user(A, name="chinmay"):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _run_payload(A, slug="sunrise", seconds=None):
    """A run that will pass validation: real splits and a believable replay."""
    import runcheck
    import tracks as tracks_mod
    track = tracks_mod.get(slug)
    seconds = seconds or track["ideal"]
    ms = int(seconds * 1000)
    sp = track["spawn"]["p"]
    n = max(2, int(seconds * runcheck.GHOST_HZ))
    step = 20.0 / runcheck.GHOST_HZ
    ghost = [[sp[0] + i * step, sp[1] + 0.45, sp[2], 0, 0, 0, 1] for i in range(n)]
    ncp = track["checkpoints"]
    splits = [int(ms * (i + 1) / (ncp + 1)) for i in range(ncp)]
    return {"track": slug, "time_ms": ms, "splits": splits, "ghost": ghost,
            "distance": 500}


def _login(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid


# ---------------------------------------------------------------------------
# /solo, and the track you were last on
# ---------------------------------------------------------------------------

def test_solo_opens_the_track_you_were_last_on(env):
    """Solo is a door back into the game, not a menu, so it has to remember."""
    c = env.app.test_client()
    c.get("/solo/twist")
    assert b"Twin Loop" in c.get("/solo").data
    c.get("/solo/sunrise")
    assert b"Sunrise Circuit" in c.get("/solo").data


def test_the_switcher_records_where_you_moved_to(env):
    """Solo changes track without changing URL, so the server is told directly -
    otherwise coming back would land on the track you first arrived at."""
    c = env.app.test_client()
    c.get("/solo/sunrise")
    assert c.post("/api/last-track", json={"track": "gauntlet"}).status_code == 200
    assert b"The Gauntlet" in c.get("/solo").data


def test_a_nonsense_track_is_not_remembered(env):
    c = env.app.test_client()
    c.get("/solo/twist")
    assert c.post("/api/last-track", json={"track": "../etc/passwd"}).status_code == 404
    assert b"Twin Loop" in c.get("/solo").data


def test_an_unknown_track_url_falls_back_to_solo(env):
    r = env.app.test_client().get("/solo/no-such-track")
    assert r.status_code == 302 and r.headers["Location"].endswith("/solo")


# ---------------------------------------------------------------------------
# A guest's times, handed over at login
# ---------------------------------------------------------------------------

def test_a_guest_run_is_not_stored_but_is_not_refused(env):
    """The honest answer, so the browser knows to keep hold of the run."""
    r = env.app.test_client().post("/api/run", json=_run_payload(env))
    d = r.get_json()
    assert r.status_code == 200
    assert d["ok"] and d["guest"] and not d["stored"]
    assert d["run_rank"] == 1


def test_the_same_run_posted_after_logging_in_reaches_the_board(env):
    """The whole point: a lap set before there was an account still counts.

    This is exactly what pending.js replays on the first page load after login,
    so it is submitted through the ordinary endpoint with no special casing.
    """
    c = env.app.test_client()
    payload = _run_payload(env)
    assert c.post("/api/run", json=payload).get_json()["stored"] is False

    _login(c, _user(env))
    d = c.post("/api/run", json=payload).get_json()
    assert d["stored"] and d["improved"]
    assert d["pb_ms"] == payload["time_ms"] and d["rank"] == 1

    board = c.get("/api/board/sunrise").get_json()["rows"]
    assert [r["name"] for r in board] == ["chinmay"]
    assert board[0]["time_ms"] == payload["time_ms"]


def test_a_replayed_run_that_is_slower_than_your_pb_does_not_replace_it(env):
    c = env.app.test_client()
    _login(c, _user(env))
    fast = _run_payload(env, seconds=20)
    slow = _run_payload(env, seconds=30)
    c.post("/api/run", json=fast)
    d = c.post("/api/run", json=slow).get_json()
    assert d["stored"] and not d["improved"] and d["pb_ms"] == fast["time_ms"]


def test_being_fast_is_no_longer_a_reason_to_reject_a_run(env):
    """The floor under `ideal` is gone; the replay is what has to hold up."""
    import tracks as tracks_mod
    c = env.app.test_client()
    _login(c, _user(env))
    quick = tracks_mod.get("sunrise")["ideal"] * 0.6
    d = c.post("/api/run", json=_run_payload(env, seconds=quick)).get_json()
    assert d["ok"] and d["stored"], d


# ---------------------------------------------------------------------------
# The board, and racing somebody's lap
# ---------------------------------------------------------------------------

def test_a_board_row_carries_what_it_takes_to_open_it(env):
    """Splits and an id per row, so the detail pane needs no second request."""
    c = env.app.test_client()
    _login(c, _user(env))
    payload = _run_payload(env)
    c.post("/api/run", json=payload)
    row = c.get("/api/board/sunrise").get_json()["rows"][0]
    assert row["splits"] == payload["splits"]
    assert row["has_ghost"] and row["me"] and row["id"]


def test_the_board_says_which_row_is_yours_only_to_you(env):
    A = env
    mine, theirs = _user(A, "chinmay"), _user(A, "alex")
    c = A.app.test_client()
    _login(c, mine)
    c.post("/api/run", json=_run_payload(A, seconds=20))
    _login(c, theirs)
    c.post("/api/run", json=_run_payload(A, seconds=25))
    rows = {r["name"]: r["me"] for r in c.get("/api/board/sunrise").get_json()["rows"]}
    assert rows == {"chinmay": False, "alex": True}


def test_any_lap_on_the_board_can_be_fetched_as_a_ghost(env):
    """Which is what "race this person's lap" is, and it must work while logged
    out - the board is public and so is watching a replay from it."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=_run_payload(env))
    rid = c.get("/api/board/sunrise").get_json()["rows"][0]["id"]

    anon = env.app.test_client()
    d = anon.get("/api/ghost/sunrise?who=%d" % rid).get_json()
    assert d["ok"] and d["who"] == "chinmay" and len(d["ghost"]) > 2
    assert d["splits"] and d["id"] == rid


def test_a_ghost_id_from_another_track_is_not_served(env):
    """A replay fetched onto the wrong track would be played against geometry it
    was never driven on, so the id is scoped to the track that asked."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=_run_payload(env, slug="sunrise"))
    rid = c.get("/api/board/sunrise").get_json()["rows"][0]["id"]
    assert c.get("/api/ghost/twist?who=%d" % rid).get_json()["ghost"] is None


def test_the_record_ghost_is_the_fastest_one(env):
    A = env
    c = A.app.test_client()
    _login(c, _user(A, "slow"))
    c.post("/api/run", json=_run_payload(A, seconds=30))
    _login(c, _user(A, "quick"))
    c.post("/api/run", json=_run_payload(A, seconds=20))
    assert c.get("/api/ghost/sunrise?who=wr").get_json()["who"] == "quick"


# ---------------------------------------------------------------------------
# What the switcher and the home page show
# ---------------------------------------------------------------------------

def test_a_pb_never_appears_without_its_rank(env):
    A = env
    c = A.app.test_client()
    _login(c, _user(A, "leader"))
    c.post("/api/run", json=_run_payload(A, seconds=20))
    me = _user(A, "second")
    _login(c, me)
    c.post("/api/run", json=_run_payload(A, seconds=25))
    with A.app.test_request_context():
        from flask import session
        session["user_id"] = me
        cards = {t["slug"]: t for t in A._track_cards()}
        records = A._records()
    card = cards["sunrise"]
    assert card["pb_rank"] == 2 and card["pb_ms"] == 25000
    assert card["image"].startswith("/static/img/tracks/sunrise.png")
    # The record deliberately is not on a switcher card - picking a track should
    # not be a comparison with somebody else. It still reaches the home page.
    assert "wr_ms" not in card and "wr_by" not in card
    assert records["sunrise"] == (20000, "leader")


def test_every_track_has_a_preview_picture_on_disk(env):
    """The switcher shows photographs, so a missing one is a broken card. Run
    `python tools/shoot_tracks.py` after adding or reshaping a track."""
    import tracks as tracks_mod
    here = os.path.join(os.path.dirname(__file__), "..", "static", "img", "tracks")
    missing = [t["slug"] for t in tracks_mod.TRACKS
               if not os.path.exists(os.path.join(here, t["slug"] + ".png"))]
    assert not missing, "no preview picture for: " + ", ".join(missing)


def test_the_track_page_hands_each_lap_over_whole(env):
    """The public board opens a lap the same way the in-game one does."""
    c = env.app.test_client()
    _login(c, _user(env))
    payload = _run_payload(env)
    c.post("/api/run", json=payload)
    html = c.get("/track/sunrise").get_data(as_text=True)
    assert "rows-open" in html, "the rows have to look clickable"
    assert "has_ghost" in html, "Watch and Race need to know there is a replay"
    for ms in payload["splits"]:
        assert str(ms) in html, "every split is needed to open the lap"
