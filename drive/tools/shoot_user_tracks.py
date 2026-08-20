"""Take cover pictures for the community tracks, the way the pool gets its own.

**This tool is almost empty, and that is the point.** A published user track is
resolved by `tracks.get` exactly as Spa is, so `/solo/<slug>` renders it, so
`_hero.shoot` can photograph it - the same function, the same framing, the same
960x540 card - without knowing that user tracks exist. Everything here is
choosing *which* slugs to hand it.

Run it after approving tracks:

    venv/bin/python tools/shoot_user_tracks.py            # every live track
    venv/bin/python tools/shoot_user_tracks.py foggy-ridge
    venv/bin/python tools/shoot_user_tracks.py --missing  # only ones with none

Every track has a picture without this: `tracks/plan.py` draws the shape of the
lap from the ribbon, and the switcher and the gallery use it wherever there is no
render. So this is an improvement to a card that already works, which is why it
is a tool run by hand rather than something the approve button does - approving
happens on the box, on the one eventlet worker that is also relaying live race
poses at 30Hz, and starting a headless Chromium in there would be a strange way
to drop everybody's race.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import _hero    # noqa: E402
import _shots   # noqa: E402

OUT = os.path.join(ROOT, "static", "img", "tracks")
PORT = int(os.environ.get("SHOT_PORT", "5078"))


def live_slugs():
    """Every published community track, newest first.

    Reads the database directly rather than the site, because this runs from a
    checkout and the site it is about to start is the one being photographed.
    """
    os.environ.setdefault("DRIVE_VERIFY", "0")
    import app  # noqa: F401  - importing it wires the resolver and the models
    from models import DriveUserTrack
    with app.app.app_context():
        rows = (DriveUserTrack.query.filter_by(status="live")
                .order_by(DriveUserTrack.published_at.desc().nullslast()).all())
        return [r.slug for r in rows]


def main(argv):
    if not _shots.have_playwright():
        print("this needs Playwright and there is none in this venv. The hero\n"
              "compose is a page evaluation, so the Chrome CLI cannot take it,\n"
              "and falling back to a plain screenshot would write the wrong\n"
              "picture under the right name. `pip install playwright && "
              "playwright install chromium` into drive/venv.")
        return 1

    only_missing = "--missing" in argv
    wanted = [a for a in argv[1:] if not a.startswith("-")]
    if not wanted:
        wanted = live_slugs()
        if not wanted:
            print("no community tracks are live yet - nothing to shoot.")
            return 0
    if only_missing:
        wanted = [s for s in wanted
                  if not os.path.exists(os.path.join(OUT, "%s.png" % s))]
        if not wanted:
            print("every live community track already has a picture.")
            return 0

    # A slug that does not resolve would be photographed as a 404 page and
    # written under the right name, which is the failure this refuses to have.
    import tracks as tracks_mod
    import app
    with app.app.app_context():
        unknown = [s for s in wanted if not tracks_mod.get(s)]
    if unknown:
        print("not live (so there is nothing to photograph): "
              + ", ".join(unknown))
        return 1

    print("shooting %d community track(s) with playwright chromium"
          % len(wanted))
    written, failed, errors = _hero.shoot(wanted, OUT, size=_hero.CARD,
                                          port=PORT)
    for slug, msg in errors:
        print("  ! %s: %s" % (slug, msg))
    print("%d/%d written to %s"
          % (len(written), len(wanted), os.path.relpath(OUT, ROOT)))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
