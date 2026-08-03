"""Seed ``drive_starts`` from the finishes counted before it existed.

Drive counted finishes long before it counted starts, so on the day the counter
arrived every existing player had a pile of laps behind them and a start count
of nought. ``_starts_for`` will not *show* that - it clamps the count from below
by the finishes beside it - but a stored zero under a shown 200 is a trap: the
next real start is written as 1, disappears under the clamp, and goes on
disappearing for the next two hundred attempts. The number would look right and
stop moving.

So the floor goes into the rows themselves, once. For every ``drive_times`` row,
this lifts the matching ``drive_starts.starts`` to at least that track's finish
count. It invents nothing - the true number of attempts behind an old lap is
unknowable and certainly higher - it only asserts the one thing that must be
true, that a lap was started at least as often as it was finished, and puts the
counter somewhere the next start can count on from.

**Run it once on the box, straight after the deploy that creates the table** -
``create_all`` makes ``drive_starts`` on boot, and this fills it:

    cd /home/ubuntu/website/drive && venv/bin/python tools/backfill_starts.py --dry-run
    cd /home/ubuntu/website/drive && venv/bin/python tools/backfill_starts.py

It takes the same ``DATABASE_URL`` the app does, out of ``drive/.env``, so it
writes to whatever database the running service is reading. Nothing needs to be
stopped: it is a handful of small writes to tables only Drive uses, and the app
tolerates the before and after states equally.

Safe to run twice. Every write is a ``max``, so a second pass over a database it
has already seen changes nothing, and a pass after people have driven only
raises rows that are somehow still below their own finish count.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import app as A                                       # noqa: E402  (needs the path first)
from models import db, DriveTime, DriveStart          # noqa: E402


def backfill(dry_run=False):
    """Returns (rows seeded, rows already fine, total starts added)."""
    seeded = fine = added = 0
    with A.app.app_context():
        existing = {(r.user_id, r.track): r
                    for r in DriveStart.query.all()}
        for t in DriveTime.query.order_by(DriveTime.user_id, DriveTime.track).all():
            finishes = t.runs or 0
            row = existing.get((t.user_id, t.track))
            have = (row.starts or 0) if row else 0
            if have >= finishes:
                fine += 1
                continue
            seeded += 1
            added += finishes - have
            print("  %-10s user %-4s  %d starts -> %d" %
                  (t.track, t.user_id, have, finishes))
            if dry_run:
                continue
            if row is None:
                row = DriveStart(user_id=t.user_id, track=t.track, starts=0)
                db.session.add(row)
                existing[(t.user_id, t.track)] = row
            row.starts = finishes
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    return seeded, fine, added


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change and write nothing")
    args = ap.parse_args()

    print("database: %s" % A.app.config["SQLALCHEMY_DATABASE_URI"])
    print("%s:" % ("would seed" if args.dry_run else "seeding"))
    seeded, fine, added = backfill(dry_run=args.dry_run)
    print("%s %d (user, track) rows, %d starts; %d already at or above their "
          "finish count." % ("would seed" if args.dry_run else "seeded",
                             seeded, added, fine))


if __name__ == "__main__":
    main()
