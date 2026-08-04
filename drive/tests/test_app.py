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
    # The holder is the user rather than their name, so the records table can
    # put a flag and a profile link on it the way every other board does.
    assert records["sunrise"][0] == 20000
    assert records["sunrise"][1].username == "leader"
    # ...and when it was set, which is the records page's Date column.
    assert records["sunrise"][2] is not None


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


# ---------------------------------------------------------------------------
# Starts: the attempts that did not end in a time
# ---------------------------------------------------------------------------

def test_starting_a_run_counts_an_attempt(env):
    """The thing a board of finishes cannot tell you: how many goes it took."""
    c = env.app.test_client()
    _login(c, _user(env))
    for _ in range(3):
        assert c.post("/api/start", json={"track": "sunrise"}).get_json()["stored"]
    with env.app.app_context():
        row = env.DriveStart.query.filter_by(track="sunrise").first()
        assert row.starts == 3


def test_starts_are_counted_per_track(env):
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/start", json={"track": "sunrise"})
    c.post("/api/start", json={"track": "twist"})
    c.post("/api/start", json={"track": "twist"})
    with env.app.app_context():
        got = {r.track: r.starts for r in env.DriveStart.query.all()}
    assert got == {"sunrise": 1, "twist": 2}


def test_a_guest_start_is_refused_gently_and_a_nonsense_track_is_not(env):
    """Same shape as /api/run: no account is not an error, a bad slug is."""
    c = env.app.test_client()
    assert c.post("/api/start", json={"track": "sunrise"}).get_json() == {
        "ok": True, "stored": False}
    assert c.post("/api/start", json={"track": "nowhere"}).status_code == 404


def test_finishes_never_outnumber_the_starts_beside_them(env):
    """A database the backfill has not reached yet still has to read right.

    Between the deploy and `tools/backfill_starts.py` - and on any database it
    was never run against - there are finishes with no starts behind them at
    all. "0 starts, 200 finishes" is not a smaller number than the truth but a
    wrong one, so the finishes clamp the count on the way out to the screen too.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=_run_payload(env, seconds=30))
    c.post("/api/run", json=_run_payload(env, seconds=25))
    with env.app.app_context():
        env.DriveStart.query.delete()          # how a pre-counter database looks
        env.db.session.commit()
        times = env.DriveTime.query.all()
        assert env._starts_for(times[0].user_id, times) == {"sunrise": 2}
    assert "Starts" in c.get("/account").get_data(as_text=True)


def test_a_start_and_a_finish_are_the_same_attempt_not_two(env):
    """One go at a track that ends in a time is one start, not one of each."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/start", json={"track": "sunrise"})
    c.post("/api/run", json=_run_payload(env))
    with env.app.app_context():
        times = env.DriveTime.query.all()
        assert env._starts_for(times[0].user_id, times) == {"sunrise": 1}


def test_a_track_you_never_finished_still_shows_its_starts(env):
    """It has no time row, and it is the track the count says the most about."""
    c = env.app.test_client()
    _login(c, _user(env))
    for _ in range(7):
        c.post("/api/start", json={"track": "twist"})
    html = c.get("/account").get_data(as_text=True)
    assert "Twin Loop" in html, "a track with starts and no time still belongs"
    assert ">7</td>" in html, "with the number of goes it has had out of you"


def test_the_world_record_ghost_skips_a_lap_with_no_replay(env):
    """"World record" used to report that nobody had set a time here at all.

    It took the fastest row and served whatever replay was on it, and a row
    keeps its time whether or not a ghost was stored beside it - so one old
    row with no replay made the record ghost unusable on a track with a full
    board. Every other way in already only offers laps that have one, which is
    why picking the same lap through "view others" worked.
    """
    A = env
    c = A.app.test_client()
    uid = _user(A, "chinmay")
    _login(c, uid)
    c.post("/api/run", json=_run_payload(A, "sunrise", seconds=30))
    # Somebody quicker, from before replays were kept.
    with A.app.app_context():
        other = A.User(username="ghostless", email="g@example.com")
        other.set_password("password123")
        A.db.session.add(other)
        A.db.session.commit()
        A.db.session.add(A.DriveTime(user_id=other.id, track="sunrise",
                                     time_ms=1000, splits_json="[]", ghost=None))
        A.db.session.commit()

    d = c.get("/api/ghost/sunrise?who=wr").get_json()
    assert d["ghost"], "the record ghost must be a lap that can actually be shown"
    assert d["who"] == "chinmay"


def test_the_record_ghost_is_still_the_fastest_of_those_with_replays(env):
    A = env
    c = A.app.test_client()
    _login(c, _user(A, "slow"))
    c.post("/api/run", json=_run_payload(A, "sunrise", seconds=40))
    c2 = A.app.test_client()
    _login(c2, _user(A, "quick"))
    c2.post("/api/run", json=_run_payload(A, "sunrise", seconds=25))
    d = c.get("/api/ghost/sunrise?who=wr").get_json()
    assert d["who"] == "quick" and d["time_ms"] == 25000


def test_a_track_carries_the_record_on_it(env):
    """The medals card shows the record above the three medal times, so the
    record travels with the track rather than in a request of its own."""
    A = env
    c = A.app.test_client()
    assert c.get("/api/track/sunrise").get_json()["record_ms"] is None

    _login(c, _user(A, "chinmay"))
    c.post("/api/run", json=_run_payload(A, "sunrise"))
    got = c.get("/api/track/sunrise").get_json()
    assert got["record_ms"] > 0
    # The time and nothing else. Whose lap it is is the leaderboard's job.
    assert "record_by" not in got
    # The play page has to have it on the first paint, not after a round trip.
    assert '"record_ms"' in c.get("/solo/sunrise").get_data(as_text=True)


def test_the_track_dicts_are_not_mutated_by_serving_them(env):
    """`tracks_mod` holds one dict per track for the whole process, so adding
    the record to a response must never write into it."""
    import tracks as tracks_mod
    A = env
    c = A.app.test_client()
    c.get("/api/track/sunrise")
    assert "record_ms" not in tracks_mod.get("sunrise")


def test_the_account_tracks_are_in_the_same_order_as_everywhere_else(env):
    """The pool's order, the one the switcher and the home page use.

    It used to be most-recent-PB first, with the never-finished tracks in a
    block underneath - so the same track moved every time you drove, and no
    two pages agreed on where to look for it.
    """
    import tracks as tracks_mod
    A = env
    c = A.app.test_client()
    _login(c, _user(A))
    pool = [t["slug"] for t in tracks_mod.TRACKS]
    # Finish the last track in the pool first and the first one last, so
    # "most recent" is the exact reverse of the order that is wanted, and
    # start a middle one without ever finishing it.
    for slug in (pool[-1], pool[0]):
        c.post("/api/run", json=_run_payload(A, slug))
    c.post("/api/start", json={"track": pool[2]})

    html = c.get("/account").get_data(as_text=True)
    # The table itself and nothing after it - there is another list of every
    # track further down the page.
    table = html.split('acct-tracks', 1)[1].split('</table>', 1)[0]
    shown = [s for s in pool if tracks_mod.BY_SLUG[s]["name"] in table]
    seen = sorted(shown, key=lambda s: table.index(tracks_mod.BY_SLUG[s]["name"]))
    assert set(shown) == {pool[0], pool[2], pool[-1]}, "every driven track is listed"
    assert seen == [s for s in pool if s in shown], "and in the pool's order"


def test_a_race_start_is_counted_like_any_other(env):
    """A lap driven against other people is still a lap.

    The mode never reaches the server - `/api/start` is posted from the one
    place the clock starts - so what needs pinning is that the race branch
    posts it as well as the solo one.
    """
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "static", "js", "game.js")) as f:
        src = f.read()
    branches = src.split("S.run.start(")[1:]
    assert len(branches) == 2, "the clock now starts somewhere new: count it too"
    for b in branches:
        assert "noteStart()" in b[:160], "a start that is not counted"


def test_a_finish_lifts_the_start_count_in_the_row_not_just_on_the_screen(env):
    """Otherwise the next real start lands under the backlog and vanishes.

    A guest's kept laps arrive here at login with no starts behind them. If the
    finishes only clamped the number on the way out, the start after them would
    be stored as 1 against 5 finishes and show as 5 - and so would the next
    four. The counter would look right and stop moving.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    for s in (34, 33, 32, 31, 30):                 # five laps, no starts posted
        c.post("/api/run", json=_run_payload(env, seconds=s))
    with env.app.app_context():
        assert env.DriveStart.query.filter_by(track="sunrise").first().starts == 5
    c.post("/api/start", json={"track": "sunrise"})
    with env.app.app_context():
        times = env.DriveTime.query.all()
        assert env._starts_for(times[0].user_id, times) == {"sunrise": 6}


def test_the_backfill_seeds_old_finishes_and_can_be_run_twice(env):
    """The one-shot for players who were driving before starts were counted."""
    import tools.backfill_starts as bf
    c = env.app.test_client()
    uid = _user(env)
    _login(c, uid)
    c.post("/api/run", json=_run_payload(env, "sunrise", seconds=30))
    c.post("/api/run", json=_run_payload(env, "twist", seconds=40))
    # Wind the database back to how a pre-starts one looks: finishes, no starts.
    with env.app.app_context():
        env.DriveStart.query.delete()
        env.db.session.commit()

    seeded, fine, added = bf.backfill(dry_run=True)
    assert (seeded, added) == (2, 2)
    with env.app.app_context():
        assert env.DriveStart.query.count() == 0, "--dry-run writes nothing"

    assert bf.backfill()[0] == 2
    with env.app.app_context():
        assert {r.track: r.starts for r in env.DriveStart.query.all()} == {
            "sunrise": 1, "twist": 1}

    # Idempotent: every write is a max, so a second pass is a no-op.
    c.post("/api/start", json={"track": "sunrise"})
    assert bf.backfill() == (0, 2, 0)
    with env.app.app_context():
        assert env.DriveStart.query.filter_by(track="sunrise").first().starts == 2


# ---------------------------------------------------------------------------
# The track you are on, and the links that name it
# ---------------------------------------------------------------------------

def test_every_link_that_names_the_track_is_repointable(env):
    """The switcher changes the world under a page rendered for another track.

    You arrive from the home page on `/solo/<slug>`, switch track, and the
    leaderboard button still points at the track you arrived on - so it has to
    carry the hook `loadTrack` uses to repoint it.
    """
    html = env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert html.count('class="btn secondary board-link"') == 2, (
        "both leaderboard links must be repointable")
    # The help sheet used to name the track as well, and had to be repointed
    # with the rest. It is the controls table now and names nothing, so the
    # blurb lives only on the track card - which is rewritten by `loadTrack`
    # through `trackName` / `trackBlurb`.
    assert 'id="helpBlurb"' not in html
    assert 'id="trackBlurb"' in html

    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "static", "js", "game.js")).read()
    load = src[src.index("function loadTrack("):]
    load = load[:load.index("\n}\n")]
    for needle in ("board-link", "document.title", "trackBlurb"):
        assert needle in load, "loadTrack leaves %s stale" % needle


def test_switching_track_rewrites_the_url_but_not_in_a_room():
    """`/solo/<slug>` is a link people copy out of the bar, so it has to name
    the track on the screen. A room's URL is its join code and is not about the
    track at all."""
    here = os.path.dirname(__file__)
    src = open(os.path.join(here, "..", "static", "js", "game.js")).read()
    fn = src[src.index("async function switchTrack("):]
    fn = fn[:fn.index("\n}\n")]
    # The comments here discuss pushState at length; the code must not use it.
    code = "\n".join(ln for ln in fn.splitlines()
                     if not ln.lstrip().startswith("//"))
    assert "history.replaceState" in code, "the URL goes stale on a switch"
    assert "pushState" not in code, "a switch is not somewhere to go Back out of"
    assert "CFG.mode !== 'room'" in code, "a room's URL must be left alone"


def test_the_records_page_dates_the_record_and_drops_the_gold_time(env):
    """Gold time is a property of the track, not of whoever holds the record."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=_run_payload(env, "sunrise", seconds=22))
    html = c.get("/leaderboard").get_data(as_text=True)
    assert "<th class=\"num\">Date</th>" in html
    assert "Gold time" not in html
    with env.app.app_context():
        row = env.DriveTime.query.filter_by(track="sunrise").first()
        assert row.updated_at.strftime("%Y") in html, "the record has to be dated"
    assert "<time datetime=" in html and "UTC</time>" in html, (
        "served as UTC so it is right before any script runs")


def test_a_track_with_no_record_still_lists(env):
    """Nine rows, record or not - the table is the pool, not the records."""
    html = env.app.test_client().get("/leaderboard").get_data(as_text=True)
    import tracks as tracks_mod
    for t in tracks_mod.TRACKS:
        assert t["name"] in html
