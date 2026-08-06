"""Small rules that live in game.js and are worth pinning.

Each one is lifted out of the file **by name** and run in QuickJS against a
stub, the same trick `test_touch.py` and `test_slipstream.py` use: there is no
browser in CI, and these are the kind of rule that is one character away from
being silently wrong.

Two groups are not fixed bugs but contracts between two files. The tow level
goes out over the wire as one number and comes back as the two things a rival's
slipstream is drawn and heard from, and the flag byte is what says which.
Getting that backwards is silent - every rival simply looks like it is
permanently boosting - so both ends are pinned here. The camera views are the
same shape of thing: two words leave the keyboard and are read in render.js, and
one of them being renamed is a key that quietly does nothing.

What the rest have in common is that they used to be bugs:

* R and T fired before the clock was running, which on a grid moved the car
  *forward* to the start gate - ahead of every grid slot - so a driver could
  walk themselves up the road while the lights counted down. A world record was
  set that way.
* the grid alternated which side pole started on, because nothing knew which
  way the first corner went, so half the time the fastest qualifier lined up on
  the outside of it.
* a ghost has no lamps of its own; it wears the flags of the lap it recorded.
* a lap driven in a room used to go on the leaderboard, tow and all.
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
    """Red or dark, and nothing else. Drifting is in the byte and deliberately
    not on the lamps: the handbrake counts as braking, so an amber drift state
    changed the colour of lamps that were already lit rather than turning any
    on, and a car that goes yellow whenever it steps out looks broken."""
    import json
    ctx = _ctx()
    ctx.eval("var FLAG = {DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16};")
    ctx.eval(_fn("lampsOf"))
    out = json.loads(ctx.eval("JSON.stringify([lampsOf(0), lampsOf(8), lampsOf(1), "
                              "lampsOf(9), lampsOf(undefined)])"))
    dark, braking, drifting, both, old = out
    assert dark == {"braking": False}
    assert braking == {"braking": True}
    assert drifting == {"braking": False}
    assert both == {"braking": True}
    # A lap recorded before flags existed has none, which is lamps off.
    assert old == {"braking": False}


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


# --- a lap in a room never reaches the leaderboard --------------------------

@pytest.mark.parametrize("mode,want", [
    ("solo", True),      # alone against the clock, which is what a time is
    ("room", False),     # other cars on the road in every phase of one
    ("replay", False),   # not a lap of yours at all
])
def test_only_a_lap_driven_alone_counts_for_the_board(mode, want):
    """A record set with a tow is a record of the traffic. Both halves of a lap
    counting - the attempt and the time - read this one answer, so they cannot
    disagree and leave a track with more finishes than goes."""
    ctx = jsrt.quickjs.Context()
    ctx.eval("var CFG = {mode: '%s'};" % mode)
    ctx.eval(_fn("countsForTheBoard"))
    assert bool(ctx.eval("countsForTheBoard()")) is want


def test_an_attempt_in_a_room_is_not_counted_either():
    """`noteStart` is the other half, and it asks the same question."""
    import json
    ctx = jsrt.quickjs.Context()
    ctx.eval("var posted = [];")
    ctx.eval("function fetch(u) { posted.push(u); return {catch: () => {}}; }")
    ctx.eval(_fn("countsForTheBoard"))
    ctx.eval(_fn("noteStart"))
    for mode in ("room", "solo"):
        ctx.eval("var CFG = {mode: '%s', loggedIn: true};" % mode)
        ctx.eval("var S = {track: {slug: 'sunrise'}};")
        ctx.eval("noteStart();")
    assert json.loads(ctx.eval("JSON.stringify(posted)")) == ["/api/start"]


# --- Escape closes things before it opens one -------------------------------

ESC_STUB = """
var did = [];
var shut = {board: true, tracks: true};
var S = {watch: null, helpOpen: false};
function $(id) {
  return {style: {display: shut[id === 'boardOv' ? 'board' : 'tracks'] ? 'none' : ''}};
}
function stopWatching() { did.push('stopWatching'); }
function toggleBoard(v) { did.push('board:' + v); }
function toggleTracks(v) { did.push('tracks:' + v); }
function toggleHelp(v) { did.push('help:' + v); }
function toggleMenu() { did.push('menu'); }
"""


@pytest.mark.parametrize("open_what,want", [
    ("S.watch = {}", "stopWatching"),
    ("shut.board = false", "board:false"),
    ("shut.tracks = false", "tracks:false"),
    ("S.helpOpen = true", "help:false"),
    ("", "menu"),
])
def test_escape_closes_what_is_in_front_of_you_before_opening_settings(open_what, want):
    """Help was missing from the chain, so Escape put the settings sheet on top
    of the controls instead of closing them."""
    import json
    ctx = jsrt.quickjs.Context()
    ctx.eval(ESC_STUB)
    ctx.eval(_fn("onEscape"))
    if open_what:
        ctx.eval(open_what + ";")
    ctx.eval("onEscape();")
    assert json.loads(ctx.eval("JSON.stringify(did)")) == [want]


# --- the tow, over the wire and back ----------------------------------------

FLAGS = "var FLAG = {DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16};"

POSE_STUB = FLAGS + """
var POSE_HZ = 30;
var T = {SLIP_BOOST: 1.6};
var sent = null;
var S = {
  socket: {emit: (ev, d) => { sent = d; }},
  lastPose: 0,
  run: {bestS: 12.5, nextCp: 2},
  car: {
    pos: {x: 0, y: 0, z: 0}, quat: {x: 0, y: 0, z: 0, w: 1}, vel: {x: 0, y: 0, z: 0},
    slipCharge: 0, slipBoost: 0,
    flags: function () { return this.slipBoost > 0 ? FLAG.SLIP : 0; },
  },
};
"""


def _pose(charge=0.0, boost=0.0):
    import json
    ctx = jsrt.quickjs.Context()
    ctx.eval(POSE_STUB)
    ctx.eval(_fn("sendPose"))
    ctx.eval("S.car.slipCharge = %s; S.car.slipBoost = %s; sendPose(100000);"
             % (charge, boost))
    return json.loads(ctx.eval("JSON.stringify(sent)"))


def test_the_tow_goes_out_as_one_number_the_flag_disambiguates():
    """`sl` is 0..1 either way and `FLAG.SLIP` says which of the two it is - the
    charge while it fills, what is left of the boost while it pays. Two fields
    would have been the obvious thing and the flag was already on the wire for
    the tail lamps, so there is one."""
    filling = _pose(charge=0.62)
    assert filling["sl"] == pytest.approx(0.62)
    assert not filling["flags"] & 16

    paying = _pose(boost=0.8)                       # half of SLIP_BOOST left
    assert paying["sl"] == pytest.approx(0.5)
    assert paying["flags"] & 16


def test_a_boost_beats_a_stale_charge_on_the_wire():
    """The charge is zeroed when the boost fires, but nothing about `sl` should
    depend on that: the boost is the answer whenever there is one."""
    assert _pose(charge=0.9, boost=1.6)["sl"] == pytest.approx(1.0)


RIVAL_STUB = FLAGS + """
var CFG = {mode: 'room'};
var T = {MAX_SPEED: 44, SLIP_BOOST: 1.6};
var S = {
  racePhase: 'free', raceMode: false,
  renderer: {camera: {position: {x: 0, y: 0, z: 0}}},
  remotes: new Map(),
};
function car(pid, z, opts) {
  const o = opts || {};
  S.remotes.set(pid, {
    pid, pos: {x: 0, y: 0, z: z},
    speed: o.speed == null ? 40 : o.speed, flags: o.flags || 0,
    slipCharge: o.charge || 0, slipBoost: o.boost || 0,
  });
}
"""


def _rivals(setup="", phase="free", race="false", mode="room"):
    import json
    ctx = jsrt.quickjs.Context()
    ctx.eval(RIVAL_STUB)
    ctx.eval(_fn("contactOn"))
    ctx.eval(_fn("rivalSound"))
    ctx.eval("CFG.mode = '%s'; S.racePhase = '%s'; S.raceMode = %s;"
             % (mode, phase, race))
    if setup:
        ctx.eval(setup)
    return json.loads(ctx.eval("JSON.stringify(rivalSound())"))


@pytest.mark.parametrize("mode,phase,race,heard", [
    ("room", "free", "false", True),        # cars you are driving among
    ("room", "racing", "true", True),
    ("room", "qualifying", "false", False), # everybody alone on their own lap
    ("room", "countdown", "true", False),
    ("room", "results", "false", False),
    ("solo", "free", "false", False),       # nobody out there at all
])
def test_you_only_hear_the_cars_you_are_driving_among(mode, phase, race, heard):
    """The same gate contact and the tow read. In qualifying a car howling past
    your ear is somebody a corner behind you on an out lap - a rival you are not
    racing, arriving as though you were."""
    out = _rivals("car('a', -10);", phase, race, mode)
    assert (out is not None and len(out) == 1) is heard


def test_a_respawning_car_is_not_out_there_to_be_heard():
    """It is not drawn and cannot be hit either: it is off the track."""
    out = _rivals("car('a', -10, {flags: FLAG.RESPAWN}); car('b', -20);")
    assert [c["id"] for c in out] == ["b"]


def test_the_closest_cars_get_the_voices():
    """Only the nearest few are given one, so a full grid seen from the back
    spends them on the cars close enough to be worth hearing."""
    out = _rivals("car('far', -90); car('near', -8); car('mid', -30);")
    assert [c["id"] for c in out] == ["near", "mid", "far"]


def test_a_rival_on_the_power_is_one_that_is_not_braking():
    """There is no throttle on the wire and there does not need to be: an engine
    note only has to know whether the car is on it."""
    out = _rivals("car('drive', -10); car('slowing', -20, {flags: FLAG.BRAKE}); "
                  "car('parked', -30, {speed: 0});")
    by = {c["id"]: c for c in out}
    assert by["drive"]["throttle"] and not by["slowing"]["throttle"]
    assert not by["parked"]["throttle"]


def test_the_tow_comes_back_as_the_two_numbers_it_is_drawn_from():
    """`updateRemotes` has already split `sl` on the flag by the time this reads
    it, so the boost is a fraction of SLIP_BOOST exactly as your own car's is."""
    out = _rivals("car('filling', -10, {charge: 0.4}); "
                  "car('paying', -20, {boost: 0.8});")
    by = {c["id"]: c for c in out}
    assert by["filling"]["charge"] == pytest.approx(0.4) and by["filling"]["boost"] == 0
    assert by["paying"]["boost"] == pytest.approx(0.5) and by["paying"]["charge"] == 0


# --- the two views you hold a key for ---------------------------------------
#
# A stuck camera is a silent failure at both ends. The views are held rather than
# toggled, so a keyup is the only thing that ends one; and the two words travel
# from KEYMAP through `viewKeys` into `Renderer.follow` in another file, where a
# name that stopped matching would leave a key that does nothing at all.

def _view(*held):
    """`viewKeys` with exactly these actions held."""
    import json
    ctx = _ctx("var keys = new Set(%s);" % json.dumps(list(held)))
    ctx.eval(_fn("viewKeys"))
    return json.loads(ctx.eval("JSON.stringify(viewKeys())"))


def test_no_key_held_is_the_chase_camera():
    assert _view() == {"rear": False, "first": False}


@pytest.mark.parametrize("held,want", [
    ("rear", {"rear": True, "first": False}),
    ("first", {"rear": False, "first": True}),
])
def test_each_key_asks_for_its_own_view(held, want):
    assert _view(held) == want


def test_both_at_once_is_a_look_over_the_shoulder():
    """They are two questions, not three cameras - where the eye sits, and which
    way it looks - so both at once composes instead of one of them winning."""
    assert _view("rear", "first") == {"rear": True, "first": True}


def test_the_car_never_sees_the_camera_keys():
    """They are held in the same set as the throttle, which is what gets emptied
    on blur and on opening the chat box. `readInput` takes the five it wants by
    name, so being in there costs the physics nothing."""
    import json
    ctx = _ctx("var keys = new Set(['rear', 'first']); var touchKeys = new Set();"
               "var input = {};")
    ctx.eval(_fn("readInput"))
    assert json.loads(ctx.eval("JSON.stringify(readInput())")) == {
        "throttle": 0, "brake": 0, "steer": 0, "handbrake": False}


def test_the_keys_are_bound_where_holding_one_can_be_let_go_of():
    """In KEYMAP, which blur and the chat box clear. Bound beside R and T instead,
    a keyup swallowed by the message box would leave the camera looking backwards
    for the rest of the lap."""
    src = open(GAME_JS).read()
    keymap = re.search(r"const KEYMAP = \{(.*?)\};", src, re.S).group(1)
    assert "KeyQ: 'rear'" in keymap and "KeyF: 'first'" in keymap


def test_the_renderer_reads_the_same_two_words():
    """The far end of the contract, in the other file."""
    render_js = os.path.join(os.path.dirname(GAME_JS), "render.js")
    follow = re.search(r"^  follow\(car, dt, opts = \{\}\) \{.*?^  \}$",
                       open(render_js).read(), re.S | re.M)
    assert follow, "Renderer.follow is gone, or no longer takes opts"
    assert "opts.first" in follow.group(0) and "opts.rear" in follow.group(0)
