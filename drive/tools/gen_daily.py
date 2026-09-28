"""Fill the daily queue: propose tracks, throw most of them away, keep the rest.

    venv/bin/python tools/gen_daily.py 50          # fifty into the queue
    venv/bin/python tools/gen_daily.py 50 --dry-run
    venv/bin/python tools/gen_daily.py 5 --from 9000

**The loop is the whole tool.** `tracks.generate` lays a seeded walk; this builds
it through the same `tracks.from_document` the editor and the play page use, runs
the same battery `maker._run_checks` runs, prices the lap with the same
`laptime`, and discards anything that fails or lands outside 30-40 seconds. About
half of what it proposes survives, at ~0.2s a candidate, so fifty keepers is
twenty seconds of laptop.

Rejecting rather than steering is deliberate and it is what keeps this honest.
A generator that *guaranteed* its output would be a second, weaker copy of
`checks.py`, and it would drift the day somebody adds a check. Here a new check
simply lowers the accept rate, and nothing gets into the queue that the editor
would have refused from a person.

What comes out is an ordinary **queued** `drive_user_tracks` row - the same thing
a player submitting from `/make` produces - owned by Chinmay's account. So
`/admin/tracks` already reviews them, the Drive button already drives them, and
approving one is the same click. Nothing here is a second publishing path.

**Nobody has driven these, and that is the one gate they skip.** A person cannot
submit a track they have not finished, which proves finishability by
demonstration. A generated one is proved by `laptime` getting a racing line round
it instead, which is weaker - it is why these go to the queue rather than
straight live, and why the review is a lap and not a glance.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tracks as tracks_mod                                    # noqa: E402
from tracks import checks, generate, moves as moves_mod        # noqa: E402

# The account every generated track belongs to: Chinmay's own, so a daily's
# card says "by Chinmay". A real row in `users` rather than a null author,
# because a track with no author reads as one of the editor's starter shapes -
# which cannot be published.
DAILY_USER = "chinmay"

# What a generated track is called until it is approved and becomes `Daily #N`
# (`maker._number_daily`). The generator's own names were not wanted anywhere,
# so this is all a queued one is ever shown as; the seed makes its slug unique.
QUEUE_NAME = "Daily (in review)"


def pool_looks():
    """Every look in the pool. A void one makes a stunt track and a grounded one
    a circuit (`generate.is_void`); keys tied to one track's own layout are
    stripped by `generate.borrow`."""
    return [{"slug": t["slug"], "name": t["name"], "pal": t.get("pal") or {}}
            for t in tracks_mod.TRACKS
            if t.get("pal") and t["slug"] not in INDOOR_LOOKS]


# Looks that are a building rather than a place: without its warehouse the
# Costco's palette is a flat grey plain, and "make the theme more interesting"
# was the review note on the one daily that had it.
INDOOR_LOOKS = ("costco",)


def look_order(looks, n, avoid=(), seed=0):
    """Which look each of `n` dailies gets, in queue order.

    The queue is approved oldest first and each approval takes the next free
    day, so queue order is day order: neighbours must differ, and the first few
    must differ from the dailies already scheduled (`avoid`) - "same theme as
    daily #1" was a review note. Every look is used once before any is used
    twice.
    """
    import random
    rng = random.Random(seed)
    avoid = list(avoid)
    out = []
    while len(out) < n:
        deck = looks[:]
        rng.shuffle(deck)
        recent = (avoid + [l["slug"] for l in out])[-min(8, len(looks) - 1):]
        deck.sort(key=lambda l: l["slug"] in recent)
        out += deck
    return out[:n]


def _move_at(doc, station):
    """Index of the move that laid this station, off the builder's own spans."""
    spans = []
    moves_mod.build(doc, spans=spans)
    for k, (a, b) in enumerate(spans):
        if a <= station <= b:
            return k
    return None


def _wall_move(doc, k):
    """Barriers on both edges of move `k` and nowhere else: `rail` is sticky, so
    the move after it is handed back whatever was in force before."""
    ms = doc["moves"]
    cur = "lr" if doc.get("rails") else ""
    for m in ms[:k + 1]:
        if "rail" in m:
            cur = m["rail"]
    if ms[k]["t"] not in moves_mod.LAYS_ROAD or cur == "lr":
        return False
    ms[k]["rail"] = "lr"
    if k + 1 < len(ms) and "rail" not in ms[k + 1]:
        ms[k + 1]["rail"] = cur
    return True


def repair(doc, cut):
    """Close one shortcut from `checks.shortcuts`, in place. False if it cannot.

    A cut across the grass gets barriers on the two stretches it joins. A drop
    gets barriers on the stretch it leaves from, and if that is already walled
    - a kicker or a wall of death can still throw a car over - a checkpoint
    between take-off and landing, which is how Rickety Rails' loop was closed,
    placed two-thirds of the way along so it is nearer the landing than the
    take-off and not under it. Barriers are only ever added here, so a track
    ends up walled exactly where leaving the road would pay. The document is
    re-judged after either, so a repair that made something else wrong is
    caught.
    """
    if cut["kind"] == "grass":
        a, b = _move_at(doc, cut["i"]), _move_at(doc, cut["j"])
        if a is None or b is None:
            return False
        done = _wall_move(doc, b)
        return _wall_move(doc, a) or done
    off = _move_at(doc, cut["i"])
    if off is not None and _wall_move(doc, off):
        return True
    at = _move_at(doc, cut["i"] + (cut["j"] - cut["i"]) * 2 // 3)
    if at is None or at + 1 >= len(doc["moves"]) - 1:
        return False
    if doc["moves"][at + 1]["t"] == "cp":
        return False
    doc["moves"].insert(at + 1, {"t": "cp"})
    return True


def bot_laps(track, levels=("max", "easy"), max_t=None):
    """Send bots round it. A daily nobody has driven is only proved finishable
    by something driving it, and the room bots are the game's own physics -
    `botsim.solo_lap`, the calibrator's harness. `None` if every level got
    round, else what went wrong."""
    import json as json_mod
    import botsim
    slug = track["slug"]
    tracks_mod.set_resolver(lambda s: track if s == slug else None)
    rt = botsim.runtime()
    rt.ctx.eval("TRACKS = TRACKS.filter(t => !t.slug.startsWith('daily-cand'));"
                "TRACKS.push(%s);" % json_mod.dumps(track))
    try:
        for lvl in levels:
            out = botsim.solo_lap(slug, lvl, max_t=max_t or track["ideal"] * 2.5)
            if not out.get("finished"):
                return "%s bot stuck at %.0f%%" % (lvl, 100 * out.get("progress", 0))
    finally:
        rt.ctx.eval("delete BUILT[%s];" % json_mod.dumps(slug))
        tracks_mod.set_resolver(None)
    return None


# A daily walled end to end is no fun to drive, and one that needed barriers
# over most of its lap to close its shortcuts is a layout that doubles back on
# itself too much - better dropped than fenced.
MAX_WALLED = 0.4


def judge(doc, bot=True):
    """Build it, check it, price it. Returns `(track, why_not)`.

    `why_not` is a list of short reasons, empty when the candidate is good. It
    is printed rather than stored: what a rejected seed was wrong about is only
    interesting while the generator is being tuned, and keeping every reject
    would be a table of tracks nobody will ever drive.
    """
    # **Built twice, priced once.** The first build is untimed and exists only
    # so `settle_ground` can see where the road actually goes - an untimed
    # ribbon is ~5ms where `laptime.ideal_lap` is ~550ms, so paying for a second
    # one is cheaper than the alternative, which is a ground plane guessed in
    # advance and drawn straight through the tarmac.
    slug = "daily-cand-%s" % (doc.get("generated") or {}).get("seed", 0)
    try:
        # Shortcuts first, on the untimed ribbon, because closing one moves the
        # road: up to eight repairs, and a track that still has one is dropped.
        for _ in range(9):
            rough = tracks_mod.from_document(slug, doc, timed=False)
            cuts = checks.shortcuts(rough)
            if not cuts:
                break
            if not repair(doc, cuts[0]):
                return None, ["a %s shortcut worth %.0f units that could not "
                              "be closed" % (cuts[0]["kind"], cuts[0]["gain"])]
        else:
            return None, ["still a shortcut after eight repairs"]
        generate.settle_ground(doc, rough)
        track = tracks_mod.from_document(slug, doc, timed=True)
    except Exception as e:
        return None, ["%s: %s" % (type(e).__name__, str(e)[:60])]

    why = []
    # The defect `test_the_road_is_never_buried_in_its_own_ground` covers, which
    # lives in the pool's suite rather than in `checks.py` - so it is asserted
    # here too rather than trusted to `settle_ground` having worked.
    low = min(e["p"][1] for e in track["line"])
    if track["ground"] is not None and low < track["ground"] - 0.01:
        why.append("road buried %.1f below its own ground" % (track["ground"] - low))
    if checks.self_proximity(track):
        why.append("runs too close to itself")
    radii = sorted({round(abs(1.0 / e["curv"]), 1)
                    for e in track["line"] if abs(e.get("curv") or 0) > 1e-6})
    if not radii or radii[0] < checks.MIN_RADIUS:
        why.append("a corner nothing can drive")
    if len(radii) < checks.RADII_DISTINCT:
        why.append("every corner the same radius")
    if radii and radii[-1] / radii[0] < checks.RADII_SPREAD:
        why.append("no spread of corner radii")
    if track.get("pole_side") not in (-1, 1):
        why.append("turn one too vague to put a grid behind")

    ceil = track.get("gate_ceil")
    line = track["line"]
    if ceil is None or not (checks.GATE_CEIL_MIN <= ceil <= checks.GATE_CEIL_MAX):
        why.append("checkpoint ceiling out of range")
    elif any(ceil >= abs(line[i]["p"][1] - line[j]["p"][1])
             for i, j in checks.crossings(track)):
        why.append("a checkpoint creditable from above")

    if sum(1 for m in doc["moves"] if m.get("t") == "cp") < checks.MIN_CHECKPOINTS:
        why.append("not enough checkpoints")

    for lvl, _at, text in moves_mod.advise(doc):
        if lvl == "refuse":
            why.append(text[:60])

    ideal = track.get("ideal")
    if ideal is None:
        why.append("no lap time")
    elif not (generate.TARGET_LOW <= ideal <= generate.TARGET_HIGH):
        why.append("%.1fs, wanted %.0f-%.0f"
                   % (ideal, generate.TARGET_LOW, generate.TARGET_HIGH))

    med = track.get("medals")
    if not med or not (med["gold"] < med["silver"] < med["bronze"]):
        why.append("medals out of order")
    road = [e for e in line if not e.get("air")]
    walled = sum(1 for e in road if e.get("wl") or e.get("wr")) / max(1, len(road))
    if walled > MAX_WALLED:
        why.append("%.0f%% walled after closing its shortcuts" % (100 * walled))
    if (doc.get("ground") is None and not doc.get("exposed")
            and not doc.get("rails")):
        why.append("floats with no barriers and is not exposed")
    if not why and bot:
        stuck = bot_laps(track)
        if stuck:
            why.append(stuck)
    return track, why


def propose(n, first_seed=0, verbose=True, avoid=(), per_look=80):
    """`n` documents that pass everything, one per look in `look_order`."""
    looks = pool_looks()
    kept, seed, tried = [], first_seed, 0
    for look in look_order(looks, n, avoid, seed=first_seed):
        for _ in range(per_look):
            tried += 1
            doc = generate.generate(seed, looks, look=look)
            track, why = judge(doc)
            seed += 1
            if not why:
                kept.append((seed - 1, doc, track))
                if verbose:
                    print("  keep  seed %-8d %5.1fs  %-7s %s"
                          % (seed - 1, track["ideal"], doc["generated"]["kind"],
                             look["slug"]), flush=True)
                break
            if verbose and tried <= 12:
                print("  drop  seed %-8d %s" % (seed - 1, "; ".join(why)), flush=True)
        else:
            print("  ! nothing kept for %s in %d tries" % (look["slug"], per_look))
    if verbose:
        print("kept %d of %d candidates (%.0f%%)"
              % (len(kept), tried, 100.0 * len(kept) / max(1, tried)))
    return kept


def store(kept):
    """Each keeper as a queued row, exactly as a person's submission is."""
    import app                                                  # noqa: E402
    from models import DriveUserTrack, User, db                 # noqa: E402
    import maker                                                # noqa: E402
    import json as json_mod
    from datetime import datetime
    from tracks import plan as plan_mod

    with app.app.app_context():
        author = User.query.filter(
            db.func.lower(User.username) == DAILY_USER).first()
        if author is None:
            raise SystemExit("there is no `%s` account to author the dailies"
                             % DAILY_USER)
        made = []
        for seed, doc, track in kept:
            if track is None:
                track = tracks_mod.from_document("daily-candidate", doc, timed=True)
            slug = maker._free_slug("daily draft %d" % seed)
            if slug is None:
                print("  ! no free slug for seed %d, skipped" % seed)
                continue
            doc = dict(doc, slug=slug, name=QUEUE_NAME)
            row = DriveUserTrack(
                slug=slug, author_id=author.id, status="queued",
                name=doc["name"], difficulty=doc["difficulty"],
                doc_json=json_mod.dumps(doc, separators=(",", ":")),
                geom_hash=moves_mod.fingerprint(track, None),
                look_hash=moves_mod.look_fingerprint(doc),
                plan_path=plan_mod.path_for(track.get("line") or ()),
                queued_at=datetime.utcnow())
            db.session.add(row)
            made.append(slug)
        db.session.commit()
        return made


def clear_queue():
    """Tombstone every generated track still queued or sent back, as the admin
    queue's Delete does: `status = "deleted"`, the row kept so its slug is never
    handed out again. Live dailies are not touched."""
    import app                                                  # noqa: E402
    from models import DriveUserTrack, db                       # noqa: E402
    with app.app.app_context():
        rows = [r for r in DriveUserTrack.query.filter(
                    DriveUserTrack.status.in_(("queued", "needs_fix"))).all()
                if r.doc.get("generated")]
        for r in rows:
            r.status = "deleted"
        db.session.commit()
        return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("count", type=int, nargs="?", default=10,
                    help="how many to put in the queue")
    ap.add_argument("--from", dest="seed", type=int, default=None,
                    help="first seed to try (default: the clock, so two runs "
                         "do not propose the same tracks)")
    ap.add_argument("--dry-run", action="store_true",
                    help="propose and print, write nothing")
    ap.add_argument("--avoid", default="",
                    help="comma-separated looks the first few must not use: "
                         "the ones on the dailies already scheduled")
    ap.add_argument("--save", help="write the keepers to this JSON file instead "
                                   "of the database (generate on a laptop)")
    ap.add_argument("--load", help="queue the keepers from a --save file (on "
                                   "the box) instead of generating any")
    ap.add_argument("--replace-queue", action="store_true",
                    help="first tombstone every generated track still in the "
                         "queue or sent back")
    a = ap.parse_args(argv)

    import json as json_mod
    if a.load:
        with open(a.load) as f:
            kept = [(k["seed"], k["doc"], None) for k in json_mod.load(f)]
    else:
        seed = a.seed
        if seed is None:
            import time
            seed = int(time.time()) % 1_000_000 * 1000
        kept = propose(a.count, seed,
                       avoid=[x for x in a.avoid.split(",") if x])
    if a.save:
        with open(a.save, "w") as f:
            json_mod.dump([{"seed": sd, "doc": doc} for sd, doc, _ in kept], f)
        print("\nsaved %d to %s" % (len(kept), a.save))
        return 0
    if a.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if a.replace_queue:
        print("tombstoned %d queued or sent-back generated tracks" % clear_queue())
    made = store(kept)
    print("\nqueued %d for review: %s" % (len(made), ", ".join(made)))
    print("review them at /admin/tracks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
