"""Take the track switcher's preview pictures.

The switcher shows a photograph of each track rather than a drawing of it,
which means the pictures have to come from the game itself - the sky, the
lighting and whatever is floating underneath are most of what tells two tracks
apart, and none of that survives a line drawing of the centreline.

So this starts the app on a spare port, loads every track with ``?shot=1``
(see ``S.shot`` in game.js - HUD off, car hidden, camera pulled back over the
start line) and screenshots it headlessly.

    cd drive && venv/bin/python tools/shoot_tracks.py            # all of them
    cd drive && venv/bin/python tools/shoot_tracks.py twist      # just one

**Re-run this whenever a track's geometry or palette changes**, or the switcher
will keep showing the old one. That staleness is the price of a real picture;
nothing in the test suite can notice it, because nothing in the test suite can
see.

For *authoring* a track, `track_views.py` is the one you want - a plan view and
several along the road. This tool takes the one picture the switcher shows, and
its framing is deliberately fixed: nothing downstream can tell a re-framed
preview from a stale one, so `?shot=1` is left alone.

The browser search and the software-GL flags live in `_shots.py`, which is also
where the note about why a wrong flag produces a picture of the *wrong track*
rather than an error.

**Every preview will come back "modified" the first time you run this after
changing browsers, and it does not mean anything.** The render itself is
deterministic - three consecutive runs of the same track are byte-identical - but
a different renderer build rounds antialiasing differently. Measured between the
Chrome CLI that took the committed set and the Playwright chromium this now
prefers: **1.68% of pixels differ and the largest channel delta is 1 of 255**,
which is invisible. So `git checkout` them unless a track actually changed; there
is no reason to commit a megabyte of rounding noise. If you need to know whether
a change is real, the number that matters is the max channel delta, not the file
size.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _shots  # noqa: E402

OUT = os.path.join(ROOT, "static", "img", "tracks")
PORT = int(os.environ.get("SHOT_PORT", "5077"))
# 16:9 to match the card. Big enough to look sharp on a dense screen, small
# enough that fifteen of them are not a burden in the repo.
SIZE = (960, 540)
# Long enough for the track mesh, the sky and the scenery below to be built and
# for the first frames to settle - these are rendered on a software GL stack,
# and the longest tracks in the pool are three times the size of the shortest.
BUDGET_MS = 16000


def main(argv):
    if _shots.describe_backend().startswith("NONE"):
        print("no way to take pictures: no Playwright in this venv and no "
              "Chrome on PATH or in /Applications")
        return 1
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    wanted = [a for a in argv[1:] if not a.startswith("-")]
    wanted = wanted or [t["slug"] for t in tracks_mod.TRACKS]
    unknown = [s for s in wanted if not tracks_mod.get(s)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1

    print("shooting %d track(s) with %s" % (len(wanted), _shots.describe_backend()))
    failed = []
    with _shots.serving(PORT) as base, \
            _shots.Shooter(size=SIZE, budget_ms=BUDGET_MS) as cam:
        for slug in wanted:
            out = os.path.join(OUT, slug + ".png")
            size = cam.shoot("%s/solo/%s?shot=1" % (base, slug), out)
            if size:
                print("  %-16s %6.1f kB" % (slug, size / 1024.0))
            else:
                print("  %-16s FAILED" % slug)
                failed.append(slug)
        # A track whose scenery throws still renders a plausible picture of the
        # road with nothing on it, so the errors matter more than the file size.
        errors = list(cam.errors)
    for url, msg in errors:
        print("  ! %s: %s" % (url.rsplit("/", 1)[-1], msg))
    print("%d/%d written to %s"
          % (len(wanted) - len(failed), len(wanted), os.path.relpath(OUT, ROOT)))
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
