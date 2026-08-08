"""The routes and APIs behind the switcher, the board and a guest's times.

These run against a throwaway SQLite file with the real app on top of it, so
they exercise the actual routes rather than a description of them. Everything
that talks to the database gets its own empty one per test.
"""

import json as json_mod
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
    """A run that will pass validation: a replay that drives the track.

    It used to be a straight line along +X from the spawn with evenly spaced
    splits, which stopped being acceptable when `validate` started comparing a
    replay to the course - that fixture *was* the replay-synthesis hole.
    """
    import tracks as tracks_mod
    from conftest import lap_frames, lap_splits
    track = tracks_mod.get(slug)
    seconds = seconds or track["ideal"]
    ms = int(seconds * 1000)
    ghost = lap_frames(track, seconds=seconds)
    return {"track": slug, "time_ms": ms, "splits": lap_splits(track, ghost),
            "ghost": ghost, "distance": 500}


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
    """The floor under `ideal` is gone; the replay is what has to hold up.

    0.8 rather than the 0.6 this used to ask for, and the difference is the
    fixture and not the rule. The replay drives the *centreline*, which is longer
    than any racing line, so it carries more speed than a real lap at the same
    fraction of ideal - and 0.6 of ideal round the outside of every corner needs
    70 u/s, which is a car this game does not have. The quickest lap ever set on
    the site is 0.754 of ideal and medians 48.2.
    """
    import tracks as tracks_mod
    c = env.app.test_client()
    _login(c, _user(env))
    quick = tracks_mod.get("sunrise")["ideal"] * 0.8
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


def test_the_records_page_is_three_named_boards_in_order(env):
    """Track records, then the time trials, then the multiplayer ratings.

    The middle one is new, and the last one was called "Race ratings" and was
    the only heading on the page carrying a line of explanation under it. Three
    boards on one page are a set: one of them dressed differently reads as
    though it were a different kind of thing.
    """
    html = env.app.test_client().get("/leaderboard").get_data(as_text=True)
    at = [html.index("Track Records"), html.index("Time Trials Leaderboard"),
          html.index("Multiplayer Leaderboard")]
    assert at == sorted(at), "the three boards are in that order down the page"
    assert "Race ratings" not in html, "the multiplayer board is named for the mode"
    assert "From finishing positions in multiplayer races" not in html, (
        "no board on this page carries a subtitle")


def test_every_column_heading_on_a_board_is_in_the_one_font(env):
    """A heading row is labels, so every label on it is the display face.

    `table.board th.num` was handed `var(--mono)` along with the cells beneath
    it, which split one heading row into two fonts and left the left-hand
    labels looking pasted in from another table. The cells keep the distinction,
    which is where it does the work - figures line up under each other.
    """
    import re
    here = os.path.dirname(__file__)
    css = open(os.path.join(here, "..", "static", "css", "style.css")).read()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # prose, not selectors
    for rule in css.split("}"):
        if "font-family" not in rule or "var(--mono)" not in rule:
            continue
        sel = rule.split("{")[0]
        assert not re.search(r"\bth\b", sel), (
            "a column heading must not be mono: %s" % sel.strip())
    assert "table.board td.num { font-family: var(--mono); }" in css


# --- the Time Trials board --------------------------------------------------
# Golf scoring: your placing on each of the twelve tracks, added up, so low is
# good and a clean sweep of the pool is 12.

def _pbs(A, name, times, bot=False):
    """A driver with a personal best on each track in `times` ({slug: ms}).

    Written straight into `drive_times` rather than driven through `/api/run`:
    these tests are about what a table of times adds up to, and posting a
    believable replay for each of twelve tracks would put the lap validator in
    the middle of an arithmetic test.
    """
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com", is_bot=bot)
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        for slug, ms in times.items():
            A.db.session.add(A.DriveTime(user_id=u.id, track=slug, time_ms=ms,
                                         splits_json="[]"))
        A.db.session.commit()
        return u.id


def _tt(A):
    """The Time Trials board as {username: row}."""
    with A.app.app_context():
        return {r["user"].username: r for r in A._time_trial_board()}


def _pool(A):
    import tracks as tracks_mod
    return [t["slug"] for t in tracks_mod.TRACKS]


def test_the_time_trial_score_is_the_sum_of_your_placings(env):
    """Ten firsts and two thirds is 16."""
    A = env
    slugs = _pool(A)
    # Quickest on the first ten, and beaten by both of the others on the last two.
    _pbs(A, "sweeper", {s: (1000 if i < 10 else 3000) for i, s in enumerate(slugs)})
    _pbs(A, "second", {s: 2000 for s in slugs})
    _pbs(A, "third", {s: 2500 for s in slugs})

    board = _tt(A)
    assert board["sweeper"]["score"] == 10 * 1 + 2 * 3 == 16
    assert board["second"]["score"] == 10 * 2 + 2 * 1
    assert board["third"]["score"] == 10 * 3 + 2 * 2
    assert [board[n]["pos"] for n in ("sweeper", "second", "third")] == [1, 2, 3], (
        "low is good"
    )
    assert board["sweeper"]["best"] == "1st" and board["third"]["best"] == "2nd"


def test_a_track_you_have_never_driven_counts_as_one_worse_than_last(env):
    """Adding up only the tracks you have driven makes driving fewer the way to win."""
    A = env
    slugs = _pool(A)
    _pbs(A, "everywhere", {s: 2000 for s in slugs})
    _pbs(A, "oneandgone", {slugs[0]: 1000})     # quickest on one track, nothing else

    board = _tt(A)
    # On the first track 1000 beats 2000. On the other eleven only one driver has
    # a time at all, so the missing lap is second of two.
    assert board["oneandgone"]["score"] == 1 + 11 * 2
    assert board["everywhere"]["score"] == 2 + 11 * 1
    assert board["everywhere"]["pos"] == 1, (
        "one lonely first place must not beat a full sweep")
    assert board["oneandgone"]["driven"] == 1
    assert board["everywhere"]["driven"] == board["everywhere"]["of"] == len(slugs)


def test_an_equal_time_shares_the_placing(env):
    """The same rule a placing on one track already uses: strictly faster, plus one."""
    A = env
    slugs = _pool(A)
    for name in ("dead", "heat"):
        _pbs(A, name, {s: 2000 for s in slugs})
    _pbs(A, "slower", {s: 3000 for s in slugs})

    board = _tt(A)
    assert board["dead"]["score"] == board["heat"]["score"] == len(slugs)
    assert board["dead"]["pos"] == board["heat"]["pos"] == 1, (
        "an equal score is an equal place")
    assert board["slower"]["score"] == 3 * len(slugs), "two laps are faster on every track"
    assert board["slower"]["pos"] == 3, "a shared place still uses up two of them"


def test_a_new_personal_best_moves_everybody_it_overtook(env):
    """Which is why the score is derived on the way to the screen and stored nowhere.

    A PB is not only a change to your own score - it demotes everybody it
    passed. A number kept per driver would have to rewrite most of the board on
    every lap; derived, both halves land on the next page load.
    """
    A = env
    c = A.app.test_client()
    _pbs(A, "slowcoach", {"sunrise": 30000})
    _login(c, _pbs(A, "quick", {}))

    before = _tt(A)
    assert "quick" not in before, "a driver with no times has no placings to add up"
    assert before["slowcoach"]["best"] == "1st"

    c.post("/api/run", json=_run_payload(A, "sunrise", seconds=22))

    after = _tt(A)
    assert after["quick"]["best"] == "1st"
    assert after["slowcoach"]["best"] == "2nd", "the driver who was passed moves too"
    assert after["slowcoach"]["score"] == before["slowcoach"]["score"] + 1


def test_a_bot_is_not_a_driver_on_the_time_trials_board(env):
    """Same filter the ratings board applies: a bot is not somebody's rival here."""
    A = env
    slugs = _pool(A)
    _pbs(A, "human", {s: 2000 for s in slugs})
    _pbs(A, "botzilla", {s: 1000 for s in slugs}, bot=True)

    board = _tt(A)
    assert "botzilla" not in board
    assert board["human"]["score"] == len(slugs), (
        "and a bot's laps do not push a person down the field either")


def test_the_time_trials_board_reaches_the_page(env):
    """The score, what it is out of, and a way to the driver."""
    A = env
    _pbs(A, "quick", {"sunrise": 20000})
    html = A.app.test_client().get("/leaderboard").get_data(as_text=True)
    tt = html[html.index("Time Trials Leaderboard"):html.index("Multiplayer Leaderboard")]
    assert 'href="/account/quick"' in tt, "a name on a board is a way to that driver"
    import tracks as tracks_mod
    assert "1/%d" % len(tracks_mod.TRACKS) in tt, "one track driven of the pool"


def test_the_score_heading_carries_its_own_explanation(env):
    """"Score" is the one heading here that does not explain itself.

    It says so where it stands, rather than the board growing a line of small
    print underneath that neither of the other two has - and as a `title`,
    which is how every other hover on Drive works.
    """
    A = env
    _pbs(A, "quick", {"sunrise": 20000})
    html = A.app.test_client().get("/leaderboard").get_data(as_text=True)
    tt = html[html.index("Time Trials Leaderboard"):html.index("Multiplayer Leaderboard")]
    assert ('title="Time Trial Score is the sum of your best lap\'s rank on '
            'each track"') in tt
    assert 'class="whatsthis"' in tt, "and it has to look like something to hover"

    here = os.path.dirname(__file__)
    css = open(os.path.join(here, "..", "static", "css", "style.css")).read()
    assert ".whatsthis {" in css, "a mark nobody can see is not a mark"


# --- the boards point at Drive's own account page ---------------------------

def test_a_name_on_a_board_opens_that_driver_on_drive(env):
    """A lap time raises a question about that driver's *other* laps.

    The boards used to jump straight out to the profile on the main site, which
    is the right page for "who is this across four games" and the wrong one for
    "how do they go round here". They point at `/account/<username>` now, and
    that page carries the link on to the shared profile.
    """
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    c.post("/api/run", json=_run_payload(env, "sunrise", seconds=22))
    for page in ("/leaderboard", "/track/sunrise"):
        html = env.app.test_client().get(page).get_data(as_text=True)
        assert 'href="/account/quick"' in html, page
        assert "/accounts/quick" not in html, "%s links here first" % page


def test_somebody_elses_drive_page_is_public_and_leads_on(env):
    """No login needed to read it, and the one link off it is the main site."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    c.post("/api/run", json=_run_payload(env, "sunrise", seconds=22))

    html = env.app.test_client().get("/account/quick").get_data(as_text=True)
    import tracks as tracks_mod
    assert tracks_mod.BY_SLUG["sunrise"]["name"] in html, (
        "a stranger sees the record, not a login page")
    assert "/accounts/quick" in html, "and a way on to all four games"
    assert "@quick on cgovind" in html
    assert "Your cgovind account" not in html, "it is not your page"


def test_your_own_name_lands_on_your_own_account_page(env):
    """One canonical address for your own record - `/account`, where the nav
    sends you - rather than a second copy of it by name."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    resp = c.get("/account/quick")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/account")
    assert "Your cgovind account" in c.get("/account").get_data(as_text=True)


def test_a_drive_profile_has_one_spelling_and_has_to_exist(env):
    c = env.app.test_client()
    _user(env, "Quick")
    resp = c.get("/account/QUICK")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/Quick")
    assert c.get("/account/nobody-at-all").status_code == 404


def test_reading_a_stranger_writes_nothing(env):
    """`_stats` makes a row on first touch, which is right for your own page and
    wrong for a stranger opening somebody else's: a GET by a passer-by would
    otherwise leave a `drive_stats` row behind for every account ever looked at.
    """
    uid = _user(env, "quick")
    assert env.app.test_client().get("/account/quick").status_code == 200
    with env.app.app_context():
        assert env.DriveStats.query.filter_by(user_id=uid).first() is None


# ---------------------------------------------------------------------------
# The garage
# ---------------------------------------------------------------------------

def test_the_garage_needs_a_login_and_comes_back_to_itself(env):
    """A livery is stored against an account, so there is nowhere to put a
    guest's - and the redirect carries `next`, because being sent to the login
    page and then dumped on the home page is losing the thing you clicked."""
    c = env.app.test_client()
    resp = c.get("/garage")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert "next=%2Fgarage" in resp.headers["Location"] or \
        "next=/garage" in resp.headers["Location"]

    _login(c, _user(env, "quick"))
    assert c.get("/garage").status_code == 200


def test_the_nav_offers_the_garage_and_the_account_page_offers_logging_out(env):
    """The garage took `Log out`'s slot in the nav, so the way out has to be
    somewhere - beside your own name, on the one page that is about you. Both
    halves are checked because losing either is losing a door."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    # The nav is on the pages around the game, not on the play page - the HUD is
    # the play page's navigation.
    nav = c.get("/leaderboard").get_data(as_text=True)
    assert 'href="/garage"' in nav
    assert 'href="/logout"' not in nav, "the nav slot is the garage's now"

    mine = c.get("/account").get_data(as_text=True)
    assert 'href="/logout"' in mine

    other = env.app.test_client().get("/account/quick").get_data(as_text=True)
    assert 'href="/logout"' not in other, "not on somebody else's page"


def test_a_guest_is_offered_a_login_and_not_a_garage(env):
    """A garage a guest cannot own would be a door onto a locked room."""
    html = env.app.test_client().get("/leaderboard").get_data(as_text=True)
    assert 'href="/garage"' not in html
    assert 'href="/login"' in html


def test_the_livery_round_trips_through_the_api(env):
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    got = c.post("/api/garage", json={"body": "#7b6cf6", "finish": "gloss",
                                      "livery": "twin", "rim_style": "spoke5",
                                      "roof": "#ffffff"}).get_json()
    assert got["ok"] is True
    assert got["livery"]["body"] == "#7b6cf6"
    assert got["livery"]["finish"] == "gloss"
    assert got["livery"]["roof"] == "#ffffff"
    assert c.get("/api/garage").get_json()["livery"] == got["livery"]


def test_a_gated_item_is_stored_but_not_worn(env):
    """The split `validate` and `resolve` exist for. What you asked for is kept,
    so earning it later puts it on without you having to ask twice - and until
    then the car wears the default however the request arrived."""
    c = env.app.test_client()
    uid = _user(env, "quick")
    _login(c, uid)
    got = c.post("/api/garage", json={"badge": "shield",
                                      "rim_style": "forged"}).get_json()
    assert got["livery"]["badge"] == "none"
    assert got["livery"]["rim_style"] == "stock"
    with env.app.app_context():
        import garage
        row = env.DriveGarage.query.filter_by(user_id=uid).first()
        assert garage.loads(row.livery_json)["badge"] == "shield", (
            "the ask is kept, so earning it later is not asking twice")


def test_a_guest_cannot_write_a_livery(env):
    assert env.app.test_client().post("/api/garage", json={"body": "#7b6cf6"}) \
        .status_code == 401


def test_junk_posted_to_the_garage_is_not_a_five_hundred(env):
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    for junk in ({"body": []}, {"finish": 7}, {"nothing_like_a_slot": "x"},
                 {"trim": "#zzzzzz"}, {}):
        assert c.post("/api/garage", json=junk).status_code == 200


def test_the_play_page_carries_the_livery_on_the_first_paint(env):
    """Embedded rather than fetched, the same reason the track payload is: the
    car has to be right before any request lands, or it is repainted a frame in."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    c.post("/api/garage", json={"body": "#7b6cf6", "livery": "band"})
    html = c.get("/solo").get_data(as_text=True)
    assert "carLivery" in html
    assert "#7b6cf6" in html and '"livery":"band"' in html


def test_a_ghost_wears_its_drivers_car(env):
    """A lap set before the garage existed has no stored livery and gets its
    owner's current one, which is right: it is their car."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    c.post("/api/run", json=_run_payload(env, "sunrise", seconds=22))
    c.post("/api/garage", json={"body": "#17bfa8", "rim_style": "mesh"})
    got = c.get("/api/ghost/sunrise?who=wr").get_json()
    assert got["livery"]["body"] == "#17bfa8"
    assert got["livery"]["rim_style"] == "mesh"
    assert got["color"] == "#17bfa8", "and the old field agrees with it"


def test_the_swatch_and_the_car_are_one_answer(env):
    """`car_color` predates the garage and is still what a swatch is drawn from -
    the self dot on the minimap, a standings row in solo - while `car_livery` is
    what the car is built from. Computing them separately is how they came to
    disagree for a guest, whose livery is hashed off the name they typed and
    whose `color_for(None)` is the one guest red."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    c.post("/api/garage", json={"body": "#17bfa8"})
    html = c.get("/solo").get_data(as_text=True)
    import re
    swatch = re.search(r'carColor:\s*"([^"]+)"', html)
    assert swatch, "carColor is not on the page at all"
    assert swatch.group(1) == "#17bfa8"


def test_two_guests_in_a_room_are_not_the_same_car(env):
    """Guests have no account to keep a livery against, so their colour is still
    the hash of the name they typed - and that is exactly what let the first-free
    colour rule be deleted. Resolve a guest against nothing instead and every one
    of them comes out `GUEST_COLOR`, which is the bug that rule existed to
    prevent, arriving from the other end."""
    import garage
    with env.app.app_context():
        assert env._livery_for(None, name="dave")["body"] == \
            garage.color_for("dave")
        assert env._livery_for(None, name="dave")["body"] != \
            env._livery_for(None, name="erin")["body"]
        assert env._livery_for(None)["body"] == garage.GUEST_COLOR


def test_the_pole_lap_is_chased_in_its_drivers_car(env):
    """The one ghost everybody in a qualifying session is looking at, and it went
    out with a body colour and nothing else - so the pole driver's paint arrived
    on stock wheels with no stripe. `_seat_livery` answers the whole car, and
    answers it *now* rather than from the live car dict: that copy is only as
    fresh as their last connect, and a ghost is a lap you are chasing today.
    """
    import garage
    with env.app.app_context():
        game = env.DriveGame(code="POLE01", track="sunrise")
        u = env.User(username="quick", email="q@example.com")
        u.set_password("password123")
        env.db.session.add_all([game, u])
        env.db.session.commit()
        me = env.DrivePlayer(game_id=game.id, user_id=u.id, session_key="sk-q",
                             name="quick", color="#fff", seat_order=0)
        guest = env.DrivePlayer(game_id=game.id, session_key="sk-g", name="dave",
                                color="#fff", seat_order=1)
        env.db.session.add_all([me, guest])
        env.db.session.add(env.DriveGarage(
            user_id=u.id, earned_json="[]",
            livery_json=garage.dumps({"body": "#17bfa8", "rim_style": "mesh",
                                      "livery": "twin"})))
        env.db.session.commit()

        got = env._seat_livery("POLE01", me.pid)
        assert got["body"] == "#17bfa8" and got["rim_style"] == "mesh"
        assert got["livery"] == "twin", "the whole car, not just the colour"
        # A guest has no garage row and still gets a car rather than a hole,
        # hashed off the name they typed - the same as their seat.
        assert env._seat_livery("POLE01", guest.pid)["body"] == \
            garage.color_for("dave")
        # And a seat that is not in this room is not a car.
        assert env._seat_livery("POLE01", "p9999") is None
        assert env._seat_livery("NOSUCH", me.pid) is None


def test_the_pole_ghost_leaves_the_wire_with_a_whole_car(env):
    """And through an actual socket, which is unusual here - `test_race.py` builds
    the live room's dicts directly on the grounds that the bookkeeping is what
    matters. The wire is what mattered this time: `_seat_livery` can be right
    while the emit next to it still sends only a colour, and that is exactly the
    bug this pins.

    The car dict is left holding a stale white on purpose. It is only ever as
    fresh as that driver's last connect, so it is the wrong place to answer from -
    and `color` coming back as the livery's body rather than the white is what
    says the two are one answer instead of two.
    """
    import garage
    A = env
    with A.app.app_context():
        game = A.DriveGame(code="POLEX", track="sunrise", status="waiting")
        u = A.User(username="ghosty", email="g@example.com")
        u.set_password("password123")
        A.db.session.add_all([game, u])
        A.db.session.commit()
        A.db.session.add(A.DriveGarage(
            user_id=u.id, earned_json="[]",
            livery_json=garage.dumps({"body": "#17bfa8", "rim_style": "mesh",
                                      "livery": "twin"})))
        me = A.DrivePlayer(game_id=game.id, user_id=u.id, session_key="sk-g",
                           name="ghosty", color="#ffffff", seat_order=0)
        A.db.session.add(me)
        A.db.session.commit()
        uid, pid = u.id, me.pid
        r = A._room("POLEX")
        r["phase"] = "qualifying"
        car = A._car(r, pid)
        car["name"], car["color"] = "ghosty", "#ffffff"      # the stale copy
        r["pole"] = {"pid": pid, "name": "ghosty", "color": "#ffffff",
                     "ms": 20000, "hz": 15,
                     "frames": [[0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1]]}

    fc = A.app.test_client()
    with fc.session_transaction() as s:
        s["session_key"], s["user_id"] = "sk-g", uid
    cl = A.socketio.test_client(A.app, flask_test_client=fc)
    cl.emit("join_room_", {"code": "POLEX"})
    cl.get_received()
    cl.emit("qual_pole_req", {})
    sent = [e["args"][0] for e in cl.get_received() if e["name"] == "qual_pole_ghost"]
    assert sent, "no pole ghost came back at all"
    d = sent[0]
    assert d["livery"]["rim_style"] == "mesh" and d["livery"]["livery"] == "twin"
    assert d["color"] == "#17bfa8", "the colour is the livery's, not the car dict's"
    assert len(d["ghost"]) == 2 and d["who"] == "ghosty"


def test_the_garage_payload_carries_how_far_along_you_are(env):
    """So the page can say `Pinstripe: A gold on every track (9/12)` rather than
    only that it is locked. The numbers come from the server beside the check,
    not from the client counting rows it can see."""
    import tracks as tracks_mod
    c = env.app.test_client()
    uid = _user(env, "quick")
    _login(c, uid)
    with env.app.app_context():
        env.db.session.add(env.DriveStats(user_id=uid, golds=4))
        env.db.session.commit()
    gates = {g["id"]: g for g in c.get("/api/garage").get_json()["gates"]}
    n = len(tracks_mod.TRACKS)
    assert gates["shield"]["got"] is True and gates["shield"]["have"] == 3
    assert gates["pinstripe"] == dict(gates["pinstripe"],
                                      have=4, need=n, got=False)
    # And the page itself carries it, so the first paint is right.
    assert '"have": 4' in c.get("/garage").get_data(as_text=True) or \
        '"have":4' in c.get("/garage").get_data(as_text=True)


def test_the_garage_page_is_a_stage_and_not_a_document(env):
    """It opts out of `.wrap` entirely: the whole screen under the nav is the
    car. `body.garage-page` is what turns the page into a flex column, so losing
    it would silently put a 100dvh canvas inside a scrolling document."""
    c = env.app.test_client()
    _login(c, _user(env, "quick"))
    html = c.get("/garage").get_data(as_text=True)
    assert 'class="garage-page"' in html
    assert '<canvas id="gcanvas">' in html
    assert 'class="wrap' not in html, "the stage is not a document column"


# ---------------------------------------------------------------------------
# The way out of a replay
# ---------------------------------------------------------------------------

def _seated(env, client, code="BACK42", status="playing"):
    """A room with this client sat in it, and a finished race to watch."""
    with client.session_transaction() as s:
        s["session_key"] = "sk-watcher"
    with env.app.app_context():
        game = env.DriveGame(code=code, track="sunrise", status=status)
        env.db.session.add(game)
        env.db.session.commit()
        env.db.session.add(env.DrivePlayer(
            game_id=game.id, session_key="sk-watcher", name="dave",
            color="#fff", seat_order=0))
        race = env.DriveRace(code=code, track="sunrise", cars_json="[]")
        env.db.session.add(race)
        env.db.session.commit()
        return race.id


def test_the_way_out_of_a_replay_is_back_into_the_room(env):
    """A race is watched from the room that drove it, so the way out of the
    replay should be the way back in. It used to be a one-way trip to the lobby
    list, which meant watching your own race cost you the room you were racing
    in - and you were never actually out of it: leaving for the replay is a soft
    disconnect and the seat stays in the database.
    """
    c = env.app.test_client()
    rid = _seated(env, c)
    html = c.get("/race/%d" % rid).get_data(as_text=True)
    assert '"BACK42"' in html, "the room code has to reach the page"
    assert "Back to room" in html and ">Leave<" not in html
    assert 'href="/room/BACK42"' in html


def test_a_replay_opened_by_nobody_in_particular_still_leads_to_the_lobbies(env):
    """The other half of the same rule. A replay link outlives the room it was
    driven in and can be opened by somebody who was never in it, so "back to the
    room" has to be a thing the page only says when there is one."""
    c = env.app.test_client()
    with env.app.app_context():
        race = env.DriveRace(code="GONE", track="sunrise", cars_json="[]")
        env.db.session.add(race)
        env.db.session.commit()
        rid = race.id
    html = c.get("/race/%d" % rid).get_data(as_text=True)
    assert "backRoom: null" in html
    assert "Back to room" not in html and "/room/GONE" not in html


def test_an_ended_room_is_not_somewhere_to_go_back_to(env):
    """`_seated_room` goes through `_my_players`, which skips ended games. A row
    can outlive the race it was in by a sweep interval, and sending somebody back
    to that is a redirect straight out again."""
    c = env.app.test_client()
    rid = _seated(env, c, code="DEAD01", status="ended")
    html = c.get("/race/%d" % rid).get_data(as_text=True)
    assert "backRoom: null" in html and "Back to room" not in html


def test_going_off_to_watch_a_replay_does_not_give_up_the_seat(env):
    """The claim the whole feature rests on. Closing the room's page is a socket
    disconnect, and the *soft* kind: the car comes off the road and the seat stays
    behind. If it did not, the way out of a replay would send everybody to a room
    that bounced them straight back to the lobby list.

    Driven through `_drop` rather than a socket, like the rest of the room's
    bookkeeping - and only the soft half, because the hard one reads the session
    off a request that a disconnect does not have.
    """
    A = env
    c = A.app.test_client()
    _seated(A, c, code="SOFT01")
    with A.app.app_context():
        game = A.DriveGame.query.filter_by(code="SOFT01").first()
        pid = game.players[0].pid
        r = A._room("SOFT01")
        A._car(r, pid)["ts"] = A._now_ms()
        A._sid_room["sid-watcher"] = ("SOFT01", pid)
        A._drop("sid-watcher", hard=False)
        assert pid not in r["cars"], "the car leaves the road"
        assert A.DriveGame.query.filter_by(code="SOFT01").first().players, \
            "the seat does not leave the room"
        assert A._seated_room("sk-watcher") == "SOFT01"


# ---------------------------------------------------------------------------
# /api/activity - the driving that never reached the board
# ---------------------------------------------------------------------------
#
# `drive_time` and `distance` were written only by `/api/run`, which is posted when a
# lap *finishes*. Measured on the live database that meant 8,134 of 9,758 attempts
# (83%) counted for nothing, and every room lap counted for nothing at all, because
# `countsForTheBoard()` gates the board APIs.


def _stats_row(A, uid):
    with A.app.app_context():
        st = A.DriveStats.query.filter_by(user_id=uid).first()
        if st is None:
            return None
        return {c.name: getattr(st, c.name) for c in st.__table__.columns}


def test_activity_adds_driving_and_touches_nothing_else(env):
    """The counters it is allowed to move, and - the important half - the ones it is
    not. `runs` means laps *finished*, so an abandoned run must not touch it, and
    nothing here may reach a medal, a rating or the board."""
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    # One post to bring the row into being (`/api/start` writes `DriveStart`, a
    # different table, so it leaves no stats row behind), then measure the census
    # across a second - which is the case that matters: an existing row, and only
    # the two counters on it allowed to move.
    c.post("/api/activity", json={"track": "sunrise", "ms": 1000, "distance": 10})
    before = _stats_row(A, uid)
    assert before is not None
    r = c.post("/api/activity", json={"track": "sunrise", "ms": 12_000,
                                      "distance": 400, "why": "restart"})
    assert r.get_json() == {"ok": True, "stored": True}
    after = _stats_row(A, uid)
    assert after["drive_time"] == pytest.approx((before["drive_time"] or 0) + 12.0)
    assert after["distance"] == pytest.approx((before["distance"] or 0) + 400)
    # Census, not field by field: a counter added later cannot quietly start moving.
    moved = {k for k in after if after[k] != before[k]}
    assert moved == {"drive_time", "distance"}, moved
    with A.app.app_context():
        assert A.DriveTime.query.count() == 0, "an abandoned run is not a board entry"


def test_activity_does_not_count_a_finished_lap_twice(env):
    """**The test this feature lives or dies by.**

    `/api/run` adds a finished lap's own time and distance. If an abandon path also
    reported it, every lap would be worth double - so the client claims the run
    (`run.counted`) the moment `/api/run` takes it, and `reportActivity` refuses a
    run it has already banked. Here that contract is checked from the server's side:
    the two routes are additive, so posting both for one lap *is* the double count,
    and the client is the only thing that stops it.

    The wiring that enforces it is pinned in `test_rules_js.py`; this test exists so
    the arithmetic is written down next to the route that does it.
    """
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    payload = _run_payload(A)
    assert c.post("/api/run", json=payload).get_json()["stored"] is True
    once = _stats_row(A, uid)
    assert once["drive_time"] == pytest.approx(payload["time_ms"] / 1000.0)
    # What a buggy client would do. It has to be visible, or nobody would know the
    # client-side guard is the only thing standing here.
    c.post("/api/activity", json={"track": payload["track"],
                                  "ms": payload["time_ms"], "distance": 500})
    twice = _stats_row(A, uid)
    assert twice["drive_time"] == pytest.approx(once["drive_time"] * 2), \
        "the routes are additive by design; the client must post exactly one of them"


def test_activity_clamps_both_numbers(env):
    """Both are the client's word. `distance` had a clamp already because it always
    was; `ms` never needed one on `/api/run` (the replay's frame count checks it) and
    badly needs one here, where there is no replay - it is the number the whole
    minutes-played figure is made of."""
    A = env
    import runcheck
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    c.post("/api/activity", json={"track": "sunrise", "ms": 10 ** 9,
                                  "distance": 10 ** 9})
    st = _stats_row(A, uid)
    assert st["drive_time"] == pytest.approx(runcheck.MAX_RUN_MS / 1000.0)
    assert st["distance"] < 10 ** 9
    # Rubbish is nought rather than an exception or a NaN in somebody's profile.
    c.post("/api/activity", json={"track": "sunrise", "ms": "banana",
                                  "distance": None})
    st2 = _stats_row(A, uid)
    assert st2["drive_time"] == pytest.approx(st["drive_time"])


def test_activity_is_honest_to_a_guest(env):
    """The rule `/api/start` already follows: there is no row to count it in and
    nothing has gone wrong, so it is a `false` and not a 401."""
    A = env
    c = A.app.test_client()
    r = c.post("/api/activity", json={"track": "sunrise", "ms": 5000, "distance": 90})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "stored": False}
    with A.app.app_context():
        assert A.DriveStats.query.count() == 0


def test_activity_accepts_a_beacon(env):
    """`navigator.sendBeacon` sends `text/plain`, so a route reading `request.json`
    sees nothing and drops it silently - which would undo the one case this feature
    is mostly for, the run abandoned by closing the tab."""
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    r = c.post("/api/activity", data=json_mod.dumps({"track": "sunrise", "ms": 3000,
                                                     "distance": 50}),
               content_type="text/plain;charset=UTF-8")
    assert r.get_json() == {"ok": True, "stored": True}
    assert _stats_row(A, uid)["drive_time"] == pytest.approx(3.0)


def test_activity_refuses_a_track_that_does_not_exist(env):
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    assert c.post("/api/activity", json={"track": "nope", "ms": 1000}).status_code == 404


# ---------------------------------------------------------------------------
# Embedding somebody's name in a <script> block
# ---------------------------------------------------------------------------

def test_a_name_cannot_end_the_script_tag_it_is_drawn_in(env):
    """The XSS that was live: a thirty-character display name.

    `</script><svg onload=alert(1)>` is exactly the length a display name was
    allowed to be, `json.dumps` does not escape `<`, and every roster is
    embedded in a `<script>` block - so the tag ended early and the rest was
    parsed as HTML, for every other player in the lobby.
    """
    import app as A
    payload = A.script_json([{"name": "</script><svg onload=alert(1)>"}])
    assert "</script>" not in payload
    assert "\\u003c/script\\u003e" in payload


def test_script_json_escapes_everything_that_can_break_out():
    """`<`, `>`, `&`, and the two JS line terminators that are legal in JSON."""
    import app as A
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                    ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        out = A.script_json({"n": "a%sb" % ch})
        assert esc in out, ch
        assert ch not in out, ch


def test_script_json_stays_compact():
    """Why this is not Jinja's `|tojson`: the track payload is the whole ribbon.

    `|tojson` cannot be told to use compact separators - only
    `JSONProvider.response` honours `compact` - and `", "` instead of `","` is
    +17% on a track payload, which is 12KB a page load on Sandy Cove.
    """
    import app as A
    assert A.script_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'


def test_a_guest_cannot_be_called_something_that_breaks_the_page(env):
    """The one name on the site that took no validation at all."""
    c = env.app.test_client()
    for bad in ("</script>x", "a<b", "\u202eevil"):
        d = c.post("/guest", json={"name": bad}).get_json()
        assert not d["ok"], bad
    assert c.post("/guest", json={"name": "Dave"}).get_json()["ok"]


# ---------------------------------------------------------------------------
# Claiming a race result
# ---------------------------------------------------------------------------

def _room(A, code, track):
    """A room row, which is where `_finish_is_possible` reads the track from."""
    g = A.DriveGame(code=code, track=track, status="waiting")
    A.db.session.add(g)
    A.db.session.commit()
    return g


def test_a_finish_cannot_be_quicker_than_the_car_goes(env):
    """`emit('finish', {ms: 1})` used to win any race outright.

    The floor is the ribbon's own length over the physics' hard velocity clamp,
    so it is a statement about the simulation and not about anybody's driving -
    it cannot punish somebody for being quick the way a floor under `ideal`
    would. On Sunrise it is about 9.8s against a real lap of roughly 16.
    """
    import app as A
    import laptime
    import tracks as tracks_mod
    import tuning

    track = tracks_mod.get("sunrise")
    length = laptime.line_length(track)
    floor_ms = length / (tuning.MAX_SPEED * 1.7) * 1000.0

    with A.app.app_context():
        _room(A, "ZZZZZZ", "sunrise")
        r = {"code": "ZZZZZZ", "t0": A._now_ms() - 20000}
        car = {"prog": length}

        def possible(ms):
            return A._finish_is_possible(r, car, ms)

        assert not possible(1), "a one-millisecond lap is not a lap"
        assert not possible(int(floor_ms) - 500)
        assert possible(int(floor_ms) + 500)
        assert possible(16000), "a real Sunrise lap has to be accepted"


def test_a_finish_cannot_take_longer_than_the_race_has_run(env):
    import app as A
    with A.app.app_context():
        _room(A, "ZZZZZZ", "sunrise")
        r = {"code": "ZZZZZZ", "t0": A._now_ms() - 12000}
        assert not A._finish_is_possible(r, {"prog": 10_000.0}, 30000)


def test_a_finish_needs_the_car_to_have_gone_round(env):
    """`prog` is the car's own progress along the ribbon."""
    import app as A
    with A.app.app_context():
        _room(A, "ZZZZZZ", "sunrise")
        r = {"code": "ZZZZZZ", "t0": A._now_ms() - 20000}
        assert not A._finish_is_possible(r, {"prog": 5.0}, 16000)


def test_an_unknown_track_skips_the_track_checks_rather_than_failing_them(env):
    """Refusing a finish nobody can prove is wrong costs a race somebody drove."""
    import app as A
    with A.app.app_context():
        r = {"code": "NOSUCH", "t0": A._now_ms() - 20000}
        assert A._finish_is_possible(r, {"prog": 0.0}, 16000)
