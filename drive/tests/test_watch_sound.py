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
    # The three that turn a frame into what you hear and what you see, plus the
    # table that says which element each bit lights - which is lifted rather
    # than restated, so a bit added to one and not the other fails here.
    keys = src.index("const INPUT_KEYS = [")
    return "\n".join([
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
function Q4() {} Q4.prototype.normalize = function () { return this; };
var THREE = { Vector3: V3, Quaternion: Q4 };
var T = { MAX_SPEED: 50 };
var FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };
var S = { watch: null, sound: { engine: function (sf, th, sl, air) {
  HEARD.push({ sf: sf, th: th, sl: sl, air: !!air });
} } };
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
              subject: { pos: new V3(), fwd: new V3(), up: new V3(), speed: 0 },
              title: null, playing: true, rate: 1, shown: -1 };
  LIT = {}; AMBER = {};
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


def test_the_space_bar_is_the_handbrake_and_goes_amber(js):
    """The one key on the pad that is a request rather than a direction, and it
    is coloured like the touch button is for the same reason: a slide drawn in
    the colour of a held throttle is a slide you cannot see."""
    js.eval("watching([car(lap(0.5, 0, 8, true, IN.HANDBRAKE), true)]); play();")
    assert _lit(js, "kSpace")
    assert js.eval("!!AMBER['kSpace']")


def test_an_old_lap_infers_the_hands_from_the_car(js):
    """Eight wide, so there is nothing to read: the throttle is not-braking-and-
    moving, which is the rule the engine note already uses, and the handbrake is
    the car sliding."""
    js.eval("watching([car(lap(0.5, 0))]); play();")
    assert _lit(js, "kUp") and not _lit(js, "kDown") and not _lit(js, "kSpace")

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.BRAKE))]); play();")
    assert _lit(js, "kDown") and not _lit(js, "kUp")

    js.eval("HEARD = []; watching([car(lap(0.5, FLAG.DRIFT))]); play();")
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
