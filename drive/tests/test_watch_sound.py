"""A replay you can hear, and a replay you can read the driver's hands off.

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

Driven rather than read, like `test_panels.py` and `test_touch.py`: `inputsOf`,
`paintInputs` and `updateWatch` are lifted out of `game.js` by name and run
against stubs, because what is under test is the mapping from a recorded frame
to an engine note and a lit key.
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
        _fn(src, "padUnder"),
        _fn(src, "padCrossed"),
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
V3.prototype.lerpVectors = function (a, b, u) {
  this.x = a.x + (b.x - a.x) * u; this.y = a.y + (b.y - a.y) * u;
  this.z = a.z + (b.z - a.z) * u; return this;
};
function Q4() {} Q4.prototype.normalize = function () { return this; };
var THREE = { Vector3: V3, Quaternion: Q4 };
var T = { MAX_SPEED: 50, PROBE: 2.6, RIDE_HEIGHT: 0.45, SNAP: 0.12, PAD_BOOST: 1.3 };
var FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };
var KIND = { ROAD: 0, WALL: 1, OFFROAD: 2, BOOST: 3, BOUNCE: 4 };
// One boost pad, two units of it, lying across the lap at x 2..4 - and a road
// that never runs out, so anywhere else is a surface the car is on and not a
// hole it is falling through.
var PAD = [2, 4];
// Every whoosh, and the level the rushing air was last left at.
var WHOOSH = 0, AIR = [], KICKS = 0;
var S = {
  watch: null,
  sound: {
    engine: function (sf, th, sl, air) { HEARD.push({ sf: sf, th: th, sl: sl, air: !!air }); },
    draft: function (charge, boost) { AIR.push(boost); },
    boostPad: function () { WHOOSH++; },
  },
  renderer: { kick: function () { KICKS++; } },
  built: { collider: { ground: function (x, y, z) {
    return { hit: true, dist: T.RIDE_HEIGHT,
             kind: (x >= PAD[0] && x <= PAD[1]) ? KIND.BOOST : KIND.ROAD };
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
  return { g: { at: function (t) {
                  var q = t * 10, i = Math.floor(q), u = q - i;
                  var a = frames[i], b = frames[i + 1];
                  if (!a) return null;
                  if (!b) return a;
                  var out = a.slice();
                  out[0] = a[0] + (b[0] - a[0]) * u;
                  return out;
                },
                hz: 10 },
           view: { update: function () {}, group: {} }, prev: null,
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
  LIT = {}; AMBER = {}; WHOOSH = 0; AIR = []; KICKS = 0;
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


def test_a_seek_is_not_a_stretch_of_road(js):
    """`padCrossed` samples the ground the car covered, because the film's step
    is not the simulation's and a short pad can sit wholly between two frames of
    a 4x replay. A scrub moves the car by more than any frame can, and sampling
    *that* line is a probe of wherever the track happens to lie between two
    unrelated places - which fired the whoosh for a pad nobody drove over."""
    assert js.eval("padCrossed(new V3(-100, 0, 0), new V3(100, 0, 0), new V3(0, 1, 0))") is False
    # But the ground a frame really covers is sampled along, not at its ends:
    # a car at 4x steps over a two-unit pad in one frame.
    assert js.eval("padCrossed(new V3(0, 0, 0), new V3(6, 0, 0), new V3(0, 1, 0))") is True


def test_a_car_that_runs_out_takes_its_boost_with_it(js):
    """A lap shorter than the replay stops existing partway through, and
    nothing else in there would ever close the band again."""
    js.eval("watching([car(lap(0.5, 0, 6))]); play(4);")
    assert js.eval("S.watch.subject.padBoost") > 0
    js.eval("play(4);")
    assert js.eval("S.watch.subject.padBoost") == 0
    assert js.eval("AIR[AIR.length - 1]") == 0
