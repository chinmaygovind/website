"""Add the driving done in races to ``drive_stats.drive_time`` and ``.distance``.

Both numbers were only ever written by ``/api/run``, which a room lap never
reaches - ``countsForTheBoard()`` sends it back before the request is made - so
every race anybody has driven counted as nought minutes and nought kilometres.
``/api/activity`` fixes that going forwards. This is the driving that happened
before it existed.

**It is measurement rather than estimation**, which is why races are the only
thing here. ``drive_races.cars_json`` holds each car's replay packed exactly the
way a ghost is, at a known rate, so the two numbers fall straight out of it:
``len(frames) / hz`` is the seconds the car was on the road, and the sum of the
distances between consecutive frames is the metres it covered. Nothing is
inferred from a lap time or scaled from a racing line. The abandoned *solo* runs
are the larger undercount and are not recoverable at all - a run nobody finished
left no replay and no row anywhere, so there is nothing to read.

Identity is the one wrinkle. ``cars_json`` carries a ``name`` and no
``user_id``, and the ``drive_players`` rows that mapped one to the other are
deleted with their room, so nothing survives to join on. A name is matched
against ``users.username`` directly, which is sound here because Drive has no
display-name column of its own: a replay's name *is* the username of whoever
logged in, and a name with no account is a guest, who correctly has no
``drive_stats`` row to add to. Guests are counted and reported, not guessed at.

It **adds** rather than recomputes, and it has to: ``drive_times`` keeps only the
best lap per track, so the totals already in ``drive_stats`` are the only record
that the other finished laps ever happened. There is nothing to recompute
*from*.

**Idempotent by construction**, because a backfill that double-applies is worse
than one that never ran and 58 races is not a number you can eyeball afterwards.
The job writes a marker row into ``drive_backfill`` and a second run refuses
unless ``--force``. That table is created here with plain SQL rather than being a
model: nothing in the app reads it, so mapping it would put a table in
``models.py`` that only a tool in ``tools/`` ever touches. ``visits.py`` does the
same for the same reason.

Run it on the box, ``--dry-run`` first:

    cd /home/ubuntu/website/drive && venv/bin/python tools/backfill_race_activity.py --dry-run
    cd /home/ubuntu/website/drive && venv/bin/python tools/backfill_race_activity.py

It takes the same ``DATABASE_URL`` the app does, out of ``drive/.env``. Nothing
needs stopping: it is a handful of small writes to one table Drive owns, and the
app tolerates the before and after states equally.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import app as A                                        # noqa: E402  (needs the path first)
import runcheck                                        # noqa: E402
from models import db, User, DriveStats, DriveRace      # noqa: E402
from sqlalchemy import text                             # noqa: E402

JOB = "race_activity_v1"

# A frame is 1/hz apart from the next one, so a car that teleports between two of
# them was respawning - a respawn is not distance driven, and counting it would
# hand somebody the width of the map for falling off. `REMOTE_SNAP` (12 units) is
# the same threshold the client uses to decide a rival's move was not driven.
MAX_STEP = 12.0


def _ensure_marker_table():
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS drive_backfill (job TEXT PRIMARY KEY)"))
    db.session.commit()


def _already_done():
    row = db.session.execute(
        text("SELECT job FROM drive_backfill WHERE job = :j"), {"j": JOB}).first()
    return row is not None


def _mark_done():
    db.session.execute(
        text("INSERT OR REPLACE INTO drive_backfill (job) VALUES (:j)"), {"j": JOB})


def measure(ghost, hz):
    """(seconds, metres) actually driven in one packed replay.

    The distance is 3D on purpose - Drive has loops, half-pipes and a track made
    of jumps, so the vertical component is real driving rather than noise.
    """
    frames = runcheck.unpack_ghost(ghost)
    if not frames or len(frames) < 2:
        return 0.0, 0.0
    hz = float(hz or runcheck.GHOST_HZ)
    if hz <= 0:
        return 0.0, 0.0
    metres = 0.0
    for a, b in zip(frames, frames[1:]):
        step = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
        if step <= MAX_STEP:
            metres += step
    return len(frames) / hz, metres


def collect():
    """Every race's driving, summed per username. No database writes.

    Returns (per_name, races, cars, skipped_empty) where per_name maps a name to
    (seconds, metres) - including names that turn out to be guests, since who was
    skipped and why is the thing worth printing.
    """
    per_name = {}
    races = cars = skipped = 0
    for race in DriveRace.query.order_by(DriveRace.id).all():
        races += 1
        for car in race.cars:
            name = (car.get("name") or "").strip()
            secs, metres = measure(car.get("ghost"), race.hz)
            if not name or secs <= 0:
                skipped += 1
                continue
            cars += 1
            have = per_name.get(name, (0.0, 0.0))
            per_name[name] = (have[0] + secs, have[1] + metres)
    return per_name, races, cars, skipped


def backfill(dry_run=False, force=False):
    with A.app.app_context():
        _ensure_marker_table()
        if _already_done() and not force:
            print("already applied (job %r is in drive_backfill); "
                  "pass --force to apply it again." % JOB)
            return False

        per_name, races, cars, skipped = collect()
        print("%d races, %d cars with a readable replay (%d skipped)."
              % (races, cars, skipped))

        # One query for every name at once: a per-name lookup is fine for 58 races
        # and this is the shape that stays fine if it is ever run on more.
        names = list(per_name)
        users = {u.username: u for u in
                 User.query.filter(User.username.in_(names)).all()} if names else {}

        guests, applied = [], 0
        total_s = total_m = 0.0
        for name in sorted(per_name, key=lambda n: -per_name[n][0]):
            secs, metres = per_name[name]
            user = users.get(name)
            if user is None:
                guests.append((name, secs, metres))
                continue
            st = DriveStats.query.filter_by(user_id=user.id).first()
            if st is None:
                st = DriveStats(user_id=user.id)
                db.session.add(st)
            was_s, was_m = (st.drive_time or 0.0), (st.distance or 0.0)
            print("  %-16s %6.1f min -> %6.1f   %7.1f km -> %7.1f"
                  % (name, was_s / 60.0, (was_s + secs) / 60.0,
                     was_m / 1000.0, (was_m + metres) / 1000.0))
            st.drive_time = was_s + secs
            st.distance = was_m + metres
            applied += 1
            total_s += secs
            total_m += metres

        for name, secs, metres in guests:
            print("  %-16s skipped - no account (guest), %.1f min / %.1f km"
                  % (name, secs / 60.0, metres / 1000.0))

        print("%s %d accounts: +%.1f minutes, +%.1f km."
              % ("would credit" if dry_run else "credited",
                 applied, total_s / 60.0, total_m / 1000.0))

        if dry_run:
            db.session.rollback()
        else:
            _mark_done()
            db.session.commit()
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change and write nothing")
    ap.add_argument("--force", action="store_true",
                    help="apply again even though the marker says it already ran")
    args = ap.parse_args()

    print("database: %s" % A.app.config["SQLALCHEMY_DATABASE_URI"])
    backfill(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
