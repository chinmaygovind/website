"""Rework the dailies Chinmay sent back from review.

    venv/bin/python tools/daily_fixes.py list             # every sent-back track and its note
    venv/bin/python tools/daily_fixes.py show <slug>      # its document, as JSON
    venv/bin/python tools/daily_fixes.py put <slug> doc.json   # a reworked document, back in the queue
    venv/bin/python tools/daily_fixes.py regen <slug>     # a fresh generated track in its place

Run on the box with the `.env` sourced, like `gen_daily.py`. A reworked
document goes through the same `gen_daily.judge` as a new candidate, so nothing
reaches the queue that the generator itself would have thrown away. The note
is kept, prefixed with what was done about it, so the review card's history
survives the round trip.
"""

import argparse
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import gen_daily                                                # noqa: E402
from tracks import moves as moves_mod, plan as plan_mod       # noqa: E402


def _requeue(row, doc, track, what):
    doc = dict(doc, slug=row.slug, name=gen_daily.QUEUE_NAME)
    row.doc_json = json.dumps(doc, separators=(",", ":"))
    row.name = doc["name"]
    row.difficulty = doc["difficulty"]
    row.geom_hash = moves_mod.fingerprint(track, None)
    row.look_hash = moves_mod.look_fingerprint(doc)
    row.plan_path = plan_mod.path_for(track.get("line") or ())
    row.status = "queued"
    row.queued_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    row.review_note = "%s: %s" % (what, row.review_note or "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("list", "show", "put", "regen"))
    ap.add_argument("slug", nargs="?")
    ap.add_argument("file", nargs="?")
    a = ap.parse_args(argv)

    import app
    from models import DriveUserTrack, db

    with app.app.app_context():
        if a.cmd == "list":
            rows = (DriveUserTrack.query.filter_by(status="needs_fix")
                    .order_by(DriveUserTrack.id).all())
            for r in rows:
                print("%-24s %s" % (r.slug, r.review_note))
            print("%d sent back" % len(rows))
            return 0

        row = DriveUserTrack.query.filter_by(slug=a.slug).first()
        if row is None:
            raise SystemExit("no track %r" % a.slug)
        if a.cmd == "show":
            print(json.dumps(row.doc, indent=1))
            return 0
        if row.status != "needs_fix":
            raise SystemExit("%s is %s, not needs_fix" % (a.slug, row.status))

        if a.cmd == "put":
            doc = json.load(open(a.file))
            track, why = gen_daily.judge(doc)
            if why:
                raise SystemExit("refused: " + "; ".join(why))
            _requeue(row, doc, track, "fixed")
        else:
            seed = (row.doc.get("generated") or {}).get("seed", 0) + 7_000_000
            (_seed, doc, track), = gen_daily.propose(1, seed, verbose=False)
            _requeue(row, doc, track, "regenerated")
        db.session.commit()
        print("%s back in the queue (%.1fs)" % (a.slug, track["ideal"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
