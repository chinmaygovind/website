"""The track pool, plus the block format the whole game is built on.

Format
------
A track is a list of **blocks** on a 3D grid. Every block is

    {"t": type, "p": [gx, gy, gz], "r": rot, "dy": levels, ...opts}

where ``p`` is the grid cell (``gy`` is a *float* elevation in LEVEL units, so
ramps do not need a special case), ``r`` is 0-3 quarter turns about Y, and ``dy``
is how much the surface climbs across the block. Rotation ``r`` maps the block's
local +X to world ``DIRS[r]``; local +Z is always the road's right-hand side.

The surface height at a block's entry edge is ``p.gy * LEVEL`` and at its exit
edge ``(p.gy + dy) * LEVEL``. That is the entire elevation model.

This dict-of-primitives shape is deliberately what a **track editor** would
produce, so adding one later means writing a UI that emits these blocks - no
change to the mesh builder, the physics or the server.

Authoring
---------
Nobody hand-writes block lists. ``Builder`` is a turtle that walks the grid
(``straight``, ``left``, ``ramp``, ``loop``, ``jump``, ...) and emits blocks as
it goes, which makes it impossible to author a disconnected track. It also
records the road **centreline** as it walks, and that polyline earns its keep
three times over: ``laptime.py`` relaxes it into a racing line to derive medal
times, the client turns distance-along-it into live race positions, and a
respawn uses it to face you back down the road.

Tracks are point-to-point like Polytrack's - a start block, ordered checkpoints,
a finish block - not laps.
"""

import math

from tuning import CELL, LEVEL

# Grid headings. Index into DIRS; right of heading h is (h+1)%4, left is (h+3)%4.
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
EAST, SOUTH, WEST, NORTH = 0, 1, 2, 3


def _world(gx, gy, gz):
    return [gx * CELL, gy * LEVEL, gz * CELL]


class Builder:
    """Turtle that walks the grid laying road and recording the centreline."""

    def __init__(self, gx=0, gz=0, gy=0.0, h=EAST, rails=False):
        # `rails` puts guard rails along both sides of every straight and ramp by
        # default. Tracks that float in the void get them: without a ground plane
        # to catch a wide moment, a single-cell-wide corner exit at 40 u/s is a
        # fall and a respawn, over and over. Tracks sitting on the ground do not -
        # running wide there costs time on the grass, which is the better penalty.
        # Jumps are unaffected either way: a gap has no road to put a rail on.
        self.rails = rails
        self.gx, self.gz, self.y, self.h = gx, gz, float(gy), h
        self.blocks = []
        self.line = []          # centreline: {"p":[x,y,z], "lat":[x,y,z], "hw":half width, "air":bool}
        self.n_cp = 0
        self.spawn = None
        self.finish = None
        self._pending_gate = None

    # -- internals ---------------------------------------------------------
    def _advance(self, n=1):
        dx, dz = DIRS[self.h]
        self.gx += dx * n
        self.gz += dz * n

    def _fwd_vec(self):
        dx, dz = DIRS[self.h]
        return (float(dx), 0.0, float(dz))

    def _lat_vec(self):
        """Road right-hand direction for the current heading."""
        dx, dz = DIRS[(self.h + 1) % 4]
        return [float(dx), 0.0, float(dz)]

    def _add(self, t, **opts):
        b = {"t": t, "p": [self.gx, round(self.y, 4), self.gz], "r": self.h}
        if self._pending_gate:
            b["gate"] = self._pending_gate
            if self._pending_gate == "cp":
                self.n_cp += 1
                b["gi"] = self.n_cp
            self._pending_gate = None
        b.update({k: v for k, v in opts.items() if v is not None})
        self.blocks.append(b)
        return b

    def _walls(self, w):
        """Explicit walls win; otherwise fall back to the track's rails setting."""
        if w is not None:
            return w
        return "lr" if self.rails else None

    def _mark_line(self, pt, lat, hw=CELL / 2, air=False, boost=False, loop=False):
        e = {"p": [round(v, 3) for v in pt], "lat": lat, "hw": hw}
        if air:
            e["air"] = True
        if boost:
            e["boost"] = True
        if loop:
            e["loop"] = True
        self.line.append(e)

    # -- gates -------------------------------------------------------------
    def gate(self, kind):
        """Tag the next placed block as start / cp / finish."""
        self._pending_gate = kind
        return self

    def start(self):
        self.gate("start")
        fx, _, fz = self._fwd_vec()
        self.spawn = {"p": _world(self.gx, self.y, self.gz), "fwd": [fx, 0.0, fz]}
        return self.straight(1)

    def cp(self, n=1):
        self.gate("cp")
        return self.straight(n)

    def finish_line(self):
        self.gate("finish")
        self.finish = {"p": _world(self.gx, self.y, self.gz)}
        return self.straight(1)

    # -- road --------------------------------------------------------------
    def straight(self, n=1, w=None, boost=False):
        """``boost`` puts a single pad on the *first* cell, not on all of them.

        A pad snaps you to BOOST_SPEED, so paving a whole straight with them
        pins the car at full boost right up to the corner at the end of it, which
        is unrecoverable. One pad gives the burst and leaves the rest of the
        straight to spend it.
        """
        w = self._walls(w)
        for i in range(n):
            pad = boost and i == 0
            self._add("road", w=w, boost=(True if pad else None))
            self._mark_line(_world(self.gx, self.y, self.gz), self._lat_vec(), boost=pad)
            self._advance()
        return self

    def ramp(self, rise, length=None, w=None):
        """Climb (or drop, if rise<0) ``rise`` levels over ``length`` cells."""
        length = length or max(1, int(round(abs(rise))))
        w = self._walls(w)
        step = rise / length
        for _ in range(length):
            self._add("road", dy=round(step, 4), w=w)
            # the line sits at the middle of the sloped cell
            p = _world(self.gx, self.y + step / 2, self.gz)
            self._mark_line(p, self._lat_vec())
            self.y += step
            self._advance()
        return self

    def turn(self, d, w="o"):
        """A 90 degree corner filling one cell: a quarter disc pivoted on the
        inside corner, so the entry and exit edges are fully road and the far
        corner is off the track."""
        self._add("turn", d=d, w=w)
        # Sample the arc so the racing-line relaxation has something to bend.
        fx, _, fz = self._fwd_vec()
        rx, _, rz = self._lat_vec()
        side = 1.0 if d == "r" else -1.0
        cx, cy, cz = _world(self.gx, self.y, self.gz)
        # Pivot corner: back along forward, and to the inside.
        px = cx - fx * CELL / 2 + rx * side * CELL / 2
        pz = cz - fz * CELL / 2 + rz * side * CELL / 2
        # Sweep the arc around the pivot at half the road width. From the pivot,
        # the entry edge runs along -side*right and the exit edge along +forward,
        # so the arc between them is a blend of those two directions. Getting this
        # wrong put the samples a whole cell outside the corner tile.
        r = CELL / 2
        ex, ez = -rx * side, -rz * side          # entry-edge direction from pivot
        for k in range(1, 4):
            a = (math.pi / 2) * (k / 4.0)
            sx = px + (ex * math.cos(a) + fx * math.sin(a)) * r
            sz = pz + (ez * math.cos(a) + fz * math.sin(a)) * r
            # tangent along the arc, and the road's right-hand side (tangent x up)
            tx = fx * math.cos(a) + rx * side * math.sin(a)
            tz = fz * math.cos(a) + rz * side * math.sin(a)
            self._mark_line([sx, cy, sz], [-tz, 0.0, tx])
        self.h = (self.h + (1 if d == "r" else 3)) % 4
        self._advance()
        return self

    def left(self, w="o"):
        return self.turn("l", w)

    def right(self, w="o"):
        return self.turn("r", w)

    def hairpin(self, d, w="o"):
        """Two corners back to back with one cell between - the slowest thing
        on any track, and where the lap sim's braking pass earns its money."""
        self.turn(d, w)
        self.straight(1, w="lr")
        self.turn(d, w)
        return self

    def chicane(self, first="l"):
        other = "r" if first == "l" else "l"
        self.turn(first)
        self.turn(other)
        return self

    # -- features ----------------------------------------------------------
    def loop(self, rad=11.0, length=None):
        """A vertical loop that returns to the same height further along.

        ``length`` (in cells) is how far down the track the loop travels while it
        goes round, and it is **not** a free choice: the loop's path is
        ``x(t) = advance*t/2pi + rad*sin(t)``, so if advance is much smaller than
        ``pi*rad`` the climbing and descending halves pass within a couple of
        units of each other near the bottom. A car coming down the back of the
        loop then finds the *ascending* surface inside its ground probe, snaps
        onto it and gets carried round again forever - which is exactly what
        happened before this was derived rather than hand-picked. Defaulting to
        ``ceil(pi*rad/CELL)`` keeps the two halves comfortably apart.
        """
        if length is None:
            length = int(math.ceil(math.pi * rad / CELL))
        self._add("loop", length=length, rad=rad)
        fx, fy, fz = self._fwd_vec()
        lat = self._lat_vec()
        ox, oy, oz = _world(self.gx - DIRS[self.h][0] * 0.5, self.y, self.gz - DIRS[self.h][1] * 0.5)
        adv = length * CELL
        for k in range(1, 13):
            a = 2 * math.pi * k / 12.0
            s = adv * a / (2 * math.pi)
            px = ox + fx * (s + rad * math.sin(a))
            py = oy + rad * (1 - math.cos(a))
            pz = oz + fz * (s + rad * math.sin(a))
            self._mark_line([px, py, pz], lat, loop=True)
        self._advance(length)
        return self

    def jump(self, rise=1.0, gap=3, land=0.0):
        """A kicker, a hole, and a landing. ``rise`` levels of ramp over one
        cell launches you; ``gap`` cells have no road at all; the landing sits
        ``land`` levels below the lip."""
        self._add("kick", dy=round(rise, 4))
        p = _world(self.gx, self.y + rise / 2, self.gz)
        self._mark_line(p, self._lat_vec())
        self.y += rise
        self._advance()
        lip_y = self.y
        for i in range(gap):
            # Airborne segments: no block, and the lap sim holds speed here.
            arc = math.sin(math.pi * (i + 0.5) / gap) * rise * 0.8
            self._mark_line(_world(self.gx, lip_y + arc, self.gz), self._lat_vec(), air=True)
            self._advance()
        self.y = lip_y - land
        return self

    def bridge_over(self, n=1, w="lr"):
        """Plain road, but flagged so the mesh builder puts piers under it and
        the client knows two blocks legitimately share a cell."""
        for _ in range(n):
            self._add("road", w=w, over=True)
            self._mark_line(_world(self.gx, self.y, self.gz), self._lat_vec())
            self._advance()
        return self

    # -- output ------------------------------------------------------------
    def build(self):
        return {"blocks": self.blocks, "line": self.line, "spawn": self.spawn,
                "checkpoints": self.n_cp}


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------
# Each entry: slug, display name, one-line blurb, a palette key, `ground`
# (elevation of the solid ground plane, or None for a track floating in the
# void where leaving the road means falling), and the builder that lays it out.

# Authoring notes, learned the hard way from the headless driving tests:
#
#  * Leave at least two cells of flat road after a ramp, a loop or a jump landing
#    before the next corner. A car arriving at a 90-degree tile still carrying
#    vertical speed will not make the corner, and on a floating track that means
#    falling off rather than merely running wide.
#  * Never lay a track back across itself at the same height - `overlaps()` fails
#    the tests if you do. A real crossing needs a `bridge_over` at 2.5+ levels,
#    and the crossing block must be flat, not part of the ramp.
#  * Corners are one cell wide, so the line through them is what opens them up.
#    Two corners with a single cell between them (a hairpin) is the slowest thing
#    a car can do here; use it on purpose, sparingly.
#  * Put checkpoints in the middle of a straight, never in the cell before a
#    corner. The racing line through a corner cuts the inside, so a gate placed
#    right before one gets clipped at the edge of its mouth or missed entirely -
#    which is how four tracks ended up unfinishable. `test_tracks.py` enforces
#    two cells of straight on each side of every gate.

def _sunrise():
    """Easy, wide open, on the ground. The track to learn the car on."""
    b = Builder(0, 0, h=EAST)
    b.start().straight(8)
    b.right().straight(3).cp().straight(3)
    b.right().straight(6, boost=True).cp().straight(3)
    b.right().straight(5)
    b.left().straight(4)
    b.left().straight(4).cp().straight(3)
    b.right().straight(7, boost=True)
    b.straight(2)
    b.finish_line().straight(3)
    return b


def _chicane_park():
    """Quick direction changes, one deliberate hairpin, all on the ground."""
    b = Builder(0, 0, h=EAST)
    b.start().straight(6)
    b.chicane("r").straight(3).cp().straight(4)
    b.right().straight(6, boost=True).cp().straight(3)
    b.chicane("l").straight(7)
    b.right().straight(3).cp().straight(3)
    b.hairpin("r")
    b.straight(5)
    b.left().straight(6)
    b.finish_line().straight(3)
    return b


def _skyline():
    """Elevation over a floating track - run wide and you fall."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(4)
    b.ramp(2, 3).straight(2).cp().straight(3)
    b.right().straight(4)
    b.ramp(1.5, 2).straight(2, boost=True).cp().straight(3)
    b.right().straight(4)
    b.ramp(-2, 3).straight(3)
    b.right().straight(3).cp().straight(3)
    b.ramp(2.5, 4).straight(3)
    b.left().straight(4)
    b.ramp(-4, 4).straight(2).cp().straight(3)
    b.left().straight(5, boost=True)
    b.straight(2)
    b.finish_line().straight(3)
    return b


def _loop_lagoon():
    """Two full loops. Carry speed in or you will not make it round."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(5, boost=True)
    b.loop(10.0).straight(3).cp().straight(3)
    b.right().straight(5)
    b.right().straight(4, boost=True).cp().straight(3)
    b.loop(11.0).straight(4)
    b.left().straight(3).cp().straight(3)
    b.left().straight(4)
    b.right().straight(6)
    b.finish_line().straight(3)
    return b


def _hairpin_heights():
    """A climb built out of hairpins, then a fast plunge back down."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(5)
    b.ramp(3, 4).straight(2).cp().straight(3)
    b.hairpin("r")
    b.straight(3).ramp(3, 4).straight(2).cp().straight(3)
    b.hairpin("l")
    b.straight(3).ramp(2.5, 3).straight(2).cp().straight(3)
    b.right().straight(5)
    b.ramp(-5, 4).straight(3)
    b.left().straight(4, boost=True).cp().straight(3)
    b.ramp(-3.5, 3).straight(3)
    b.left().straight(4)
    b.finish_line().straight(3)
    return b


def _jump_city():
    """Four gaps with nothing under them. Boost, launch, land, repeat."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(5, boost=True)
    b.jump(1.0, 3, 0.0).straight(3).cp().straight(3)
    b.right().straight(4)
    b.straight(3, boost=True)
    b.jump(1.5, 4, 1.5).straight(3).cp().straight(3)
    b.right().straight(4)
    b.ramp(2, 2).straight(3, boost=True)
    b.jump(1.0, 4, 3.0).straight(3).cp().straight(3)
    b.right().straight(5)
    b.straight(3, boost=True)
    b.jump(1.5, 4, 1.5).straight(3).cp().straight(3)
    b.left().straight(5)
    b.finish_line().straight(3)
    return b


def _spiral():
    """A tight climbing spiral, then a dive back down the outside."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(6, boost=True)
    b.ramp(1.5, 2).straight(2)
    b.right().straight(6)
    b.ramp(1.5, 2).straight(2).cp().straight(3)
    b.right().straight(5)
    b.ramp(1.5, 2).straight(2)
    b.right().straight(6)
    b.ramp(1.5, 2).straight(2).cp().straight(3)
    b.right().straight(7, boost=True)
    b.ramp(-3, 3).straight(3)
    b.left().straight(3).cp().straight(3)
    b.ramp(-3, 3).straight(3)
    b.left().straight(4, boost=True)
    b.straight(2).cp().straight(3)
    b.right().straight(7)
    b.finish_line().straight(3)
    return b


def _figure_eight():
    """Short, and it really does cross over itself on a bridge."""
    b = Builder(0, 0, h=EAST)
    b.start().straight(4)
    b.right().straight(4)
    b.ramp(3, 3).straight(2).cp().straight(2)
    b.right().straight(4)
    b.bridge_over(3)
    b.straight(2).cp().straight(2)
    b.ramp(-3, 3).straight(3)
    b.right().straight(5, boost=True)
    b.right().straight(4).cp().straight(3)
    b.left().straight(5)
    b.finish_line().straight(3)
    return b


def _gauntlet():
    """Loops, gaps, hairpins, elevation. Everything, and twice as long."""
    b = Builder(0, 0, h=EAST, rails=True)
    b.start().straight(5, boost=True)
    b.loop(10.0).straight(3).cp().straight(3)
    b.right().ramp(2.5, 3).straight(3)
    b.chicane("l").straight(3, boost=True).cp().straight(3)
    b.jump(1.5, 4, 2.5).straight(3)
    b.right().straight(3).cp().straight(3)
    b.hairpin("r")
    b.straight(3).ramp(-3, 3).straight(4, boost=True).cp().straight(3)
    b.loop(11.0).straight(4)
    b.right().ramp(2, 2).straight(3).cp().straight(3)
    b.jump(1.0, 3, 2.0).straight(4)
    b.right().straight(5, boost=True)
    b.straight(3).cp().straight(3)
    b.hairpin("l")
    b.straight(4).ramp(-3.5, 3).straight(4)
    b.left().straight(5)
    b.finish_line().straight(3)
    return b


_POOL = [
    ("sunrise", "Sunrise Circuit", "Wide, flowing and forgiving - the one to learn the car on.",
     "sunrise", 0.0, 1, _sunrise),
    ("chicane", "Chicane Park", "Quick direction changes and one very slow hairpin.",
     "park", 0.0, 2, _chicane_park),
    ("skyline", "Skyline Sprint", "Up and over a floating skyline. Miss a corner and you fall.",
     "skyline", None, 3, _skyline),
    ("lagoon", "Loop Lagoon", "Two full loops. Carry speed in or you will not make it round.",
     "lagoon", 0.0, 3, _loop_lagoon),
    ("heights", "Hairpin Heights", "A climb made of hairpins, then a fast plunge back down.",
     "heights", None, 4, _hairpin_heights),
    ("jumpcity", "Jump City", "Four gaps with nothing under them. Boost, launch, land, repeat.",
     "city", None, 4, _jump_city),
    ("spiral", "Spiral Ascent", "A tight spiral to the top and a dive down the outside.",
     "spiral", None, 5, _spiral),
    ("eight", "Figure Eight", "Short, and it crosses over itself on a bridge.",
     "park", 0.0, 2, _figure_eight),
    ("gauntlet", "The Gauntlet", "Loops, gaps, hairpins, elevation. Everything, twice as long.",
     "gauntlet", None, 5, _gauntlet),
]


def _assemble():
    out = []
    for slug, name, blurb, palette, ground, difficulty, fn in _POOL:
        built = fn().build()
        t = {"slug": slug, "name": name, "blurb": blurb, "palette": palette,
             "ground": ground, "difficulty": difficulty,
             "cell": CELL, "level": LEVEL}
        t.update(built)
        out.append(t)
    return out


TRACKS = _assemble()
BY_SLUG = {t["slug"]: t for t in TRACKS}

# Medal times need the lap simulation, which needs the assembled centrelines -
# hence the import down here rather than at the top.
import laptime  # noqa: E402

for _t in TRACKS:
    _t["ideal"] = laptime.ideal_lap(_t)
    _t["medals"] = laptime.medals(_t["ideal"])


def overlaps(track, min_gap=1.6):
    """Cells where two blocks sit on top of each other closer than ``min_gap``
    levels apart.

    A turtle makes it easy to lay a track back across itself by accident, and two
    road surfaces a metre apart in the same cell is not a bridge - it is a car
    trap, and the ground query has no good answer for it. A genuine crossing is
    marked ``over`` and needs real clearance, which this also checks. Used by the
    tests, so no track can regress into overlapping itself unnoticed.
    """
    seen = {}
    bad = []
    for b in track["blocks"]:
        if b["t"] == "loop":
            continue          # a loop legitimately passes over its own cells
        key = (b["p"][0], b["p"][2])
        for other in seen.get(key, []):
            gap = abs(other["p"][1] - b["p"][1])
            if gap < min_gap:
                bad.append({"cell": key, "gap": round(gap, 2),
                            "a": other["t"], "b": b["t"]})
        seen.setdefault(key, []).append(b)
    return bad


def summaries():
    """Everything the track-select screen needs, without the block lists."""
    return [{k: t[k] for k in ("slug", "name", "blurb", "difficulty", "ideal",
                               "medals", "checkpoints")} for t in TRACKS]


def get(slug):
    return BY_SLUG.get(slug)
