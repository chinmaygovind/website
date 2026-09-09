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
    # Plus the one thing the bindings call that is a rule rather than a stub.
    # `restartOrRestore` is what decides whether the restart button goes back to
    # a save state or to the line, and it lives further down the file because
    # the R key shares it - so stubbing it here would leave the interesting half
    # of that button untested. Lifted whole, the same way test_panels.py lifts
    # the panel toggles: every function in game.js closes in column 0.
    # And the replay transport, for the same reason and a weaker one: it is
    # called from the foot of `bindInput` and it is not what any of these tests
    # are about, but a stub for it would be one more thing that can silently
    # stop matching the real function.
    return src[start:end] + "\n" + _fn(src, "restartOrRestore") + \
        "\n" + _fn(src, "wireTransport")


def _fn(src, name):
    """One top-level `function name(...)`, to its column-0 closing brace."""
    at = src.index("function %s(" % name)
    return src[at:re.compile(r"^\}$", re.M).search(src, at).end()]


# Enough DOM to hold listeners and classes, and nothing else. `$` hands back a
# stub for any id so the menu wiring at the end of bindInput is harmless.
STUB = r"""
var NOW = 0;
var performance = { now: function () { return NOW; } };
var location = { search: '' };
var els = {};
// Where the four driving buttons are on the glass. The slide between the two
// buttons of a pad is *measured* - a touch is delivered for its whole life to
// the element it went down on, so nothing in the browser will tell it which
// button a finger is over now - and that makes these rectangles part of what is
// under test rather than scenery. Two side-by-side pairs, laid out the way the
// pads are: the arrows on the left, the pedals on the right.
var RECTS = {
  tLeft: { left: 20, right: 120 },
  tRight: { left: 140, right: 240 },
  tBrake: { left: 500, right: 600 },
  tGas: { left: 620, right: 720 },
};
function El(id) {
  this.id = id; this.h = {}; this.cls = {}; this.style = {};
  this.getBoundingClientRect = () => RECTS[id] || { left: 0, right: 0 };
  this.classList = {
    add: (c) => this.cls[c] = 1,
    remove: (c) => delete this.cls[c],
    toggle: (c, v) => { if (v) this.cls[c] = 1; else delete this.cls[c]; },
    contains: (c) => !!this.cls[c],
  };
  this.querySelectorAll = () => [];
  this.addEventListener = (t, f) => { (this.h[t] = this.h[t] || []).push(f); };
  // `ev` carries the touch list for the drag gesture; the button bindings that
  // only care whether a thumb is down ignore it.
  this.fire = (t, ev) => (this.h[t] || []).forEach(f => f(
    Object.assign({ preventDefault() {} }, ev)));
}
function $(id) { if (!els[id]) els[id] = new El(id); return els[id]; }
var window = { addEventListener: function () {}, matchMedia: null };
var document = {
  addEventListener: function () {},
  querySelectorAll: function () { return { forEach: function () {} }; },
  body: { classList: { add: function () {} } },
};
var S = { sound: { start: function () {}, resume: function () {} }, touch: false,
          view: { setVisible: function () {} }, car: {}, showGhost: true,
          saveActive: -1 };
var CFG = { mode: 'solo' };
// Everything bindInput reaches for that is not the input handling itself. If a
// new one appears, the slice throws rather than silently testing nothing.
function backToCheckpoint() {} function toggleMenu() {}
function toggleHelp() {} function setSound() {} function showSide() {}
function resetToStart() {} function chooseGhost() {} function setGhostMode() {}
function toggleTracks() {} function toggleBoard() {} function openBoard() {}
function stopWatching() {} function renderTrackCards() {}
function renderSettings() {} function openChat() {} function closeChat() {}
function setGhostCar() {} function setMusic() {} function storedFlag() {}
// The two readouts. They are switches wired here beside Sound and Music, so
// they land in this slice for the same reason those two do.
function setFpsOn() {} function setPingOn() {}
// The save-state pair, counted rather than stubbed away, because whether a tap
// reaches them is the whole of `test_saving_works_with_a_thumb_on_the_throttle`.
var SAVED = 0, OPENED = 0;
function saveState() { SAVED++; }
function toggleSaves() { OPENED++; }
// The restart button's two jobs, recorded rather than performed.
var ACTS = [];
function restartRun() { ACTS.push('start'); }
function restoreState() { ACTS.push('restore'); }
function deactivateSave() { ACTS.push('off'); }
function savesEnabled() { return S.saveActive >= 0; }
"""

# A thumb: every press and release advances the clock by a millisecond, so the
# only thing that opens or closes the double-tap window is an explicit wait().
HARNESS = r"""
bindInput();
// A real touchstart always carries the finger that caused it, so the thumb here
// does too - the drag gesture reads its identifier and where it landed.
var Y0 = 500;
function at(y, x) {
  return { changedTouches: [{ identifier: 1, clientY: y, clientX: x }] };
}
// A thumb goes down in the middle of the button it is pressing, which is the
// only starting X that leaves the sideways gesture with nothing to say - so a
// vertical drag in these tests is a vertical drag and not a slide as well.
// The small buttons above the pads have no rectangle here, because nothing
// slides between them - they are taps. Zero is as good a place as any for a
// thumb that no sideways gesture is watching.
function mid(id) {
  var r = RECTS[id];
  return r ? (r.left + r.right) / 2 : 0;
}
function press(id) { NOW += 1; $(id).fire('touchstart', at(Y0, mid(id))); }
function release(id) { NOW += 1; $(id).fire('touchend', at(Y0, mid(id))); }
// Distances are fractions of the threshold rather than pixel counts, so
// retuning DRAG_DRIFT retunes the tests instead of quietly invalidating them.
function dragBy(id, px) { NOW += 1; $(id).fire('touchmove', at(Y0 + px, mid(id))); }
// The sideways one. `slideTo` is a thumb arriving in the middle of the other
// button of the pad without ever having left the glass; `slideX` puts it at an
// exact place, which is how the hysteresis is measured.
function slideX(id, x) { NOW += 1; $(id).fire('touchmove', at(Y0, x)); }
function slideTo(from, to) { slideX(from, mid(to)); }
function liftAt(id) { NOW += 1; $(id).fire('touchend', at(Y0, mid(id))); }
function boundary(a, b) { return (RECTS[a].right + RECTS[b].left) / 2; }
function wait(ms) { NOW += ms; }
// Expressed against the window rather than in fixed milliseconds, so retuning
// DOUBLE_TAP retunes the tests instead of silently invalidating them.
function quick() { wait(Math.max(1, Math.round(DOUBLE_TAP * 0.4))); }
function slow() { wait(DOUBLE_TAP * 4 + 100); }
// The restart button has a window of its own, and it is much longer than the
// steering one - expressed against the constant so retuning it retunes these.
function quickTap() { wait(Math.round(RESTART_DOUBLE_TAP * 0.4)); }
function slowTap() { wait(RESTART_DOUBLE_TAP * 2); }
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
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      [drifting_(), held(), lit('tLeft')].join('|');
    """) == "true|drift,left|true"


def test_either_arrow_drifts_on_its_own_double_tap():
    assert run("""
      press('tRight'); release('tRight'); quick(); press('tRight');
      [drifting_(), held()].join('|');
    """) == "true|drift,right"


def test_letting_go_of_the_arrow_lets_go_of_the_handbrake():
    """Which is also how you catch the slide, so it has to be immediate."""
    assert run("""
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      release('tLeft');
      [drifting_(), held(), lit('tLeft')].join('|');
    """) == "false||false"


def test_a_slow_second_press_is_not_a_double_tap():
    assert run("""
      press('tLeft'); release('tLeft'); slow(); press('tLeft');
      drifting_();
    """) is False


def test_re_grabbing_the_same_arrow_mid_corner_is_not_a_double_tap():
    """The failure that set the window where it is.

    Coming off an arrow and putting it straight back on is an ordinary
    correction, made constantly, on the same arrow - which is the exact shape of
    the gesture. At a relaxed window it fired on half of them and the car spent
    the corner sideways. So the window has to be shorter than a thumb adjusting
    its grip, which is what 150ms is standing in for here: a deliberate
    double-tap is much faster than a correction, and nothing else is.
    """
    assert run("""
      press('tLeft'); release('tLeft'); wait(150); press('tLeft');
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
      press('{a}'); release('{a}'); quick();
      press('{b}'); release('{b}'); quick();
      press('{a}');
      drifting_();
    """) is False


def test_counter_steering_out_of_a_drift_drops_the_handbrake():
    assert run("""
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      press('tRight');
      release('tLeft');
      [drifting_(), held()].join('|');
    """) == "false|right"


def test_the_throttle_survives_starting_a_drift():
    """The whole point of putting the gesture on the steering thumb."""
    assert run("""
      press('tGas');
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      [drifting_(), held()].join('|');
    """) == "true|drift,left,up"


@pytest.mark.parametrize("pedal", ["tBrake", "tGas"])
def test_a_pedal_never_drifts_however_fast_you_tap_it(pedal):
    """The gesture used to live on the brake. Tapping a pedal is now just tapping
    a pedal, so stabbing the brake into a corner cannot start a slide."""
    assert run(f"""
      press('{pedal}'); release('{pedal}'); quick(); press('{pedal}');
      drifting_();
    """) is False


def test_a_cancelled_touch_releases_the_handbrake():
    """A notification tray or a palm can cancel a touch mid-corner; the car must
    not be left with the handbrake on and no way to let it off."""
    assert run("""
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      $('tLeft').fire('touchcancel');
      [drifting_(), held()].join('|');
    """) == "false|"


# ---------------------------------------------------------------------------
# The other way in: drag the throttle down
# ---------------------------------------------------------------------------

def test_dragging_the_throttle_down_pulls_the_handbrake():
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT);
      [drifting_(), lit('tGas')].join('|');
    """) == "true|true"


def test_the_throttle_stays_open_through_the_drag():
    """The entire reason this gesture can live on the pedal thumb.

    Every earlier candidate for that thumb charged it a release, and coming off
    the power mid-corner is the one thing it must never do. A drag costs
    nothing: the slide arrives under throttle, which is how the turn is driven.
    """
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT * 2);
      held();
    """) == "drift,up"


def test_a_short_drag_is_not_a_drift():
    """A thumb rolls and settles on a pedal it holds all lap. That is not a
    request for the handbrake, and it happens constantly."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT - 1);
      drifting_();
    """) is False


def test_dragging_up_the_throttle_never_drifts():
    """Down is the direction the lever comes up, and it is the only one."""
    assert run("""
      press('tGas'); dragBy('tGas', -DRAG_DRIFT * 3);
      drifting_();
    """) is False


def test_sliding_back_up_lets_the_handbrake_off():
    """Same as letting go of the arrow: you catch the slide by undoing the ask."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT);
      dragBy('tGas', 0);
      [drifting_(), held(), lit('tGas')].join('|');
    """) == "false|up|false"


def test_the_handbrake_does_not_chatter_on_the_threshold():
    """A thumb parked on the boundary would otherwise flick it on and off under
    itself, which is a car that will not settle rather than a car sliding."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT);
      dragBy('tGas', (DRAG_DRIFT + DRAG_KEEP) / 2);
      drifting_();
    """) is True


def test_letting_go_of_the_pedal_lets_go_of_the_drift():
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT * 2);
      release('tGas');
      [drifting_(), held(), lit('tGas')].join('|');
    """) == "false||false"


def test_a_cancelled_pedal_touch_releases_the_drift():
    """A palm or a notification tray must not leave the car held sideways."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT * 2);
      $('tGas').fire('touchcancel');
      [drifting_(), held()].join('|');
    """) == "false|"


def test_a_drag_on_the_brake_is_not_a_drift():
    """Only the throttle carries the gesture. Braking into a corner already
    moves the thumb about, and that was the failure of `brake while steering`."""
    assert run("""
      press('tBrake'); dragBy('tBrake', DRAG_DRIFT * 3);
      drifting_();
    """) is False


def test_the_two_gestures_do_not_interfere():
    """They are for different hands, so both can be going at once, and letting
    go of one must not let go of the other's handbrake."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT * 2);
      press('tLeft'); release('tLeft'); quick(); press('tLeft');
      release('tLeft');
      [drifting_(), held()].join('|');
    """) == "true|drift,up"


# ---------------------------------------------------------------------------
# The save-state buttons, with a thumb already on the throttle
# ---------------------------------------------------------------------------

def test_the_save_buttons_are_bound_on_touch_and_not_on_click():
    """**They were `onclick`, and on a phone that meant they did nothing.**

    Every other button on these pads binds `touchstart` and calls
    `preventDefault()` - which is exactly what suppresses the synthetic click
    that `onclick` is waiting for. So with a thumb held on the throttle, tapping
    Create Save State or Manage Save States registered nothing at all, which is
    the only way anybody would ever use them: you cannot save where you are
    without being somewhere, and being somewhere means holding the accelerator.

    Asserted on the *binding* rather than only on the effect, because the effect
    can be reached by either wiring in a stub that fakes a click - and it is the
    wiring that was wrong.
    """
    # Joined into a string, like `held()` above: an array comes back from
    # QuickJS as an opaque object rather than as a list.
    got = run("['tSaveNew', 'tSaves'].map(i =>"
              " i + ':' + (($(i).h.touchstart || []).length ? 'touch' : 'NONE')).join(' ')")
    assert got == "tSaveNew:touch tSaves:touch"


def test_saving_works_with_a_thumb_on_the_throttle():
    """The reported bug, as a sequence: hold the pedal, tap the button twice,
    open the panel, never letting go."""
    got = run("""
      press('tGas');
      press('tSaveNew'); release('tSaveNew');
      press('tSaveNew'); release('tSaveNew');
      press('tSaves');   release('tSaves');
      SAVED + ',' + OPENED + ',' + held()
    """)
    # The third field is the throttle, still held. Without it this proves
    # nothing: a tap with no other finger down worked even before the fix.
    assert got == "2,1,up"


def test_tapping_a_save_button_does_not_disturb_the_pedals():
    """A second finger must not let go of the first. `tb` adds and removes only
    its own button's state, but these two pass an empty `off`, so a mistake here
    would look like the throttle cutting out when you save."""
    got = run("""
      press('tGas'); press('tBrake');
      press('tSaveNew'); release('tSaveNew');
      held()
    """)
    assert got == "down,up"


# ---------------------------------------------------------------------------
# The restart button, once practice states exist
# ---------------------------------------------------------------------------

def _restart(script):
    return run("ACTS = []; " + script + " ACTS.join(',')")


def test_the_restart_button_still_restarts_with_no_save_state():
    """Nothing about practice mode may change the button for somebody who has
    never used it. Two taps is then simply two restarts."""
    assert _restart("S.saveActive = -1; press('tRestart'); release('tRestart');") == "start"
    assert _restart("S.saveActive = -1;"
                    " press('tRestart'); release('tRestart');"
                    " press('tRestart'); release('tRestart');") == "start,start"


def test_a_tap_goes_back_to_the_save_state():
    """**The gap this closes.** The touch button called `restartRun` straight
    out, so with a save state active it sent you to the line when you wanted the
    corner - on the one device where opening the panel instead is most
    expensive, and where not driving the lap again is the entire point."""
    assert _restart("S.saveActive = 0; press('tRestart'); release('tRestart');") == "restore"


def test_two_quick_taps_turn_practice_off():
    """What Shift+R does, for a device with no Shift.

    The first tap still restores - deferring it to find out whether a second is
    coming would put a third of a second of lag on the most-pressed button in
    the game - so the sequence is restore then off, and where you end up is the
    start line."""
    got = _restart("S.saveActive = 0;"
                   " press('tRestart'); release('tRestart');"
                   " quickTap();"
                   " press('tRestart'); release('tRestart');")
    assert got == "restore,off"


def test_two_slow_taps_are_two_restores_and_not_a_deactivate():
    """Coming back to the same corner twice is the single most common thing
    anybody does with this feature, so it must not be mistaken for asking to
    leave practice mode."""
    got = _restart("S.saveActive = 0;"
                   " press('tRestart'); release('tRestart');"
                   " slowTap();"
                   " press('tRestart'); release('tRestart');")
    assert got == "restore,restore"


# ---------------------------------------------------------------------------
# Sliding between the two buttons of a pad
# ---------------------------------------------------------------------------
#
# The objection this answers is `dragDrift`'s, one step further on. Every way of
# getting from the throttle to the brake, or from one arrow to the other,
# charged the thumb a *release* - lift, find the other button, land on it - and
# for the half-second that takes the car is doing neither. Going from power to
# brakes at the end of a straight is the most common transition there is, and it
# was the one the phone made hardest.
#
# The boundary is the midpoint between the two buttons, measured on X, because a
# touch is delivered for its whole life to the element it went down on and
# nothing in the browser will say which button it is over now.


def test_sliding_from_the_throttle_to_the_brake_brakes():
    """The whole point: the thumb never leaves the glass and the car goes from
    full throttle to full brakes."""
    assert run("press('tGas'); slideTo('tGas', 'tBrake'); held();") == "down"


def test_sliding_back_returns_the_throttle():
    assert run("""
      press('tGas'); slideTo('tGas', 'tBrake'); slideTo('tGas', 'tGas'); held();
    """) == "up"


def test_lifting_after_a_slide_leaves_nothing_held():
    """`tb`'s own release only knows about the button the thumb went *down* on,
    so without the slide's own release a thumb that slid to the brake and lifted
    would leave the brake on for the rest of the lap - which is the worst way
    for this feature to fail, and silent."""
    assert run("""
      press('tGas'); slideTo('tGas', 'tBrake'); liftAt('tGas'); held();
    """) == ""


def test_the_arrows_slide_too():
    """Left to right without a lift is the correction you make mid-corner, and
    it is the same gesture on the other thumb."""
    assert run("press('tLeft'); slideTo('tLeft', 'tRight'); held();") == "right"


def test_a_thumb_on_the_boundary_does_not_chatter():
    """`SLIDE_HYST`'s reason, and `DRAG_KEEP`'s: a pedal that swapped under a
    thumb resting on the line would be the car alternating between full throttle
    and full brakes several times a second."""
    assert run("""
      press('tGas');
      slideX('tGas', boundary('tBrake', 'tGas') + SLIDE_HYST - 1);
      held();
    """) == "up"
    # And past it, it does hand over.
    assert run("""
      press('tGas');
      slideX('tGas', boundary('tBrake', 'tGas') - SLIDE_HYST - 1);
      held();
    """) == "down"


def test_a_slide_is_not_a_drift():
    """The two gestures are on one thumb and one of them must not be able to
    fire the other. They are orthogonal on purpose - sideways hands the pedal
    over, downwards pulls the handbrake - and this is that said as a test."""
    assert run("""
      press('tGas'); slideTo('tGas', 'tBrake'); [drifting_(), held()].join('|');
    """) == "false|down"


def test_sliding_off_the_throttle_drops_a_drift_it_was_holding():
    """The handbrake belonged to the throttle, and the thumb is not on the
    throttle any more. Leaving it on would be a slide nobody is asking for held
    by a finger that has gone somewhere else."""
    assert run("""
      press('tGas'); dragBy('tGas', DRAG_DRIFT);
      slideTo('tGas', 'tBrake');
      [drifting_(), held()].join('|');
    """) == "false|down"


def test_arriving_on_the_throttle_from_below_does_not_arrive_drifting():
    """A thumb that goes to the brake and comes back has travelled a long way
    down the glass on the way. Handing it back the origin it went down with
    would start a slide it never asked for, so the drag is re-based where the
    thumb actually landed."""
    assert run("""
      press('tGas');
      slideX('tGas', mid('tBrake'));
      $('tGas').fire('touchmove', at(Y0 + DRAG_DRIFT * 3, mid('tGas')));
      drifting_();
    """) is False


def test_the_handbrake_still_works_from_the_pedal_the_thumb_slid_to():
    """Re-based, not taken away: the drag is still there on the pedal the thumb
    has arrived at, measured from where it arrived."""
    assert run("""
      press('tBrake');
      slideX('tBrake', mid('tGas'));
      $('tGas').fire('touchmove', at(Y0 + DRAG_DRIFT, mid('tGas')));
      [drifting_(), held()].join('|');
    """) == "true|drift,up"


def test_a_second_thumb_is_not_released_by_the_first_one_lifting():
    """Two thumbs on one pad is two touches with two identifiers, and a release
    must only ever let go of the button its own finger is holding."""
    assert run("""
      press('tLeft');
      $('tRight').fire('touchstart',
        { changedTouches: [{ identifier: 2, clientY: Y0, clientX: mid('tRight') }] });
      release('tLeft');
      held();
    """) == "right"


def test_the_pedals_are_a_readout_during_a_replay():
    """Watching is not driving. The four driving buttons are lit by the
    recording rather than by a thumb, so a press on one has to do nothing at all
    - otherwise the phone would be steering a parked car while the button under
    the thumb says the driver in the replay is turning the other way."""
    assert run("S.watch = {}; press('tGas'); held();") == ""
    assert run("S.watch = {}; press('tLeft'); slideTo('tLeft', 'tRight'); held();") == ""


def test_the_small_buttons_stay_live_during_a_replay():
    """Restarting and going back to a checkpoint are things you do to a replay
    too, and on a phone these are the only doors to them."""
    assert run("S.watch = {}; ACTS = []; S.saveActive = -1;"
               " press('tRestart'); release('tRestart'); ACTS.join(',')") == "start"
