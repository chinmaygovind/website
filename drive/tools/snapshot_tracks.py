"""Freeze every track's geometry and medal times, so a refactor can prove it moved nothing.

This exists because of one property of this game: **a leaderboard is only
comparable against unchanged geometry.** Every time on `drive_times` was driven
on a particular ribbon, and every medal was derived from that ribbon by
`laptime`. Move a station by a tenth of a unit and the gold time shifts, which
silently re-grades laps that were driven months ago.

So before the tracks were split into one folder each, this recorded all fifteen
of them - every station, every gate, the spawn, the sections, the derived
`pole_side` and `gate_ceil`, the ideal lap and the three medal times - and
`tests/test_tracks_did_not_move.py` asserts the loader still reproduces it.

The snapshot is *kept* rather than deleted after the refactor. It is the only
thing in the suite that can notice a geometry change at all: every other track
test asks whether the ribbon is well formed, and a ribbon that moved ten units
sideways is still perfectly well formed.

    cd drive && venv/bin/python tools/snapshot_tracks.py          # write it
    cd drive && venv/bin/python tools/snapshot_tracks.py --check   # compare only

Re-write it **only** when you have decided a geometry change is correct, and say
so in the commit message. `--check` is what the test runs, and it is also the
fastest way to see what a change you are in the middle of has done.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "tests", "data", "tracks_snapshot.json")

# Rounded before storing, for two reasons. It keeps the file readable as a diff -
# an eight-decimal float per coordinate is 906 stations of noise on Spa - and it
# is below the resolution anything downstream can act on: the car is 2.6 units
# wide and the collision hash cell is 8, so 1e-6 of a unit is not a position, it
# is float dust. Medal times are stored as they are, because they are already
# rounded to 1/100s by `laptime.medals`.
PLACES = 6

# Everything a track carries. Named explicitly rather than dumping the dict,
# because a new key appearing should be a deliberate decision to snapshot it and
# not something that silently starts being compared.
KEYS = ("slug", "name", "blurb", "ground", "difficulty", "exposed", "closed",
        "cell", "level", "station", "checkpoints", "spawn", "sections",
        "gates", "line", "pole_side", "gate_ceil", "ideal", "medals")


def _round(v):
    """Round every float in a nested structure, leaving everything else alone."""
    if isinstance(v, float):
        return round(v, PLACES)
    if isinstance(v, list):
        return [_round(x) for x in v]
    if isinstance(v, tuple):
        return [_round(x) for x in v]
    if isinstance(v, dict):
        return {k: _round(x) for k, x in v.items()}
    return v


def snapshot():
    """Every track, in pool order, as plain JSON."""
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    out = []
    for t in tracks_mod.TRACKS:
        out.append({k: _round(t[k]) for k in KEYS if k in t})
    return out


def _fmt(snap):
    """One track per line: compact, and a diff names the tracks that moved.

    Indenting this properly costs 1.6MB and 200k lines, because 7347 stations
    have three vectors each. One line per track is 400kB, and it gives a git diff
    the only granularity that is useful anyway - *which track* changed. What
    changed inside it is `--check`'s job, and it says it in units and seconds
    rather than in floats.
    """
    rows = [json.dumps(t, sort_keys=True, separators=(",", ":")) for t in snap]
    return "[\n" + ",\n".join(rows) + "\n]"


def main(argv):
    snap = snapshot()
    text = _fmt(snap)

    if "--check" in argv:
        if not os.path.exists(OUT):
            print("no snapshot at %s - run without --check to write one" % OUT)
            return 1
        with open(OUT) as f:
            old = json.load(f)
        return _report(old, snap)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(text + "\n")
    print("%d tracks, %d stations, %.0f kB -> %s"
          % (len(snap), sum(len(t["line"]) for t in snap),
             len(text) / 1024.0, os.path.relpath(OUT, ROOT)))
    return 0


def _report(old, new):
    """Print what moved, in the terms an author thinks in."""
    import math
    by_slug = {t["slug"]: t for t in old}
    bad = 0
    for t in new:
        o = by_slug.pop(t["slug"], None)
        if o is None:
            print("  %-10s NEW - not in the snapshot" % t["slug"])
            bad += 1
            continue
        notes = []
        if len(o["line"]) != len(t["line"]):
            notes.append("stations %d -> %d" % (len(o["line"]), len(t["line"])))
        else:
            shift = max((math.dist(a["p"], b["p"])
                         for a, b in zip(o["line"], t["line"])), default=0.0)
            if shift > 0:
                notes.append("max station shift %.6f" % shift)
        if o["medals"] != t["medals"]:
            notes.append("MEDALS %s -> %s" % (o["medals"], t["medals"]))
        if o["ideal"] != t["ideal"]:
            notes.append("ideal %.3f -> %.3f" % (o["ideal"], t["ideal"]))
        for k in ("gates", "spawn", "sections", "pole_side", "gate_ceil",
                  "checkpoints", "closed", "exposed", "ground", "difficulty"):
            if k in o and o[k] != t.get(k):
                notes.append("%s changed" % k)
        if notes:
            print("  %-10s %s" % (t["slug"], "; ".join(notes)))
            bad += 1
    for slug in by_slug:
        print("  %-10s GONE - in the snapshot, not in the pool" % slug)
        bad += 1
    if bad:
        print("%d track(s) differ from the snapshot" % bad)
        return 1
    print("all %d tracks identical to the snapshot" % len(new))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
