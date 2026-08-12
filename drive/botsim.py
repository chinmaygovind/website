"""The bots, running on the server, in the game's own physics.

A room's bots are real `Car`s being stepped by the real `Car.step` at the real
`FIXED_DT`, inside a QuickJS runtime that has `physics.js`, `course.js`,
`trackmesh.js` and `bot.js` loaded - the same files the browser runs. There is
no Python model of the car anywhere in here and there must never be one: a
second implementation of the physics is a thing that can disagree with the game,
which is the argument `verify.py` already makes about the anti-cheat and it
applies twice over to something people race against.

Why the server and not the host's browser
-----------------------------------------
The host's tab is the cheap place to run these - it has V8 and a spare core, and
it already steps one car. It was rejected for three reasons and the first is
fatal on its own:

  * **A background tab stops.** `requestAnimationFrame` is throttled to nothing
    when the host switches tab, so the field would freeze mid-race for everybody
    else in the room. The host is the one person who cannot be relied on to keep
    looking at it.
  * Bots would arrive on every other screen a round trip late, and would
    themselves see everybody a round trip late - a bot's overtake would be aimed
    at where you were 60ms ago.
  * The host would be authoring the position of eight cars nobody can check.

What it costs
-------------
Measured, eight bots with contact, tows and the JSON crossing, on a laptop:
**4.6-7.0 ms of CPU per 30Hz tick**, and about 30-50MB of RSS for the runtime
plus one built track. That lands on the single eventlet worker that also relays
every pose, so two things bound it: `MAX_BOTS`, and `DRIVE_BOTS=0` in the box
`.env`, which turns the whole feature off without a deploy. `tick_ms()` reports
the rolling cost so the box can be measured rather than guessed about.

Built tracks are shared between rooms on the same track, because the collider is
by far the biggest thing here and it is read-only once built.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bots                                              # noqa: E402
import jsrt                                              # noqa: E402
import tracks as tracks_mod                              # noqa: E402
import tuning                                            # noqa: E402

# The most bots one room may hold. `MAX_ROOM` is 8 seats and a bot takes one, so
# this is only ever reached in a room somebody is racing alone in - which is
# exactly the case this feature was asked for, hence 7 rather than something
# smaller.
MAX_BOTS = 7

# A single tick may not take longer than this. It is a backstop against a bug
# rather than a budget: an honest tick is single-digit milliseconds, and quickjs
# resets this clock per eval, so it can never accumulate into a room that dies
# after an hour.
EVAL_LIMIT_S = 2

# Assembling a track's collider is a one-off and the long ones take seconds, so
# it gets its own, much looser ceiling. See `build`.
BUILD_LIMIT_S = 30

_rt = None
_worlds = {}          # room code -> World
_built_order = []     # slugs built in JS, oldest first
_cost = []            # rolling tick costs, ms


def enabled():
    """Is anything here allowed to run? `DRIVE_BOTS=0` is the switch on the box."""
    flag = os.environ.get("DRIVE_BOTS", "")
    if flag:
        return flag.lower() in ("1", "true", "yes")
    return jsrt.HAVE_QUICKJS


def available():
    """Can bots actually be seated - the switch is on and the engine is here."""
    return enabled() and jsrt.HAVE_QUICKJS


def _read(name):
    with open(os.path.join(HERE, name)) as f:
        return f.read()


def runtime():
    """The one QuickJS context every room's bots share.

    One rather than one per room: the bundle is the same, the tuning is the
    same, and the only per-room state is a `BotWorld` object, which lives in a
    registry on the JS side keyed by room code. A context per room would mean a
    copy of the game's code per room for no isolation anybody needs - these are
    all the same trusted program.
    """
    global _rt
    if _rt is None:
        extra = [jsrt._strip_modules(_read(os.path.join("static", "js", "bot.js"))),
                 jsrt._strip_modules(_read("botworld.js")),
                 "var WORLDS = {};"]
        _rt = jsrt.Runtime(seconds=EVAL_LIMIT_S, extra=extra)
        _rt.ctx.eval("var T = %s;" % tuning.as_json())
        # Only the built tracks are shared; `TRACKS` itself is the metadata the
        # builder needs and is small.
        _rt.ctx.eval("var TRACKS = %s;" % json.dumps(tracks_mod.TRACKS))
        _rt.ctx.eval("var BUILT = {};")
    return _rt


def build(rt, slug):
    """Build one track's collider in JS, once, shared by every room on it.

    **Outside the per-eval time limit**, which is set for a *tick* - single
    digit milliseconds - and is far too tight for this: assembling the longest
    tracks in the pool takes over two seconds of QuickJS, so leaving the limit
    where it is meant that a room on Mount Joy threw on its first bot and, since
    a world that throws is dropped rather than taken seriously, silently had no
    bots at all. Raised for the build and put straight back.
    """
    expr = ("if (!BUILT[%(s)s]) BUILT[%(s)s] = "
            "buildTrack(TRACKS.find(t => t.slug === %(s)s), T);"
            % {"s": json.dumps(slug)})
    if rt.ctx.eval("!!BUILT[%s]" % json.dumps(slug)):
        return
    t0 = time.monotonic()
    try:
        rt.ctx.set_time_limit(BUILD_LIMIT_S)
        rt.ctx.eval(expr)
    finally:
        rt.ctx.set_time_limit(EVAL_LIMIT_S)
    if slug in _built_order:
        _built_order.remove(slug)
    _built_order.append(slug)
    forget_unused()
    return time.monotonic() - t0


# How many built tracks may sit in JS with no room using them.
#
# **They are big and they never expire on their own.** One built collider is
# 20-40MB and `BUILT` is keyed by slug, so a service that has hosted a room on
# every track in the pool accumulates all sixteen - which is most of a box with
# a gigabyte across five services. It is not theoretical: the calibrator builds
# the whole pool in one runtime and was killed partway through doing it, with no
# traceback, which is what being killed looks like.
#
# Two spare is enough to make the common moves free - a host flicking between
# two tracks between races - while bounding the total at three or four.
BUILT_SPARE = 2


def forget_unused():
    """Drop built tracks no live world needs, keeping a couple in reserve.

    Called whenever the set of worlds changes. The tracks in use are pinned; the
    rest are an LRU, and JS garbage collects a collider the moment nothing on
    either side refers to it.
    """
    if _rt is None:
        return
    keep = {w.slug for w in _worlds.values()}
    spare = [s for s in _built_order if s not in keep]
    drop = spare[:max(0, len(spare) - BUILT_SPARE)]
    for slug in drop:
        _rt.ctx.eval("delete BUILT[%s];" % json.dumps(slug))
        _built_order.remove(slug)


def tick_ms():
    """The rolling mean cost of a tick, in ms, and how many were measured."""
    if not _cost:
        return (0.0, 0)
    return (sum(_cost) / len(_cost), len(_cost))


class World:
    """One room's bots. Addressed by room code; the objects live in JS."""

    def __init__(self, code, slug):
        self.code = code
        self.slug = slug
        self.rt = runtime()
        self.bots = {}                 # pid -> level
        build(self.rt, slug)
        self.rt.ctx.eval(
            "WORLDS[%(c)s] = new BotWorld(TRACKS.find(t => t.slug === %(s)s), T,"
            "                             BUILT[%(s)s]);"
            % {"s": json.dumps(slug), "c": json.dumps(code)})

    def _js(self, expr):
        return self.rt.ctx.eval("WORLDS[%s].%s" % (json.dumps(self.code), expr))

    def _json(self, expr):
        return self.rt.call("WORLDS[%s].%s" % (json.dumps(self.code), expr))

    def add(self, pid, level, seed=0):
        """Put one on the road. Returns the line it ended up driving."""
        line, source = bots.line_for(self.slug, level)
        prof = bots.profile(self.slug, level, seed=seed)
        self._js("add(%s, %s, %s)" % (json.dumps(pid), json.dumps(line),
                                      json.dumps(prof)))
        self.bots[pid] = level
        return source

    def remove(self, pid):
        self.bots.pop(pid, None)
        self._js("remove(%s)" % json.dumps(pid))

    def place_grid(self, slots):
        """`{pid: slot}` - line them up and hold them there for the lights."""
        for pid, slot in slots.items():
            if pid in self.bots:
                self._js("placeGrid(%s, %d)" % (json.dumps(pid), int(slot)))

    def restart(self, pid, slot, now_ms):
        """Another lap, from the line. Practice and qualifying only."""
        if pid in self.bots:
            self._js("restart(%s, %d, %d)" % (json.dumps(pid), int(slot),
                                              int(now_ms)))

    def ghost_of(self, pid):
        """The replay of the lap this bot has just driven, packed like any other.

        `Run` records one on every timed lap whether anybody asks or not, so
        this is a read rather than a recording. It is what lets a bot on
        provisional pole hand its lap to the room to chase - which is the one
        ghost worth having during a session whose whole point is that lap.
        """
        if pid not in self.bots:
            return None
        return self._json("get(%s).run.ghost" % json.dumps(pid))

    def release(self):
        self._js("release()")

    def green(self, now_ms):
        self._js("green(%d)" % int(now_ms))

    def tick(self, dt, humans, now_ms, phase="free", since=None):
        """Advance every bot and hand back their poses and whatever happened.

        `humans` is the room's real cars as `[{pid, x, y, z, qx..qw, vx, vy, vz,
        prog, done}]`. They are handed over so the bots can hit them, tow off
        them and race them - a bot with no idea the people are there is a bot
        that drives through them.
        """
        if not self.bots:
            return [], []
        t0 = time.monotonic()
        self._js("setHumans(%s)" % json.dumps(humans))
        poses = self._json("tick(%r, %d, %s, %s)"
                           % (float(dt), int(now_ms), json.dumps(phase),
                              "null" if since is None else repr(float(since))))
        events = self._json("drainEvents()")
        _cost.append((time.monotonic() - t0) * 1000.0)
        del _cost[:-300]
        return poses, events

    def close(self):
        self.rt.ctx.eval("delete WORLDS[%s];" % json.dumps(self.code))
        self.bots = {}


def world(code, slug, create=True):
    """This room's bot world, rebuilt if the room has changed track."""
    if not available():
        return None
    w = _worlds.get(code)
    if w is not None and w.slug != slug:
        w.close()
        w = None
        _worlds.pop(code, None)
    if w is None:
        if not create:
            return None
        w = _worlds[code] = World(code, slug)
    return w


def drop(code):
    """Forget a room's bots entirely - the room has gone, or its last bot has."""
    w = _worlds.pop(code, None)
    if w is not None:
        w.close()
        forget_unused()


def live_codes():
    return list(_worlds)


# ---------------------------------------------------------------------------
# Offline: one bot, one track, one lap, as fast as the box can compute it
# ---------------------------------------------------------------------------

def solo_lap(slug, level, pace=None, fps=60, max_t=240, seed=1, line=None):
    """Drive one level round one track alone. What the calibrator measures.

    Deliberately the same `BotWorld` and the same `Bot` a race uses, with only
    the clock different: a calibration run that measured some other driver would
    be calibrating some other driver.
    """
    rt = runtime()
    track = tracks_mod.get(slug)
    if not track:
        raise ValueError("no such track: %s" % slug)
    line, source = bots.line_for(slug, level, force=line)
    prof = bots.profile(slug, level, seed=seed, pace=pace)
    build(rt, slug)
    # A whole lap is one `eval`, and the live limit is deliberately tight enough
    # that a *tick* cannot wedge a room - so a two-minute lap of Big Red trips it
    # every time. Lifted for the call and put straight back, because the same
    # runtime is the one the rooms use when this is being run from a test.
    try:
        rt.ctx.set_time_limit(max(60, int(max_t)))
        out = rt.call("botLap(TRACKS.find(t => t.slug === %s), T, %s, %s, %s)"
                      % (json.dumps(slug), json.dumps(line), json.dumps(prof),
                         json.dumps({"fps": fps, "maxT": max_t})))
    finally:
        rt.ctx.set_time_limit(EVAL_LIMIT_S)
    out["source"] = source
    out["pace"] = prof["pace"]
    return out
