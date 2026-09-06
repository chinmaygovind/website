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
MUSIC_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "music.js")
MUSIC_JSON = os.path.join(os.path.dirname(__file__), "..", "static", "audio", "music.json")


def _src():
    """`sound.js` and the `music.js` it imports, flattened into one script.

    QuickJS is given a plain script rather than a module, so the `export`s come
    off and the one `import` is satisfied by pasting the imported file above it.
    Order matters only for the `const`s - the classes are hoisted either way.
    """
    music = re.sub(r"^export\s+", "", open(MUSIC_JS).read(), flags=re.M)
    music = re.sub(r"^export \{.*?\};?$", "", music, flags=re.M)
    sound = re.sub(r"^export\s+", "", open(SOUND_JS).read(), flags=re.M)
    sound = re.sub(r"^import .*?;$", "", sound, flags=re.M)
    return music + "\n" + sound

def _const(name):
    """Read out of the file rather than written down twice, so the curve and the
    tests that measure it cannot drift apart."""
    return float(re.search(r"const %s = ([\d.]+)" % name, open(SOUND_JS).read()).group(1))


IDLE_TC = _const("IDLE_TC")
WAKE_TC = _const("WAKE_TC")
SLEEP_TC = _const("SLEEP_TC")
IDLE_HZ = _const("IDLE_HZ")

# A Web Audio just real enough for the graph to be built and inspected. Every
# node records where it was connected and every param records the last value it
# was asked for, which between them is the whole of what this file does.
STUB = """
var LOG = {made: [], stopped: 0, disconnected: 0, audio: [], timers: []};

function Param(v) { this.value = v === undefined ? 0 : v; }
// The third argument is the whole of the fade, so it is recorded beside the
// value: "goes to zero" and "goes to zero over two seconds" are different sounds.
Param.prototype.setTargetAtTime = function (v, t, tc) {
  this.value = v; this.tc = tc; return this;
};
Param.prototype.setValueAtTime = function (v) { this.value = v; return this; };
Param.prototype.exponentialRampToValueAtTime = function (v) { this.value = v; return this; };
Param.prototype.linearRampToValueAtTime = function (v) { this.value = v; return this; };
// A crossfade cancels whatever the last one booked before it ramps, so that a
// seam arriving mid-fade does not fight the fade already running. Nothing is
// actually scheduled here, so there is nothing to drop - but it is called, and
// a Param that cannot be cancelled is not one.
Param.prototype.cancelScheduledValues = function () { return this; };

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
AudioContext.prototype.createMediaElementSource = function (el) {
  const n = new Node('mediasrc'); n.el = el; return n;
};

// An <audio> element, real enough to be cued, played and asked where it is.
// `src` is a property *and* an attribute because `music.js` reads it through
// `getAttribute` - it wants what was set, not the absolute URL a browser
// resolves it to, and the two differ in a browser but would not here.
function Audio() {
  this.preload = ''; this.crossOrigin = null; this.loop = false;
  this._src = null; this.currentTime = 0; this.duration = 0;
  this.readyState = 0; this.paused = true; this.plays = 0;
  this._on = {};
  LOG.made.push('audio');
  LOG.audio.push(this);
}
Object.defineProperty(Audio.prototype, 'src', {
  get: function () { return this._src; },
  // Setting src is what a browser treats as a fresh load: no metadata yet.
  set: function (v) { this._src = v; this.readyState = 0; this.currentTime = 0; },
});
Audio.prototype.getAttribute = function (k) { return k === 'src' ? this._src : null; };
Audio.prototype.play = function () { this.paused = false; this.plays++; return null; };
Audio.prototype.pause = function () { this.paused = true; };
Audio.prototype.addEventListener = function (k, fn) { (this._on[k] = this._on[k] || []).push(fn); };
Audio.prototype.removeEventListener = function (k, fn) {
  const a = this._on[k] || []; const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
};
/** Metadata arrived - which is what makes a seek stick. */
Audio.prototype.ready = function (dur) {
  this.readyState = 4; this.duration = dur;
  (this._on.loadedmetadata || []).slice().forEach(function (f) { f(); });
};

// Timers are recorded rather than run: every one of them here is the tail of a
// fade, and a test that wants the tail runs it by hand.
function setTimeout(fn, ms) { LOG.timers.push({fn: fn, ms: ms}); return LOG.timers.length; }
function clearTimeout() {}
function runTimers() {
  const t = LOG.timers; LOG.timers = [];
  t.forEach(function (x) { x.fn(); });
}

// `loadManifest` is called from `start()` and must not throw. It never
// resolves: the tests set `snd.manifest` by hand, because a manifest arriving
// after the context is exactly the case worth being explicit about.
function Pending() {}
Pending.prototype.then = function () { return this; };
Pending.prototype.catch = function () { return this; };
function fetch() { return new Pending(); }

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
    c.eval(_src())
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
    c.eval(_src())
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
    # and the panner into the bus that sits under the effects bus, so muting -
    # which is that bus's gain - still mutes the whole field.
    assert ctx.eval("v.panner.out.indexOf(snd.rivalBus) >= 0")
    assert ctx.eval("snd.rivalBus.out.indexOf(snd.sfx) >= 0")
    assert ctx.eval("snd.sfx.out.indexOf(snd.master) >= 0")


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
    c.eval(_src())
    c.eval("var snd = new Sound();")
    c.eval("snd.listener(camera()); snd.rivals([rival('a', 0, -10)]); snd.engine(1, 1, 0, false);")
    assert _n(c, "LOG.made.length") == 0
    assert _n(c, "snd.voices.size") == 0


# --- the two switches -------------------------------------------------------

def test_muting_the_sound_leaves_the_music_playing(ctx):
    """The whole reason there are two buses. Muting used to be the master's
    gain, which is above both of them, so a music switch under it would have
    been a switch the sound switch could silently override."""
    ctx.eval("snd.setMusic(true); snd.mute(true);")
    assert _n(ctx, "snd.sfx.gain.value") == 0
    assert _n(ctx, "snd.master.gain.value") > 0
    assert _n(ctx, "snd.music.bus.gain.value") > 0
    # and the other way round: no music, but the car is still audible.
    ctx.eval("snd.mute(false); snd.setMusic(false);")
    assert _n(ctx, "snd.sfx.gain.value") > 0
    assert _n(ctx, "snd.music.bus.gain.value") == 0


def test_the_music_is_beside_the_effects_rather_than_under_them(ctx):
    assert ctx.eval("snd.music.bus.out.indexOf(snd.master) >= 0")
    assert not ctx.eval("snd.music.bus.out.indexOf(snd.sfx) >= 0")


def test_a_muted_driver_who_wants_music_still_gets_a_context():
    """`start` used to bail on `!enabled` alone, which was the same thing when
    sound was the only switch and is not now."""
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    c.eval(_src())
    c.eval("var snd = new Sound(); snd.mute(true); snd.setMusic(true); snd.start();")
    assert c.eval("!!snd.ctx") and c.eval("!!snd.music")
    assert _n(c, "snd.sfx.gain.value") == 0
    # And with both off - which is the mute plus the default - there is still
    # nothing at all to build.
    c.eval("var q = new Sound(); q.mute(true); q.start();")
    assert not c.eval("!!q.ctx")


def test_the_music_switch_survives_being_set_before_there_is_a_context():
    """It is read off a stored preference at boot, which is long before the
    first gesture has built anything for it to be applied to."""
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    c.eval(_src())
    c.eval("var snd = new Sound(); snd.setMusic(true); snd.start();")
    assert _n(c, "snd.music.bus.gain.value") > 0
    c.eval("snd.setMusic(false);")
    assert _n(c, "snd.music.bus.gain.value") == 0


# --- the song ---------------------------------------------------------------
#
# The music is a file now rather than an arpeggio, so what is worth testing has
# moved with it: not where a note lands, but that the right song is picked, that
# the loop point is a crossfade rather than a cut, and that a track with no song
# is silence rather than the last track's song carrying on over it.

# A manifest small enough to read, with the two shapes that differ: a song with
# hand-written loop points and one that just plays the file.
FAKE = """
snd.manifest = {fade: 1.2, tracks: {
  costco: {file: 'costco.mp3', artist: 'MKWii', title: 'Coconut Mall',
           url: 'https://example.invalid/1'},
  rainbow: {file: 'rainbow.mp3', artist: 'Panman14', title: 'Rainbow Road',
            url: 'https://example.invalid/2', in: 20, out: 330, fade: 2.5},
  spa: {file: 'f1.mp3', artist: 'Hans Zimmer', title: 'F1'},
  monaco: {file: 'f1.mp3', artist: 'Hans Zimmer', title: 'F1'}
}};
"""


def _cued(ctx, deck=None):
    """The deck that is actually playing, as a plain dict."""
    d = "snd.music.decks[%s]" % ("snd.music.active" if deck is None else deck)
    return {
        "src": ctx.eval("%s.el.getAttribute('src')" % d),
        "at": _n(ctx, "%s.el.currentTime" % d),
        "paused": ctx.eval("%s.el.paused" % d),
        "gain": _n(ctx, "%s.gain.gain.value" % d),
    }


def _ready(ctx, dur):
    """Metadata arrives on both decks, because both are cued up front - see
    `_cue`. Readying only the playing one models a browser that does not
    preload, which is the thing that bug was."""
    ctx.eval("snd.music.decks.forEach(function (d) { d.el.ready(%f); });" % dur)


def test_both_decks_are_cued_before_either_is_needed(ctx):
    """The idle deck is what the crossfade brings in. Handed its `src` at that
    moment it has no metadata, so its seek to `in` is deferred while `play()`
    has already started it at 0:00 - and every song with an `in` came round the
    first time at the top of the file."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('rainbow');")
    assert ctx.eval("snd.music.decks[0].el.getAttribute('src')") == "/static/audio/rainbow.mp3"
    assert ctx.eval("snd.music.decks[1].el.getAttribute('src')") == "/static/audio/rainbow.mp3"


def test_the_song_follows_the_track(ctx):
    """The switcher swaps worlds without a navigation, so which song plays is
    not a page-load decision - `setSong` is called on every load and switch."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('costco');")
    assert _cued(ctx)["src"] == "/static/audio/costco.mp3"
    ctx.eval("snd.setSong('rainbow');")
    assert _cued(ctx)["src"] == "/static/audio/rainbow.mp3"


def test_a_track_with_no_song_is_silence_rather_than_the_last_one(ctx):
    """Figure Eight has no entry, and neither does a draft out of the editor or
    anything somebody made themselves. The failure worth preventing is not an
    error - it is Coconut Mall playing over a track that is not Costco."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('costco');")
    assert not _cued(ctx)["paused"]
    ctx.eval("snd.setSong('eight');")
    assert ctx.eval("snd.music.entry") is None
    assert ctx.eval("snd.music.decks.every(function (d) { return d.el.paused; })")
    assert ctx.eval("snd.currentSong()") is None


def test_the_three_circuits_share_one_file_without_restarting_it(ctx):
    """Spa, Silverstone and Monaco are one song in the manifest. Driving from
    one to another is the same file, and cueing it again would restart it."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('spa');")
    ctx.eval("snd.music.decks[snd.music.active].el.ready(300);")
    ctx.eval("snd.music.decks[snd.music.active].el.currentTime = 42;")
    ctx.eval("snd.setSong('monaco');")
    assert _cued(ctx)["at"] == 42
    assert not _cued(ctx)["paused"]


def test_the_loop_point_is_a_crossfade_and_not_a_cut(ctx):
    """A song trimmed to an in/out pair has a ringing tail at `out` and a cold
    start at `in`, so butting them together clicks. Both decks are audible
    across the seam, which is the whole of what stops it."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('rainbow');")
    _ready(ctx, 400)
    was = _n(ctx, "snd.music.active")
    # Inside the fade of the hand-written `out` at 330, not of the file's 400.
    ctx.eval("snd.music.decks[0].el.currentTime = 328.5; snd.musicTick();")
    assert _n(ctx, "snd.music.active") != was
    # The old deck is on its way down but still connected and still playing;
    # the new one is cued to `in` and coming up.
    assert ctx.eval("snd.music.decks[%d].el.paused" % 0) is False
    to = _cued(ctx)
    assert to["src"] == "/static/audio/rainbow.mp3"
    assert to["gain"] > 0
    # Only once the fade has actually run is the old deck parked.
    ctx.eval("runTimers();")
    assert ctx.eval("snd.music.decks[%d].el.paused" % 0) is True


def test_the_written_loop_points_are_honoured(ctx):
    """`in: 20` is a song that starts twenty seconds in, every time round -
    including the first, which is the one a cold `currentTime` gets wrong."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('rainbow');")
    _ready(ctx, 400)
    assert _cued(ctx)["at"] == 20
    ctx.eval("snd.music.decks[0].el.currentTime = 329; snd.musicTick();")
    assert _cued(ctx)["at"] == 20


def test_a_seek_before_the_metadata_is_applied_when_it_arrives(ctx):
    """Setting `currentTime` on an element that has not loaded is thrown away,
    which is how a song with an `in` starts at zero on a cold page."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('rainbow');")
    assert _n(ctx, "snd.music.decks[0].el.readyState") == 0
    assert _cued(ctx)["at"] == 0          # nothing to seek yet
    _ready(ctx, 400)
    assert _cued(ctx)["at"] == 20         # and the seek was kept for this moment


def test_a_song_shorter_than_its_written_out_still_loops(ctx):
    """`out` is trusted only as far as the file goes. A manifest that outlives
    the file it names would otherwise wait for a moment that never comes."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('rainbow');")
    _ready(ctx, 100)                                # written out is 330
    ctx.eval("snd.music.decks[0].el.currentTime = 99; snd.musicTick();")
    assert _n(ctx, "snd.music.active") == 1


def test_the_music_off_plays_nothing(ctx):
    ctx.eval(FAKE + "snd.setSong('costco');")       # off is the default
    for t in range(6):
        ctx.eval("snd.ctx.currentTime = %d; snd.musicTick();" % t)
    assert ctx.eval("!snd.music.decks || snd.music.decks.every(function (d) { return d.el.paused; })")


def test_switching_the_music_on_starts_the_song_it_was_already_given(ctx):
    """The track is loaded long before anybody opens settings, so turning the
    switch on has to pick up the song that is already sitting there."""
    ctx.eval(FAKE + "snd.setSong('costco');")
    assert ctx.eval("!snd.music.decks || snd.music.decks[0].el.paused")
    ctx.eval("snd.setMusic(true);")
    assert not _cued(ctx)["paused"]
    assert _cued(ctx)["src"] == "/static/audio/costco.mp3"


def test_a_manifest_that_lands_after_the_track_still_gets_played(ctx):
    """`setSong` runs from `loadTrack` and the manifest is a fetch, so on a cold
    load the slug is known first. Either order has to end up playing."""
    ctx.eval("snd.setMusic(true); snd.setSong('costco');")   # no manifest yet
    assert ctx.eval("snd.currentSong()") is None
    ctx.eval(FAKE + "snd._applySong();")
    assert _cued(ctx)["src"] == "/static/audio/costco.mp3"


def test_the_card_is_told_what_is_playing(ctx):
    """The now-playing card is a credit, so what it needs is the artist, the
    title and the link - read from the manifest and not from the filename."""
    ctx.eval(FAKE + "snd.setMusic(true); snd.setSong('costco');")
    assert ctx.eval("snd.currentSong().artist") == "MKWii"
    assert ctx.eval("snd.currentSong().title") == "Coconut Mall"
    assert ctx.eval("snd.currentSong().url") == "https://example.invalid/1"


def test_music_is_off_until_it_is_asked_for(ctx):
    """The engine is what the game sounds like; a song over the top of it is a
    preference, so it is one you switch on rather than one you switch off."""
    assert ctx.eval("snd.musicOn") is False
    assert _n(ctx, "snd.music.bus.gain.value") == 0
    # and the sound is the other way round.
    assert ctx.eval("snd.enabled") is True
    assert _n(ctx, "snd.sfx.gain.value") > 0


# --- a car nobody is driving ------------------------------------------------
#
# The stub applies a target instantly, so what is checkable here is the pair of
# numbers every one of these calls is: what the gain is heading for, and how
# long it is taking to get there. That is the whole of the design - the fade is
# an exponential decay, which is a straight line in dB and so the one curve that
# sounds like one steady movement, and it is the time constant that says how
# steady. A test that only looked at the target would pass on a cut.

def _run(ctx, speed=0, throttle=0, air="false"):
    ctx.eval("snd.engine(%f, %f, 0, %s);" % (speed, throttle, air))
    return _n(ctx, "snd.engGain.gain.value")


def test_a_parked_car_starts_going_quiet_at_once(ctx):
    """No hold in front of it. It used to sit at full volume for five seconds
    and then drop in under three, which is the same time arranged the worst way
    round: nothing happens, and then something obviously happens."""
    assert _run(ctx, speed=0.5, throttle=1) > 0
    assert _run(ctx) == 0, "still heading for a level while parked"
    assert _n(ctx, "snd.engGain.gain.tc") == IDLE_TC
    # And the whine with it, or the engine goes quiet and leaves a tone behind.
    assert _n(ctx, "snd.whineGain.gain.value") == 0


def test_the_fade_is_slow_and_the_way_back_is_not(ctx):
    """A fade-in is a key press being answered late, so there isn't one."""
    _run(ctx)
    assert _n(ctx, "snd.engGain.gain.tc") == IDLE_TC
    assert _run(ctx, throttle=1) > 0
    assert _n(ctx, "snd.engGain.gain.tc") == WAKE_TC
    assert WAKE_TC < 0.09 < IDLE_TC, "the fade has to be the slowest of the three"
    # A second frame on the power is an ordinary frame again, not a wake.
    _run(ctx, throttle=1)
    assert _n(ctx, "snd.engGain.gain.tc") > WAKE_TC


def test_it_darkens_as_it_goes(ctx):
    """Distance eats high frequencies first and an engine off the load loses
    its top end for real, so the lowpass closes on the way down - and the whine,
    which is the highest thing in the car, is given half the time and leaves
    first. Gain on its own reads as somebody turning a knob."""
    _run(ctx, speed=1, throttle=1)
    bright = _n(ctx, "snd.engFilter.frequency.value")
    _run(ctx)
    assert _n(ctx, "snd.engFilter.frequency.value") == IDLE_HZ < bright
    assert _n(ctx, "snd.engFilter.frequency.tc") == IDLE_TC
    assert _n(ctx, "snd.whineGain.gain.tc") < _n(ctx, "snd.engGain.gain.tc")


def test_the_three_things_that_count_as_driving(ctx):
    """Throttle, movement above a crawl, or air - and nothing else, because
    nothing else is a car making a noise for a reason."""
    _run(ctx)
    assert _run(ctx, throttle=1) > 0, "a foot on the throttle"
    _run(ctx)
    assert _run(ctx, speed=0.5) > 0, "rolling"
    _run(ctx)
    assert _run(ctx, air="true") > 0, "in the air"
    # A car that drag has left rolling at a unit a second is parked, and the
    # fade has to happen for it or it never happens at all.
    assert _run(ctx, speed=0.005) == 0


def test_a_car_that_keeps_moving_never_fades(ctx):
    for _ in range(60):
        assert _run(ctx, speed=0.5) > 0
        assert _n(ctx, "snd.engGain.gain.tc") != IDLE_TC


def test_a_parked_rival_goes_the_same_way(ctx):
    """A room where nobody has pressed anything is seven of these."""
    ctx.eval("snd.rivals([rival('a', 0, -10, {speedFrac: 0.5, throttle: true})]);")
    assert _n(ctx, "snd.voices.get('a').engGain.gain.value") > 0
    ctx.eval("snd.rivals([rival('a', 0, -10, {speedFrac: 0})]);")
    assert _n(ctx, "snd.voices.get('a').engGain.gain.value") == 0
    assert _n(ctx, "snd.voices.get('a').engGain.gain.tc") == IDLE_TC
    assert _n(ctx, "snd.voices.get('a').engFilter.frequency.value") == IDLE_HZ
    # Off the line and it is a car again, at once.
    ctx.eval("snd.rivals([rival('a', 0, -10, {speedFrac: 0.4, throttle: true})]);")
    assert _n(ctx, "snd.voices.get('a').engGain.gain.value") > 0
    assert _n(ctx, "snd.voices.get('a').engGain.gain.tc") == WAKE_TC


def test_a_hidden_tab_takes_the_sound_with_it(ctx):
    """rAF stops in a hidden tab and the audio clock does not, so every gain
    the frame loop drives holds its last value until the tab comes back. The
    idle fade cannot cover this - it is driven from the same loop."""
    _run(ctx, speed=1, throttle=1)
    ctx.eval("snd.draft(1, 1); snd.rivals([rival('a', 0, -10)]);")
    assert _n(ctx, "snd.engGain.gain.value") > 0
    ctx.eval("snd.sleep();")
    for part in ("engGain", "whineGain", "tyreGain", "windGain", "draftGain", "rivalBus"):
        assert _n(ctx, "snd.%s.gain.value" % part) == 0, part
        assert _n(ctx, "snd.%s.gain.tc" % part) == SLEEP_TC, part
    # Quicker than a resting car, which is still on the screen and should
    # settle gently; this is somebody who has gone.
    assert SLEEP_TC < IDLE_TC
    # Not the mute's gain, which belongs to the switch in settings.
    assert _n(ctx, "snd.sfx.gain.value") > 0
    # Back, and the field with it; the rest is written by the next frame.
    ctx.eval("snd.wake();")
    assert _n(ctx, "snd.rivalBus.gain.value") > 0
    assert _run(ctx, speed=1, throttle=1) > 0


def test_sleeping_before_the_first_gesture_is_a_no_op():
    """Alt-tabbing away from a page nobody has clicked on must not be the thing
    that builds an AudioContext."""
    c = jsrt.quickjs.Context()
    c.eval(STUB)
    c.eval(_src())
    c.eval("var snd = new Sound(); snd.sleep(); snd.wake();")
    assert _n(c, "LOG.made.length") == 0
