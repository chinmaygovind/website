"""The phone handbrake gesture, driven through the game's own input bindings.

The handbrake is the one control on a phone that is not a button, so it is the
one control that can fire when nobody asked for it - and the place it would fire
is mid-corner, with a thumb already busy saving the car. That is worth pinning.

`test_sim.py` bundles the simulation modules; this cannot use that bundle because
the bindings live in `game.js`, which imports the renderer and calls `boot()` at
the end of the file. So it lifts one contiguous slice - the touch-input state
through the end of `bindInput` - and runs it against a DOM stub small enough to
read: elements that only remember their listeners and classes, and a clock the
test moves by hand so the double-tap window is exact rather than raced.
"""

import os
import re

import pytest

from jsrt import HAVE_QUICKJS, JS

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")


def _input_bindings():
    """`game.js` from the touch-input state through the end of `bindInput`.

    Located by markers rather than line numbers, and bounded by the first
    top-level `}` after `bindInput` - every function in the file closes in
    column 0, so this needs no brace matching.
    """
    src = open(os.path.join(JS, "game.js")).read()
    start = src.index("const input = {")
    body = src.index("function bindInput() {", start)
    end = re.compile(r"^\}$", re.M).search(src, body).end()
    return src[start:end]


# Enough DOM to hold listeners and classes, and nothing else. `$` hands back a
# stub for any id so the menu wiring at the end of bindInput is harmless.
STUB = r"""
var NOW = 0;
var performance = { now: function () { return NOW; } };
var location = { search: '' };
var els = {};
function El(id) {
  this.id = id; this.h = {}; this.cls = {}; this.style = {};
  this.classList = {
    add: (c) => this.cls[c] = 1,
    remove: (c) => delete this.cls[c],
    toggle: (c, v) => { if (v) this.cls[c] = 1; else delete this.cls[c]; },
    contains: (c) => !!this.cls[c],
  };
  this.querySelectorAll = () => [];
  this.addEventListener = (t, f) => { (this.h[t] = this.h[t] || []).push(f); };
  this.fire = (t) => (this.h[t] || []).forEach(f => f({ preventDefault() {} }));
}
function $(id) { if (!els[id]) els[id] = new El(id); return els[id]; }
var window = { addEventListener: function () {}, matchMedia: null };
var document = {
  addEventListener: function () {},
  querySelectorAll: function () { return { forEach: function () {} }; },
  body: { classList: { add: function () {} } },
};
var S = { sound: { start: function () {}, resume: function () {} }, touch: false,
          view: { setVisible: function () {} }, car: {} };
var CFG = { mode: 'solo' };
// Everything bindInput reaches for that is not the input handling itself. If a
// new one appears, the slice throws rather than silently testing nothing.
function backToCheckpoint() {} function restartRun() {} function toggleMenu() {}
function toggleHelp() {} function setSound() {} function showSide() {}
function resetToStart() {} function chooseGhost() {} function setGhostMode() {}
function toggleTracks() {} function toggleBoard() {} function openBoard() {}
function stopWatching() {} function renderTrackCards() {}
"""

# A thumb: every press and release advances the clock by a millisecond, so the
# only thing that opens or closes the double-tap window is an explicit wait().
HARNESS = r"""
bindInput();
function press(id) { NOW += 1; $(id).fire('touchstart'); }
function release(id) { NOW += 1; $(id).fire('touchend'); }
function wait(ms) { NOW += ms; }
function held() { var a = []; touchKeys.forEach(k => a.push(k)); return a.sort().join(','); }
function drifting_() { return touchKeys.has('drift'); }
function lit(id) { return $(id).classList.contains('drifting'); }
"""


def run(script):
    import quickjs
    return quickjs.Context().eval(STUB + _input_bindings() + HARNESS + script)


def test_a_single_press_just_steers():
    """The common case by a distance: one arrow, held through a corner."""
    assert run("press('tLeft'); [drifting_(), held()].join('|');") == "false|left"


def test_double_tap_and_hold_an_arrow_is_the_handbrake():
    assert run("""
      press('tLeft'); release('tLeft'); wait(100); press('tLeft');
      [drifting_(), held(), lit('tLeft')].join('|');
    """) == "true|drift,left|true"


def test_either_arrow_drifts_on_its_own_double_tap():
    assert run("""
      press('tRight'); release('tRight'); wait(100); press('tRight');
      [drifting_(), held()].join('|');
    """) == "true|drift,right"


def test_letting_go_of_the_arrow_lets_go_of_the_handbrake():
    """Which is also how you catch the slide, so it has to be immediate."""
    assert run("""
      press('tLeft'); release('tLeft'); wait(100); press('tLeft');
      release('tLeft');
      [drifting_(), held(), lit('tLeft')].join('|');
    """) == "false||false"


def test_a_slow_second_press_is_not_a_double_tap():
    assert run("""
      press('tLeft'); release('tLeft'); wait(600); press('tLeft');
      drifting_();
    """) is False


@pytest.mark.parametrize("a,b", [("tLeft", "tRight"), ("tRight", "tLeft")])
def test_a_correction_the_other_way_is_not_a_double_tap(a, b):
    """left-right-left is saving the car, not asking for the handbrake.

    It is fast, it is common, and it ends on the arrow you started on - so
    without a shared window it would look exactly like the gesture, and would
    fire it at the worst possible moment. A press on either arrow voids the
    other's window; only arrow-nothing-arrow counts.
    """
    assert run(f"""
      press('{a}'); release('{a}'); wait(40);
      press('{b}'); release('{b}'); wait(40);
      press('{a}');
      drifting_();
    """) is False


def test_counter_steering_out_of_a_drift_drops_the_handbrake():
    assert run("""
      press('tLeft'); release('tLeft'); wait(60); press('tLeft');
      press('tRight');
      release('tLeft');
      [drifting_(), held()].join('|');
    """) == "false|right"


def test_the_throttle_survives_starting_a_drift():
    """The whole point of putting the gesture on the steering thumb."""
    assert run("""
      press('tGas');
      press('tLeft'); release('tLeft'); wait(60); press('tLeft');
      [drifting_(), held()].join('|');
    """) == "true|drift,left,up"


@pytest.mark.parametrize("pedal", ["tBrake", "tGas"])
def test_a_pedal_never_drifts_however_fast_you_tap_it(pedal):
    """The gesture used to live on the brake. Tapping a pedal is now just tapping
    a pedal, so stabbing the brake into a corner cannot start a slide."""
    assert run(f"""
      press('{pedal}'); release('{pedal}'); wait(50); press('{pedal}');
      drifting_();
    """) is False


def test_a_cancelled_touch_releases_the_handbrake():
    """A notification tray or a palm can cancel a touch mid-corner; the car must
    not be left with the handbrake on and no way to let it off."""
    assert run("""
      press('tLeft'); release('tLeft'); wait(60); press('tLeft');
      $('tLeft').fire('touchcancel');
      [drifting_(), held()].join('|');
    """) == "false|"
