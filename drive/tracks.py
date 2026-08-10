"""The track pool, and the ribbon format the whole game is built on.

Format
------
A track is a **ribbon**: an ordered list of stations along the road, roughly
``STATION`` units apart. Every station is

    {"p": [x,y,z], "n": [nx,ny,nz], "lat": [lx,ly,lz], "hw": half_width, ...opts}

``p`` is the centre of the road, ``n`` is the surface normal pointing up out of
the tarmac, ``lat`` is the road's right-hand direction, and ``hw`` is how far the
tarmac reaches either side. The forward direction is ``n x lat``, so it does not
need storing. Optional flags: ``air`` (a gap - no road here), ``wl`` / ``wr``
(barrier on the left / right edge), ``fix`` (the racing line may not be moved
here), ``curv`` (1/radius of the corner), ``crad`` (radius of a loop),
``kick`` (a deliberate crease that launches the car).

Everything downstream is one code path over that list: the mesh is a strip of
quads between consecutive stations, the collision soup is the same quads, the
racing line is the same points relaxed sideways, and race position is distance
along it. There are no block types, no grid, and no per-shape special cases -
which is exactly why corners can be any radius, roads can change width, and a
loop is not a special case but a station list whose normal rotates.

Why a ribbon and not a grid of tiles
------------------------------------
The first version of this snapped 90-degree corner tiles to an 8-unit grid. That
makes every corner the same corner, every corner radius exactly one cell (a
4-unit-radius hairpin no car can hold, so the *only* way through was to cut the
tile diagonally), and it makes a smooth elevation change impossible - a ramp was
a crease between two flat tiles. A ribbon has none of those problems and is
simpler.

Authoring
---------
Nobody hand-writes station lists. ``Builder`` is a turtle in continuous space:
``straight``, ``arc``, ``crest``, ``gap``, ``loop``, ``width``, ``rail``.
Heading, height and bank are floats, so a corner is ``arc(-70, 34)`` - seventy
degrees left at a thirty-four unit radius - and it joins whatever came before it
exactly.

Tracks are point-to-point like Polytrack's: a start, ordered checkpoints, a
finish. Not laps.
"""

import math

from tuning import CELL, LEVEL, ROAD_W

# Station spacing along the road. Small enough that a 20-unit-radius corner is
# smooth (3.5 units of arc is a 10 degree step) and that the collision surface
# has no visible facets; large enough that a 1000-unit track is ~290 stations,
# which is a few thousand triangles and a JSON payload measured in tens of KB.
STATION = 3.5

# A road surface may not come within this of another part of the track unless it
# is a deliberate crossing, in which case it must clear it by CROSS_CLEAR.
CROSS_CLEAR = 5.0

# How much of the road's heading has to have gone one way before that counts as
# the first corner - see `pole_side`. Small enough to catch a gentle opening
# sweep, large enough that a station's worth of noise is not a corner.
FIRST_TURN_DEG = 25.0

# Bounds on the checkpoint window's roof - see `gate_ceiling`. The margin is
# what keeps the window clear of a road passing overhead: a car on the upper
# level sits at the crossing clearance above the gate, so the roof stays that
# far below it.
GATE_CEIL_MAX = 14.0
GATE_CEIL_MIN = 5.0
GATE_CEIL_MARGIN = 4.0

# Lateral profile
# ---------------
# A station is normally a flat strip, and the road is the quad between one
# station's two edges and the next one's. A *profiled* station carries ``pf``:
# samples ``[u, rise]`` across the road, ``u`` running -1 to +1 as a fraction of
# ``hw`` and ``rise`` measured along that station's own normal. The road there
# is the ``len(pf)-1`` quads between one station's samples and the next one's.
#
# That is the whole change. It is still quads and still one loop, so the
# collision soup, the mesh and the car all work inside a half-pipe without
# knowing they are in one - for exactly the reason a loop needs no special case,
# which is that steering is applied about the surface normal rather than world
# up. Riding up a pipe wall is the same code as driving round the inside of a
# loop.
#
# The samples are baked here rather than written as a formula the JS
# re-evaluates. Everything else in a station is baked too, and a second copy of
# the cross-section is a second thing that can drift out of step with this one.
PROF_SAMPLES = 9

# How far a profile takes to reach full depth. A pipe that starts at its full
# height in one station is a wall you hit rather than a wall you ride, so the
# depth is smoothstepped in and out over this distance at each end.
PROF_BLEND = 14.0


def _profile(depth, floor, side, samples=PROF_SAMPLES):
    """Cross-section samples for a trough ``depth`` deep with a flat floor.

    ``floor`` is the fraction of the half-width that stays flat; outside it the
    surface curves up to ``depth`` at the lip. The curve is ``1 - cos``, which
    leaves the floor tangentially and steepens toward the top - the shape of a
    real half-pipe wall, and more to the point a shape with no crease at the
    bottom to unsettle a car dropping back in.

    ``side`` is ``'lr'``, ``'l'`` or ``'r'``: a one-sided wall is how a fast
    corner gets a bank you can take a high line on.
    """
    out = []
    for i in range(samples):
        u = -1.0 + 2.0 * i / (samples - 1)
        a = abs(u)
        wants = side == "lr" or (side == "l" and u < 0) or (side == "r" and u > 0)
        rise = 0.0
        if wants and a > floor:
            t = (a - floor) / (1.0 - floor)
            rise = depth * (1.0 - math.cos(t * math.pi / 2.0))
        out.append([round(u, 4), round(rise, 3)])
    return out


def rise_at(e, u):
    """Height of the surface above a station's floor plane at lateral ``u``.

    Reads the station's baked samples rather than re-deriving the curve, so the
    lap-time model, the tests and the mesh all measure the same road.
    """
    pf = e.get("pf")
    if not pf:
        return 0.0
    u = max(-1.0, min(1.0, u))
    for i in range(len(pf) - 1):
        u0, r0 = pf[i]
        u1, r1 = pf[i + 1]
        if u <= u1:
            t = 0.0 if u1 <= u0 else (u - u0) / (u1 - u0)
            return r0 + (r1 - r0) * t
    return pf[-1][1]


def surface_at(e, u):
    """The 3D point on a station's surface at lateral ``u`` (-1..+1)."""
    r = rise_at(e, u)
    return [e["p"][k] + e["lat"][k] * u * e["hw"] + e["n"][k] * r for k in range(3)]


def _norm(v):
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if m < 1e-12:
        return [0.0, 1.0, 0.0]
    return [v[0] / m, v[1] / m, v[2] / m]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _frame(yaw, pitch, roll):
    """Road axes for a heading, a grade and a bank.

    Returns (forward, right, up). ``yaw`` 0 points along +X; ``right`` is
    ``forward x up`` and stays horizontal until ``roll`` tilts it, which is the
    same right-handed triple the car uses (see physics.js).
    """
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    f = [cy * cp, sp, sy * cp]
    r = [-sy, 0.0, cy]
    u = [-cy * sp, cp, -sy * sp]
    if roll:
        cr, sr = math.cos(roll), math.sin(roll)
        # rotate r and u about f: f x r == -u, so this is the standard rotation
        r, u = ([r[i] * cr - u[i] * sr for i in range(3)],
                [u[i] * cr + r[i] * sr for i in range(3)])
    return f, r, u


def _smooth(u):
    """Smoothstep. Used for elevation, so a hill has no crease at either end."""
    return u * u * (3.0 - 2.0 * u)


class Builder:
    """A turtle in continuous space that lays a ribbon of road behind it."""

    def __init__(self, x=0.0, y=0.0, z=0.0, yaw=0.0, width=ROAD_W, rails=False):
        # `rails` is the *default* for sections that do not say otherwise. Tracks
        # floating in the void want it on: without a ground plane to catch a wide
        # moment, running out of road is a fall and a respawn. Tracks on the
        # ground want it off - running wide there costs you time on the grass,
        # which is the better penalty, and a barrier on every corner both looks
        # like a bobsleigh run and removes the only interesting decision on the
        # exit of a corner.
        self.x, self.y, self.z = float(x), float(y), float(z)
        self.yaw = math.radians(yaw)
        self.hw = width / 2.0
        self.roll = 0.0
        self.rails = rails
        self.wl = rails
        self.wr = rails
        self.nodes = []
        self.gates = []
        self.spawn = None
        self.n_cp = 0
        self.sections = []      # authored primitives, in order - for an editor
        # Cross-section. `prof` is what we are heading toward (None = flat) and
        # `_pb` is how far into the blend we are, so a pipe rises out of the
        # road over PROF_BLEND units and sinks back into it the same way.
        self.prof = None
        self.prof_last = None
        self._pb = 0.0
        # Whether the stations being laid are boost pads. `boost` turns it on
        # for a measured length and back off again, so unlike the cross-section
        # it is never a mode you can leave running by accident.
        self._pad = False

    # -- internals ---------------------------------------------------------
    def _pf(self):
        """The cross-section for the station about to be laid, part-blended.

        Called once per station, so the blend advances with the road rather than
        with the number of primitives - a pipe opened mid-corner ramps in over
        the same distance as one opened on a straight.
        """
        step = STATION / PROF_BLEND
        if self.prof:
            self._pb = min(1.0, self._pb + step)
            shape = self.prof
        else:
            self._pb = max(0.0, self._pb - step)
            shape = self.prof_last      # still shrinking the last one away
        if not shape or self._pb <= 1e-3:
            return None
        depth, floor, side = shape
        return _profile(depth * _smooth(self._pb), floor, side)

    def _emit(self, p, n, lat, hw=None, air=False, fix=False, curv=0.0,
              wl=None, wr=None, kick=False):
        e = {"p": [round(v, 2) for v in p],
             "n": [round(v, 4) for v in n],
             "lat": [round(v, 4) for v in lat],
             "hw": round(hw if hw is not None else self.hw, 2)}
        pf = self._pf()
        # A gap has no surface, so it has no cross-section either.
        if pf and not air:
            e["pf"] = pf
        if air:
            e["air"] = 1
        # A boost pad is a property of the surface, not a thing standing on it -
        # see `boost` below.
        if self._pad and not air:
            e["bp"] = 1
        if fix:
            e["fix"] = 1
        if kick:
            e["kick"] = 1
        if curv:
            e["curv"] = round(curv, 5)
        if (self.wl if wl is None else wl) and not air:
            e["wl"] = 1
        if (self.wr if wr is None else wr) and not air:
            e["wr"] = 1
        self.nodes.append(e)
        return e

    def _steps(self, length):
        """How many stations to spend on ``length`` units of road."""
        return max(1, int(round(abs(length) / STATION)))

    def _height(self, rise, u, length, ease):
        """(height offset, grade) a fraction ``u`` through a rising section."""
        if not rise:
            return 0.0, 0.0
        if ease:
            # smoothstep: grade is zero at both ends, so a hill joins the flat
            # road before and after it without a crease - and therefore without
            # launching the car. Deliberate launches are `crest` and `gap`.
            return rise * _smooth(u), rise * 6.0 * u * (1.0 - u) / length
        return rise * u, rise / length

    # -- state -------------------------------------------------------------
    def width(self, w):
        """Set the road width from here on."""
        self.hw = w / 2.0
        return self

    def rail(self, which):
        """``'lr'``, ``'l'``, ``'r'`` or ``''`` - barriers from here on."""
        which = which or ""
        self.wl = "l" in which
        self.wr = "r" in which
        return self

    def bank(self, degrees):
        """Roll the road. Positive raises the right-hand edge."""
        self.roll = math.radians(degrees)
        return self

    def pipe(self, depth=4.5, floor=0.34, side="lr"):
        """Curve the road's cross-section up into walls, from here on.

        ``bank`` tilts the whole road as one plane; this bends it. The middle
        ``floor`` of the width stays flat and the rest sweeps up to ``depth`` at
        the lip, so ``side='lr'`` is a half-pipe you can swing up either wall of
        and drop back into, and ``side='l'`` or ``'r'`` is a single banked wall
        on the outside of a corner that lets you take a high line through it.

        It blends in and out over ``PROF_BLEND`` units at each end, so a pipe is
        opened and closed where you want it rather than where a station happens
        to fall. Stays on until ``flat()``.
        """
        self.prof = (depth, floor, side)
        self.prof_last = self.prof
        self.sections.append({"t": "pipe", "depth": depth, "floor": floor,
                              "side": side})
        return self

    def flat(self):
        """Back to a flat cross-section, sinking away over ``PROF_BLEND`` units."""
        self.prof = None
        self.sections.append({"t": "flat"})
        return self

    @property
    def pos(self):
        return [self.x, self.y, self.z]

    # -- road --------------------------------------------------------------
    def straight(self, length, rise=0.0, ease=True, w=None):
        if w is not None:
            self.rail(w)
        self.sections.append({"t": "straight", "len": length, "rise": rise})
        n = self._steps(length)
        f0, _, _ = _frame(self.yaw, 0.0, 0.0)
        x0, y0, z0 = self.x, self.y, self.z
        for i in range(1, n + 1):
            u = i / n
            s = length * u
            dh, grade = self._height(rise, u, length, ease)
            pitch = math.atan(grade)
            f, r, up = _frame(self.yaw, pitch, self.roll)
            p = [x0 + f0[0] * s, y0 + dh, z0 + f0[2] * s]
            self._emit(p, up, r, kick=(rise != 0.0 and not ease))
            self.x, self.y, self.z = p
        return self

    def arc(self, degrees, radius, rise=0.0, ease=True, w=None, bank=None):
        """Sweep a corner of any angle at any radius.

        Positive ``degrees`` turns right, negative turns left. This is the whole
        cornering vocabulary: a hairpin is ``arc(170, 13)``, a long fourth-gear
        sweep is ``arc(60, 90)``, and a chicane is two arcs of opposite sign.
        """
        if w is not None:
            self.rail(w)
        if radius <= 0:
            raise ValueError("arc radius must be positive")
        self.sections.append({"t": "arc", "deg": degrees, "rad": radius,
                              "rise": rise})
        sign = 1.0 if degrees >= 0 else -1.0
        total = math.radians(abs(degrees))
        length = total * radius
        n = self._steps(length)
        # Pivot: radius to the side we are turning toward.
        _, r0, _ = _frame(self.yaw, 0.0, 0.0)
        cx = self.x + r0[0] * sign * radius
        cz = self.z + r0[2] * sign * radius
        yaw0 = self.yaw
        y0 = self.y
        roll_target = math.radians(bank) * sign if bank else self.roll
        for i in range(1, n + 1):
            u = i / n
            a = total * u
            yaw = yaw0 + sign * a
            dh, grade = self._height(rise, u, length, ease)
            pitch = math.atan(grade)
            # Ease the bank in and out across the corner so the entry and exit
            # join the straights flat.
            roll = self.roll + (roll_target - self.roll) * math.sin(math.pi * u) \
                if bank else self.roll
            f, r, up = _frame(yaw, pitch, roll)
            # position on the arc: pivot plus radius back along the new right
            px = cx - r[0] * sign * radius
            pz = cz - r[2] * sign * radius
            p = [px, y0 + dh, pz]
            self._emit(p, up, r, curv=sign / radius)
            self.x, self.y, self.z = p
        self.yaw = yaw0 + sign * total
        return self

    def crest(self, rise, length, w=None):
        """A deliberate crease in the road - it launches you.

        ``straight(l, rise=r)`` eases its grade in and out and so keeps the
        wheels down. This does not: the grade changes abruptly at both ends, so
        arriving at speed throws the car into the air. That is the difference
        between a hill and a jump, and it is geometry rather than a special case.
        """
        return self.straight(length, rise=rise, ease=False, w=w)

    def hump(self, rise, length, w=None):
        """A hill with a real crest on it: up, then straight back down.

        The grade reverses abruptly at the top, so arriving at speed throws the
        car into the air and it lands on the descending far side. This is the
        difference between the road having character and the road being a
        conveyor belt - ``straight(l, rise=r)`` is deliberately smooth and will
        never do this, so rolling crests have to be asked for.
        """
        half = length / 2.0
        self.crest(rise, half, w=w)
        return self.crest(-rise, half)

    def boost(self, length=12.0, rise=0.0):
        """A strip of road that hands you speed for driving over it.

        The pad is the *surface*, not an object standing on it: the stations are
        flagged and their road quads go into the collider as ``KIND.BOOST``, so
        the ground query the car already runs finds it with no new code, and a
        pad works upside down inside a loop for exactly the reason a half-pipe
        does. What it then does to the car is in physics.js; how much, in
        tuning.py.

        It is deliberately only a **straight**, and that is the rule rather than
        a missing feature. A pad is worth about a second of unarguable speed, so
        the place for one is somewhere the speed is usable and survivable - out
        of a slow corner, down a straight, into a jump - and never mid-corner or
        into a braking zone, where all it does is take away the decision the
        corner was for. Wanting a pad round a bend is almost always wanting it
        on the exit.
        """
        self._pad = True
        try:
            self.straight(length, rise=rise)
            # `straight` records itself as it starts and nothing else appends
            # while it runs, so this is that entry - rewritten rather than added
            # to, or one authored primitive would show up in `sections` twice.
            self.sections[-1] = {"t": "boost", "len": length, "rise": rise}
        finally:
            self._pad = False
        return self

    def gap(self, length, drop=0.0, bow=None):
        """No road at all for ``length`` units, landing ``drop`` below the lip.

        The stations across a gap are still recorded (flagged ``air``) so the
        racing line, the lap-time model and race position stay continuous over
        it, but no surface is built, so what happens in between is entirely up
        to the car's ballistics.
        """
        self.sections.append({"t": "gap", "len": length, "drop": drop})
        n = self._steps(length)
        f, r, up = _frame(self.yaw, 0.0, self.roll)
        x0, y0, z0 = self.x, self.y, self.z
        if bow is None:
            bow = min(4.0, length * 0.12)
        for i in range(1, n + 1):
            u = i / n
            s = length * u
            # A rough ballistic bow, so the line through the gap is not a chord
            # through the floor. Pinned, so the racing-line relaxation leaves it.
            h = math.sin(math.pi * u) * bow - drop * u
            p = [x0 + f[0] * s, y0 + h, z0 + f[2] * s]
            self._emit(p, up, r, air=True, fix=True)
            self.x, self.y, self.z = p
        self.y = y0 - drop
        return self

    def jump(self, rise, gap, drop=0.0, kick=8.0, land=14.0):
        """A kicker, a hole, and a landing - the whole sequence."""
        self.crest(rise, kick)
        self.gap(gap, drop=drop + rise)
        return self.straight(land)

    def loop(self, radius=20.0, shift=None, dir="l", w="lr"):
        """A full vertical loop that comes out to one side of where it went in.

        This is Polytrack's trick, and it is the only honest way to build a loop.
        A plain vertical loop is a circle in the plane of travel: it comes back to
        exactly where it started, so the road at the bottom of the descent lands
        on top of the road at the bottom of the climb. Two surfaces a metre apart
        is not a loop, it is a car trap - the ground probe finds the *ascending*
        surface on the way down and carries the car round forever, which is
        precisely what the first version of this did.

        Sliding the exit ``shift`` units sideways fixes it completely: the two
        ends are then a road's width apart and nothing overlaps. The sideways
        motion is smoothstepped, so its rate is zero at both ends and the loop
        still joins the straight road before and after it *tangentially*. That
        detail matters more than it sounds - a helix about the direction of
        travel (the obvious alternative) has a tangent permanently off its own
        axis, so it meets the road at a 55 degree kink and the car simply drives
        into the wall. This was measured, not guessed.

        The car goes fully inverted over the top, the surface normal rotates with
        it, and because steering is applied about that normal rather than about
        world up, none of the car code knows anything happened.

        ``radius`` is not a free choice. Coming over the top the road curves away
        from the car and only gravity plus ``STICK_FORCE`` hold it on, against a
        centripetal demand of ``v^2/R``. At 40 u/s that wants R near 20. A
        radius-10 loop is undrivable at racing speed however good the geometry
        is.
        """
        sd = -1.0 if dir == "l" else 1.0
        if shift is None:
            # Far enough that the exit road clears the entry road completely.
            shift = 2.0 * self.hw + 14.0
        if w is not None:
            self.rail(w)
        self.sections.append({"t": "loop", "rad": radius, "shift": shift,
                              "dir": dir})
        f0, r0, u0 = _frame(self.yaw, 0.0, 0.0)
        total = 2.0 * math.pi
        # |tangent| is sqrt(R^2 + lateral^2), so arc length is very nearly
        # uniform in theta and a fixed number of steps gives even spacing.
        n = max(24, self._steps(total * radius))
        lat_rate = shift / total
        o = self.pos
        for i in range(1, n + 1):
            a = total * i / n
            u = i / n
            ca, sa = math.cos(a), math.sin(a)
            side = shift * _smooth(u)
            # Circle in the (forward, up) plane, centre one radius above the
            # entry, plus the sideways slide.
            p = [o[k] + f0[k] * radius * sa + u0[k] * radius * (1.0 - ca)
                 + r0[k] * sd * side for k in range(3)]
            # Normal points from the road toward the centre of the circle.
            nrm = _norm([u0[k] * ca - f0[k] * sa for k in range(3)])
            # Tangent is the derivative of the path; the smoothstep's derivative
            # vanishes at both ends, which is what makes the joins tangential.
            dside = lat_rate * 6.0 * u * (1.0 - u)
            tan = _norm([f0[k] * radius * ca + u0[k] * radius * sa
                         + r0[k] * sd * dside for k in range(3)])
            lat = _norm(_cross(tan, nrm))
            e = self._emit(p, nrm, lat, fix=True)
            # The radius travels with the station so the lap-time model can work
            # out how fast the car can actually hold this thing.
            e["crad"] = round(radius, 2)
        # Exit upright, heading unchanged, `shift` to the side.
        self.x += r0[0] * sd * shift
        self.z += r0[2] * sd * shift
        self.roll = 0.0
        return self

    # -- gates -------------------------------------------------------------
    def _gate(self, kind):
        if not self.nodes:
            raise ValueError("a gate needs road under it")
        e = self.nodes[-1]
        # A gate is a plane of a fixed width and height across a flat road (see
        # `_withinGate` in course.js). Hang one across a pipe and its mouth is
        # the chord of a curve, so the car passes through the *posts* on the
        # walls and misses the gate - which is a checkpoint you cannot reach.
        # Loud here beats undrivable later.
        if e.get("pf"):
            raise ValueError("a gate cannot sit on a profiled station - "
                             "call flat() and run out the blend first")
        f = _norm(_cross(e["n"], e["lat"]))
        gi = 0
        if kind == "cp":
            self.n_cp += 1
            gi = self.n_cp
        self.gates.append({"kind": kind, "gi": gi, "p": list(e["p"]),
                           "f": f, "r": list(e["lat"]), "hw": e["hw"],
                           "si": len(self.nodes) - 1})
        return self

    def start(self, run=14.0):
        # Lay the first station *at* the turtle before moving, then put the spawn
        # a couple of stations in. Every primitive emits stations 1..n and takes
        # station 0 from whatever came before it, so without this the ribbon has
        # no surface at its own origin - and the car spawned into thin air and
        # fell through the world before it had moved.
        f, r, up = _frame(self.yaw, 0.0, self.roll)
        self._emit(self.pos, up, r)
        self.straight(STATION * 2)
        f, _, _ = _frame(self.yaw, 0.0, 0.0)
        self.spawn = {"p": self.pos, "fwd": [round(v, 4) for v in f]}
        self.straight(STATION * 2)
        self._gate("start")
        return self.straight(run)

    def cp(self, pre=17.0, post=17.0):
        """A checkpoint, with straight road either side of it.

        The run-up matters. A gate placed a few units before a corner gets cut
        by the racing line and missed entirely, which is how four tracks in the
        first pool ended up unfinishable. ``test_tracks.py`` enforces this.
        """
        self.straight(pre)
        self._gate("cp")
        return self.straight(post)

    def finish(self, pre=17.0, post=24.0):
        self.straight(pre)
        self._gate("finish")
        return self.straight(post)

    def finish_at_start(self):
        """Close the circuit: the finish line *is* the start line.

        For a closed track the road under the line is laid once, by ``start``,
        and the last primitive brings the turtle back onto it - so there is no
        road left to hang a finish gate on and ``finish`` would lay a second
        pit straight on top of the first. This copies the start gate instead,
        which is what "starts and ends at the same place" actually means.

        Crossing it on lap zero is harmless: ``Run._advance`` in course.js only
        credits the finish once every checkpoint is behind you, so the car
        driving off the grid and over the line at t=0 is ignored, exactly as a
        car crossing a checkpoint out of order is.
        """
        start = next((g for g in self.gates if g["kind"] == "start"), None)
        if start is None:
            raise ValueError("finish_at_start needs a start gate to sit on")
        g = dict(start)
        g["kind"] = "finish"
        self.gates.append(g)
        return self

    # -- output ------------------------------------------------------------
    def build(self):
        return {"line": self.nodes, "gates": self.gates, "spawn": self.spawn,
                "checkpoints": self.n_cp, "sections": self.sections}


# ---------------------------------------------------------------------------
# Geometry checks
# ---------------------------------------------------------------------------

def self_proximity(track, clearance=None):
    """Places the road runs too close to another part of itself.

    A turtle makes it easy to lay a track back over its own path. Two road
    surfaces a couple of units apart is not a crossing, it is a car trap: the
    ground probe has no good answer for which one you are on. This is the one
    check that replaces every per-shape rule the grid version needed, and it
    catches the failure for corners, hills, gaps and loops alike.

    A genuine over/under crossing is fine and shows up here as a pair with a
    large vertical gap, which is why the test is "close in plan AND close in
    height".
    """
    line = track["line"]
    n = len(line)
    if clearance is None:
        clearance = CROSS_CLEAR
    # Stations closer than this along the road are neighbours, not a crossing.
    skip = int(30.0 / STATION) + 1
    # On a closed circuit the ribbon is a ring, so the last station is the first
    # station's neighbour however far apart their indices are. Measuring the gap
    # linearly would read the join as the worst car trap on the track and, via
    # `crossings`, collapse `gate_ceiling` to its floor - which would make the
    # checkpoints unreachable on the one track that closes.
    closed = track.get("closed")
    bad = []
    for i in range(n):
        a = line[i]
        if a.get("air"):
            continue
        for j in range(i + skip, n):
            if closed and n - (j - i) < skip:
                break
            b = line[j]
            if b.get("air"):
                continue
            dx = a["p"][0] - b["p"][0]
            dz = a["p"][2] - b["p"][2]
            plan = math.hypot(dx, dz)
            reach = a["hw"] + b["hw"]
            if plan > reach:
                continue
            dy = abs(a["p"][1] - b["p"][1])
            if dy < clearance:
                bad.append({"i": i, "j": j, "plan": round(plan, 2),
                            "dy": round(dy, 2)})
    return bad


def pole_side(track):
    """Which side of the road the inside of the first corner is on.

    ``-1`` is the left-hand side, ``+1`` the right - the same sign the starting
    grid places cars with, so pole always lines up on the inside of the corner
    it is about to reach. That used to be nobody's decision: the grid simply
    alternated sides every race, which meant half the time the car that earned
    pole started on the outside of turn one and lost the place it had qualified
    for.

    Nothing here has to understand corners. Every station already carries
    ``curv``, signed the way ``arc`` is (positive turns right) and left at zero
    by hills, crests and loops - a loop is pitch, not yaw - so this is just
    "integrate the road's heading from the start line until it has committed to
    a direction". A track that never commits gets the left, arbitrarily and
    harmlessly.
    """
    line = track["line"]
    start = next((g for g in track["gates"] if g["kind"] == "start"), None)
    i0 = start["si"] if start else 0
    limit = math.radians(FIRST_TURN_DEG)
    total = 0.0
    for e in line[i0:]:
        total += e.get("curv", 0.0) * STATION
        if abs(total) >= limit:
            break
    return 1 if total > 0 else -1


def gate_ceiling(track):
    """How far above a checkpoint's centre still counts as passing through it.

    A gate is credited on a plane crossing inside a window, and the window's
    roof used to be a flat 5 units on every track. That is lower than the car
    gets: land a jump slightly long, or come out of a tow over a crest, and you
    fly straight over a checkpoint without being credited for it - which loses
    a lap you actually drove.

    It cannot simply be raised, because the roof is what stops a car on a
    bridge triggering the gate on the road underneath it. So it is per track,
    and it is derived from the one number that decides the answer: the closest
    any part of this track passes over any other part of itself. Tracks that
    never cross themselves - which is most of them, including the one made of
    jumps - get the full ceiling; Spiral Ascent, whose helix stacks 10 units
    above itself, gets a low one and keeps it honest.
    """
    line = track["line"]
    clears = [abs(line[i]["p"][1] - line[j]["p"][1]) for i, j in crossings(track)]
    if not clears:
        return GATE_CEIL_MAX
    return round(max(GATE_CEIL_MIN, min(GATE_CEIL_MAX,
                                        min(clears) - GATE_CEIL_MARGIN)), 2)


def crossings(track):
    """Station pairs that legitimately pass over each other, for the piers."""
    line = track["line"]
    n = len(line)
    skip = int(30.0 / STATION) + 1
    closed = track.get("closed")
    out = []
    for i in range(n):
        a = line[i]
        if a.get("air"):
            continue
        for j in range(i + skip, n):
            # See `self_proximity`: on a ring the two ends are neighbours.
            if closed and n - (j - i) < skip:
                break
            b = line[j]
            if b.get("air"):
                continue
            if math.hypot(a["p"][0] - b["p"][0], a["p"][2] - b["p"][2]) > a["hw"] + b["hw"]:
                continue
            if abs(a["p"][1] - b["p"][1]) >= CROSS_CLEAR:
                out.append((i, j))
    return out


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------
# Each entry: slug, display name, blurb, palette key, `ground` (world Y of the
# solid ground plane, or None for a track floating in the void where leaving the
# road means falling), difficulty, and the builder.
#
# Authoring notes, most of them learned from the headless driving tests:
#
#  * Corner radius is the whole character of a corner. Under ~16 is a hairpin you
#    have to brake hard for; 25-40 is a third-gear corner; over 60 barely slows
#    you down. Vary them - a track of identical corners is the thing the grid
#    version got wrong.
#  * `straight(l, rise=r)` is a hill and keeps the wheels down. `crest` and
#    `jump` are creases and throw the car. Use crests on purpose, and leave a
#    long flat landing after them - not a corner.
#  * A hill needs length or it becomes a jump by accident. Smoothstep peaks its
#    vertical curvature at ``6*rise/length^2``, and staying under gravity at
#    40 u/s wants a radius of 55+, so the rule of thumb is
#    ``length >= sqrt(330 * rise)``: 40 units for a 5-unit climb, 55 for 9, 77
#    for 18. `test_hills_are_eased_but_kickers_are_not` enforces it. An arc's
#    length for this purpose is its arc length, ``radians(deg) * radius``, which
#    is why a long sweeping corner can climb a long way for free.
#  * Barriers are opt-in. Floating tracks get them by default; on the ground use
#    them only where falling would be unrecoverable.
#  * Widening the road into a corner and narrowing it on a straight reads well
#    and gives the racing line something to work with.
#  * Do not lay the road back over itself under CROSS_CLEAR of vertical gap -
#    `self_proximity` fails the tests if you do.


def _sunrise():
    """Wide, flowing, on the ground. The one to learn the car on."""
    b = Builder(0, 0, 0, yaw=0, width=13.0)
    b.start(run=44)
    b.arc(72, 58).straight(30)          # fast, barely a lift
    b.cp()
    b.arc(-100, 30).straight(38)        # third gear, hook it in
    b.width(11.0)
    b.arc(-66, 44).straight(24)
    b.cp()
    b.arc(84, 26).straight(20)          # the slow one
    b.width(14.0)
    b.hump(4.0, 34).straight(26)        # over the brow, both wheels off

    b.arc(64, 52, rise=6.0)             # long sweep, climbing
    b.straight(46, rise=-6.0)
    b.cp()
    b.arc(-58, 38).straight(42)
    b.arc(-96, 34).straight(30)
    b.finish()
    return b


def _chicane_park():
    """Direction changes, two proper hairpins, all on the ground."""
    b = Builder(0, 0, 0, yaw=0, width=11.0)
    b.start(run=44)
    b.arc(-42, 30).arc(48, 26).straight(18)
    b.cp()
    b.arc(150, 15).straight(40)
    b.cp()
    b.width(13.0)
    b.hump(3.4, 30).straight(24)
    b.arc(-64, 56).arc(58, 48).straight(26)
    b.arc(-88, 30).straight(22)
    b.cp()
    b.width(10.0)
    b.arc(-165, 14).straight(46)
    b.arc(64, 40).straight(24)
    b.finish()
    return b


def _skyline():
    """Elevation over a floating track. Run wide and you fall."""
    b = Builder(0, 0, 0, yaw=0, width=11.0, rails=True)
    b.start(run=34)
    b.straight(56, rise=9.0)
    b.cp()
    b.arc(-80, 34, rise=4.0).straight(26)
    b.arc(70, 42, rise=-6.0).straight(22)
    b.cp()
    b.width(13.0)
    b.arc(95, 28, bank=16).straight(52, rise=8.0)
    b.hump(4.6, 32).straight(26)
    b.cp()
    b.arc(-72, 54, rise=-12.0).straight(26)
    b.width(10.0)
    b.arc(-104, 22).straight(48, rise=-5.0)
    b.cp()
    b.arc(88, 46).straight(34)
    b.finish()
    return b


def _twist():
    """Two full loops, each stepping out to one side. Carry speed in."""
    b = Builder(0, 0, 0, yaw=0, width=11.0, rails=True)
    b.start(run=56)
    b.loop(radius=20.0, dir="l")
    b.straight(30)
    b.cp()
    b.arc(-92, 24).straight(30)
    b.hump(4.2, 32).straight(26)
    b.cp()
    b.loop(radius=23.0, dir="r")
    b.straight(36)
    b.arc(104, 30).straight(26)
    b.cp()
    b.width(13.0)
    b.arc(-62, 56).straight(44)
    b.arc(-84, 38).straight(28)
    b.arc(58, 46).straight(26)
    b.finish()
    return b


def _hairpin_heights():
    """A climb out of hairpins, then a fast plunge back down."""
    b = Builder(0, 0, 0, yaw=0, width=11.0, rails=True)
    b.start(run=36)
    b.straight(54, rise=8.0)
    b.cp()
    b.arc(158, 17, rise=6.0).straight(50, rise=7.0)
    b.cp()
    b.arc(-150, 19, rise=6.0).straight(44, rise=5.0)
    b.cp()
    b.width(13.0)
    b.arc(90, 36).straight(78, rise=-18.0)
    b.hump(3.8, 30).straight(28)
    b.cp()
    b.arc(-72, 52, rise=-6.0).straight(30)
    b.arc(-96, 28).straight(30)
    b.arc(64, 44).straight(24)
    b.finish()
    return b


def _jump_city():
    """Gaps with nothing under them. Launch, land, repeat."""
    b = Builder(0, 0, 0, yaw=0, width=12.0, rails=True)
    b.start(run=54)
    b.jump(rise=2.6, gap=20, drop=0.0, land=34)
    b.cp()
    b.arc(-84, 30).straight(50)
    b.jump(rise=3.4, gap=26, drop=5.0, land=38)
    b.cp()
    b.arc(80, 46).straight(52, rise=7.0)
    b.jump(rise=2.2, gap=22, drop=10.0, land=40)
    b.cp()
    b.arc(96, 24).straight(52)
    b.jump(rise=3.0, gap=24, drop=4.0, land=36)
    b.cp()
    b.arc(-64, 56).straight(30)
    b.arc(-88, 36).straight(26)
    b.finish()
    return b


def _spiral():
    """A long climbing spiral, then a dive down the outside of it."""
    b = Builder(0, 0, 0, yaw=0, width=11.0, rails=True)
    b.start(run=40)
    b.arc(180, 42, rise=14.0, bank=12)
    b.cp()
    b.straight(30)
    b.arc(180, 32, rise=13.0, bank=14)
    b.cp()
    b.straight(28)
    b.width(13.0)
    b.arc(120, 26, rise=5.0)
    b.straight(56, rise=-9.0)
    b.cp()
    b.arc(-140, 48, rise=-16.0, bank=16)
    b.straight(50, rise=-7.0)
    b.cp()
    b.arc(88, 38).straight(26)
    b.hump(4.0, 32).straight(26)
    b.arc(-60, 54).straight(26)
    b.finish()
    return b


def _figure_eight():
    """Short, and it really does cross over itself."""
    b = Builder(0, 0, 0, yaw=0, width=12.0)
    b.start(run=40)
    b.straight(40)                      # this is the road it comes back over
    # Three quarters of a turn, climbing. Ending a 270 degree arc of radius R
    # puts you one radius back down the road you came in on, heading across it -
    # which is what makes the crossing happen rather than hoping for it.
    b.arc(270, 34, rise=14.0)
    b.hump(3.4, 30).straight(24)        # over the deck, above the start straight
    b.cp()
    b.straight(30)
    b.straight(68, rise=-14.0)          # back down to ground level
    b.arc(-98, 24).straight(44)
    b.cp()
    b.arc(-86, 52).straight(54)
    b.cp()
    b.arc(94, 38).straight(28)
    b.finish()
    return b


def _gauntlet():
    """Loops, gaps, hairpins, elevation. Everything, and twice as long."""
    b = Builder(0, 0, 0, yaw=0, width=12.0, rails=True)
    b.start(run=52)
    b.loop(radius=20.0, dir="l")
    b.straight(34)
    b.cp()
    b.arc(-78, 42, rise=8.0).straight(32)
    b.arc(66, 30).straight(24)
    b.hump(4.4, 34).straight(26)
    b.cp()
    b.jump(rise=3.0, gap=24, drop=6.0, land=38)
    b.cp()
    b.arc(162, 16).straight(56, rise=-9.0)
    b.cp()
    b.width(14.0)
    b.arc(-84, 54, bank=14).straight(46)
    b.loop(radius=22.0, dir="r")
    b.straight(36)
    b.cp()
    b.arc(96, 26).straight(48, rise=6.0)
    b.jump(rise=2.4, gap=20, drop=8.0, land=34)
    b.cp()
    b.arc(-152, 18).straight(30)
    b.hump(3.6, 30).straight(24)
    b.width(11.0)
    b.arc(78, 46).straight(38)
    b.cp()
    b.arc(-90, 34).straight(30)
    b.finish()
    return b


def _rainbow():
    """Rainbow Road: half-pipes, a loop, and almost nothing to stop you falling.

    The three long tracks are meant to be endurance tests, and this one takes
    its difficulty from exposure. It is deliberately the only track in the pool
    with barriers almost nowhere (see ``EXPOSED``): the pipes catch you where
    there are pipes, and everywhere else running wide is a fall.
    """
    b = Builder(0, 0, 0, yaw=0, width=13.0, rails=False)
    b.start(run=44)
    b.straight(58)
    b.cp()

    # The one full half-pipe on the track: walls both sides, swing up either and
    # drop back in. Everywhere else the profile is one-sided (see below), which
    # is a corner you can lean on rather than a trough you sit in - so this is
    # the section that shows what the cross-section can do, and it is deliberately
    # the only one of its kind.
    b.pipe(5.5).straight(96).arc(-38, 95).straight(64)
    b.flat().straight(32)
    b.cp()

    # A fast left with a wall only on its outside, so the high line exists.
    b.pipe(4.8, floor=0.28, side="r").arc(-98, 48).flat().straight(38)
    b.cp()

    # Out over nothing.
    b.straight(34)
    b.jump(rise=3.6, gap=27, drop=0.0)
    b.straight(34)
    b.cp()

    # The loop keeps its rails - a loop without them is a fall at the top
    # rather than a corner, and that is not exposure, it is a broken corner.
    b.loop(radius=22.0, dir="r", w="lr")
    b.rail("").straight(44)
    b.cp()

    # A long right-hander banked up its outside - the left - so the high line
    # through it is a real choice rather than a wall to avoid.
    b.width(15.0)
    b.pipe(6.2, side="l").arc(76, 58).straight(72)
    b.flat().width(12.0).straight(34)
    b.cp()

    # Then the exposed part, with nothing either side of it.
    b.arc(-128, 23).straight(42)
    b.hump(4.2, 34).straight(30)
    b.cp()

    # A chicane out in the open, then a climb away.
    b.arc(58, 30).arc(-62, 28).straight(60, rise=9.0)
    b.arc(96, 40, rise=6.0).straight(52)
    b.cp()

    # The deepest wall on the track, and again only on the corner's outside. It
    # opens at the corner rather than on the straight before it, so the bank
    # arrives with the turn.
    b.width(14.0)
    b.straight(58)
    b.pipe(6.8, floor=0.26, side="r").arc(-84, 44).straight(66)
    b.flat().width(12.0).straight(34)
    b.cp()

    # The second loop, then the long exposed run home.
    b.loop(radius=24.0, dir="l", w="lr")
    b.rail("").straight(66, rise=-11.0)
    b.cp()

    b.arc(-142, 21).straight(48)
    b.arc(78, 54, rise=-8.0).straight(62)
    b.hump(3.8, 32).straight(34)
    b.cp()

    b.arc(92, 42).straight(56)
    b.arc(-64, 68).straight(34)
    b.finish()
    return b


def _big_red():
    """Big Red: a sheer dive through a sunset sky, over a city drowned in cloud.

    The shape is the whole idea, and it is Big Blue's: you start at the top and
    the track spends the rest of itself going *down* - over 220 units of it
    across 3300, so the finish sits nearly three loops' height below the start
    and the one real climb on the whole track is the loop itself, the moment it
    hauls you back up rather than a trick sitting in the middle of a flat road.

    Five moments are genuinely airborne rather than just steep, and four of
    them are the same big jump repeated: a pad feeds a long, shallow kicker
    into a gap wide enough that the car is in the air for the best part of two
    seconds, dropping onto a stretch of road well under where it left - the
    one place on the track where "down" is something you fly rather than
    corner your way through. One is small, in the middle, the same idea in
    miniature. The other three are the real thing, and the back third of the
    lap is built around them: off the first slow hairpin, then a closing run
    of hairpin-into-jump repeated twice more, each hairpin resetting the
    speed for a pad that feeds the next jump, so the last stretch of the track
    is a hairpin, a jump, a hairpin, a jump, and the flag. All five gaps are
    pure ballistics: ``gap``'s own bow is too gentle for a fall this size and
    reads as a kink the lap model brakes hard for, so each is authored with an
    explicit ``bow`` that matches the kicker's exit angle and lets the model
    see the same rising-then-falling arc the car actually flies.

    None of the big jumps is as long as it could be made to look on paper.
    ``AIR_PITCH`` noses the car down at a constant rate for as long as the
    throttle is held in the air - which is how the pool's other jumps are
    flown, and how these are too - so hang time is what decides how far past
    level the nose has rotated by the time the wheels come back down, not
    distance or drop. A shallow kicker (a 4-unit rise over 50, on all four)
    buys most of that budget back: pitch grows with time in the air, not with
    how far it falls, so a launch angle close to flat gets a deep drop and a
    long carry for the same rotation a steeper, shorter kicker would spend on
    height it does not need. It also has to stay short enough that the pad is
    still live at the lip - `PAD_BOOST` is 1.3s, and a kicker long enough to
    run the car out of it arrives much slower, which is most of a jump's real
    reach gone before the ballistics get a say. The landing straight after
    each gap is long - 140 units before the next gate - on purpose: real
    speed at the lip varies with how the corner before it was driven, so the
    touchdown point moves around, and the gate needs room to be past it every
    time rather than only on the one lap that matched the model exactly.

    Corners are big and banked because a descent is fast and a fast corner you
    can lean on is what carries speed rather than scrubbing it; the tight
    hairpins exist so the big ones have something to be big *against*. It is
    in ``EXPOSED`` and keeps barriers in only five places - the loop, and the
    landing straight after each of the four big jumps, all of them being where
    a car arrives with no chance to correct rather than an ordinary corner
    exit. Everywhere else the edge is just the edge, including every one of
    the closing hairpins: a downhill track built around how far down it is
    loses the point of itself walled all the way round.

    The six boost pads are the only ones in the pool. They are all on
    straights and all with a long run to the next braking point - out of each
    slow corner and into the jump that follows it, and onto the loop - because
    a pad is worth about a second of unarguable speed and the place for that
    is somewhere you can use it, never into a corner where all it does is take
    the corner away.
    """
    b = Builder(0, 0, 0, yaw=0, width=14.0, rails=False)
    b.start(run=46)
    b.boost(20)                              # off the line, before anything else
    b.straight(95, rise=-16.0)               # the drop off the top

    b.arc(-64, 92, rise=-18.0, bank=16)      # the first big banked left, falling
    b.cp()
    b.straight(75, rise=-10.0)
    b.arc(80, 62, bank=18, rise=-14.0)
    b.straight(34)
    b.cp()

    # The slow one. Everything either side of it is fourth gear or better, so
    # this is the only place on the track anybody has to think about braking.
    b.width(12.0)
    b.arc(-120, 26, rise=-6.0)
    b.straight(26)
    b.cp()

    # The big jump. A pad and a short runway to speed, a long shallow kicker,
    # and a gap wide enough that the fall is the point: 90 units of nothing
    # and a 30-unit drop to the far side. ``bow`` is authored by hand rather
    # than left to default - see the docstring above - so the lap model's own
    # ballistics see the same climb-then-fall the car does and do not brake
    # for it as if it were a corner. The landing straight is long on purpose -
    # see the docstring - so the gate is well clear of the touchdown however
    # the lip was actually hit, and it is the one place either side of the
    # loop that gets its rails back: the car arrives with no steering, so
    # a wide touchdown is not a decision anybody made.
    b.width(13.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.width(14.0)
    b.arc(96, 66, bank=20, rise=-16.0)       # the longest corner on the track
    b.straight(40)
    b.cp()

    # The small jump, the same idea in miniature - and its landing gets the
    # same short-lived rail for the same reason.
    b.crest(3.4, 9.0)
    b.gap(26.0, drop=9.4)
    b.rail("lr").straight(32.0)
    b.rail("")
    b.arc(-88, 48, rise=-10.0).straight(36)
    b.cp()

    # The loop, and the one climb. It is fed by a pad and a straight because a
    # loop is a speed check before it is anything else - arrive slow and the car
    # comes off the roof of it. It keeps its rails too: a loop without them is
    # a fall at the top rather than a corner, which is not exposure, it is a
    # broken corner.
    b.boost(20)
    b.rail("lr").straight(30)
    b.loop(radius=22.0, dir="l")
    b.straight(40)
    b.rail("")
    b.cp()

    b.arc(70, 58, rise=-12.0, bank=15).straight(44)
    b.width(12.0)
    b.arc(-140, 22).straight(34)             # the hairpin, and the last slow bit
    b.cp()

    # The third jump, off the last pad - the same shallow kicker and the same
    # margins as the first, closing the lap the way it opened: in the air.
    b.boost(20)
    b.width(14.0)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    # A closing run of hairpin-into-jump, twice over, each jump the same size
    # as the others and fed the same way - a hairpin to reset the speed, a
    # pad, the same shallow kicker and gap. None of these last corners are
    # railed: by here the track has committed to being run at the edge, and a
    # hairpin taken wide is a fall rather than a save either way.
    b.width(12.0)
    b.arc(128, 24, rise=-6.0)
    b.straight(24)
    b.cp()

    b.width(14.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.width(12.0)
    b.arc(-136, 20, rise=-5.0)
    b.straight(24)
    b.cp()

    b.width(14.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.arc(86, 42).straight(34)
    b.finish()
    return b


# Sandy Cove's waterline, as a world Z. The track is authored against it rather
# than the other way round: a shoreline can only read as a coast if the road
# runs *along* it, so the outbound half is pinned to a band just inland of this
# and the pier is the one thing that crosses it. `SHORE_Z` is duplicated in the
# `cove` palette in trackmesh.js, which draws the water - and a test pins the
# two together, because a waterline that drifts inland puts the road in the sea.
SHORE_Z = 170.0
SHORE_AMP = 40.0
SHORE_WAVE = 420.0


def _cove():
    """Sandy Cove: a coast road along the water, out onto a pier, then inland.

    A ground track, so running wide costs you sand rather than your lap, which
    is the right penalty on a long one. The sea is scenery and is never in the
    collider, so the pier has nothing at all under it: run off that and you fall.

    The geography is the point and it constrains the layout. The outbound half
    runs along the beach with the water on its left, close enough to see the
    whole way; the pier is a loop out over it and back; then the road turns
    inland and the return half is dunes, which is what lets it have the hairpins
    a coast road cannot.
    """
    b = Builder(0, 0, -20, yaw=0, width=12.0, rails=False)
    b.start(run=40)
    b.straight(70, rise=9.0)                     # up onto the low headland
    b.cp()

    # Along the top, bending out toward the water and back.
    b.arc(30, 66, rise=4.0).straight(52)
    b.arc(-38, 58, rise=-5.0).straight(44)
    b.cp()

    b.width(14.0)
    b.arc(44, 46, bank=14).straight(72, rise=-8.0)     # down onto the sand
    b.arc(-40, 52).straight(40)
    b.cp()

    # Two inlets cut into the beach.
    b.width(11.0)
    b.straight(30)
    b.jump(rise=2.8, gap=22, drop=0.0)
    b.straight(28)
    b.jump(rise=3.0, gap=25, drop=0.0)
    b.straight(34)
    b.cp()

    # The pier: out over open water and back. Narrow, flat, no barriers, and
    # the only part of the track with nothing whatever underneath it.
    b.width(9.5)
    b.arc(58, 34).straight(210)
    b.arc(-116, 28).straight(150)
    b.cp()
    b.arc(-58, 34).straight(46)                        # back onto the sand
    b.width(13.0)
    b.arc(52, 60).straight(58)
    b.cp()

    # Turn inland. Everything from here is dunes, so it can be tighter.
    b.width(11.0)
    b.arc(-128, 24).straight(48, rise=6.0)
    b.arc(96, 30, rise=5.0).straight(44)
    b.cp()

    b.width(14.0)
    b.arc(-62, 78, rise=6.0).straight(82)
    b.hump(3.4, 30).straight(30)
    b.cp()

    # Round the rocky point: three corners and no straight worth the name.
    b.width(10.5)
    b.arc(116, 26).straight(30)
    b.arc(-102, 24).straight(28)
    b.arc(128, 22).straight(40)
    b.cp()

    # A last drop to the sand for the third inlet, then the climb to the line.
    b.width(12.0)
    b.arc(-70, 48, rise=-11.0).straight(56)
    b.jump(rise=3.2, gap=26, drop=0.0)
    b.straight(36)
    b.cp()

    b.width(13.0)
    b.arc(88, 40, rise=8.0).straight(64, rise=6.0)
    b.arc(-66, 50).straight(42)
    b.finish()
    return b


def _pillars():
    """Cloudbreak: threaded between rock spires, a long way above anything.

    The spires are scenery (see the ``pillars`` world in trackmesh.js) - they
    are placed clear of the road, so what actually catches you out here is the
    elevation and the corner radii, not hitting one.

    Barriers are the exception rather than the rule here (it is in ``EXPOSED``).
    Railing the whole thing made it a bobsleigh run: on a track whose entire
    subject is how far down the ground is, a wall along every corner is the one
    thing that takes the height away. So they are kept for the three places
    where going off is not a mistake you could have avoided - the two jump
    landings, where you arrive with no steering, and the narrow bridge, which is
    barely wider than the car.
    """
    b = Builder(0, 0, 0, yaw=0, width=11.5, rails=False)
    b.start(run=40)
    b.straight(56, rise=7.0)
    b.cp()

    b.arc(-92, 38, rise=5.0).straight(44)
    b.arc(104, 30, rise=-3.0).straight(36)
    b.cp()

    b.width(13.0)
    b.arc(-74, 56, bank=17).straight(70, rise=10.0)
    b.cp()

    b.width(10.5)
    b.arc(148, 18, rise=4.0).straight(40)              # hairpin between spires
    b.arc(-136, 20).straight(58, rise=-8.0)
    b.cp()

    # Across the gorge. Rails on the landing only: you come down with no
    # steering authority, which is not a mistake, it is the jump.
    b.straight(28)
    b.jump(rise=4.0, gap=30, drop=6.0)
    b.rail("lr").straight(36)
    b.rail("").cp()

    b.width(13.5)
    b.arc(88, 52, rise=-6.0).straight(58)
    b.hump(4.4, 34).straight(30)
    b.cp()

    b.arc(-116, 26).straight(60, rise=-9.0)
    b.arc(96, 34).straight(40)
    b.cp()

    # A long banked spiral down between the spires.
    b.width(12.5)
    b.arc(-132, 42, rise=-14.0, bank=19).straight(54, rise=-6.0)
    b.arc(-118, 38, rise=-11.0, bank=17).straight(52)
    b.cp()

    # The narrow bridge - 9.5 wide, so it keeps its rails - and the second gorge.
    b.width(9.5)
    b.rail("lr").straight(72)
    b.arc(86, 28).straight(34)
    b.rail("").jump(rise=3.6, gap=28, drop=0.0)
    b.rail("lr").straight(34)
    b.rail("").cp()

    b.width(13.0)
    b.arc(-98, 44, rise=7.0).straight(66, rise=8.0)
    b.hump(4.0, 32).straight(30)
    b.cp()

    b.width(11.5)
    b.arc(-68, 60, rise=-5.0).straight(62)
    b.arc(74, 44).straight(38)
    b.finish()
    return b


def _spa(kemmel=334.35, stav=355.50):
    """Spa-Francorchamps: the real circuit, compressed, and the only closed lap.

    Every other track in the pool is point-to-point, because a turtle that ends
    where it started is a turtle you have to solve for rather than author. This
    one closes: the finish line *is* the start line (``finish_at_start``), and
    the ribbon is a ring whose seam is station 0, fourteen units behind the grid.

    Three things had to be true at once for that to work and they are worth
    knowing before moving anything:

     * **The corner angles sum to exactly 360.** They are fixed, so yaw closes
       by construction and the solver can never reach for a named corner and
       distort it - the first attempt left Stavelot as a 179-degree hairpin.
       Change one angle and you must take the same amount out of another.
     * **Two straights are solved, not authored.** ``KEMMEL`` and the two halves
       of the Stavelot run are whatever closes the position, found offline by
       Newton on the plan-view walk and baked here. They are the two long legs
       of the circuit's triangle, so they span the plane between them and the
       solve is well conditioned. Change any other length and they must be
       re-solved or the ribbon will not meet itself.
     * **The rises sum to exactly zero**, or the road arrives at the line at the
       wrong height. ``test_spa_closes`` pins all of it.

    The shape is Spa's and so is the elevation: the grades are real, which on a
    circuit compressed to 2800 units puts 63 units between the top of the hill
    at Les Combes and the bottom at Campus. It climbs to La Source, plunges to
    Eau Rouge, climbs all the way up Raidillon and Kemmel to the highest point,
    then falls continuously for the whole middle of the lap to Stavelot before
    the long blast home lifts it back to the line.

    It is wide - 16 units, the widest in the pool - because a Grand Prix circuit
    is, and because the run-off does the punishing here rather than the kerb.
    There are no barriers on the road edge at all: what catches a car is the
    armco set back beyond the gravel, which is drawn and collided in trackmesh
    off the ribbon rather than authored corner by corner.
    """
    # A checkpoint lays CP units of its own road (`cp`'s pre + post), so every
    # one of them is subtracted from the straight that hosts it. Miss that and
    # eight checkpoints walk the ribbon 272 units past its own start.
    CP = 34.0
    KEMMEL = kemmel                   # solved, see tools/close_spa.py
    STAV_A, STAV_B = stav * 0.55, stav * 0.45   # solved, split by the kink

    b = Builder(0, 0, 0, yaw=0, width=16.0, rails=False)

    # --- the pit straight, and up to La Source ------------------------------
    # `start` puts the line 14 units in and lays `run` past it, so the grid sits
    # on the same tarmac that is the last thing you cross on the lap.
    b.start(run=70.0)
    b.straight(69.0, rise=11.0)
    b.cp()
    b.straight(62.0)

    # La Source. A big slow right through 170 degrees that points you down the
    # hill - the one place on the circuit you are properly slow.
    b.width(14.0)
    b.arc(170, 22.10, rise=2.0)
    b.width(16.0)

    # --- the plunge, Eau Rouge and Raidillon --------------------------------
    b.straight(143.0 - CP, rise=-26.0)
    b.cp()
    b.arc(-25, 62.40, rise=-2.0)         # Eau Rouge, at the bottom
    b.arc(50, 52.00, rise=6.0)           # Raidillon, turning up the hill
    b.straight(62.0, rise=9.0)
    # The car goes light over the top and settles again, which is the whole
    # sensation of the place. `crest` is a deliberate crease; `straight(rise=)`
    # smoothsteps and would keep the wheels down.
    b.crest(2.0, 24.0)
    b.straight(20.0)
    b.arc(-28, 84.50, rise=4.0)          # the kink at the top

    # --- Kemmel, the longest straight on the circuit ------------------------
    b.straight(KEMMEL - CP, rise=14.0)
    b.cp()

    # --- Les Combes, and the top of the hill --------------------------------
    b.width(14.0)
    b.arc(78, 33.80, rise=-1.0)
    b.arc(-80, 31.20, rise=-1.0)
    b.width(16.0)
    b.straight(71.50, rise=-5.0)

    # --- the long descent: Malmedy, Rivage, Speaker's -----------------------
    b.arc(58, 58.50, rise=-4.0)          # Malmedy
    b.straight(65.0, rise=-5.0)
    b.width(14.0)
    b.arc(152, 23.40, rise=-7.0)         # Rivage, tight and downhill
    b.width(16.0)
    b.straight(58.50, rise=-5.0)
    b.arc(-75, 44.20, rise=-4.0)         # Speaker's Corner
    b.straight(78.0 - CP, rise=-4.0)
    b.cp()

    # --- Pouhon: the fast double-left, still falling ------------------------
    b.width(17.0)
    b.arc(-105, 71.50, rise=-11.0, bank=8)
    b.width(16.0)
    b.straight(91.0 - CP, rise=-6.0)
    b.cp()

    # --- Fagnes, Campus, and the bottom of the circuit ----------------------
    b.width(14.0)
    b.arc(72, 35.10, rise=-2.0)
    b.arc(-70, 32.50, rise=-2.0)
    b.width(16.0)
    b.straight(71.50, rise=-3.0)
    b.arc(88, 41.60, rise=-2.0)          # Campus
    # 150 rather than the ~78 the shape wants, and the extra 72 units are load
    # bearing: they push the bottom of the circuit clear of the Blanchimont
    # return leg. At 78 the Pouhon exit and Blanchimont A ran 6.5 units apart in
    # plan with 4 units of height between them, which is not a crossing, it is a
    # car trap - two surfaces the ground probe cannot choose between. Clearing
    # `self_proximity` was not enough either: at 110 the two roads' centres were
    # 15 units apart, so their kerbs touched and there was physically nowhere to
    # put the gravel and the armco this track is supposed to have. At 150 the
    # closest the circuit comes to itself anywhere is La Source's own hairpin,
    # which is a corner doubling back and has nothing between its ends anyway.
    b.straight(150.0 - CP, rise=-1.0)
    b.cp()

    # --- Stavelot, and the long blast home ----------------------------------
    b.arc(130, 44.20, rise=2.0)
    b.straight(STAV_A, rise=14.0)
    b.arc(9, 286.00, rise=2.0)           # a gentle kink, so it is not a runway
    b.straight(STAV_B - CP, rise=11.0)
    b.cp()

    # Blanchimont: flat out, and barely a corner at this radius.
    b.arc(-43, 123.50, rise=4.0)
    b.straight(97.50, rise=5.0)
    b.arc(-26, 117.00, rise=2.0)
    b.straight(84.50 - CP, rise=3.0)
    b.cp()

    # --- the Bus Stop, and back onto the line -------------------------------
    b.width(13.0)
    b.arc(90, 19.50)
    b.arc(-85, 19.50)
    b.width(16.0)
    b.straight(123.50)

    # The ribbon is now back on top of station 0, and the line is already there.
    b.finish_at_start()
    return b


# Tracks whose ribbon is a ring: the last station is the first station's
# neighbour, and the finish gate is the start gate. `self_proximity` and
# `crossings` measure the gap between stations circularly for these, or the
# join reads as the worst car trap on the track.
CLOSED = {"spa"}

# Tracks where falling off is the point rather than a gap in the barriers.
# `test_barriers_are_opt_in` requires a floating track to catch a wide moment
# somehow, because with no ground under it running wide is a respawn rather
# than a penalty. These declare that they deliberately do not, and the test
# checks the claim in both directions - an "exposed" track with rails all over
# it is as wrong as a normal one without them.
EXPOSED = {"rainbow", "pillars", "bigred"}


_POOL = [
    ("sunrise", "Sunrise Circuit", "Wide, flowing and forgiving - the one to learn the car on.",
     "sunrise", -1.2, 1, _sunrise),
    ("chicane", "Chicane Park", "Quick direction changes and two very slow hairpins.",
     "chicane", -1.2, 2, _chicane_park),
    ("skyline", "Skyline Sprint", "Up and over a floating skyline. Miss a corner and you fall.",
     "skyline", None, 3, _skyline),
    ("twist", "Twin Loop", "Two full loops that step out sideways. Carry speed in.",
     "desert", None, 3, _twist),
    ("heights", "Hairpin Heights", "A climb made of hairpins, then a fast plunge back down.",
     "heights", None, 4, _hairpin_heights),
    ("jumpcity", "Jump City", "Four gaps with nothing under them. Launch, land, repeat.",
     "city", None, 4, _jump_city),
    ("spiral", "Spiral Ascent", "A long banked spiral to the top and a dive down the outside.",
     "spiral", None, 4, _spiral),
    ("eight", "Figure Eight", "Short, and it crosses over itself.",
     "winter", -1.2, 2, _figure_eight),
    ("gauntlet", "The Gauntlet", "Loops, gaps, hairpins, elevation. Everything, twice over.",
     "gauntlet", None, 5, _gauntlet),
    ("cove", "Sandy Cove", "A coast road down to the beach and out along the pier. Long.",
     "cove", -1.2, 5, _cove),
    ("pillars", "Cloudbreak", "Threaded between rock spires, miles above the cloud.",
     "pillars", None, 5, _pillars),
    ("rainbow", "Rainbow Road", "Half-pipes in deep space, and almost no barriers. Do not fall.",
     "rainbow", None, 5, _rainbow),
    ("bigred", "Big Red", "A sheer dive on boost pads, launched twice over a drowned city.",
     "bigred", None, 4, _big_red),
    ("spa", "Spa-Francorchamps", "The Ardennes circuit, compressed. Wide, fast, and a full closed lap.",
     "spa", -1.2, 4, _spa),
]


def _assemble():
    out = []
    for slug, name, blurb, palette, ground, difficulty, fn in _POOL:
        built = fn().build()
        t = {"slug": slug, "name": name, "blurb": blurb, "palette": palette,
             "ground": ground, "difficulty": difficulty,
             "exposed": slug in EXPOSED, "closed": slug in CLOSED,
             "cell": CELL, "level": LEVEL, "station": STATION}
        t.update(built)
        # Both derived from the ribbon rather than authored, so a new track gets
        # them for free and cannot get them wrong.
        t["pole_side"] = pole_side(t)
        t["gate_ceil"] = gate_ceiling(t)
        out.append(t)
    return out


TRACKS = _assemble()
BY_SLUG = {t["slug"]: t for t in TRACKS}

# Medal times need the lap simulation, which needs the assembled ribbons - hence
# the import down here rather than at the top.
import laptime  # noqa: E402

for _t in TRACKS:
    _t["ideal"] = laptime.ideal_lap(_t)
    _t["medals"] = laptime.medals(_t["ideal"])


def summaries():
    """Everything the track-select screen needs, without the station lists."""
    return [{k: t[k] for k in ("slug", "name", "blurb", "difficulty", "ideal",
                               "medals", "checkpoints")} for t in TRACKS]


def get(slug):
    return BY_SLUG.get(slug)
