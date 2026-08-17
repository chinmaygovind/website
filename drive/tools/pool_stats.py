"""Measure a track against the sixteen that are already good.

The pool is a labelled set. Every track in it has been driven, looked at, and
kept, which makes it the only description of "a good track here" that exists —
and nothing used it. This reads it back: profile a candidate on the numbers that
are cheap to compute, and say where each one sits against the rest of the pool.

    cd drive && venv/bin/python tools/pool_stats.py            # the whole pool
    cd drive && venv/bin/python tools/pool_stats.py dockyard   # one against the rest
    cd drive && venv/bin/python tools/pool_stats.py dockyard --csv

**This is advisory and it is not a test.** Big Red falls 223 units and no other
track falls more than 63; Rainbow Road has almost no barriers; the Costco has a
roof. Every one of those is an outlier here and every one of them is the point of
the track. What the report is good for is the *other* kind of outlier — the fog
distance that is a third of anything else in the pool, the scatter density ten
times the next densest, the closing straight that is longer than any straight
anybody has driven here. Those are usually a typo or a units mistake, and they
are exactly the class of defect that is hard to see in a render and hard to
remember to look for.

A track already in the pool is compared against the other fifteen, not against a
pool containing itself, or it would drag its own median toward it and never look
unusual.

Ranges are printed as the pool's own min..max. `>` and `<` mark a value outside
that range, with how far outside as a multiple of the nearer end.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tracks                                    # noqa: E402
from tracks.builder import STATION               # noqa: E402


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def profile(t):
    """Every number worth comparing, off the track dict and its palette.

    Only things that are cheap and that a mistake actually moves. Deliberately
    no per-station statistics: a candidate with a bad leg shows up in the leg
    numbers, and a hundred columns is a report nobody reads.
    """
    line = t["line"]
    secs = t["sections"]
    pal = t.get("pal") or {}
    # Chicane and Skyline predate the graded dome and carry a bare colour here.
    # Their fog and stop counts are not zero, they are *absent*, and a metric
    # that does not apply has to stay out of the pool's range or it drags the
    # floor to zero and nothing can ever read as unusually foggy again.
    sky = pal.get("sky")
    sky = sky if isinstance(sky, dict) else {}
    graded = bool(sky)

    ys = [e["p"][1] for e in line]
    hws = [e["hw"] for e in line]
    radii = [s["rad"] for s in secs if s["t"] == "arc" and s.get("rad")]
    runs = [s["len"] for s in secs if s["t"] == "straight" and s.get("len")]
    medals = t.get("medals") or {}
    gold = medals.get("gold") or 0.0

    return {
        # shape
        "length": len(line) * STATION,
        "corners": len(radii),
        "radius min": min(radii) if radii else 0.0,
        "radius med": _median(radii) if radii else 0.0,
        "radius max": max(radii) if radii else 0.0,
        "straights": len(runs),
        "straight max": max(runs) if runs else 0.0,
        "straight med": _median(runs) if runs else 0.0,
        "climb range": max(ys) - min(ys),
        "net height": ys[-1] - ys[0],
        "width min": min(hws) * 2.0,
        "width max": max(hws) * 2.0,
        # features
        "gaps": sum(1 for s in secs if s["t"] == "gap"),
        "loops": sum(1 for s in secs if s["t"] == "loop"),
        "boosts": sum(1 for s in secs if s["t"] == "boost"),
        "checkpoints": t.get("checkpoints") or 0,
        "gate ceiling": t.get("gate_ceil") or 0.0,
        "walled %": 100.0 * sum(1 for e in line if e.get("wl") or e.get("wr")) / max(1, len(line)),
        "air %": 100.0 * sum(1 for e in line if e.get("air")) / max(1, len(line)),
        # pace
        "difficulty": t.get("difficulty") or 0,
        "gold": gold,
        "medal spread": (medals.get("bronze") or 0.0) / gold if gold else 0.0,
        # look
        # The *effective* density, not the declared one. A palette that says
        # nothing gets a real default from `addScenery` (0.17 on the ground,
        # 0.05 in the void), so reporting the absence as 0 would both read as
        # "no scatter here" and hold the pool's floor at zero, which is the one
        # value that stops a mistyped density from ever looking unusual.
        "density": pal.get("density", 0.17 if t.get("ground") is not None else 0.05),
        "fog near": sky.get("fogNear") if graded else None,
        "fog far": sky.get("fogFar") if graded else None,
        "sky stops": len(sky.get("stops") or ()) if graded else None,
    }


KEYS = list(profile(tracks.get(tracks.TRACKS[0]["slug"])).keys())


def pool(exclude=None):
    """Every track's profile, optionally leaving one out."""
    out = {}
    for e in tracks.TRACKS:
        if e["slug"] == exclude:
            continue
        out[e["slug"]] = profile(tracks.get(e["slug"]))
    return out


def compare(slug):
    """One track against the rest of the pool."""
    try:
        t = tracks.get(slug)
    except Exception as exc:
        print("no track %r: %s" % (slug, exc))
        return 1
    # A folder that failed to load is left out of the pool rather than raising,
    # so `get` hands back None and the only symptom is a warning on import. That
    # is the state a track being authored is most often in, so say so plainly
    # instead of dying on a subscript.
    if t is None:
        print("\n%r is not in the pool.\n" % slug)
        print("  Either there is no tracks/%s/, or the folder failed to load and" % slug)
        print("  was skipped with a warning. Run this to see the loader's reason:")
        print("    venv/bin/python -c 'import tracks'")
        print()
        return 1

    me = profile(t)
    rest = pool(exclude=slug)
    if not rest:
        print("nothing to compare against")
        return 1

    others = len(rest)
    print("\n%s (%s) against the other %d\n" % (t["name"], slug, others))
    print("  %-14s %10s   %-19s %9s" % ("", "this", "pool", "median"))
    print("  " + "-" * 58)

    odd = []
    for k in KEYS:
        vals = [p[k] for p in rest.values() if p[k] is not None]
        v = me[k]
        if v is None or not vals:
            # A metric this track does not have, or that nothing to compare
            # against has. Shown, so its absence is visible, but not judged.
            print("  %-14s %10s   %-19s %9s" % (k, "-", "-", "-"))
            continue
        lo, hi, mid = min(vals), max(vals), _median(vals)

        # Being the longest track in the pool by 4% is not unusual, it is just
        # being the longest, and a report that says so nine times is a report
        # nobody reads to the end. So `>` is merely outside the range and stays
        # in the table, and only `>>` - outside it by a quarter of the pool's
        # own spread - is worth a line at the bottom. The yardstick is the
        # spread rather than a ratio because `net height` runs through zero and
        # a ratio there is meaningless.
        span = (hi - lo) or abs(hi) or 1.0
        tol = span * 0.25
        mark = "  "
        if v > hi:
            mark = ">>" if v > hi + tol else "> "
            if mark == ">>":
                odd.append("%s is %s - the pool tops out at %s (+%s)"
                           % (k, _fmt(v), _fmt(hi), _fmt(v - hi)))
        elif v < lo:
            mark = "<<" if v < lo - tol else "< "
            if mark == "<<":
                odd.append("%s is %s - the pool bottoms out at %s (-%s)"
                           % (k, _fmt(v), _fmt(lo), _fmt(lo - v)))
        print("%s%-14s %10s   %-19s %9s"
              % (mark, k, _fmt(v), "%s..%s" % (_fmt(lo), _fmt(hi)), _fmt(mid)))

    print()
    print("  > outside the pool's range, >> outside it by a wide margin")
    print()
    if not odd:
        print("  Nothing far out. Every number sits in or near the pool's own range.")
    else:
        print("  %d worth a look:" % len(odd))
        for line in odd:
            print("    - %s" % line)
        print()
        print("  Unusual is not wrong - Big Red falls 223 units on purpose. But a")
        print("  number far outside the pool is where a typo or a units mistake")
        print("  hides, so check each one was deliberate.")
    print()
    return 0


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        if v and abs(v) < 1:
            return "%.3f" % v
        return "%.1f" % v if v % 1 else "%d" % v
    return str(v)


def table(csv=False):
    """The whole pool, one row each."""
    ps = pool()
    if csv:
        print("slug," + ",".join(k.replace(" ", "_") for k in KEYS))
        for slug, p in ps.items():
            print(slug + "," + ",".join(_fmt(p[k]) for k in KEYS))
        return 0

    # Too many columns for one terminal, so the interesting ones and a pointer
    # to --csv for the rest.
    cols = [("length", "len"), ("corners", "bends"), ("radius min", "tightest"),
            ("straight max", "longrun"), ("climb range", "climb"),
            ("gaps", "gaps"), ("loops", "loops"), ("difficulty", "diff"),
            ("gold", "gold"), ("density", "scatter"), ("fog far", "fogfar")]
    print()
    print("  %-10s" % "track" + "".join("%9s" % short for _, short in cols))
    print("  " + "-" * (10 + 9 * len(cols)))
    for slug, p in ps.items():
        print("  %-10s" % slug + "".join("%9s" % _fmt(p[k]) for k, _ in cols))
    print()
    print("  %d tracks. All %d metrics with --csv; one track against the rest"
          % (len(ps), len(KEYS)))
    print("  with `pool_stats.py <slug>`.")
    print()
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    csv = "--csv" in argv
    if not args:
        return table(csv=csv)
    if csv:
        p = profile(tracks.get(args[0]))
        print(",".join(k.replace(" ", "_") for k in KEYS))
        print(",".join(_fmt(p[k]) for k in KEYS))
        return 0
    return compare(args[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
