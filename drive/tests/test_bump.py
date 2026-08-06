"""Car-to-car contact: what you are told about, what it costs, and what it moves.

The same shape as `test_slipstream.py` and `test_catchup.py`, because it is the
same shape of feature: the rule is `Car.resolveCars` in physics.js and it is run
here for real in QuickJS. Unlike those two it does need a world - contact happens
between two cars driving on a road, and the grip term the whole thing turns on
only exists while a car is grounded - so these drive on the pool's own spawn
point rather than in the void.

Three things are under test, and each of them was a bug or is a decision that
looks arbitrary until it is written down:

- **There were two questions behind one number.** A single `hit > 5` decided both
  whether a contact was reported *and* whether it cost anything, so every touch
  under it was completely silent - no clank, no sparks, no camera, no lean - and
  running wheel to wheel down a straight, which is most of what contact in a race
  is, looked and sounded like driving alone. Now `BUMP_FEEL` says when you are
  told and `BUMP_COST` says when it hurts, and the gap between them is where
  rubbing lives: audible and free.
- **Sustained contact must not bleed a car.** The per-pair cooldown is 0.15s, so
  a second and a half of rubbing is about ten events. Charging speed for each of
  them compounds, which is the trap the note on `CAR_BUMP_SCRUB` describes, and
  lowering the reporting floor is exactly what would have walked back into it.
- **A hit has to move the car, and only one thing makes it.** `GRIP` kills
  lateral velocity at `1 - exp(-GRIP*dt)` per step, so a sideways impulse on
  full grip is gone inside a tenth of a second *however large it is* - measured,
  raising the restitution and the push spring moved a 14 u/s side-swipe from 0.26
  units to 0.25. The tyres letting go (`BUMP_SLIP_GRIP`) is the entire
  difference, which is why the test for it is a comparison against itself with
  that one number pinned back to `GRIP`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

# Fast enough that a swipe is a swipe rather than two cars shuffling, and below
# MAX_SPEED so both are still on the power and a speed *loss* is unambiguous.
SPEED = 45.0

HARNESS = """
var TRACK = TRACKS.find(t => t.slug === 'sunrise');
var BUILT = buildTrack(TRACK, T);

// A pair of cars side by side on the start line at SPEED, close enough to be in
// contact. `tune` is an optional override of the tuning object, which is how the
// grip release is measured against its own absence.
function pair(tune) {
  var TT = tune ? Object.assign({}, T, tune) : T;
  var a = new Car(TT, BUILT), b = new Car(TT, BUILT);
  a.id = 'a'; b.id = 'b';
  a.placeAt(TRACK.spawn.p, TRACK.spawn.fwd);
  b.placeAt(TRACK.spawn.p, TRACK.spawn.fwd);
  b.pos.copy(a.pos).addScaledVector(a.right, TT.CAR_RADIUS * 2 - 0.05);
  a.vel.copy(a.fwd).multiplyScalar(%(speed)s);
  b.vel.copy(a.fwd).multiplyScalar(%(speed)s);
  return { T: TT, a: a, b: b,
           oa: { pos: a.pos, vel: a.vel, fwd: a.fwd, mass: 1, id: 'a' },
           ob: { pos: b.pos, vel: b.vel, fwd: b.fwd, mass: 1, id: 'b' } };
}

// What happened to `a`, measured against where and how fast it started.
function report(p, lat0, fwd0) {
  return { lat: p.a.pos.dot(p.a.right) - lat0,
           speed: p.a.vel.length(),
           dspeed: p.a.vel.length() - %(speed)s,
           clanks: p.a._clanks || 0, peak: p.a._peak || 0,
           lean: p.a._lean || 0, slip: p.a.bumpSlip,
           upY: p.a.up.y, heading: p.a.fwd.dot(fwd0) };
}

function watch(car) {
  car._clanks = 0; car._peak = 0; car._lean = 0;
  car.onBump = function (m) { car._clanks++; if (m > car._peak) car._peak = m; };
}

// b comes across into a at `closing` u/s and they are left to it. This is a
// racing incident: one shove, then whatever the cars do about it.
function swipe(closing, secs, tune) {
  var p = pair(tune);
  p.b.vel.addScaledVector(p.a.right, -closing);
  var lat0 = p.a.pos.dot(p.a.right), fwd0 = p.a.fwd.clone();
  watch(p.a);
  var dt = p.T.FIXED_DT, n = Math.round(secs / dt);
  for (var i = 0; i < n; i++) {
    p.a.step(dt, { throttle: 1 }); p.b.step(dt, { throttle: 1 });
    p.a.resolveCars([p.ob], dt); p.b.resolveCars([p.oa], dt);
    if (Math.abs(p.a.bumpLean) > p.a._lean) p.a._lean = Math.abs(p.a.bumpLean);
  }
  return report(p, lat0, fwd0);
}

// Two cars racing side by side and leaning on each other for the whole time,
// `closing` u/s of lean-in held all the way through. b is put back beside a
// every step and given the lean back, because the separation spring's entire
// job is to end contact and the worst case for the cooldown is contact that
// keeps being renewed.
//
// The lean matters and is not decoration: `hit` is *closing* speed, so two cars
// glued alongside each other at the same velocity are overlapping without ever
// impacting, and correctly produce no events at all. Rubbing is somebody
// leaning on you over and over.
function rub(closing, secs, tune) {
  var p = pair(tune);
  var lat0 = p.a.pos.dot(p.a.right), fwd0 = p.a.fwd.clone();
  watch(p.a);
  var dt = p.T.FIXED_DT, n = Math.round(secs / dt);
  for (var i = 0; i < n; i++) {
    p.a.step(dt, { throttle: 1 }); p.b.step(dt, { throttle: 1 });
    p.b.pos.copy(p.a.pos).addScaledVector(p.a.right, p.T.CAR_RADIUS * 2 - 0.1);
    p.b.vel.copy(p.a.vel).addScaledVector(p.a.right, -closing);
    p.a.resolveCars([p.ob], dt); p.b.resolveCars([p.oa], dt);
    if (Math.abs(p.a.bumpLean) > p.a._lean) p.a._lean = Math.abs(p.a.bumpLean);
  }
  return report(p, lat0, fwd0);
}

// The same car, the same throttle, nobody to hit. What contact is measured
// against, since a car on the power is *gaining* speed the whole time and "did
// it lose any" needs the counterfactual rather than the starting number.
function alone(secs) {
  var p = pair(null);
  var dt = T.FIXED_DT, n = Math.round(secs / dt);
  for (var i = 0; i < n; i++) p.a.step(dt, { throttle: 1 });
  return p.a.vel.length();
}
""" % {"speed": SPEED}


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


@pytest.fixture(scope="module")
def free(rt):
    """How fast the car is after 2s on the throttle with nobody to hit."""
    return rt.call("alone(2.0)")


def _swipe(rt, closing, secs=2.0, tune="null"):
    return rt.call("swipe(%s, %s, %s)" % (closing, secs, tune))


def _rub(rt, closing, secs=1.5):
    return rt.call("rub(%s, %s, null)" % (closing, secs))


# ---------------------------------------------------------------------------
# What you are told about
# ---------------------------------------------------------------------------

def test_a_touch_too_light_to_notice_is_not_reported(rt):
    """`BUMP_FEEL` is a floor, and it has to have something under it.

    Two cars in company are in and out of contact constantly at depths of a
    centimetre, and a clank for each would be a rattle rather than information.
    """
    assert _swipe(rt, T.BUMP_FEEL * 0.5)["clanks"] == 0


def test_every_touch_past_the_floor_is_reported(rt):
    """And above it nothing is silent, which is the whole change.

    This closing speed is far below the old `hit > 5` gate, so a rub like this
    used to happen with no clank, no sparks, no camera kick and no body lean -
    the cars simply passed through a shove that moved them both.
    """
    r = _swipe(rt, T.BUMP_FEEL * 1.6)
    assert r["clanks"] >= 1
    assert r["peak"] > T.BUMP_FEEL


def test_a_rub_is_heard_and_costs_nothing(rt, free):
    """The gap between the two thresholds is where racing side by side lives.

    A touch in it is reported - you know you leaned on somebody - and takes no
    speed off either car, because it is not a mistake, it is a race.
    """
    r = _swipe(rt, (T.BUMP_FEEL + T.BUMP_COST) / 2)
    assert r["clanks"] >= 1, "a rub is still an event"
    assert r["speed"] == pytest.approx(free, rel=0.005), "and it is a free one"


def test_a_firm_hit_costs_real_speed(rt, free):
    """Past `BUMP_COST` it is a mistake, and it is charged for."""
    r = _swipe(rt, 14.0)
    assert r["speed"] < free * 0.9


def test_sustained_rubbing_does_not_bleed_the_car(rt, free):
    """The reason there are two thresholds rather than one lowered one.

    Held in contact, the 0.15s cooldown is the only thing rationing the events,
    so a second and a half of this is about ten of them. Charging speed for each
    compounds - which is the trap `CAR_BUMP_SCRUB`'s own note describes, and
    lowering the reporting floor is precisely what would have walked back into
    it. Many clanks, no bill.
    """
    r = _rub(rt, (T.BUMP_FEEL + T.BUMP_COST) / 2, 1.5)
    assert r["clanks"] >= 5, "held contact really is reported over and over"
    assert r["speed"] > free * 0.98, "and ten of them still cost under 2%"


def test_sustained_contact_does_not_pin_the_body_over(rt):
    """The lean is per hit, not per step, and that is not a style choice.

    It used to be applied on every step a contact lasted, climbing to its own
    0.5 clamp inside a tenth of a second - so a car rubbing alongside somebody
    drove along at 29 degrees of roll until it let go.
    """
    r = _rub(rt, (T.BUMP_FEEL + T.BUMP_COST) / 2, 1.5)
    assert abs(r["lean"]) < 0.2, "a lean, not a lie-down"


# ---------------------------------------------------------------------------
# What it moves
# ---------------------------------------------------------------------------

# The grip release turned off: grip during a hit is the grip outside one, which
# is what the car did before and the only honest baseline for "does this move
# the car". Everything else - the restitution, the push spring, the scrub - is
# left exactly as it is.
NO_RELEASE = "{BUMP_SLIP_GRIP: T.GRIP}"


@pytest.mark.parametrize("closing,least", [(10.0, 2.0), (14.0, 2.5), (20.0, 2.0)])
def test_letting_the_tyres_go_is_what_moves_the_car(rt, closing, least):
    """Measured against its own absence, because that is the surprise here.

    Every instinct says a harder shove is a bigger `REST` and a stiffer
    `CAR_PUSH`, and it is not: grip kills lateral velocity at
    `1 - exp(-GRIP*dt)` per step, so on full grip a sideways impulse is gone
    inside a tenth of a second whatever its size - raising both of those numbers
    moved a 14 u/s swipe from 0.26 units to 0.25. Only `BUMP_SLIP_GRIP` moves
    it, so the assertion is against the same hit with that one number pinned
    back to `GRIP` rather than against a figure in a comment that will rot.
    """
    hit = abs(_swipe(rt, closing)["lat"])
    glued = abs(_swipe(rt, closing, tune=NO_RELEASE)["lat"])
    assert hit > glued * least


def test_a_harder_hit_moves_you_further(rt):
    """Monotonic, and it comes out of the impulse rather than out of the window.

    `bumpSlip` is deliberately *not* scaled by how hard the hit was: the impulse
    the let-go tyres are letting through already is, so scaling the window as
    well squares it, and an ordinary firm shunt ends up moving the car less than
    the same shunt on full grip would suggest.
    """
    lats = [abs(_swipe(rt, c)["lat"]) for c in (6.0, 10.0, 14.0, 20.0)]
    assert lats == sorted(lats)
    assert lats[-1] > lats[0] * 2.5, "a punt is a different event from a nudge"


def test_a_hit_is_a_nudge_and_never_a_spin(rt):
    """The one thing all of this must not become.

    A car that spins because somebody leaned on it turns a race into a
    demolition derby, and it is what the yaw term is kept to a whisper for.
    Checked at closing speeds well past anything a track produces, and in both
    directions - a hit must not turn the car over either.
    """
    for closing in (6.0, 14.0, 20.0, 28.0, 40.0):
        r = _swipe(rt, closing)
        assert r["upY"] > 0.9, "still the right way up at %s" % closing
        assert r["heading"] > 0.9, "still pointing where it was at %s" % closing


def test_the_tyres_come_back(rt):
    """And they come back on their own clock, wherever the car has got to.

    The timer is decayed with the other per-step timers rather than inside the
    grounded branch that reads it, because a car knocked into the air would
    otherwise hold the whole of its let-go tyres frozen for the length of the
    flight and land on them - a slide arriving a second after the hit that
    caused it, on a corner the driver had already saved.
    """
    during = _swipe(rt, 20.0, secs=T.BUMP_SLIP_TIME * 0.4)
    assert during["slip"] > 0, "let go while the window is open"
    after = _swipe(rt, 20.0, secs=T.BUMP_SLIP_TIME * 1.5)
    assert after["slip"] == 0, "and fully back once it has closed"
