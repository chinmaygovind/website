"""World-record reels: which lap to film next, off a queue kept on the box.

    python3 tools/wr_queue.py --out reels            # prints "slug lap rank", or nothing
    python3 tools/wr_queue.py --out reels --urgent   # only a world record set since last look

Runs in the wr-reel Action: every six hours for the queue, and every ten
minutes `--urgent`, so a new world record is filmed and posted as soon as it is
seen rather than at the next slot. Stdlib only.

**The state is `drive/static/reels/wr-state.json` on the box**, public like
`last-posted.txt`, so this reads it with nothing but a URL:

    {"seen": {slug: [lap id, time_ms]}, "queue": [[slug, lap id, time_ms, rank], ...],
     "races": [race id, ...], "n": posts so far}

`seen` is the record each track had last time anybody looked. **Every lap
that has beaten it since is a new world record** (`records_since`), and all of
them are filmed at once, one runner each, and posted in the order they were
set - so a burst of records keeps up rather than queueing behind each other.
The first run, with no state at all, fills the queue with each track's record.

**Records only.** The queue used to interleave each track's best lap by
somebody else, posted as "#2 All Time"; Chinmay dropped those, and `plan`
throws away any still queued.

**The record is (lap id, time), not the lap id.** A board keeps one row per
driver per track, so a holder beating their own record changes the time on
the same id - and the watch page would then play the new lap under the old
card. A queued lap whose time has moved since is dropped, and the new one is
already in the queue as a fresh record.

**Every third post is a room race instead** (`RACE_EVERY`), because racing
other people live is the thing about Drive no other browser racer has. Among
`/api/races`, between at least two people - a win over bots alone is not
multiplayer - it is the one where somebody climbed furthest through the field,
best of all to the win, with a close finish as the tie-breaker (`best_race`).
Printed as `race <id> 0`. `races` in the state is the ids already posted; `n` counts posts.
With no race good enough the slot goes to the next lap as usual.

**A beaten record still posts, as a record.** Its rank was fixed when it was
queued, and the card says what it was when it was set.

Prints the reels to film as one JSON list, and writes the state as it will be
once they are all posted to `<out>/wr-state.next.json`. The Action swaps it in
only if every one posted, so a failed run re-plans rather than losing a lap;
the ones that did post leave a `.posted` marker and are not posted twice.
"""

import argparse
import json
import os
import random
import urllib.error
import urllib.request

BASE = "https://drive.cgovind.com"
RACE_EVERY = 3
RACE_GAP_MS = 1500    # a finish further apart than this is not a race on film
VETOED = {535}       # races Chinmay has looked at and does not want posted


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def boards():
    """Each pool track's board, laps with a replay only, keeping their rank."""
    out = {}
    for t in get("/api/tracks")["tracks"]:
        rows = get("/api/board/" + t["slug"])["rows"]
        out[t["slug"]] = [(i + 1, r) for i, r in enumerate(rows) if r["has_ghost"]]
    return out


def prefill(b):
    """Every track's record, in a fixed shuffle."""
    slugs = [s for s in b if b[s]]
    random.Random(1).shuffle(slugs)
    return [[slug, b[slug][0][1]["id"], b[slug][0][1]["time_ms"], 1] for slug in slugs]


def progress(frames, line, closed):
    """How far along `line` a car is at each frame, in stations, unwrapped.

    Searched near the last answer rather than over the whole line, so a track
    that passes over or beside itself (Suzuka, Monaco) does not jump a car to
    the other road. Wide enough to follow a respawn back to its checkpoint.
    """
    pts = [q["p"] for q in line]
    n = len(pts)
    d2 = lambda a, b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    at = min(range(n), key=lambda i: d2(pts[i], frames[0]))
    if closed and at > n // 2:          # a grid behind the line is the end of the lap
        at -= n
    out = []
    for f in frames:
        near = range(at - 80, at + 81)
        if not closed:
            near = range(max(0, at - 80), min(n, at + 81))
        at = min(near, key=lambda i: d2(pts[i % n], f))
        out.append(at)
    return out


def comeback(race, line, closed, bots):
    """(places climbed, name, from, to, [seconds of each place gained]) for the
    person who climbed furthest - from their worst place after the lights to
    where they finished - or None if nobody passed anybody."""
    hz, cars = race["hz"], [c for c in race["cars"] if c.get("frames")]
    if len(cars) < 2:
        return None
    prog = [progress(c["frames"], line, closed) for c in cars]
    end = min(len(f) for f in prog)
    done = [int(c["ms"] * hz / 1000) if c.get("ms") else None for c in cars]
    places = []
    for k in range(end):
        # A car over the line stays ahead of everybody still driving, in finish order.
        key = lambda i: (0, cars[i]["ms"]) if done[i] is not None and k >= done[i] else (1, -prog[i][k])
        order = sorted(range(len(cars)), key=key)
        places.append({i: order.index(i) + 1 for i in order})
    best = None
    for i, c in enumerate(cars):
        if c["name"] in bots or not c.get("ms"):
            continue
        run = [p[i] for p in places[hz:]]        # from a second after the green
        if not run:
            continue
        worst = max(run)
        k0 = run.index(worst)
        gains = [k for k in range(k0 + 1, len(run)) if run[k] < run[k - 1]]
        climb = worst - run[-1]
        if climb and (best is None or climb > best[0]):
            best = (climb, c["name"], worst, run[-1], [(hz + k) / hz for k in gains])
    return best


def score(r, posted):
    """How much a race summary is worth filming, before fetching its frames:
    two or more people over the line, and close. None if not a candidate."""
    done = sorted((c for c in r["cars"] if c["ms"]), key=lambda c: c["ms"])
    if r["id"] in posted or r["id"] in VETOED or len(done) < 2 or sum(not c["bot"] for c in done) < 2:
        return None
    return done[1]["ms"] - done[0]["ms"]


def best_race(races, posted, look=None):
    """The best race not yet posted: the biggest climb through the field by a
    person, a climb to the win counting a place more, and a close finish worth
    up to one more - so a finish inside 0.75s with no passing still qualifies. `look(race)` is (climbed, to) or None; it fetches frames,
    so only the twenty closest candidates are looked at."""
    cands = sorted(((g, r) for r in races if (g := score(r, posted)) is not None),
                   key=lambda c: c[0])[:20]
    best = None
    for gap, r in cands:
        cb = look(r) if look else None
        val = max(0.0, 1.0 - gap / RACE_GAP_MS)
        if cb:
            val += cb[0] + (cb[1] == 1)
        if val >= 0.5 and (best is None or val > best[0]):
            best = (val, r["id"])
    return best and best[1]


def look_at(r):
    """`best_race`'s `look`, off the live site."""
    race = get("/api/race/%d" % r["id"])
    track = get("/api/track/" + r["track"])
    cb = comeback(race, track["line"], track["closed"], {c["name"] for c in r["cars"] if c["bot"]})
    return cb and (cb[0], cb[3])


def records_since(rows, seen):
    """Every lap on a board that was a world record when it was set, since the
    record `seen` - in the order they were set. A burst of records inside ten
    minutes is all still on the board (one row per driver), so each one that
    beat the running best at its own `at` was a record, and posts. The only
    one lost is a holder's own lap they have since improved, whose replay is
    gone. A board without `at` (before it was served) gives just its top."""
    top = [rows[0][1]["id"], rows[0][1]["time_ms"]]
    if seen == top:
        return []
    if seen is None or not all("at" in r for _, r in rows):
        return [top]
    out, best = [], seen[1]
    for r in sorted((r for _, r in rows if [r["id"], r["time_ms"]] != seen),
                    key=lambda r: r["at"]):
        if r["time_ms"] < best:
            out.append([r["id"], r["time_ms"]])
            best = r["time_ms"]
    return out or [top]


def name_of(item):
    """The reel's file name: the time is in it because a holder beating their
    own record keeps the lap id, and that is a new reel, not a repost."""
    return "race-%d" % item[1] if item[0] == "race" else "%s-%d-%d" % tuple(item[:3])


def plan(state, b, races=(), look=None, urgent=False, posted_already=lambda name: False):
    """(every reel to film now, the state once they are posted).

    Every world record set since the last look, oldest first, and - unless
    `urgent` - one more off the queue or a race. `posted_already(name)` is
    what keeps a run that half failed from posting a reel twice."""
    if state is None:
        state = {"seen": {}, "queue": prefill(b)}
        fresh = False
    else:
        fresh = True
    new = list(state.get("new", []))
    found = []
    for slug, rows in b.items():
        if not rows:
            continue
        if fresh:
            at = {r["id"]: r.get("at", "") for _, r in rows}
            found += [(at[i], [slug, i, ms, 1]) for i, ms in records_since(rows, state["seen"].get(slug))]
        state["seen"][slug] = [rows[0][1]["id"], rows[0][1]["time_ms"]]
    new += [q for _, q in sorted(found, key=lambda f: f[0])]
    queue = [q for q in state["queue"] if q[3] == 1]
    races_done, n = state.get("races", []), state.get("n", 0)
    on_board = lambda q: any(r["id"] == q[1] and r["time_ms"] == q[2] for _, r in b.get(q[0], []))
    out = [q for q in new if on_board(q) and not posted_already(name_of(q))]
    if not urgent:
        race = best_race(races, races_done, look) if n % RACE_EVERY == RACE_EVERY - 1 else None
        if race:
            out.append(["race", race, 0, 0])
            races_done = races_done + [race]
        else:
            while queue:
                q = queue.pop(0)
                if on_board(q) and not posted_already(name_of(q)):
                    out.append(q)
                    break
    return out, {"seen": state["seen"], "queue": queue, "races": races_done, "n": n + len(out)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reels")
    ap.add_argument("--urgent", action="store_true", help="only new world records")
    args = ap.parse_args()
    try:
        state = get("/static/reels/wr-state.json")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        state = None
    races = [] if args.urgent else get("/api/races?limit=300")["races"]
    items, after = plan(state, boards(), races, look_at, args.urgent, posted_already)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "wr-state.next.json"), "w") as f:
        json.dump(after, f)
    # One JSON list for the Action's matrix: the reel's name and how to film it.
    print(json.dumps([{"name": name_of(q), "args": (
        "--race %d" % q[1] if q[0] == "race" else "%s --lap %d --rank %d" % (q[0], q[1], q[3]))
        + " --name " + name_of(q)} for q in items]))


def posted_already(name):
    """`post_reel.py` leaves `<name>.posted` beside a reel once Instagram has it."""
    try:
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/static/reels/%s.posted" % name, method="HEAD"), timeout=30)
        return True
    except urllib.error.HTTPError:
        return False


def _check():
    lap = lambda i, n, ms: {"id": i, "name": n, "time_ms": ms, "has_ghost": True}
    b = {"a": [(1, lap(1, "tyler", 100)), (2, lap(2, "tyler2", 101))],
         "b": [(1, lap(3, "tyler", 200)), (3, lap(4, "sam", 205))]}
    items, st = plan(None, b)
    assert len(items) == 1 and len(st["queue"]) == 1 and items[0][3] == 1, (items, st)
    assert {q[0] for q in st["queue"] + items} == {"a", "b"}
    # Nothing new: one off the queue, and an urgent run films nothing.
    assert plan(json.loads(json.dumps(st)), b, urgent=True)[0] == []
    items2, st2 = plan(json.loads(json.dumps(st)), b)
    assert items2 == st["queue"] and st2["queue"] == []
    # A burst: sam beats tyler at 1, then tyler beats sam at 2, then ann sets
    # a lap at 3 that is quick but no record. Both records post, in order.
    at = lambda r, t: dict(r, at=t)
    b["a"] = [(1, at(lap(1, "tyler", 97), "2")), (2, at(lap(9, "sam", 98), "1")),
              (3, at(lap(5, "ann", 99), "3"))]
    b["b"] = [(1, at(lap(3, "tyler", 200), "0"))]
    items3, st3 = plan(json.loads(json.dumps(st2)), b, urgent=True)
    assert items3 == [["a", 9, 98, 1], ["a", 1, 97, 1]], items3
    # ...and with them posted, nothing more.
    assert plan(st3, b, urgent=True)[0] == []
    # A run that half failed re-plans, skipping what did post.
    items4, _ = plan(json.loads(json.dumps(st2)), b, urgent=True,
                     posted_already=lambda n: n == "a-9-98")
    assert items4 == [["a", 1, 97, 1]], items4
    # #2-all-time laps left in an old queue are dropped.
    old = {"seen": st3["seen"], "queue": [["b", 4, 205, 2], ["b", 3, 200, 1]]}
    assert plan(old, b)[0] == [["b", 3, 200, 1]]
    # Every third post is the best race between people, never twice.
    car = lambda n, ms, bot=False: {"name": n, "ms": ms, "bot": bot}
    races = [{"id": 7, "cars": [car("a", 1000), car("b", 1100)]},
             {"id": 8, "cars": [car("a", 1000), car("b", 1050)]},
             {"id": 9, "cars": [car("a", 1000), car("x", 1001, True)]},
             {"id": 10, "cars": [car("a", 1000), car("b", 9000)]}]
    b = {"a": [(1, lap(1, "tyler", 100))]}
    st = {"seen": {"a": [1, 100]}, "queue": [["a", 1, 100, 1]] * 9, "n": 2}
    items, st = plan(st, b, races)
    assert items == [["race", 8, 0, 0]] and st["n"] == 3, items
    items, st = plan(st, b, races)
    assert items[0][0] == "a", items
    st["n"] = 5
    assert plan(st, b, races)[0] == [["race", 7, 0, 0]]
    st["n"], st["races"] = 5, [7, 8]
    assert plan(st, b, races)[0][0][0] == "a"     # 9 is bots, 10 too far apart
    # A comeback outranks a closer finish with no passing in it.
    look = lambda r: (3, 1) if r["id"] == 7 else None
    assert best_race(races, [], look) == 7
    # Running order off the frames: b starts behind a, passes, and wins.
    line = [{"p": [float(x), 0.0, 0.0]} for x in range(100)]
    fr = lambda xs: [[x, 0.0, 0.0] for x in xs]
    race = {"hz": 2, "cars": [
        {"name": "a", "ms": 6000, "frames": fr([10, 20, 30, 40, 50, 60, 70, 80, 90, 99, 99, 99, 99])},
        {"name": "b", "ms": 5000, "frames": fr([5, 10, 20, 35, 55, 70, 85, 95, 99, 99, 99, 99, 99])}]}
    cb = comeback(race, line, False, set())
    assert cb[:4] == (1, "b", 2, 1), cb
    assert comeback(race, line, False, {"b"}) is None
    print("ok")


if __name__ == "__main__":
    import sys
    _check() if sys.argv[1:] == ["--check"] else main()
