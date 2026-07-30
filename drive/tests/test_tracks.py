"""Structural tests on the track pool.

Every failure mode in here is one that actually happened while the pool was being
authored, and each one made a track quietly unfinishable rather than obviously
broken - which is exactly the kind of thing a test should be holding down.
"""

import math
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
    # the anti-cheat floor must sit below the hardest medal, or a gold lap would
    # be rejected as impossible
    assert track["ideal"] * T.MIN_PLAUSIBLE < m["gold"]
    assert 8 < track["ideal"] < 120, "ideal lap outside a sane range"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_barriers_are_opt_in(track):
    """Rails on every corner look like a bobsleigh run and remove the only
    interesting decision on a corner exit. Ground-level tracks get none."""
    line = track["line"]
    walled = sum(1 for e in line if e.get("wl") or e.get("wr"))
    if track["ground"] is not None:
        assert walled == 0, \
            f"{track['slug']} sits on the ground but has {walled} walled stations"
    else:
        # floating tracks do want them: there is nothing to catch a wide moment
        assert walled > len(line) * 0.5, \
            f"{track['slug']} floats in the void with only {walled} walled stations"


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


def test_summaries_do_not_ship_station_lists():
    """The track-select page gets metadata only; the ribbon is a per-track fetch."""
    for s in tracks_mod.summaries():
        assert "line" not in s and "sections" not in s
        assert s["medals"] and s["ideal"] > 0
