"""Structural tests on the track pool.

Every failure mode in here is one that actually happened while the pool was being
authored, and each one made a track quietly unfinishable rather than obviously
broken - which is exactly the kind of thing a test should be holding down.
"""

import math
import re
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import laptime
import tracks as tracks_mod
import tuning as T

ALL = tracks_mod.TRACKS
IDS = [t["slug"] for t in ALL]
STATION = tracks_mod.STATION


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_track_is_well_formed(track):
    assert track["spawn"], "no start block"
    assert track["checkpoints"] >= 1
    kinds = [g["kind"] for g in track["gates"]]
    assert kinds.count("start") == 1 and kinds.count("finish") == 1
    cps = {g["gi"] for g in track["gates"] if g["kind"] == "cp"}
    # checkpoint indices are 1..n with no gaps, which is what the in-order
    # crossing check in course.js assumes
    assert cps == set(range(1, track["checkpoints"] + 1))
    # the start has to come first and the finish last, along the road
    order = [g["si"] for g in track["gates"]]
    if track.get("closed"):
        # On a ring the finish IS the start - same station, same plane - so the
        # gates cannot be in increasing station order and should not be. What
        # still has to hold is that the checkpoints between them are.
        start = next(g for g in track["gates"] if g["kind"] == "start")
        fin = next(g for g in track["gates"] if g["kind"] == "finish")
        assert fin["si"] == start["si"], "a closed lap must finish where it started"
        assert fin["p"] == start["p"] and fin["f"] == start["f"]
        mid = [g["si"] for g in track["gates"] if g["kind"] == "cp"]
        assert mid == sorted(mid) and mid[0] > start["si"]
    else:
        assert order == sorted(order)


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_stations_are_a_continuous_ribbon(track):
    """Every station has an orthonormal frame and joins the previous one.

    A discontinuity here is a hole in the road that would only show up as the car
    falling through the world, so it is worth checking directly.
    """
    line = track["line"]
    assert len(line) > 40
    for i, e in enumerate(line):
        n, lat = e["n"], e["lat"]
        assert abs(math.hypot(*n) - 1) < 1e-3, f"station {i} normal is not unit"
        assert abs(math.hypot(*lat) - 1) < 1e-3, f"station {i} lat is not unit"
        assert abs(sum(n[k] * lat[k] for k in range(3))) < 1e-3, \
            f"station {i} normal and lat are not perpendicular"
        assert e["hw"] > 2.0
        if i:
            d = math.dist(e["p"], line[i - 1]["p"])
            assert d < STATION * 3, f"a {d:.1f}-unit hole between stations {i-1} and {i}"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_track_does_not_run_too_close_to_itself(track):
    """Two road surfaces a couple of units apart is a car trap, not a crossing.

    This one check replaces every per-shape rule the old grid version needed. It
    holds for corners, hills, gaps and corkscrews alike, which is the whole
    argument for having one geometry primitive instead of six.
    """
    bad = tracks_mod.self_proximity(track)
    assert not bad, f"{track['slug']} runs into itself: {bad[:4]}"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_every_gate_sits_on_the_racing_line(track):
    """A gate the driving line does not pass through can never be crossed.

    The line is the relaxed racing line, not the centreline, because that is what
    a driver actually follows - a gate placed just before a corner gets cut and
    missed, which is how four tracks were briefly unfinishable.
    """
    pts, _, _ = laptime.speed_profile(track)
    for g in track["gates"]:
        p, r = g["p"], g["r"]
        near = min(pts, key=lambda q: sum((q[i] - p[i]) ** 2 for i in range(3)))
        lx = (near[0] - p[0]) * r[0] + (near[2] - p[2]) * r[2]
        dy = near[1] - p[1]
        label = f"{track['slug']} {g['kind']}{g['gi'] or ''}"
        assert abs(lx) <= g["hw"] + 2.5, f"{label}: line passes {lx:.1f} wide of it"
        assert -2.5 < dy < 5.0, f"{label}: line passes {dy:.1f} above/below it"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_gates_have_straight_road_either_side(track):
    """Ten units of straight, flat, solid road before and after every gate.

    The racing line through a corner cuts across the stations next to it, so a
    gate needs a settled run at it or the line misses its mouth entirely.
    """
    line = track["line"]
    span = int(round(10.0 / STATION))
    for g in track["gates"]:
        si = g["si"]
        lo = max(0, si - span) if g["kind"] != "start" else si
        for j in range(lo, min(len(line), si + span + 1)):
            e = line[j]
            label = f"{track['slug']} {g['kind']}{g['gi'] or ''}"
            assert not e.get("air"), f"{label}: a gap runs through it"
            assert not e.get("curv"), f"{label}: a corner runs through it"
            assert e["n"][1] > 0.9, f"{label}: the road is banked or pitched under it"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_corner_radii_are_varied_and_drivable(track):
    """The complaint that started the rewrite: every corner being the same corner.

    The grid version could only make one shape - a 90-degree tile whose
    centreline radius was four units. Now radius is a free parameter, so assert
    the pool actually uses it: nothing tighter than a hairpin the car can hold,
    and a real spread of radii on every track.
    """
    radii = sorted({round(abs(1.0 / e["curv"]), 1)
                    for e in track["line"] if e.get("curv")})
    assert radii, f"{track['slug']} has no corners at all"
    assert radii[0] >= 12.0, f"{track['slug']} has a {radii[0]:.0f}-unit corner"
    assert len(radii) >= 4, f"{track['slug']} only uses radii {radii}"
    assert radii[-1] / radii[0] > 1.8, \
        f"{track['slug']} corners are all much the same: {radii}"


# Smallest vertical curvature radius a *hill* may have. Below this the road
# falls away from the car faster than gravity can pull it down and the crest
# throws it, which is a fine thing for a jump to do and a terrible thing for a
# hill to do by accident. 55 units keeps a crest taken at 40 u/s inside
# v^2/r < GRAVITY; a `kick` is exempt because launching is its entire job.
MIN_CREST_RADIUS = 55.0


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_hills_are_eased_but_kickers_are_not(track):
    """A hill must not have a crease in it, or it launches the car by accident.

    `straight(l, rise=r)` smoothsteps its grade so the road meets the flat at
    each end with no crease at all. `crest` and `jump` deliberately do not, and
    mark their stations `kick`. This is the test that separates the two, and it
    is expressed as a real vertical curvature radius rather than a fudge factor
    so the number means something: at 40 u/s, v^2/r has to stay under gravity.
    """
    line = track["line"]
    for i in range(1, len(line) - 1):
        window = line[max(0, i - 2):i + 3]
        if any(e.get("air") or e.get("fix") or e.get("kick") for e in window):
            continue
        prev, a, b = line[i - 1], line[i], line[i + 1]
        d0 = math.dist(prev["p"], a["p"]) or 1e-6
        d1 = math.dist(a["p"], b["p"]) or 1e-6
        ga = (a["p"][1] - prev["p"][1]) / d0
        gb = (b["p"][1] - a["p"][1]) / d1
        kappa = abs(gb - ga) / ((d0 + d1) / 2)
        if kappa < 1e-9:
            continue
        radius = 1.0 / kappa
        assert radius >= MIN_CREST_RADIUS, (
            f"{track['slug']}: station {i} is a {radius:.0f}-unit vertical crease - "
            f"a hill needs {MIN_CREST_RADIUS:.0f}+ or it launches the car")


def _loop_runs(line):
    """Index ranges of each loop, found by the radius its stations carry."""
    runs, cur = [], []
    for i, e in enumerate(line):
        if e.get("crad"):
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_loops_invert_and_step_aside(track):
    """What makes a loop buildable at all.

    A plain vertical loop returns to exactly where it started, so the bottom of
    the descent lands on the bottom of the climb - two surfaces a metre apart,
    which is a car trap rather than a loop. Sliding the exit sideways is the
    whole trick, and this checks it really happens: the loop goes fully inverted
    over the top, and its two ends are more than a road's width apart.
    """
    line = track["line"]
    for run in _loop_runs(line):
        entry, exit_ = line[run[0] - 1], line[run[-1]]
        label = f"{track['slug']} loop at {run[0]}"
        assert min(line[i]["n"][1] for i in run) < -0.95, \
            f"{label} never goes properly inverted"
        assert max(line[i]["p"][1] for i in run) - entry["p"][1] > \
            line[run[0]]["crad"] * 1.7, f"{label} does not go over the top"
        apart = math.hypot(exit_["p"][0] - entry["p"][0],
                           exit_["p"][2] - entry["p"][2])
        assert apart > entry["hw"] * 2 + 6, \
            f"{label}: entry and exit are only {apart:.1f} apart"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_loops_join_the_road_tangentially(track):
    """The failure that made the first attempt at this undrivable.

    A helix about the direction of travel looks like the obvious way to build a
    corkscrew, but its tangent sits permanently off its own axis - 55 degrees for
    a radius-20, one-turn helix - so it meets the straight road before it at a
    kink, and the car drives into the barrier instead of round the loop. The
    speed trace showed 43 u/s becoming 8 in a tenth of a second. A vertical
    circle enters and leaves along the direction of travel, and the sideways
    slide is smoothstepped so it contributes nothing at either end. This checks
    both joins.
    """
    line = track["line"]
    for run in _loop_runs(line):
        for a, b, where in ((line[run[0] - 1], line[run[0]], "entry"),
                            (line[run[-1]], line[min(run[-1] + 1, len(line) - 1)],
                             "exit")):
            d = [b["p"][k] - a["p"][k] for k in range(3)]
            m = math.hypot(*d) or 1.0
            fa = [a["n"][1] * a["lat"][2] - a["n"][2] * a["lat"][1],
                  a["n"][2] * a["lat"][0] - a["n"][0] * a["lat"][2],
                  a["n"][0] * a["lat"][1] - a["n"][1] * a["lat"][0]]
            dot = sum(d[k] / m * fa[k] for k in range(3))
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            assert angle < 14, (
                f"{track['slug']}: the loop meets the road at a {angle:.0f} degree "
                f"kink on {where} - the car will hit the barrier, not the loop")


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_every_gap_is_clearable(track):
    """Ballistics on the speed the lap sim says you arrive at the lip with."""
    pts, speeds, _ = laptime.speed_profile(track)
    line = track["line"]
    for i, e in enumerate(line):
        if not e.get("air") or (i and line[i - 1].get("air")):
            continue                      # only the first station of each gap
        j = i
        while j < len(line) and line[j].get("air"):
            j += 1
        span = math.dist(line[i - 1]["p"], line[min(j, len(line) - 1)]["p"])
        v = speeds[max(0, i - 1)]
        # The kicker's grade at the lip sets the launch angle.
        lip, before = line[i - 1]["p"], line[max(0, i - 2)]["p"]
        run = math.hypot(lip[0] - before[0], lip[2] - before[2]) or 1e-6
        theta = math.atan2(lip[1] - before[1], run)
        drop = max(0.0, lip[1] - line[min(j, len(line) - 1)]["p"][1])
        # range of a projectile launched at theta, landing `drop` lower
        vx, vy = v * math.cos(theta), v * math.sin(theta)
        flight = (vy + math.sqrt(max(0.0, vy * vy + 2 * T.GRAVITY * drop))) / T.GRAVITY
        reach = vx * flight
        assert reach >= span * 0.9, (
            f"{track['slug']}: a {span:.0f}-unit gap entered at {v:.0f} u/s "
            f"only carries {reach:.0f} units")


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_medal_times_are_ordered_and_reachable(track):
    m = track["medals"]
    assert "author" not in m, "the author medal is retired - gold is the best one"
    assert m["gold"] < m["silver"] < m["bronze"]
    assert 8 < track["ideal"] < 120, "ideal lap outside a sane range"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_the_three_medals_are_close_together(track):
    """One standard in three steps, not three unrelated ones.

    They used to be 1.04 / 1.18 / 1.42 of the ideal lap, which put gold to
    silver 2.8-5.7s apart and silver to bronze 4.8-9.7s apart - on a twenty
    second track, bronze was half a lap slower than gold. A step is now under
    a tenth of the lap, which is a second or two on most of the pool.
    """
    m, ideal = track["medals"], track["ideal"]
    for a, b in (("gold", "silver"), ("silver", "bronze")):
        step = m[b] - m[a]
        assert step < ideal * 0.09, \
            f"{a} to {b} is {step:.2f}s on a {ideal:.1f}s lap - too far apart"
        assert step > 0.4, f"{a} and {b} are {step:.2f}s apart - indistinguishable"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_gold_is_faster_than_the_estimate(track):
    """Every record actually set on the site is 0.77-0.90 of `ideal`, so a gold
    at or above 1.0 was slower than what people were already driving - which is
    what made the old 1.04 gold trivial. It has to be under the estimate."""
    assert track["medals"]["gold"] < track["ideal"], \
        "gold must ask for more than the relaxed-racing-line estimate"


@pytest.mark.parametrize("track", [t for t in ALL if t.get("closed")],
                         ids=[t["slug"] for t in ALL if t.get("closed")])
def test_a_closed_lap_actually_closes(track):
    """A ring has to meet itself, in all three axes and in heading.

    Spa's two free straights are solved offline (``tools/close_spa.py``) and the
    answer is baked into ``_spa``'s defaults, so nothing at import time would
    notice them drifting apart - and the failure is quiet and nasty. A ribbon
    that misses its own start by a few units is a step in the road you fall
    down; miss it by sixty and the finish line is in a field. Every length and
    angle in the track feeds these numbers, so this is the test that says
    "re-run the solver".
    """
    line = track["line"]
    a, b = line[0], line[-1]
    gap = math.dist(a["p"], b["p"])
    assert gap < 1.0, (
        "%s does not close: its ends are %.2f units apart. Re-run "
        "tools/close_spa.py and paste the numbers into the builder."
        % (track["slug"], gap))
    # ...and arrives pointing the way it left, or the join is a kink.
    fa = [a["p"][k] - line[1]["p"][k] for k in (0, 2)]
    fb = [line[-2]["p"][k] - b["p"][k] for k in (0, 2)]
    na = math.hypot(*fa) or 1.0
    nb = math.hypot(*fb) or 1.0
    cos = (fa[0] * fb[0] + fa[1] * fb[1]) / (na * nb)
    assert cos > 0.999, "%s closes at a kink (%.2f deg)" % (
        track["slug"], math.degrees(math.acos(max(-1, min(1, cos)))))
    # The finish gate is the start gate, which is what makes it one lap.
    kinds = {g["kind"]: g for g in track["gates"] if g["kind"] in ("start", "finish")}
    assert kinds["finish"]["p"] == kinds["start"]["p"]


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_barriers_are_opt_in(track):
    """Rails on every corner look like a bobsleigh run and remove the only
    interesting decision on a corner exit. Ground-level tracks get none."""
    line = track["line"]
    walled = sum(1 for e in line if e.get("wl") or e.get("wr"))
    if track["ground"] is not None:
        assert walled == 0, \
            f"{track['slug']} sits on the ground but has {walled} walled stations"
    elif track["exposed"]:
        # A track may declare that falling off is the point rather than a gap in
        # its barriers - but then it has to actually be exposed. A track wearing
        # the flag with rails all down it is as wrong as a normal floating track
        # without them, and it is the more likely mistake of the two: the flag
        # stays behind long after somebody has railed the track for safety.
        assert walled < len(line) * 0.25, (
            f"{track['slug']} is marked exposed but {walled} of {len(line)} "
            f"stations are walled - either unrail it or drop it from EXPOSED")
    else:
        # floating tracks do want them: there is nothing to catch a wide moment
        assert walled > len(line) * 0.5, \
            f"{track['slug']} floats in the void with only {walled} walled stations"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_pole_starts_on_the_inside_of_the_first_corner(track):
    """`pole_side` has to agree with the corner the grid is pointing at.

    Derived independently of `tracks.pole_side` here: walk the road from the
    start line and take the sign of the first heading change worth the name,
    measured off the station positions rather than off the `curv` field the
    real one integrates. Two ways of asking the same question, so a sign error
    in either shows up as a disagreement.
    """
    line = track["line"]
    start = next(g for g in track["gates"] if g["kind"] == "start")
    i0 = start["si"]
    turn = 0.0
    for i in range(i0 + 1, len(line) - 1):
        a, b, c = line[i - 1]["p"], line[i]["p"], line[i + 1]["p"]
        # Yaw only: a loop pitches through 360 degrees without turning at all.
        h0 = math.atan2(b[2] - a[2], b[0] - a[0])
        h1 = math.atan2(c[2] - b[2], c[0] - b[0])
        d = (h1 - h0 + math.pi) % (2 * math.pi) - math.pi
        turn += d
        if abs(turn) >= math.radians(tracks_mod.FIRST_TURN_DEG):
            break
    expect = 1 if turn > 0 else -1
    assert track["pole_side"] == expect, (
        f"{track['slug']} turns {'right' if expect > 0 else 'left'} first but "
        f"puts pole on the {'right' if track['pole_side'] > 0 else 'left'}")


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_a_gate_can_never_be_credited_from_the_road_above_it(track):
    """The checkpoint window's roof is what stops a car on a bridge triggering
    the gate underneath it, so it must stay clear of anything passing overhead.

    This is the guard on `gate_ceiling` being generous: raise the ceiling past
    a track's own crossing clearance and Figure Eight starts crediting laps
    from the wrong level.
    """
    ceil = track["gate_ceil"]
    assert tracks_mod.GATE_CEIL_MIN <= ceil <= tracks_mod.GATE_CEIL_MAX
    line = track["line"]
    for i, j in tracks_mod.crossings(track):
        dy = abs(line[i]["p"][1] - line[j]["p"][1])
        assert ceil < dy, \
            f"{track['slug']} credits gates {ceil} up but crosses itself at {dy:.1f}"


def test_the_ceiling_is_high_enough_to_catch_a_jump():
    """The tracks that made this necessary are the ones you fly on.

    Jump City is four gaps with nothing under them and never crosses itself, so
    there is nothing above a gate to protect and no reason for its checkpoints
    to stop counting five units up.
    """
    assert tracks_mod.get("jumpcity")["gate_ceil"] == tracks_mod.GATE_CEIL_MAX


def test_the_pool_uses_the_whole_vocabulary():
    """Loops, gaps, hills, banking and width changes should all be in use."""
    kinds = set()
    for t in ALL:
        for s in t["sections"]:
            kinds.add(s["t"])
    assert {"straight", "arc", "gap", "loop"} <= kinds
    banked = any(abs(e["n"][1]) < 0.985 and not e.get("fix") and not e.get("air")
                 for t in ALL for e in t["line"])
    assert banked, "nothing in the pool is banked or on a slope"
    widths = {e["hw"] for t in ALL for e in t["line"]}
    assert len(widths) >= 4, f"the pool only uses widths {sorted(widths)}"


def test_the_figure_eight_actually_crosses_over_itself():
    """It is called Figure Eight and its blurb promises a crossing, so it has to
    have one. An earlier layout quietly stopped crossing when a section length
    changed and became a long thin oval with a misleading name."""
    t = tracks_mod.get("eight")
    cross = tracks_mod.crossings(t)
    assert cross, "the figure eight does not cross over itself anywhere"
    line = t["line"]
    gap = max(abs(line[i]["p"][1] - line[j]["p"][1]) for i, j in cross)
    assert gap > 8.0, f"its crossing only clears itself by {gap:.1f}"


def test_pool_has_a_difficulty_spread():
    diffs = sorted(t["difficulty"] for t in ALL)
    assert diffs[0] <= 2 and diffs[-1] >= 4, "no easy or no hard tracks"
    assert len(ALL) >= 8


def _cove_shore_from_js():
    """The `shore` block out of the `cove` palette in trackmesh.js."""
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                           "trackmesh.js")).read()
    i = js.index("shore: {")
    block = js[i:js.index("}", i)]
    return {k: float(v) for k, v in re.findall(r"(at|amp|wave):\s*(-?[\d.]+)", block)}


def test_the_waterline_agrees_with_the_track():
    """tracks.py authors Sandy Cove against a waterline that trackmesh.js draws.

    Two copies of one number, which is this repo's convention and the right one
    here - Python cannot draw the sea and the JS cannot lay the road. But the
    road is placed *relative* to this line, so if the two drift the water moves
    inland over a road that was authored to be dry.
    """
    js = _cove_shore_from_js()
    assert js["at"] == tracks_mod.SHORE_Z
    assert js["amp"] == tracks_mod.SHORE_AMP
    assert js["wave"] == tracks_mod.SHORE_WAVE


def test_only_the_pier_is_over_the_water():
    """Sandy Cove's sea is scenery and is never in the collider, so anywhere the
    road crosses the waterline has *nothing* under it - run wide there and you
    fall instead of landing on sand.

    That is exactly what the pier is for, and it must be the only place it
    happens: everywhere else the beach is the run-off, which is the whole reason
    this is a ground track. A layout change that walks the coast road out over
    the sea would otherwise only show up as people falling off it.
    """
    t = tracks_mod.get("cove")
    line = t["line"]

    def shore(x):
        return (tracks_mod.SHORE_Z
                + tracks_mod.SHORE_AMP * math.sin(x / tracks_mod.SHORE_WAVE * 2 * math.pi)
                + tracks_mod.SHORE_AMP * 0.38
                * math.sin(x / (tracks_mod.SHORE_WAVE * 0.37) * 2 * math.pi))

    over = [i for i, e in enumerate(line)
            if not e.get("air") and e["p"][2] > shore(e["p"][0])]
    assert over, "nothing is over the water - the pier has come back inland"
    # One contiguous run, and it is the pier.
    assert over == list(range(over[0], over[-1] + 1)), \
        f"the road crosses the waterline in more than one place: {over}"
    # Both ends of the track are firmly on the sand.
    assert min(e["p"][2] for e in line) < tracks_mod.SHORE_Z - 100
    # And the road either side of the pier has real clearance from the water,
    # so it is dry land rather than dry by a metre.
    dry = [shore(e["p"][0]) - e["p"][2] for i, e in enumerate(line)
           if i < over[0] - 12 or i > over[-1] + 12]
    assert min(dry) > 25, \
        f"the coast road comes within {min(dry):.0f} units of the waterline"


def _costco_shell_from_js():
    """The `building` block out of the `costco` palette in trackmesh.js."""
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                           "trackmesh.js")).read()
    i = js.index("building: {")
    block = js[i:js.index("door:", i)]
    x = re.search(r"x:\s*\[([\d.\-]+),\s*([\d.\-]+)\]", block)
    z = re.search(r"z:\s*\[([\d.\-]+),\s*([\d.\-]+)\]", block)
    ceil = re.search(r"ceil:\s*([\d.\-]+)", block)
    return ((float(x.group(1)), float(x.group(2))),
            (float(z.group(1)), float(z.group(2))), float(ceil.group(1)))


def test_the_costco_shell_agrees_with_the_track():
    """tracks.py authors the Costco against walls that trackmesh.js draws.

    Two copies of three numbers, which is this repo's convention and the right
    one here for the same reason the waterline is: Python cannot draw a building
    and the JS cannot lay a road. Deriving the shell from whichever stations are
    indoors is the tidier-sounding alternative and it is circular - the wall
    position would depend on the set of stations used to decide where the wall
    goes. So they are authored twice and pinned here. Drift them apart and a wall
    lands across a road, or a doorway stops being where the road goes through.
    """
    x, z, ceil = _costco_shell_from_js()
    assert x == tracks_mod.SHELL_X
    assert z == tracks_mod.SHELL_Z
    assert ceil == tracks_mod.SHELL_CEIL


def test_the_warehouse_fits_inside_its_own_walls():
    """Everything the Costco does off the ground has to happen indoors.

    Both travelators and the whole rooftop car park are authored against
    SHELL_X/SHELL_Z, and a leg lengthened past a wall does not fail loudly - it
    puts a doorway-sized hole in the building where a hairpin pokes out, or brings
    a ramp through a wall three units up in the air. Neither is visible from
    anywhere except inside the building.

    The road is *expected* to cross a wall - twice, once in and once out - so what
    is checked is that it only ever does so on the flat, which is what makes a
    doorway a doorway.
    """
    t = tracks_mod.get("costco")
    line = t["line"]
    (x0, x1), (z0, z1) = tracks_mod.SHELL_X, tracks_mod.SHELL_Z

    inside = lambda e: x0 <= e["p"][0] <= x1 and z0 <= e["p"][2] <= z1

    raised = [i for i, e in enumerate(line) if e["p"][1] > 0.4]
    assert raised, "nothing on the Costco is off the ground - the roof has gone"
    out = [i for i in raised if not inside(line[i])]
    assert not out, (
        "%d raised stations are outside the shell, e.g. station %d at "
        "(%.0f, %.0f, %.0f)" % (len(out), out[0], line[out[0]]["p"][0],
                                line[out[0]]["p"][1], line[out[0]]["p"][2]))

    # Where the road goes through a wall it has to be level, or the doorway is a
    # hole partway up one.
    doors = []
    for i in range(1, len(line)):
        a, b = line[i - 1]["p"], line[i]["p"]
        for at, ax, lo, hi, oax in ((x0, 0, z0, z1, 2), (x1, 0, z0, z1, 2),
                                    (z0, 2, x0, x1, 0), (z1, 2, x0, x1, 0)):
            if (a[ax] - at) * (b[ax] - at) < 0 and lo <= a[oax] <= hi:
                doors.append(i)
                assert abs(b[1]) < 0.35, (
                    "the road leaves the building %.1f units up at station %d - "
                    "that is a hole in a wall, not a door" % (b[1], i))
    assert len(doors) == 2, \
        "expected one way in and one way out, found %d wall crossings" % len(doors)


def test_summaries_do_not_ship_station_lists():
    """The track-select page gets metadata only; the ribbon is a per-track fetch."""
    for s in tracks_mod.summaries():
        assert "line" not in s and "sections" not in s
        assert s["medals"] and s["ideal"] > 0
