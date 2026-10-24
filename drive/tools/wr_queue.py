"""World-record reels: which lap to film next, off a queue kept on the box.

    python3 tools/wr_queue.py --out reels    # prints "slug lap rank", or nothing

Runs in the wr-reel Action every six hours. Stdlib only.

**The state is `drive/static/reels/wr-state.json` on the box**, public like
`last-posted.txt`, so this reads it with nothing but a URL:

    {"seen": {slug: [lap id, time_ms]}, "queue": [[slug, lap id, time_ms, rank], ...]}

`seen` is the record each track had last time anybody looked, and a top of the
board that differs from it is a **new world record, which goes to the front**.
The first run, with no state at all, fills the queue with each track's record
and its best lap by anybody else, shuffled so the names alternate.

**The record is (lap id, time), not the lap id.** A board keeps one row per
driver per track, so a holder beating their own record changes the time on
the same id - and the watch page would then play the new lap under the old
card. A queued lap whose time has moved since is dropped, and the new one is
already in the queue as a fresh record.

**A beaten record still posts, as a record.** Its rank was fixed when it was
queued, and the card says what it was when it was set.

Writes the state as it will be once this one is posted to
`<out>/wr-state.next.json`; the Action swaps it in only after Instagram has
the reel, so a failed run re-plans the same lap rather than losing it.
"""

import argparse
import json
import os
import random
import urllib.error
import urllib.request

BASE = "https://drive.cgovind.com"


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
    """Every record, and the best lap by somebody else, interleaved."""
    slugs = [s for s in b if b[s]]
    random.Random(1).shuffle(slugs)
    recs, others = [], []
    for slug in slugs:
        rank, wr = b[slug][0]
        recs.append([slug, wr["id"], wr["time_ms"], 1])
        rest = next(((k, r) for k, r in b[slug] if r["name"] != wr["name"]), None)
        if rest:
            others.append([slug, rest[1]["id"], rest[1]["time_ms"], rest[0]])
    # Half a lap of the queue apart, so one track's two reels are never adjacent.
    others = others[len(others) // 2:] + others[:len(others) // 2]
    out = []
    for i in range(max(len(recs), len(others))):
        out += recs[i:i + 1] + others[i:i + 1]
    return out


def plan(state, b):
    """(the lap to film or None, the state after posting it)."""
    if state is None:
        state = {"seen": {}, "queue": prefill(b)}
        fresh = False
    else:
        fresh = True
    new = []
    for slug, rows in b.items():
        if not rows:
            continue
        top = [rows[0][1]["id"], rows[0][1]["time_ms"]]
        if fresh and state["seen"].get(slug) != top:
            new.append([slug] + top + [1])
        state["seen"][slug] = top
    queue = new + state["queue"]
    while queue:
        item = queue.pop(0)
        slug, lap, ms, _ = item
        if any(r["id"] == lap and r["time_ms"] == ms for _, r in b.get(slug, [])):
            return item, {"seen": state["seen"], "queue": queue}
    return None, {"seen": state["seen"], "queue": queue}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reels")
    args = ap.parse_args()
    try:
        state = get("/static/reels/wr-state.json")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        state = None
    item, after = plan(state, boards())
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "wr-state.next.json"), "w") as f:
        json.dump(after, f)
    if item:
        print("%s %d %d" % (item[0], item[1], item[3]))


def _check():
    lap = lambda i, n, ms: {"id": i, "name": n, "time_ms": ms, "has_ghost": True}
    b = {"a": [(1, lap(1, "tyler", 100)), (2, lap(2, "tyler2", 101))],
         "b": [(1, lap(3, "tyler", 200)), (3, lap(4, "sam", 205))]}
    item, st = plan(None, b)
    assert len(st["queue"]) == 3 and item[3] == 1, (item, st)
    assert {q[0] for q in st["queue"] + [item]} == {"a", "b"}
    # Nothing changed: the queue just pops.
    item2, st2 = plan(json.loads(json.dumps(st)), b)
    assert item2 == st["queue"][0] and len(st2["queue"]) == 2
    # A new record jumps the queue; the beaten one stays queued as a record.
    b["a"] = [(1, lap(9, "sam", 99)), (2, lap(1, "tyler", 100))]
    item3, st3 = plan(json.loads(json.dumps(st2)), b)
    assert item3 == ["a", 9, 99, 1], item3
    # The holder improving their own lap makes the queued copy stale.
    b["b"] = [(1, lap(3, "tyler", 190)), (3, lap(4, "sam", 205))]
    st3["queue"] = [["b", 3, 200, 1]]
    item4, st4 = plan(st3, b)
    assert item4 == ["b", 3, 190, 1], item4
    # ...and is dropped when its turn comes rather than filmed under the old time.
    assert plan(st4, b)[0] is None
    print("ok")


if __name__ == "__main__":
    import sys
    _check() if sys.argv[1:] == ["--check"] else main()
