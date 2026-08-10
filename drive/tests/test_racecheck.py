"""The room's anti-cheat: is this car doing something the car can do?

Two halves, and they fail in opposite directions, which is what most of this
file is about.

The **live** half runs on every pose, thirty times a second per car, while
somebody is mid-corner. Its expensive mistake is a false positive, so the tests
that matter most here are the ones that feed it an *honest* car through the
nastiest conditions a network produces - jitter, coalesced arrivals, a
reconnect, a respawn - and require it to say nothing at all.

The **post-race** half runs once, at the flag, over the trace the server
recorded itself. It has no jitter in it and no deadline, so it can afford the
questions the live half cannot ask, and its tests are about those.

The thing neither half can do is worth restating, because a test file is where
somebody will come looking for it: this does not decide that a *person* drove
the car, and it cannot see a slightly richer engine. That is `verify.py`, it
needs the input stream, and a race does not carry one. See `racecheck`'s
preamble for why a room is not the place for it.
"""

import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import racecheck
import runcheck
import tracks as tracks_mod
import tuning


TRACK = tracks_mod.get("sunrise")


# ---------------------------------------------------------------------------
# Walking a car round honestly, which most of these tests need
# ---------------------------------------------------------------------------

def _walk(track, speed, hz, n=None, start=0.0):
    """Poses along the ribbon at `speed`, `hz` of them a second.

    The racing line is the one path through a track that is certainly legal, so
    an honest car for testing purposes is one that follows it. Every "this must
    not fire" test below is driven from here.
    """
    line = track["line"]
    arcs = [racecheck.station_arc(track, i) for i in range(len(line))]
    total = arcs[-1]
    step = speed / hz
    out, s, i = [], start, 0
    while s <= total and (n is None or len(out) < n):
        while i + 1 < len(arcs) and arcs[i + 1] < s:
            i += 1
        out.append(list(line[i]["p"]))
        s += step
    return out


def _drive(w, poses, hz=30, track=TRACK, flags=0, t0=0):
    """Feed a walk through the live checks the way `on_pose` does."""
    dt = int(1000 / hz)
    prev, t = None, t0
    for p in poses:
        racecheck.check_pose(w, track, prev, p, dt if prev else 0, flags)
        racecheck.sample_progress(w, track, p, t)
        prev, t = p, t + dt
    return w


# ---------------------------------------------------------------------------
# The live half: it must not accuse anybody
# ---------------------------------------------------------------------------

def test_an_honest_lap_collects_no_strikes():
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED, 30))
    assert w.strikes == 0


def test_arrival_jitter_does_not_accuse_an_honest_car():
    """The reason the budget is a bucket and not a per-step ceiling.

    `dt` is measured when a pose *arrives*, not when it was sent, so two poses
    sent 33ms apart routinely land 5ms apart behind a bit of jitter - and read
    naively that honest pair is a car doing six times the speed limit. Here the
    same honest lap is delivered with the gaps scrambled between 2ms and 70ms,
    averaging the 33 it really was, and nothing may fire: jitter cancels over
    any window longer than the jitter, which is exactly what the bucket is.
    """
    import random
    rng = random.Random(7)
    w = racecheck.Watcher()
    poses = _walk(TRACK, tuning.MAX_SPEED, 30)
    prev, t = None, 0
    for p in poses:
        gap = rng.choice([2, 5, 12, 33, 33, 33, 55, 70])
        racecheck.check_pose(w, TRACK, prev, p, gap if prev else 0, 0)
        racecheck.sample_progress(w, TRACK, p, t)
        prev, t = p, t + gap
    assert w.strikes == 0, w.reasons


def test_a_long_silence_is_a_reconnect_and_not_a_teleport():
    """A rule that fires when somebody's wifi drops is a rule that punishes wifi.

    Past `BUCKET_GAP_S` the server has been redrawing a stale pose for everybody
    for most of a second, so whatever arrives next is a resynchronisation rather
    than a measurement, and the check has no opinion about it.
    """
    w = racecheck.Watcher()
    poses = _walk(TRACK, tuning.MAX_SPEED, 30)
    _drive(w, poses[:30])
    far = poses[-1]
    assert racecheck.check_pose(w, TRACK, poses[29], far,
                                racecheck.BUCKET_GAP_S * 1000 + 500, 0) is None
    assert w.strikes == 0


def test_one_bad_pose_costs_nothing():
    """The whole design is that a single false positive is free.

    A car is only unrated after `STRIKE_LIMIT` of them, and the gap between a
    burst of network noise and a cheat is enormous: a raised speed drains the
    bucket on every pose for as long as it is raised.
    """
    w = racecheck.Watcher()
    racecheck.check_pose(w, TRACK, [0, 0, 0], [900, 0, 0], 33, 0)
    assert w.strikes == 1 and not w.flagged


# ---------------------------------------------------------------------------
# The live half: what it does catch
# ---------------------------------------------------------------------------

def test_a_car_cannot_travel_faster_than_the_car_travels():
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED * 4, 30))
    assert w.flagged, w.reasons


def test_a_banked_budget_cannot_buy_a_jump():
    """The cap on the bucket, which is the other half of it working.

    Without one, a car could sit on the line for ten seconds quietly banking
    allowance and spend all of it on a single hop to the finish. The bucket
    holds `BUCKET_MAX_S` seconds of travel and no more, however long it waits.
    """
    w = racecheck.Watcher()
    p = TRACK["line"][0]["p"]
    for _ in range(300):                     # ten seconds of standing still
        racecheck.check_pose(w, TRACK, p, p, 33, 0)
    assert w.strikes == 0, "standing still is not a crime"
    # Chosen to sit *between* the two answers: an uncapped bucket would have
    # banked ten seconds of travel and waved this through, and the cap holds
    # `BUCKET_MAX_S` of it, which is a couple of car lengths.
    hop = 200.0
    assert racecheck.BUCKET_MAX_S * runcheck.SPEED_CEIL < hop < 10 * runcheck.SPEED_CEIL
    far = [p[0] + hop, p[1], p[2]]
    assert racecheck.check_pose(w, TRACK, p, far, 33, 0)
    assert w.strikes == 1


def test_a_pose_off_the_course_is_noticed():
    w = racecheck.Watcher()
    p = list(TRACK["line"][0]["p"])
    for i in range(80):
        # Straight out sideways at a speed the bucket is perfectly happy with,
        # so the only thing left to object to is where it ends up - which by
        # the end is well past `LIVE_CORRIDOR`.
        p = [p[0], p[1], p[2] + 2.0]
        racecheck.check_pose(w, TRACK, None, p, 33, 0)
        racecheck.sample_progress(w, TRACK, p, i * 250)
    assert any("off the course" in k for k in w.reasons), w.reasons


# ---------------------------------------------------------------------------
# Respawns, which are a real jump and therefore the interesting exception
# ---------------------------------------------------------------------------

def test_a_respawn_goes_back_to_a_gate_the_car_reached():
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED, 30, n=200))
    pts = racecheck.respawn_points(TRACK)
    behind = [pt for pt, arc in pts if arc <= w.prog]
    assert behind, "the walk should have passed at least the grid"
    assert racecheck.check_pose(w, TRACK, [0, 500, 0], behind[-1], 33,
                                racecheck.FLAG_RESPAWN) is None
    assert w.strikes == 0


def test_the_respawn_flag_is_not_a_free_teleport():
    """Setting one bit in a payload the client already writes cannot be the
    whole of a defence, so a respawn has to land where a respawn goes."""
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED, 30, n=200))
    here = TRACK["line"][0]["p"]
    away = [here[0] + 400, here[1] + 400, here[2] + 400]
    assert racecheck.check_pose(w, TRACK, here, away, 33, racecheck.FLAG_RESPAWN)


def test_a_respawn_cannot_skip_forward_to_a_gate_the_car_has_not_reached():
    """The reason this asks `Watcher.prog` rather than the car's own `cp`.

    Read off the client's checkpoint counter, `{cp: 99, flags: RESPAWN}` was a
    legal jump to the last gate on the track - which is the whole lap, for one
    message. Progress is the server's own projection, so reaching a gate to be
    allowed to respawn at it means having driven there.
    """
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED, 30, n=30))
    last, arc = racecheck.respawn_points(TRACK)[-1]
    assert arc > w.prog + racecheck.PROG_LEAD, "pick a gate genuinely ahead"
    assert racecheck.check_pose(w, TRACK, TRACK["line"][0]["p"], last, 33,
                                racecheck.FLAG_RESPAWN)


# ---------------------------------------------------------------------------
# Progress, which is what a finish claim is actually measured against
# ---------------------------------------------------------------------------

def test_progress_is_the_servers_own_measurement():
    w = racecheck.Watcher()
    _drive(w, _walk(TRACK, tuning.MAX_SPEED, 30))
    import laptime
    assert w.prog > 0.9 * laptime.line_length(TRACK)


def test_progress_only_goes_up():
    """A car that rolls backwards over its own line still finished."""
    w = racecheck.Watcher()
    poses = _walk(TRACK, tuning.MAX_SPEED, 30)
    _drive(w, poses)
    peak = w.prog
    _drive(w, list(reversed(poses[:100])), t0=10 ** 6)
    assert w.prog == peak


def test_nonsense_never_becomes_a_pose():
    """JSON has `NaN` and `Infinity` and Python parses both, so `float(x)` is
    not the guard it looks like - and a pose is fanned straight back out to
    five other browsers."""
    assert not racecheck.finite([1.0, float("nan"), 3.0])
    assert not racecheck.finite([1.0, float("inf"), 3.0])
    assert not racecheck.finite([1.0, "2", 3.0])
    assert not racecheck.finite([True, 2.0, 3.0])
    assert racecheck.finite([1, 2.0, -3.5])


# ---------------------------------------------------------------------------
# The post-race half
# ---------------------------------------------------------------------------

def _frames(poses, flags=0):
    return [[p[0], p[1], p[2], 0.0, 0.0, 0.0, 1.0, flags] for p in poses]


def test_an_honest_race_passes_the_scan():
    frames = _frames(_walk(TRACK, tuning.MAX_SPEED * 0.9, runcheck.GHOST_HZ))
    assert racecheck.scan_race(TRACK, frames, runcheck.GHOST_HZ) == []


def test_a_whole_race_spent_over_the_speed_limit_is_caught():
    """The check a per-step ceiling cannot make.

    A single-frame bound is dodged by sitting just underneath it. A race's
    median is not, because nothing in the physics holds a car over
    `MEDIAN_SPEED_CEIL` for half a race - a long descent lifts one over
    `MAX_SPEED` for a few seconds and that is all.
    """
    frames = _frames(_walk(TRACK, runcheck.MEDIAN_SPEED_CEIL * 1.4,
                           runcheck.GHOST_HZ))
    out = racecheck.scan_race(TRACK, frames, runcheck.GHOST_HZ)
    assert any("median" in why for why in out), out


def test_a_race_that_left_the_course_is_caught():
    line = TRACK["line"]
    poses = [[p["p"][0], p["p"][1] + 400, p["p"][2]] for p in line[:60]]
    out = racecheck.scan_race(TRACK, _frames(poses), runcheck.GHOST_HZ)
    assert "left the course" in out


def test_the_scan_skips_respawn_frames():
    """A respawn really is a teleport, and the flag byte is recorded with the
    pose - so here it is cheaper to spot than it is live."""
    poses = _walk(TRACK, tuning.MAX_SPEED * 0.9, runcheck.GHOST_HZ)
    frames = _frames(poses)
    frames[20] = [900.0, 900.0, 900.0, 0.0, 0.0, 0.0, 1.0, racecheck.FLAG_RESPAWN]
    assert racecheck.scan_race(TRACK, frames, runcheck.GHOST_HZ) == []


def test_a_scan_of_nothing_says_nothing():
    """A race everybody left before the first frame is not evidence."""
    assert racecheck.scan_race(TRACK, [], runcheck.GHOST_HZ) == []
    assert racecheck.scan_race(TRACK, None, runcheck.GHOST_HZ) == []


# ---------------------------------------------------------------------------
# The one constant that lives in two languages
# ---------------------------------------------------------------------------

def test_the_flag_bits_match_the_js():
    """`static/js/physics.js` is the source of truth for the flag byte and this
    is a copy of it, because Python cannot read the module and a three-bit
    constant is not worth a build step. So the copy is pinned instead."""
    js = open(os.path.join(os.path.dirname(__file__), "..",
                           "static", "js", "physics.js")).read()
    decl = re.search(r"export const FLAG = \{([^}]*)\}", js).group(1)
    want = dict((k, int(v)) for k, v in re.findall(r"(\w+):\s*(\d+)", decl))
    got = {"DRIFT": racecheck.FLAG_DRIFT, "AIR": racecheck.FLAG_AIR,
           "RESPAWN": racecheck.FLAG_RESPAWN, "BRAKE": racecheck.FLAG_BRAKE,
           "SLIP": racecheck.FLAG_SLIP}
    assert want == got


# ---------------------------------------------------------------------------
# Wired into the room
# ---------------------------------------------------------------------------

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
    os.unlink(path)


def _pose(A, code, pid, sid="s1", **fields):
    A._sid_room[sid] = (code, pid)
    with A.app.test_request_context():
        from flask import request
        request.sid = sid
        A.on_pose(dict({"p": [0.0, 0.0, 0.0], "q": [0, 0, 0, 1], "v": [0, 0, 0],
                        "prog": 0.0, "cp": 0, "flags": 0}, **fields))


def test_an_inflated_prog_no_longer_wins_a_race(env):
    """The hole this was written for.

    `prog` orders the standings and was the only real tooth in
    `_finish_is_possible`, and it arrived unchecked from the same client that
    then claimed the finish. So `emit('pose', {prog: 99999})`, wait out the
    physics floor, `emit('finish')` - and that was a win, its ELO, its win
    tally, its podium and its badge, without the car being driven.
    """
    A = env
    with A.app.app_context():
        A.db.session.add(A.DriveGame(code="ZZZZZZ", track="sunrise",
                                     status="waiting"))
        A.db.session.commit()
        r = A._room("ZZZZZZ")
        r["phase"] = "racing"
        r["t0"] = A._now_ms() - 20000
        A._car(r, "a")
        _pose(A, "ZZZZZZ", "a", p=list(TRACK["line"][0]["p"]), prog=99999.0)
        assert r["cars"]["a"]["prog"] < 999, "the claim is clamped to what was seen"
        assert not A._finish_is_possible(r, r["cars"]["a"], 16000, A._watch(r, "a"))


def test_a_car_the_server_watched_go_round_can_finish(env, monkeypatch):
    """And the other half of it, which matters more: driving the lap works.

    On a clock this test drives itself, because the real one does not move
    between two calls into a handler - every pose would arrive in the same
    millisecond, the bucket would never refill, and an honest lap would collect
    a strike per frame. Which is worth noting as more than a test detail: the
    budget is spent against *arrival* time, so it measures a speed and not a
    message rate.
    """
    A = env
    clock = [A._now_ms()]
    monkeypatch.setattr(A, "_now_ms", lambda: clock[0])
    with A.app.app_context():
        A.db.session.add(A.DriveGame(code="ZZZZZZ", track="sunrise",
                                     status="waiting"))
        A.db.session.commit()
        r = A._room("ZZZZZZ")
        r["phase"] = "racing"
        A._car(r, "a")
        for i, p in enumerate(_walk(TRACK, tuning.MAX_SPEED, 30)):
            clock[0] += 33
            _pose(A, "ZZZZZZ", "a", p=p, prog=float(i))
        r["t0"] = clock[0] - 20000
        assert A._watch(r, "a").strikes == 0, A._watch(r, "a").reasons
        assert A._finish_is_possible(r, r["cars"]["a"], 16000, A._watch(r, "a"))


def test_the_grid_clears_what_qualifying_measured(env):
    """`Watcher.prog` is monotone - it has to be, or a car that rolled backwards
    over its own line would be refused its finish - so a qualifying lap's
    progress would still be sitting there when the lights went out, and the
    first finish claim of the race would be waved through on the strength of a
    lap driven before it."""
    A = env
    with A.app.app_context():
        A.db.session.add(A.DriveGame(code="ZZZZZZ", track="sunrise",
                                     status="waiting"))
        A.db.session.commit()
        r = A._room("ZZZZZZ")
        r["phase"] = "countdown"
        r["t0"] = A._now_ms()
        r["grid"] = {"a": 0}
        A._car(r, "a")
        w = A._watch(r, "a")
        w.prog = 99999.0
        w.strikes = 3
        A._go_green("ZZZZZZ", r["race_seq"])
        assert w.prog == 0.0 and w.strikes == 0


def test_the_grid_move_is_not_charged_to_anybody(env):
    """Every race would otherwise open with strikes for the whole field.

    Being placed in a grid slot is a teleport by every measure in `racecheck`,
    and the client does it partway through the countdown - so the strikes are
    real and they are nobody's fault. `_go_green` clearing the watchers five
    seconds later is what pays for them, which only works because it happens
    *after* the move rather than before it.
    """
    A = env
    with A.app.app_context():
        A.db.session.add(A.DriveGame(code="ZZZZZZ", track="sunrise",
                                     status="waiting"))
        A.db.session.commit()
        r = A._room("ZZZZZZ")
        r["phase"] = "countdown"
        r["t0"] = A._now_ms()
        r["grid"] = {"a": 0}
        A._car(r, "a")
        # Practice at one end of the track, then the countdown puts the car on
        # the grid at the other - which is the jump nobody drove.
        _pose(A, "ZZZZZZ", "a", p=list(TRACK["line"][-1]["p"]))
        _pose(A, "ZZZZZZ", "a", p=list(TRACK["line"][0]["p"]))
        assert A._watch(r, "a").strikes > 0, "the move really is a teleport"
        A._go_green("ZZZZZZ", r["race_seq"])
        assert A._watch(r, "a").strikes == 0


def test_a_flagged_car_is_not_rated_and_is_written_down(env):
    """The whole verdict: silent, rating-shaped, and recorded.

    A flagged car keeps its place in the standings and nobody in the room is
    told anything - it goes through the same door a guest already goes through.
    The finding is the part that survives, in a table nothing reads yet.
    """
    A = env
    with A.app.app_context():
        game = A.DriveGame(code="ZZZZZZ", track="sunrise", status="waiting")
        A.db.session.add(game)
        A.db.session.commit()
        players = {}
        for n in ("alice", "bob"):
            u = A.User(username=n, email=n + "@example.com", password_hash="x")
            A.db.session.add(u)
            A.db.session.commit()
            pl = A.DrivePlayer(game_id=game.id, name=n, user_id=u.id,
                               session_key=n, color="#fff")
            A.db.session.add(pl)
            A.db.session.commit()
            players[n] = pl

        cheat, clean = players["alice"].pid, players["bob"].pid
        r = A._room("ZZZZZZ")
        r["grid"] = {cheat: 0, clean: 1}
        for pid, n in ((cheat, "alice"), (clean, "bob")):
            A._car(r, pid)["name"] = n
        A._watch(r, cheat).strikes = racecheck.STRIKE_LIMIT
        A._watch(r, cheat).reasons = {"moved 900 units in 33ms": 40}
        standings = [{"pid": cheat, "name": "alice", "ms": 12000},
                     {"pid": clean, "name": "bob", "ms": 15000}]

        flagged = A._judge_race(r)
        assert set(flagged) == {cheat}
        elo = A._rate_race(game, standings, set(flagged))
        assert elo == {}, "one clean account has nobody left to be rated against"
        A._record_flags(r, game, flagged, None)

        rows = A.DriveCheatFlag.query.all()
        assert len(rows) == 1
        assert rows[0].name == "alice"
        assert rows[0].user_id == players["alice"].user_id
        assert rows[0].reasons == {"moved 900 units in 33ms": 40}


def test_a_clean_race_flags_nobody(env):
    A = env
    with A.app.app_context():
        r = A._room("ZZZZZZ")
        r["grid"] = {"a": 0, "b": 1}
        for pid in ("a", "b"):
            A._car(r, pid)
        r["rec"] = {"track": "sunrise", "n": 10, "cars": {
            "a": _frames(_walk(TRACK, tuning.MAX_SPEED * 0.9, A.REPLAY_HZ)),
            "b": _frames(_walk(TRACK, tuning.MAX_SPEED * 0.5, A.REPLAY_HZ)),
        }}
        assert A._judge_race(r) == {}
