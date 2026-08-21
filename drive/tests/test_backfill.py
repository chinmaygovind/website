"""``tools/backfill_race_activity.py``: the driving done before anything counted it.

A backfill is a script that runs once, against a database nobody can restore, and
whose output is a set of numbers on a page that looked plausible before it ran and
looks plausible after. There is nothing to notice if it is wrong. So the two
things pinned here are the two that cannot be checked by looking: that the
arithmetic on a replay is the arithmetic, worked by hand on a synthetic one where
the answer is known; and that running it twice does not credit anybody twice.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


@pytest.fixture()
def env():
    """A fresh app + database, same shape as test_app.py's."""
    A, path = boot_app()
    yield A
    close_app(path)


@pytest.fixture()
def tool(env):
    import backfill_race_activity as B
    return B


def _straight(n, step=2.0, hz=15):
    """A car driven in a straight line: n frames, `step` units apart along x."""
    import runcheck
    return runcheck.pack_ghost([[i * step, 0.0, 0.0, 0, 0, 0, 1] for i in range(n)])


def _race(A, cars, hz=15, track="sunrise"):
    with A.app.app_context():
        import json
        r = A.DriveRace(code="ABCDEF", track=track, hz=hz, ms=1000,
                        cars_json=json.dumps(cars))
        A.db.session.add(r)
        A.db.session.commit()


def _user(A, name):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _stats(A, uid):
    with A.app.app_context():
        st = A.DriveStats.query.filter_by(user_id=uid).first()
        return (None if st is None
                else (round(st.drive_time or 0.0, 6), round(st.distance or 0.0, 6)))


# ---------------------------------------------------------------------------
# the arithmetic
# ---------------------------------------------------------------------------

def test_a_replay_measures_its_own_seconds_and_metres(tool):
    """31 frames at 15Hz is 31/15 seconds; 30 gaps of 2 units is 60 metres.

    Worked by hand rather than against the function's own output, because "the
    number this returns" is exactly the thing in question. Note the seconds are
    frames and not gaps: a frame is a slice of road, so the last one is time the
    car spent driving too - and the alternative (`(n-1)/hz`) loses a fifteenth of
    a second per car per race, which is the kind of error that is invisible in
    one race and a minute across a season.
    """
    secs, metres = tool.measure(_straight(31, step=2.0), 15)
    assert secs == pytest.approx(31 / 15.0)
    assert metres == pytest.approx(60.0, abs=1e-3)


def test_distance_is_measured_in_three_dimensions(tool):
    """Drive has loops, half-pipes and a track made of jumps, so the vertical
    component is driving rather than noise. A 3-4-5 step is 5 metres, not 3."""
    import runcheck
    g = runcheck.pack_ghost([[0, 0, 0, 0, 0, 0, 1], [3, 4, 0, 0, 0, 0, 1]])
    _, metres = tool.measure(g, 15)
    assert metres == pytest.approx(5.0, abs=1e-3)


def test_a_respawn_is_not_distance_driven(tool):
    """A jump between frames bigger than a car can travel in 1/15s is a respawn,
    and crediting it hands somebody the width of the map for falling off. The gap
    is dropped; the driving either side of it is not."""
    import runcheck
    g = runcheck.pack_ghost([[0, 0, 0, 0, 0, 0, 1],
                             [2, 0, 0, 0, 0, 0, 1],     # 2m driven
                             [900, 0, 0, 0, 0, 0, 1],   # respawned - not driven
                             [902, 0, 0, 0, 0, 0, 1]])  # 2m driven
    _, metres = tool.measure(g, 15)
    assert metres == pytest.approx(4.0, abs=1e-3)


def test_the_rate_comes_from_the_race_not_from_a_constant(tool):
    """`DriveRace.hz` is a column, so a race recorded at another rate must not be
    measured at 15. Same frames, half the rate, twice the seconds."""
    g = _straight(30)
    assert tool.measure(g, 30)[0] == pytest.approx(1.0)
    assert tool.measure(g, 15)[0] == pytest.approx(2.0)


@pytest.mark.parametrize("bad", [None, "", "not a ghost", "!!!"])
def test_an_unreadable_replay_is_nothing_rather_than_a_crash(tool, bad):
    """One corrupt row must not take the whole backfill down - it has already
    credited the accounts before it, and there is no marker yet to stop a re-run
    doing them twice."""
    assert tool.measure(bad, 15) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# who gets credited
# ---------------------------------------------------------------------------

def test_it_credits_the_account_whose_name_is_on_the_replay(env, tool):
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31, step=2.0)}])
    tool.backfill()
    secs, metres = _stats(env, uid)
    assert secs == pytest.approx(31 / 15.0)
    assert metres == pytest.approx(60.0, abs=1e-3)


def test_it_adds_to_what_is_already_there(env, tool):
    """It cannot recompute: `drive_times` keeps only the best lap per track, so
    the existing total is the only record that the other finished laps happened."""
    uid = _user(env, "chinmay")
    with env.app.app_context():
        env.db.session.add(env.DriveStats(user_id=uid, drive_time=100.0, distance=5000.0))
        env.db.session.commit()
    _race(env, [{"name": "chinmay", "ghost": _straight(31, step=2.0)}])
    tool.backfill()
    secs, metres = _stats(env, uid)
    assert secs == pytest.approx(100.0 + 31 / 15.0)
    assert metres == pytest.approx(5060.0, abs=1e-3)


def test_a_guest_is_skipped_rather_than_guessed_at(env, tool):
    """A replay carries a name and no user_id, and the `drive_players` row that
    mapped one to the other went with its room. A name with no account is a guest,
    who correctly has no stats row - inventing one would be inventing a player."""
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31)},
                {"name": "CoolBags", "ghost": _straight(31)}])
    tool.backfill()
    assert _stats(env, uid) is not None
    with env.app.app_context():
        assert env.DriveStats.query.count() == 1, "a guest was given a stats row"


def test_one_person_across_several_races_is_summed_once(env, tool):
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31, step=2.0)}])
    _race(env, [{"name": "chinmay", "ghost": _straight(31, step=2.0)}])
    tool.backfill()
    secs, metres = _stats(env, uid)
    assert secs == pytest.approx(2 * 31 / 15.0)
    assert metres == pytest.approx(120.0, abs=1e-3)


def test_it_touches_nothing_but_the_two_numbers(env, tool):
    """Asserted as a census rather than field by field, so a column added to
    `DriveStats` later cannot quietly start being written by a backfill."""
    uid = _user(env, "chinmay")
    with env.app.app_context():
        env.db.session.add(env.DriveStats(user_id=uid, elo=1234, races=7, wins=3,
                                          podiums=5, runs=11, golds=2, silvers=1,
                                          bronzes=4, authors=1))
        env.db.session.commit()

        def census():
            st = env.DriveStats.query.filter_by(user_id=uid).first()
            return {c.name: getattr(st, c.name)
                    for c in env.DriveStats.__table__.columns}
        before = census()
    _race(env, [{"name": "chinmay", "ghost": _straight(31)}])
    tool.backfill()
    with env.app.app_context():
        after = census()
    moved = {k for k in before if before[k] != after[k]}
    assert moved == {"drive_time", "distance"}, "moved %s" % sorted(moved)


# ---------------------------------------------------------------------------
# running it twice
# ---------------------------------------------------------------------------

def test_a_second_run_credits_nobody_twice(env, tool):
    """The whole reason there is a marker table. A double-applied backfill is
    worse than one that never ran, and 58 races is not a number anybody can
    eyeball afterwards."""
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31)}])
    assert tool.backfill() is True
    once = _stats(env, uid)
    assert tool.backfill() is False, "the second run was not refused"
    assert _stats(env, uid) == once


def test_a_dry_run_writes_nothing_at_all(env, tool):
    """Including the marker - a dry run that armed the refusal would mean the
    real run could never happen."""
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31)}])
    tool.backfill(dry_run=True)
    assert _stats(env, uid) is None, "a dry run created a stats row"
    assert tool.backfill() is True, "a dry run armed the marker"
    assert _stats(env, uid) is not None


def test_force_applies_it_again(env, tool):
    """The escape hatch, and it has to actually double-credit or it is not one -
    somebody reaching for `--force` has decided the first run was wrong."""
    uid = _user(env, "chinmay")
    _race(env, [{"name": "chinmay", "ghost": _straight(31, step=2.0)}])
    tool.backfill()
    tool.backfill(force=True)
    secs, _ = _stats(env, uid)
    assert secs == pytest.approx(2 * 31 / 15.0)


def test_the_marker_table_is_made_by_the_tool(env, tool):
    """`create_all` never sees it: nothing in the app reads it, so mapping it
    would put a table in `models.py` that only `tools/` touches."""
    from sqlalchemy import text
    with env.app.app_context():
        rows = env.db.session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='drive_backfill'")).all()
        assert rows == [], "the marker table exists before the tool has run"
    tool.backfill(dry_run=True)
    with env.app.app_context():
        rows = env.db.session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='drive_backfill'")).all()
        assert len(rows) == 1
