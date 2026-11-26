"""Fill `DriveStats.record_tracks` from the laps already on the boards.

    python tools/backfill_records.py            # report only
    python tools/backfill_records.py --write    # and store it

`record_tracks` is exact from the day it was added: a lap that becomes a
pool track's record adds the track as it goes on the board. Before that
nothing remembered a record once it was beaten, so this reconstructs it from
`drive_times`: walk each track's best laps in the order they were set, and a
lap that was the fastest on that track when it was set was the record. It can
miss a record somebody held with a lap they later improved on, since only the
best lap is kept. It only ever adds tracks, so running it twice is harmless.

On the box, source the service's `.env` first or it opens the wrong database.
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from app import app
    import tracks as tracks_mod
    from models import db, DriveStats, DriveTime, User

    write = "--write" in sys.argv
    with app.app_context():
        laps = defaultdict(list)
        for t in DriveTime.query.all():
            if t.track in tracks_mod.BY_SLUG:
                laps[t.track].append(t)
        ever = defaultdict(set)
        for slug, rows in laps.items():
            rows.sort(key=lambda r: r.updated_at or r.created_at)
            best = None
            for r in rows:
                if best is None or r.time_ms < best:
                    best = r.time_ms
                    ever[r.user_id].add(slug)
        changed = 0
        for uid, slugs in sorted(ever.items(), key=lambda kv: -len(kv[1])):
            st = DriveStats.query.get(uid)
            if st is None:
                continue
            try:
                have = set(json.loads(st.record_tracks or "[]"))
            except Exception:
                have = set()
            merged = have | slugs
            name = (User.query.get(uid) or User(username="?")).username
            print("%-16s %3d tracks%s" % (name, len(merged), "" if merged == have else "  (+%d)" % len(merged - have)))
            if merged != have:
                st.record_tracks = json.dumps(sorted(merged))
                changed += 1
        if write:
            db.session.commit()
            print("stored for %d accounts" % changed)
        else:
            print("report only; --write to store (%d accounts would change)" % changed)


if __name__ == "__main__":
    main()
