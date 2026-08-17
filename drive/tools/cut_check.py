#!/usr/bin/env python3
"""Corners you could simply leave out: paying shortcuts, and whether anything stops them.

Chinmay found this on Silverstone before a single lap had been driven: the arena
and the Brooklands-Luffield loop each sat entirely between two checkpoints, so the
straight line across them was a *legal* lap that skipped a third of a corner
sequence. Three and a half seconds each, and nothing in the suite could see it.

What makes a cut pay
--------------------
`OFFROAD_DRAG` is a linear term, so grass tops out near half the road's top speed
(see `docs/tracks-and-geometry.md`). Driving `chord` units of grass therefore costs
about what `2 * chord` units of road would - so a chord pays once the road distance
it skips is more than roughly twice it. That is the whole model, and it is
deliberately crude: it is a *screen*, not a lap-time simulation.

Two things then decide whether a paying chord matters, and the point of this tool
is that it asks both:

  * **does it skip a checkpoint?** If so it is already dead - `Run._advance` in
    course.js will not credit a lap that missed one, so nothing needs doing.
  * **does anything stand across it?** This is the half that cannot be answered
    from the ribbon, and answering it wrongly is why this is a tool rather than a
    test. A chord in plan says nothing about whether there is a wall, a building or
    a loop in the way: the naive version of this check flags a hairpin on Spa, a
    warehouse on the Costco and a loop on four other tracks, all of them fine. So
    the collider gets built for real, in QuickJS, through the same `buildTrack`
    the game and the anti-cheat use, and every `WALL` triangle is tested against
    the chord.

Usage
-----
    venv/bin/python tools/cut_check.py                 # every track in the pool
    venv/bin/python tools/cut_check.py silverstone     # one, with the worst listed

It reports rather than failing, because "this corner is skippable" is a judgement
about how mean a track is allowed to be, and that is the track's decision. What it
removes is having to make that decision without knowing.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import jsrt                                                   # noqa: E402
import tracks as tracks_mod                                   # noqa: E402

# A chord pays when the road it skips is more than this many times its own length.
# Two, because grass is about half road speed; a little over two so a cut that
# merely breaks even is not reported as a defect.
PAYS = 2.0
# Below this there is nothing to skip - it is a corner's own apex, which is what
# kerbs and run-off are for.
MIN_ROAD = 60.0
# A chord that climbs or drops more than this is not a line anybody can drive: it
# is a loop passing overhead, or a bridge. Without it every loop in the pool reads
# as a shortcut.
MAX_RISE = 6.0
# Stations closer together than this along the road are neighbours.
MIN_APART = 16
# Only report cuts worth more than this many units of road.
REPORT = 25.0

COLLIDER = """
function walls(slug) {
  var t = TRACKS.filter(function (x) { return x.slug === slug; })[0];
  var b = buildTrack(t, T);
  var v = b.collider.v, k = b.collider.k, out = [];
  for (var i = 0; i < k.length; i++) {
    if (k[i] !== KIND.WALL) continue;
    var o = i * 9;
    // Flattened to plan, which is all the chord test needs. Height comes back too
    // so a wall under a bridge does not block a chord that flies over it.
    out.push([v[o], v[o+1], v[o+2], v[o+3], v[o+4], v[o+5], v[o+6], v[o+7], v[o+8]]);
  }
  return out;
}
"""


def _seg_hits_tri(a, b, tri, y0, y1):
    """Does the chord a->b cross this wall triangle in plan, at a shared height?"""
    ys = (tri[1], tri[4], tri[7])
    if min(ys) > max(y0, y1) + 1.5 or max(ys) < min(y0, y1) - 1.5:
        return False                      # the wall is not at the chord's height
    p = ((tri[0], tri[2]), (tri[3], tri[5]), (tri[6], tri[8]))

    def cross(o, u, w):
        return (u[0]-o[0]) * (w[1]-o[1]) - (u[1]-o[1]) * (w[0]-o[0])

    for i in range(3):
        c, e = p[i], p[(i + 1) % 3]
        d1, d2 = cross(a, b, c), cross(a, b, e)
        d3, d4 = cross(c, e, a), cross(c, e, b)
        if (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0):
            return True
    return False


def cuts(track, walls):
    """Every paying chord on this track, worst first, each marked blocked or open."""
    line = track["line"]
    n = len(line)
    along = [0.0]
    for i in range(n - 1):
        along.append(along[-1] + math.dist(line[i]["p"], line[i + 1]["p"]))

    gates = []
    for g in track["gates"]:
        if g["kind"] == "start":
            continue
        p = g["p"]
        gates.append(min(range(n), key=lambda i: (line[i]["p"][0] - p[0]) ** 2
                                                 + (line[i]["p"][2] - p[2]) ** 2))
    gates.sort()

    out = []
    for i in range(n):
        if line[i].get("air"):
            continue
        for j in range(i + MIN_APART, n):
            if line[j].get("air"):
                continue
            # Past a gate there is nothing left to check on this `i`: the gate
            # defends every chord that reaches beyond it.
            if any(i < c < j for c in gates):
                break
            road = along[j] - along[i]
            if road < MIN_ROAD:
                continue
            a3, b3 = line[i]["p"], line[j]["p"]
            if abs(a3[1] - b3[1]) > MAX_RISE:
                continue
            a, b = (a3[0], a3[2]), (b3[0], b3[2])
            chord = math.dist(a, b)
            if chord < 4:
                continue
            gain = road - PAYS * chord
            if gain < REPORT:
                continue
            blocked = any(_seg_hits_tri(a, b, t, a3[1], b3[1]) for t in walls)
            out.append((gain, chord, road, along[i] / along[-1],
                        along[j] / along[-1], blocked))
    out.sort(reverse=True)
    return out


def report(rt, track, verbose):
    walls = rt.call("walls(%r)" % track["slug"])
    found = cuts(track, walls)
    open_ = [c for c in found if not c[-1]]
    worst = max((c[0] for c in open_), default=0.0)
    print("%-12s %5d paying  %5d open   worst open %6.0f u%s"
          % (track["slug"], len(found), len(open_), worst,
             "   <-- look at this" if worst > 40 else ""))
    if not verbose:
        return worst
    seen = []
    for gain, chord, road, f0, f1, blocked in found:
        if any(abs(f0 - x) < 0.015 and abs(f1 - y) < 0.015 for x, y in seen):
            continue
        seen.append((f0, f1))
        print("      %6.0f u  chord %4.0f  road %4.0f   f %.3f -> %.3f   %s"
              % (gain, chord, road, f0, f1,
                 "blocked" if blocked else "** OPEN **"))
        if len(seen) >= 12:
            break
    return worst


def main(argv):
    want = argv[1:] if len(argv) > 1 else None
    rt = jsrt.Runtime()
    rt.load_tuning_and_tracks()
    rt.eval(COLLIDER)
    pool = [t for t in tracks_mod.TRACKS if not want or t["slug"] in want]
    if not pool:
        print("no such track: %s" % ", ".join(want))
        return 2
    print("A chord pays when the road it skips is over %.1fx its own length, and it\n"
          "only matters if it skips no checkpoint and nothing stands across it.\n"
          % PAYS)
    for t in pool:
        report(rt, t, verbose=bool(want))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
