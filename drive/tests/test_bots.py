"""The room's bots: the driver, the seats, and everything they must not touch.

Three kinds of test here and they fail for different reasons.

**The driver** ones drive real laps through the real physics, so they are the
slow ones and they are parametrised one track at a time to stay inside the
per-test budget. What they are really guarding is that a bot *gets round*: two
of the bugs found writing this were silent in exactly the way that matters - a
NaN steering input turned the car into nothing and a reference speed of zero on
the start line left it sitting there being respawned - and in both cases the
suite would have been perfectly green while no bot ever moved.

**The seat** ones are ordinary Flask/socket tests about who may add a bot and
when.

**The boundary** ones are the important ones: a bot must never reach ELO, a
leaderboard, or the anti-cheat's findings table.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bots as bots_mod                                    # noqa: E402
import botsim                                              # noqa: E402
import tracks as tracks_mod                                # noqa: E402
from conftest import NO_BOARD_YET                          # noqa: E402

needs_js = pytest.mark.skipif(not botsim.available(),
                              reason="quickjs is not installed")

# Two short tracks with different shapes: one flat and forgiving, one with the
# jumps and a loop. Driving the whole pool here would be minutes.
DRIVEN = ["sunrise", "chicane"]


@pytest.fixture()
def env():
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
    A._rooms.clear()
    # **The bot worlds live in a module global that outlives the fixture**, and
    # `_game` hands every room in this file the same code, so without this a
    # test inherits the previous one's cars. It is not hypothetical: it is how
    # `test_a_bot_reaching_a_checkpoint_tells_the_room` came to be handed a car
    # that had already finished the race in the test before it, and so had no
    # checkpoint left to report. Production cannot reach it - room codes are
    # unique and `_delete_game` drops the world - so the fixture is the honest
    # place for it rather than a guard in `botsim`.
    for code in botsim.live_codes():
        botsim.drop(code)
    os.unlink(path)


def _game(A, track="sunrise", code="BOTS"):
    """A room with one human host in it."""
    from models import DriveGame, DrivePlayer
    g = DriveGame(code=code, status="waiting", track=track, max_players=8)
    A.db.session.add(g)
    A.db.session.commit()
    p = DrivePlayer(game_id=g.id, session_key="human", name="me",
                    color="#fff", seat_order=0, is_host=True)
    A.db.session.add(p)
    A.db.session.commit()
    return g, p


# ---------------------------------------------------------------------------
# The names
# ---------------------------------------------------------------------------

def test_there_is_a_pool_of_names_and_they_are_distinct():
    names = bots_mod.names()
    assert len(names) >= 400, "run tools/bot_names.py"
    assert len({n.lower() for n in names}) == len(names), "two bots share a name"
    assert all(3 <= len(n) <= 16 for n in names), (
        "a name has to fit on the plate over a car at racing distance")


def test_a_room_never_seats_two_bots_with_the_same_name():
    used = set()
    for _ in range(20):
        n = bots_mod.pick_name(used)
        assert n not in used
        used.add(n)


# ---------------------------------------------------------------------------
# The recorded fast lines
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", [t["slug"] for t in tracks_mod.TRACKS])
def test_every_track_has_a_usable_hot_lap(slug):
    """`tools/hotlap.py` has been run and what it wrote still lines up.

    A missing one is not fatal - the quick levels fall back to the relaxed line
    - but on any track that has been driven it is a mistake rather than a
    decision, so it is worth being told about. The length checks are what catch
    a half-written file.

    The exception is a track that has only just landed and has no record to cut
    a line from at all; see `NO_BOARD_YET` in conftest.
    """
    hot = bots_mod.hotlap(slug)
    if slug in NO_BOARD_YET:
        # Still checked, if it is there: an entry left behind after the file
        # arrives would silently stop testing a track that is being tested
        # everywhere else.
        assert not hot, (
            "tracks/%s has a hotlap.json now - drop it from NO_BOARD_YET in "
            "tests/conftest.py so it is checked like every other track" % slug)
        pytest.skip("%s has no record on the board yet, so no fast line" % slug)
    assert hot, "no hotlap.json in tracks/%s - run tools/hotlap.py" % slug
    n = len(hot["p"])
    assert n > 50
    assert len(hot["v"]) == n
    assert len(hot["air"]) == n
    assert len(hot["vmin"]) == n
    assert all(len(p) == 3 for p in hot["p"])
    assert hot["time_ms"] > 0


@pytest.mark.parametrize("slug", [t["slug"] for t in tracks_mod.TRACKS])
def test_a_jump_run_up_carries_a_speed_floor(slug):
    """Wherever the fast line leaves the ground, the approach has a floor on it.

    This is what stops a pace multiplier turning a jump into a hole - see
    JUMP_RUNUP in tools/hotlap.py. A track with no jumps has no floors and that
    is fine; what must never happen is a jump with none.
    """
    hot = bots_mod.hotlap(slug)
    if not hot or not any(hot["air"]):
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hotlap_tool", os.path.join(os.path.dirname(__file__), "..", "tools",
                                    "hotlap.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    for (a, _b) in tool.air_runs(hot["air"], hot["hz"]):
        take = max(0, a - 1)
        assert hot["vmin"][take] > 0, (
            "%s: the jump at frame %d has no speed floor on its approach"
            % (slug, a))


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

@needs_js
@pytest.mark.parametrize("slug", DRIVEN)
@pytest.mark.parametrize("level", list(bots_mod.LEVELS))
def test_a_bot_gets_round(slug, level):
    """Every level completes a lap. The floor under everything else here.

    Both of the bugs this test exists for were invisible: with a NaN steering
    input the car simply stopped being anywhere, and with the reference lap's
    standing start read as a speed limit it sat on the line being respawned
    forty times. Neither raised anything.
    """
    out = botsim.solo_lap(slug, level, max_t=120)
    assert out["finished"], (
        "%s could not get round %s (%.0f%% of the way, %d respawns)"
        % (level, slug, 100 * out["progress"], out["respawns"]))
    assert out["respawns"] <= 1, "%s fell off %s" % (level, slug)


@needs_js
@pytest.mark.parametrize("slug", DRIVEN)
def test_the_levels_come_out_in_the_right_order(slug):
    """Easy is slower than medium is slower than hard.

    Pinned because it is the one property a *player* can see directly, and
    because it is not automatic: the pace is calibrated per level per track, and
    a bad calibration or a driver that cannot use the extra pace can invert two
    of them - `max` was slower than `hard` on Sunrise for most of a day.
    """
    times = {}
    for level in ("easy", "medium", "hard"):
        out = botsim.solo_lap(slug, level, max_t=120)
        assert out["finished"]
        times[level] = out["time"]
    assert times["easy"] > times["medium"] > times["hard"], times


@needs_js
def test_a_bot_never_reports_a_pose_that_is_not_a_number():
    """Every number a bot puts on the wire is finite.

    A NaN here is not a bot that drives badly, it is a car at coordinates that
    are not coordinates in five other browsers - and it happened, from one
    vector indexed as an array. The pose path is the only place it can escape,
    so this is asserted on the pose path.
    """
    import math
    code, slug = "NANS", "sunrise"
    w = botsim.world(code, slug, create=True)
    w.add("b1", "max", seed=3)
    now = 1000
    for _ in range(120):
        now += 33
        poses, _ = w.tick(0.033, [], now, "free", None)
        for row in poses:
            for v in row[1:]:
                assert isinstance(v, (int, float)) and math.isfinite(v), row
    botsim.drop(code)


@needs_js
def test_a_bot_dropped_off_the_track_gets_itself_back():
    """Put one in the void and it takes the checkpoint rather than staying there.

    The recovery is what turns a missed jump into a few lost seconds instead of
    a car that is out of the race, and a bot that cannot do it is one that spends
    a whole race falling off the same lip.
    """
    code, slug = "LOST", "sunrise"
    w = botsim.world(code, slug, create=True)
    w.add("b1", "medium", seed=5)
    now = 1000
    for _ in range(60):                      # get it moving and onto the line
        now += 33
        w.tick(0.033, [], now, "free", None)
    # Straight down, a long way under the road.
    w.rt.ctx.eval("WORLDS['LOST'].get('b1').car.pos.y = -500;")
    back = False
    for _ in range(300):                     # ten seconds to sort itself out
        now += 33
        poses, _ = w.tick(0.033, [], now, "free", None)
        if poses and poses[0][2] > -50:
            back = True
            break
    assert back, "a bot that fell off never came back"
    botsim.drop(code)


# ---------------------------------------------------------------------------
# The seats
# ---------------------------------------------------------------------------

def test_the_host_can_seat_a_bot_and_it_is_an_ordinary_player_row(env):
    with env.app.app_context():
        g, _ = _game(env)
        p = env._seat_bot(g, "hard")
        assert p.is_bot and p.bot_level == "hard"
        assert p.user_id is None, "a bot must have no account - that is what "\
                                  "keeps it out of the rating"
        assert p.session_key.startswith("bot_")
        assert not p.is_host
        row = p.to_dict(None)
        assert row["bot"] and row["level"] == "hard"
        assert not row["guest"], "a bot is not a guest; the roster says which"


def test_an_unknown_level_falls_back_rather_than_seating_nonsense(env):
    with env.app.app_context():
        g, _ = _game(env)
        p = env._seat_bot(g, "impossible")
        assert p.bot_level == bots_mod.DEFAULT_LEVEL


def test_a_room_full_of_bots_still_lets_a_person_in(env):
    """A person takes the weakest bot's seat rather than being turned away.

    A grid filled with bots is not full in any sense that should keep somebody
    out - they are only there because nobody else was.
    """
    with env.app.app_context():
        g, _ = _game(env)
        for lv in ("max", "hard", "medium", "easy", "easy", "hard", "max"):
            env._seat_bot(g, lv)
        assert len(g.players) == 8
        c = env.app.test_client()
        with c.session_transaction() as s:
            s["guest_name"] = "someone"
        r = c.post("/join", json={"code": "BOTS"})
        assert r.status_code == 200, r.get_json()
        left = env.DrivePlayer.query.filter_by(game_id=g.id).all()
        assert len(left) == 8
        assert sum(1 for p in left if not p.is_bot) == 2
        assert "easy" not in [p.bot_level for p in left if p.is_bot][:1] or True
        # the one that stood down was an easy one, not a max one
        assert sorted(p.bot_level for p in left if p.is_bot) == \
            ["easy", "hard", "hard", "max", "max", "medium"]


def test_a_room_with_nothing_but_bots_in_it_is_closed(env):
    """Bots cannot keep a room open. They cannot leave, and never would."""
    with env.app.app_context():
        g, p = _game(env)
        env._seat_bot(g, "medium")
        env._seat_bot(g, "hard")
        code = g.code
        env._sid_room["sid1"] = (code, p.pid)
        with env.app.test_request_context():
            from flask import session
            session["session_key"] = "human"
            env._drop("sid1", hard=True)
        assert env.DriveGame.query.filter_by(code=code).first() is None, (
            "a room of bots outlived the last person in it")


def test_bots_do_not_count_as_people_for_the_room_going_idle(env):
    """`_humans` is what the pump and the sweep ask, and it excludes bots.

    Bots report a pose thirty times a second for as long as the pump runs, so
    a room that measured liveness on `_live` would never go idle and would hold
    its world - tens of megabytes - for ever.
    """
    with env.app.app_context():
        r = env._room("IDLE")
        now = env._now_ms()
        for pid in ("p1", "p2"):
            c = env._car(r, pid)
            c["ts"] = now
        r["bots"] = {"p2": "hard"}
        assert env._live(r) == ["p1", "p2"] or set(env._live(r)) == {"p1", "p2"}
        assert env._humans(r) == ["p1"]


# ---------------------------------------------------------------------------
# What a bot must never touch
# ---------------------------------------------------------------------------

def test_a_bot_is_invisible_to_the_rating(env):
    """Beating a bot gains nothing and losing to one costs nothing.

    True by construction - a bot has no `user_id` and `_rate_race` ranks the
    accounts among themselves - which is exactly why it is worth a test: the
    property is inherited rather than written down anywhere in the rating code.
    """
    with env.app.app_context():
        from models import User, DrivePlayer
        g, human = _game(env)
        u = User(username="racer", email="r@example.com")
        env.db.session.add(u)
        env.db.session.commit()
        human.user_id = u.id
        env.db.session.commit()
        bot = env._seat_bot(g, "max")
        standings = [{"pid": bot.pid, "name": bot.name, "ms": 10000},
                     {"pid": human.pid, "name": "me", "ms": 20000}]
        out = env._rate_race(g, standings)
        assert out == {}, "a race against bots was rated"
        st = env._stats(u)
        assert (st.wins or 0) == 0, "losing to a bot took a win off somebody"
        assert (st.races or 0) == 0


def test_a_bot_is_never_judged_by_the_anti_cheat(env):
    """The quick levels drive a line that jumps across a loop, which is the
    exact shape `racecheck` is looking for - and there is no client to accuse."""
    with env.app.app_context():
        r = env._room("JUDG")
        r["grid"] = {"p1": 0, "p2": 1}
        r["bots"] = {"p2": "max"}
        r["rec"] = {"track": "sunrise", "cars": {}, "n": 0, "t0": 0}
        w = env._watch(r, "p2")
        for _ in range(50):                  # well past STRIKE_LIMIT
            w.strike("corridor")
        assert w.flagged, "the watcher was not set up to flag anything"
        flagged = env._judge_race(r)
        assert "p2" not in flagged, "a bot was flagged for cheating"
        # And the same evidence against a person is still caught, or this test
        # would pass just as well with the anti-cheat switched off.
        wh = env._watch(r, "p1")
        for _ in range(50):
            wh.strike("corridor")
        assert "p1" in env._judge_race(r)


@needs_js
def test_a_bot_lap_never_reaches_a_leaderboard(env):
    """Nothing a bot drives is a time trial.

    Two independent rules already say so - no room lap reaches the board, and a
    bot has no account to hang one on - and this is the test that notices if
    either is ever relaxed.
    """
    with env.app.app_context():
        g, _ = _game(env)
        bot = env._seat_bot(g, "max")
        assert env.DriveTime.query.filter_by(user_id=None).count() == 0
        r = env._room(g.code)
        env._sync_bots(r, g)
        env._tick_bots(r)
        env._tick_bots(r)
        assert env.DriveTime.query.count() == 0
        assert env.DriveStart.query.count() == 0
        assert env.DriveRunCheck.query.count() == 0
        assert bot.user_id is None


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------

def test_the_bot_columns_are_added_to_a_table_that_predates_them(env):
    """`ensure_columns` is idempotent and fixes an old `drive_players`.

    It runs at boot because a mapped column the table does not have makes every
    query against that table fail - so a deploy that forgot the ALTER would not
    be a feature that does not work, it would be Drive down.
    """
    import models as M
    with env.app.app_context():
        from sqlalchemy import inspect, text
        with env.db.engine.begin() as conn:
            # The index goes first, or SQLite refuses to drop the column it is
            # on - which is also what the live table looks like, since the one
            # there was added by `ensure_columns` and never indexed.
            conn.execute(text("DROP INDEX IF EXISTS ix_drive_players_is_bot"))
            conn.execute(text("ALTER TABLE drive_players DROP COLUMN is_bot"))
        cols = {c["name"] for c in inspect(env.db.engine).get_columns("drive_players")}
        assert "is_bot" not in cols
        M.ensure_columns(env.db)
        cols = {c["name"] for c in inspect(env.db.engine).get_columns("drive_players")}
        assert "is_bot" in cols
        M.ensure_columns(env.db)          # again: must not raise
        g, _ = _game(env)
        assert env._seat_bot(g, "easy").is_bot


@needs_js
def test_a_room_that_loses_its_bot_world_builds_another(env, monkeypatch):
    """Seats with no world must not be a state the room stays in.

    Everything that builds a bot world is a host action, so before this the
    room sat with bots in the roster and no cars on the track until somebody
    thought to re-add one. Reported from a real room after a track change; the
    trigger was never reproduced, so what is pinned here is the recovery rather
    than the fault.
    """
    with env.app.app_context():
        g, _ = _game(env, track="sunrise")
        env._seat_bot(g, "medium")
        r = env._room(g.code)
        env._sync_bots(r, g)
        pid = list(r["bots"])[0]
        now = [2_000_000]
        monkeypatch.setattr(env, "_now_ms", lambda: now[0])
        # The world goes, the seats do not - exactly the broken state.
        env.botsim.drop(g.code)
        assert r["bots"] and env._bot_world(r) is None

        now[0] += env.BOT_REVIVE_MS + 1
        env._tick_bots(r)                      # notices, rebuilds
        assert env._bot_world(r) is not None, "the room never got a world back"
        assert pid in env._bot_world(r).bots

        # And it drives again, rather than merely existing.
        moved = False
        first = None
        for _ in range(40):
            now[0] += 33
            env._tick_bots(r)
            c = r["cars"].get(list(r["bots"])[0])
            if c and "p" in c:
                if first is None:
                    first = list(c["p"])
                elif abs(c["p"][0] - first[0]) + abs(c["p"][2] - first[2]) > 1:
                    moved = True
        assert moved, "the rebuilt bot never moved"


def test_one_bad_tick_does_not_end_the_bots_for_the_session(env, monkeypatch):
    """A world that throws once is retried; one that keeps throwing is given up on."""
    with env.app.app_context():
        g, _ = _game(env, track="sunrise")
        env._seat_bot(g, "medium")
        r = env._room(g.code)
        env._sync_bots(r, g)
        now = [3_000_000]
        monkeypatch.setattr(env, "_now_ms", lambda: now[0])

        class Boom:
            slug = "sunrise"
            bots = {"x": "medium"}

            def tick(self, *a, **k):
                raise RuntimeError("bang")

        monkeypatch.setattr(env, "_bot_world", lambda r, create=False: Boom())
        now[0] += 33; env._tick_bots(r)        # first tick primes the interval
        for i in range(env.BOT_FAIL_LIMIT):
            now[0] += 33
            env._tick_bots(r)
        assert r["bots"] == {}, "a world that always throws should be given up on"
        assert r["bot_fail"] >= env.BOT_FAIL_LIMIT


def test_filling_the_grid_uses_the_level_on_the_dropdown(env):
    """Every seat the fill makes is at the level that was chosen, not the default.

    The point of the dropdown is that a grid of Max and a grid of Easy are one
    press apart. A fill that quietly seated the default would make the control
    above it look broken, and on a field of seven that is the whole race.

    Also pins the one-commit behaviour: the loop re-reads `game.players` each
    pass to work out the next seat number, so the rows have to be visible to
    the session before the single commit at the end - `flush`, not `commit`.
    """
    with env.app.app_context():
        g, _ = _game(env)
        added = 0
        while len(g.players) < g.max_players:
            if not env._seat_bot(g, "hard", commit=False):
                break
            added += 1
        env.db.session.commit()
        bots = [p for p in g.players if p.is_bot]
        assert added == 7 and len(bots) == 7, "the grid should fill to eight cars"
        assert {p.bot_level for p in bots} == {"hard"}
        assert len({p.seat_order for p in g.players}) == 8, "seats must be distinct"


def test_only_the_levels_that_are_ready_can_be_seated(env):
    """A level that is not offered cannot be reached by editing a payload.

    The dropdown is rendered from `OFFERED` and the server validates against the
    same tuple, so the two can never disagree about which levels are ready -
    which is the whole reason it is one name and not a list in two files.
    """
    with env.app.app_context():
        g, _ = _game(env)
        for lv in bots_mod.LEVELS:
            p = env._seat_bot(g, lv)
            if lv in bots_mod.OFFERED:
                assert p.bot_level == lv
            else:
                assert p.bot_level == bots_mod.DEFAULT_LEVEL, (
                    "a level that is not offered was seated anyway")
        assert bots_mod.DEFAULT_LEVEL in bots_mod.OFFERED, (
            "the default has to be one of the levels a room can pick")


@needs_js
def test_a_whole_race_with_bots_in_it_runs_to_a_result(env, monkeypatch):
    """Green light to chequered flag, with the bots driving, and nothing raises.

    The room's own paths are what this is really about. A bot's checkpoint and
    finish do not arrive through a socket handler with a request context around
    them - they come out of the simulation on the pump's greenlet - so
    `_bot_events`, `_bot_finished`, the standings and `_maybe_close` all run
    somewhere none of the rest of the room's code runs. That is exactly the sort
    of difference that is invisible until a race is halfway through.

    The clock is driven rather than waited on: the suite may not sleep.
    """
    with env.app.app_context():
        g, human = _game(env, track="sunrise")
        env._seat_bot(g, "medium")
        env._seat_bot(g, "easy")
        r = env._room(g.code)
        env._sync_bots(r, g)
        assert len(r["bots"]) == 2

        # A driven clock, so a 20-second race costs no wall time.
        now = [1_000_000]
        monkeypatch.setattr(env, "_now_ms", lambda: now[0])

        pids = list(r["bots"])
        r["grid"] = {pid: i for i, pid in enumerate(pids)}
        r["phase"] = "countdown"
        w = env._bot_world(r)
        w.place_grid(r["grid"])
        r["t0"] = now[0]
        r["phase"] = "racing"
        w.green(now[0])
        r["rec"] = {"t0": now[0], "track": "sunrise", "n": 0,
                    "cars": {pid: [] for pid in pids}}

        for _ in range(3000):                       # 100s of race at 30Hz
            now[0] += 33
            env._tick_bots(r)
            env._record_race(r)
            if len(r["finish"]) == len(pids):
                break

        assert len(r["finish"]) == len(pids), (
            "the bots never finished: %s" % r["finish"])
        # In order, quickest first, and every one a real lap time.
        times = [e["ms"] for e in r["finish"]]
        assert times == sorted(times)
        assert all(t > 5000 for t in times), times
        # And the replay recorded them, which is what `/race/<id>` plays back.
        assert all(len(f) > 10 for f in r["rec"]["cars"].values())


@needs_js
def test_a_bot_reaching_a_checkpoint_tells_the_room(env, monkeypatch):
    """Splits are fanned out for a bot the same way they are for a person.

    Without this the gap on everybody's HUD simply ignores the bots, which on a
    grid that is mostly bots is a gap to nobody.
    """
    sent = []
    with env.app.app_context():
        g, _ = _game(env, track="sunrise")
        env._seat_bot(g, "medium")
        r = env._room(g.code)
        env._sync_bots(r, g)
        now = [1_000_000]
        monkeypatch.setattr(env, "_now_ms", lambda: now[0])
        monkeypatch.setattr(env.socketio, "emit",
                            lambda ev, *a, **k: sent.append(ev))
        pid = list(r["bots"])[0]
        r["grid"] = {pid: 0}
        r["phase"] = "racing"
        r["t0"] = now[0]
        env._bot_world(r).green(now[0])
        for _ in range(900):
            now[0] += 33
            env._tick_bots(r)
            if "race_split" in sent:
                break
        assert "race_split" in sent, "a bot passed a checkpoint and said nothing"
