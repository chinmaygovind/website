"""Cut each track's medal times from the times people have actually driven.

Generated, not authored - the same deal `hotlap.json` has. Run it when the
boards have moved enough to be worth re-cutting, look at what it prints, and
commit the `track.py` edits it made.

    python tools/set_medals.py --times board.json          # dry run, prints a table
    python tools/set_medals.py --times board.json --write  # and edits track.py

`--times` is a JSON `{slug: [time_ms, ...]}`. On the box the DB is right there
and `--db` reads it directly:

    python tools/set_medals.py --db instance/tickettoride.db --write

**Why not derive them from `laptime.ideal_lap` like everything else here?**
Because `ideal` is an estimate of a *lap* and the medal is a *standard*, and the
error between the two is per-track rather than global: measured against the
records on the site, `WR/ideal` runs from 0.744 (Chicane Park) to 0.888 (Spiral
Ascent). A single multiplier over that spread has no good setting. At 0.92 - what
shipped for months - 92.7% of every time ever set on this site earned gold, and
on eight of the sixteen tracks *everybody* on the board had one. Tighten the
multiplier until Chicane Park is a real gold and Spiral Ascent, Heights and
Skyline have no gold at all. `docs/runs-and-scoring.md` called this out and said
the fix was a better `laptime.py` rather than per-track fudge factors; the fix
that was actually available was to stop guessing and read the board.

**Gold is `min(5th best, WR x 1.06)`.** The fifth best is the target - "about the
fifth quickest person here" is a standard a player can picture, and it lands
naturally at top-5 pace on a board deep enough to have one. The cap is what makes
it survive a board that is not: Big Red has five times on it, so its fifth best
*is* its slowest, 15.8% off the record, and gold would have gone to everybody who
ever finished. Twist and Cloudbreak have the same shape one row down - a cliff
after fourth place. The cap costs nothing on a healthy board (it binds on 4 of
16) and stops a thin one handing out a medal for turning up.

**Silver and bronze are two equal 5% steps**, which makes them proportional to
the lap rather than a flat number of seconds: 0.9s apart on Sunrise Circuit, 3s
apart on Big Red. Three steps of one standard, which is what the medals were
supposed to be and were not - they used to be 2.8-5.7s apart at the top and
4.8-9.7s at the bottom, three unrelated standards wearing one name.

Everything is rounded **up** to a tenth. See `laptime.ceil_tenth` for why up.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import laptime                                                    # noqa: E402
import tracks as tracks_mod                                       # noqa: E402

# The cap on gold, as a multiple of the record, and the two steps under it.
# Both are here rather than in `tuning.py` because they are a policy about the
# leaderboard and not a property of the car - retuning the car must not silently
# re-cut medals that were measured against laps driven under the old tune.
GOLD_RANK = 5
GOLD_CAP = 1.06
STEP = 1.05

DECL = re.compile(r"^medals\s*=.*$", re.M)


def times_from_db(path):
    import sqlite3
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    out = {}
    for slug, ms in c.execute("SELECT track, time_ms FROM drive_times"):
        out.setdefault(slug, []).append(ms)
    return out


def cut(times):
    """`(gold, silver, bronze)` in seconds for one track's board, or None."""
    v = sorted(t / 1000.0 for t in times)
    if not v:
        return None
    nth = v[min(GOLD_RANK - 1, len(v) - 1)]
    gold = laptime.ceil_tenth(min(nth, v[0] * GOLD_CAP))
    silver = laptime.ceil_tenth(gold * STEP)
    bronze = laptime.ceil_tenth(silver * STEP)
    # Rounding up can collide two steps on a very short lap. Nudge rather than
    # emit a card with two identical times on it, which `_medals_decl` refuses.
    if silver <= gold:
        silver = round(gold + 0.1, 1)
    if bronze <= silver:
        bronze = round(silver + 0.1, 1)
    return gold, silver, bronze


def write_decl(slug, medals):
    """Put (or replace) the `medals = (...)` line in a track's `track.py`."""
    path = os.path.join(ROOT, "tracks", slug, "track.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    line = "medals = (%s, %s, %s)" % tuple(("%.1f" % m) for m in medals)
    if DECL.search(src):
        src = DECL.sub(line, src, count=1)
    else:
        # Under `difficulty`, which is the other number on the same subject.
        m = re.search(r"^difficulty\s*=.*$", src, re.M)
        if not m:
            raise SystemExit("tracks/%s/track.py has no difficulty line to sit "
                             "under; add `medals` by hand" % slug)
        src = src[:m.end()] + "\n" + line + src[m.end():]
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--times", help="JSON {slug: [time_ms, ...]}")
    src.add_argument("--db", help="a Drive SQLite file, read-only")
    ap.add_argument("--write", action="store_true",
                    help="edit tracks/<slug>/track.py; without it, print only")
    args = ap.parse_args()

    board = (times_from_db(args.db) if args.db
             else json.load(open(args.times, encoding="utf-8")))

    print("%-10s %4s %8s %8s   %8s %8s %8s   %s"
          % ("track", "n", "record", "5th", "gold", "silver", "bronze", "earned now"))
    missing = []
    for t in tracks_mod.TRACKS:
        slug = t["slug"]
        times = board.get(slug) or []
        m = cut(times)
        if not m:
            missing.append(slug)
            continue
        v = sorted(x / 1000.0 for x in times)
        nth = v[min(GOLD_RANK - 1, len(v) - 1)]
        got = [sum(1 for x in v if x <= b) for b in m]
        print("%-10s %4d %8.2f %8.2f   %8.1f %8.1f %8.1f   %2d/%2d/%2d of %d"
              % (slug, len(v), v[0], nth, m[0], m[1], m[2],
                 got[0], got[1], got[2], len(v)))
        if args.write:
            write_decl(slug, m)

    if missing:
        print("\nno times, left deriving from the ribbon: %s" % ", ".join(missing))
    if not args.write:
        print("\ndry run. --write to edit the track files.")


if __name__ == "__main__":
    main()
