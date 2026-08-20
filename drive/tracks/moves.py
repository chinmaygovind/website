"""A track as a *document*: the authored moves, recorded and replayed.

Why this exists, and why `Builder.sections` is not it
----------------------------------------------------
`Builder` collects `sections` as it goes and its comment says "for an editor".
It is not enough to be one, and the gap is silent rather than obvious:

* `width()`, `rail()` and `bank()` append **nothing**, so a document built from
  `sections` loses every width change and every barrier on the track;
* `crest()` records itself as an ordinary `straight` (it *is* one, with
  `ease=False`), so a jump and a hill are indistinguishable in it;
* gates live in `Builder.gates`, so `sections` does not say where a single
  checkpoint is.

`sections` is a **positional index for the closure solver** - it needs to name
"the third straight" and substitute a number into it, and for that the list is
exactly right. This module is the other thing: a complete, serialisable record
of what an author asked for, which can be stored, edited and replayed.

Sticky state becomes per-move state, on purpose
-----------------------------------------------
The turtle's `width`/`rail`/`bank` are modes: set one and it applies until
changed. That reads perfectly in a file, where the reader's eye travels in the
same direction the turtle does. It is a bug factory in a list you can reorder -
delete one move and nine later ones silently change width.

So a document stamps `w` and `rail` on **every move that lays road**, and
`replay` turns them back into `width()`/`rail()` calls, emitting one only when
the value actually changes. The two directions are symmetric, which is what
makes the round-trip test in `tests/test_moves.py` meaningful: it records a real
track, replays it, and asserts the ribbon is identical station for station.

What `record` is for besides that test
--------------------------------------
It is how **forking one of the nineteen** works. "Make my own" on Spa is
`record(spa.build, ...)` and hand the document to the editor. The test and the
feature are the same code path, which is the only reason to trust either.
"""

import hashlib
import math

from tracks.builder import FREE, Builder
from tuning import ROAD_W

# Bumped when the shape of a document changes in a way old rows cannot be read
# as. Stored on every row so a migration is possible at all; a document with no
# version is a document nobody can safely load.
SCHEMA_VERSION = 1

# The authored vocabulary, as data.
#
# `REQ` marks a field with no default; anything else is that field's default
# **taken from the Builder method's own signature**. The sentinel is not `None`
# because `None` is a real, meaningful default for three of these - an `arc`
# with no `bank`, a `gap` with no `bow`, a `loop` with no `shift` all pass it
# deliberately, and the method reads it as "work it out for me". Keeping them here rather than
# relying on Python's defaults is deliberate: `check` has to reject an unknown
# field and fill a missing one, and the editor has to know what to put in a
# slider, and neither can read a function signature usefully. `test_moves.py`
# asserts these match `Builder` by introspection, so the copy cannot drift.
class _Required:
    """Sentinel for a move field the author must supply. Never stored."""
    def __repr__(self):
        return "<required>"


REQ = _Required()

SPEC = {
    "start":           {"run": 14.0},
    "straight":        {"len": REQ, "rise": 0.0, "ease": True},
    "arc":             {"deg": REQ, "rad": REQ, "rise": 0.0, "ease": True,
                        "bank": None},
    "crest":           {"rise": REQ, "len": REQ},
    "hump":            {"rise": REQ, "len": REQ},
    "gap":             {"len": REQ, "drop": 0.0, "bow": None},
    "jump":            {"rise": REQ, "gap": REQ, "drop": 0.0, "kick": 8.0,
                        "land": 14.0},
    "loop":            {"rad": 20.0, "shift": None, "dir": "l"},
    "boost":           {"len": 12.0, "rise": 0.0, "ease": True},
    "bounce":          {"len": 14.0, "rise": 0.0, "ease": True},
    "pipe":            {"depth": 4.5, "floor": 0.34, "side": "lr"},
    "flat":            {},
    "cp":              {"pre": 17.0, "post": 17.0},
    "finish":          {"pre": 17.0, "post": 24.0},
    "finish_at_start": {},
}

# What each move is, in one line, and what each of its numbers does.
#
# Beside `SPEC` and not in a document, because both are read together by
# `_moves_spec` in app.py: the track maker hands this whole vocabulary to
# whatever model the author brought a key for, and no model has seen it. A
# vocabulary described in a file somewhere else is a vocabulary that will be
# described wrongly - the palette contract was moved into Python for the same
# reason, and the AI panel's whole job is making this API legible to something
# that has never met it.
#
# The units are the game's: one unit is about a metre, a station is 3.5 of them,
# and a road is 9 wide by default.
HELP = {
    "start": ("The start line. Every track begins with exactly one. `run` is "
              "how much straight road there is before the turtle is free, so a "
              "long run means a fast first corner."),
    "straight": ("Straight road. `rise` climbs (or falls, if negative) over its "
                 "length; `ease` true smooths both ends into a hill you can "
                 "carry speed over, false leaves a crease that launches you."),
    "arc": ("A corner. `deg` is how far it turns - negative is left, positive "
            "right - and `rad` is its radius, so a hairpin is a big `deg` with a "
            "small `rad`. Under about 12 nothing can drive it. `bank` tilts the "
            "road into the corner in degrees; `rise` climbs through it."),
    "crest": ("A sharp brow with no easing, which is what makes it launch you. "
              "`rise` over `len`. This is the deliberate version of the mistake "
              "`ease: false` makes by accident."),
    "hump": ("Up and then straight back down - one move, not two crests. `rise` "
             "is the height at the top, `len` the whole thing."),
    "gap": ("No road at all: a hole to clear. `len` is how wide, `drop` how much "
            "lower the far side is, `bow` an optional arc through the air. "
            "Whether it is clearable depends on the speed you arrive at."),
    "jump": ("A kicker, a hole and a landing, as one move. `rise` is the ramp, "
             "`gap` the hole, `drop` how far down the landing sits, `kick` how "
             "steep the ramp is and `land` how much flat road there is to catch "
             "you. A shallower kicker flies further."),
    "loop": ("A full vertical loop. `rad` under about 18 is undrivable at any "
             "speed - only gravity holds the car over the top. `dir` is which "
             "way it exits, `shift` how far sideways it moves you."),
    "boost": ("A pad. Worth about a second, and it belongs somewhere the speed "
              "is usable - out of a slow corner, into a jump - and never into a "
              "braking zone."),
    "bounce": ("A mushroom cap that throws you up. Widen the road over one: a "
               "12-wide disc at the end of a fifty-unit flight is a coin toss "
               "rather than a line."),
    "pipe": ("Turns the road into a half-pipe from here on - walls you can drive "
             "up. `depth` how deep, `floor` how much of the width stays flat, "
             "`side` which walls ('l', 'r' or 'lr'). Ended with `flat`."),
    "flat": "Ends a `pipe`: the road goes back to being flat.",
    "cp": ("A checkpoint, with its own run-up and run-off. One move, not a gate "
           "between two straights. Three or four round a lap is usual."),
    "finish": "The finish line, with road before and after it.",
    "finish_at_start": ("Finishes on the start line, which is what makes a "
                        "closed lap. The layout is then re-solved so the two "
                        "ends actually meet - see `free`."),
}
assert set(HELP) == set(SPEC), "HELP and SPEC disagree about the vocabulary"

# Moves that lay road, and therefore carry the width and barriers in force at
# the point they were authored. `pipe`, `flat` and `finish_at_start` change no
# geometry of their own and carry neither.
LAYS_ROAD = ("start", "straight", "arc", "crest", "hump", "gap", "jump", "loop",
             "boost", "bounce", "cp", "finish")

# Fields the closure solver may substitute into, and therefore the only ones a
# `FREE()` mark can sit on. See `Builder._tweak`: it is called with ("len",
# "rise") for a straight and ("deg", "rise") for an arc, and nothing else.
FREEABLE = ("len", "rise", "deg")


class MoveError(ValueError):
    """A document that cannot be replayed, with a message for its author."""


# -- recording ---------------------------------------------------------------
class Recorder:
    """The authored vocabulary, captured instead of executed.

    A stand-in for `Builder` that lays no road: it records the call and returns
    itself so chaining works. It can be a pure recorder rather than a wrapper
    because **nothing in `tracks/` reads the turtle's state** - no `track.py`
    touches `b.pos`, `b.yaw` or `b.hw`, and none branches on geometry - so there
    is nothing for a recorder to have to compute. If that ever stops being true
    the recorder will raise `AttributeError` naming the attribute, which is the
    loud failure this design wants rather than a quietly wrong document.

    It records at the level the author *wrote*: `hump` is one move, not the two
    crests it becomes, and `cp` is one move, not the two straights and a gate.
    """

    def __init__(self, width=ROAD_W, rails=False):
        self.moves = []
        # Sticky state, tracked so each road-laying move can be stamped with the
        # values in force when it was authored.
        self._w = float(width)
        self._rail = "lr" if rails else ""
        self._bank = 0.0

    # -- state, folded into the moves that follow it ----------------------
    def width(self, w):
        self._w = float(w)
        return self

    def rail(self, which):
        self._rail = _rail_str(which)
        return self

    def bank(self, degrees):
        self._bank = float(degrees)
        return self

    # -- the recording itself ---------------------------------------------
    def _put(self, t, **kw):
        """Record one move, dropping anything that equals its own default.

        Omitting defaults keeps a document readable and small, and it means a
        default changing in `Builder` changes every stored track with it -
        which is right for a number like `cp`'s run-up, whose whole purpose is
        to be the one good answer everywhere.
        """
        spec = SPEC[t]
        m = {"t": t}
        free = []
        for k, default in spec.items():
            v = kw.get(k, default)
            if isinstance(v, FREE):
                free.append(k)
                v = float(v)
            if v is REQ or (v is None and default is REQ):
                raise MoveError("%s needs %s" % (t, k))
            # A value equal to its own default is left out; `None` is only
            # dropped when `None` *is* the default, never when it stands in for
            # a field the author had to fill in.
            if default is not REQ and v == default:
                continue
            m[k] = _num(v) if isinstance(v, (int, float)) else v
        if free:
            m["free"] = free
        if t in LAYS_ROAD:
            m["w"] = _num(self._w)
            m["rail"] = self._rail
            if self._bank:
                m["bank_state"] = _num(self._bank)
        self.moves.append(m)
        return self

    def start(self, run=14.0):
        return self._put("start", run=run)

    def straight(self, length, rise=0.0, ease=True, w=None):
        if w is not None:
            self.rail(w)
        return self._put("straight", len=length, rise=rise, ease=ease)

    def arc(self, degrees, radius, rise=0.0, ease=True, w=None, bank=None):
        if w is not None:
            self.rail(w)
        return self._put("arc", deg=degrees, rad=radius, rise=rise, ease=ease,
                         bank=bank)

    def crest(self, rise, length, w=None):
        if w is not None:
            self.rail(w)
        return self._put("crest", rise=rise, len=length)

    def hump(self, rise, length, w=None):
        if w is not None:
            self.rail(w)
        return self._put("hump", rise=rise, len=length)

    def gap(self, length, drop=0.0, bow=None):
        return self._put("gap", len=length, drop=drop, bow=bow)

    def jump(self, rise, gap, drop=0.0, kick=8.0, land=14.0):
        return self._put("jump", rise=rise, gap=gap, drop=drop, kick=kick,
                         land=land)

    def loop(self, radius=20.0, shift=None, dir="l", w="lr"):
        # `w` defaults to "lr" on the real method, so a loop walls itself unless
        # the author says otherwise. Applying that here rather than leaving it
        # implicit is what keeps the replayed rail state in step afterwards.
        if w is not None:
            self.rail(w)
        return self._put("loop", rad=radius, shift=shift, dir=dir)

    def boost(self, length=12.0, rise=0.0, ease=True):
        return self._put("boost", len=length, rise=rise, ease=ease)

    def bounce(self, length=14.0, rise=0.0, ease=True):
        return self._put("bounce", len=length, rise=rise, ease=ease)

    def pipe(self, depth=4.5, floor=0.34, side="lr"):
        return self._put("pipe", depth=depth, floor=floor, side=side)

    def flat(self):
        return self._put("flat")

    def cp(self, pre=17.0, post=17.0):
        return self._put("cp", pre=pre, post=post)

    def finish(self, pre=17.0, post=24.0):
        return self._put("finish", pre=pre, post=post)

    def finish_at_start(self):
        return self._put("finish_at_start")


def record(build, *, name="Untitled", difficulty=3, width=ROAD_W, rails=False,
           ground=None, closed=False, exposed=False, origin=(0.0, 0.0, 0.0, 0.0),
           pal=None, scenery=None):
    """Run an authored `build(b)` against a `Recorder` and return a document.

    This is how a pool track becomes an editable document - the "make my own"
    button on Spa, and the round-trip test, are both this call.
    """
    r = Recorder(width=width, rails=rails)
    got = build(r)
    if got is not None and got is not r:
        raise MoveError("build() returned something that is not the builder")
    doc = {
        "v": SCHEMA_VERSION,
        "name": name,
        "difficulty": int(difficulty),
        "width": _num(width),
        "rails": bool(rails),
        "ground": None if ground is None else _num(ground),
        "closed": bool(closed),
        "exposed": bool(exposed),
        "origin": [_num(v) for v in origin],
        "moves": r.moves,
    }
    if pal:
        doc["pal"] = pal
    if scenery:
        doc["scenery"] = scenery
    return doc


# -- replaying ---------------------------------------------------------------
def replay(doc, b, spans=None):
    """Drive a real `Builder` from a document.

    Pass a list as `spans` and it is filled with `[first, last]` station indices
    per move. The editor needs it for two things and cannot work out either from
    the ribbon alone: which stretch of road to highlight when you select a move,
    and where to fly the camera. Optional because nothing else wants the cost of
    a list nobody reads.

    Sticky state is re-emitted only when it changes, which reproduces the
    author's original call sequence rather than a louder version of it. That
    matters for one non-obvious reason: `loop` sets `self.roll = 0` on its way
    out, so what the *next* move sees depends on whether a `bank()` call sat
    between them. Tracking what this function has set - rather than reading the
    builder back - keeps that faithful.
    """
    cur_w = _num(doc.get("width", ROAD_W))
    cur_rail = "lr" if doc.get("rails") else ""
    cur_bank = 0.0

    for i, raw in enumerate(doc.get("moves", ())):
        m = dict(raw)
        t = m.pop("t", None)
        if t not in SPEC:
            raise MoveError("move %d: %r is not a move. Known moves: %s"
                            % (i, t, ", ".join(sorted(SPEC))))
        free = m.pop("free", None) or []
        w = m.pop("w", None)
        rail = m.pop("rail", None)
        bank_state = m.pop("bank_state", 0.0)

        if t in LAYS_ROAD:
            # Width first: `rail` does not touch it and a barrier is drawn at
            # the edge of whatever width is in force.
            if w is not None and _num(w) != cur_w:
                b.width(float(w))
                cur_w = _num(w)
            if rail is not None and _rail_str(rail) != cur_rail:
                b.rail(_rail_str(rail))
                cur_rail = _rail_str(rail)
            if _num(bank_state) != cur_bank:
                b.bank(float(bank_state))
                cur_bank = _num(bank_state)

        args = {}
        for k, default in SPEC[t].items():
            v = m.pop(k, default)
            if v is REQ:
                raise MoveError("move %d (%s) is missing %s" % (i, t, k))
            if k in free and isinstance(v, (int, float)):
                v = FREE(v)
            args[k] = v
        if m:
            raise MoveError("move %d (%s) has %s, which nothing reads"
                            % (i, t, ", ".join(sorted(m))))
        first = len(b.nodes)
        _APPLY[t](b, args)
        if spans is not None:
            # `first` is the count *before* the move, so it is the index of its
            # own first new station. A move that lays no road at all (`flat`,
            # `pipe`, `finish_at_start`) gets an empty span rather than a wrong
            # one, and the editor shows it as a marker instead of a stretch.
            spans.append([first, max(first, len(b.nodes) - 1)]
                         if len(b.nodes) > first else [max(0, first - 1),
                                                      max(0, first - 1)])
    return b


# One adapter per move, so the mapping from document field to method argument is
# written down once. `len` and `dir` are the two names that cannot be keyword
# arguments as spelled, which is why this is a table and not `**args`.
_APPLY = {
    "start":    lambda b, a: b.start(run=a["run"]),
    "straight": lambda b, a: b.straight(a["len"], rise=a["rise"], ease=a["ease"]),
    "arc":      lambda b, a: b.arc(a["deg"], a["rad"], rise=a["rise"],
                                   ease=a["ease"], bank=a["bank"]),
    "crest":    lambda b, a: b.crest(a["rise"], a["len"]),
    "hump":     lambda b, a: b.hump(a["rise"], a["len"]),
    "gap":      lambda b, a: b.gap(a["len"], drop=a["drop"], bow=a["bow"]),
    "jump":     lambda b, a: b.jump(a["rise"], a["gap"], drop=a["drop"],
                                    kick=a["kick"], land=a["land"]),
    "loop":     lambda b, a: b.loop(radius=a["rad"], shift=a["shift"],
                                    dir=a["dir"], w=None),
    "boost":    lambda b, a: b.boost(length=a["len"], rise=a["rise"],
                                     ease=a["ease"]),
    "bounce":   lambda b, a: b.bounce(length=a["len"], rise=a["rise"],
                                      ease=a["ease"]),
    "pipe":     lambda b, a: b.pipe(depth=a["depth"], floor=a["floor"],
                                    side=a["side"]),
    "flat":     lambda b, a: b.flat(),
    "cp":       lambda b, a: b.cp(pre=a["pre"], post=a["post"]),
    "finish":   lambda b, a: b.finish(pre=a["pre"], post=a["post"]),
    "finish_at_start": lambda b, a: b.finish_at_start(),
}
# `loop` is passed `w=None` on purpose: the rail it wants was already applied
# above from the move's own stamp, and letting the method default to "lr" here
# would wall a loop whose author had turned barriers off.

assert set(_APPLY) == set(SPEC), "every move needs an adapter"


def builder_for(doc):
    """A fresh `Builder` positioned as the document says."""
    x, y, z, yaw = (list(doc.get("origin") or (0.0, 0.0, 0.0, 0.0)) + [0.0] * 4)[:4]
    return Builder(x, y, z, yaw=yaw, width=float(doc.get("width", ROAD_W)),
                   rails=bool(doc.get("rails")))


def build(doc, spans=None):
    """Document in, built ribbon out. The whole load path, in one call."""
    return replay(doc, builder_for(doc), spans=spans)


# -- helpers -----------------------------------------------------------------
def _num(v):
    """A float rounded to the precision a document stores.

    Six places, which is far finer than any number an author can see and coarse
    enough that a document round-trips through JSON as the same value it went in
    as. Without it, comparing two documents means comparing float repr.
    """
    f = float(v)
    if not math.isfinite(f):
        raise MoveError("%r is not a finite number" % (v,))
    r = round(f, 6)
    return int(r) if r == int(r) and abs(r) < 1e15 else r


def _rail_str(which):
    """Normalise a barrier spec to '', 'l', 'r' or 'lr'.

    The Builder accepts anything and tests it with `"l" in which`, so `rail(1)`
    would be a silent no-op there. Normalising here means a document only ever
    holds one spelling of each of the four states, which is what lets `replay`
    compare against what it last set.
    """
    if not which:
        return ""
    s = str(which)
    return ("l" if "l" in s else "") + ("r" if "r" in s else "")


# -- fingerprinting ----------------------------------------------------------
def fingerprint(built, scenery=None):
    """A hash of the road a lap was driven on.

    `tests/test_scenery.py` already says why this has to exist, in the message
    it fails with: *"the collider changed. Every time on this track's board was
    driven against the old one."* A board only means something against one road,
    so an edit that changes the road has to wipe it - and an edit that does not
    must leave it alone. A hash makes that a fact rather than a guess, and it
    means a no-op edit (drag a slider, drag it back) costs nobody their record.

    Taken over the **built ribbon** rather than the document, deliberately: two
    documents can differ in ways that produce the same road - a width restated,
    a default written out - and neither should cost anybody a lap time. It is
    the geometry that has to match, not the paperwork.

    `scenery` is whatever the document carries, in either of its two shapes: a
    **placement list** from the library, or the **baked geometry** a player's
    code produced under sandbox. Either way only the part the *car* can touch
    goes in - a wall changes where you can go and therefore what a lap time
    means, while a tower is decoration and moving one has not invalidated
    anybody's record. That split is what lets a mesh-only edit keep its board.
    """
    h = hashlib.sha1()
    h.update(b"drive-ribbon-1\n")
    for e in built.get("line", ()):
        h.update(repr(sorted(e.items())).encode())
    for g in built.get("gates", ()):
        h.update(repr(sorted(g.items())).encode())
    h.update(repr(built.get("spawn")).encode())
    for part in _solid_scenery(scenery):
        h.update(part)
    return h.hexdigest()


# The library models whose geometry reaches the collider, and therefore the only
# ones a lap time can feel. Mirrored from `static/js/scenery_kit.js`, where each
# one declares `collides: true`, and held in step by
# `tests/test_scenery_kit.py` - a model that gained a collider here and not
# there would be a wall that never wiped a board.
COLLIDING_MODELS = ("wall", "tecpro")


def _solid_scenery(scenery):
    """The parts of a scenery document a lap time depends on, as bytes.

    Two shapes arrive here and both are legitimate. A **list** is placements from
    the library; a **dict** is the baked geometry of somebody's code. Reading one
    as the other is how this went wrong the first time: `scenery.get(...)` on a
    list raises, which meant saving any track with a placement on it was a 500.
    """
    if not scenery:
        return
    if isinstance(scenery, dict):
        for quad in scenery.get("collider", ()):
            yield repr(quad).encode()
        return
    for p in scenery:
        if not isinstance(p, dict) or p.get("o") not in COLLIDING_MODELS:
            continue
        yield repr(sorted((k, v) for k, v in p.items()
                          if not isinstance(v, (dict, list)))).encode()


def look_fingerprint(doc):
    """A hash of everything you can *see*, which is a different question.

    The board rule and the review rule are not the same rule. A moved corner
    invalidates every time on the board, so it wipes it. A swapped-out city does
    not - lap times do not care - but it still has to come back to the queue,
    because what was approved was a particular city and a mesh-only edit could
    replace it with one that would not have been.

    So: everything visual, and nothing else. The palette is deliberately *out* -
    a colour is the one edit that saves straight onto a live track.
    """
    h = hashlib.sha1()
    h.update(b"drive-look-1\n")
    h.update(repr(doc.get("scenery")).encode())
    h.update(repr(doc.get("source") or "").encode())
    h.update(repr(doc.get("ground")).encode())
    return h.hexdigest()

def advise(doc):
    """What is wrong with a document, as things to say rather than exceptions.

    `replay` raises on a document it cannot build. This is the other half: a
    document that builds perfectly and describes a track nobody can drive. A
    corner of radius 4 is valid geometry and the builder is right to lay it -
    the reason it must not ship is that the car cannot get round it, which is a
    fact about the physics and not about the schema.

    Two levels, and they mean different things to a caller. A `refuse` is
    unplayable and the editor will not let a proposal carrying one be applied.
    A `note` is taste, and taste is only ever said - the same split
    `look.advise` uses for palettes, for the same reason.

    Returns [(level, index_or_None, text)]. The index is which move it is about,
    so the editor can put the message on that move rather than in a list.
    """
    from . import checks

    out = []
    ms = list(doc.get("moves") or ())
    if not ms:
        return [("refuse", None, "A track with no moves in it.")]

    starts = [i for i, m in enumerate(ms) if m.get("t") == "start"]
    ends = [i for i, m in enumerate(ms)
            if m.get("t") in ("finish", "finish_at_start")]
    if starts != [0]:
        out.append(("refuse", starts[0] if starts else None,
                    "A track needs exactly one `start` and it has to be first."))
    if len(ends) != 1 or ends[0] != len(ms) - 1:
        out.append(("refuse", ends[0] if ends else None,
                    "A track needs exactly one `finish` or `finish_at_start`, "
                    "and it has to be last."))

    def maybe(v):
        """A number, or None. `_num` raises, and advice never may: it describes
        documents that are half-written, which is most of them while somebody
        is still typing."""
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    for i, m in enumerate(ms):
        t = m.get("t")
        if t == "arc":
            rad = maybe(m.get("rad"))
            if rad is not None and abs(rad) < checks.MIN_RADIUS:
                out.append(("refuse", i,
                    "A %.4g-unit corner cannot be driven at all. Under about "
                    "%.4g the car cannot get round whatever else is right - "
                    "the first version of this game could only make one corner "
                    "shape and that was its radius."
                    % (abs(rad), checks.MIN_RADIUS)))
        elif t == "loop":
            rad = maybe(m.get("rad"))
            if rad is None:
                rad = SPEC["loop"]["rad"]
            if rad < checks.MIN_LOOP_RADIUS:
                out.append(("note", i,
                    "A loop under about %.4g is undrivable at racing speed "
                    "however good the geometry is - over the top there is "
                    "nothing holding the car on but gravity."
                    % checks.MIN_LOOP_RADIUS))

    radii = sorted({round(abs(maybe(m.get("rad")) or 0.0), 1)
                    for m in ms if m.get("t") == "arc" and m.get("rad")})
    if radii and len(radii) < checks.RADII_DISTINCT:
        out.append(("note", None,
            "Only %d different corner radi%s here (%s). A circuit that is worth "
            "learning uses at least %d - otherwise every corner is the same "
            "corner and there is nothing to remember."
            % (len(radii), "us" if len(radii) == 1 else "i",
               ", ".join("%g" % r for r in radii), checks.RADII_DISTINCT)))
    elif radii and radii[-1] / radii[0] <= checks.RADII_SPREAD:
        out.append(("note", None,
            "The corners are all much the same size (%g to %g). Somewhere "
            "between a hairpin and a long sweep is where a lap gets a shape."
            % (radii[0], radii[-1])))

    cps = sum(1 for m in ms if m.get("t") == "cp")
    if cps < checks.MIN_CHECKPOINTS:
        out.append(("note", None,
            "%s checkpoint%s. Three or four round a lap is usual - they are "
            "what stop a lap being driven by cutting the corners out."
            % (cps or "No", "" if cps == 1 else "s")))
    return out
