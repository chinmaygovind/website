"""Close a lap: make a ribbon come back to exactly where it started.

A track here is authored like directions given to somebody walking with their eyes
shut - *forward 200, turn 47 left, forward 330* - and for a **closed** track the
walk has to end on the spot it began, facing the same way, at the same height.
Nobody gets that right by eye. Off by three units and the road has a three-unit
step in it at the join, which is a wall you hit at 40 m/s; off by two degrees and
there is a kink; off by a metre of height and there is a jump nobody authored.

So the author lays out a loop that feels right, writes ``closed = True``, and this
closes it - by re-running ``build`` a handful of times with slightly different
numbers for one or two legs until the seam shuts. There is no tool to remember to
run and no solved constant to paste into a track file.

**Spa used to be the tool.** Its two long straights were solved offline by
`tools/close_spa.py` and the answers - 334.35 and 355.50 - were pasted into the
track as literals, with a docstring warning that changing *any* other length or
angle meant re-running it. That is the failure this replaces: the numbers were
right for exactly one set of numbers around them, and nothing checked.

What it costs
-------------
Almost nothing, for a reason worth knowing. With the corner angles held fixed, the
end position is an **exactly linear** function of the straight lengths, so Newton
converges in one step from any starting guess: measured on Spa, 4 to 8 ribbon
builds and 16-32ms, against a 2.4s pool import dominated by lap-time relaxation.
Freeing an angle as well makes it genuinely non-linear and costs a few more
iterations. Only closed tracks pay any of it.

What it will not do
-------------------
Quietly ruin a corner. `_spa`'s docstring records the first attempt at this
"[leaving] Stavelot as a 179-degree hairpin", and that is the failure mode of a
solver that reaches for whatever closes the equations. So:

* it prefers the legs where the change is least visible - the longest straights,
  the biggest-radius corner, the longest graded leg;
* every adjustment is bounded (`MAX_LEN_FRAC`, `MAX_DEG`, and a rise may not break
  the hill-easing rule and turn a hill into a kicker);
* if it cannot close inside those bounds it **raises**, naming the legs it tried,
  rather than shipping a track that is subtly wrong;
* and it reports every change it did make.
"""

import math

# How far a leg may be moved from what the author wrote.
#
# A straight is allowed a proportion, because 15% of a 350-unit blast down a hill
# is invisible and 15% of a 20-unit link between two corners is a different track.
MAX_LEN_FRAC = 0.15
# An angle is allowed an absolute amount, for the opposite reason: a degree is a
# degree whether the corner is a hairpin or a sweep, and eight of them is about
# where a named corner starts to stop being itself.
MAX_DEG = 8.0
# A rise is allowed this many units, on top of which it must still satisfy the
# hill-easing rule - see `_rise_cap`.
MAX_RISE = 12.0

# Closed to better than this and there is nothing to report: it is far below the
# 3.5-unit station spacing, so the join is smoother than the road either side.
QUIET = 0.01
# What counts as closed. Tight enough that nothing downstream can see the seam.
TOL = 1e-6
MAX_ITERS = 40


class CannotClose(ValueError):
    pass


def _wrap(a):
    """An angle difference in [-pi, pi].

    Heading closure is modulo a full turn: a lap that went round once and a lap
    that went round twice are both closed. Subtracting raw yaws would make the
    second look 360 degrees out.
    """
    return (a + math.pi) % (2 * math.pi) - math.pi


def _rise_cap(length):
    """The most a leg of this length may climb before it stops being a hill.

    ``length >= sqrt(330 * rise)`` is the rule `test_hills_are_eased_but_kickers_
    are_not` enforces: smoothstep peaks its vertical curvature at
    ``6*rise/length^2``, and staying under gravity at 40 u/s wants a radius of 55+.
    Inverted, that is the ceiling on rise. Without this the solver could close a
    lap's *height* by turning one hill into a jump.
    """
    return (length * length) / 330.0


def _residual(b, closes):
    """How far the walk is from having closed, in the order `closes` names."""
    start = b.nodes[0]["p"]
    out = []
    for what in closes:
        if what == "pos":
            out.append(b.x - start[0])
            out.append(b.z - start[2])
        elif what == "yaw":
            # `nodes[0]` has no stored yaw, so the start heading is taken from the
            # turtle's initial value, which `run` records before building.
            out.append(_wrap(b.yaw - b._yaw0))
        elif what == "y":
            out.append(b.y - start[1])
    return out


def _solve_linear(A, rhs):
    """Gaussian elimination with partial pivoting, for a 2x2 to 4x4."""
    n = len(rhs)
    M = [row[:] + [rhs[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-14:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def _describe(knob):
    """Name a leg the way an author can find it by counting down the file.

    `nth` is its position among primitives of its own kind - the 4th straight, the
    2nd corner - not among the solver's knobs. The difference matters: "gradient
    #4" meaning "the fourth thing I chose to adjust" is a label nobody can act on.
    """
    kind = {"len": "straight", "deg": "corner", "rise": "gradient on leg"}[knob["param"]]
    return "%s #%d" % (kind, knob["nth"])


def _nth(sections, index):
    """Which straight / corner / leg this is, counting from the top of `build`."""
    t = sections[index]["t"]
    same = ("straight", "boost") if t in ("straight", "boost") else (t,)
    return sum(1 for s in sections[:index + 1] if s["t"] in same)


def _pick(sections, closes, nominated):
    """Which legs to adjust, and in what order the residuals need them.

    One knob per residual. Position needs two, and they must not be parallel: two
    straights pointing the same way span a line rather than a plane, and the solve
    is singular. Spa's own note is that Kemmel and the Stavelot run "are the two
    long legs of the circuit's triangle, so they span the plane between them" -
    that is this choice, made rather than lucky.
    """
    straights = [(i, s) for i, s in enumerate(sections) if s["t"] in ("straight", "boost")]
    arcs = [(i, s) for i, s in enumerate(sections) if s["t"] == "arc"]
    knobs = []

    # `FREE()` marks, in the order the author wrote them. They are used first and
    # anything still needed is picked automatically, so a track can nominate the
    # two straights it cares about and leave the heading and the height alone -
    # which is exactly what Spa wants.
    taken = set()
    for i, param in (nominated or []):
        s = sections[i]
        base = s.get(param)
        if base is None:
            raise CannotClose(
                "FREE() on %s #%d marks `%s`, which that primitive does not have"
                % (s["t"], i, param))
        knobs.append({"i": i, "param": param, "nth": _nth(sections, i), "base": base,
                      "span": s["len"] if "len" in s
                      else math.radians(abs(s["deg"])) * s["rad"]})
        taken.add((i, param))

    def want(kind):
        """How many more knobs this residual needs, after the nominations."""
        have = sum(1 for k in knobs if k["param"] == kind)
        return {"len": 2 if "pos" in closes else 0,
                "deg": 1 if "yaw" in closes else 0,
                "rise": 1 if "y" in closes else 0}[kind] - have

    if want("len") > 0 and "pos" in closes:
        if len(straights) < 2:
            raise CannotClose(
                "a closed lap needs at least two straights for the solver to "
                "adjust; this one has %d" % len(straights))
        # Heading at the start of each straight, from the running sum of arcs
        # before it. Enough to tell parallel legs from crossed ones.
        head, headings = 0.0, {}
        for i, s in enumerate(sections):
            headings[i] = head
            if s["t"] == "arc":
                head += math.radians(s["deg"])
        free = [t for t in straights if (t[0], "len") not in taken]
        longest = sorted(free, key=lambda t: -t[1]["len"])[:8]
        best, pair = -1.0, None
        for a in range(len(longest)):
            for c in range(a + 1, len(longest)):
                ia, sa = longest[a]
                ic, sc = longest[c]
                # Long, and pointing in different directions. The product is what
                # keeps it from picking two long parallel straights or two short
                # perpendicular ones.
                score = (abs(math.sin(headings[ia] - headings[ic]))
                         * math.sqrt(sa["len"] * sc["len"]))
                if score > best:
                    best, pair = score, ((ia, sa), (ic, sc))
        if best <= 1e-6:
            raise CannotClose(
                "every straight on this closed lap points the same way, so no "
                "pair of them can close a position. Vary the layout, or nominate "
                "legs with FREE().")
        for i, s in pair[:want("len")]:
            knobs.append({"i": i, "param": "len", "nth": _nth(sections, i),
                          "base": s["len"], "span": s["len"]})

    if want("deg") > 0:
        arcs = [t for t in arcs if (t[0], "deg") not in taken]
        if not arcs:
            raise CannotClose("a closed lap with no corners cannot close a heading")
        # The biggest-radius corner: a fast sweep is the one whose exact angle
        # matters least to how the track drives, and half a degree on it is
        # invisible where half a degree on a hairpin's entry is not.
        i, s = max(arcs, key=lambda t: t[1]["rad"])
        knobs.append({"i": i, "param": "deg", "nth": _nth(sections, i),
                      "base": s["deg"],
                      "span": math.radians(abs(s["deg"])) * s["rad"]})

    if want("rise") > 0:
        graded = [(i, s) for i, s in enumerate(sections)
                  if s["t"] in ("straight", "boost", "arc")
                  and (i, "rise") not in taken]
        if not graded:
            raise CannotClose("nothing on this lap can carry a gradient")
        # The longest leg, graded or not: a metre spread over 90 units is a
        # gradient nobody notices, and the same metre over 20 is a bump.
        def span(s):
            return s["len"] if "len" in s else math.radians(abs(s["deg"])) * s["rad"]
        i, s = max(graded, key=lambda t: span(t[1]))
        knobs.append({"i": i, "param": "rise", "nth": _nth(sections, i),
                      "base": s.get("rise", 0.0), "span": span(s)})

    return knobs


def close(build, base_builder, closes=("pos", "yaw", "y")):
    """Adjust a few legs until the ribbon meets itself. Returns (builder, report).

    `build` is the track's own `build(b)`; `base_builder` makes a fresh Builder.
    Legs the author marked with `FREE()` are used before any are chosen
    automatically - see `_pick`.
    """
    def run(sub):
        b = base_builder()
        b._sub = dict(sub)
        got = build(b)
        return got if got is not None else b

    base = run({})
    shape = [s["t"] for s in base.sections]
    knobs = _pick(base.sections, closes, base._free)

    r0 = _residual(base, closes)
    if len(knobs) != len(r0):
        raise CannotClose(
            "%d things to close but %d legs to close them with. Closing %r needs "
            "%d free legs; nominate them with FREE() if the automatic choice "
            "cannot find enough." % (len(r0), len(knobs), list(closes), len(r0)))

    if max((abs(v) for v in r0), default=0.0) < TOL:
        return base, []

    p = [k["base"] for k in knobs]

    def at(vals):
        b = run({(k["i"], k["param"]): v for k, v in zip(knobs, vals)})
        if [s["t"] for s in b.sections] != shape:
            raise CannotClose(
                "this track's `build` changes which primitives it lays depending "
                "on their values, so the solver cannot address a leg by position. "
                "Author the loop without branching on geometry.")
        return b

    last = None
    for _ in range(MAX_ITERS):
        b = at(p)
        r = _residual(b, closes)
        last = max(abs(v) for v in r)
        if last < TOL:
            break
        # Finite-difference Jacobian, one column per knob. The step is scaled to
        # each knob because they are in different units - hundreds of units of
        # length beside tens of degrees.
        cols = []
        for k in range(len(p)):
            h = max(1e-4, abs(p[k]) * 1e-5)
            q = list(p)
            q[k] += h
            rq = _residual(at(q), closes)
            cols.append([(rq[i] - r[i]) / h for i in range(len(r))])
        A = [[cols[k][i] for k in range(len(p))] for i in range(len(r))]
        step = _solve_linear(A, [-v for v in r])
        if step is None:
            raise CannotClose(
                "the legs picked to close this lap do not independently affect "
                "it (singular Jacobian): %s. Nominate different ones with FREE()."
                % ", ".join(_describe(k) for k in knobs))
        p = [p[k] + step[k] for k in range(len(p))]
    else:
        raise CannotClose(
            "could not close this lap: still %.4f out after %d attempts, "
            "adjusting %s." % (last, MAX_ITERS,
                               ", ".join(_describe(k) for k in knobs)))

    # ---- guards, after the solve and before anyone drives it ----------------
    for k, v in zip(knobs, p):
        if k["param"] == "len":
            if v <= 0:
                raise CannotClose(
                    "closing this lap needs %s to be %.1f units long, which is "
                    "not a straight. The layout cannot close as authored."
                    % (_describe(k), v))
            moved = abs(v - k["base"]) / max(1e-9, abs(k["base"]))
            if moved > MAX_LEN_FRAC:
                raise CannotClose(
                    "closing this lap needs %s changed from %.1f to %.1f (%.0f%%, "
                    "over the %.0f%% a straight is allowed). The layout is too far "
                    "from closing for the solver to hide the difference - move a "
                    "corner, or nominate a longer straight with FREE()."
                    % (_describe(k), k["base"], v, moved * 100, MAX_LEN_FRAC * 100))
        elif k["param"] == "deg":
            if abs(v - k["base"]) > MAX_DEG:
                raise CannotClose(
                    "closing this lap needs %s changed from %.1f to %.1f degrees, "
                    "more than the %.0f a corner is allowed to move. That is how "
                    "an early attempt at Spa turned Stavelot into a 179-degree "
                    "hairpin. Adjust the angles so they nearly close, or nominate "
                    "a different corner." % (_describe(k), k["base"], v, MAX_DEG))
        elif k["param"] == "rise":
            if abs(v - k["base"]) > MAX_RISE:
                raise CannotClose(
                    "closing this lap needs %s changed from %.1f to %.1f units of "
                    "climb, more than the %.0f allowed. Make the authored rises "
                    "nearly cancel." % (_describe(k), k["base"], v, MAX_RISE))
            cap = _rise_cap(k.get("span", 1.0))
            if abs(v) > cap:
                raise CannotClose(
                    "closing this lap needs %s to climb %.1f units over %.0f, "
                    "which is a kicker rather than a hill (the limit is %.1f). "
                    "Lengthen that leg, or spread the climb over more of the lap."
                    % (_describe(k), v, k.get("span", 0.0), cap))

    final = at(p)
    report = []
    for k, v in zip(knobs, p):
        if abs(v - k["base"]) >= QUIET:
            report.append({"leg": _describe(k), "param": k["param"],
                           "was": round(k["base"], 3), "now": round(v, 3)})
    return final, report
