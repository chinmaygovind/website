"""Small rules that live in game.js and are worth pinning.

Each one is lifted out of the file **by name** and run in QuickJS against a
stub, the same trick `test_touch.py` and `test_slipstream.py` use: there is no
browser in CI, and these are the kind of rule that is one character away from
being silently wrong.

What they have in common is that all three used to be bugs:

* R and T fired before the clock was running, which on a grid moved the car
  *forward* to the start gate - ahead of every grid slot - so a driver could
  walk themselves up the road while the lights counted down. A world record was
  set that way.
* the grid alternated which side pole started on, because nothing knew which
  way the first corner went, so half the time the fastest qualifier lined up on
  the outside of it.
* a ghost has no lamps of its own; it wears the flags of the lap it recorded.
"""

import os
import re

import pytest

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")


def _fn(name):
    """One top-level function from game.js, exactly as it ships."""
    src = open(GAME_JS).read()
    m = re.search(r"^function %s\(.*?^\}" % re.escape(name), src, re.S | re.M)
    assert m, "%s is gone from game.js, or is no longer a plain function" % name
    return m.group(0)


def _ctx(setup=""):
    ctx = jsrt.quickjs.Context()
    ctx.eval("var CFG = {mode: 'room'};")
    ctx.eval(setup or "var S = {};")
    return ctx


# --- R and T do nothing until you have set off ------------------------------

RESTART_STUB = """
var calls = [];
var S = {started: false, car: {requestRespawn: () => calls.push('respawn')}};
function resetToStart() { calls.push('reset'); }
function toast(t) { calls.push('toast:' + t); }
"""


@pytest.mark.parametrize("started,want", [(False, []), (True, ["reset", "toast:Restart"])])
def test_restart_does_nothing_until_the_clock_is_running(started, want):
    import json
    ctx = _ctx(RESTART_STUB)
    ctx.eval(_fn("restartRun"))
    ctx.eval("S.started = %s; restartRun();" % ("true" if started else "false"))
    assert json.loads(ctx.eval("JSON.stringify(calls)")) == want


@pytest.mark.parametrize("started,want", [(False, []), (True, ["respawn"])])
def test_the_checkpoint_key_does_nothing_until_the_clock_is_running(started, want):
    """This is the half that was worth time: on a grid, a respawn puts you on the
    start gate, which is in front of every slot on it."""
    import json
    ctx = _ctx(RESTART_STUB)
    ctx.eval(_fn("backToCheckpoint"))
    ctx.eval("S.started = %s; backToCheckpoint();" % ("true" if started else "false"))
    assert json.loads(ctx.eval("JSON.stringify(calls)")) == want


def test_refusing_is_silent():
    """No toast, no sound, no flash. It is not an event that you have not set off
    yet - the whole point is that pressing them early does nothing at all."""
    import json
    ctx = _ctx(RESTART_STUB)
    ctx.eval(_fn("restartRun"))
    ctx.eval(_fn("backToCheckpoint"))
    ctx.eval("restartRun(); backToCheckpoint();")
    assert json.loads(ctx.eval("JSON.stringify(calls)")) == []


# --- the tail lamps a recorded flag byte asks for ---------------------------

def test_the_lamps_come_off_the_recorded_flags():
    import json
    ctx = _ctx()
    ctx.eval("var FLAG = {DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16};")
    ctx.eval(_fn("lampsOf"))
    out = json.loads(ctx.eval("JSON.stringify([lampsOf(0), lampsOf(8), lampsOf(1), "
                              "lampsOf(9), lampsOf(undefined)])"))
    dark, braking, drifting, both, old = out
    assert dark == {"braking": False, "drifting": False}
    assert braking == {"braking": True, "drifting": False}
    assert drifting == {"braking": False, "drifting": True}
    # The handbrake counts as braking, so both is the common case and drift has
    # to win it - CarView paints amber over red.
    assert both == {"braking": True, "drifting": True}
    # A lap recorded before flags existed has none, which is lamps off.
    assert old == {"braking": False, "drifting": False}


# --- pole starts on the inside, every race, on every track ------------------

GRID_STUB = """
var placed = null;
var toasts = [];
var CFG = {mode: 'room', me: {pid: 'me'}};
var S = {
  track: {pole_side: POLE},
  course: {startGate: () => ({p: [0, 0, 0], f: [0, 0, -1], r: [1, 0, 0]})},
  car: {placeAt: (p, f) => { placed = p; }},
};
function toast(t) { toasts.push(t); }
function ordinal(n) { return String(n); }
"""


def _place(pole_side, slot, others=4):
    import json
    ctx = jsrt.quickjs.Context()
    ctx.eval(GRID_STUB.replace("POLE", str(pole_side)))
    ctx.eval(_fn("placeOnGrid"))
    grid = {"p%d" % i: i for i in range(others)}
    grid["me"] = slot
    ctx.eval("placeOnGrid({grid: %s});" % json.dumps(grid))
    return json.loads(ctx.eval("JSON.stringify(placed)"))


@pytest.mark.parametrize("pole_side", [-1, 1])
def test_pole_lines_up_on_the_inside_of_the_first_corner(pole_side):
    """`r` in the stub is world +X, so the lateral offset is the sign of x."""
    p = _place(pole_side, 0)
    assert p[0] * pole_side > 0, "pole started on the outside of turn one"


@pytest.mark.parametrize("pole_side", [-1, 1])
def test_second_lines_up_on_the_other_side_and_further_back(pole_side):
    """The stagger is the other half of it: side by side, the car on the inside
    of the corner simply gets there first whatever the order said."""
    pole, second = _place(pole_side, 0), _place(pole_side, 1)
    assert second[0] * pole_side < 0
    # `f` is -Z and the grid is laid out behind the gate, so further back is +Z.
    assert second[2] > pole[2]


def test_the_side_does_not_depend_on_the_race_number():
    """It used to alternate, which is what put the fastest qualifier on the
    outside every other race. Same track, same slot, same side, always."""
    assert _place(1, 0) == _place(1, 0)
    assert _place(-1, 2)[0] < 0 and _place(1, 2)[0] > 0
