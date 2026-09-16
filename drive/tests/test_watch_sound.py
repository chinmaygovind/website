"""A replay you can hear, a replay you can read the driver's hands off, and the
air round the cars in one.

Watching used to be silent about the thing on the screen and loud about the
thing that was not - your own parked car went on making whatever noise it had
been making when you pressed Watch, and the lap actually being played made
none. Both halves are the same fact: nothing steps a car during a replay, so
the only thing that knows what the watched car is doing is the replay itself.

It knows plenty. A ghost frame carries the pose *and* the flag byte the lap was
recorded with (`Run._recordGhost`), which is the same byte the live cars put on
the wire - braking, sliding, airborne - so the engine note can be driven from a
recording exactly the way it is driven from a rival.

The same frame answers the second question. A lap driven since the ninth
value carries `inputByte` - what the driver was *pressing*, which is a different
fact from what the car was doing and is not recoverable from it: `FLAG_DRIFT` is
a car that is sliding, and nothing in the flag byte knows about steering or the
throttle at all. Anything older, and every race replay, is inferred from the
motion instead, and the pad says which of the two it is drawing.

The third question is what a boost looks like in a recording, and it has two
halves that come from two different places. A **pad** is not recorded at all and
does not need to be - it is a place on the track, and the replay knows the track
and where the car was, so `padUnder` asks the collider exactly what `Car.step`
asks it. A **tow** is `FLAG.SLIP`, which is set for precisely as long as the
boost pays; its *charge* is recorded nowhere and is reconstructed backwards from
the payout, which is the one thing in here that is an inference rather than a
reading. Both are worked out once per recording as a timeline and then read by
time, so scrubbing, pausing, playing at 4x and switching cars are all right
without any of them being handled.

Driven rather than read, like `test_panels.py` and `test_touch.py`: `inputsOf`,
`paintInputs`, `updateWatch`, the timeline pair and `ghostAir` are lifted out of
`game.js` by name and run against stubs, because what is under test is the
mapping from a recorded frame to an engine note, a lit key and the air round a
car.
"""

import os
import re

import pytest

from jsrt import HAVE_QUICKJS, JS, quickjs

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")

DT = 0.1                       # one stubbed frame, and the clock the speed is per
FLAG = {"DRIFT": 1, "AIR": 2, "RESPAWN": 4, "BRAKE": 8, "SLIP": 16}


def _fn(src, name):
    start = src.index("function %s(" % name)
    return src[start:re.compile(r"^\}$", re.M).search(src, start).end()]


def _lifted():
    src = open(os.path.join(JS, "game.js")).read()
    extra = _fn(src, "recordedSpeed")
    # The three that turn a frame into what you hear and what you see, plus the
    # table that says which element each bit lights - which is lifted rather
    # than restated, so a bit added to one and not the other fails here.
    keys = src.index("const INPUT_KEYS = [")
    return "\n".join([
        extra,
        _fn(src, "surfaceUnder"),
        _fn(src, "recordedTimeline"),
        _fn(src, "zeroDraft"),
        _fn(src, "padBoostAt"),
        _fn(src, "padHeardIn"),
        _fn(src, "slipStartedIn"),
        _fn(src, "slipAt"),
        _fn(src, "recordedCar"),
        _fn(src, "surfaceAt"),
        _fn(src, "smokeFor"),
        _fn(src, "tyreSmoke"),
        _fn(src, "ghostAir"),
        _fn(src, "inputsOf"),
        _fn(src, "paintInputs"),
        src[keys:src.index("];", src.index("const DRIFT_LIT")) + 2],
        _fn(src, "updateWatch"),
    ])


# Enough three.js to hold a position, and enough of everything else for one
# frame of a replay to happen. `HEARD` is the whole point: every engine note
# the replay asks for, in order.
STUB = r"""
var HEARD = [];
function V3(x, y, z) { this.x = x || 0; this.y = y || 0; this.z = z || 0; }
V3.prototype.copy = function (o) { this.x = o.x; this.y = o.y; this.z = o.z; return this; };
V3.prototype.set = function (x, y, z) { this.x = x; this.y = y; this.z = z; return this; };
V3.prototype.applyQuaternion = function () { return this; };
V3.prototype.clone = function () { return new V3(this.x, this.y, this.z); };
V3.prototype.distanceTo = function (o) {
  var dx = this.x - o.x, dy = this.y - o.y, dz = this.z - o.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
};
// Real ones: the steering half of `inputsOf` is a cross product and its sign,
// and a stub that returned zero would pass every steering test by never
// steering.
V3.prototype.crossVectors = function (a, b) {
  this.x = a.y * b.z - a.z * b.y;
  this.y = a.z * b.x - a.x * b.z;
  this.z = a.x * b.y - a.y * b.x;
  return this;
};
V3.prototype.length = function () {
  return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
};
V3.prototype.dot = function (o) { return this.x * o.x + this.y * o.y + this.z * o.z; };
V3.prototype.addScaledVector = function (o, k) {
  this.x += o.x * k; this.y += o.y * k; this.z += o.z * k; return this;
};
V3.prototype.lerpVectors = function (a, b, u) {
  this.x = a.x + (b.x - a.x) * u; this.y = a.y + (b.y - a.y) * u;
  this.z = a.z + (b.z - a.z) * u; return this;
};
function Q4() {}
Q4.prototype.set = function () { return this; };
Q4.prototype.normalize = function () { return this; };
var THREE = { Vector3: V3, Quaternion: Q4 };
var T = { MAX_SPEED: 50, PROBE: 2.6, RIDE_HEIGHT: 0.45, SNAP: 0.12, PAD_BOOST: 1.3,
          SLIP_CHARGE: 1.5, SLIP_BOOST: 1.6 };
var GHOST_RATE = 15;
var FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };
var KIND = { ROAD: 0, WALL: 1, OFFROAD: 2, BOOST: 3, BOUNCE: 4 };
// One boost pad, two units of it, lying across the lap at x 2..4, and the grass
// out past x 20 - with road everywhere else, so anywhere is a surface the car is
// on and not a hole it is falling through.
var PAD = [2, 4], GRASS = 20;
// Every whoosh, and the level the rushing air was last left at.
var WHOOSH = 0, AIR = [], AIRC = [], KICKS = 0, DRAWN = [], FXN = 0, PUFFS = [];
var S = {
  watch: null,
  // The chased ghost's half of this: its recording, its air and the effect
  // drawing it, all built on demand by `ghostAir`.
  ghost: null, ghostTl: null, ghostTlFor: null, ghostAir: null, ghostFx: null,
  sound: {
    engine: function (sf, th, sl, air) { HEARD.push({ sf: sf, th: th, sl: sl, air: !!air }); },
    draft: function (charge, boost) { AIR.push(boost); AIRC.push(charge); },
    boostPad: function () { WHOOSH++; },
  },
  renderer: {
    kick: function () { KICKS++; },
    makeDraft: function () { var id = ++FXN; return { id: id, gone: false,
                                                      dispose: function () { this.gone = true; } }; },
    // Every car's air, as it was drawn: which effect, and the three numbers
    // `Draft` reads off a car. The last row is the last car drawn this frame.
    // Every puff, in order: what kind and where the back of the car was.
    smoke: function (pos, vel, kind) { PUFFS.push({ kind: kind, x: pos.x }); },
    draft: function (st, dt, fx) {
      DRAWN.push({ fx: fx ? fx.id : 0, pad: st.padBoost, slip: st.slipBoost,
                   charge: st.slipCharge, out: st.respawnIn > 0 });
    },
  },
  built: { collider: { ground: function (x, y, z) {
    var kind = KIND.ROAD;
    if (x >= PAD[0] && x <= PAD[1]) kind = KIND.BOOST;
    else if (x > GRASS) kind = KIND.OFFROAD;
    return { hit: true, dist: T.RIDE_HEIGHT, kind: kind };
  } } },
};
// Enough of an element for the pad: `LIT` is which key ids are on, in the
// same shape `classList.toggle` leaves them.
var LIT = {}, AMBER = {};
function $(id) {
  return {
    textContent: '',
    style: { width: '', setProperty: function () {} },
    setAttribute: function () {},
    classList: {
      toggle: function (cls, on) {
        (cls === 'drifting' ? AMBER : LIT)[id] = !!on;
      },
    },
  };
}
function syncWatchUi() {}
var IN = { THROTTLE: 1, BRAKE: 2, HANDBRAKE: 4, RIGHT: 8, LEFT: 16 };
// A lap that drives for `after` seconds and then goes sideways for good, with
// the lamps lit or not - which is the whole question the pad has to answer.
function slideFrom(step, after, braking, n) {
  var out = [];
  for (var i = 0; i < (n || 12); i++) {
    var sliding = (i / 10 >= after);
    var f = (sliding ? FLAG.DRIFT : 0) | (sliding && braking ? FLAG.BRAKE : 0);
    out.push([i * step, 0, 0, 0, 0, 0, 1, f]);
  }
  return out;
}
// A lap with a tow paying out over frames [from, to). The bit is set for
// exactly as long as `slipBoost` is above zero, which is what makes a run of it
// the payout itself rather than a hint about one.
// Well clear of `PAD`, so the tow is the only boost in the lap - a pad's air
// and a tow's are the same air, and a test that could not tell them apart would
// pass on either.
function towLap(step, from, to, n) {
  var out = [];
  for (var i = 0; i < (n || 40); i++) {
    out.push([-100 + i * step, 0, 0, 0, 0, 0, 1, (i >= from && i < to) ? FLAG.SLIP : 0]);
  }
  return out;
}
// A lap already out on the grass, past `GRASS`, at whatever pace the step says.
function grassLap(step, flags, n) {
  var out = [];
  for (var i = 0; i < (n || 12); i++) {
    out.push([30 + i * step, 0, 0, 0, 0, 0, 1, flags | 0]);
  }
  return out;
}
function fmt() { return ''; }
function lampsOf() { return {}; }

// A lap along +X at a fixed spacing, so the speed the camera measures is the
// spacing over the frame time - and, with `wide` false, one recorded before the
// flag byte existed.
function lap(step, flags, n, wide, input) {
  var out = [];
  for (var i = 0; i < (n || 8); i++) {
    var f = [i * step, 0, 0, 0, 0, 0, 1];
    if (wide !== false) f.push(flags | 0);
    if (input !== undefined) f.push(input | 0);
    out.push(f);
  }
  return out;
}
function car(frames, recorded) {
  // Interpolated along +X the way the real `Ghost.at` interpolates, not snapped
  // to the nearest sample: a stub that quantised would report a car standing
  // still on every frame that landed inside a sample, which is exactly the
  // shape a slowed-down replay is.
  var g = { frames: frames, at: function (t) {
                  var q = t * 10, i = Math.floor(q), u = q - i;
                  var a = frames[i], b = frames[i + 1];
                  if (!a) return null;
                  if (!b) return a;
                  var out = a.slice();
                  out[0] = a[0] + (b[0] - a[0]) * u;
                  return out;
                },
                hz: 10 };
  return { g: g, view: { update: function () {}, group: {} }, prev: null,
           fx: S.renderer.makeDraft(), air: null, tl: recordedTimeline(g),
           gates: [], recorded: !!recorded };
}
function watching(cars, at) {
  S.watch = { cars: cars, at: at || 0, t: 0, dur: 1e6,
              // The same shape `startReplay` builds, including the four numbers
              // the camera and the air read off a car: a stub short of them
              // would pass by never having a boost to get wrong.
              subject: { pos: new V3(), fwd: new V3(), up: new V3(),
                         right: new V3(), speed: 0, grounded: true, T: T,
                         padBoost: 0, slipBoost: 0, slipCharge: 0, respawnIn: 0 },
              title: null, playing: true, rate: 1, shown: -1 };
  LIT = {}; AMBER = {}; WHOOSH = 0; AIR = []; AIRC = []; KICKS = 0; DRAWN = [];
  PUFFS = [];
}
// Two frames, because a speed is measured between them: the first has nothing
// to measure against and is honestly zero.
function play(n) { for (var i = 0; i < (n || 2); i++) updateWatch(0.1); }
"""


@pytest.fixture()
def js():
    c = quickjs.Context()
    c.eval(STUB)
    c.eval(_lifted())
    return c


def _last(c, key):
    return c.eval("HEARD[HEARD.length - 1].%s" % key)


def test_the_car_you_are_watching_is_the_car_you_hear(js):
    """One note a frame, off the lap being played - and it is a real speed, not
    a car sitting at the wheel of a replay it is not driving."""
    js.eval("watching([car(lap(0.5, 0))]); play();")
    assert js.eval("HEARD.length") == 2
    assert _last(js, "sf") == pytest.approx(0.5 / DT / 50)


def test_a_faster_lap_revs_harder(js):
    js.eval("watching([car(lap(0.5, 0))]); play();")
    slow = _last(js, "sf")
    js.eval("HEARD = []; watching([car(lap(2, 0))]); play();")
    assert _last(js, "sf") > slow


def test_the_recorded_flags_are_what_the_driver_was_doing(js):
    """The byte is the whole reason a replay can sound like a lap rather than
    like a speed: braking is off the power, and sliding and flying are heard."""
    js.eval("watching([car(lap(0.5, 0))]); play();")
    assert _last(js, "th") == 1 and _last(js, "sl") == 0 and _last(js, "air") is False

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.BRAKE))]); play();")
    assert _last(js, "th") == 0, "on the power with the brakes on"

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.DRIFT))]); play();")
    assert _last(js, "sl") > 0

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.AIR))]); play();")
    assert _last(js, "air") is True


def test_a_crawling_car_is_not_on_the_power(js):
    """There is no throttle on the wire or in a recording, and there does not
    need to be: not braking and not crawling is on the power."""
    js.eval("watching([car(lap(0.02, 0))]); play();")
    assert _last(js, "th") == 0


def test_a_lap_from_before_the_flag_byte_still_drives(js):
    """Seven values wide, so every state in it reads false - which is a car
    that is driving, and that is the right answer for a lap that was."""
    js.eval("watching([car(lap(0.5, 0, 8, false))]); play();")
    assert _last(js, "th") == 1 and _last(js, "air") is False


def test_only_the_car_the_camera_is_on_is_heard(js):
    """Eight cars in a race replay are eight cars on the screen and one in your
    ears: the camera is riding one of them, and that is the one you are in."""
    js.eval("watching([car(lap(0.5, 0)), car(lap(2, 0))], 0); play();")
    assert js.eval("HEARD.length") == 2
    one = _last(js, "sf")
    js.eval("HEARD = []; watching([car(lap(0.5, 0)), car(lap(2, 0))], 1); play();")
    assert js.eval("HEARD.length") == 2
    assert _last(js, "sf") > one


# ---------------------------------------------------------------------------
# The input pad
# ---------------------------------------------------------------------------

IN = {"THROTTLE": 1, "BRAKE": 2, "HANDBRAKE": 4, "RIGHT": 8, "LEFT": 16}


def _lit(c, key):
    return c.eval("!!LIT['%s']" % key)


def test_a_recorded_lap_shows_what_the_driver_pressed(js):
    """The ninth value and nothing else. It is the driver's hands, so it is not
    second-guessed against what the car appears to be doing - a lap held on the
    throttle into a spin shows the throttle held."""
    js.eval("watching([car(lap(0.5, 0, 8, true, IN.THROTTLE | IN.LEFT), true)]); play();")
    assert _lit(js, "kUp") and _lit(js, "kLeft")
    assert not _lit(js, "kRight") and not _lit(js, "kDown")
    # Both drawings of the one byte, because which of them is on the screen is a
    # media query's business rather than the replay's.
    assert _lit(js, "tGas") and _lit(js, "tLeft")


def test_a_recorded_brake_is_not_a_recorded_throttle(js):
    js.eval("watching([car(lap(0.5, 0, 8, true, IN.BRAKE), true)]); play();")
    assert _lit(js, "kDown") and not _lit(js, "kUp")


def test_the_space_bar_is_lit_like_any_other_key(js):
    """The desktop pad is a picture of a keyboard, and on a keyboard a held key
    is a held key. The amber belongs to the phone's pedals, where it is on a
    *control* under a thumb that asked for one thing and got another - here it
    would be a second colour to learn for nothing, and it made the one key that
    is purely a readout look like a warning."""
    js.eval("watching([car(lap(0.5, 0, 8, true, IN.HANDBRAKE), true)]); play();")
    assert _lit(js, "kSpace")
    assert not js.eval("!!AMBER['kSpace']"), "the space bar is still amber"


def test_the_phone_pedal_still_goes_amber(js):
    """The same byte, drawn for a different reader: on a phone the drift has to
    be obvious or the slide reads as the car misbehaving."""
    js.eval("watching([car(lap(0.5, 0, 8, true, IN.HANDBRAKE | IN.THROTTLE), true)]);"
            " play();")
    assert js.eval("!!AMBER['tGas']")


def test_an_old_lap_infers_the_hands_from_the_car(js):
    """Eight wide, so there is nothing to read: the throttle is not-braking-and-
    moving, which is the rule the engine note already uses, and the handbrake is
    the car sliding."""
    js.eval("watching([car(lap(0.5, 0))]); play();")
    assert _lit(js, "kUp") and not _lit(js, "kDown") and not _lit(js, "kSpace")

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.BRAKE))]); play();")
    assert _lit(js, "kDown") and not _lit(js, "kUp")

    # Braking *and* sideways - see the handbrake tests below for why both.
    js.eval("HEARD = []; watching([car(slideFrom(0.5, 0.4, true))]);"
            " S.watch.t = 0.5; play(1);")
    assert _lit(js, "kSpace")


def test_an_inferred_straight_is_not_steering(js):
    """A lap along +X with the car pointing one way the whole time. The deadband
    is what stops a straight flickering left and right under the pad."""
    js.eval("watching([car(lap(0.5, 0))]); play(4);")
    assert not _lit(js, "kLeft") and not _lit(js, "kRight")


def test_an_inferred_crawl_is_not_on_the_power(js):
    """The same rule the engine note is under, said on the pad: below walking
    pace a car that is not braking is not being driven, it is stopped."""
    js.eval("watching([car(lap(0.02, 0))]); play();")
    assert not _lit(js, "kUp")


def test_a_recorded_lap_is_not_second_guessed(js):
    """A recorded frame saying nothing is held is a driver coasting, and it has
    to read as one - inferring a throttle over the top of it would mean the pad
    could never show a lift, which is half of what anybody watches a fast lap
    to see."""
    js.eval("watching([car(lap(0.5, 0, 8, true, 0), true)]); play();")
    assert not _lit(js, "kUp") and not _lit(js, "kDown")


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------

def test_a_slide_with_the_lamps_off_is_not_a_handbrake(js):
    """The one deduction in here that is a **proof rather than a guess**, and the
    reason the inferred space bar is worth drawing at all.

    `Car.braking` is `(brake && moving forwards) || handbrake`, so the handbrake
    sets `FLAG.BRAKE` unconditionally - and therefore `FLAG.BRAKE` clear means
    the handbrake was *not* down, whatever the car is doing. `FLAG.DRIFT` on its
    own is `slip > 0.35`, which any hard corner produces: on BotTyler's Big Red
    lap it fires 21 times and the driver's hands are provably off the key for 19
    of them. Reading the slide alone put a handbrake on nearly every corner of a
    lap that used it twice.
    """
    js.eval("watching([car(slideFrom(0.5, 0.2, false))]); S.watch.t = 0.6; play(1);")
    assert not _lit(js, "kSpace"), "a handbrake on a lap that could not have used it"


def test_braking_and_sideways_is_the_handbrake(js):
    """The two inputs share the one bit, so which of them it was cannot be read
    off directly - but a car slowing on the driver's say-so that is also out of
    shape is the shape of a handbrake pull."""
    js.eval("watching([car(slideFrom(0.5, 0.2, true))]); S.watch.t = 0.6; play(1);")
    assert _lit(js, "kSpace")
    # And it is the handbrake rather than the brake, which is the same bit
    # reading a different way.
    assert not _lit(js, "kDown")


def test_braking_in_a_straight_line_is_the_brake(js):
    js.eval("watching([car(lap(0.5, FLAG.BRAKE))]); play();")
    assert _lit(js, "kDown") and not _lit(js, "kSpace")


def test_the_inferred_space_bar_lasts_as_long_as_the_lamps_do(js):
    """Which is the check the eye actually makes. The bar and the tail lamps read
    the same bit now, so a pad that disagrees with the car beside it is a bug you
    can see without instrumenting anything - and that is how the last two
    versions of this were caught."""
    got = js.eval("""
      var out = [];
      watching([car(slideFrom(0.5, 0.3, true))]);
      for (var i = 0; i < 9; i++) {
        S.watch.t = i / 10; S.watch.shown = -1; updateWatch(0.001);
        var f = S.watch.cars[0].g.at(S.watch.t);
        out.push(((f[7] & FLAG.BRAKE) ? 'L' : '-') + (LIT['kSpace'] ? 'S' : '-'));
      }
      out.join(' ');
    """)
    # Lamps and space bar move together, frame for frame.
    assert all(p in ("--", "LS") for p in got.split()), got


def test_a_recorded_handbrake_is_not_shortened(js):
    """The tap is a guess about a lap that did not record one. A lap that did
    says how long the key was actually down, and a driver who really does hold
    it through a corner has to be drawn holding it."""
    js.eval("watching([car(lap(0.5, FLAG.DRIFT, 8, true, IN.HANDBRAKE), true)]);"
            " S.watch.t = 0.6; play(1);")
    assert _lit(js, "kSpace")


def test_a_scrubbed_car_is_not_a_stopped_car(js):
    """The camera measures speed between the frame it drew last and this one,
    and a seek clears that on purpose - a jump measured that way is the distance
    jumped, heard as an engine at several thousand km/h. But a *paused* replay
    never draws a second frame either, so a scrub landed on a car reading zero:
    the engine went quiet and the pad dropped the throttle, on a frame where the
    driver was flat out.

    The recording knows how fast it was going. One frame ahead over one frame of
    time - the same quantity the camera estimates, and not an estimate."""
    js.eval("watching([car(lap(0.5, 0))]); S.watch.t = 0.3; play(1);")
    assert _last(js, "sf") > 0, "a car scrubbed to is silent"
    assert _lit(js, "kUp"), "a car scrubbed to has let go of the throttle"
    # And it stays right for as long as you sit there. The camera's measure is
    # an honest zero about a still picture - the car does not move between two
    # frames of a paused replay - so the pad has to be asking the recording
    # rather than the picture, or the throttle drops out one frame later on
    # exactly the frame somebody paused to look at.
    js.eval("S.watch.playing = false; play(6);")
    assert _lit(js, "kUp"), "the throttle fell off a paused frame"


def test_the_playback_rate_does_not_change_the_engine_note(js):
    """Slow motion is a slower *film*, not a slower car. The speed is measured
    between frames and divided by the rate, so what you hear at 0.25x is what
    the driver heard - which is the whole reason slow motion is worth having."""
    js.eval("watching([car(lap(0.5, 0))]); play();")
    full = _last(js, "sf")
    js.eval("HEARD = []; watching([car(lap(0.5, 0))]); S.watch.rate = 0.25; play(5);")
    assert _last(js, "sf") == pytest.approx(full)


def test_a_paused_replay_does_not_advance(js):
    """Pause is the clock stopping, not the picture: the same frame is drawn
    again, which is what makes a still frame a still frame."""
    js.eval("watching([car(lap(0.5, 0))]); S.watch.playing = false; play(4);")
    assert js.eval("S.watch.t") == 0


def test_the_replay_stops_at_the_flag_rather_than_looping(js):
    """A bar that never stops moving cannot be read, and a replay that starts
    itself again is one you have to catch."""
    js.eval("watching([car(lap(0.5, 0))]); S.watch.dur = 0.25; play(8);")
    assert js.eval("S.watch.t") == pytest.approx(0.25)
    assert js.eval("S.watch.playing") is False


def test_a_lap_that_runs_out_goes_quiet(js):
    """A replay is as long as its longest car, so the one you are watching can
    stop existing partway through - and nothing else in there would ever move
    its engine again."""
    js.eval("watching([car(lap(0.5, 0, 3))]); play(6);")
    assert _last(js, "sf") == 0 and _last(js, "th") == 0


# --- the boost pads a replay drives over ------------------------------------
#
# A pad is the one thing that happens to a car that is neither in the pose nor
# in the flag byte: `padBoost` lives on the driven car and a recording has no
# car. Watching one was therefore silent and dry - the driver was thrown down
# the straight and the replay showed the throw with none of what makes it one.
# It is recoverable because a pad is a *place*: the replay has the track and it
# has where the car was, which is both halves of `Car.step`'s own test.


def test_a_pad_in_a_replay_makes_its_noise(js):
    """One whoosh, and the air goes with it."""
    js.eval("watching([car(lap(0.5, 0, 40))]); play(12);")
    assert js.eval("WHOOSH") == 1
    assert js.eval("KICKS") == 1, "the camera took no punch"
    assert js.eval("AIR[AIR.length - 1]") > 0


def test_a_long_pad_is_one_whoosh_and_not_a_stutter(js):
    """`Car.step` re-arms while the car is still on the pad rather than firing
    again, so a travelator holds the boost open. The rising edge here is the
    same one, for the same reason: the car is over the pad for five frames."""
    js.eval("watching([car(lap(0.5, 0, 40))]); play(20);")
    assert js.eval("WHOOSH") == 1


def test_a_replay_that_touches_no_pad_stays_dry(js):
    """The whole lap short of the pad, which is most laps on most tracks."""
    js.eval("watching([car(lap(0.1, 0, 40))]); play(12);")
    assert js.eval("WHOOSH") == 0
    assert js.eval("AIR[AIR.length - 1]") == 0, "the band was left open"


def test_a_car_over_a_pad_in_the_air_is_not_boosted(js):
    """Same rule as the simulation: a pad is touched, not flown over. The flag
    byte is what says which, and it is in every recording."""
    js.eval("watching([car(lap(0.5, FLAG.AIR, 40))]); play(12);")
    assert js.eval("WHOOSH") == 0


def test_the_boost_falls_away_in_the_films_seconds(js):
    """Slow motion is a slower film, not a shorter boost. The air has to fade
    over the same stretch of road it faded over when it was driven, or at 0.25x
    it is gone a corner before the car stops accelerating."""
    js.eval("watching([car(lap(0.5, 0, 40))]); play(12);")
    was = js.eval("S.watch.subject.padBoost")
    # Off the far end of the pad at frame nine, so three frames of fade.
    assert was == pytest.approx(1.3 - 0.4, abs=1e-6), "not decaying at all"
    js.eval("S.watch.rate = 0.25; play(4);")
    # Four frames at a quarter speed is one tenth of a second of the lap.
    assert js.eval("S.watch.subject.padBoost") == pytest.approx(was - 0.1)


def test_a_paused_boost_is_a_still_picture(js):
    """Pause is the clock stopping, and the air is on that clock. A boost that
    drained while somebody looked at the frame would empty the one thing they
    paused to look at."""
    js.eval("watching([car(lap(0.5, 0, 40))]); play(12); S.watch.playing = false;")
    was = js.eval("S.watch.subject.padBoost")
    js.eval("play(8);")
    assert js.eval("S.watch.subject.padBoost") == was
    assert js.eval("WHOOSH") == 1, "the pad fired again while nothing moved"


def test_a_pad_between_two_recorded_frames_is_still_a_pad(js):
    """The lap was driven at 120Hz and recorded at 15. At speed that is three
    units a frame, which is wider than a pad - so the timeline samples the
    ground *between* frames as well as on them, or a pad drives clean through
    the gap and the boost it gave never happened."""
    # Eight units a frame, which steps over the whole pad in one.
    js.eval("watching([car(lap(8, 0, 12))]); play(4);")
    assert js.eval("WHOOSH") == 1
    assert js.eval("S.watch.subject.padBoost") > 0


def test_a_scrub_past_a_pad_is_not_a_pad_anybody_drove_over(js):
    """The whoosh is the one event among levels, so it asks what the film just
    crossed rather than where it is. Dragging the bar past a pad is not a car
    going over one, and the replay must not shout about it - but the boost it
    lands *in* is a level, and that is simply true of where it landed."""
    js.eval("watching([car(lap(0.5, 0, 40))]); S.watch.playing = false;"
            " S.watch.t = 0.85; play(1);")
    assert js.eval("WHOOSH") == 0, "a scrub made a noise"
    assert js.eval("S.watch.subject.padBoost") > 0, "a scrub into a boost is dry"


def test_a_boost_is_read_off_the_recording_and_not_carried(js):
    """Everything about a boost is a pure function of where the film is, which
    is what makes scrubbing, T and picking another car right for nothing. Land
    on the same frame from either direction and it is the same boost."""
    js.eval("watching([car(lap(0.5, 0, 40))]); play(12);")
    forwards = js.eval("S.watch.subject.padBoost")
    js.eval("watching([car(lap(0.5, 0, 40))]); S.watch.playing = false;"
            " S.watch.t = 1.2; play(1);")
    assert js.eval("S.watch.subject.padBoost") == pytest.approx(forwards)


def test_a_car_that_runs_out_takes_its_boost_with_it(js):
    """A lap shorter than the replay stops existing partway through, and
    nothing else in there would ever close the band again."""
    js.eval("watching([car(lap(0.5, 0, 6))]); play(4);")
    assert js.eval("S.watch.subject.padBoost") > 0
    js.eval("play(4);")
    assert js.eval("S.watch.subject.padBoost") == 0
    assert js.eval("AIR[AIR.length - 1]") == 0


# --- the tow, and everybody's air -------------------------------------------
#
# `FLAG.SLIP` has been in the pose and in every recording since the tail lamps
# needed it, and it is set for exactly as long as the boost is paying - so the
# payout in a replay is a fact rather than a reading. The *charge* is not
# recorded anywhere, and it is the half worth watching: see `slipAt` for what is
# reconstructed and what that costs.


def _air(js, key, i=0):
    """One number out of the air drawn for the i-th car of the frame just played.

    In car order, because that is the order `updateWatch` draws them in - and
    the tests clear `DRAWN` immediately before the frame they are about, so the
    rows are that frame and nothing else.
    """
    return js.eval("DRAWN[%d].%s" % (i, key))


def test_a_recorded_tow_pays_out_in_the_replay(js):
    """The bit is the boost: a run of it starts where the tow fired and ends
    where it ran out, so the air goes amber for the same second and a half it
    did when it was driven."""
    js.eval("watching([car(towLap(0.5, 6, 22))]); S.watch.t = 0.7; play(1);")
    assert js.eval("S.watch.subject.slipBoost") > 0
    assert js.eval("AIR[AIR.length - 1]") > 0
    # And it is gone once the bit is, rather than lingering over a car that is
    # back to its own engine.
    js.eval("S.watch.t = 2.5; play(1);")
    assert js.eval("S.watch.subject.slipBoost") == 0


def test_the_boost_is_what_is_left_and_not_a_switch(js):
    """`Draft` reads seconds, not a flag, so the air peters out with the boost
    the way it does from the seat. Later in the same run is less of it."""
    js.eval("watching([car(towLap(0.5, 6, 22))]); S.watch.t = 0.65; play(1);")
    early = js.eval("S.watch.subject.slipBoost")
    js.eval("S.watch.t = 1.9; play(1);")
    assert 0 < js.eval("S.watch.subject.slipBoost") < early


def test_the_charge_fills_towards_a_tow_that_is_coming(js):
    """The wind-up is the half you can only see from outside the car, and the
    only thing in the recording that says it happened is the payout at the far
    end of it. A boost at t means the driver was in somebody's air a full
    SLIP_CHARGE earlier, so the ramp runs back from there."""
    js.eval("watching([car(towLap(0.5, 20, 36))]);")   # the tow fires at t=2.0
    js.eval("S.watch.playing = false; S.watch.t = 1.9; DRAWN = []; play(1);")
    nearly = js.eval("S.watch.subject.slipBoost")
    assert nearly == 0, "not paying yet"
    assert js.eval("AIR[AIR.length - 1]") == 0, "the band opens on the boost"
    # The rushing air fills with the charge instead, which is what `Sound.draft`
    # takes as its first argument - so you hear the boost coming, watching, the
    # same way you do driving.
    assert js.eval("AIRC[AIRC.length - 1]") > 0
    late = _air(js, "charge")
    js.eval("S.watch.t = 0.6; DRAWN = []; play(1);")
    early = _air(js, "charge")
    assert 0 < early < late < 1


def test_a_lap_with_no_tow_in_it_has_no_charge_anywhere(js):
    """Nothing to run a ramp back from, which is most laps: the tow belongs to
    a room and the leaderboard is driven alone."""
    js.eval("watching([car(lap(0.1, 0, 40))]); play(9); DRAWN = []; play(1);")
    assert _air(js, "charge") == 0
    assert _air(js, "slip") == 0


def test_a_tow_makes_the_same_noise_a_pad_does(js):
    """Both are the same fact from inside the car - more engine than you had a
    moment ago - and the whoosh is the announcement either way."""
    js.eval("watching([car(towLap(0.5, 6, 22))]); play(12);")
    assert js.eval("WHOOSH") == 1
    assert js.eval("KICKS") == 1


def test_every_car_in_a_race_replay_gets_its_own_air(js):
    """A tow is the one move in this game its own driver cannot see, so a race
    replay showing only the camera car's air would be hiding the half worth
    watching. One `Draft` each, because the streaks have to fly their own run
    out and cannot be shared."""
    js.eval("watching([car(towLap(0.5, 6, 22)), car(lap(0.5, 0, 40))], 0);"
            " S.watch.t = 0.7; DRAWN = []; play(1);")
    assert _air(js, "slip") > 0, "the car the camera is on"
    assert _air(js, "slip", 1) == 0, "a car that was not in a tow"
    # And the one being towed is the *other* car, from the same one frame.
    js.eval("watching([car(lap(0.5, 0, 40)), car(towLap(0.5, 6, 22))], 0);"
            " S.watch.t = 0.7; DRAWN = []; play(1);")
    assert _air(js, "slip", 1) > 0, "a rival's tow is not drawn"


def test_a_car_being_put_back_on_the_road_has_no_air(js):
    """`Draft` already knows this and only has to be told, and the recording
    says so: RESPAWN is in the same byte."""
    js.eval("watching([car(lap(0.5, FLAG.RESPAWN | FLAG.SLIP, 40))]);"
            " play(3); DRAWN = []; play(1);")
    assert _air(js, "out") is True


# --- the ghost you are chasing ----------------------------------------------
#
# Same two timelines, no sound. A ghost is a lap you are being shown rather than
# a rival, and where its driver took a pad or picked up a tow is most of what
# there is to learn from it.


def _ghost(js, frames):
    js.eval("S.ghost = null; S.ghostFx = null; S.ghostTl = null;"
            " S.ghostTlFor = null; S.ghostAir = null; DRAWN = [];")
    js.eval("S.ghost = car(%s).g;" % frames)


def test_the_ghost_gets_the_air_its_lap_had_in_it(js):
    _ghost(js, "towLap(0.5, 6, 22)")
    js.eval("DRAWN = []; ghostAir(0.7, new V3(3, 0, 0), new Q4(), 0.1);")
    assert _air(js, "slip") > 0


def test_the_ghost_finds_the_pads_the_track_has(js):
    """Off the collider, the same way a replay does - so a ghost recorded years
    before any of this lights up on the pads it drove over."""
    _ghost(js, "lap(0.5, 0, 40)")
    js.eval("DRAWN = []; ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    assert _air(js, "pad") > 0


def test_the_ghost_is_silent(js):
    """The whoosh belongs to the car you are sitting in. Two of them on one pad
    reads as an echo, and the ghost is not the one you are driving."""
    _ghost(js, "lap(0.5, 0, 40)")
    js.eval("DRAWN = []; ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    assert js.eval("WHOOSH") == 0 and js.eval("KICKS") == 0


def test_the_ghosts_timeline_is_built_once_per_ghost(js):
    """Keyed on the `Ghost` object, because a ghost is swapped by five different
    things and none of them should have to know an effect exists. A different
    object is a different lap; the same one is the same answer."""
    _ghost(js, "lap(0.5, 0, 40)")
    js.eval("DRAWN = []; ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    fx = js.eval("S.ghostFx.id")
    # A mark on the timeline that only survives if it is not rebuilt.
    js.eval("S.ghostTl.mine = 1; ghostAir(1.0, new V3(5, 0, 0), new Q4(), 0.1);")
    assert js.eval("S.ghostTl.mine") == 1, "the timeline was built again"
    assert js.eval("S.ghostFx.id") == fx, "a second effect was made"
    assert js.eval("S.ghostTlFor === S.ghost") is True
    # A different lap is a different object, and gets its own.
    js.eval("S.ghost = car(lap(0.5, 0, 40)).g;"
            " ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    assert js.eval("S.ghostTl.mine") is None, "a new ghost kept the old timeline"


def test_a_ghost_off_the_screen_lets_its_air_fly_out(js):
    """Called with no pose before the lap starts, after it ends and with ghosts
    off - what is in the air finishes its run instead of freezing over the road,
    and nothing new is launched."""
    _ghost(js, "lap(0.5, 0, 40)")
    js.eval("DRAWN = []; ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    assert _air(js, "pad") > 0
    js.eval("DRAWN = []; ghostAir(null, null, null, 0.1);")
    assert _air(js, "pad") == 0


# --- the dust ---------------------------------------------------------------
#
# Smoke is `smokeFor`, which is one rule read off a car and is the same function
# the driven car uses. A recording answers it with the byte for the slide and
# with the timeline's surface pass for the grass - which is the same trick the
# pads are: the road knows what it is made of and the recording does not have to.


def _puff(js, i=-1, key="kind"):
    return js.eval("(PUFFS.length ? PUFFS[%s].%s : null)"
                   % ("PUFFS.length - 1" if i < 0 else i, key))


def test_a_sliding_replay_smokes(js):
    """`FLAG.DRIFT` is in every recording, and a slide on the road is smoke."""
    js.eval("watching([car(lap(0.5, FLAG.DRIFT, 40))]); play(4);")
    assert _puff(js) == "smoke"


def test_a_slide_on_the_grass_is_dust_and_not_smoke(js):
    """Which of the two it is, is a fact about the *track*, and the track is the
    one thing a replay has all of."""
    js.eval("watching([car(grassLap(0.5, FLAG.DRIFT))]); play(4);")
    assert _puff(js) == "dust"


def test_running_wide_trails_dust_without_sliding(js):
    """The second half of the rule: on the grass at any pace is dust, which is
    what a car that has simply run wide is doing."""
    js.eval("watching([car(grassLap(3, 0))]); play(4);")
    assert _puff(js) == "dust"


def test_a_car_crawling_on_the_grass_kicks_up_nothing(js):
    js.eval("watching([car(grassLap(0.05, 0))]); play(4);")
    assert js.eval("PUFFS.length") == 0


def test_a_car_in_the_air_leaves_no_tyre_marks(js):
    """Not grounded is not smoking, however sideways the byte says it was."""
    js.eval("watching([car(lap(0.5, FLAG.DRIFT | FLAG.AIR, 40))]); play(4);")
    assert js.eval("PUFFS.length") == 0


def test_a_paused_replay_stops_smoking(js):
    """The same frame drawn over and over, and a puff a frame would bury the
    still picture somebody paused to look at."""
    js.eval("watching([car(lap(0.5, FLAG.DRIFT, 40))]); play(4);"
            " S.watch.playing = false; PUFFS = []; play(8);")
    assert js.eval("PUFFS.length") == 0


def test_only_the_camera_car_smokes(js):
    """The rule the live track runs on - the one car making smoke is the one you
    are sitting in - and a budget as well as a rule: the pool is ninety
    particles and one sliding car fills a third of it."""
    js.eval("watching([car(lap(0.5, FLAG.DRIFT, 40)), car(lap(0.5, FLAG.DRIFT, 40))], 0);"
            " PUFFS = []; play(1);")
    assert js.eval("PUFFS.length") == 1


def test_the_ghost_you_are_chasing_smokes_too(js):
    """Where a ghost is sliding and where it has run wide are the two things
    about somebody else's lap you can read at a glance from behind it."""
    _ghost(js, "lap(0.5, FLAG.DRIFT, 40)")
    js.eval("PUFFS = []; ghostAir(0.9, new V3(4, 0, 0), new Q4(), 0.1);")
    assert _puff(js) == "smoke"
    # And it stops with the ghost, rather than smoking over the road it left.
    js.eval("PUFFS = []; ghostAir(null, null, null, 0.1);")
    assert js.eval("PUFFS.length") == 0
