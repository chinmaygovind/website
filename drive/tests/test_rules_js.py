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

// The arming half. No timers in QuickJS, so `setTimeout` records the callback
// instead of running it and `fire()` below is the clock running out - which is
// the only way to test an expiry at all without waiting 3.5 real seconds.
var ARM_MS = 3500, timers = [], restartArm = null;
function setTimeout(fn, ms) { timers.push(fn); return timers.length; }
function clearTimeout(t) { if (t) timers[t - 1] = null; }
function fire() { var t = timers.slice(); timers = []; t.forEach(f => f && f()); }
var els = {btnRestart: cls(), tRestart: cls()};
function cls() {
  var on = false;
  return {classList: {toggle: (n, v) => { on = v; }, has: () => on}};
}
function $(id) { return els[id]; }
function armedButtons() {
  return Object.keys(els).filter(k => els[k].classList.has()).sort();
}
"""


# `restartRun` is one of five now: the rule about when to ask, the two halves of
# the asking, and the button that shows it. Lifted together because they only
# make sense together.
RESTART_FNS = ("restartRun", "restartCostsARace", "showRestartArmed",
               "armRestart", "disarmRestart")


def _restart_ctx(phase=None, race=False, touch=False, mode="room"):
    """A room, mid-race or not, with every door into `restartRun` loaded."""
    ctx = _ctx(RESTART_STUB)
    for fn in RESTART_FNS:
        ctx.eval(_fn(fn))
    ctx.eval("CFG.mode = '%s';" % mode)
    ctx.eval("S.started = true; S.touch = %s; S.raceMode = %s; S.racePhase = %s;"
             % ("true" if touch else "false", "true" if race else "false",
                "null" if phase is None else "'%s'" % phase))
    return ctx


def _calls(ctx):
    import json
    out = json.loads(ctx.eval("JSON.stringify(calls)"))
    ctx.eval("calls = [];")
    return out


@pytest.mark.parametrize("started,want", [(False, []), (True, ["reset", "toast:Restart"])])
def test_restart_does_nothing_until_the_clock_is_running(started, want):
    ctx = _restart_ctx()
    ctx.eval("S.started = %s; restartRun();" % ("true" if started else "false"))
    assert _calls(ctx) == want


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
    ctx = _restart_ctx()
    ctx.eval(_fn("backToCheckpoint"))
    ctx.eval("S.started = false; restartRun(); backToCheckpoint();")
    assert _calls(ctx) == []


# --- and mid-race R has to be asked twice -----------------------------------

def test_mid_race_the_first_r_only_asks():
    """The whole point. R is next to T, T is the key you want when you have just
    fallen off, and in a race the lap you are on is the only one you get - so one
    stray press used to put you back on the grid with the field gone."""
    ctx = _restart_ctx(phase="racing", race=True)
    ctx.eval("restartRun();")
    assert _calls(ctx) == ["toast:Press R again to restart"], "asks, does not reset"
    ctx.eval("restartRun();")
    assert _calls(ctx) == ["reset", "toast:Restart"], "and the second press does it"


def test_the_question_expires_so_two_strays_are_not_a_restart():
    """Two accidents three seconds apart are two accidents, not a confirmation.
    Otherwise the guard only moves the problem: an R at the hairpin and another at
    the next lap's would restart between them."""
    ctx = _restart_ctx(phase="racing", race=True)
    ctx.eval("restartRun(); fire();")            # the arming ran out
    assert _calls(ctx) == ["toast:Press R again to restart"]
    ctx.eval("restartRun();")
    assert _calls(ctx) == ["toast:Press R again to restart"], "asks again, no reset"


def test_arming_lights_both_restart_buttons_and_then_stops():
    """R and the two buttons are three doors into one rule, so the state is not
    the button's - but the button still has to show it, because on a phone the
    pulse is the only thing that says the first tap landed."""
    import json
    ctx = _restart_ctx(phase="racing", race=True, touch=True)
    ctx.eval("restartRun();")
    assert json.loads(ctx.eval("JSON.stringify(armedButtons())")) \
        == ["btnRestart", "tRestart"]
    assert _calls(ctx) == ["toast:Tap again to restart"], "and it says tap, not press"
    ctx.eval("restartRun();")
    assert json.loads(ctx.eval("JSON.stringify(armedButtons())")) == [], \
        "the restart clears it, so the buttons do not keep pulsing"


def test_the_question_expiring_puts_the_buttons_back():
    import json
    ctx = _restart_ctx(phase="racing", race=True)
    ctx.eval("restartRun(); fire();")
    assert json.loads(ctx.eval("JSON.stringify(armedButtons())")) == []


def test_only_a_race_asks():
    ctx = _restart_ctx(phase="racing", race=True)
    assert ctx.eval("restartCostsARace()") is True


@pytest.mark.parametrize("mode,race,phase", [
    # Free practice in a room, and qualifying, and the countdown, and solo. R is
    # the most useful key on the board in all of them: practice is nothing but
    # restarting, and a qualifying lap thrown away is one of the two or three that
    # ninety seconds holds - so being asked would be in the way.
    ("room", False, "free"),
    ("room", False, "qualifying"),
    ("room", True, "countdown"),
    ("room", True, "results"),
    ("solo", False, None),
    ("replay", False, None),
])
def test_everywhere_else_r_is_still_one_press(mode, race, phase):
    ctx = _restart_ctx(phase=phase, race=race, mode=mode)
    assert ctx.eval("restartCostsARace()") is False
    ctx.eval("restartRun();")
    assert _calls(ctx) == ["reset", "toast:Restart"]


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


# --- the splits and the ghost car are two switches --------------------------

GHOST_STUB = """
var toasts = [];
var els = {};
function El() { this.cls = {}; this.attrs = {}; this.textContent = ''; }
El.prototype.classList = null;
function $(id) {
  if (!els[id]) {
    var e = new El();
    e.classList = {on: false,
                   toggle: function (c, v) { e.cls[c] = v; }};
    e.setAttribute = function (k, v) { e.attrs[k] = v; };
    els[id] = e;
  }
  return els[id];
}
function toast(t) { toasts.push(t); }
function rememberFlag() {}
var S = {showGhost: true, ghostMode: 'wr', ghost: [1], ghostTimes: [{s: 0, ms: 0}]};
"""


def test_hiding_the_ghost_car_leaves_the_lap_it_was_driving():
    """The whole point of splitting the two: the reference lap is what the
    split deltas are measured against, and turning off a translucent car used
    to throw it away with them."""
    ctx = _ctx(GHOST_STUB)
    ctx.eval(_fn("setGhostCar"))
    ctx.eval("setGhostCar(false);")
    assert ctx.eval("S.showGhost") is False
    assert ctx.eval("S.ghostMode") == "wr"
    assert ctx.eval("S.ghostTimes !== null && S.ghostTimes.length > 0")


def test_the_ghost_car_is_the_only_thing_that_switch_decides():
    """`ghostOn` is what the drawing asks, and it reads that flag and the lap.
    Neither one on its own is a car on the road."""
    ctx = _ctx(GHOST_STUB)
    ctx.eval("CFG = {mode: 'solo'};")
    ctx.eval(_fn("ghostOn"))
    assert ctx.eval("ghostOn()") is True
    ctx.eval("S.showGhost = false;")
    assert ctx.eval("ghostOn()") is False
    # And a lap that never loaded is no car either, however the switch is set.
    ctx.eval("S.showGhost = true; S.ghost = null;")
    assert ctx.eval("ghostOn()") is False


def test_picking_a_lap_does_not_turn_the_ghost_car_back_on():
    """It used to be the same assignment - `showGhost = mode !== 'off'` - so
    every press on the splits row overrode a switch one button to the right."""
    src = open(GAME_JS).read()
    body = re.search(r"^function setGhostMode\(.*?^\}", src, re.S | re.M).group(0)
    assert "S.showGhost" not in body


# --- your splits choice is yours, and nothing else may write it --------------

def _game_src():
    return open(GAME_JS).read()


def _body(name):
    m = re.search(r"^(?:async )?function " + name + r"\(.*?^\}", _game_src(),
                  re.S | re.M)
    assert m, f"{name} is gone or no longer a top-level function"
    return m.group(0)


def test_a_new_personal_best_does_not_move_the_lap_you_chose():
    """The bug this pins: after a PB, `/api/run`'s handler called
    `loadGhost('me')` unconditionally. It never touched `S.ghostMode`, so the
    settings row still said *World Record* while the car on the road had quietly
    become your own lap - the setting told the truth about your choice and a lie
    about what you were chasing, which is the worst of both.

    Read out of the source rather than driven, because reaching this line needs a
    finished lap, a server and a stored PB row; what is worth pinning is that the
    reload is *conditional on the mode*, and that is right there in the text.
    """
    src = _game_src()
    reload_site = re.search(r"if \(d\.improved && CFG\.mode !== 'room'\) \{(.*?)\n      \}",
                            src, re.S)
    assert reload_site, "the post-run ghost reload moved; re-check this rule"
    block = reload_site.group(1)
    assert "S.ghostMode === 'me'" in block, \
        "a PB reloads the ghost without asking which lap you chose"
    # Taking the record is the one case where a `wr` ghost is genuinely stale.
    assert "S.ghostMode === 'wr'" in block and "d.is_record" in block


def test_a_lap_chased_off_the_board_is_never_saved_as_your_setting():
    """`run` is a specific lap on a specific track, and `storedGhostMode` cannot
    restore it - so it used to be filed under `me`. That meant opening one lap
    from the leaderboard permanently rewrote a `wr` preference to `me`, which is
    the same complaint as the PB bug arriving by a different door.

    Asserted against the **guard on the write itself**, not against `mode !== 'run'`
    appearing somewhere in the function. The looser version of this test passed with
    the fix reverted, because that same comparison also appears three lines up
    clearing `S.ghostRun` - a source-reading test that cannot fail is worse than no
    test, and this one proved it by not failing.
    """
    body = _body("setGhostMode")
    m = re.search(r"if \(([^)]*)\)\s*\{\s*try \{ localStorage\.setItem\("
                  r"'drive\.ghost', ([^)]+)\)", body)
    assert m, "the drive.ghost write is no longer a guarded one-liner; re-read this"
    cond, value = m.group(1), m.group(2)
    assert "mode !== 'run'" in cond, \
        f"`run` is still written to storage; guard is: {cond}"
    assert "'me'" not in value, \
        f"`run` is still being filed as `me`, which overwrites a real choice: {value}"


def test_the_defaults_are_your_best_lap_and_a_car_to_chase():
    """Both asked for explicitly: splits start on your PB and the ghost car is on,
    for somebody who has never opened the settings sheet."""
    assert "return ok.includes(v) ? v : 'me'" in _body("storedGhostMode")
    assert "storedFlag('drive.ghostcar', true)" in _game_src()


def test_switching_track_leaves_the_ghost_car_alone():
    """It used to turn the car off on arrival with `remember: false`, so the
    stored preference said *on* while the road had no car - a setting disagreeing
    with the game, which is the shape of every bug in this group. The car is a
    remembered switch with its own key now, and a setting that turns itself off
    when you go somewhere is not a setting."""
    body = _body("loadTrack")
    assert "setGhostCar(false" not in body


def test_the_two_switches_are_two_keys():
    """K is which lap, G is whether it is drawn. They shared G, which is why the
    car could only be turned off from the settings sheet. P is left alone - it has
    always changed track, and that is the more common thing to do."""
    src = _game_src()
    assert "if (e.code === 'KeyK') setGhostMode(nextGhostMode());" in src
    assert "if (e.code === 'KeyG') setGhostCar(!S.showGhost);" in src
    assert "if (e.code === 'KeyP') toggleTracks();" in src


# --- the nameplate is the car's business, not the roster's -------------------

def test_a_rival_is_labelled_in_its_own_cars_colour():
    """`CarView.setLabel(text, color)` lets a caller override the plate, and
    `game.js` used to pass the roster's colour at both call sites. That is
    indistinguishable for almost everybody - the plate colour *is* the body
    colour - and wrong for the one car it matters on: a record holder's plate is
    the record green, so the only driver who had earned a green nameplate was the
    only one who could never show it.

    Pinned by reading the calls out of the file rather than by running them,
    because building a remote needs a renderer, a socket and a track - and what
    is being checked is that nobody passes a second argument.
    """
    src = open(GAME_JS).read()
    calls = re.findall(r"\.view\.setLabel\(([^)]*)\)", src)
    assert calls, "the remote label calls are gone from game.js"
    for c in calls:
        assert "," not in c or "plateColor" in c, (
            "setLabel(%s) overrides the car's own plate colour" % c)


# --- somebody else's lap is driven in somebody else's car --------------------

def test_watching_one_lap_keeps_its_owners_whole_car():
    """`/api/ghost` answers with the driver's whole car, and this dropped all of
    it but the body colour - so a lap you *watched* came up on stock wheels with
    no stripe and a matte finish, while the same lap *chased* came up right. Two
    ways of looking at one lap, disagreeing about whose car it was.
    """
    import json
    ctx = _ctx()
    ctx.eval("var got = null; function startReplay(cars) { got = cars; }")
    ctx.eval(_fn("startWatching"))
    ctx.eval("""
      startWatching([1, 2], 15, {who: 'ghosty', color: '#f2c94c',
        livery: {body: '#f2c94c', rim_style: 'mesh', livery: 'twin'}});
    """)
    car = json.loads(ctx.eval("JSON.stringify(got[0])"))
    assert car["livery"] == {"body": "#f2c94c", "rim_style": "mesh",
                             "livery": "twin"}, "the whole car, not just a colour"
    assert car["color"] == "#f2c94c"
    assert car["name"] == "ghosty"


def test_a_lap_with_no_livery_still_gets_a_car():
    """A guest's lap, or one from before the garage. `startReplay` reads a bare
    colour as a complete livery, so there is no branch to get wrong - but only if
    the undefined actually arrives rather than being turned into an object."""
    import json
    ctx = _ctx()
    ctx.eval("var got = null; function startReplay(cars) { got = cars; }")
    ctx.eval(_fn("startWatching"))
    ctx.eval("startWatching([1, 2], 15, {who: '?', color: '#9aa7b8'});")
    car = json.loads(ctx.eval("JSON.stringify(got[0])"))
    assert "livery" not in car or car["livery"] is None
    assert car["color"] == "#9aa7b8"


# The ghost *car*, which is not the ghost *switch* two sections up - that one owns
# the plain `GHOST_STUB` name, and taking it twice silently re-stubbed its tests.
GHOST_CAR_STUB = """
var S = {ghostView: null, ghostViewColor: null, ghostColor: null,
         ghostLivery: null, renderer: {scene: 'scene'}};
var GHOST_GREY = '#9aa7b8', GHOST_RATE = 15;
var built = [], disposed = 0;
function Ghost(frames, hz) { this.frames = frames; this.hz = hz; }
function lapTimeline() { return []; }
function CarView(scene, spec, opts) {
  built.push({spec: spec, ghost: !!(opts && opts.ghost)});
  this.dispose = () => { disposed++; };
}
"""


def _ghost_ctx():
    ctx = _ctx(GHOST_CAR_STUB)
    ctx.eval(_fn("useGhost"))
    ctx.eval(_fn("ghostView"))
    return ctx


def test_the_ghost_you_chase_is_built_from_the_whole_livery():
    """The other half of the same rule as `startWatching` above, and the half that
    was already right - pinned because nothing covered it, and because the two
    ways of looking at one lap have to agree about whose car it is."""
    import json
    ctx = _ghost_ctx()
    ctx.eval("""
      useGhost([1, 2], 15, '#f2c94c',
               {body: '#f2c94c', rim_style: 'mesh', livery: 'twin'});
      ghostView();
    """)
    built = json.loads(ctx.eval("JSON.stringify(built)"))
    assert len(built) == 1
    assert built[0]["spec"] == {"body": "#f2c94c", "rim_style": "mesh",
                               "livery": "twin"}
    assert built[0]["ghost"] is True, "and it is see-through, being a ghost"


def test_a_ghost_with_only_a_colour_is_still_a_car():
    """A guest's lap, or one from before the garage: `CarView` reads a bare colour
    as a complete livery, so there is no branch downstream."""
    import json
    ctx = _ghost_ctx()
    ctx.eval("useGhost([1, 2], 15, '#f2c94c', null); ghostView();")
    assert json.loads(ctx.eval("JSON.stringify(built[0].spec)")) == "#f2c94c"
    # And a lap with nobody attached at all falls back to the grey.
    ctx.eval("useGhost([1, 2], 15, null, null); ghostView();")
    assert json.loads(ctx.eval("JSON.stringify(built[1].spec)")) == "#9aa7b8"


def test_two_drivers_on_one_colour_do_not_share_a_ghost_car():
    """The rebuild is keyed on the whole livery, not the body colour. Keyed on the
    colour, the second of two people on the same paint with different wheels was
    handed the first one's car - and the key was right about the only thing it was
    checking."""
    same = "{body: '#f2c94c', rim_style: '%s'}"
    ctx = _ghost_ctx()
    ctx.eval("useGhost([1, 2], 15, '#f2c94c', %s); ghostView();" % (same % "mesh"))
    ctx.eval("useGhost([1, 2], 15, '#f2c94c', %s); ghostView();" % (same % "dish"))
    assert ctx.eval("built.length") == 2, "different wheels, different car"
    assert ctx.eval("disposed") == 1, "and the old one is disposed of, not leaked"
    # The same car twice is not rebuilt: a CarView bakes its livery into half a
    # dozen materials and some geometry, so this happens per ghost and not per frame.
    ctx.eval("ghostView(); ghostView();")
    assert ctx.eval("built.length") == 2


# --- the colour picker's own arithmetic --------------------------------------
# `garage.js` has no test coverage at all: it is a page, and the way it is checked
# is by looking at it. These two functions are the exception, because they are
# arithmetic rather than appearance - a hue that comes back three degrees off, or a
# hex that loses its leading zero, is invisible in a screenshot and permanent in
# somebody's saved car.

GARAGE_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js",
                         "garage.js")


def _gfn(name):
    src = open(GARAGE_JS).read()
    m = re.search(r"^function %s\(.*?^\}" % re.escape(name), src, re.S | re.M)
    assert m, "%s is gone from garage.js, or is no longer a plain function" % name
    return m.group(0)


def _pick_ctx():
    ctx = jsrt.quickjs.Context()
    ctx.eval(_gfn("hexToHsv"))
    ctx.eval(_gfn("hsvToHex"))
    return ctx


@pytest.mark.parametrize("hex_", [
    "#000000", "#ffffff", "#808080",           # the greys, where hue is undefined
    "#ff0000", "#00ff00", "#0000ff",           # the primaries
    "#e8453c", "#3d8bfd", "#17bfa8", "#f2c94c",  # real body colours
    "#010203", "#0f0f0f",                      # near-black, where rounding bites
])
def test_a_colour_survives_the_round_trip(hex_):
    """Every swatch in the garage is a hex, and opening the picker on one turns it
    into hue/saturation/value and back. A round trip that is off by a bit turns
    "open the picker and close it again" into an edit."""
    ctx = _pick_ctx()
    got = ctx.eval("(function () { const k = hexToHsv('%s');"
                   " return hsvToHex(k.h, k.s, k.v); })()" % hex_)
    assert got == hex_


def test_a_hex_is_always_six_digits():
    """`toString(16)` drops leading zeros, so a dark colour comes out as `#102`
    without the pad - which is a valid CSS colour meaning something else entirely,
    and would be stored and sent to the server as one."""
    ctx = _pick_ctx()
    for h in range(0, 360, 37):
        got = ctx.eval("hsvToHex(%d, 0.9, 0.04)" % h)
        assert re.fullmatch(r"#[0-9a-f]{6}", got), got


def test_the_greys_keep_their_hue_while_you_drag_off_the_edge():
    """The reason the panel stores h/s/v rather than a hex. Saturation zero has no
    hue to read back - `hexToHsv('#ffffff').h` is 0, i.e. red - so a drag along the
    top of the square, where everything is white, would silently reset the hue to
    red on every move if the state round-tripped through a colour."""
    ctx = _pick_ctx()
    assert ctx.eval("hexToHsv('#ffffff').s") == 0
    assert ctx.eval("hexToHsv('#ffffff').h") == 0
    # Which is exactly why `S.pick` holds the three numbers: the value the user
    # chose is kept, not re-derived from what it currently looks like.
    assert ctx.eval("hsvToHex(210, 0, 1)") == "#ffffff"
    assert ctx.eval("hsvToHex(210, 1, 1)") == "#0080ff"


def test_hue_wraps_rather_than_clipping():
    """The hue strip is a ring drawn straight, so both ends are red and dragging
    past either of them has to keep working."""
    ctx = _pick_ctx()
    assert ctx.eval("hsvToHex(360, 1, 1)") == ctx.eval("hsvToHex(0, 1, 1)")
    assert ctx.eval("hsvToHex(-30, 1, 1)") == ctx.eval("hsvToHex(330, 1, 1)")


# --- the garage has a word for everything it offers --------------------------

def test_every_value_in_the_vocabulary_has_a_word_for_it():
    """`label()` falls back to the raw slug, so a value with no entry in `TITLE`
    renders as `chequers` or `shield` in lowercase, in a row of properly capitalised
    chips. It is not an error and it is not a crash - it just looks like a mistake,
    which is exactly the sort of thing an eye skips over. Two of them shipped that
    way inside an hour of each other.

    Read out of the two files rather than run, because `garage.js` needs a DOM, a
    renderer and a payload before it will do anything at all.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import garage
    src = open(GARAGE_JS).read()
    block = src[src.index("const TITLE = {"):]
    block = block[:block.index("};")]
    words = set(re.findall(r"(\w+):", block))
    for group in ("FINISHES", "LIVERIES", "RIM_STYLES", "BADGES"):
        for value in getattr(garage, group):
            assert value in words, "%s has no word in TITLE (%s)" % (value, group)


def test_no_word_is_left_over_for_something_nobody_offers():
    """The other direction, which is how `Chequers` sat in the map after the value
    was renamed: harmless, and a lie about what the garage has in it."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import garage
    src = open(GARAGE_JS).read()
    block = src[src.index("const TITLE = {"):]
    block = block[:block.index("};")]
    words = set(re.findall(r"(\w+):", block))
    known = set(garage.FINISHES) | set(garage.LIVERIES) | set(garage.RIM_STYLES) \
        | set(garage.BADGES)
    assert not (words - known), "TITLE has words for %s" % sorted(words - known)


# --- every run counts, and no run counts twice ------------------------------
#
# `drive_time` and `distance` were written only by `/api/run`, which is posted when a
# lap finishes - so 83% of attempts on the live board counted for nothing and a whole
# evening in a room counted for nothing at all. `reportActivity` is the funnel that
# fixes it, and these rules are what stop it counting anything twice.


def test_a_run_is_never_banked_twice():
    """`run.counted` is the whole correctness of this. `/api/run` adds a finished
    lap's own time and distance, so an abandon path reporting the same run would make
    every lap worth double - the two routes are additive on the server (see
    `test_activity_does_not_count_a_finished_lap_twice`) and the client is the only
    thing standing between them."""
    body = _body("reportActivity")
    assert "run.counted" in body, "reportActivity does not guard on the flag"
    assert re.search(r"if \([^)]*run\.counted\)[^\n]*return", body), \
        "the flag is read but does not stop the report"
    assert "run.counted = true" in body, "the report does not claim the run"
    # And the board path claims it too, because /api/run is what banks that one.
    src = _game_src()
    assert re.search(r"run\.counted = true;\s*\n\s*try \{\s*\n\s*const r = await fetch\("
                     r"'/api/run'", src), \
        "the /api/run path does not claim the run before posting it"


def test_the_flag_is_cleared_where_a_run_begins():
    """In `Run.start`, which is the one place a new run starts - and not in `reset`
    alone, because `start` is what zeroes the time and distance being counted."""
    course_js = os.path.join(os.path.dirname(GAME_JS), "course.js")
    src = open(course_js).read()
    start = re.search(r"^  start\(nowMs\) \{.*?^  \}$", src, re.S | re.M)
    assert start, "Run.start moved"
    assert "this.counted = false" in start.group(0)


def test_every_way_a_run_ends_reports_it():
    """The three that end a run for good. Each reads the run *before* the thing that
    destroys it: `resetToStart` zeroes it, `loadTrack` replaces it wholesale."""
    reset = _body("resetToStart")
    assert reset.index("reportActivity") < reset.index("S.run.reset()"), \
        "resetToStart reports after clearing the run, so it reports zero"
    load = _body("loadTrack")
    assert "reportActivity" in load and "opts.switched" in load
    assert load.index("reportActivity") < load.index("S.run = new Run("), \
        "loadTrack reports after replacing the run"
    assert "pagehide" in _game_src()


def test_a_room_lap_is_reported_even_though_it_is_not_a_record():
    """A room lap never reaches `/api/run` - `countsForTheBoard()` sends it back - so
    without this an evening of racing is nought minutes and nought kilometres. It is
    the one *finished* lap that reports through `/api/activity`."""
    src = _game_src()
    gate = re.search(r"if \(!countsForTheBoard\(\)\) \{(.*?)\n  \}", src, re.S)
    assert gate, "the room-lap branch in onFinish moved"
    assert "reportActivity" in gate.group(1)


def test_holding_the_page_open_does_not_bank_a_running_lap():
    """`visibilitychange` and `blur` are deliberately not listeners: both fire on an
    ordinary alt-tab mid-lap, which people come back from - and a banked run that
    then finishes is banked again by `/api/run`. Only `pagehide` means the document
    is really going, and a back/forward-cache restore is caught by `pageshow`."""
    src = _game_src()
    # Not "visibilitychange" absent from the file - it is *named* in the comment above
    # `pagehide` saying why it is not used, and asserting on the mention would fail on
    # the explanation rather than on the behaviour.
    assert not re.search(r"addEventListener\(\s*'visibilitychange'", src), \
        "visibilitychange banks runs that may still be running"
    assert re.search(r"addEventListener\('pageshow'", src), \
        "nothing catches a page restored from cache with a banked run"
    # `blur` exists, but only to drop held keys - it must not report.
    blur = re.search(r"addEventListener\('blur', \(\) => \{(.*?)\n  \}\);", src, re.S)
    assert blur and "reportActivity" not in blur.group(1)
