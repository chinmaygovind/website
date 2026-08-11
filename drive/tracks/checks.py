"""What has to be true of any ribbon, whoever authored it.

Four questions, all of them derived from the station list rather than from what
the author thought they were doing - so a track cannot pass by declaring itself
fine, and a *new* track gets every one of them for free.

Every one exists because of a bug that made a track quietly unfinishable rather
than obviously broken, which is the only kind worth a check: `self_proximity`
because a turtle makes it easy to lay road back over road and a ground probe has
no good answer for which surface you are on; `pole_side` because the grid used to
alternate sides and put half of all pole positions on the outside of turn one;
`gate_ceiling` because a flat 5-unit window let a car fly over a checkpoint it
had driven through; `crossings` because the piers under a raised road have to
know what is above them.
"""

import math

from tracks.builder import STATION

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

