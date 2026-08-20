"""The five shapes a new track can start from.

Nobody's first minute in the editor should be spent in an empty field wondering
what a `rise` is. Each of these is a **real, short, drivable track with a
hand-tuned palette**, so the first thing a player can do is press Drive, and
every control in the editor is already demonstrated by something in the list.

They are documents rather than folders on purpose. A folder would put them in
the pool - on the home page, in the switcher, on the leaderboard - and a
starting shape is scaffolding, not a track anybody should be setting records on.
As documents they are also editable by Chinmay without a deploy.

**The palettes are borrowed from the pool, and that is the whole trick.** Each
starter names an existing track's `palette.py`, so a new track begins at the
standard the nineteen are held to instead of at `look.DEFAULT` - which the
palette contract itself describes as "deliberately unremarkable... a starting
point to be replaced, not a house style". A player who never opens the palette
editor still ends up with a good-looking track.

Nothing here may be *harder* than it looks. A starting shape that a beginner
cannot finish is a starting shape that teaches them the editor is broken, so
Sprint and Blank are flat, Circuit is wide and Stunt - the only one with real
consequences - has barriers everywhere.
"""

import importlib

from tracks import moves

# Which pool palette each shape borrows. Named rather than copied so that
# retuning a track's look retunes the starter that borrowed it, and so that this
# module holds no colours of its own to drift.
BORROWS = {
    "sprint": "sunrise",
    "circuit": "spa",
    "mountain": "heights",
    "stunt": "gauntlet",
    "blank": "sunrise",
}


def _pal(slug):
    try:
        return dict(importlib.import_module("tracks.%s.palette" % slug).PALETTE)
    except ModuleNotFoundError:                            # pragma: no cover
        return None


# -- the shapes --------------------------------------------------------------
def _sprint(b):
    """Point to point, flat, two corners you can see all the way through.

    The shortest thing that still reads as a track. Every corner is over 30
    radius, which is fast enough to take flat and forgiving enough to get wrong.
    """
    b.start(run=40)
    b.arc(-55, 42).straight(34)
    b.cp()
    b.arc(70, 34).straight(28)
    b.arc(-40, 48).straight(30)
    b.cp()
    b.arc(60, 38).straight(36)
    b.finish()


def _circuit(b):
    """A closed lap, and the arithmetic is exact rather than left to the solver.

    Four ninety-degree corners. Because the arcs of a rounded rectangle cancel
    exactly - each quarter turn displaces the turtle by one radius along the old
    heading and one along the new, and the four sum to nothing - closing it is
    just making opposite sides equal. So it closes to the *unit*: no position
    error, no heading error, no height error, and the solver reports nothing.

    That matters more than the shape does. The first thing a beginner does to a
    closed lap is drag a straight, and they should meet the solver working on a
    lap that was closed to begin with rather than one already 8% out.

    The sides are not the `straight()` numbers, which is where the first version
    of this went wrong: `start(run)` lays `14 + run` before the turtle is free,
    and every `cp()` lays `pre + post` of its own. Both are road on that side of
    the circuit and both have to be in the sum.
    """
    R = 46.0                      # corner radius, wide enough to take flat
    LONG, SHORT = 220.0, 124.0    # side lengths *including* gates and run-ups
    CP = 17.0 + 17.0              # what one `cp()` lays
    RUN = 60.0                    # the run to the start line
    side1 = 14.0 + RUN            # what `start` lays before the turtle is free
    b.rail("")
    b.start(run=RUN)
    b.arc(90, R)
    b.straight(SHORT - CP)
    b.cp()
    b.arc(90, R)
    b.straight(LONG - CP)
    b.cp()
    b.arc(90, R)
    b.straight(SHORT - CP)
    b.cp()
    b.arc(90, R)
    # Back onto the road `start` laid. LONG - side1, because side one and this
    # closing leg are the two halves of the same side of the circuit.
    b.straight(LONG - side1)
    b.finish_at_start()


def _mountain(b):
    """Up. Switchbacks, a crest near the top, and a run back down the far side.

    The shape that demonstrates `rise` - which is the one field nobody thinks to
    look for, because a flat track never needs it.
    """
    b.start(run=36)
    b.straight(48, rise=6.0)
    b.arc(-150, 17, rise=7.0)
    b.cp()
    b.straight(44, rise=8.0)
    b.arc(148, 18, rise=7.0)
    b.straight(40, rise=6.0)
    b.cp()
    b.arc(-64, 40, rise=4.0)
    b.hump(3.2, 30)
    b.straight(30, rise=-6.0)
    b.cp()
    b.arc(84, 34, rise=-9.0)
    b.straight(52, rise=-11.0)
    b.arc(-58, 44, rise=-6.0)
    b.straight(34)
    b.finish()


def _stunt(b):
    """The one with consequences, so it is the one with barriers everywhere.

    A loop, a pad into a jump, and a half-pipe - the three things a player is
    most likely to want and least likely to guess the numbers for. The loop is
    radius 20 because `Builder.loop` says so: coming over the top only gravity
    and `STICK_FORCE` hold the car on against v squared over R, and a radius-10
    loop is undrivable at racing speed however good the geometry is.
    """
    b.start(run=44)
    b.straight(30)
    b.loop(radius=20.0, dir="l")
    b.straight(26)
    b.cp()
    b.arc(-70, 30).straight(20)
    # A pad *into* the kicker: a pad is worth about a second of unarguable
    # speed, and out of a slow corner into a jump is where that second is both
    # usable and survivable.
    b.boost(14.0)
    b.jump(rise=2.6, gap=22, drop=5.0, land=34)
    b.cp()
    b.arc(150, 16).straight(24)
    b.width(16.0)
    b.pipe(depth=4.5, floor=0.34, side="lr")
    b.arc(-90, 40)
    b.flat()
    b.straight(24)
    b.width(12.0)
    b.cp()
    b.arc(66, 34).straight(32)
    b.finish()


def _blank(b):
    """A start line, a stub of road, a finish. Somewhere to begin.

    Not empty: a track with no road at all spawns the car into thin air, and
    `Builder.start` exists because that is exactly what the first version did.
    """
    b.start(run=40)
    b.straight(46)
    b.cp()
    b.straight(46)
    b.finish()


SHAPES = {
    "sprint": {
        "build": _sprint, "name": "Sprint", "difficulty": 1, "width": 12.0,
        "ground": -1.2,
        "about": "Point to point, flat, corners you can see through. "
                 "The shortest thing that still feels like a track.",
    },
    "circuit": {
        "build": _circuit, "name": "Circuit", "difficulty": 2, "width": 16.0,
        "ground": -1.2, "closed": True,
        "about": "A real lap: the finish line is the start line. Wide and fast, "
                 "and it closes on itself exactly.",
    },
    "mountain": {
        "build": _mountain, "name": "Mountain Climb", "difficulty": 3,
        "width": 11.0, "ground": -1.2,
        "about": "Switchbacks up, a crest at the top, a fast run down. "
                 "The shape that shows you what rise does.",
    },
    "stunt": {
        "build": _stunt, "name": "Stunt Park", "difficulty": 4, "width": 12.0,
        "ground": None, "rails": True, "exposed": True,
        "about": "A loop, a boost pad into a jump, and a half-pipe, floating in "
                 "the void. Leaving the road is a fall.",
    },
    "blank": {
        "build": _blank, "name": "Blank", "difficulty": 1, "width": 11.0,
        "ground": -1.2,
        "about": "A start line, a stub of road and a finish. Somewhere to begin.",
    },
}

ORDER = ("sprint", "circuit", "mountain", "stunt", "blank")


def document(shape):
    """One starting shape, as a document ready for the editor."""
    if shape not in SHAPES:
        raise KeyError("no starting shape %r. Known: %s"
                       % (shape, ", ".join(ORDER)))
    s = SHAPES[shape]
    doc = moves.record(
        s["build"],
        name=s["name"], difficulty=s["difficulty"], width=s["width"],
        rails=bool(s.get("rails")), ground=s.get("ground"),
        closed=bool(s.get("closed")), exposed=bool(s.get("exposed")),
        pal=_pal(BORROWS[shape]),
    )
    doc["from_shape"] = shape
    return doc


def _plan(shape, w=200.0, h=96.0, pad=10.0):
    """The shape's layout from above, as an SVG path, normalised into a box.

    On the summary rather than fetched per card: the pick screen shows all five,
    and five extra round trips to draw five thumbnails would be silly when the
    ribbon each is drawn from costs four milliseconds to build. Memoised at
    module scope below, so a page load costs nothing at all.

    The drawing itself is `tracks/plan.py`, which the community gallery uses
    too - the two want the identical picture, and a second implementation of
    "normalise a ribbon into a box" is a second chance to squash one.
    """
    import tracks as tracks_mod
    from . import plan as plan_mod
    line = tracks_mod.from_document(shape, document(shape), timed=False)["line"]
    return plan_mod.path_for(line, w=w, h=h, pad=pad)

_PLANS = {}


def summaries():
    """What the "start from" screen needs: no station lists, no palettes."""
    for k in ORDER:
        if k not in _PLANS:
            _PLANS[k] = _plan(k)
    return [{"shape": k, "name": SHAPES[k]["name"],
             "difficulty": SHAPES[k]["difficulty"],
             "about": SHAPES[k]["about"],
             "closed": bool(SHAPES[k].get("closed")),
             "void": SHAPES[k].get("ground") is None,
             "plan": _PLANS[k]}
            for k in ORDER]
