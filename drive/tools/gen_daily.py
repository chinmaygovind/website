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
a player submitting from `/make` produces - owned by the `daily` account. So
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

# The account every generated track belongs to. A real row in `users` rather
# than a null author, because `author_id` is what `_may_edit` and the gallery
# card read, and a track with no author reads as one of the editor's starter
# shapes - which cannot be published.
DAILY_USER = "daily"


def pool_looks():
    """The palettes worth borrowing: grounded, and not tied to their own layout.

    A void track's look has a `below` and no ground under it, and lifting one
    onto a track that *has* ground gives a world with two floors. The four
    tracks that sculpt their own terrain are excluded by `generate.borrow`
    stripping the keys rather than here, since what is wrong is the key and not
    the track.
    """
    out = []
    for t in tracks_mod.TRACKS:
        pal = t.get("pal") or {}
        if not pal or pal.get("below"):
            continue
        out.append({"slug": t["slug"], "name": t["name"], "pal": pal})
    return out


def judge(doc):
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
    try:
        rough = tracks_mod.from_document("daily-candidate", doc, timed=False)
        generate.settle_ground(doc, rough)
        track = tracks_mod.from_document("daily-candidate", doc, timed=True)
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
    return track, why


def propose(n, first_seed=0, verbose=True):
    """`n` documents that pass everything, and the seeds they came from."""
    looks = pool_looks()
    kept, seed, tried = [], first_seed, 0
    while len(kept) < n:
        tried += 1
        doc = generate.generate(seed, looks)
        track, why = judge(doc)
        if not why:
            kept.append((seed, doc, track))
            if verbose:
                print("  keep  seed %-6d %5.1fs  %-26s (look: %s)"
                      % (seed, track["ideal"], doc["name"],
                         doc["generated"]["look"]))
        elif verbose and tried <= 8:
            print("  drop  seed %-6d %s" % (seed, "; ".join(why)))
        seed += 1
        if tried > n * 40:
            raise SystemExit(
                "gave up after %d candidates for %d keepers - the generator or "
                "a check has moved" % (tried, n))
    if verbose:
        print("kept %d of %d candidates (%.0f%%)" % (n, tried, 100.0 * n / tried))
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
        author = User.query.filter_by(username=DAILY_USER).first()
        if author is None:
            raise SystemExit(
                "there is no `%s` account - make one first, because a track "
                "with no author cannot be published" % DAILY_USER)
        made = []
        for seed, doc, track in kept:
            slug = maker._free_slug(doc["name"])
            if slug is None:
                print("  ! no free slug for %r, skipped" % doc["name"])
                continue
            doc = dict(doc, slug=slug)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("count", type=int, nargs="?", default=10,
                    help="how many to put in the queue")
    ap.add_argument("--from", dest="seed", type=int, default=None,
                    help="first seed to try (default: the clock, so two runs "
                         "do not propose the same tracks)")
    ap.add_argument("--dry-run", action="store_true",
                    help="propose and print, write nothing")
    a = ap.parse_args(argv)

    seed = a.seed
    if seed is None:
        import time
        seed = int(time.time()) % 1_000_000 * 1000
    kept = propose(a.count, seed)
    if a.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    made = store(kept)
    print("\nqueued %d for review: %s" % (len(made), ", ".join(made)))
    print("review them at /admin/tracks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
