"""Simulate a near-perfect lap so medal times can be derived, not guessed.

Hand-picking medal times means driving every track dozens of times and redoing
it whenever the car is retuned. Instead this module does what a lap-time
simulator does:

1. **Find a racing line.** Relax the road centreline toward minimum curvature,
   clamped to stay inside the road. That is what turns a 90 degree corner from a
   4-unit-radius centreline hairpin into the ~19-unit-radius line a driver
   actually takes, which is the difference between a corner taken at 12 u/s and
   one taken at 33.
2. **Find the speed limit at every point** from its curvature, inverted through
   the car's own speed-dependent yaw rate: the fastest v where ``v / omega(v)``
   still fits the corner radius.
3. **Join the limits up** with a backward braking pass and a forward
   acceleration pass, both including the gravity component along the slope, then
   integrate ``ds / v``.

It reads its constants from ``tuning``, so retuning the car retunes the medals.
The result is an *ideal* lap - cleaner than a human will drive - which is why
``MEDAL_MULT["author"]`` sits at 1.0 and the other medals are multiples of it.
"""

import math

import tuning as T


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dist(a, b):
    d = _sub(a, b)
    return math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])


def _omega(v):
    """Yaw rate the car can sustain at speed v - the same lerp the JS uses."""
    t = min(1.0, max(0.0, v / T.MAX_SPEED))
    return T.STEER_RATE_LOW + (T.STEER_RATE_HIGH - T.STEER_RATE_LOW) * t


def _corner_speed(radius):
    """Fastest v whose turn radius v/omega(v) still fits ``radius``.

    v/omega(v) increases monotonically with v (omega falls as v rises), so a
    bisection is exact and needs no care about local minima.
    """
    if radius <= 0 or radius > 1e5:
        return T.MAX_SPEED
    lo, hi = 0.0, T.MAX_SPEED
    if lo / _omega(lo) > radius:
        return 0.5
    if hi / _omega(hi) <= radius:
        return T.MAX_SPEED
    for _ in range(40):
        mid = (lo + hi) / 2
        if mid / _omega(mid) <= radius:
            lo = mid
        else:
            hi = mid
    return lo


def racing_line(line, iterations=260, relax=0.34, margin=2.4):
    # `margin` is how close the line may come to the edge of the road. It cannot
    # be zero: the car has width, so its centre line has to stay about a
    # half-width off the kerb, and a driver needs a little more than that again.
    # Too small a margin produces a line whose corner radii are only achievable
    # with perfect placement, and the derived corner speeds are then higher than
    # anything with tracking error can hold.
    """Relax the centreline toward minimum curvature, staying on the road.

    Each point may only slide along its own lateral vector (across the road), so
    the line can never leave the track no matter how many iterations run. Air
    and loop sections are pinned: you cannot choose a line mid-flight, and a
    loop's line is fixed by the geometry.
    """
    pts = [list(e["p"]) for e in line]
    n = len(pts)
    if n < 3:
        return pts
    off = [0.0] * n
    pinned = [bool(e.get("air") or e.get("loop")) for e in line]
    base = [list(e["p"]) for e in line]
    lat = [e["lat"] for e in line]
    lim = [max(0.0, e["hw"] - margin) for e in line]

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
            pts[i] = [base[i][k] + lat[i][k] * off[i] for k in range(3)]
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

    cap = []
    for i in range(n):
        e = line[i]
        top = T.BOOST_SPEED if e.get("boost") else T.MAX_SPEED
        if e.get("air"):
            cap.append(top)          # no steering authority matters mid-flight
        elif e.get("loop"):
            cap.append(top)          # a loop's curvature is pitch, not yaw
        elif i == 0 or i == n - 1:
            cap.append(top)
        else:
            r = _curvature_radius(pts[i - 1], pts[i], pts[i + 1])
            cap.append(min(top, _corner_speed(r)))

    v = list(cap)
    v[0] = 0.0               # standing start

    def slope(i):
        """Gravity component along the direction of travel at point i."""
        j = min(i + 1, n - 1)
        seg = ds[i] if ds[i] > 1e-6 else (ds[j] if ds[j] > 1e-6 else 1e-6)
        dy = pts[j][1] - pts[i][1]
        return -T.GRAVITY * (dy / seg)

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
            a = T.ACCEL - T.DRAG * u * u + slope(i - 1)
        reachable = math.sqrt(max(0.0, u * u + 2 * max(a, -T.BRAKE) * ds[i - 1]))
        v[i] = min(v[i], reachable)
        if v[i] < 0.5:
            v[i] = 0.5

    total = 0.0
    for i in range(n - 1):
        if ds[i] < 1e-6:
            continue
        total += ds[i] / max(0.5, (v[i] + v[i + 1]) / 2)
    return pts, v, total


# The quasi-static model above is not the same thing as a driven lap: it holds one
# fixed line, brakes to the corner speed before every apex, and never uses a kerb,
# a drift or a rail to carry more speed - but it also assumes perfect placement,
# which no driver manages. Driving all nine tracks through the real physics with
# the headless autopilot (tests/test_sim.py) came out a consistent ~11% *slower*
# than this predicts, so the raw estimate is scaled to match measured reality
# before the medals are cut from it.
#
# `test_sim.py::test_ideal_lap_matches_the_simulated_driver` pins this ratio, so
# if the car is retuned enough to move it, the tests say so instead of the medal
# times quietly drifting away from what is achievable.
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
