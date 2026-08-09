"""The room's race machine: qualifying, the grid, ending a race, and rating it.

These are the parts that used to strand a room. A race only ever ended because
somebody finished one - the grace clock was armed by the first finisher and
nothing else - so a race nobody finished never ended at all, which left the
room in `racing` with the host unable to start another or change track. Every
test below is one of the ways that happened, plus the two rules that decide
who starts where and whose number moves.

The live room state is plain dicts, so it is built here directly rather than
driven through a socket: what is under test is the bookkeeping, not the wire.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


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


def _room(A, code="TEST", phase="racing"):
    """A live room with the pump left alone."""
    r = A._room(code)
    r["phase"] = phase
    return r


def _add_car(A, r, pid, name=None, ms=None, dnf=False, gone=False,
             qual=None, fresh=True, on_grid=True):
    c = A._car(r, pid)
    c["name"] = name or pid
    c["color"] = "#fff"
    c["ts"] = A._now_ms() if fresh else 0
    c["ms"], c["dnf"], c["gone"] = ms, dnf, gone
    if ms is not None:
        r["finish"].append({"pid": pid, "name": c["name"], "ms": ms,
                            "color": c["color"]})
        r["finish"].sort(key=lambda e: e["ms"])
    if qual is not None:
        r["qual"][pid] = qual
    if on_grid:
        r["grid"][pid] = len(r["grid"])
    return c


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------

def test_the_grid_is_qualifying_order(env):
    A = env
    r = _room(A, phase="qualifying")
    r["grid"] = {}
    _add_car(A, r, "slow", qual=50000, on_grid=False)
    _add_car(A, r, "fast", qual=42000, on_grid=False)
    _add_car(A, r, "mid", qual=45000, on_grid=False)
    grid = A._start_grid(r)
    assert [p for p, _ in sorted(grid.items(), key=lambda kv: kv[1])] == \
        ["fast", "mid", "slow"]


def test_a_driver_with_no_lap_starts_at_the_back(env):
    """A lap is the price of a good slot, however fast you might have been."""
    A = env
    r = _room(A, phase="qualifying")
    r["grid"] = {}
    _add_car(A, r, "nolap", on_grid=False)
    _add_car(A, r, "slow", qual=90000, on_grid=False)
    grid = A._start_grid(r)
    assert grid["slow"] == 0 and grid["nolap"] == 1


def test_the_grid_is_never_ordered_by_name(env):
    """The old order was alphabetical, so the same person had pole every race.

    Arbitrary would have been survivable; arbitrary *and stable* was not.
    """
    A = env
    poles = set()
    for _ in range(40):
        r = _room(A, "N" + str(len(poles)), phase="qualifying")
        r["cars"], r["grid"], r["qual"] = {}, {}, {}
        for pid in ("aaa", "bbb", "ccc", "ddd"):
            _add_car(A, r, pid, on_grid=False)
        grid = A._start_grid(r)
        poles.add(next(p for p, i in grid.items() if i == 0))
    assert len(poles) > 1, "an unqualified field must not always line up the same way"


def test_the_grid_knows_which_side_the_inside_line_is(env):
    """Pole always starts on the inside of the first corner, so the client has
    to be told which side that is - and it comes with the track, because it is a
    fact about the track rather than about the race.

    It used to alternate instead, on the grounds that nobody knew which side was
    the good one. Half the time that put the car which had just qualified
    fastest on the outside of turn one.
    """
    A = env
    with A.app.app_context():
        for slug in ("sunrise", "spiral"):
            assert A._track_payload(slug)["pole_side"] in (-1, 1)


def test_without_qualifying_the_grid_reverses_the_last_result(env):
    """No session to earn a slot in, so the room's own last answer is used:
    whoever was beaten starts ahead of whoever beat them."""
    A = env
    r = _room(A, phase="free")
    for pid in ("won", "second", "last"):
        _add_car(A, r, pid, on_grid=False)
    r["last_order"] = ["won", "second", "last"]
    grid = A._reverse_grid(r)
    assert [p for p, _ in sorted(grid.items(), key=lambda kv: kv[1])] == \
        ["last", "second", "won"]


def test_somebody_who_was_not_in_the_last_race_lines_up_behind_it(env):
    """A grid slot is something the room has watched you earn or lose. Turning
    up is neither, so a newcomer starts behind the field."""
    A = env
    r = _room(A, phase="free")
    for pid in ("won", "lost", "newcomer"):
        _add_car(A, r, pid, on_grid=False)
    r["last_order"] = ["won", "lost"]
    grid = A._reverse_grid(r)
    assert grid["lost"] == 0 and grid["won"] == 1 and grid["newcomer"] == 2


def test_the_first_race_of_a_room_is_not_lined_up_the_same_way_twice(env):
    """With no last result there is nothing to reverse, and the one thing the
    order must not be is stable - that is the bug the name sort was."""
    A = env
    poles = set()
    for n in range(40):
        r = _room(A, "R" + str(n), phase="free")
        r["cars"], r["grid"], r["last_order"] = {}, {}, []
        for pid in ("aaa", "bbb", "ccc", "ddd"):
            _add_car(A, r, pid, on_grid=False)
        grid = A._reverse_grid(r)
        poles.add(next(p for p, i in grid.items() if i == 0))
    assert len(poles) > 1


def test_a_room_races_unless_the_host_asks_for_qualifying(env):
    """So a new room's first grid is the shuffle `_reverse_grid` falls back to,
    not the order a session it never ran would have produced."""
    A = env
    assert A._room("NEW")["settings"]["qualifying"] is False


def test_the_settings_and_the_last_result_survive_a_race(env):
    """`_reset_race` clears the race. These two are not the race: one is the
    host's setting and the other is the next grid."""
    A = env
    r = _room(A)
    r["settings"]["qualifying"] = False
    r["last_order"] = ["a", "b"]
    A._reset_race(r)
    assert r["phase"] == "free"
    assert r["settings"]["qualifying"] is False and r["last_order"] == ["a", "b"]


def test_the_qualifying_countdown_is_a_phase_a_race_can_be_called_off_in(env):
    """It is one of the live phases, so the track cannot be changed underneath
    it and the host calling it off has something to call off."""
    A = env
    assert "qual_countdown" in A.LIVE_PHASES
    r = _room(A, phase="qual_countdown")
    _add_car(A, r, "a", on_grid=False)
    A._abort_race("TEST", "testing")
    assert r["phase"] == "free"


# ---------------------------------------------------------------------------
# The room's settings
# ---------------------------------------------------------------------------

def test_qualifying_is_off_unless_the_host_turns_it_on(env):
    """A new room races. Ninety seconds of session plus five of lights is
    longer than some of the races it sets the grid for."""
    A = env
    assert A._room("SET1")["settings"]["qualifying"] is False


def test_a_room_owns_its_settings(env):
    """A copy of the defaults, not the defaults - one host must not set every
    other room's rules along with their own."""
    A = env
    A._room("SET2")["settings"]["qualifying"] = True
    assert A._room("SET3")["settings"]["qualifying"] is False
    assert A.ROOM_DEFAULTS["qualifying"] is False


def test_opening_a_race_lights_the_session(env):
    """Both answers end in five seconds of lights. With qualifying on, what
    they are counting down to is the session; the clock on it is not started
    until they have run out, so the ninety seconds are ninety seconds of
    driving rather than eighty-five."""
    A = env
    r = _room(A, phase="free")
    r["settings"]["qualifying"] = True
    assert A._open_race(r) is True
    assert r["phase"] == "qual_countdown"
    assert r["qual_end"] is None and r["t0"] is not None


def test_opening_a_race_without_qualifying_goes_straight_to_the_grid(env):
    """With it off - which is how a room starts - the room never enters the
    session at all: the same five seconds of lights, counting down to the race
    itself."""
    A = env
    r = _room(A, phase="free")
    assert r["settings"]["qualifying"] is False
    assert A._open_race(r) is False
    assert r["phase"] == "countdown"
    assert r["qual"] == {} and r["qual_end"] is None


# ---------------------------------------------------------------------------
# Ending a race
# ---------------------------------------------------------------------------

def test_a_race_nobody_finished_still_ends(env):
    """The case that stranded rooms: no finisher, so nothing armed the clock."""
    A = env
    r = _room(A)
    _add_car(A, r, "a", dnf=True)
    _add_car(A, r, "b", dnf=True)
    assert A._pending(r) == []
    A._close_race("TEST", "all in", r["race_seq"])
    assert r["phase"] == "results"


def test_the_results_sheet_comes_down_by_itself(env, monkeypatch):
    """`_close_race` leaves the room on the results sheet and *schedules* the drop
    back to practice; `_clear_results` is that drop.

    The two used to be one function with an inline `eventlet.sleep(12)` between
    them, which meant this half could only be reached by waiting twelve real
    seconds - so it was never tested, and the two tests that called `_close_race`
    paid the twelve seconds each. That was 24s of a 56s suite.
    """
    A = env
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    monkeypatch.setattr(A, "_broadcast_lobbies", lambda *a, **k: None)
    r = _room(A)
    _add_car(A, r, "a", ms=41000)
    A._close_race("TEST", "all in", r["race_seq"])
    assert r["phase"] == "results"
    A._clear_results("TEST", r["race_seq"])
    assert r["phase"] == "free"


def test_a_stale_results_timer_leaves_the_next_race_alone(env, monkeypatch):
    """The guard that matters here: Rematch can start a new race inside
    RESULTS_HOLD_S, so the timer armed for the *previous* one must not tidy up the
    one now running. Same rule every deferred close in this file carries."""
    A = env
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    monkeypatch.setattr(A, "_broadcast_lobbies", lambda *a, **k: None)
    r = _room(A)
    _add_car(A, r, "a", ms=41000)
    stale = r["race_seq"]
    A._close_race("TEST", "all in", stale)
    r["phase"] = "racing"                 # Rematch, inside the hold
    r["race_seq"] = stale + 1
    A._clear_results("TEST", stale)
    assert r["phase"] == "racing"         # untouched
    assert r["race_seq"] == stale + 1


def test_the_last_car_leaving_ends_the_race(env):
    A = env
    r = _room(A)
    _add_car(A, r, "a", ms=41000)
    left = _add_car(A, r, "b")
    left["gone"] = True                     # closed the tab mid-race
    assert A._pending(r) == []


def test_somebody_who_walks_in_mid_race_cannot_hold_it_open(env):
    """The grid is the field. A latecomer is driving, but not racing."""
    A = env
    r = _room(A)
    _add_car(A, r, "racer", ms=41000)
    _add_car(A, r, "tourist", on_grid=False)
    assert A._pending(r) == []


def test_a_car_still_out_there_holds_the_race_open(env):
    A = env
    r = _room(A)
    _add_car(A, r, "home", ms=41000)
    _add_car(A, r, "out")
    assert A._pending(r) == ["out"]


def test_leaving_mid_race_is_a_dnf_not_an_escape(env, monkeypatch):
    """Quitting the tab used to delete the car, and with it the loss.

    So the cheapest way to protect a rating was to close the browser, which is
    the one thing a rating system must never make the smart move.
    """
    A = env
    sent = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, *a, **k: sent.append((ev, a[0] if a else None)))
    r = _room(A)
    _add_car(A, r, "winner", ms=41000)
    _add_car(A, r, "quitter", gone=True)
    A._close_race("TEST", "all in", r["race_seq"])
    result = next(d for ev, d in sent if ev == "race_result")
    assert [e["pid"] for e in result["standings"]] == ["winner", "quitter"]
    assert result["standings"][1]["ms"] is None


def test_a_stale_timer_cannot_close_the_next_race(env):
    """Every close is stamped with the race it was armed for."""
    A = env
    r = _room(A)
    stale = r["race_seq"]
    r["race_seq"] += 1                      # a new race has since started
    A._close_race("TEST", "timeout", stale)
    assert r["phase"] == "racing"


def test_the_hard_limit_is_bounded_at_both_ends(env):
    A = env
    assert A._hard_race_ms("") >= A.HARD_RACE_MIN_MS
    for slug in ("sunrise", "twist"):
        ms = A._hard_race_ms(slug)
        assert A.HARD_RACE_MIN_MS <= ms <= A.HARD_RACE_MAX_MS


def test_aborting_hands_the_room_back_clean(env):
    A = env
    r = _room(A, phase="countdown")
    _add_car(A, r, "a", qual=42000)
    A._abort_race("TEST", "called off")
    assert r["phase"] == "free"
    assert r["qual"] == {} and r["grid"] == {} and r["finish"] == []
    assert r["t0"] is None and r["hard_end"] is None


def test_a_reset_forgets_the_cars_that_left_but_keeps_the_ones_here(env):
    A = env
    r = _room(A)
    _add_car(A, r, "here", ms=41000)
    _add_car(A, r, "gone", gone=True)
    A._reset_race(r)
    assert set(r["cars"]) == {"here"}
    assert r["cars"]["here"]["ms"] is None and r["cars"]["here"]["dnf"] is False


# ---------------------------------------------------------------------------
# The pose snapshot, which is the only thing a rival is drawn and heard from
# ---------------------------------------------------------------------------

def _pose(A, code, pid, sid="sid1", **fields):
    """Drive the real handler, which reads its player off the socket id."""
    A._sid_room[sid] = (code, pid)
    with A.app.test_request_context():
        from flask import request
        request.sid = sid
        A.on_pose(dict({"p": [1.0, 2.0, 3.0], "q": [0, 0, 0, 1], "v": [0, 0, -40],
                        "prog": 12.5, "cp": 2, "flags": 0}, **fields))


def test_the_snapshot_carries_how_full_a_cars_tow_is(env):
    """A rival's slipstream is drawn and heard from this one number, with the
    flag byte saying whether it is the charge or the boost. Without it the only
    thing a rival's tow could be is on or off - and the half worth watching is
    the second and a half it spends filling behind you."""
    A = env
    r = _room(A)
    _add_car(A, r, "a")
    _pose(A, "TEST", "a", sl=0.4)
    row = A._snapshot(r)["cars"]["a"]
    assert row[12] == 0 and row[14] == pytest.approx(0.4)
    _pose(A, "TEST", "a", sl=0.75, flags=16)
    row = A._snapshot(r)["cars"]["a"]
    assert row[12] & 16 and row[14] == pytest.approx(0.75)


def test_the_tow_and_the_age_are_appended_not_inserted(env):
    """Both trailing fields arrived after the format did, and the client guards
    on the array's length - so a page left open across a deploy loses the tow
    rather than reading a car's velocity as its position."""
    A = env
    r = _room(A)
    _add_car(A, r, "a")
    _pose(A, "TEST", "a")
    row = A._snapshot(r)["cars"]["a"]
    assert row[:3] == [1.0, 2.0, 3.0] and row[7:10] == [0, 0, -40.0]
    assert row[10] == 12.5 and row[11] == 2
    assert len(row) == 15


def test_a_client_cannot_claim_a_tow_it_does_not_have(env):
    """It is fanned straight back out and it is the loudness of an effect on
    everybody else's screen, so it is clamped rather than trusted."""
    A = env
    r = _room(A)
    _add_car(A, r, "a")
    for sent, want in ((400, 1.0), (-3, 0.0), (None, 0.0)):
        _pose(A, "TEST", "a", sl=sent)
        assert A._snapshot(r)["cars"]["a"][14] == want


# ---------------------------------------------------------------------------
# Splits, which is how everyone gets a gap to the leader
# ---------------------------------------------------------------------------

def _split(A, code, pid, cp, ms, sid="sid1"):
    """Drive the real handler, which reads its player off the socket id."""
    A._sid_room[sid] = (code, pid)
    with A.app.test_request_context():
        from flask import request
        request.sid = sid
        A.on_split({"cp": cp, "ms": ms})


def test_a_checkpoint_time_is_recorded_once(env, monkeypatch):
    """A second time for the same checkpoint is a replayed message, not a
    faster lap, and taking it would let a client rewrite its own gap."""
    A = env
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    r = _room(A)
    _add_car(A, r, "a")
    _split(A, "TEST", "a", 1, 12000)
    _split(A, "TEST", "a", 1, 9000)
    assert r["splits"]["a"] == {1: 12000}


def test_only_cars_in_the_race_report_splits(env, monkeypatch):
    """Somebody practising alongside a race is not in it, and their times
    must not become anybody's reference."""
    A = env
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    r = _room(A)
    _add_car(A, r, "tourist", on_grid=False)
    _split(A, "TEST", "tourist", 1, 5000)
    assert r["splits"] == {}


def test_splits_are_dropped_with_the_race_they_belong_to(env):
    A = env
    r = _room(A)
    _add_car(A, r, "a")
    r["splits"]["a"] = {1: 12000}
    A._reset_race(r)
    assert r["splits"] == {}


# ---------------------------------------------------------------------------
# Rating it
# ---------------------------------------------------------------------------

def _game_with(A, players):
    """A DriveGame whose players are (name, logged_in) pairs. Returns pids."""
    with A.app.app_context():
        game = A.DriveGame(code="RATE", track="sunrise")
        A.db.session.add(game)
        A.db.session.commit()
        pids = {}
        for i, (name, logged_in) in enumerate(players):
            uid = None
            if logged_in:
                u = A.User(username=name, email=name + "@example.com")
                u.set_password("password123")
                A.db.session.add(u)
                A.db.session.commit()
                uid = u.id
            p = A.DrivePlayer(game_id=game.id, user_id=uid, session_key=name,
                              name=name, color="#fff", seat_order=i)
            A.db.session.add(p)
            A.db.session.commit()
            pids[name] = p.pid
        return game.id, pids


def _standings(pids, *rows):
    """rows are (name, ms) with ms None for a DNF, in finishing order."""
    return [{"pid": pids[n], "name": n, "ms": ms, "color": "#fff"}
            for n, ms in rows]


def test_a_guest_beating_you_costs_you_nothing(env):
    """Guests are in the race and on the screen, but not in the rating.

    Otherwise the number is one anybody can move with a second browser tab.
    """
    A = env
    gid, pids = _game_with(A, [("alice", True), ("bob", True), ("ghost", False)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        out = A._rate_race(game, _standings(
            pids, ("ghost", 40000), ("alice", 41000), ("bob", 42000)))
        assert out[pids["alice"]]["delta"] > 0, "alice beat every rated rival"
        assert out[pids["bob"]]["delta"] < 0
        assert pids["ghost"] not in out


def test_the_win_goes_to_the_best_account_not_the_best_car(env):
    """A guest winning used to mean nobody was recorded as having won."""
    A = env
    gid, pids = _game_with(A, [("alice", True), ("bob", True), ("ghost", False)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        A._rate_race(game, _standings(
            pids, ("ghost", 40000), ("alice", 41000), ("bob", 42000)))
        alice = A.User.query.filter_by(username="alice").first()
        assert alice.drive.wins == 1
        assert alice.drive.podiums == 1


def test_one_account_among_guests_is_not_rated(env):
    """There is nobody to rate them against, so nothing happens - including
    the race count, which would otherwise climb on races that never counted."""
    A = env
    gid, pids = _game_with(A, [("alice", True), ("g1", False), ("g2", False)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        out = A._rate_race(game, _standings(
            pids, ("g1", 40000), ("alice", 41000), ("g2", 42000)))
        assert out == {}
        alice = A.User.query.filter_by(username="alice").first()
        # Not even a stats row: nothing about her was touched, so the race
        # count cannot creep up on races that were never rated.
        assert alice.drive is None or (alice.drive.races or 0) == 0


def test_two_dnfs_draw_with_each_other(env):
    """Their order is the order they happened to give up in. Rating it is
    rating noise, and at equal ratings a draw has to move nobody."""
    A = env
    gid, pids = _game_with(A, [("alice", True), ("bob", True)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        out = A._rate_race(game, _standings(
            pids, ("alice", None), ("bob", None)))
        assert out[pids["alice"]]["delta"] == 0
        assert out[pids["bob"]]["delta"] == 0


def test_retiring_is_never_a_win(env):
    A = env
    gid, pids = _game_with(A, [("alice", True), ("bob", True)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        A._rate_race(game, _standings(pids, ("alice", None), ("bob", None)))
        alice = A.User.query.filter_by(username="alice").first()
        assert alice.drive.wins == 0
        assert alice.drive.races == 1, "it was still a race you took part in"


def test_finishing_beats_retiring(env):
    A = env
    gid, pids = _game_with(A, [("alice", True), ("bob", True)])
    with A.app.app_context():
        game = A.DriveGame.query.get(gid)
        out = A._rate_race(game, _standings(pids, ("alice", 41000), ("bob", None)))
        assert out[pids["alice"]]["delta"] > 0
        assert out[pids["bob"]]["delta"] < 0


# ---------------------------------------------------------------------------
# The replay
# ---------------------------------------------------------------------------
# Recorded off the poses the server already has, on the ghost's clock, so that
# frame `n` of every car in a race is the same instant. The rows therefore have
# to stay the same length whatever the cars do - a car that finishes, drops out
# or simply goes quiet must not leave a hole, because a hole slides everything
# after it and slews that car's replay against everybody else's.

def _recording(A, code="REC", cars=("a", "b")):
    r = _room(A, code, phase="racing")
    for pid in cars:
        _add_car(A, r, pid)
    r["rec"] = {"t0": A._now_ms() - 1000, "track": "sunrise", "n": 0,
                "cars": {pid: [] for pid in cars}}
    return r


def test_a_race_is_recorded_on_the_ghosts_clock(env):
    A = env
    r = _recording(A)
    A._record_race(r)
    # A second of race at the ghost rate, and every car has all of it.
    lens = {pid: len(f) for pid, f in r["rec"]["cars"].items()}
    assert set(lens.values()) == {A.REPLAY_HZ + 1}


def test_a_car_that_stops_reporting_still_fills_its_row(env):
    """It has finished, or left, or its connection went. Either way the replay
    has to stay rectangular or every car after it plays back out of step."""
    A = env
    r = _recording(A)
    A._record_race(r)
    del r["cars"]["b"]
    r["rec"]["t0"] -= 1000
    A._record_race(r)
    a, b = (r["rec"]["cars"][k] for k in ("a", "b"))
    assert len(a) == len(b)
    assert b[-1] == b[len(b) - A.REPLAY_HZ - 1], "a gone car should hold its last pose"


def test_nothing_is_recorded_outside_a_race(env):
    A = env
    r = _recording(A)
    r["phase"] = "results"
    A._record_race(r)
    assert all(not f for f in r["rec"]["cars"].values())


def test_a_finished_race_is_stored_as_one_replay_per_car(env):
    A = env
    with A.app.app_context():
        game = A.DriveGame(code="REC", track="sunrise")
        A.db.session.add(game)
        A.db.session.commit()
        r = _recording(A)
        A._record_race(r)
        standings = [{"pid": "b", "name": "b", "ms": 41000, "color": "#fff"},
                     {"pid": "a", "name": "a", "ms": None, "color": "#fff"}]
        rid = A._store_replay(r, game, standings, "all in")
        race = A.DriveRace.query.get(rid)
        assert race.track == "sunrise" and race.hz == A.REPLAY_HZ
        cars = race.cars
        assert [c["pid"] for c in cars] == ["b", "a"], "opens on the winner"
        for c in cars:
            frames = A.runcheck.unpack_ghost(c["ghost"])
            assert len(frames) == A.REPLAY_HZ + 1 and len(frames[0]) == 8


def test_a_race_with_nothing_recorded_stores_no_replay(env):
    """Everybody vanished before the first frame. An empty replay offered from
    the results sheet is worse than no replay at all."""
    A = env
    with A.app.app_context():
        game = A.DriveGame(code="REC", track="sunrise")
        A.db.session.add(game)
        A.db.session.commit()
        r = _recording(A)
        assert A._store_replay(r, game, [], "all in") is None
        assert A.DriveRace.query.count() == 0


# ---------------------------------------------------------------------------
# The whole way in: free -> qualifying -> the grid
# ---------------------------------------------------------------------------
# The phase machine grew a fourth live phase (the five seconds before
# qualifying) and a way to skip two of them, so the transitions are driven here
# through the real handlers rather than by setting `phase` by hand. Timers are
# fired immediately: what is under test is the order things happen in, not
# eventlet.

@pytest.fixture()
def live(env, monkeypatch):
    """A room with a host, a guest, and every emit and timer captured."""
    A = env
    sent = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, *a, **k: sent.append((ev, a[0] if a else None)))
    monkeypatch.setattr(A, "emit", lambda *a, **k: None)
    monkeypatch.setattr(A, "_broadcast_lobbies", lambda *a, **k: None)
    fired = []
    monkeypatch.setattr(A.eventlet, "spawn_after",
                        lambda delay, fn, *a: fired.append((fn, a)))
    with A.app.app_context():
        game = A.DriveGame(code="LIVE", track="sunrise")
        A.db.session.add(game)
        A.db.session.commit()
        host = A.DrivePlayer(game_id=game.id, session_key="sk-host", name="host",
                             color="#fff", seat_order=0, is_host=True)
        other = A.DrivePlayer(game_id=game.id, session_key="sk-other", name="other",
                              color="#0f0", seat_order=1)
        A.db.session.add_all([host, other])
        A.db.session.commit()
        r = A._room("LIVE")
        for p in (host, other):
            c = A._car(r, p.pid)
            c["name"], c["color"], c["ts"] = p.name, p.color, A._now_ms()
        yield A, r, {"host": host.pid, "other": other.pid}, sent, fired


def _as_host(A, fn, *args):
    """Run a host-only handler as the host of the LIVE room."""
    with A.app.test_request_context():
        from flask import session
        session["session_key"] = "sk-host"
        fn(*args)


def _qual_on(r):
    """A room defaults to racing, so a test about the session has to ask for it.

    Set straight into the state rather than through `on_set_setting`: its fan-out
    lands in `sent`, which is the list several of these tests read the room's
    events off.
    """
    r["settings"]["qualifying"] = True


def _run(fired):
    """Fire every timer armed so far, in order, and clear the queue."""
    todo, fired[:] = list(fired), []
    for fn, args in todo:
        fn(*args)


def test_starting_runs_the_lights_before_qualifying_not_after(live):
    """The session used to simply begin, so the first anyone knew of it was a
    toast saying they were already in it and a lap that no longer counted."""
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    assert r["phase"] == "qual_countdown"
    assert [e for e, _ in sent] == ["qual_countdown"]
    _run(fired)
    assert r["phase"] == "qualifying"
    assert "qual_start" in [e for e, _ in sent]


def test_with_qualifying_off_the_lights_are_the_races_own(live):
    """Nobody wants ninety seconds of driving alone before every race, which is
    why it is off unless asked for - and then Start race means start the race."""
    A, r, pids, sent, fired = live
    assert r["settings"]["qualifying"] is False
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    assert r["phase"] == "countdown"
    assert "race_start" in [e for e, _ in sent]
    assert set(r["grid"]) == set(pids.values())
    _run(fired)
    assert r["phase"] == "racing"


def test_the_qualifying_switch_is_the_hosts_and_only_between_races(live):
    A, r, pids, sent, fired = live
    with A.app.test_request_context():
        from flask import session
        session["session_key"] = "sk-other"
        A.on_set_setting({"code": "LIVE", "key": "qualifying", "value": True})
    assert r["settings"]["qualifying"] is False, "anybody could turn it on"
    _as_host(A, A.on_set_setting,
             {"code": "LIVE", "key": "qualifying", "value": True})
    assert r["settings"]["qualifying"] is True, "the host could not turn it on"
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _as_host(A, A.on_set_setting,
             {"code": "LIVE", "key": "qualifying", "value": False})
    assert r["settings"]["qualifying"] is True, "changed under a live session"


def test_a_qualifying_lap_puts_its_replay_on_pole(live):
    """The lap that is provisionally on pole is the one ghost worth having in a
    session that exists to set it, so it comes up with the time."""
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _run(fired)
    frames = [[0, 0, 0, 0, 0, 0, 1, 0]] * 40
    A._sid_room["s1"] = ("LIVE", pids["other"])
    with A.app.test_request_context():
        from flask import request
        request.sid = "s1"
        A.on_qual_time({"ms": 44000, "ghost": frames})
    assert r["pole"]["pid"] == pids["other"] and r["pole"]["ms"] == 44000
    # Only who is on pole is broadcast; the lap is fetched by whoever wants it.
    pole = [d for e, d in sent if e == "qual_pole"][-1]
    assert "ghost" not in pole and pole["name"] == "other"


def test_a_slower_lap_does_not_take_pole(live):
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _run(fired)
    frames = [[0, 0, 0, 0, 0, 0, 1, 0]] * 40

    def lap(sid, pid, ms):
        A._sid_room[sid] = ("LIVE", pid)
        with A.app.test_request_context():
            from flask import request
            request.sid = sid
            A.on_qual_time({"ms": ms, "ghost": frames})

    lap("s1", pids["other"], 42000)
    lap("s2", pids["host"], 47000)
    assert r["pole"]["pid"] == pids["other"]
    lap("s2", pids["host"], 41000)
    assert r["pole"]["pid"] == pids["host"]


def test_the_session_ends_on_the_grid_it_set(live):
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _run(fired)                       # the lights -> qualifying
    r["qual"] = {pids["other"]: 42000, pids["host"]: 44000}
    _run(fired)                       # the session clock -> the grid
    assert r["phase"] == "countdown"
    assert r["grid"][pids["other"]] == 0
    _run(fired)                       # the countdown -> green
    assert r["phase"] == "racing" and r["rec"] is not None


def test_the_host_can_skip_the_rest_of_the_session(live):
    """Ninety seconds is the right length for a session nobody wants cut short
    and the wrong length for two people who are ready."""
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _run(fired)
    r["qual"] = {pids["host"]: 43000}
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    assert r["phase"] == "countdown"


def test_somebody_leaving_between_the_flag_and_the_grid_is_not_lined_up(live):
    """The grid is worked out at the end of qualifying and used a moment later,
    under a second hold of the room lock. During qualifying a leaver's car is
    dropped outright - there is no race for them to be a DNF in - so the list
    can name somebody who is no longer there, and the slots have to close up
    rather than start the race with a hole in the field."""
    A, r, pids, sent, fired = live
    _qual_on(r)
    _as_host(A, A.on_start_race, {"code": "LIVE"})
    _run(fired)
    r["qual"] = {pids["other"]: 42000, pids["host"]: 44000}
    grid = A._start_grid(r)
    r["cars"].pop(pids["other"])          # they close the tab on their in-lap
    A._light_grid("LIVE", r["race_seq"], "sunrise", grid)
    assert r["grid"] == {pids["host"]: 0}
    assert r["phase"] == "countdown"


# ---------------------------------------------------------------------------
# Leaving
# ---------------------------------------------------------------------------

def test_leaving_takes_your_name_with_you(env, monkeypatch):
    """Every button that leaves a room emits `leave` with no payload at all, so
    the handler has to be callable with no arguments - it was not, and it threw
    before deleting anything. You left the room and your name stayed in it.

    The same default is on every handler here now, so a client that emits
    without a payload is a non-event rather than a line in the log.
    """
    A = env
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    monkeypatch.setattr(A, "_broadcast_lobbies", lambda *a, **k: None)
    with A.app.app_context():
        game = A.DriveGame(code="BYE", track="sunrise")
        A.db.session.add(game)
        A.db.session.commit()
        stay = A.DrivePlayer(game_id=game.id, session_key="sk-stay", name="stay",
                             color="#fff", seat_order=0, is_host=True)
        go = A.DrivePlayer(game_id=game.id, session_key="sk-go", name="go",
                           color="#0f0", seat_order=1)
        A.db.session.add_all([stay, go])
        A.db.session.commit()
        gid, gone_pid = game.id, go.pid
        r = _room(A, "BYE", phase="free")
        _add_car(A, r, gone_pid, on_grid=False)
        A._sid_room["sid-go"] = ("BYE", gone_pid)
        with A.app.test_request_context():
            from flask import request, session
            request.sid = "sid-go"
            session["session_key"] = "sk-go"
            A.on_leave()                      # exactly how the client calls it
        left = [p.name for p in A.DriveGame.query.get(gid).players]
        assert left == ["stay"]
        assert gone_pid not in r["cars"]


# ---------------------------------------------------------------------------
# Two people, one colour
# ---------------------------------------------------------------------------

def test_two_people_choosing_one_colour_both_keep_it(env):
    """The deleted first-free rule, asserted from the other side.

    A seat used to take your colour only if nobody in the room had it already,
    and fall back to the first colour going otherwise. That was the right trade
    while nobody had chosen anything - a hashed colour is not yours in any sense
    worth protecting, and two identical cars on a grid is worse than being the
    wrong red for one race. It is exactly the wrong trade now: being handed a
    stranger's colour without being told is far worse than sharing one, and the
    cars have names over them precisely so colour is not the only way to tell
    them apart.

    So the rule is gone, and this is what says it stays gone.
    """
    import garage
    with env.app.app_context():
        game = env.DriveGame(code="SAME", track="sunrise")
        env.db.session.add(game)
        env.db.session.commit()
        seats = []
        for i, name in enumerate(("alice", "bob")):
            u = env.User(username=name, email=name + "@example.com")
            u.set_password("password123")
            env.db.session.add(u)
            env.db.session.commit()
            env.db.session.add(env.DriveGarage(
                user_id=u.id, livery_json=garage.dumps({"body": "#7b6cf6"}),
                earned_json="[]"))
            seats.append(env.DrivePlayer(game_id=game.id, user_id=u.id,
                                         session_key="sk-" + name, name=name,
                                         color=garage.color_for(name),
                                         seat_order=i))
        env.db.session.add_all(seats)
        env.db.session.commit()

        roster = env._roster(game.players)
        assert [p["livery"]["body"] for p in roster] == ["#7b6cf6", "#7b6cf6"]
        # And the dot, the standings row and the nameplate agree with the car -
        # `color` is answered off the livery, so nothing points at somebody in a
        # colour they are not driving.
        assert [p["color"] for p in roster] == ["#7b6cf6", "#7b6cf6"]
        # The names are what tell them apart, so they had better be there.
        assert [p["name"] for p in roster] == ["alice", "bob"]


def test_a_seat_takes_the_colour_you_chose_and_not_the_one_you_were_given(env):
    """`_add_player` writes the hashed colour into the column as a seed, and
    every path that reports a seat answers off the livery instead - so opening
    the garage changes the car you turn up in, which is the entire point."""
    import garage
    with env.app.app_context():
        game = env.DriveGame(code="MINE", track="sunrise")
        u = env.User(username="alice", email="a@example.com")
        u.set_password("password123")
        env.db.session.add_all([game, u])
        env.db.session.commit()
        seat = env.DrivePlayer(game_id=game.id, user_id=u.id, session_key="sk-a",
                               name="alice", color=garage.color_for("alice"),
                               seat_order=0)
        env.db.session.add(seat)
        env.db.session.commit()

        hashed = garage.color_for("alice")
        assert env._roster(game.players)[0]["color"] == hashed

        env.db.session.add(env.DriveGarage(
            user_id=u.id, livery_json=garage.dumps({"body": "#17bfa8"}),
            earned_json="[]"))
        env.db.session.commit()
        assert env._roster(game.players)[0]["color"] == "#17bfa8"
        assert seat.color == hashed, "the column is the seed, not the answer"


def test_a_guest_seat_is_still_hashed_off_the_name_it_typed(env):
    """Guests spread out for free, which is what let the first-free rule go
    entirely: they have no account to store a livery against, so the hash is
    still the whole answer - and `GUEST_COLOR` for all of them would have put
    every guest in a room in the same car."""
    import garage
    assert garage.color_for("dave") != garage.color_for("erin")
    with env.app.app_context():
        game = env.DriveGame(code="GST", track="sunrise")
        env.db.session.add(game)
        env.db.session.commit()
        for i, n in enumerate(("dave", "erin")):
            env.db.session.add(env.DrivePlayer(
                game_id=game.id, session_key="sk-" + n, name=n,
                color=garage.color_for(n), seat_order=i))
        env.db.session.commit()
        roster = env._roster(game.players)
        assert roster[0]["color"] != roster[1]["color"]
        assert all(p["livery"]["body"] == p["color"] for p in roster)


def test_a_replay_keeps_the_cars_as_they_were_on_the_day(env):
    """The livery goes into `drive_races.cars_json` beside the colour rather than
    being looked up when the replay is watched. A race is a record of an evening,
    so somebody repainting next week must not repaint themselves in it - which is
    the opposite of the ghost rule, and deliberately: a ghost is a lap you are
    chasing *now*, and a replay is a thing that happened.
    """
    import garage
    A = env
    with A.app.app_context():
        game = A.DriveGame(code="REC", track="sunrise")
        u = A.User(username="alice", email="a@example.com")
        u.set_password("password123")
        A.db.session.add_all([game, u])
        A.db.session.commit()
        alice = A.DrivePlayer(game_id=game.id, user_id=u.id, session_key="sk-a",
                              name="alice", color="#fff", seat_order=0)
        bob = A.DrivePlayer(game_id=game.id, session_key="sk-b", name="bob",
                            color="#0f0", seat_order=1)
        A.db.session.add_all([alice, bob])
        A.db.session.commit()
        A.db.session.add(A.DriveGarage(
            user_id=u.id, earned_json="[]",
            livery_json=garage.dumps({"body": "#17bfa8", "rim_style": "mesh"})))
        A.db.session.commit()

        r = _recording(A, cars=(alice.pid, bob.pid))
        A._record_race(r)
        standings = [{"pid": alice.pid, "name": "alice", "ms": 41000,
                      "color": "#fff"},
                     {"pid": bob.pid, "name": "bob", "ms": 42000, "color": "#0f0"}]
        race = A.DriveRace.query.get(A._store_replay(r, game, standings, "all in"))
        by = {c["pid"]: c for c in race.cars}
        assert by[alice.pid]["livery"]["body"] == "#17bfa8"
        assert by[alice.pid]["livery"]["rim_style"] == "mesh"
        # A guest has no garage row and still gets a car rather than a hole -
        # hashed off the name they typed, the same as their seat.
        assert by[bob.pid]["livery"]["body"] == garage.color_for("bob")

        # And it survives the repaint, because it was written down.
        A.DriveGarage.query.filter_by(user_id=u.id).first().livery_json = \
            garage.dumps({"body": "#f2c94c"})
        A.db.session.commit()
        again = A.DriveRace.query.get(race.id)
        assert {c["pid"]: c for c in again.cars}[alice.pid]["livery"]["body"] \
            == "#17bfa8"
