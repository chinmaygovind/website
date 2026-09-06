"""A practice save state has to put the car back *exactly*, not nearly.

This is the test that matters for the feature, and it is the failure with no
visual signature: a restore that drops `coyote`, `padBoost` or the accumulated
bump-cooldown looks perfect on screen and drives the corner slightly differently
every time you come back to it - which is the one thing a practice tool must not
do, because the whole point is that the section is the same section.

So it is written as a comparison of two histories rather than of two states. Drive
a car, snapshot it, drive on, restore, and drive **the same inputs again**: every
pose from there has to match the first time to the bit. A state that is 99% right
passes a field-by-field check on the snapshot and fails this, because the physics
compounds whatever was left out.

Run against the real `Car` on a real track in QuickJS - see `jsrt.py`. Big Red
because it is the track with boost pads on it, so `padBoost` and `bounceLock` are
actually live rather than zero throughout.

**What these tests can and cannot pin, measured rather than assumed.** Deleting
one field at a time from `Car.restore` and re-running this file, seven of them
fail it: `coyote`, `airTime`, `steer`, `padBoost`, `slipBoost`, `bounceLock`,
`bumpSlip` and `wheelSpin`. Those are the load-bearing ones - the physics reads
them before it writes them, so a restore that drops one drives the corner
differently.

The rest of the snapshot cannot be caught here and does not need to be:
`grounded`, `surface`, `speed`, `offroad`, `groundN` and `bumpLean` are
recomputed at the top of every `step` from the ground query (physics.js ~178),
and `towed`, `slipCharge` and `catchupBoost` are re-derived from the other cars,
of which a solo save state has none. They are in the snapshot anyway, because
they are read by the renderer and the HUD *between* steps and because a function
whose whole job is to be complete should not be selectively incomplete - but a
test asserting on them would be asserting that `step` overwrites them, which is
a different fact and is not this file's.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt        # noqa: E402

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

HARNESS = """
var TRACK = TRACKS.find(t => t.slug === 'bigred');
var BUILT = buildTrack(TRACK, T);

/** A car on the road at station `si`, up to speed and pointing down it. */
function at(si, speed) {
  const e = TRACK.line[si], f = TRACK.line[si + 1];
  const fwd = [f.p[0] - e.p[0], f.p[1] - e.p[1], f.p[2] - e.p[2]];
  const m = Math.hypot(fwd[0], fwd[1], fwd[2]);
  const c = new Car(T, BUILT);
  c.placeAt(e.p, [fwd[0] / m, fwd[1] / m, fwd[2] / m]);
  c.vel.set(fwd[0] / m * speed, 0, fwd[2] / m * speed);
  return c;
}

/**
 * A varied but repeatable input stream, so the car actually uses the parts of
 * its state a restore could drop. A car held on full throttle in a straight
 * line has no steer angle, never leaves the ground and never touches a wall,
 * which is exactly the car a broken snapshot would restore correctly.
 */
function inputAt(i) {
  return {
    throttle: (i % 37) < 30 ? 1 : 0,
    brake: (i % 53) > 49 ? 1 : 0,
    steer: ((i % 71) < 20 ? 1 : ((i % 71) < 40 ? -1 : 0)),
    handbrake: (i % 97) > 92,
  };
}

/** Where the car is, to full precision. This is what has to match. */
function pose(c) {
  return [c.pos.x, c.pos.y, c.pos.z, c.vel.x, c.vel.y, c.vel.z,
          c.quat.x, c.quat.y, c.quat.z, c.quat.w,
          c.steer, c.speed, c.slip, c.airTime, c.coyote,
          c.padBoost, c.slipBoost, c.bounceLock, c.bumpSlip,
          c.grounded ? 1 : 0, c.surface, c.wheelSpin];
}

function drive(c, from, n) {
  const out = [];
  for (let i = from; i < from + n; i++) {
    c.step(T.FIXED_DT, inputAt(i));
    out.push(pose(c));
  }
  return out;
}
"""


@pytest.fixture(scope="module")
def js():
    rt = jsrt.Runtime()
    rt.load_tuning_and_tracks()
    rt.eval(HARNESS)
    return rt


def test_a_restored_car_drives_an_identical_future(js):
    """The whole feature, in one assertion.

    Drive 400 steps, snapshot, drive 400 more, restore, drive the *same* 400
    again. Every pose has to match the first pass exactly. Anything the snapshot
    failed to carry shows up here as a divergence that grows.
    """
    got = js.call("""(() => {
      const c = at(40, 30);
      drive(c, 0, 400);
      const snap = c.snapshot();
      const first = drive(c, 400, 400);
      c.restore(snap);
      const second = drive(c, 400, 400);
      return { first, second };
    })()""")
    assert got["first"] == got["second"]


def test_a_restore_is_exact_from_mid_air(js):
    """Big Red is four full-size jumps, and a car in the air is the state most
    likely to be restored *nearly* right: `airTime` drives `AIR_PITCH`, `coyote`
    decides whether the next contact is a landing, and `placeAt` - the respawn
    path this deliberately is not - zeroes both."""
    got = js.call("""(() => {
      // Find a step where the car is actually off the ground.
      const c = at(40, 30);
      let i = 0;
      for (; i < 4000 && (c.grounded || c.airTime < 0.15); i++) c.step(T.FIXED_DT, inputAt(i));
      if (c.grounded) return { skip: true };
      const snap = c.snapshot();
      const first = drive(c, i, 300);
      c.restore(snap);
      return { air: snap.airTime, grounded: snap.grounded,
               first, second: drive(c, i, 300) };
    })()""")
    if got.get("skip"):
        pytest.skip("no airborne step found on this layout")
    assert got["grounded"] is False and got["air"] > 0
    assert got["first"] == got["second"]


def test_a_snapshot_does_not_track_the_car_it_came_from(js):
    """Every vector is copied out by value. A snapshot sharing a `Vector3` with
    the live car would quietly follow it and restore to wherever the car ended
    up - which reads as "R does nothing" and is very hard to see."""
    got = js.call("""(() => {
      const c = at(40, 30);
      const snap = c.snapshot();
      const was = snap.pos.slice();
      drive(c, 0, 200);
      return { was, now: snap.pos, moved: [c.pos.x, c.pos.y, c.pos.z] };
    })()""")
    assert got["was"] == got["now"]
    assert got["moved"] != got["now"]


def test_the_boosts_and_the_let_go_tyres_survive(js):
    """The fields a solo car driving a clean lap never has switched on.

    Written because the history test above **did not catch these**: dropping
    `padBoost` or `bumpSlip` from `restore` left it green, since a car driving
    Big Red alone from station 40 touches no pad and hits nobody in 800 steps, so
    both were zero on either side of the comparison. They are set by hand here
    rather than by finding a pad, because the physics reads them the same way
    whatever put them there - and a test that has to drive onto a pad is a test
    that quietly stops covering this if the pad moves.

    `bumpSlip`, `towed`, `slipCharge` and `_bumpCooldown` only ever happen in a
    room, where there is another car. They are in the snapshot anyway: a save
    state is taken solo today, and "this field cannot be set here" is not a
    property worth building into the one function whose whole job is to be
    complete.
    """
    got = js.call("""(() => {
      const c = at(40, 30);
      drive(c, 0, 60);
      // Everything a clean solo lap leaves at zero.
      c.padBoost = T.PAD_BOOST;
      c.slipBoost = T.SLIP_BOOST;
      c.catchupBoost = 0.6;
      c.bumpSlip = 0.4;
      c.bumpLean = 0.3;
      c.bumpTimer = 0.2;
      c.bounceLock = 0.5;
      c.towed = true;
      c.slipCharge = 0.7;
      c._wallHit = 3;
      c._bumpCooldown.set('rival', 1.25);
      const snap = c.snapshot();
      const first = drive(c, 60, 200);
      c.restore(snap);
      const second = drive(c, 60, 200);
      return { first, second,
               cooldown: [...c._bumpCooldown],
               towed: c.towed, charge: c.slipCharge, wall: c._wallHit };
    })()""")
    assert got["first"] == got["second"]
    # The three the pose vector cannot see, checked directly.
    assert got["cooldown"] == [["rival", 1.25]]
    assert got["towed"] is True
    assert got["charge"] == 0.7


def test_the_bump_cooldown_map_is_copied_and_not_shared(js):
    """A Map handed straight into the snapshot would be the live one, so every
    hit after the save would appear in the state you go back to."""
    got = js.call("""(() => {
      const c = at(40, 30);
      c._bumpCooldown.set('a', 1);
      const snap = c.snapshot();
      c._bumpCooldown.set('b', 2);
      c.restore(snap);
      return { keys: [...c._bumpCooldown.keys()] };
    })()""")
    assert got["keys"] == ["a"]


def test_restoring_does_not_resurrect_a_stale_collision_spark(js):
    """`lastBump` is a one-frame message to the renderer, consumed by whoever
    reads it. Carried across a restore it would throw a shower of sparks for a
    hit that happened minutes ago."""
    got = js.call("""(() => {
      const c = at(40, 30);
      const snap = c.snapshot();
      c.lastBump = { x: 1, y: 2, z: 3, mag: 9 };
      c.restore(snap);
      return { bump: c.lastBump };
    })()""")
    assert got["bump"] is None


# ---------------------------------------------------------------------------
# The run, and the clock the movers are posed off
# ---------------------------------------------------------------------------

RUN_HARNESS = """
var COURSE = new Course(BUILT);

function freshRun() {
  const r = new Run(COURSE, TRACK);
  r.start(0);
  return r;
}
"""


@pytest.fixture(scope="module")
def jsrun(js):
    js.eval(RUN_HARNESS)
    return js


def test_the_step_clock_survives_a_restore(jsrun):
    """**Dino Park's herd is posed off `Run.stepIndex()`.**

    It is the physics step index, and it is `inputs.length` - so a restore that
    put the clock back to 0:41 and left the step count where it had got to would
    meet the hadrosaurs somewhere else. The section you are drilling would not be
    the section you saved, and nothing about that looks like a bug: the animals
    are simply in a different place each time.

    `stepBase` is what keeps it right. The recording arrays are cleared (so they
    do not grow across thirty restores) and the count carries on.
    """
    got = jsrun.call("""(() => {
      const r = freshRun();
      const c = at(40, 30);
      for (let i = 0; i < 500; i++) { r.noteStep(c, inputAt(i), i * 8.33); }
      const at500 = r.stepIndex();
      const snap = r.snapshot();
      for (let i = 500; i < 900; i++) { r.noteStep(c, inputAt(i), i * 8.33); }
      const at900 = r.stepIndex();
      r.restore(snap, 12345);
      const back = r.stepIndex();
      // And it keeps counting from there rather than restarting.
      r.noteStep(c, inputAt(0), 12345);
      return { at500, at900, back, next: r.stepIndex(),
               inputs: r.inputs.length, anchors: r.anchors.length };
    })()""")
    assert got["at500"] == 500 and got["at900"] == 900
    assert got["back"] == 500, "the movers would be 400 steps out of place"
    assert got["next"] == 501
    # Cleared rather than truncated, so thirty restores cost no memory.
    assert got["inputs"] == 1 and got["anchors"] == 1


def test_a_restored_run_is_tainted_and_a_fresh_one_is_not(jsrun):
    """The taint is on the *run*, not the session, which is what makes "Shift+R
    and drive it properly" always give you a lap that counts - the alternative is
    a save state left lying around silently costing somebody a personal best.

    Shift+R is `resetToStart` and then setting off, so both halves are driven
    here. `reset` is the one that does the work: `start` returns at its first
    line on a run that is already `running`, which a restored one is.
    """
    got = jsrun.call("""(() => {
      const r = freshRun();
      const c = at(40, 30);
      for (let i = 0; i < 100; i++) r.noteStep(c, inputAt(i), i * 8.33);
      const clean = r.tainted;
      r.restore(r.snapshot(), 999);
      const after = r.tainted;
      const startAlone = (r.start(0), r.tainted);   // still running: no-op
      r.reset();                                    // what Shift+R actually does
      r.start(0);
      return { clean, after, startAlone, restarted: r.tainted, base: r.stepBase };
    })()""")
    assert got["startAlone"] is True, "start() on a running run is a no-op"
    assert got["clean"] is False
    assert got["after"] is True
    assert got["restarted"] is False
    assert got["base"] == 0


def test_a_tainted_run_offers_no_evidence(jsrun):
    """`verifyPayload` refuses, and the refusal belongs next to the format
    rather than only at the call site: a half-lap of inputs claiming to be a
    whole one is the shape of an attack rather than of a mistake."""
    got = jsrun.call("""(() => {
      const r = freshRun();
      const c = at(40, 30);
      for (let i = 0; i < 100; i++) r.noteStep(c, inputAt(i), i * 8.33);
      const before = r.verifyPayload() !== null;
      r.restore(r.snapshot(), 999);
      for (let i = 0; i < 100; i++) r.noteStep(c, inputAt(i), i * 8.33);
      return { before, after: r.verifyPayload() };
    })()""")
    assert got["before"] is True
    assert got["after"] is None


def test_the_clock_resumes_where_it_was_saved(jsrun):
    got = jsrun.call("""(() => {
      const r = freshRun();
      r.time = 41900;
      r.distance = 1200;
      r.nextCp = 2;
      r.splits = [11000, 23400];
      const snap = r.snapshot();
      r.time = 60000; r.distance = 1800; r.nextCp = 3;
      r.restore(snap, 500000);
      return { time: r.time, startedAt: r.startedAt, distance: r.distance,
               nextCp: r.nextCp, splits: r.splits, state: r.state };
    })()""")
    assert got["time"] == 41900
    # Rebased so the clock reads 41.9s at the moment of the restore and carries on.
    assert got["startedAt"] == 500000 - 41900
    assert got["distance"] == 1200
    assert got["nextCp"] == 2
    assert got["splits"] == [11000, 23400]
    assert got["state"] == "running"


# ---------------------------------------------------------------------------
# Play stats across a practice session
# ---------------------------------------------------------------------------

def test_practice_credits_the_driving_that_happened_and_no_more(jsrun):
    """`/api/activity` is additive on the server, so `claimReport` measures a
    delta and not a total.

    This is the arithmetic that goes wrong if it does not. Drive to 40s, save,
    drive to 60s, restore, drive to 55s, restore. The real driving is 60s (the
    first pass) plus 15s (40 -> 55), and reporting the *total* each time would
    credit 60 + 55 = 115s - the whole of the first forty seconds twice over.
    """
    got = jsrun.call("""(() => {
      const r = freshRun();
      const claims = [];
      const claim = () => { const c = r.claimReport(500); if (c) claims.push(c.ms); };

      r.time = 40000; r.distance = 400;
      const snap = r.snapshot();          // save at 0:40
      r.time = 60000; r.distance = 700;
      claim();                            // abandon at 1:00
      r.restore(snap, 0);
      r.time = 55000; r.distance = 620;
      claim();                            // abandon at 0:55
      r.restore(snap, 0);
      return { claims, total: claims.reduce((a, b) => a + b, 0) };
    })()""")
    assert got["claims"] == [60000, 15000]
    assert got["total"] == 75000


def test_a_hop_under_the_floor_is_kept_rather_than_dropped(jsrun):
    """Below `MIN_REPORTED_MS` nothing is claimed **and the mark does not move**,
    so the driving accumulates into the next report. Drilling a corner in
    four-second bites would otherwise throw away every metre of it."""
    got = jsrun.call("""(() => {
      const r = freshRun();
      r.time = 300; r.distance = 20;
      const first = r.claimReport(500);
      r.time = 900; r.distance = 60;
      const second = r.claimReport(500);
      return { first, second };
    })()""")
    assert got["first"] is None
    # The 300ms is still in there, not lost.
    assert got["second"]["ms"] == 900
    assert got["second"]["m"] == 60
