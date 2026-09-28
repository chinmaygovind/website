"""A race with nobody in it but bots, written out as an ordinary replay.

    python tools/stage_race.py --db media/video/staged.db spa suzuka baku
    python tools/stage_race.py --db ... monaco --seeds 6 --cars 8

The trailer's race footage used to be races that happened on prod, which is
three problems: only a handful of tracks had one worth filming, the database
holding them existed on one box, and every name in frame was a real person's.
This drives the room's own bots - `botsim.World`, the same JS the server runs,
real `Car.step`, contact, slipstream and catch-up all included - through a race
on any track and stores it as a `DriveRace`, so `/race/<id>` plays it back
exactly as it plays back a real one and `shoot_video.py --db` can film it.

**Several seeds per track, and the closest race is kept.** A race footage beat
wants a pack, and whether one forms is luck: the catch-up boost holds a field
together but a bot that bins it on lap one is gone. Each seed is scored on how
long the leading four stay within `PACK` units of each other and the best is
the one stored; the rest are thrown away. It prints the id and who led, which
is the name `shoot_video.BEATS` follows.

**It records the way the server does** (`app._record_frame`): one pose per car
every `1/REPLAY_HZ` seconds of race time, flag byte included, packed with
`runcheck.pack_ghost`. The only difference is that the clock is ours, so the
frames land exactly on time and the replay needs none of the smoothing a live
recording gets in `shoot_video.install_smoothing`.
"""

import argparse
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
sys.path.insert(0, DRIVE)
sys.path.insert(0, HERE)

from _hero import LIVERIES  # noqa: E402

DT = 1.0 / 30            # the room's own TICK_HZ
MAX_S = 150              # a race still running at this point is not a race
PACK = 30.0              # units: "together", for scoring a seed

# A mixed field, as "Fill the grid" makes one: the quick ones pull a pack along
# and the slow ones are traffic to get through.
FIELD = ("max", "max", "hard", "hard", "hard", "medium", "medium", "easy")


def run(slug, seed, cars, laps):
    """One race. Returns (cars, ms, score)."""
    import botsim
    import bots
    import runcheck
    rng = random.Random(seed)
    w = botsim.World("V%05d" % seed, slug)
    used, entries = set(), []
    for k in range(cars):
        name = bots.pick_name(used, rng)
        used.add(name)
        pid = "b%d" % k
        w.add(pid, FIELD[k % len(FIELD)], seed=seed * 31 + k)
        entries.append(dict(pid=pid, name=name, frames=[], ms=None,
                            livery=LIVERIES[(seed + k) % len(LIVERIES)]))
    order = list(range(cars))
    rng.shuffle(order)
    w.place_grid({entries[i]["pid"]: slot for slot, i in enumerate(order)})
    w.tick(DT, [], 0, "grid", None)
    w.green(0, laps)

    hz = runcheck.GHOST_HZ
    by_pid = {e["pid"]: e for e in entries}
    t, n, together = 0.0, 0, 0
    last = {}
    while t < MAX_S:
        t += DT
        now = int(t * 1000)
        poses, events = w.tick(DT, [], now, "racing", t)
        for p in poses:
            last[p[0]] = p
        for pid, evs in events:
            for e in evs:
                if e[0] == "finish" and by_pid[pid]["ms"] is None:
                    by_pid[pid]["ms"] = e[1]
        while n / hz <= t:
            for e in entries:
                p = last.get(e["pid"])
                if p:
                    e["frames"].append([p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[13]])
            n += 1
        # Score: the front four within PACK of their centroid, per second.
        if n % hz == 0 and len(last) >= 4:
            lead = sorted(last.values(), key=lambda p: -(p[11] or 0))[:4]
            cx = [sum(p[i] for p in lead) / 4 for i in (1, 2, 3)]
            if all(math.dist(p[1:4], cx) < PACK for p in lead):
                together += 1
        if all(e["ms"] is not None for e in entries):
            break
    w.close()
    for e in entries:
        e["ghost"] = runcheck.pack_ghost(e.pop("frames"))
    entries.sort(key=lambda e: e["ms"] if e["ms"] is not None else 1e12)
    return entries, int(t * 1000), together


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--db", required=True, help="sqlite file to write the races into")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--cars", type=int, default=8)
    ap.add_argument("--laps", type=int, default=1)
    args = ap.parse_args()
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(args.db)

    import json
    import runcheck
    from app import app, db
    from models import DriveRace

    for slug in args.tracks:
        best = None
        for seed in range(1, args.seeds + 1):
            cars, ms, score = run(slug, seed, args.cars, args.laps)
            print("  %-12s seed %d  %5.1fs  together %3ds" % (slug, seed, ms / 1000, score))
            if best is None or score > best[2]:
                best = (cars, ms, score)
        cars, ms, _ = best
        out = [dict(pid=c["pid"], name=c["name"], color=c["livery"]["body"],
                    livery=c["livery"], ms=c["ms"], dnf=c["ms"] is None, bot=True,
                    ghost=c["ghost"]) for c in cars]
        with app.app_context():
            race = DriveRace(code="STAGED", track=slug, hz=runcheck.GHOST_HZ, ms=ms,
                             why="staged", cars_json=json.dumps(out))
            db.session.add(race)
            db.session.commit()
            print("%-12s race %d, won by %s" % (slug, race.id, out[0]["name"]))


if __name__ == "__main__":
    main()
