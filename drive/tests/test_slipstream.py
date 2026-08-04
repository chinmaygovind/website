"""The slipstream: who gets a tow, when, and in which phases at all.

Two things are under test and they live in two different files. The *rule* -
what counts as sitting in another car's hole, and the charge-then-fire cadence -
is `Car.draft` in physics.js, and it is run here for real in QuickJS: it only
reads the body's own frame and the rivals handed to it, so it can be exercised
without driving anywhere or having a world under the car.

The *gate* - that a tow and a shove both belong to free practice and the race
and to nothing else - is `contactOn` in game.js, which is a pure function of the
phase. It is lifted out of the file by name (the same trick `test_touch.py`
uses on the touch bindings) and run against a stubbed state, so the qualifying
rule cannot quietly come undone.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

HARNESS = """
// A car parked at the origin pointing down -Z (the local forward), fast enough
// to be in a tow, with nothing under it: `draft` never touches the world.
function follower() {
  const c = new Car(T, {});
  c.placeAt([0, 0, 0], [0, 0, -1]);
  c.pos.set(0, 0, 0);
  c.grounded = true;
  c.speed = 40;
  return c;
}
// A rival, by default directly up the road and pointing the same way.
function rival(x, y, z, fwd) {
  return { id: 'r', pos: new THREE.Vector3(x, y, z),
           fwd: new THREE.Vector3(...(fwd || [0, 0, -1])) };
}
// Hold the car where it is for `seconds` and report what the tow did.
function hold(car, others, seconds) {
  const dt = T.FIXED_DT;
  car.onSlipstream = () => car._fired = (car._fired || 0) + 1;
  const n = Math.round(seconds / dt);
  for (let i = 0; i < n; i++) car.draft(others, dt);
  return { fired: car._fired || 0, charge: car.slipCharge,
           boost: car.slipBoost, towed: car.towed };
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


def _hold(rt, rivals, seconds, setup=""):
    return rt.call("(() => { const c = follower(); %s "
                   "return hold(c, %s, %s); })()" % (setup, rivals, seconds))


AHEAD = "[rival(0, 0, -12)]"


def test_the_tow_charges_and_then_fires(rt):
    """Nothing for SLIP_CHARGE seconds, then the whole of it at once."""
    early = _hold(rt, AHEAD, T.SLIP_CHARGE * 0.6)
    assert early["fired"] == 0 and early["boost"] == 0
    assert 0.5 < early["charge"] < 0.7          # filling, and paying nothing yet

    fired = _hold(rt, AHEAD, T.SLIP_CHARGE + 0.05)
    assert fired["fired"] == 1
    assert fired["boost"] == pytest.approx(T.SLIP_BOOST, abs=0.1)


def test_the_boost_ends_and_the_tow_starts_again(rt):
    """Charge, fire, charge - not one permanent tow behind a car you cannot pass."""
    r = _hold(rt, AHEAD, T.SLIP_CHARGE + T.SLIP_BOOST + T.SLIP_CHARGE + 0.1)
    assert r["fired"] == 2
    # Nothing accumulated while the boost was running: two boosts cost two full
    # charges, so a third is not already most of the way there.
    assert r["charge"] < 0.2


def test_nothing_accumulates_while_the_boost_runs(rt):
    r = _hold(rt, AHEAD, T.SLIP_CHARGE + T.SLIP_BOOST * 0.5)
    assert r["fired"] == 1 and r["boost"] > 0 and r["charge"] == 0


@pytest.mark.parametrize("rivals,why", [
    ("[rival(0, 0, 12)]", "behind you"),
    ("[rival(0, 0, -%s)]" % (T.SLIP_RANGE + 4), "too far up the road"),
    ("[rival(%s, 0, -12)]" % (T.SLIP_HALF_W + 1.5), "in the next lane"),
    ("[rival(0, %s, -12)]" % (T.SLIP_HALF_W + 1.5), "on the road above"),
    ("[rival(0, 0, -12, [0, 0, 1])]", "coming the other way"),
    ("[rival(0, 0, -12, [1, 0, 0])]", "crossing"),
    ("[]", "nobody there"),
    ("null", "no contact in this phase"),
])
def test_there_is_no_tow_off_a_car_you_are_not_following(rt, rivals, why):
    r = _hold(rt, rivals, T.SLIP_CHARGE * 2)
    assert r["fired"] == 0 and r["charge"] == 0 and not r["towed"], why


def test_there_is_no_tow_at_a_crawl_or_in_the_air(rt):
    """No hole to sit in, and nothing under you to sit in it with."""
    slow = _hold(rt, AHEAD, T.SLIP_CHARGE * 2, "c.speed = T.SLIP_MIN_SPEED - 2;")
    assert slow["fired"] == 0
    air = _hold(rt, AHEAD, T.SLIP_CHARGE * 2, "c.grounded = false;")
    assert air["fired"] == 0


def test_a_charge_bleeds_away_when_you_drop_out_of_the_hole(rt):
    """Pull out, and the tow is not waiting where you left it."""
    r = rt.call("""(() => {
      const c = follower();
      for (let i = 0; i < Math.round((T.SLIP_CHARGE * 0.8) / T.FIXED_DT); i++)
        c.draft(%s, T.FIXED_DT);
      const filled = c.slipCharge;
      for (let i = 0; i < Math.round((T.SLIP_DECAY * 0.5) / T.FIXED_DT); i++)
        c.draft([], T.FIXED_DT);
      return { filled, left: c.slipCharge };
    })()""" % AHEAD)
    assert r["filled"] > 0.7
    assert r["left"] < r["filled"] - 0.2
    assert r["left"] > 0            # a moment out of the tow is not a reset


def test_being_put_back_on_the_track_takes_the_tow_with_it(rt):
    r = rt.call("""(() => {
      const c = follower();
      for (let i = 0; i < Math.round((T.SLIP_CHARGE * 1.2) / T.FIXED_DT); i++)
        c.draft(%s, T.FIXED_DT);
      const before = c.slipBoost;
      c.placeAt([0, 0, 0], [0, 0, -1]);
      return { before, boost: c.slipBoost, charge: c.slipCharge };
    })()""" % AHEAD)
    assert r["before"] > 0 and r["boost"] == 0 and r["charge"] == 0


def test_the_boost_is_flagged_so_a_rival_can_be_told(rt):
    r = rt.call("""(() => {
      const c = follower();
      const off = c.flags() & FLAG.SLIP;
      for (let i = 0; i < Math.round((T.SLIP_CHARGE * 1.2) / T.FIXED_DT); i++)
        c.draft(%s, T.FIXED_DT);
      return { off, on: c.flags() & FLAG.SLIP };
    })()""" % AHEAD)
    assert r["off"] == 0 and r["on"] != 0


def test_the_boost_is_a_bigger_top_end_and_not_a_teleport():
    """Top speed is where the engine fights DRAG, so the multiplier is squared.

    A tow that did not raise the top speed would be worthless on the straight it
    is for, and one that doubled it would decide the race on its own. About a
    fifth faster is a pass you have to line up and can still get wrong.
    """
    boosted = (T.ACCEL * T.SLIP_ACCEL_MULT / T.DRAG) ** 0.5
    assert 1.15 < boosted / T.MAX_SPEED < 1.30
    # And it is still under the hard cap the car is clamped to, or the clamp
    # would be what set the boosted top speed instead of the tuning.
    assert boosted < T.MAX_SPEED * 1.7


# --- the phase gate, lifted out of game.js ---------------------------------

GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")


def _contact_on_src():
    """`contactOn` as it actually ships, by name rather than by line number."""
    src = open(GAME_JS).read()
    m = re.search(r"^function contactOn\(\) \{.*?^\}", src, re.S | re.M)
    assert m, "contactOn is gone from game.js, or is no longer a plain function"
    return m.group(0)


@pytest.mark.parametrize("mode,phase,race,want", [
    ("room", "free", False, True),          # practice: cars are cars
    ("room", "racing", True, True),         # the race itself
    ("room", "qualifying", False, False),   # everybody alone against the clock
    ("room", "countdown", True, False),
    ("room", "results", False, False),
    ("solo", "free", False, False),         # nobody to hit or to tow off
])
def test_contact_and_the_tow_belong_to_practice_and_the_race(mode, phase, race, want):
    ctx = jsrt.quickjs.Context()
    ctx.eval("var CFG = {mode: '%s'};" % mode)
    ctx.eval("var S = {racePhase: '%s', raceMode: %s};" % (phase, "true" if race else "false"))
    ctx.eval(_contact_on_src())
    assert bool(ctx.eval("contactOn()")) is want
