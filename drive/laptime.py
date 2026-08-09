"""Simulate a near-perfect lap so medal times can be derived, not guessed.

Hand-picking medal times means driving every track dozens of times and redoing
it whenever the car is retuned. Instead this module does what a lap-time
simulator does:

1. **Find a racing line.** Relax the road centreline toward minimum curvature,
   clamped to stay inside the road. On a 13-wide road that opens a 30-unit
   centreline corner out to nearer 40, which is the difference between taking it
   at 23 u/s and taking it at 27 - and on a chicane it is the difference between
   two corners and one straight line.
2. **Find the speed limit at every point** from its curvature, inverted through
   the car's own speed-dependent yaw rate: the fastest v where ``v / omega(v)``
   still fits the corner radius.
3. **Join the limits up** with a backward braking pass and a forward
   acceleration pass, both including the gravity component along the slope, then
   integrate ``ds / v``.

It reads its constants from ``tuning``, so retuning the car retunes the medals.
The result is an *ideal* lap - cleaner than a human will drive - which is why
``MEDAL_MULT["gold"]`` sits just above 1.0 and the other medals are multiples
of it.
"""

import math

import tuning as T


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dist(a, b):
    d = _sub(a, b)
    return math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])


def _rise_at(pf, u):
    """Interpolate a station's baked cross-section samples at lateral ``u``.

    Reads the samples rather than re-deriving the curve. ``tracks`` imports this
    module at the foot of itself to get the medal times, so importing its
    ``rise_at`` back would be a cycle - and reading the same baked numbers is
    what stops the two answers differing anyway.
    """
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


def _omega(v):
    """Yaw rate the car can sustain at speed v - the same lerp the JS uses."""
    t = min(1.0, max(0.0, v / T.MAX_SPEED))
    return T.STEER_RATE_LOW + (T.STEER_RATE_HIGH - T.STEER_RATE_LOW) * t


def _corner_speed(radius, top=None):
    """Fastest v whose turn radius v/omega(v) still fits ``radius``.

    v/omega(v) increases monotonically with v (omega falls as v rises), so a
    bisection is exact and needs no care about local minima.

    ``top`` is the ceiling to search up to, and it exists because of the boost
    pads: it used to be ``MAX_SPEED`` unconditionally, which meant a station
    with a boosted cap still came out of here at exactly ``MAX_SPEED`` and the
    whole pad was silently thrown away on every straight - the one place a pad
    is ever put. ``_omega`` clamps its lerp at ``MAX_SPEED``, so above it the
    yaw rate simply stays at ``STEER_RATE_HIGH`` and the radius keeps opening
    out, which is what the car itself does (``steerRate`` in physics.js).
    """
    if top is None:
        top = T.MAX_SPEED
    if radius <= 0 or radius > 1e5:
        return top
    lo, hi = 0.0, top
    if lo / _omega(lo) > radius:
        return 0.5
    if hi / _omega(hi) <= radius:
        return top
    for _ in range(40):
        mid = (lo + hi) / 2
        if mid / _omega(mid) <= radius:
            lo = mid
        else:
            hi = mid
    return lo


def racing_line(line, iterations=320, relax=0.34, margin=2.4):
    # `margin` is how close the line may come to the edge of the road. It cannot
    # be zero: the car has width, so its centre line has to stay about a
    # half-width off the kerb, and a driver needs a little more than that again.
    # Too small a margin produces a line whose corner radii are only achievable
    # with perfect placement, and the derived corner speeds are then higher than
    # anything with tracking error can hold.
    """Relax the centreline toward minimum curvature, staying on the road.

    Each point may only slide along its own lateral vector (across the road), so
    the line can never leave the track no matter how many iterations run. Air
    and ``fix`` sections are pinned: you cannot choose a line mid-flight, and
    inside a corkscrew the line is fixed by the geometry.

    Where the road has a cross-section - a half-pipe, a banked wall - sliding
    sideways also means climbing, so the point is lifted onto the surface by the
    station's own samples. Leaving it on the floor plane would measure a corner
    radius along a road that is not there, and the whole reason to relax the
    line at all is to measure the one that is.
    """
    pts = [list(e["p"]) for e in line]
    n = len(pts)
    if n < 3:
        return pts
    off = [0.0] * n
    pinned = [bool(e.get("air") or e.get("fix")) for e in line]
    base = [list(e["p"]) for e in line]
    lat = [e["lat"] for e in line]
    nrm = [e["n"] for e in line]
    hw = [e["hw"] for e in line]
    prof = [e.get("pf") for e in line]
    lim = [max(0.0, e["hw"] - margin) for e in line]

    def place(i, o):
        p = [base[i][k] + lat[i][k] * o for k in range(3)]
        if prof[i] and hw[i] > 0:
            r = _rise_at(prof[i], o / hw[i])
            if r:
                p = [p[k] + nrm[i][k] * r for k in range(3)]
        return p

    for _ in range(iterations):
        new = list(off)
        for i in range(1, n - 1):
            if pinned[i]:
                new[i] = 0.0
                continue
            # Where would this point have to move to sit exactly between its
            # neighbours? Project that onto its lateral axis and step toward it.
            mid = [(pts[i - 1][k] + pts[i + 1][k]) / 2 for k in range(3)]
            d = _sub(mid, pts[i])
            along = d[0] * lat[i][0] + d[1] * lat[i][1] + d[2] * lat[i][2]
            o = off[i] + relax * along
            new[i] = max(-lim[i], min(lim[i], o))
        off = new
        for i in range(n):
            pts[i] = place(i, off[i])
    return pts


def _curvature_radius(a, b, c):
    """Circumradius of three points; huge if they are nearly collinear."""
    ab, bc, ca = _dist(a, b), _dist(b, c), _dist(c, a)
    if ab < 1e-6 or bc < 1e-6 or ca < 1e-6:
        return 1e6
    # area via Heron, guarded against tiny negative values from rounding
    s = (ab + bc + ca) / 2
    h = s * (s - ab) * (s - bc) * (s - ca)
    if h <= 1e-9:
        return 1e6
    area = math.sqrt(h)
    return (ab * bc * ca) / (4 * area)


def _station(line):
    """Mean spacing between stations, for sizing the curvature stencil."""
    if len(line) < 2:
        return 1.0
    total = sum(_dist(line[i]["p"], line[i + 1]["p"]) for i in range(len(line) - 1))
    return total / (len(line) - 1)


def _boost_window(line, ds, v):
    """Which stations the car is still carrying a boost pad's help at.

    A pad arms the boost for ``PAD_BOOST`` seconds (physics.js), so how far up
    the road it reaches is a question about *time*, and the answer depends on
    how fast the car is going - which is what this module is working out. Hence
    the loop in ``speed_profile``: solve with no boost, ask this where the boost
    then reaches, solve again. It settles in one refinement because the window
    is a second and a bit either way.

    A track with no pads gets a window of all-False from the first call, which
    equals the mask it started with, so the loop stops after one pass and every
    medal time on the existing pool is the number it always was.
    """
    n = len(line)
    left = 0.0
    out = []
    for i in range(n):
        if line[i].get("bp"):
            left = T.PAD_BOOST
        out.append(left > 0.0)
        if i < n - 1 and ds[i] > 1e-6:
            left = max(0.0, left - ds[i] / max(0.5, (v[i] + v[i + 1]) / 2))
    return out


def speed_profile(track):
    """Return (points, speeds, ideal_time) for the track's racing line."""
    line = track["line"]
    pts = racing_line(line)
    n = len(pts)
    if n < 3:
        return pts, [T.MAX_SPEED] * n, 0.0

    ds = [0.0] * n           # segment length from i to i+1
    for i in range(n - 1):
        ds[i] = _dist(pts[i], pts[i + 1])

    # Curvature is measured across a stencil about eight units wide rather than
    # between neighbouring stations. Stations are only ~3.5 units apart, and a
    # three-point circumradius over that short a baseline is dominated by the
    # relaxation's own residual wobble - it reported hairpin radii on straights.
    stride = max(1, int(round(8.0 / max(1e-6, _station(line)))))

    def slope(i):
        """Gravity component along the direction of travel at point i."""
        j = min(i + 1, n - 1)
        seg = ds[i] if ds[i] > 1e-6 else (ds[j] if ds[j] > 1e-6 else 1e-6)
        dy = pts[j][1] - pts[i][1]
        return -T.GRAVITY * (dy / seg)

    def solve(boost):
        """The three passes, given where a boost pad's help is live.

        ``boost`` lifts two different things and it has to lift both. The engine
        term is the obvious one; the speed *cap* is the one that is easy to
        miss, because a boost is more engine rather than a raised limit and the
        limit is still where ACCEL fights DRAG - a car with 1.7 times the engine
        settles at sqrt(1.7) times the top speed, and capping it at MAX_SPEED
        would quietly throw the whole pad away on any straight long enough to
        use it.
        """
        cap = []
        for i in range(n):
            e = line[i]
            top = T.MAX_SPEED * math.sqrt(T.PAD_ACCEL_MULT) if boost[i] else T.MAX_SPEED
            if e.get("air"):
                cap.append(top)          # no steering authority matters mid-flight
            elif e.get("crad"):
                # A corkscrew. Its curvature is not something you steer, so the
                # limit is not the yaw rate - it is whether the car can be held
                # onto the wall at all. On the wall gravity points along the road
                # rather than into it, so STICK_FORCE is the whole centripetal
                # budget.
                cap.append(min(top, math.sqrt(e["crad"] * T.STICK_FORCE)))
            elif e.get("fix"):
                cap.append(top)
            elif i - stride < 0 or i + stride >= n:
                cap.append(top)
            else:
                r = _curvature_radius(pts[i - stride], pts[i], pts[i + stride])
                cap.append(_corner_speed(r, top))

        v = list(cap)
        v[0] = 0.0               # standing start

        # Backward pass: never arrive at a corner faster than you can brake to.
        for i in range(n - 2, -1, -1):
            if ds[i] < 1e-6:
                continue
            decel = T.BRAKE - slope(i)
            if decel < 2.0:
                decel = 2.0
            reachable = math.sqrt(max(0.0, v[i + 1] ** 2 + 2 * decel * ds[i]))
            v[i] = min(v[i], reachable)

        # Forward pass: and never leave one faster than the engine can pull.
        for i in range(1, n):
            if ds[i - 1] < 1e-6:
                continue
            u = v[i - 1]
            if line[i - 1].get("air"):
                a = slope(i - 1)             # coasting through the air
            else:
                eng = T.ACCEL * (T.PAD_ACCEL_MULT if boost[i - 1] else 1.0)
                a = eng - T.DRAG * u * u + slope(i - 1)
            reachable = math.sqrt(max(0.0, u * u + 2 * max(a, -T.BRAKE) * ds[i - 1]))
            v[i] = min(v[i], reachable)
            if v[i] < 0.5:
                v[i] = 0.5
        return v

    boost = [False] * n
    v = solve(boost)
    for _ in range(3):
        nxt = _boost_window(line, ds, v)
        if nxt == boost:
            break
        boost = nxt
        v = solve(boost)

    total = 0.0
    for i in range(n - 1):
        if ds[i] < 1e-6:
            continue
        total += ds[i] / max(0.5, (v[i] + v[i + 1]) / 2)
    return pts, v, total


# The quasi-static model above is not the same thing as a driven lap: it holds one
# fixed line, brakes to the corner speed before every apex, and never uses a kerb,
# a drift or a rail to carry more speed - but it also assumes perfect placement,
# which no driver manages. Driving every track through the real physics with a
# headless autopilot came out a consistent ~11% *slower* than this predicts, so
# the raw estimate is scaled to match measured reality before the medals are cut
# from it.
#
# **Nothing pins this any more.** The autopilot was deleted along with
# `tests/test_sim.py`, because requiring a clean lap from a simulated driver is a
# ceiling on how mean a track is allowed to be, and that is a decision for the
# track rather than for the test suite. What went with it is this number's only
# guardian: retune the car enough and the medals drift away from what is
# achievable, silently. The check that replaces it is the one that was always the
# real one - `MEDAL_MULT` is calibrated against times people have actually set
# (see tuning.py), and every record on the site sitting between 0.77 and 0.90 of
# `ideal` is what says this figure is still about right.
CALIBRATION = 1.115


def ideal_lap(track):
    """Time a good driver should expect on this track, in seconds."""
    return round(speed_profile(track)[2] * CALIBRATION, 3)


def raw_lap(track):
    """The uncalibrated quasi-static estimate, for the calibration test."""
    return round(speed_profile(track)[2], 3)


def medals(ideal):
    return {k: round(ideal * m, 2) for k, m in T.MEDAL_MULT.items()}


def line_length(track):
    pts = [e["p"] for e in track["line"]]
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
