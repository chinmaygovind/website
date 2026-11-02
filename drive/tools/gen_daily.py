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
import math
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
    from tracks import daily_looks
    return [{"slug": t["slug"], "name": t["name"], "pal": t.get("pal") or {}}
            for t in tracks_mod.TRACKS
            if t.get("pal") and t["slug"] not in INDOOR_LOOKS] + daily_looks.LOOKS


# Looks that are a building rather than a place: without its warehouse the
# Costco's palette is a flat grey plain, and "make the theme more interesting"
# was the review note on the one daily that had it.
INDOOR_LOOKS = ("costco",)


def look_order(looks, n, avoid=(), seed=0, kinds=None):
    """Which look each of `n` dailies gets, in queue order.

    The queue is approved oldest first and each approval takes the next free
    day, so queue order is day order: neighbours must differ, and the first few
    must differ from the dailies already scheduled (`avoid`) - "same theme as
    daily #1" was a review note. Every look is used once before any is used
    twice.

    `kinds[k]`, when given, is "stunt", "circuit" or None for day `k`: a tier
    that has to be one or the other (`generate.TIERS`) is dealt the freshest
    look of that kind instead of the next card.
    """
    import random
    rng = random.Random(seed)
    avoid = list(avoid)
    out = []
    deck = []
    kinds = kinds or [None] * n
    for k in range(n):
        if not deck:
            deck = looks[:]
            rng.shuffle(deck)
            # The dailies-only looks are four in thirty-odd, and they are the
            # new thing - so every third day leads with one.
            from tracks import daily_looks
            own = {l["slug"] for l in daily_looks.LOOKS}
            mine = [l for l in deck if l["slug"] in own]
            rest = [l for l in deck if l["slug"] not in own]
            deck = []
            while mine or rest:
                if mine and len(deck) % 3 == 0:
                    deck.append(mine.pop())
                elif rest:
                    deck.append(rest.pop())
                else:
                    deck.append(mine.pop())
        recent = (avoid + [l["slug"] for l in out])[-min(8, len(looks) - 1):]
        deck.sort(key=lambda l: l["slug"] in recent)
        want = kinds[k]
        fits = [l for l in deck if want is None
                or (want == "stunt") == generate.is_void(l)]
        if not fits:
            fits = [l for l in looks if (want == "stunt") == generate.is_void(l)]
            fits.sort(key=lambda l: l["slug"] in recent)
        pick = fits[0]
        if pick in deck:
            deck.remove(pick)
        out.append(pick)
    return out


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

# Only a cut that skips this much road is closed. Smaller ones are left in,
# because finding them is what people grind a track for: Rickety Rails closes
# only its 100-unit chords, and its record is 0.80 of the bot's ideal lap
# against 0.86-0.89 for the tracks with nothing to find. Closing every cut over
# `checks.CUT_MIN_GAIN` made dailies with nothing to find.
CUT_CLOSE = 70.0

# **Some days keep one big shortcut on purpose** (Nov 2026): a drop off a high
# stretch onto a lower one, on a track over the void, so it saves a couple of
# seconds landed and costs a respawn missed. Only some days - a cut every day
# is a gimmick, so one a week, on the first tier 3+ stunt day of it - and only
# on stunt tracks, because a cut across the grass is no
# risk at all. Up to this much road skipped; more is a different track.
CUT_KEEP_MAX = 260.0


def _same_cut(a, b):
    return abs(a["i"] - b["i"]) <= 25 and abs(a["j"] - b["j"]) <= 25


def keepable(cuts):
    """The cut a designed-shortcut day keeps: the biggest drop in range."""
    for c in cuts:
        if c["kind"] == "drop" and c["gain"] <= CUT_KEEP_MAX:
            return c
    return None

# A pad at the top of a climb is a pad on a crest: the road levels off under
# it, the car goes light, and only a car on the right line touches it at all.
# Daily #9's last pad had a 30% grade ending at it and "you have to get a
# finicky angle" was the note. Steepest grade allowed in the run-up; the pool's
# own worst is Citadel's 0.12, which was placed by hand.
PAD_CLIMB = 0.1
PAD_RUNUP = 14.0


def pads_on_climbs(track):
    """Station of every pad whose run-up climbs steeper than `PAD_CLIMB`."""
    line = track["line"]
    out = []
    for s in range(1, len(line)):
        if not line[s].get("bp") or line[s - 1].get("bp"):
            continue
        i, run = s, 0.0
        while i > 0 and run < PAD_RUNUP:
            a, b = line[i - 1]["p"], line[i]["p"]
            flat = math.hypot(b[0] - a[0], b[2] - a[2])
            if not line[i].get("air") and b[1] - a[1] > PAD_CLIMB * max(flat, 1e-6):
                out.append(s)
                break
            run += flat
            i -= 1
    return out


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
        want_cut = (doc.get("generated") or {}).get("cut")
        kept = None
        for _ in range(9):
            rough = tracks_mod.from_document(slug, doc, timed=False)
            cuts = checks.shortcuts(rough, min_gain=CUT_CLOSE)
            if want_cut:
                kept = keepable(cuts)
                if kept is None:
                    return None, ["no drop cut to keep"]
                cuts = [c for c in cuts if not _same_cut(c, kept)]
            if not cuts:
                break
            if not repair(doc, cuts[0]):
                return None, ["a %s shortcut worth %.0f units that could not "
                              "be closed" % (cuts[0]["kind"], cuts[0]["gain"])]
        else:
            return None, ["still a shortcut after eight repairs"]
        if kept:
            doc["generated"]["cut"] = {"i": kept["i"], "j": kept["j"],
                                       "gain": kept["gain"]}
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
    else:
        lo, hi = generate.target(doc)
        if not (lo <= ideal <= hi):
            why.append("%.1fs, wanted %.0f-%.0f" % (ideal, lo, hi))

    med = track.get("medals")
    if not med or not (med["gold"] < med["silver"] < med["bronze"]):
        why.append("medals out of order")
    road = [e for e in line if not e.get("air")]
    walled = sum(1 for e in road if e.get("wl") or e.get("wr")) / max(1, len(road))
    if walled > MAX_WALLED:
        why.append("%.0f%% walled after closing its shortcuts" % (100 * walled))
    if pads_on_climbs(track):
        why.append("a boost pad at the top of a climb")
    if (doc.get("ground") is None and not doc.get("exposed")
            and not doc.get("rails")):
        why.append("floats with no barriers and is not exposed")
    if not why and bot:
        stuck = bot_laps(track)
        if stuck:
            why.append(stuck)
    return track, why


def propose(n, first_seed=0, verbose=True, avoid=(), per_look=80, start=None):
    """`n` documents that pass everything, one per look in `look_order`.

    With `start` (a date), day `k` is `start + k`: it gets that weekday's tier
    and the date is written into the document, so approving it lands it on the
    day it was made for (`maker._day_for`) rather than the next free one."""
    from datetime import timedelta
    looks = pool_looks()
    days = [start + timedelta(days=k) for k in range(n)] if start else [None] * n
    tiers = [generate.tier_for(d) if d else None for d in days]
    kinds = [generate.TIERS[t]["kind"] if t else None for t in tiers]
    cut_weeks = set()
    kept, seed, tried = [], first_seed, 0
    for look, day, tier in zip(look_order(looks, n, avoid, seed=first_seed,
                                          kinds=kinds), days, tiers):
        week = day.isocalendar()[:2] if day else None
        cut = bool(tier and tier >= 3 and generate.is_void(look)
                   and week not in cut_weeks)
        if cut:
            cut_weeks.add(week)
        for _ in range(per_look):
            tried += 1
            doc = generate.generate(seed, looks, look=look, tier=tier, cut=cut)
            if day:
                doc["generated"]["day"] = day.isoformat()
            seed += 1
            # Neighbouring days lean on different set pieces, as they get
            # different looks - the same signature twice running reads as the
            # same track again.
            if kept and (kept[-1][1]["generated"]["signature"]
                         == doc["generated"]["signature"]):
                continue
            track, why = judge(doc)
            if not why:
                kept.append((seed - 1, doc, track))
                if verbose:
                    g = doc["generated"]
                    print("  keep  seed %-8d %5.1fs  %-7s %-12s %s tier %s %s%s"
                          % (seed - 1, track["ideal"], g["kind"], look["slug"],
                             g.get("day") or "", tier or "-", g["signature"],
                             "  cut %.0f" % g["cut"]["gain"] if g.get("cut") else ""),
                          flush=True)
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
    ap.add_argument("--start", help="first day these are for (YYYY-MM-DD): "
                                    "each gets its weekday's tier and is "
                                    "scheduled on that day when approved")
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
        from datetime import date
        kept = propose(a.count, seed,
                       avoid=[x for x in a.avoid.split(",") if x],
                       start=date.fromisoformat(a.start) if a.start else None)
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
