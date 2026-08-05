"""The spatial half of the audio, run for real against a stub Web Audio.

`sound.js` is the one file in the game a screenshot cannot check and the
autopilot never touches: it builds a graph of nodes and then only ever moves
numbers about inside it, so a wrong `connect` or a voice that is rebuilt every
frame is completely silent to look at and completely wrong to listen to. It is
also the file with the most nodes per line.

So it is run here the way `test_pending.js` runs the pending-run store: the real
module in QuickJS, against a fake AudioContext that records what was connected
to what and what was asked to move. What is under test is the wiring and the
bookkeeping - that a rival gets one voice and keeps it, that dropping out of the
list takes the voice with it, that everything a rival makes goes through its own
panner at its own position, and that the ears face the way the camera does.
"""

import os
import re

import pytest

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

SOUND_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "sound.js")

# A Web Audio just real enough for the graph to be built and inspected. Every
# node records where it was connected and every param records the last value it
# was asked for, which between them is the whole of what this file does.
STUB = """
var LOG = {made: [], stopped: 0, disconnected: 0};

function Param(v) { this.value = v === undefined ? 0 : v; }
Param.prototype.setTargetAtTime = function (v) { this.value = v; return this; };
Param.prototype.setValueAtTime = function (v) { this.value = v; return this; };
Param.prototype.exponentialRampToValueAtTime = function (v) { this.value = v; return this; };
Param.prototype.linearRampToValueAtTime = function (v) { this.value = v; return this; };

function Node(kind) {
  this.kind = kind;
  this.out = [];
  LOG.made.push(kind);
}
Node.prototype.connect = function (dst) { this.out.push(dst); return dst; };
Node.prototype.disconnect = function () { LOG.disconnected++; this.out = []; };
Node.prototype.start = function () { this.started = true; };
Node.prototype.stop = function () { LOG.stopped++; };

function AudioContext() {
  this.currentTime = 0;
  this.sampleRate = 480;                 // small: the noise buffer is filled for real
  this.destination = new Node('destination');
  this.listener = {
    positionX: new Param(), positionY: new Param(), positionZ: new Param(),
    forwardX: new Param(), forwardY: new Param(), forwardZ: new Param(),
    upX: new Param(), upY: new Param(), upZ: new Param(),
  };
}
AudioContext.prototype.createGain = function () {
  const n = new Node('gain'); n.gain = new Param(0); return n;
};
AudioContext.prototype.createBiquadFilter = function () {
  const n = new Node('filter');
  n.frequency = new Param(0); n.Q = new Param(0); n.type = '';
  return n;
};
AudioContext.prototype.createOscillator = function () {
  const n = new Node('osc');
  n.frequency = new Param(0); n.detune = new Param(0); n.type = '';
  return n;
};
AudioContext.prototype.createBufferSource = function () {
  const n = new Node('bufsrc'); n.buffer = null; n.loop = false; return n;
};
AudioContext.prototype.createPanner = function () {
  const n = new Node('panner');
  n.positionX = new Param(); n.positionY = new Param(); n.positionZ = new Param();
  return n;
};
AudioContext.prototype.createBuffer = function (ch, len) {
  const data = new Float64Array(len);
  return {getChannelData: function () { return data; }};
};
var window = {AudioContext: AudioContext};

// A camera looking down -Z from the origin, which is the identity rotation.
function camera(q, p) {
  return {position: p || {x: 0, y: 0, z: 0}, quaternion: q || {x: 0, y: 0, z: 0, w: 1}};
}
function rival(id, x, z, opts) {
  const o = opts || {};
  return {id: id, x: x, y: 0, z: z,
          speedFrac: o.speedFrac == null ? 0.8 : o.speedFrac,
          throttle: !!o.throttle, drift: !!o.drift, air: !!o.air,
          charge: o.charge || 0, boost: o.boost || 0};
}
"""


@pytest.fixture()
def ctx():
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    src = re.sub(r"^export\s+", "", open(SOUND_JS).read(), flags=re.M)
    c.eval(src)
    c.eval("var snd = new Sound(); snd.start();")
    return c


def _n(ctx, expr):
    return ctx.eval("(%s)" % expr)


# --- the voices -------------------------------------------------------------

def test_a_car_in_the_list_gets_a_voice_and_keeps_it():
    """One voice per car, reused every frame. Rebuilding it would mean new
    oscillators thirty times a second, which is both a click and a leak."""
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    c.eval(re.sub(r"^export\s+", "", open(SOUND_JS).read(), flags=re.M))
    c.eval("var snd = new Sound(); snd.start();")
    c.eval("snd.rivals([rival('a', 0, -10)]);")
    made = _n(c, "LOG.made.length")
    for _ in range(5):
        c.eval("snd.rivals([rival('a', 0, -10)]);")
    assert _n(c, "snd.voices.size") == 1
    # Nothing new built by five more frames of the same car (bar the odd
    # one-shot, of which there is none here: it is not boosting).
    assert _n(c, "LOG.made.length") == made


def test_a_car_that_leaves_the_list_takes_its_voice_with_it(ctx):
    """This is the whole phase rule: hand back nothing and the field goes
    quiet, so qualifying, a replay and an empty room all cost one call."""
    ctx.eval("snd.rivals([rival('a', 0, -10), rival('b', 0, -20)]);")
    assert _n(ctx, "snd.voices.size") == 2
    ctx.eval("snd.rivals([rival('a', 0, -10)]);")
    assert _n(ctx, "snd.voices.size") == 1 and ctx.eval("snd.voices.has('a')")
    ctx.eval("snd.rivals(null);")
    assert _n(ctx, "snd.voices.size") == 0
    # And it was actually torn down, not just forgotten about.
    assert _n(ctx, "LOG.stopped") >= 8 and _n(ctx, "LOG.disconnected") > 0


def test_only_the_closest_few_are_given_a_voice(ctx):
    """The caller sorts near-to-far, so the cap spends them on the cars close
    enough to hear rather than on whoever happens to be first in the map."""
    ctx.eval("snd.rivals([rival('a',0,-1), rival('b',0,-2), rival('c',0,-3), "
             "rival('d',0,-4), rival('e',0,-5), rival('f',0,-6), rival('g',0,-7), "
             "rival('h',0,-8), rival('i',0,-9)]);")
    assert _n(ctx, "snd.voices.size") == 7
    assert ctx.eval("snd.voices.has('a')") and not ctx.eval("snd.voices.has('i')")


# --- where a rival is -------------------------------------------------------

def test_everything_a_rival_makes_comes_from_where_the_rival_is(ctx):
    """Engine, tyres and tow all through the one panner - the point of the
    exercise is that a car is a place, not a channel."""
    ctx.eval("snd.rivals([rival('a', 7, -13)]);")
    ctx.eval("var v = snd.voices.get('a');")
    assert _n(ctx, "v.panner.positionX.value") == 7
    assert _n(ctx, "v.panner.positionZ.value") == -13
    for part in ("engFilter", "tyreGain", "draftGain"):
        assert ctx.eval("v.%s.out.indexOf(v.panner) >= 0" % part), part
    # and the panner into the bus that sits under the master, so muting - which
    # is the master's gain - still mutes the whole field.
    assert ctx.eval("v.panner.out.indexOf(snd.rivalBus) >= 0")
    assert ctx.eval("snd.rivalBus.out.indexOf(snd.master) >= 0")


def test_a_new_car_is_placed_rather_than_slid_in_from_the_last_one(ctx):
    """A voice starts where its car is. Smoothing that would drag the sound
    across the map from wherever the previous car with that id was."""
    ctx.eval("snd.rivals([rival('a', 100, -200)]);")
    assert _n(ctx, "snd.voices.get('a').panner.positionX.value") == 100


# --- what a rival is doing --------------------------------------------------

def test_the_tow_is_louder_when_it_pays_than_while_it_fills(ctx):
    """The charge is the warning and the boost is the event, so they cannot be
    the same sound - and the band opens up as well as getting louder."""
    ctx.eval("snd.rivals([rival('a', 0, -10, {charge: 1})]);")
    filling = _n(ctx, "snd.voices.get('a').draftGain.gain.value")
    fill_hz = _n(ctx, "snd.voices.get('a').draftFilter.frequency.value")
    ctx.eval("snd.rivals([rival('a', 0, -10, {boost: 1})]);")
    paying = _n(ctx, "snd.voices.get('a').draftGain.gain.value")
    assert 0 < filling < paying
    assert fill_hz < _n(ctx, "snd.voices.get('a').draftFilter.frequency.value")


def test_a_car_with_no_tow_makes_no_tow_noise(ctx):
    ctx.eval("snd.rivals([rival('a', 0, -10)]);")
    assert _n(ctx, "snd.voices.get('a').draftGain.gain.value") == 0


def test_the_boost_arriving_is_a_one_shot_in_their_direction(ctx):
    """The only warning you get that the car behind you is about to not be
    behind you. Once, on the edge - not every frame the boost is running."""
    ctx.eval("snd.rivals([rival('a', 0, -10, {charge: 1})]);")
    before = _n(ctx, "LOG.made.length")
    ctx.eval("snd.rivals([rival('a', 0, -10, {boost: 1})]);")
    fired = _n(ctx, "LOG.made.length") - before
    assert fired > 0
    ctx.eval("snd.rivals([rival('a', 0, -10, {boost: 0.5})]);")
    assert _n(ctx, "LOG.made.length") - before == fired, "fired again mid-boost"


def test_a_rival_on_the_power_revs_harder_than_one_coasting(ctx):
    ctx.eval("snd.rivals([rival('a', 0, -10, {speedFrac: 0.2})]);")
    slow = _n(ctx, "snd.voices.get('a').osc[0].frequency.value")
    ctx.eval("snd.rivals([rival('a', 0, -10, {speedFrac: 1, throttle: true})]);")
    assert _n(ctx, "snd.voices.get('a').osc[0].frequency.value") > slow


def test_tyres_only_squeal_on_the_ground(ctx):
    ctx.eval("snd.rivals([rival('a', 0, -10, {drift: true})]);")
    assert _n(ctx, "snd.voices.get('a').tyreGain.gain.value") > 0
    ctx.eval("snd.rivals([rival('a', 0, -10, {drift: true, air: true})]);")
    assert _n(ctx, "snd.voices.get('a').tyreGain.gain.value") == 0


# --- where the ears are -----------------------------------------------------

def test_the_ears_face_the_way_the_camera_does(ctx):
    """Taken off the camera's quaternion, so a rival on your left is on your
    left. Identity is looking down -Z, which is three.js's own convention."""
    ctx.eval("snd.listener(camera(null, {x: 3, y: 4, z: 5}));")
    L = "snd.ctx.listener"
    assert _n(ctx, L + ".positionX.value") == 3
    assert _n(ctx, L + ".positionZ.value") == 5
    assert _n(ctx, L + ".forwardZ.value") == pytest.approx(-1)
    assert _n(ctx, L + ".upY.value") == pytest.approx(1)

    # Turned right round: forward flips and up does not.
    ctx.eval("snd.listener(camera({x: 0, y: 1, z: 0, w: 0}));")
    assert _n(ctx, L + ".forwardZ.value") == pytest.approx(1)
    assert _n(ctx, L + ".upY.value") == pytest.approx(1)


def test_the_ears_roll_with_the_camera_through_a_loop(ctx):
    """The camera rolls with the car, and the listener has to go with it or a
    rival above you stops being above you halfway round."""
    ctx.eval("snd.listener(camera({x: 0, y: 0, z: 1, w: 0}));")   # 180 about Z
    assert _n(ctx, "snd.ctx.listener.upY.value") == pytest.approx(-1)
    assert _n(ctx, "snd.ctx.listener.forwardZ.value") == pytest.approx(-1)


def test_nothing_is_touched_before_the_first_gesture():
    """No context until somebody presses something, or the browser warns about
    autoplay - so every one of these has to be a no-op until then."""
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    c.eval(re.sub(r"^export\s+", "", open(SOUND_JS).read(), flags=re.M))
    c.eval("var snd = new Sound();")
    c.eval("snd.listener(camera()); snd.rivals([rival('a', 0, -10)]); snd.engine(1, 1, 0, false);")
    assert _n(c, "LOG.made.length") == 0
    assert _n(c, "snd.voices.size") == 0
