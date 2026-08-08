"""Measure the speeds inside every stored ghost, and name the laps that are not driving.

A submitted lap is checked for *self-consistency* and never re-simulated
(`runcheck.validate` says so in its own docstring), so a browser running retuned
physics produces a replay that passes every check there is: real checkpoints in
order, a frame count that matches the clock, a start on the line. What it cannot
produce is a plausible *speed*, because the car's top speed is a property of
`ACCEL` fighting `DRAG` and no amount of driving skill exceeds it on the level.

So this reads the one thing the cheat has to leave behind. Two numbers matter and
the second is the stronger:

  * the **top** speed in the replay, against the physics' own hard velocity clamp
    (`MAX_SPEED * 1.7` = 85). Nothing the simulation can do goes past it.
  * the **median** speed over the whole lap, against `MAX_SPEED` (50). Gravity
    lifts a car over 50 down a descent - that is why the top speed alone is a
    blunt instrument - but nothing holds it there for a whole lap. Every honest
    lap on the site medians between 45 and 50.

Usage:

    python3 tools/audit_times.py /path/to/tickettoride.db
    python3 tools/audit_times.py /path/to/db --track twist -v

Take a snapshot rather than pointing this at the live file - it is under WAL with
five writers, and `sqlite3.Connection.backup` gets a consistent copy:

    ssh kotprod 'python3 -c "
    import sqlite3
    s=sqlite3.connect(\"file:/home/ubuntu/TicketToRide/instance/tickettoride.db?mode=ro\",uri=True)
    d=sqlite3.connect(\"/tmp/snap.db\"); s.backup(d)"'
    scp kotprod:/tmp/snap.db .
"""

import argparse
import base64
import json
import os
import sqlite3
import sys
import zlib
from statistics import median

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import tuning as T                                    # noqa: E402

CLAMP = T.MAX_SPEED * 1.7      # the physics' own hard velocity clamp
WINDOW = 3                     # frames to measure speed over; smooths the 1cm grid


def unpack(blob):
    """The `runcheck.unpack_ghost` positions only - rotation is not evidence."""
    obj = json.loads(zlib.decompress(base64.b64decode(blob)))
    d = obj["d"]
    pq = obj.get("q", [100.0, 4096.0])[0]
    stride = int(obj.get("n", 7))
    pts = [(d[i] / pq, d[i + 1] / pq, d[i + 2] / pq)
           for i in range(0, len(d) - stride + 1, stride)]
    return pts, obj.get("hz", 15)


def speeds(pts, hz, win=WINDOW):
    """Speed over a `win`-frame window.

    A chord across a curve understates the distance travelled and never
    overstates it, so every figure here is a floor on the real speed - which is
    the right direction for a number used to accuse somebody.
    """
    out = []
    for i in range(win, len(pts)):
        a, b = pts[i - win], pts[i]
        out.append(sum((b[k] - a[k]) ** 2 for k in range(3)) ** 0.5 / (win / hz))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", help="path to a snapshot of the shared SQLite file")
    ap.add_argument("--track", help="only this slug")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="every lap, not just the flagged ones")
    args = ap.parse_args()

    c = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    sql = ("SELECT t.id, t.track, u.username, t.time_ms, t.ghost "
           "FROM drive_times t JOIN users u ON u.id = t.user_id "
           "WHERE t.ghost IS NOT NULL")
    params = ()
    if args.track:
        sql += " AND t.track = ?"
        params = (args.track,)
    rows = c.execute(sql + " ORDER BY t.track, t.time_ms", params).fetchall()

    print("clamp %.0f   MAX_SPEED %.0f\n" % (CLAMP, T.MAX_SPEED))
    print("%-5s %-9s %-16s %8s %7s %7s %7s %7s"
          % ("id", "track", "driver", "time", "top", "p95", "median", "over50"))
    print("-" * 70)

    flagged, scanned = [], 0
    for rid, track, user, ms, ghost in rows:
        try:
            pts, hz = unpack(ghost)
        except Exception as e:
            print("%-5d %-9s %-16s  UNREADABLE GHOST (%s)" % (rid, track, user, e))
            continue
        sp = speeds(pts, hz)
        if not sp:
            continue
        scanned += 1
        top, med = max(sp), median(sp)
        p95 = sorted(sp)[int(len(sp) * 0.95)]
        over = sum(1 for s in sp if s > T.MAX_SPEED) / len(sp) * 100

        why = None
        if top > CLAMP:
            why = "top speed %.1f is past the hard clamp %.0f" % (top, CLAMP)
        elif med > T.MAX_SPEED:
            why = "median %.1f is over MAX_SPEED for the whole lap" % med
        if why:
            flagged.append((rid, track, user, why))

        if args.verbose or why:
            print("%-5d %-9s %-16s %7.3fs %7.1f %7.1f %7.1f %6.1f%%%s"
                  % (rid, track, user, ms / 1000.0, top, p95, med, over,
                     "   <== " + why if why else ""))

    print("\n%d laps scanned, %d flagged" % (scanned, len(flagged)))
    for rid, track, user, why in flagged:
        print("  drive_times id=%d  %s  %s  - %s" % (rid, track, user, why))
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
