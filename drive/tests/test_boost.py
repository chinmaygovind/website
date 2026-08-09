"""Boost pads: what arms one, what it is worth, and what it refuses to stack with.

Three things are under test and they are in three different files, which is why
this file is in three parts.

The **rule** - a pad is a surface, touching it arms a fixed number of seconds of
extra engine, and that engine is a multiplier on the throttle term - is in
physics.js, and it is run here for real in QuickJS on a real track. Unlike the
slipstream, this one cannot be tested on a car floating in a vacuum: a pad is
noticed by the ground query, so the car has to actually be on a road.

The **authoring** - that `Builder.boost` flags the stations it lays and that
those stations and only those come out of `buildTrack` as `KIND.BOOST` - is the
join between tracks.py and trackmesh.js, and a drift there is a pad you can see
and cannot use, or one you can use and cannot see.

The **medals** - that laptime.py knows a pad exists - is the part that failed
silently and is the reason this file's last group is written the way it is. See
`test_a_boosted_station_may_exceed_the_plain_top_speed`.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import laptime
import tracks as tracks_mod
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                               reason="needs the optional quickjs package")

# The pad's own top speed and the two it is not allowed to be multiplied by.
PAD_TOP = T.MAX_SPEED * math.sqrt(T.PAD_ACCEL_MULT)
CLAMP = T.MAX_SPEED * 1.7

HARNESS = """
// Big Red is the only track in the pool with pads on it, which is the point:
// these tests read the real thing rather than a fixture that could be right
// while the track is wrong.
var TRACK = TRACKS.find(t => t.slug === 'bigred');
var BUILT = buildTrack(TRACK, T);

// A car on the road at a given station, up to speed and pointing down it.
// `si` is an index into the ribbon, so a test can say "on the first pad" or
// "twenty units before it" and mean it.
function at(si, speed) {
  const e = TRACK.line[si], f = TRACK.line[si + 1];
  const fwd = [f.p[0] - e.p[0], f.p[1] - e.p[1], f.p[2] - e.p[2]];
  const m = Math.hypot(fwd[0], fwd[1], fwd[2]);
  const c = new Car(T, BUILT);
  c.placeAt(e.p, [fwd[0] / m, fwd[1] / m, fwd[2] / m]);
  c.vel.set(fwd[0] / m * speed, 0, fwd[2] / m * speed);
  c.fired = 0;
  c.onBoostPad = () => c.fired++;
  return c;
}

function firstPad() {
  return TRACK.line.findIndex(e => e.bp);
}

// Drive for `secs` on full throttle and report what happened.
function run(c, secs, inp) {
  const dt = T.FIXED_DT, n = Math.round(secs / dt);
  let peak = 0;
  for (let i = 0; i < n; i++) {
    c.step(dt, inp || { throttle: 1 });
    peak = Math.max(peak, c.vel.length());
  }
  return { fired: c.fired, pad: c.padBoost, speed: c.vel.length(), peak,
           surface: c.surface };
}

// Acceleration over one step at a given speed and station, with whichever of
// the three kinds of help the caller asks for switched on.
//
// One step rather than a long run, because a car held on full throttle for
// seconds on end steers nowhere and drives off the first corner - which is a
// fact about Big Red rather than about boost pads. One step measures the term
// under test and nothing else, and the difference between two of them at the
// same place and the same speed cancels drag, slope and the surface entirely.
//
// This runs the **real `Car.step`**. An earlier version of this file computed
// the engine multiplier from a copy of the expression in physics.js, which is
// worse than no test: changing the rule there to a product left every
// assertion here passing, because they were checking the copy against itself.
//
// `si` must be **ordinary road**, and that is not a detail either: standing on
// a pad re-arms `padBoost` at the top of every step, before the engine term
// reads it, so a car measured there is boosted whatever the caller asked for.
// Measuring on the pad reported a gain of exactly zero.
function accelWith(si, speed, opts) {
  const c = at(si, speed);
  c.step(T.FIXED_DT, { throttle: 1 });      // settle the ground query
  if (c.surface === KIND.BOOST) throw new Error('accelWith needs ordinary road');
  const before = c.vel.length();
  c.padBoost = opts.pad ? T.PAD_BOOST : 0;
  c.slipBoost = opts.slip ? T.SLIP_BOOST : 0;
  c.catchupBoost = opts.catchup || 0;
  c.step(T.FIXED_DT, { throttle: 1 });
  return (c.vel.length() - before) / T.FIXED_DT;
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


@pytest.fixture(scope="module")
def pad_i(rt):
    """The index of the first boost-pad station on Big Red."""
    return rt.call("firstPad()")


@pytest.fixture(scope="module")
def road_i(rt, pad_i):
    """A station of ordinary straight road, just before that pad."""
    return pad_i - 6


# ---------------------------------------------------------------------------
# What arms a pad, and for how long
# ---------------------------------------------------------------------------

def test_the_track_actually_has_pads_on_it(rt, pad_i):
    """Everything below reads the real track, so this is the load-bearing one."""
    assert pad_i > 0, "Big Red is supposed to be the track with the boost pads"


def test_touching_a_pad_arms_the_boost(rt, pad_i):
    r = rt.call("run(at(%d, 30), 0.05)" % pad_i)
    assert r["fired"] == 1
    assert r["pad"] == pytest.approx(T.PAD_BOOST, abs=0.05)


def test_the_boost_runs_out_on_its_own(rt, pad_i):
    """It is a moment, not a state. Driven well past the pad, it is gone."""
    r = rt.call("run(at(%d, 40), %s)" % (pad_i, T.PAD_BOOST + 0.6))
    assert r["pad"] == 0


def test_a_pad_fires_once_however_long_you_are_on_it(rt, pad_i):
    """The physics steps at 1/120 and a pad is several substeps wide.

    `onBoostPad` is a callback for exactly this reason - it has to be the *edge*
    of arriving on the pad, or crossing one slowly is a burst of forty identical
    sounds.
    """
    r = rt.call("run(at(%d, 12), 0.9)" % pad_i)
    assert r["fired"] == 1


def test_a_long_pad_holds_the_boost_open_rather_than_timing_out_on_it(rt, pad_i):
    """Re-arming while still on the pad is what makes the pad a *place*.

    Sit on a pad for longer than PAD_BOOST and the boost still has its full
    length left - otherwise a pad taken slowly is worth nothing, which is
    backwards: the car crawling out of the slow corner is the one that needs it.

    Coasting rather than on the throttle, because a boosted car on full throttle
    clears a twenty-unit pad in well under a second and the test would be about
    how long the pad is.
    """
    slow = rt.call("run(at(%d, 3), %s, {throttle: 0})" % (pad_i, T.PAD_BOOST + 0.5))
    assert slow["surface"] == 3, "still on the pad"      # KIND.BOOST
    assert slow["pad"] == pytest.approx(T.PAD_BOOST, abs=0.05)


def test_being_picked_up_takes_the_boost_with_it(rt, pad_i):
    """A respawn or a grid slot is not a moment to be holding a second of engine."""
    r = rt.call("(() => { const c = at(%d, 30); "
                "for (let i = 0; i < 6; i++) c.step(T.FIXED_DT, {throttle: 1}); "
                "const armed = c.padBoost; c.placeAt([0, 0, 0], [0, 0, -1]); "
                "return { armed, after: c.padBoost }; })()" % pad_i)
    assert r["armed"] > 0 and r["after"] == 0


# ---------------------------------------------------------------------------
# What it is worth
# ---------------------------------------------------------------------------

def _mult(rt, road_i, **opts):
    """The engine multiplier the real car actually applies, measured.

    Taken as the difference between two single steps, so `ACCEL` is the only
    thing left in it: drag, the slope and the surface are identical either side
    and cancel. Everything in this group is expressed in these units, because
    every one of them is a claim about how the three kinds of help combine.
    """
    import json
    base = rt.call("accelWith(%d, 40, {})" % road_i)
    got = rt.call("accelWith(%d, 40, %s)" % (road_i, json.dumps(opts)))
    return 1 + (got - base) / T.ACCEL


def test_a_pad_is_more_engine(rt, road_i):
    """The house rule, and half of what decides how a pad feels."""
    assert _mult(rt, road_i, pad=True) == pytest.approx(T.PAD_ACCEL_MULT, rel=0.02)


def test_a_pad_is_not_a_raised_limit(rt, road_i):
    """And the other half: the ceiling moves because the *engine* did.

    Top speed is where ACCEL fights the quadratic DRAG, so multiplying the
    throttle term by 1.7 puts the terminal speed at sqrt(1.7) times MAX_SPEED
    and the car has to accelerate up to it rather than the needle jumping.

    Pinned as an equality between two accelerations rather than by driving to
    terminal: a boosted car at PAD_TOP is doing exactly what a plain car at
    MAX_SPEED is doing, which is the definition of that being its top speed.
    Driving there for real is not available - held on full throttle the car
    steers nowhere and leaves the road at the first corner.
    """
    boosted_at_its_top = rt.call("accelWith(%d, %s, {pad: true})" % (road_i, PAD_TOP))
    plain_at_its_top = rt.call("accelWith(%d, %s, {})" % (road_i, T.MAX_SPEED))
    assert boosted_at_its_top == pytest.approx(plain_at_its_top, abs=1.5)
    assert PAD_TOP > T.MAX_SPEED * 1.15, "and it has to be worth having"


def test_a_pad_makes_you_faster_than_the_same_road_without_one(rt, pad_i):
    """End to end, with the pad armed by driving over it rather than by hand."""
    with_pad = rt.call("run(at(%d, 34), 1.6)" % pad_i)
    without = rt.call("(() => { const c = at(%d, 34); c.onBoostPad = () => {}; "
                      "const dt = T.FIXED_DT; let peak = 0; "
                      "for (let i = 0; i < Math.round(1.6 / dt); i++) { "
                      "  c.step(dt, {throttle: 1}); c.padBoost = 0; "
                      "  peak = Math.max(peak, c.vel.length()); } "
                      "return { peak }; })()" % pad_i)
    assert with_pad["peak"] > without["peak"] + 4, (
        "a pad has to be worth several u/s within its own length")


def test_a_pad_and_a_tow_do_not_multiply(rt, road_i):
    """The decision this mechanic turns on.

    Three multipliers at once is 3.4x the engine, which is 92 u/s against a hard
    velocity clamp of 85 - and then the clamp is setting the top speed instead
    of the tuning. Beyond the arithmetic: a tow is earned by sitting in
    somebody's air for a second and a half and a pad is handed to everybody who
    drives over it, so multiplying them makes the pad worth most to the car that
    was already being helped.

    Asserted against the product it must not be, and not only against the value
    it should have - the two differ by a factor of 1.5 and saying so is the
    point of the test.
    """
    both = _mult(rt, road_i, pad=True, slip=True)
    assert both == pytest.approx(max(T.PAD_ACCEL_MULT, T.SLIP_ACCEL_MULT), rel=0.02)
    assert both < T.PAD_ACCEL_MULT * T.SLIP_ACCEL_MULT * 0.9, "they must not be a product"


def test_everything_at_once_still_lands_under_the_velocity_clamp(rt, road_i):
    """Pad, tow and catch-up together, at the top of the catch-up ramp.

    If this ever fails the clamp has become the thing that decides top speed,
    and retuning the car quietly stops doing anything.
    """
    top = T.MAX_SPEED * math.sqrt(_mult(rt, road_i, pad=True, slip=True, catchup=1))
    assert top < CLAMP, "%.1f is over the %.1f clamp" % (top, CLAMP)


def test_a_pad_is_worth_less_than_a_tow_and_a_catchup_together(rt, road_i):
    """A pad is free and the other two are not, so it cannot be the big prize.

    It is deliberately the largest *single* multiplier - it has to be, or a pad
    on a straight where somebody already has a tow does nothing at all - but a
    driver who earned both of the others is still the faster car.
    """
    pad = _mult(rt, road_i, pad=True)
    assert pad > _mult(rt, road_i, slip=True), (
        "a pad alone beats a tow alone, or it is not worth crossing the road for")
    assert pad < _mult(rt, road_i, slip=True, catchup=1)


# ---------------------------------------------------------------------------
# The authoring and the geometry agreeing
# ---------------------------------------------------------------------------

def test_a_flagged_station_is_a_boost_surface_and_nothing_else_is(rt):
    """`Builder.boost` and `KIND.BOOST` have to describe the same tarmac.

    Drift here is a pad you can see and cannot use, or - worse, because nothing
    would ever look wrong - a stretch of ordinary road that quietly hands out
    engine.
    """
    r = rt.call("""(() => {
      const col = BUILT.collider || BUILT.col;
      const line = TRACK.line;
      // The road quad between stations i and i+1 is BOOST iff station i is.
      let flagged = 0, boostTris = 0;
      for (let i = 0; i + 1 < line.length; i++) if (line[i].bp) flagged++;
      for (let i = 0; i < col.k.length; i++) if (col.k[i] === KIND.BOOST) boostTris++;
      return { flagged, boostTris };
    })()""")
    assert r["flagged"] > 0
    # Two triangles per quad, one quad per station pair on a flat road.
    assert r["boostTris"] == r["flagged"] * 2


def test_every_pad_is_on_a_straight():
    """`Builder.boost` only lays straight road, and that is the rule.

    A pad is worth about a second of unarguable speed, so it belongs where the
    speed is usable - out of a slow corner, down a straight, into a jump - and
    never mid-corner, where all it does is take away the decision the corner was
    for.
    """
    for t in tracks_mod.TRACKS:
        for i, e in enumerate(t["line"]):
            if not e.get("bp"):
                continue
            assert not e.get("curv"), "%s has a pad in a corner at %d" % (t["slug"], i)
            assert not e.get("air"), "%s has a pad over a gap at %d" % (t["slug"], i)
            assert not e.get("pf"), "%s has a pad in a pipe at %d" % (t["slug"], i)


def test_a_pad_is_never_the_last_thing_before_a_braking_zone():
    """A pad wants road after it, or it is a gift you have to throw away.

    Measured as: from the end of every pad there is a clear run before the
    ribbon turns tightly, at least as far as the boost itself lasts at a
    reasonable speed.
    """
    reach = T.PAD_BOOST * T.MAX_SPEED * 0.55       # ~36 units, deliberately modest
    for t in tracks_mod.TRACKS:
        line = t["line"]
        for i, e in enumerate(line):
            if not e.get("bp") or (i + 1 < len(line) and line[i + 1].get("bp")):
                continue                            # only the last station of a pad
            run = 0.0
            j = i
            while j + 1 < len(line) and run < reach:
                nxt = line[j + 1]
                if abs(nxt.get("curv", 0.0)) > 1 / 30.0:
                    break
                run += tracks_mod.STATION
                j += 1
            assert run >= reach, (
                "%s: the pad ending at %d has only %.0f units before a corner"
                % (t["slug"], i, run))


# ---------------------------------------------------------------------------
# The medals knowing
# ---------------------------------------------------------------------------

def test_a_boosted_station_may_exceed_the_plain_top_speed():
    """This is the one that was silently false, and it is worth the words.

    `laptime` caps every station at a speed and then relaxes that cap where a
    pad's boost is live. The cap for a *cornering* station came from
    `_corner_speed`, which used to bisect between 0 and MAX_SPEED - so it
    returned exactly MAX_SPEED on anything straight, the raised cap was thrown
    away by a `min`, and the whole pad disappeared from the model on the only
    kind of road a pad is ever laid on. Every other test here passed. The ideal
    lap moved by 0.3s over four pads, which looked plausible enough to keep.

    So this asserts the thing that was wrong rather than the thing that was
    visible: on the road **just after a pad**, the model's own speed profile
    goes faster than the car's plain top speed.

    "Somewhere on the track" is not good enough and was tried first - it passed
    with the fix reverted, because Big Red has a loop in it and a loop's
    stations take their cap from the `fix` branch rather than from
    `_corner_speed`, so they were still boosted while every straight silently
    was not. The assertion has to be about the kind of road a pad is laid on.
    """
    t = tracks_mod.get("bigred")
    line = t["line"]
    _, v, _ = laptime.speed_profile(t)
    fast = False
    for i, e in enumerate(line):
        if not e.get("bp"):
            continue
        # The stations the boost is live over, which are plain straight road:
        # no loop, no gap, nothing with a cap of its own.
        for j in range(i, min(i + 18, len(line))):
            if line[j].get("crad") or line[j].get("air") or line[j].get("fix"):
                continue
            if v[j] > T.MAX_SPEED * 1.05:
                fast = True
    assert fast, (
        "no ordinary road after any pad exceeds MAX_SPEED in the lap model, "
        "so the pads are not reaching the medal times")


def test_the_pads_are_worth_real_time_in_the_ideal_lap():
    """And the medals are cut from that lap, so this is the medals being honest."""
    t = tracks_mod.get("bigred")
    with_pads = laptime.ideal_lap(t)
    stripped = {k: (list(vv) if k == "line" else vv) for k, vv in t.items()}
    stripped["line"] = [{k: vv for k, vv in e.items() if k != "bp"} for e in t["line"]]
    without = laptime.ideal_lap(stripped)
    assert without - with_pads > 0.8, (
        "four pads are worth %.2fs, which is not a mechanic" % (without - with_pads))


def test_a_track_with_no_pads_is_timed_exactly_as_it_was():
    """The boost loop must be a no-op on the twelve tracks that predate it.

    `_boost_window` returns all-False for a track with no pads, which equals the
    mask the loop starts with, so it settles after one pass and the arithmetic
    is the arithmetic it always was. A medal time moving on a track nobody
    touched would be the worst possible side effect of this feature.
    """
    for t in tracks_mod.TRACKS:
        if any(e.get("bp") for e in t["line"]):
            continue
        _, v, _ = laptime.speed_profile(t)
        assert max(v) <= T.MAX_SPEED + 1e-9, (
            "%s has no pads but its model exceeds MAX_SPEED" % t["slug"])
