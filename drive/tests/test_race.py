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


def test_pole_side_alternates_between_races(env):
    """Which column is the inside line never changes, so who gets it must."""
    A = env
    sides = []
    r = _room(A, phase="free")
    for _ in range(4):
        r["flip"] = bool(r["races_run"] % 2)
        r["races_run"] += 1
        sides.append(r["flip"])
    assert sides == [False, True, False, True]


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
