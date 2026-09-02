"""The ribbon format, and the turtle that authors one.

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

Most tracks are point-to-point: a start, ordered checkpoints, a finish. A track
that says ``closed = True`` is a lap instead - the finish line *is* the start
line - and `solver.py` is what makes its ribbon meet itself.
"""

import math

# `CELL` and `LEVEL` are re-exports, not uses: nothing below touches them, but
# `tracks/__init__.py` imports both *from here*, so a linter told to strip unused
# imports would break every `import tracks` in the game. Leave them.
from tuning import CELL, LEVEL, ROAD_W    # noqa: F401

# Station spacing along the road. Small enough that a 20-unit-radius corner is
# smooth (3.5 units of arc is a 10 degree step) and that the collision surface
# has no visible facets; large enough that a 1000-unit track is ~290 stations,
# which is a few thousand triangles and a JSON payload measured in tens of KB.
STATION = 3.5

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


class FREE(float):
    """Marks a number the closure solver may adjust: ``b.straight(FREE(330))``.

    Only needed on a **closed** track, and only when the solver's own choice is
    wrong. It picks the legs where a change shows least - the longest straights,
    the biggest-radius corner - which is right for a loop somebody laid out by eye
    and wrong for one whose shape is the point. Spa nominates Kemmel and the
    Stavelot run because every corner on it is a real place with a real name, and
    a solver free to lengthen the pit straight by 12% to close the lap would
    produce a circuit that closes and is not Spa.

    It is a ``float``, so it behaves as its value everywhere else and only the
    Builder notices. That means it has to wrap the **whole** expression - by the
    time ``FREE(330) - CP`` reaches `straight` it is an ordinary float and the mark
    is gone. Write ``FREE(330 - CP)``.
    """

    __slots__ = ()


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
        # What the closure solver is allowed to change, as
        # `{(section_index, param): value}`. Empty for every ordinary build; see
        # `_tweak` and `tracks/solver.py`.
        self._sub = {}
        # Legs the author marked with `FREE()`, as `[(section_index, param), ...]`.
        self._free = []
        # The heading the walk started on. Recorded because closing a lap means
        # ending on it, and a station carries a normal and a lateral rather than a
        # yaw - so once the turtle has moved there is nothing left to compare with.
        self._yaw0 = self.yaw
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
        # Same again for a mushroom cap. See `bounce`.
        self._cap = False
        self._skin = False       # this road is the back of something; see `skin`

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
        # A mushroom cap is a property of the surface too - see `bounce`.
        if self._cap and not air:
            e["bn"] = 1
        if fix:
            e["fix"] = 1
        if kick:
            e["kick"] = 1
        if curv:
            e["curv"] = round(curv, 5)
        # This stretch of road is not a road; see `skin` below.
        if self._skin and not air:
            e["skin"] = 1
        if (self.wl if wl is None else wl) and not air:
            e["wl"] = 1
        if (self.wr if wr is None else wr) and not air:
            e["wr"] = 1
        self.nodes.append(e)
        return e

    def _tweak(self, ka, va, kb, vb):
        """Let the closure solver substitute this primitive's numbers.

        A closed track has to come back to where it started, and no author gets
        that right by eye - a straight three units too long is a three-unit step
        in the road at the seam. So `tracks/solver.py` re-runs `build` a handful of
        times with different values for one or two legs until the ribbon meets
        itself, and this is the one seam that lets it.

        Keyed by **position in `sections`** rather than by name, so an ordinary
        track needs no annotation at all - the author writes `b.straight(330)` and
        the solver decides that leg is the one to adjust. `FREE()` in a track file
        is only a way of nominating a *different* leg than the one it would pick.

        `len(self.sections)` is the index this call is about to occupy. It is
        stable across re-runs because the primitives are appended in a fixed
        order - and `solver` checks that, because a `build` that branched on
        geometry would silently renumber every leg after the branch.
        """
        i = len(self.sections)
        # Nominations are recorded on every build, substitutions only on a solve.
        # The solver needs the list *before* it can substitute anything, so the
        # first pass has to come back with the marks in it.
        if isinstance(va, FREE):
            self._free.append((i, ka))
        if isinstance(vb, FREE):
            self._free.append((i, kb))
        if not self._sub:
            return va, vb
        return self._sub.get((i, ka), va), self._sub.get((i, kb), vb)

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

    def skin(self, on=True):
        """Stop drawing tarmac from here on: this road is the back of something.

        The same shape of thing as `boost` and `bounce` - a property of the
        *surface* rather than an object standing on it - and it is the smallest
        of the three, because it changes nothing about the simulation at all.
        The stations still carry the same road quads, the same `KIND.ROAD`
        collider and the same racing line; `trackmesh.js` simply draws them in
        `pal.skin` and lays no kerb, so what you drive along is hide rather than
        dirt with a creature under it.

        It exists because "the road goes over a dinosaur" and "the dinosaur's
        back *is* the road" look identical on paper and are completely different
        to drive: the first is a bridge with decoration beneath it, and you can
        tell, because the kerb keeps running.

        The scenery that builds the animal is expected to find its own extent by
        looking for these stations, which is why this is a flag on the ribbon and
        not a colour in a palette - it is the one statement that both halves read.
        """
        self._skin = bool(on)
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
        length, rise = self._tweak("len", length, "rise", rise)
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
        degrees, rise = self._tweak("deg", degrees, "rise", rise)
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

    def boost(self, length=12.0, rise=0.0, ease=True):
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

        ``ease`` is the same flag `straight` takes, and passing ``False`` makes
        the pad a **kicker** rather than a hill - which is the one thing a pad
        needs to be able to do that "straight" did not already cover. Mount Joy
        drives a ramp up a mountainside as a chain of steepening kickers with a
        pad on every one of them, because `PAD_BOOST` is 1.3 seconds and a ramp
        long enough to climb anything worth climbing runs out of boost halfway
        up: a pad *on* the climb re-arms itself every step, so the engine is
        still 1.7x at the lip. An eased hill cannot be used for that, because
        eased means grade zero at both ends and so no launch angle at all.
        """
        self._pad = True
        try:
            self.straight(length, rise=rise, ease=ease)
            # `straight` records itself as it starts and nothing else appends
            # while it runs, so this is that entry - rewritten rather than added
            # to, or one authored primitive would show up in `sections` twice.
            self.sections[-1] = {"t": "boost", "len": length, "rise": rise}
        finally:
            self._pad = False
        return self

    def bounce(self, length=14.0, rise=0.0, ease=True):
        """A mushroom cap: road that throws you back up instead of catching you.

        The same shape of thing as ``boost`` and built the same way - the cap is
        the *surface*, not an object standing on it. The stations are flagged,
        their road quads go into the collider as ``KIND.BOUNCE``, and the ground
        query the car already runs finds it, so nothing in the collision code has
        to know caps exist. What it does to the car is in physics.js; how much,
        in tuning.py.

        Unlike ``boost`` this is **not** restricted to a straight, and the
        difference is worth stating because the two look like the same rule. A
        pad is a strip you accelerate *along*, so a pad mid-corner takes away the
        decision the corner was for. A cap is a single point you touch and leave:
        the car is on it for one physics step out of the roughly 170 the hop
        takes, so "along" is not a thing that happens on one, and a cap on a bend
        is just a cap you have to be pointing the right way when you leave.

        It does want to be **flat**, though, and that is a real constraint rather
        than taste: the launch is along the station's own normal, so a cap on a
        grade fires the car off to one side of where the road goes, and a cap on
        a banked station fires it at the wall. ``rise`` exists to let a chain of
        caps step down a chasm without each one needing its own gap; keep it
        small, and keep ``ease`` on, because an un-eased rise marks the stations
        ``kick`` and a cap does not need help throwing you.

        **Widen the road over a cap** with ``width()`` either side of it. A cap is
        a target the car arrives at out of the air with ``AIR_STEER``'s fraction
        of its steering, and a 12-wide disc at the end of a fifty-unit flight is
        a coin toss rather than a line. Every cap on Shroom Street is 20 wide
        against a 13-wide road.
        """
        self._cap = True
        try:
            self.straight(length, rise=rise, ease=ease)
            # `straight` records itself as it starts and nothing else appends
            # while it runs, so this is that entry - rewritten rather than added
            # to, exactly as `boost` does it, or one authored primitive shows up
            # in `sections` twice and every leg index after it moves, which is
            # what the closure solver keys its substitutions on.
            self.sections[-1] = {"t": "bounce", "len": length, "rise": rise}
        finally:
            self._cap = False
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
