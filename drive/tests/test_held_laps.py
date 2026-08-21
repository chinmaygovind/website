"""What `/api/run` does with a lap that is quick enough to need checking.

`test_verify.py` is about whether the re-simulation gets the right answer. This
is about what the site does with that answer: which laps are held back, what the
board shows while one is being checked, what happens when the verdict arrives,
and what happens to a lap that arrives with nothing to check.

The rule the whole file turns on: **a held lap is not written into
`drive_times`**. `drive_times` keeps one row per player per track and a better
run overwrites it wholesale, so a lap stored now and disowned later takes the
time it replaced with it. Holding it in `drive_run_checks` instead means the
board, the record, the ghost and everybody's rank are untouched by a lap nobody
has checked - with no read path anywhere having to remember to exclude one.
"""

import json as json_mod
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import runcheck

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")


@pytest.fixture()
def env():
    """A fresh app + database, with the anti-cheat switched on.

    `_spawn_verifier` is replaced by a recorder. In production it starts a
    process and walks away; here the tests run the verifier themselves, in this
    process, so that a check is a thing that happens at a known moment rather
    than a race with the test.
    """
    A, path = boot_app(verify="1")
    A.spawned = []
    A._spawn_verifier = lambda *a: (A.spawned.append(a), True)[1]
    yield A
    close_app(path, verify="1")


@pytest.fixture(scope="module")
def laps():
    """One honest lap and one driven by a retuned car, both of Sunrise.

    Module scoped: each is a second of real simulation, and every test here
    wants the same two.
    """
    from test_verify import drive, retuned

    rt = jsrt.Runtime()
    rt.load_tuning_and_tracks()
    rt.eval("var FIELDS = %s;" %
            json_mod.dumps([runcheck.input_fields(b) for b in range(256)]))
    with open(os.path.join(os.path.dirname(__file__), "driver.js")) as f:
        rt.eval(f.read())
    honest = drive(rt, "sunrise", fps=60)
    with retuned(rt, "ACCEL", 1.4):
        cheat = drive(rt, "sunrise", fps=60)
    return {"honest": honest, "cheat": cheat}


def payload(lap, **over):
    """The lap, as the browser posts it."""
    d = {"track": "sunrise", "time_ms": lap["time"], "splits": lap["splits"],
         "ghost": lap["ghost"], "distance": 500, "verify": lap["verify"]}
    d.update(over)
    return d


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


def _verify_everything(A):
    """Run the queue for real, in this process. What the subprocess would do."""
    import verify
    with A.app.app_context():
        rows = A.DriveRunCheck.query.filter_by(status="pending").all()
        v = verify.Verifier()
        import tracks
        for row in rows:
            verify.run_check_row(row, tracks, verifier=v)
        A.db.session.commit()
        return [(r.status, r.reason) for r in rows]


def _board(A, slug="sunrise"):
    """Every time on a track's public board, quickest first."""
    with A.app.app_context():
        return [r.time_ms for r in A.DriveTime.query.filter_by(track=slug)
                .order_by(A.DriveTime.time_ms.asc()).all()]


# ---------------------------------------------------------------------------
# Holding a lap back
# ---------------------------------------------------------------------------

def test_a_lap_near_the_top_is_held_out_of_the_board_until_it_is_checked(env, laps):
    c = env.app.test_client()
    _login(c, _user(env))
    d = c.post("/api/run", json=payload(laps["honest"])).get_json()

    assert d["ok"] and d["pending"] and not d["improved"]
    assert d["note"], "the driver has to be told why their lap is not up yet"
    assert _board(env) == [], "a lap nobody has checked went on the board"
    with env.app.app_context():
        row = env.DriveRunCheck.query.one()
        assert row.status == "pending" and row.time_ms == laps["honest"]["time"]
    assert env.spawned == [("--check", "1")], "nothing was asked to check it"


def test_a_checked_lap_reaches_the_board_the_next_time_anyone_reads_it(env, laps):
    """The verdict is written by another process, so somebody has to act on it.

    That somebody is whoever loads a page with a record on it - there is no
    timer anywhere in Drive, and adding one to a single eventlet worker to
    service a queue that is empty 99.9% of the time would be the wrong trade.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=payload(laps["honest"]))
    assert _verify_everything(env) == [("pass", "")]
    assert _board(env) == [], "not applied until something reads the board"

    c.get("/leaderboard")
    assert _board(env) == [laps["honest"]["time"]]
    with env.app.app_context():
        row = env.DriveRunCheck.query.one()
        assert row.applied_at is not None and row.drive_time_id is not None
        # and the medal came with it, exactly as a directly stored lap's would
        t = env.DriveTime.query.get(row.drive_time_id)
        assert t.medal == runcheck.medal_for(
            __import__("tracks").get("sunrise"), row.time_ms)
        # The counter agrees with the medal, whichever way that falls.
        #
        # **This used to assert `>= 1`, and it stopped being true when the medal
        # times were cut from the board.** `driver.js` laps Sunrise in 20.05s;
        # every one of the thirteen humans on that board is between 16.27 and
        # 17.1, so bronze at 18.2 is comfortably inside human range and outside
        # the autopilot's - it is a crude driver, not evidence of a bad standard.
        # Asserting agreement instead is the stronger test anyway: it is the one
        # that catches a medal written to the row without the counter moving,
        # which is the bug this line was here for.
        st = env.DriveStats.query.filter_by(user_id=t.user_id).one()
        counted = (st.golds or 0) + (st.silvers or 0) + (st.bronzes or 0)
        assert counted == (1 if t.medal else 0), (
            "medal %r on the row but %d counted" % (t.medal, counted))


def test_a_lap_the_car_could_not_have_driven_never_reaches_the_board(env, laps):
    """End to end, through the real verifier, with the real cheat.

    The lap is a well-formed replay that `runcheck.validate` accepts - that is
    the whole point of it - and it is refused anyway, which is the thing this
    entire feature exists to do.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    d = c.post("/api/run", json=payload(laps["cheat"])).get_json()
    assert d["pending"], "the cheated lap was not even queued"

    status, reason = _verify_everything(env)[0]
    assert status == "fail", reason
    c.get("/leaderboard")
    assert _board(env) == [], "a cheated lap reached the board"
    with env.app.app_context():
        assert env.DriveRunCheck.query.one().applied_at is not None


def test_the_attempt_still_counts_while_the_lap_is_being_checked(env, laps):
    """A held lap is not a lap that did not happen.

    Minutes played and kilometres driven count every run, not the ones that go
    on the board - so they are added here the same as anywhere else, and a
    driver whose record is in the queue does not lose the drive as well.
    """
    c = env.app.test_client()
    uid = _user(env)
    _login(c, uid)
    c.post("/api/run", json=payload(laps["honest"]))
    with env.app.app_context():
        st = env.DriveStats.query.filter_by(user_id=uid).one()
        assert st.runs == 1
        assert st.drive_time > 0 and st.distance > 0


def test_a_lap_that_would_not_place_is_stored_the_way_it_always_was(env, laps):
    """Only the top of the board is worth seconds of CPU.

    The record is rank 1, so the record is always checked, and times only ever
    improve - a run outside the top N at submission can never rise into it.
    """
    c = env.app.test_client()
    with env.app.app_context():
        for i in range(runcheck.VERIFY_TOP_N):
            u = env.User(username="fast%d" % i, email="f%d@example.com" % i)
            env.db.session.add(u)
            env.db.session.flush()
            env.db.session.add(env.DriveTime(user_id=u.id, track="sunrise",
                                             time_ms=1000 + i))
        env.db.session.commit()

    _login(c, _user(env))
    d = c.post("/api/run", json=payload(laps["honest"])).get_json()
    assert d["stored"] and d["improved"] and not d.get("pending")
    assert laps["honest"]["time"] in _board(env)
    assert env.spawned == []


# ---------------------------------------------------------------------------
# A lap with nothing to check
# ---------------------------------------------------------------------------

def test_a_quick_lap_with_no_evidence_is_refused_and_told_why(env, laps):
    """Otherwise leaving the input stream out is the cheat.

    The honest cause is a page that was open across the deploy that added the
    recording, and it is fixed by reloading - which is what the message says.
    `pending.js` drops a 4xx, which is right: a lap it has been holding since
    before any of this existed can never grow an input stream.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    r = c.post("/api/run", json=payload(laps["honest"], verify=None))
    assert r.status_code == 400
    assert "reload" in r.get_json()["error"].lower()
    assert _board(env) == []
    with env.app.app_context():
        assert env.DriveRunCheck.query.count() == 0


@pytest.mark.parametrize("bad", [
    {"i": [1, 4], "a": "not a list"},
    {"i": "not a stream", "a": [[0] * 12]},
    {"i": [1, 4], "a": [[0] * 11]},                    # a short anchor
    {"i": [1, 4], "a": [[float("nan")] * 12]},
    {"i": [1, 4], "a": [[1e12] * 12]},
])
def test_evidence_that_is_not_evidence_is_refused_before_it_is_stored(env, laps, bad):
    """The shape check is on the request path, so it has to be cheap and total.

    Every one of these would otherwise reach `pack_verify`, which is a zlib
    compression of whatever it was handed, or the verifier, which would fall
    over on it and file an `error` nobody looks at.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    assert c.post("/api/run", json=payload(laps["honest"], verify=bad)).status_code == 400


def test_nothing_is_held_when_nothing_can_check_it(env, laps, monkeypatch):
    """A lap that would wait for ever is worse than one that was never checked.

    If `quickjs` is missing - a box mid-deploy, a fresh checkout - `/api/run`
    goes back to storing laps directly rather than filling a queue nobody is
    serving. Switchable by hand with `DRIVE_VERIFY` for the same reason.
    """
    monkeypatch.setenv("DRIVE_VERIFY", "0")
    c = env.app.test_client()
    _login(c, _user(env))
    d = c.post("/api/run", json=payload(laps["honest"], verify=None)).get_json()
    assert d["stored"] and d["improved"]
    assert _board(env) == [laps["honest"]["time"]]


# ---------------------------------------------------------------------------
# The queue looking after itself
# ---------------------------------------------------------------------------

def test_the_slower_of_two_checked_laps_does_not_overwrite_the_quicker(env, laps):
    """Two laps can be in the queue at once, and they can come back in any order.

    So the improvement is re-tested when the verdict is applied rather than when
    the lap was driven - otherwise a queue that settles out of order leaves the
    slower of your two laps as your personal best.
    """
    c = env.app.test_client()
    _login(c, _user(env))
    quick, slow = laps["honest"], dict(laps["honest"])
    c.post("/api/run", json=payload(quick))
    c.post("/api/run", json=payload(slow, time_ms=quick["time"] + 900,
                                    ghost=quick["ghost"] + quick["ghost"][-1:] * 14))
    with env.app.app_context():
        assert env.DriveRunCheck.query.count() == 2
        # Hand-marked rather than verified: the second lap is a doctored replay
        # and would rightly fail, and what is under test here is the order the
        # verdicts are applied in.
        for row in env.DriveRunCheck.query.all():
            row.status = "pass"
        env.db.session.commit()
    c.get("/leaderboard")
    assert _board(env) == [quick["time"]]


def test_a_check_nobody_answered_is_started_again(env, laps):
    """The process doing it can die - a box reboot, an OOM, a bad deploy.

    Nothing would ever notice, because the row it was going to write is the only
    thing that knows it was running. So a check still pending long after it was
    queued is handed to a fresh process the next time anybody reads a board.
    """
    from datetime import datetime, timedelta
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/api/run", json=payload(laps["honest"]))
    env.spawned.clear()

    env._last_sweep = None                  # "five minutes have gone by"
    c.get("/leaderboard")
    assert env.spawned == [], "a check that was queued a moment ago is not stale"

    with env.app.app_context():
        row = env.DriveRunCheck.query.one()
        row.queued_at = datetime.utcnow() - timedelta(hours=2)
        env.db.session.commit()

    c.get("/leaderboard")
    assert env.spawned == [], "the sweep is rate limited, not run on every page"

    env._last_sweep = None
    c.get("/leaderboard")
    assert env.spawned == [("--pending", "--again")]


def test_the_owner_can_see_that_their_lap_is_being_checked(env, laps):
    """The difference between "my lap is queued" and "my lap vanished"."""
    c = env.app.test_client()
    uid = _user(env)
    _login(c, uid)
    c.post("/api/run", json=payload(laps["honest"]))

    mine = c.get("/account").get_data(as_text=True)
    assert "Being checked" in mine

    other = env.app.test_client()
    _login(other, _user(env, name="somebodyelse"))
    theirs = other.get("/account/chinmay").get_data(as_text=True)
    assert "Being checked" not in theirs, (
        "an unchecked lap of somebody else's is a claim, not news")
