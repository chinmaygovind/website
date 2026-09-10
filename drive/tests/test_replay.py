"""The replay transport: play, seek, speed, checkpoints, and C from a replay.

Watching used to be a clock that ran and looped, which is the whole of what a
ghost car needs and much less than watching somebody's lap wants: the corner you
are trying to see goes past in a fifth of a second at racing speed, and the only
way back to it was to sit through the rest of the lap. So there is a transport
now - `playing`, `t` and `rate` - and everything on the bar reads those three.

Two of the rules here are worth stating before the tests do.

**Nothing writes `w.t` except `watchSeek` and the one line in `updateWatch` that
advances it.** Six things move the clock (the bar, the play button, R, T, the
seek keys, a save state) and a transport where each of them nudged the number
itself is a transport where one of them forgets to reset the per-car `prev` and
the engine screams for a frame.

**A seek pauses and does not un-pause.** You moved the film to look at
something, and running on from where you stopped is the picture being taken away
again.

Driven rather than read, like `test_panels.py` and `test_watch_sound.py`: the
functions are lifted out of `game.js` by name and run against stubs.
"""

import os
import re

import pytest

from jsrt import HAVE_QUICKJS, JS, quickjs

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")


def _fn(src, name):
    """One top-level function, to its column-0 closing brace.

    The `async` is part of it. Slicing from `function <name>(` drops that
    keyword, and a function body with an `await` in it and no `async` on the
    front is a **syntax error** rather than a wrong answer - so this fails loudly
    the moment somebody lifts an async one, which is exactly what happened.
    """
    at = src.index("function %s(" % name)
    if src[max(0, at - 6):at] == "async ":
        at -= 6
    return src[at:re.compile(r"^\}$", re.M).search(src, at).end()]


def _transport():
    src = open(os.path.join(JS, "game.js")).read()
    names = ["watchSeek", "watchPlay", "setReplayRate", "stepReplayRate",
             "toggleRates", "syncWatchUi", "watchLastCheckpoint", "replayKey",
             "replayGates", "drawScrubTicks"]
    rates = src.index("const REPLAY_RATES = [")
    return "\n".join([src[rates:src.index("\n", rates)]] +
                     [_fn(src, n) for n in names])


# Enough of a page for the transport to run against. `$` hands back a stub for
# any id, because what is under test is the state rather than the paint.
STUB = r"""
var GHOST_RATE = 15;
var TOASTS = [];
function toast(m) { TOASTS.push(m); }
function fmt(ms) { return String(Math.round(ms)); }
function $(id) {
  return {
    textContent: '', innerHTML: '',
    style: { display: 'none', width: '', setProperty: function () {} },
    setAttribute: function () {},
    classList: { toggle: function () {} },
    querySelectorAll: function () { return { forEach: function () {} }; },
  };
}
var S = { watch: null, course: null, built: null };
// A replay of `dur` seconds with checkpoints at `gates`.
function watching(dur, gates) {
  S.watch = {
    cars: [{ g: { hz: 15, duration: dur }, prev: {}, gates: gates || [] }],
    at: 0, t: 0, dur: dur, playing: true, rate: 1, shown: 7,
  };
  return S.watch;
}
function key(code) { return replayKey({ code: code, preventDefault: function () {} }); }
"""


@pytest.fixture()
def js():
    c = quickjs.Context()
    c.eval(STUB)
    c.eval(_transport())
    return c


# ---------------------------------------------------------------------------
# Seeking
# ---------------------------------------------------------------------------

def test_a_seek_is_clamped_to_the_lap(js):
    """The bar is a percentage of a drag that can leave the bar, and the keys
    step by five seconds from wherever they are - so both ends are reachable by
    ordinary use rather than by anything unusual."""
    js.eval("watching(20); watchSeek(-5);")
    assert js.eval("S.watch.t") == 0
    js.eval("watchSeek(9999);")
    assert js.eval("S.watch.t") == 20


def test_a_seek_forgets_the_frame_before(js):
    """A car's speed is measured from the previous frame, and a jump has no
    previous frame. Left alone it reads the distance jumped as speed, which is a
    scrub to the far end heard as an engine at several thousand km/h."""
    js.eval("watching(20); watchSeek(5);")
    assert js.eval("S.watch.cars[0].prev") is None
    # And the pad is redrawn rather than left showing the keys from before the
    # jump: `shown` is the byte it last painted.
    assert js.eval("S.watch.shown") == -1


def test_seeking_to_the_end_stops(js):
    """Landing exactly on the flag with the transport still running would play
    one frame and stop again. Arriving at the end is the end."""
    js.eval("watching(20); watchSeek(20);")
    assert js.eval("S.watch.playing") is False


def test_play_at_the_flag_starts_again_from_the_line(js):
    """The button looks like it should do something, so it does. The
    alternative is a play button that is dead exactly when it is most obviously
    pressable."""
    js.eval("watching(20); watchSeek(20); watchPlay(true);")
    assert js.eval("S.watch.t") == 0
    assert js.eval("S.watch.playing") is True


def test_play_and_pause_is_a_toggle_and_not_a_seek(js):
    js.eval("watching(20); watchSeek(7); watchPlay(true);")
    assert js.eval("S.watch.t") == 7 and js.eval("S.watch.playing") is True
    js.eval("watchPlay(false);")
    assert js.eval("S.watch.t") == 7 and js.eval("S.watch.playing") is False


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------

def test_the_speeds_are_stepped_through_rather_than_scaled(js):
    """A speed you scrubbed to is a speed nobody chose, and 1.37x reads as a
    fault. Up and down move through the seven."""
    js.eval("watching(20); stepReplayRate(1);")
    assert js.eval("S.watch.rate") == 1.5
    js.eval("stepReplayRate(-1); stepReplayRate(-1);")
    assert js.eval("S.watch.rate") == 0.5


def test_the_speed_stops_at_both_ends(js):
    js.eval("watching(20); for (var i = 0; i < 20; i++) stepReplayRate(1);")
    assert js.eval("S.watch.rate") == 4
    js.eval("for (var i = 0; i < 20; i++) stepReplayRate(-1);")
    assert js.eval("S.watch.rate") == 0.1


def test_every_offered_speed_is_reachable_from_1x(js):
    """The list is stepped through, so a speed that is in it and not on the path
    from 1x is a speed the keys cannot reach - which is a speed only half the
    controls have."""
    got = js.eval("""
      var seen = [];
      watching(20);
      seen.push(S.watch.rate);        // 1x, where it starts
      for (var i = 0; i < 10; i++) { stepReplayRate(-1); seen.push(S.watch.rate); }
      setReplayRate(1);
      for (var i = 0; i < 10; i++) { stepReplayRate(1); seen.push(S.watch.rate); }
      seen.join(',');
    """)
    assert set(float(x) for x in got.split(",")) == {0.1, 0.25, 0.5, 1, 1.5, 2, 4}


# ---------------------------------------------------------------------------
# The keys
# ---------------------------------------------------------------------------

def test_the_transport_takes_the_driving_keys(js):
    """They are the keys a hand is already on, they are free because nothing is
    being driven, and each means the kind of thing it means on the road."""
    js.eval("watching(60); watchSeek(30);")
    assert js.eval("key('Space')") is True
    assert js.eval("S.watch.playing") is False

    js.eval("key('ArrowLeft');")
    assert js.eval("S.watch.t") == 25
    js.eval("key('ArrowRight'); key('ArrowRight');")
    assert js.eval("S.watch.t") == 35

    js.eval("key('ArrowUp');")
    assert js.eval("S.watch.rate") == 1.5
    js.eval("key('ArrowDown'); key('ArrowDown');")
    assert js.eval("S.watch.rate") == 0.5


def test_a_frame_step_is_one_ghost_frame(js):
    """One recorded frame and not one rendered one: the recording has no state
    between its own samples, so a smaller step would be the same picture twice."""
    js.eval("watching(60); watchSeek(30); key('Period');")
    assert js.eval("S.watch.t") == pytest.approx(30 + 1 / 15)
    js.eval("key('Comma'); key('Comma');")
    assert js.eval("S.watch.t") == pytest.approx(30 - 1 / 15)


def test_wasd_reaches_the_transport_too(js):
    """The same keys the car takes. Somebody who steers with WASD has their hand
    nowhere near the arrows, and a transport half of them cannot reach is a
    transport half of them do not have."""
    js.eval("watching(60); watchSeek(30); key('KeyA');")
    assert js.eval("S.watch.t") == 25
    js.eval("key('KeyW');")
    assert js.eval("S.watch.rate") == 1.5


@pytest.mark.parametrize("code", ["KeyH", "KeyL", "KeyO", "KeyP", "KeyK",
                                  "KeyG", "KeyM", "Escape", "KeyQ", "KeyF",
                                  "KeyR", "KeyT", "KeyC", "KeyJ", "Digit1"])
def test_what_the_transport_does_not_claim_falls_through(code, js):
    """`replayKey` returning false is what lets the rest of the keyboard work
    during a replay - the panels, the two camera holds, Escape - and it is what
    stops R, T, C, J and the digits being answered twice: they are handled
    further down the same listener, and the two answers are different."""
    js.eval("watching(60);")
    assert js.eval("key('%s')" % code) is False


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

def test_the_last_checkpoint_is_the_one_behind_you(js):
    js.eval("watching(60, [10, 20, 30, 40]); watchSeek(35);")
    js.eval("watchLastCheckpoint();")
    assert js.eval("S.watch.t") == 30


def test_the_last_checkpoint_before_the_first_one_is_the_line(js):
    """Same as R, and silently: there is nothing behind you yet, and refusing
    would need a message for a non-event."""
    js.eval("watching(60, [10, 20]); watchSeek(4); watchLastCheckpoint();")
    assert js.eval("S.watch.t") == 0


def test_pressing_it_on_a_checkpoint_goes_to_the_one_before(js):
    """Otherwise it lands on the checkpoint you are standing on and travels
    nowhere, which reads as the button being broken - and pressing it twice at
    the same corner is exactly how somebody finds that out."""
    js.eval("watching(60, [10, 20, 30]); watchSeek(30.05); watchLastCheckpoint();")
    assert js.eval("S.watch.t") == 20


def test_the_stored_splits_are_used_when_there_are_any(js):
    """They are the clock the game stamped at the moment of the crossing.
    Nothing derived can beat that, so nothing derived is asked."""
    got = js.eval("replayGates(null, [1500, 9250]).join(',')")
    assert got == "1.5,9.25"


def test_a_replay_with_no_splits_and_no_course_has_no_ticks(js):
    """A race replay carries poses and finishing times and nothing else, and it
    can arrive before the world is built. No ticks and a T that goes to the line
    is the right failure - the bar still works."""
    assert js.eval("replayGates({frames: []}, null).length") == 0


# ---------------------------------------------------------------------------
# C, from inside a replay
# ---------------------------------------------------------------------------
#
# **It makes an ordinary slot, and that is the point.** Watch the corner you keep
# losing, press C, stop watching, press R, and your car is on the road there at
# the speed they were carrying. The whole reason the feature is worth having on a
# replay is that the two halves join up; a second kind of slot that could only be
# watched would be a bookmark pretending to be a save state.
#
# A ghost frame is a pose and a save state is a car, so three things have to be
# built rather than copied - the velocity, the transient fields, and where the
# run had got to - and those are what these test.

SAVE_STUB = r"""
function V3(x, y, z) { this.x = x || 0; this.y = y || 0; this.z = z || 0; }
var THREE = { Vector3: V3 };
var FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };
var MAX_SLOTS = 9;
var SAVED_TO_STORE = 0;
function persistSaves() { SAVED_TO_STORE++; }
function renderSaves() {}
function autoLabel(run) { return 'after CP' + run.nextCp; }
function slotName() { return ''; }
// A car mid-lap somewhere else entirely, carrying every transient a session
// picks up - so a field this forgets to clear shows up as that session's value
// rather than as a zero that was going to be there anyway.
function baseCar() {
  return { pos: [9, 9, 9], vel: [9, 9, 9], quat: [0, 0, 0, 1], speed: 99,
           grounded: false, steer: 0.4, slip: 0.9, slipCharge: 1, slipBoost: 5,
           padBoost: 7, catchupBoost: 3, bumpSlip: 2, bumpLean: 2, bumpTimer: 2,
           bounceLock: 4, respawnIn: 1, towed: true, braking: false,
           frozen: true, respawn: {p: [1, 2, 3]}, tick: 12345 };
}
var GATES = ['start', 'cp0', 'cp1', 'cp2', 'finish'];
S.course = {
  gates: GATES,
  checkpoints: function () { return ['cp0', 'cp1', 'cp2']; },
  startGate: function () { return 'start'; },
  s: [0, 10, 20, 30, 40, 50],
  locate: function () { return { idx: 3 }; },
};
S.car = { snapshot: baseCar };
S.run = { snapshot: function () { return { time: 0, splits: [], nextCp: 0 }; } };
S.track = { stamp: 'abc' };
S.ghostMode = 'wr';
S.saves = [];
S.saveActive = -1;
// A lap along +X at 10 units a second, so a central difference over one frame
// either side is exactly (10, 0, 0) wherever it is taken.
function straight(dur, flags) {
  return { hz: 15, duration: dur,
           at: function (t) { return [t * 10, 0, 0, 0, 0, 0, 1, flags | 0]; } };
}
function watchingLap(dur, gates, flags) {
  S.watch = { cars: [{ g: straight(dur, flags), gates: gates || [], prev: null }],
              at: 0, t: 0, dur: dur, playing: true, rate: 1, shown: -1 };
  return S.watch;
}
"""


def _save_from_replay():
    src = open(os.path.join(JS, "game.js")).read()
    return _fn(src, "saveFromReplay")


@pytest.fixture()
def saver():
    c = quickjs.Context()
    c.eval(STUB)
    c.eval(SAVE_STUB)
    c.eval(_save_from_replay())
    return c


def test_the_velocity_is_read_back_off_the_frames(saver):
    """A pose says where a car was and nothing about how fast. A central
    difference across one frame either side is the best a 15Hz recording can
    answer, and it is a good deal better than either one-sided version at the
    apex of anything."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].car.vel.join(',')") == "10,0,0"
    assert saver.eval("S.saves[0].car.speed") == pytest.approx(10)


def test_the_pose_is_the_frame_and_not_your_own_car(saver):
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].car.pos.join(',')") == "50,0,0"
    assert saver.eval("S.saves[0].car.quat.join(',')") == "0,0,0,1"


def test_nothing_the_session_was_carrying_comes_with_it(saver):
    """A tow, a pad, a bump and a respawn are states of a car in a session, and
    this car is about to be put on the road in a different one. `steer` goes with
    them: it is the *smoothed* angle, which the physics rebuilds within a few
    steps, and there is nowhere in a pose it could be read from."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    c = "S.saves[0].car."
    for field in ("steer", "slip", "slipCharge", "slipBoost", "padBoost",
                  "catchupBoost", "bumpSlip", "bumpLean", "bumpTimer",
                  "bounceLock", "respawnIn"):
        assert saver.eval(c + field) == 0, field
    assert saver.eval(c + "towed") is False
    assert saver.eval(c + "frozen") is False
    assert saver.eval(c + "respawn") is None


def test_the_car_is_left_flying_if_the_lap_was(saver):
    """`grounded` is re-derived by the first step, but it is read by the
    renderer before that step happens - and a car that lands on the road with
    its wheels already down is a frame of the wrong picture."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].car.grounded") is True
    saver.eval("S.saves = []; watchingLap(20, [], FLAG.AIR);"
               " S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].car.grounded") is False


def test_the_run_is_put_where_the_driver_was(saver):
    """The clock reads what their clock read and the checkpoints behind them are
    behind you - so the split deltas are about the same lap, and T works from
    the moment you land rather than sending you to the line."""
    saver.eval("watchingLap(20, [2, 6, 12]); S.watch.t = 8; saveFromReplay();")
    assert saver.eval("S.saves[0].run.time") == 8000
    assert saver.eval("S.saves[0].run.nextCp") == 2
    assert saver.eval("S.saves[0].run.splits.join(',')") == "2000,6000"
    # The gate you last went through, by index into `course.gates`.
    assert saver.eval("S.saves[0].run.respawnGate") == GATES_INDEX["cp1"]


GATES_INDEX = {"start": 0, "cp0": 1, "cp1": 2, "cp2": 3, "finish": 4}


def test_before_the_first_checkpoint_the_respawn_is_the_line(saver):
    saver.eval("watchingLap(20, [5, 9]); S.watch.t = 2; saveFromReplay();")
    assert saver.eval("S.saves[0].run.nextCp") == 0
    assert saver.eval("S.saves[0].run.respawnGate") == GATES_INDEX["start"]


def test_the_ghost_is_frozen_where_the_replay_is(saver):
    """The same rule a slot taken while driving follows: what is useful is that
    the lap you are chasing is the same distance up the road, not that it is the
    same recording."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].ghost.t") == 5
    assert saver.eval("S.saves[0].ghost.mode") == "wr"


def test_the_slot_is_stamped_with_the_track_it_was_taken_on(saver):
    """A state whose track has since been re-authored would put the car inside
    whatever is there now, and a replay slot is no different from any other."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saves[0].stamp") == "abc"


def test_it_becomes_the_active_slot_and_is_persisted(saver):
    """So that stopping the replay and pressing R lands you there, which is the
    whole gesture this exists for."""
    saver.eval("watchingLap(20); S.watch.t = 5; saveFromReplay();")
    assert saver.eval("S.saveActive") == 0
    assert saver.eval("SAVED_TO_STORE") == 1
    assert "5000" in saver.eval("TOASTS[TOASTS.length - 1]")


def test_a_full_set_of_slots_refuses_rather_than_silently_dropping_one(saver):
    saver.eval("watchingLap(20); S.watch.t = 5;"
               " for (var i = 0; i < 9; i++) saveFromReplay();"
               " saveFromReplay();")
    assert saver.eval("S.saves.length") == 9
    assert "slots full" in saver.eval("TOASTS[TOASTS.length - 1]")


# ---------------------------------------------------------------------------
# Share
# ---------------------------------------------------------------------------

SHARE_STUB = r"""
var COPIED = null, TOASTED = [];
var navigator = { clipboard: { writeText: function (s) {
  COPIED = s;
  return Promise.resolve();
} } };
var location = { origin: 'https://drive.example' };
function toast(m) { TOASTED.push(m); }
S = { track: { slug: 'bigred' }, watch: null };
"""


def _share():
    src = open(os.path.join(JS, "game.js")).read()
    return "\n".join(_fn(src, n) for n in ("copyLink", "shareReplay", "shareBoardRow"))


class Sharer:
    """`copyLink` is async, so the toast lands in a microtask rather than during
    the call. Nothing in the browser has to care - the next frame runs it - but a
    QuickJS context only drains its job queue when asked, so a test that read the
    toast straight after `eval` would assert on an empty list and pass for the
    wrong reason once the toast stopped working."""

    def __init__(self, ctx):
        self.ctx = ctx

    def run(self, script):
        self.ctx.eval(script)
        while self.ctx.execute_pending_job():
            pass

    def eval(self, expr):
        return self.ctx.eval(expr)


@pytest.fixture()
def sharer():
    c = quickjs.Context()
    c.eval(SHARE_STUB)
    c.eval(_share())
    return Sharer(c)


def test_a_lap_is_shared_as_the_link_that_opens_it(sharer):
    """`/solo/<slug>?watch=<id>` and nothing else - it is the address
    `openRequestedLap` is the other end of, and the only one a row has. A lap is
    a row rather than a page, so getting this wrong is a link that loads the
    track and quietly does not watch anything."""
    sharer.run("shareBoardRow(173);")
    assert sharer.eval("COPIED") == "https://drive.example/solo/bigred?watch=173"


def test_sharing_says_it_copied(sharer):
    """A copy has no feedback of its own - unlike an OS share sheet, which is
    why this is not `navigator.share` - so a silent one is indistinguishable
    from a dead button."""
    sharer.run("shareBoardRow(173);")
    assert sharer.eval("TOASTED[0]") == "Link copied!"


def test_a_replay_shares_whatever_address_it_was_given(sharer):
    """One lap is a row on a board and a whole race is a page, so the address is
    carried on the replay rather than rebuilt here from what it happens to be."""
    sharer.run("S.watch = { share: 'https://drive.example/race/42', cars: [{}], at: 0 };"
               " shareReplay();")
    assert sharer.eval("COPIED") == "https://drive.example/race/42"


def test_a_replay_with_no_address_shares_nothing(sharer):
    """A ghost handed over by a room has no link anybody else could open, so the
    button is not offered - and if it is reached anyway it does nothing rather
    than copying a URL that 404s."""
    sharer.run("S.watch = { share: null, cars: [{}], at: 0 }; shareReplay();")
    assert sharer.eval("COPIED") is None
    assert sharer.eval("TOASTED.length") == 0
