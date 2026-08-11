"""Netcode: where a rival is drawn, and who the board says is winning.

Two cars racing side by side used to be shown *each ahead of the other*, one
statement per monitor, with nothing to say which had it right. Neither half of
that was really about ping, and this file pins both halves.

- **The chase filter settled behind the car it was chasing.** `updateRemotes`
  extrapolates a rival's last packet to now and then eases towards it, and an
  exponential ease never catches a target that is itself moving. Nothing about
  it involves the network: it is worth most of a car length at MAX_SPEED on a
  perfect connection. `chaseLead` cancels it, and the test that matters here is
  the one that measures the lag **with the lead taken back out**, because that
  comparison is the whole surprise.
- **Half the round trip was never compensated.** A pose is stamped when it
  *lands*, so the age the client extrapolates over covers the trip out and not
  the trip in, and every car is drawn short by its own upstream leg. The client
  reports its measured round trip and `_snapshot` folds half of it into the age.
- **The running order compared fresh against stale.** `liveOrder` read your own
  distance live and everybody else's from a round trip ago. It comes off the
  snapshot now - every car, each projected from its own age to one instant - so
  the property worth testing is not that some particular car leads but that
  **two readers of the same snapshot agree**, which is the thing that failed.

The JS half runs the real functions, lifted out of game.js by name against a
stub, the trick `test_catchup.py` and `test_rules_js.py` use.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tuning as T

# The skip lives on the two JS fixtures rather than on the module, because half
# of this file is ordinary Python about the server and a missing optional
# package must not quietly take that half away as well - a skip reads as a pass.
GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")


def _src():
    with open(GAME_JS) as f:
        return f.read()


def _fn(name):
    """One top-level function from game.js, exactly as it ships."""
    m = re.search(r"^function %s\(.*?^\}" % re.escape(name), _src(), re.S | re.M)
    assert m, "%s is gone from game.js, or is no longer a plain function" % name
    return m.group(0)


def _const(name):
    """One top-level `const NAME = ...;` from game.js.

    Lifted rather than restated in the stub: the whole point of running the real
    function is that the numbers under it are the shipped ones.
    """
    m = re.search(r"^const %s = .*?;" % re.escape(name), _src(), re.M)
    assert m, "%s is gone from game.js" % name
    return m.group(0)


# --- a rival on a straight road, seen through the real updateRemotes -------

# Everything `updateRemotes` touches that is not the arithmetic under test. The
# view and the tow effect are called on every car every frame and do not decide
# where it is drawn, so they are shells; the phase gate is on, because a rival
# you cannot touch is drawn by the same code.
REMOTE_STUB = """
var NOW = 0;                                   // server ms, driven by the harness
function serverNow() { return NOW; }
function contactOn() { return true; }
function lampsOf() { return {}; }
var S = { remotes: new Map(), renderer: { draft() {} } };

/**
 * A rival driving flat out in a straight line, reported at `poseHz`, drawn at
 * `fps`, and compared against where it truly is.
 *
 * `upstream` is how long a pose spends in the air on the way *to* the server.
 * The server stamps arrival, so an uncompensated age puts `packetT` that much
 * later than the instant the pose actually describes - which is the bug, and
 * setting `compensated` reproduces the fix without needing a server here.
 */
function driveStraight(o) {
  const v = o.v, fps = o.fps || 60, poseHz = o.poseHz || 30;
  const upstream = o.upstream || 0;
  const r = {
    pos: new THREE.Vector3(), vel: new THREE.Vector3(v, 0, 0),
    fwd: new THREE.Vector3(), right: new THREE.Vector3(), up: new THREE.Vector3(),
    q: new THREE.Quaternion(), rq: new THREE.Quaternion(),
    px: 0, py: 0, pz: 0, prog: 0, cp: 0, flags: 0, tow: 0,
    packetT: 0, primed: false, speed: 0, slipCharge: 0, slipBoost: 0, respawnIn: 0,
    view: { group: {}, update() {}, setGhostly() {} }, draftFx: {},
  };
  S.remotes = new Map([['p1', r]]);
  const dt = 1 / fps, step = 1000 / fps, gap = 1000 / poseHz;
  let nextPose = 0, last = 0;
  for (NOW = 0; NOW < (o.secs || 4) * 1000; NOW += step) {
    if (NOW >= nextPose) {
      const sent = NOW - upstream;             // the instant this pose describes
      r.px = v * sent / 1000;
      // What the client is handed: the arrival stamp, less whatever the server
      // credited back as the upstream leg.
      r.packetT = o.compensated ? sent : NOW;
      nextPose += gap;
    }
    updateRemotes(dt);
    last = NOW;
  }
  return { drawn: r.pos.x, truth: v * last / 1000 };
}

/** The same drive with the lead removed, which is how it used to behave. */
function withoutTheLead(o) {
  const real = chaseLead;
  chaseLead = function () { return 0; };
  try { return driveStraight(o); } finally { chaseLead = real; }
}
"""


@pytest.fixture(scope="module")
def rt():
    if not jsrt.HAVE_QUICKJS:
        pytest.skip("needs the optional quickjs package")
    r = jsrt.Runtime()                    # brings THREE's Vector3/Quaternion
    r.eval(_const("REMOTE_SNAP"))
    r.eval(_const("CHASE_RATE"))
    r.eval(_fn("chaseLead"))
    r.eval(_fn("updateRemotes"))
    r.eval(REMOTE_STUB)
    return r


def _drive(rt, fn="driveStraight", **kw):
    kw.setdefault("v", T.MAX_SPEED)
    kw.setdefault("compensated", True)
    return rt.call("%s(%s)" % (fn, json.dumps(kw)))


@pytest.mark.parametrize("fps", [30, 60, 144])
def test_a_rival_going_in_a_straight_line_is_drawn_where_it_is(rt, fps):
    """The whole fix, stated as the thing it buys.

    A car reporting honestly, on a perfect connection, driving in a straight
    line: there is no reason for the screen to disagree with it by anything, and
    it used to disagree by most of a car length.
    """
    r = _drive(rt, fps=fps)
    assert r["drawn"] == pytest.approx(r["truth"], abs=0.05)


@pytest.mark.parametrize("fps", [30, 60, 144])
def test_and_it_is_pinned_against_its_own_absence(rt, fps):
    """Measured with the lead taken back out, because that is the surprise.

    A comparison against a figure in a comment would only ever pin the comment.
    What this says is that the ease *does* settle short by about a car length on
    its own, at every frame rate, with nothing else wrong - so the lead is
    doing a job and not decorating one.
    """
    was = _drive(rt, fn="withoutTheLead", fps=fps)
    short = was["truth"] - was["drawn"]
    # A band rather than a figure: the lag is `v*dt*(1-k)/k` and `k` is set by
    # the frame rate, so it runs from about 2.4 units at 30fps to about 3.0 at
    # 144. The point being pinned is the size of it, not the third decimal.
    assert 2.2 < short < 3.2, "the ease should settle a couple of units back"
    assert short > T.CAR_LEN * 0.65, "which is most of a car length"


def test_the_lag_is_a_filter_and_not_the_network(rt):
    """It is the same at 5ms of ping as at 200, which is why ping was a red
    herring: the two drivers blamed their connection for arithmetic."""
    quick = _drive(rt, fn="withoutTheLead", upstream=2)
    slow = _drive(rt, fn="withoutTheLead", upstream=100)
    assert (quick["truth"] - quick["drawn"]) == pytest.approx(
        slow["truth"] - slow["drawn"], abs=0.05)


def test_the_lead_is_bounded_by_the_filters_own_time_constant(rt):
    """A frame hitch must not turn the lead into a lunge.

    `dt*(1-k)/k` falls as `dt` grows and tends to `1/CHASE_RATE` as it shrinks,
    so the longest a car is ever thrown forward is 62ms of its own travel -
    which is the lag it is cancelling, by construction.
    """
    tau = 1.0 / rt.eval("CHASE_RATE")
    for dt in (0.001, 1 / 144.0, 1 / 60.0, 1 / 30.0, 0.1, 0.5):
        lead = rt.eval("chaseLead(%r, 1 - Math.exp(-CHASE_RATE * %r))" % (dt, dt))
        assert 0 < lead <= tau + 1e-9, "dt=%s put the lead outside (0, tau]" % dt
    # And it really is the time constant it approaches, not something near it.
    assert rt.eval("chaseLead(1e-6, 1 - Math.exp(-CHASE_RATE * 1e-6))") == \
        pytest.approx(tau, rel=1e-3)


def test_the_upstream_leg_is_the_other_half_of_it(rt):
    """A pose stamped on arrival describes a car that has already moved on.

    Uncompensated, a rival is drawn short by exactly the trip in - always
    backwards, and mirrored on the other screen, so it reads as a lead to both
    drivers the same way the filter lag did.
    """
    ms = 30
    late = _drive(rt, upstream=ms, compensated=False)
    fixed = _drive(rt, upstream=ms, compensated=True)
    assert late["truth"] - late["drawn"] == pytest.approx(
        T.MAX_SPEED * ms / 1000.0, abs=0.05)
    assert fixed["drawn"] == pytest.approx(fixed["truth"], abs=0.05)


def test_a_jump_is_still_taken_whole(rt):
    """The snap is what keeps a respawning car from streaking across the map,
    and the lead moves the target it is measured against - so it is worth
    knowing the lead did not quietly disarm it."""
    r = rt.call("""(() => {
      const car = {
        pos: new THREE.Vector3(0, 0, 0), vel: new THREE.Vector3(0, 0, 0),
        fwd: new THREE.Vector3(), right: new THREE.Vector3(), up: new THREE.Vector3(),
        q: new THREE.Quaternion(), rq: new THREE.Quaternion(),
        px: 500, py: 0, pz: 0, flags: 0, tow: 0, packetT: 0, primed: true,
        speed: 0, slipCharge: 0, slipBoost: 0, respawnIn: 0,
        view: {group: {}, update() {}, setGhostly() {}}, draftFx: {},
      };
      S.remotes = new Map([['p1', car]]); NOW = 0;
      updateRemotes(1 / 60);
      return car.pos.x;
    })()""")
    assert r == pytest.approx(500, abs=0.01), "500 units away is not an ease"


# --- one running order, off one snapshot -----------------------------------

ORDER_STUB = """
var S = { order: [], remotes: new Map(), standings: [],
          run: { bestS: 0, state: 'running', time: 0 } };
var CFG = { name: 'me', me: { pid: 'p1', color: '#fff' } };

/** Read the same snapshot as `pid`, and report the order it draws. */
function boardFor(pid, snap, live) {
  CFG.me = { pid: pid, color: '#fff' };
  CFG.name = pid;
  S.order = orderFromSnapshot(snap);
  S.run.bestS = live[pid];
  S.remotes = new Map();
  for (const other in live) {
    if (other !== pid) S.remotes.set(other, {name: other, color: '#fff',
                                             prog: live[other]});
  }
  return liveOrder().map(e => e.pid);
}
"""


@pytest.fixture(scope="module")
def board():
    if not jsrt.HAVE_QUICKJS:
        pytest.skip("needs the optional quickjs package")
    ctx = jsrt.quickjs.Context()
    ctx.eval(ORDER_STUB)
    ctx.eval(_fn("orderFromSnapshot"))
    ctx.eval(_fn("liveOrder"))
    return ctx


def _snap(cars, up=0):
    """A snapshot in the shape `_snapshot` sends: [x,y,z, q*4, v*3, prog, cp,
    flags, age, sl, upstream]."""
    out = {}
    for pid, (prog, speed, age) in cars.items():
        out[pid] = [0, 0, 0, 0, 0, 0, 1, speed, 0, 0, prog, 0, 0, age, 0,
                    up.get(pid, 0) if isinstance(up, dict) else up]
    return {"t": 1000, "cars": out}


def _board(board, pid, snap, live):
    return json.loads(board.eval("JSON.stringify(boardFor(%s, %s, %s))"
                                 % (json.dumps(pid), json.dumps(snap),
                                    json.dumps(live))))


def test_two_readers_of_one_snapshot_draw_the_same_board(board):
    """The property the whole change is for.

    Both cars are level to within a metre and each reads its own distance as of
    now - so the old board put the reader first on both screens. The order is
    settled off the snapshot now, which is the same bytes on both, so whatever
    it says it says once.
    """
    snap = _snap({"p1": (1000.4, T.MAX_SPEED, 0), "p2": (1000.0, T.MAX_SPEED, 0)})
    # Live numbers deliberately flatter whichever car is reading them, exactly
    # as a round trip of staleness used to.
    live = {"p1": 1003.0, "p2": 1003.0}
    assert _board(board, "p1", snap, live) == _board(board, "p2", snap, live)


def test_and_it_is_the_snapshot_that_decides_not_the_reader(board):
    """Not merely equal, but equal to what the server last saw."""
    snap = _snap({"p1": (1000.0, T.MAX_SPEED, 0), "p2": (1004.0, T.MAX_SPEED, 0)})
    live = {"p1": 9999.0, "p2": 0.0}      # a reader who thinks it is streets ahead
    assert _board(board, "p1", snap, live) == ["p2", "p1"]


def test_a_car_is_credited_for_the_time_its_pose_spent_travelling(board):
    """Two cars level on paper, one of them reporting 40ms ago.

    Without the projection the place goes to whichever pose landed nearest the
    tick, which is a coin flip thirty times a second and looks like the board
    twitching between two people who are not actually swapping.
    """
    snap = _snap({"p1": (1000.0, T.MAX_SPEED, 0), "p2": (1000.0, T.MAX_SPEED, 40)})
    assert _board(board, "p1", snap, {"p1": 1000.0, "p2": 1000.0}) == ["p2", "p1"]


def test_claiming_a_terrible_connection_does_not_buy_a_place(board):
    """The trap the upstream compensation sets for this function.

    Field 15 is what the *car being ranked* said about its own ping, and the
    drawing adds it to the pose age because it wants the whole journey. Adding
    it here too would make overstating your ping worth four units of projected
    road on everybody's board - a cheat invented by the fix for something else,
    landing on the one number this whole function exists to make trustworthy.
    So the projection reads field 13, which is the server's own measurement, and
    field 15 is not its business.
    """
    honest = _snap({"p1": (1000.0, T.MAX_SPEED, 0), "p2": (1002.0, T.MAX_SPEED, 0)})
    # Same road, same instant, and p1 claiming the worst connection allowed.
    liar = _snap({"p1": (1000.0, T.MAX_SPEED, 0), "p2": (1002.0, T.MAX_SPEED, 0)},
                 up={"p1": 80, "p2": 0})
    live = {"p1": 1000.0, "p2": 1002.0}
    assert _board(board, "p2", honest, live) == ["p2", "p1"]
    assert _board(board, "p2", liar, live) == ["p2", "p1"], "80ms bought a place"


def test_a_dead_heat_breaks_the_same_way_on_both_screens(board):
    """`prog` is rounded to 0.1 on the wire, so genuine ties reach the client.

    A tie broken by enumeration order is the one case this whole change exists
    for, resolved by whichever way each browser happened to walk the object.
    """
    snap = _snap({"p1": (1000.0, T.MAX_SPEED, 0), "p2": (1000.0, T.MAX_SPEED, 0)})
    live = {"p1": 1000.0, "p2": 1000.0}
    assert _board(board, "p1", snap, live) == _board(board, "p2", snap, live)


def test_a_car_already_home_still_leads_whoever_is_still_driving(board):
    """Progress orders the road; a lap time orders the result, and a finisher
    has left the road. The snapshot must not undo that."""
    snap = _snap({"p1": (100.0, T.MAX_SPEED, 0), "p2": (2000.0, T.MAX_SPEED, 0)})
    board.eval("S.standings = [{pid: 'p1', ms: 61234}];")
    board.eval("S.run.state = 'running';")
    try:
        assert _board(board, "p2", snap, {"p1": 100.0, "p2": 2000.0}) == ["p1", "p2"]
    finally:
        board.eval("S.standings = [];")


def test_with_no_snapshot_it_falls_back_to_what_it_did_before(board):
    """Solo and a replay have no snapshot and nobody to disagree with."""
    empty = {"t": 0, "cars": {}}
    assert _board(board, "p1", empty, {"p1": 500.0, "p2": 100.0}) == ["p1", "p2"]
    assert _board(board, "p1", empty, {"p1": 100.0, "p2": 500.0}) == ["p2", "p1"]


# --- the upstream leg, on the server ---------------------------------------

@pytest.fixture()
def env():
    import tempfile
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


def test_the_trip_in_is_reported_beside_the_wait_and_not_inside_it(env):
    """A pose is stamped when it lands, and describes a car that has moved on.

    The client adds the two to extrapolate, so leaving the trip in out entirely
    draws every car short by its own upstream leg on every screen but its own -
    always backwards, and mirrored, so both drivers see a lead. They stay
    separate on the wire because the running order may only use the half the
    server measured: `orderFromSnapshot`, and the test above it.
    """
    A = env
    r = A._room("TEST")
    c = A._car(r, "p1")
    c["ts"] = A._now_ms()
    c["up"] = 30.0
    row = A._snapshot(r)["cars"]["p1"]
    assert row[13] <= 4, "field 13 is the wait since arrival, and nothing else"
    assert row[15] == 30


def test_a_car_that_never_reported_a_trip_is_credited_with_none(env):
    """The field is absent on the first ping and from anything that does not
    send it at all, and the answer there is the old behaviour rather than a
    guess."""
    A = env
    r = A._room("TEST")
    c = A._car(r, "p1")
    c["ts"] = A._now_ms()
    assert c["up"] == 0.0
    row = A._snapshot(r)["cars"]["p1"]
    assert row[13] <= 4 and row[15] == 0


@pytest.mark.parametrize("rtt,want", [
    (60.0, 30.0),                                   # the ordinary case: halved
    (0.0, 0.0),
    (10 ** 9, 80.0),                                # a liar, meeting the cap
    (2 * 80.0 + 2, 80.0),                           # just over it
])
def test_the_reported_trip_is_halved_and_capped(env, rtt, want):
    """It arrives from the thing it flatters, so it is bounded.

    All it can buy is being drawn a little further up the road on screens that
    are not yours: it reaches neither racecheck, nor `prog`, nor the standings,
    nor the result. At the cap that is about four units, which is less than the
    error every honest car was carrying while none of this was compensated.
    """
    A = env
    c = A._car(A._room("TEST"), "p1")
    A._note_upstream(c, rtt)
    assert c["up"] == want
    assert c["up"] <= A.UPSTREAM_CAP_MS


@pytest.mark.parametrize("bad", [None, "soon", float("nan"), -50.0, [1]])
def test_nonsense_leaves_it_alone(env, bad):
    A = env
    c = A._car(A._room("TEST"), "p1")
    A._note_upstream(c, 40.0)
    A._note_upstream(c, bad)
    assert c["up"] == 20.0


def test_it_keeps_the_shortest_trip_it_saw(env):
    """The pings land while the page is still loading, so the first is the worst
    measurement of the session and must not set the number for the rest of it.
    A minimum is also the one direction a client cannot walk this upwards in."""
    A = env
    c = A._car(A._room("TEST"), "p1")
    for rtt in (400.0, 120.0, 64.0, 90.0, 300.0):
        A._note_upstream(c, rtt)
    assert c["up"] == 32.0


def test_the_cap_is_worth_less_than_the_bug_it_replaces(env):
    """The justification for taking the number from the client at all.

    The most a liar gains has to be smaller than what every honest driver was
    already losing, or this would be handing out more than it gives back.
    """
    A = env
    bought = A.UPSTREAM_CAP_MS / 1000.0 * T.MAX_SPEED
    assert bought < T.CAR_LEN * 1.5

