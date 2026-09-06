"""Practice save states: the store behind them, and what invalidates one.

The half of this feature that can be tested from Python. The other half - that a
restored car drives out of a save state exactly the way it drove in - is in
`test_save_state_js.py`, which runs the real `Car` in QuickJS, and it is the one
that actually matters.

Nothing here checks that a practice lap stays off the board, because nothing here
*could*: the refusal is a flag the client sets and never posts. What keeps the
board honest is `verify.py` re-driving the input stream from the start line, and a
restored stream cannot survive that - `test_held_laps.py` is where that lives.
"""

import json as json_mod
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import boot_app, close_app        # noqa: E402


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    close_app(path, verify="0")


def _user(A, name="chinmay"):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _login(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid


def _slot(ms=41900, name="", stamp="deadbeef"):
    """A slot of roughly the shape the client sends, small enough to read.

    The car and run blobs are opaque to the server on purpose - it stores them
    and hands them back, and the only thing it has an opinion about is how many
    and how big.
    """
    return {"car": {"pos": [1, 2, 3], "vel": [0, 0, 0]},
            "run": {"time": ms, "splits": [], "nextCp": 2},
            "ghost": {"t": ms / 1000.0, "mode": "wr"},
            "label": "after CP2", "name": name, "ms": ms, "stamp": stamp}


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

def test_a_guest_is_told_no_and_is_not_an_error(env):
    """The rule `/api/start` and `/api/activity` already follow.

    A guest keeps their states in `localStorage` and `pending.js` hands them over
    at login. There is nothing to store and nothing has gone wrong, so a 401 here
    would be the client learning to treat a normal state as a failure.
    """
    c = env.app.test_client()
    r = c.put("/api/saves/sunrise", json={"saves": [_slot()]})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "stored": False}
    assert c.get("/api/saves").get_json()["tracks"] == {}


def test_slots_round_trip(env):
    c = env.app.test_client()
    _login(c, _user(env))
    slots = [_slot(23400), _slot(41900, name="the jump")]
    assert c.put("/api/saves/sunrise", json={"saves": slots}).status_code == 200
    got = c.get("/api/saves").get_json()["tracks"]
    assert got == {"sunrise": slots}


def test_a_write_replaces_the_whole_list(env):
    """Never one slot. Two tabs drilling the same track cannot interleave a
    partial update into a set of slots that never existed."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.put("/api/saves/sunrise", json={"saves": [_slot(1), _slot(2), _slot(3)]})
    c.put("/api/saves/sunrise", json={"saves": [_slot(9)]})
    got = c.get("/api/saves").get_json()["tracks"]["sunrise"]
    assert [s["ms"] for s in got] == [9]


def test_tracks_do_not_see_each_other(env):
    c = env.app.test_client()
    _login(c, _user(env))
    c.put("/api/saves/sunrise", json={"saves": [_slot(1)]})
    c.put("/api/saves/gauntlet", json={"saves": [_slot(2)]})
    got = c.get("/api/saves").get_json()["tracks"]
    assert sorted(got) == ["gauntlet", "sunrise"]
    assert got["sunrise"][0]["ms"] == 1


def test_accounts_do_not_see_each_other(env):
    a, b = _user(env, "chinmay"), _user(env, "someone")
    ca, cb = env.app.test_client(), env.app.test_client()
    _login(ca, a)
    _login(cb, b)
    ca.put("/api/saves/sunrise", json={"saves": [_slot(1)]})
    assert cb.get("/api/saves").get_json()["tracks"] == {}


def test_an_empty_list_deletes_the_row(env):
    """The panel's last [x] and its "clear this track" are the same gesture and
    should leave the same nothing behind - not an empty row."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.put("/api/saves/sunrise", json={"saves": [_slot()]})
    c.put("/api/saves/sunrise", json={"saves": []})
    with env.app.app_context():
        assert env.DriveSave.query.count() == 0


def test_delete_one_track_and_delete_everything(env):
    c = env.app.test_client()
    _login(c, _user(env))
    c.put("/api/saves/sunrise", json={"saves": [_slot()]})
    c.put("/api/saves/gauntlet", json={"saves": [_slot()]})
    c.delete("/api/saves/sunrise")
    assert list(c.get("/api/saves").get_json()["tracks"]) == ["gauntlet"]
    c.delete("/api/saves")
    assert c.get("/api/saves").get_json()["tracks"] == {}


# ---------------------------------------------------------------------------
# The ceilings
# ---------------------------------------------------------------------------

def test_only_nine_slots_are_kept(env):
    """Nine because that is how many digits there are to restore them with. The
    client refuses a tenth with a toast; the server truncates, because it is the
    thing that has to hold whatever any client sends."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.put("/api/saves/sunrise", json={"saves": [_slot(i) for i in range(1, 21)]})
    assert len(c.get("/api/saves").get_json()["tracks"]["sunrise"]) == 9


def test_an_enormous_payload_is_refused(env):
    """So the table cannot be used as free storage. Per track rather than per
    slot, so one enormous slot is refused as readily as ten."""
    c = env.app.test_client()
    _login(c, _user(env))
    fat = _slot()
    fat["car"] = {"junk": "x" * 40000}
    r = c.put("/api/saves/sunrise", json={"saves": [fat]})
    assert r.status_code == 413
    with env.app.app_context():
        assert env.DriveSave.query.count() == 0


def test_something_that_is_not_a_list_is_a_400(env):
    c = env.app.test_client()
    _login(c, _user(env))
    assert c.put("/api/saves/sunrise", json={"saves": {"1": _slot()}}).status_code == 400


def test_a_nonsense_track_is_a_404(env):
    """Checked before the login test, so a guest cannot use it to find out which
    slugs exist - though here it is only tidiness, since the pool is public."""
    c = env.app.test_client()
    _login(c, _user(env))
    assert c.put("/api/saves/../etc", json={"saves": []}).status_code == 404
    assert c.put("/api/saves/short", json={"saves": []}).status_code == 404


def test_a_draft_is_keyed_on_its_token_and_not_its_slug(env):
    """Every draft in the world drives under the one reserved `draft`, so keying
    on that would hand one person's states to the next track they built. It is
    the trap `localBest` documents, for the personal best."""
    c = env.app.test_client()
    _login(c, _user(env))
    token = "a1b2c3d4e5f60718"
    assert c.put("/api/saves/" + token, json={"saves": [_slot()]}).status_code == 200
    assert c.put("/api/saves/draft", json={"saves": [_slot()]}).status_code == 404
    assert list(c.get("/api/saves").get_json()["tracks"]) == [token]


# ---------------------------------------------------------------------------
# What invalidates a state
# ---------------------------------------------------------------------------

def test_every_track_carries_a_stamp_to_the_page(env):
    """A state is pinned to one, and refuses to restore when it no longer
    matches - so a track with no stamp would be a track whose states never go
    stale, silently."""
    import tracks as tracks_mod
    c = env.app.test_client()
    for slug in [t["slug"] for t in tracks_mod.TRACKS]:
        got = c.get("/api/track/" + slug).get_json()
        assert got.get("stamp"), slug


def test_moving_the_road_changes_the_stamp():
    """Under a slug the pool does not know, so the cache is out of the way. A
    pool track's geometry cannot change while the process is up - that is what
    makes caching it safe - so asking this question of one would only ever be
    asking the cache."""
    import tracks as tracks_mod
    t = dict(tracks_mod.get("sunrise"))
    t["slug"] = "not-a-pool-track"
    before = tracks_mod.stamp(t)
    t["line"] = [dict(e) for e in t["line"]]
    t["line"][10]["p"] = [t["line"][10]["p"][0] + 12, t["line"][10]["p"][1],
                          t["line"][10]["p"][2]]
    assert tracks_mod.stamp(t) != before


def test_a_pool_track_s_stamp_is_stable():
    """It is what a stored state is compared against, so a stamp that moved
    between two requests would strand every save state on the track."""
    import tracks as tracks_mod
    for slug in ("sunrise", "costco", "spa"):
        t = tracks_mod.get(slug)
        assert tracks_mod.stamp(t) == tracks_mod.stamp(dict(t))


def test_the_stamp_covers_the_track_s_own_collider():
    """The gap this closes. `moves.fingerprint` covers the ribbon, the gates and
    a *user* track's scenery document - but a third of the pool keeps its
    collider in a `scenery.js` next to `track.py`: Rickety Rails' portal frames,
    the Costco's racking, Silverstone's anti-cut barriers. Without those bytes in
    the hash, a save state stays valid across an edit that moved a wall into it.
    """
    import hashlib
    import tracks as tracks_mod
    from tracks import moves
    t = tracks_mod.get("costco")
    src = tracks_mod.scenery_source("costco")
    assert src, "costco is supposed to ship a scenery.js"
    ribbon_only = moves.fingerprint(t)
    assert tracks_mod.stamp(t) != ribbon_only[:16]
    h = hashlib.sha1()
    h.update(ribbon_only.encode())
    h.update(src.encode())
    assert tracks_mod.stamp(t) == h.hexdigest()[:16]


def test_two_drafts_do_not_share_a_stamp():
    """A draft is not cached, because its geometry changes under the one
    reserved slug every time somebody saves the editor."""
    import tracks as tracks_mod
    a = dict(tracks_mod.get("sunrise"))
    a["slug"] = "draft"
    a["user"] = True
    b = dict(a)
    b["line"] = [dict(e) for e in a["line"]]
    b["line"][5]["p"] = [b["line"][5]["p"][0] + 30] + list(b["line"][5]["p"][1:])
    assert tracks_mod.stamp(a) != tracks_mod.stamp(b)


# ---------------------------------------------------------------------------
# What is selected when you arrive
# ---------------------------------------------------------------------------

def test_loading_a_track_selects_no_save_state():
    """**Arriving is not practising.**

    `loadSaves` used to make slot 0 active as soon as it found any, so opening a
    track you had drilled last week put you straight into practice mode: `R`
    restored instead of restarting, and the first lap you drove silently did not
    count. That is the exact failure the tainted-run flag exists to prevent, and
    it would have happened on the one press nobody thinks about.

    Read off the source because the alternative is a browser, and there is none
    in CI. It is a narrow test of one assignment, which is all the bug was.
    """
    import os
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "static", "js", "game.js")).read()
    at = src.index("async function loadSaves() {")
    body = src[at:re.compile(r"^\}$", re.M).search(src, at).end()]
    assert "S.saveActive = -1;" in body, "arriving has to clear the selection"
    assert not re.search(r"S\.saveActive\s*=\s*[0-9]", body), \
        "nothing may pre-select a slot on arrival"
