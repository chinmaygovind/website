"""A replay you can hear: the car you are watching sounds like the car it was.

Watching used to be silent about the thing on the screen and loud about the
thing that was not - your own parked car went on making whatever noise it had
been making when you pressed Watch, and the lap actually being played made
none. Both halves are the same fact: nothing steps a car during a replay, so
the only thing that knows what the watched car is doing is the replay itself.

It knows plenty. A ghost frame carries the pose *and* the flag byte the lap was
recorded with (`Run._recordGhost`), which is the same byte the live cars put on
the wire - braking, sliding, airborne - so the engine note can be driven from a
recording exactly the way it is driven from a rival.

Driven rather than read, like `test_panels.py` and `test_touch.py`:
`updateWatch` is lifted out of `game.js` by name and run against stubs, because
what is under test is the mapping from a recorded frame to an engine note.
"""

import os
import re

import pytest

from jsrt import HAVE_QUICKJS, JS, quickjs

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")

DT = 0.1                       # one stubbed frame, and the clock the speed is per
FLAG = {"DRIFT": 1, "AIR": 2, "RESPAWN": 4, "BRAKE": 8, "SLIP": 16}


def _update_watch():
    src = open(os.path.join(JS, "game.js")).read()
    start = src.index("function updateWatch(")
    return src[start:re.compile(r"^\}$", re.M).search(src, start).end()]


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
function Q4() {} Q4.prototype.normalize = function () { return this; };
var THREE = { Vector3: V3, Quaternion: Q4 };
var T = { MAX_SPEED: 50 };
var FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };
var S = { watch: null, sound: { engine: function (sf, th, sl, air) {
  HEARD.push({ sf: sf, th: th, sl: sl, air: !!air });
} } };
function $() { return { textContent: '' }; }
function fmt() { return ''; }
function lampsOf() { return {}; }

// A lap along +X at a fixed spacing, so the speed the camera measures is the
// spacing over the frame time - and, with `wide` false, one recorded before the
// flag byte existed.
function lap(step, flags, n, wide) {
  var out = [];
  for (var i = 0; i < (n || 8); i++) {
    var f = [i * step, 0, 0, 0, 0, 0, 1];
    if (wide !== false) f.push(flags | 0);
    out.push(f);
  }
  return out;
}
function car(frames) {
  return { g: { at: function (t) { return frames[Math.round(t * 10)] || null; } },
           view: { update: function () {}, group: {} }, prev: null };
}
function watching(cars, at) {
  S.watch = { cars: cars, at: at || 0, t: 0, dur: 1e6,
              subject: { pos: new V3(), fwd: new V3(), up: new V3(), speed: 0 },
              title: null };
}
// Two frames, because a speed is measured between them: the first has nothing
// to measure against and is honestly zero.
function play(n) { for (var i = 0; i < (n || 2); i++) updateWatch(0.1); }
"""


@pytest.fixture()
def js():
    c = quickjs.Context()
    c.eval(STUB)
    c.eval(_update_watch())
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


def test_a_lap_that_runs_out_goes_quiet(js):
    """A replay is as long as its longest car, so the one you are watching can
    stop existing partway through - and nothing else in there would ever move
    its engine again."""
    js.eval("watching([car(lap(0.5, 0, 3))]); play(6);")
    assert _last(js, "sf") == 0 and _last(js, "th") == 0
