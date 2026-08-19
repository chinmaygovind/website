"""Take each track's cover picture - the one every page of this game shows.

The home page's cards, the in-game switcher and each track's share card all show
the same photograph, and this is what takes it: `static/img/tracks/<slug>.png`,
one per track in the pool.

It is a **hero shot**, and the composition lives in `_hero.py`: a stretch of the
lap from up high with a field of cars on it, framed per track. This file is the
part that is about where the files go. `shoot_covers.py` is the same picture at
portal sizes with the wordmark across the foot, off the same framings, so a card
and a cover of one track cannot disagree.

    cd drive && venv/bin/python tools/shoot_tracks.py            # all of them
    cd drive && venv/bin/python tools/shoot_tracks.py twist      # just one

**Re-run this whenever a track's geometry, palette or sky changes**, or every
page will keep showing the old one. That staleness is the price of a real
picture; nothing in the test suite can notice it, because nothing in the test
suite can see.

It also re-makes each shot track's **share card** (`shoot_og_cards.py`), which is
a layout over the picture and therefore goes stale with it. So this one command
is the whole answer to "I changed a track".

For *authoring* a track, `track_views.py` is the one you want - a plan view and
several along the road. To choose a hero framing for a new track, run `_hero.py`
directly: it prints contact sheets of the candidates.

**It needs Playwright and refuses rather than falling back to the Chrome CLI.**
Composing the scene is a page evaluation and the CLI backend can only load a URL
and screenshot it, so a fallback would quietly write the old empty-road framing
under this tool's name - and nothing downstream can tell one picture of a track
from another. The browser search and the software-GL flags live in `_shots.py`,
which is also where the note about why a wrong flag produces a picture of the
*wrong track* rather than an error.

**Every picture will come back "modified" the first time you run this after
changing browsers, and it does not mean anything.** The render is deterministic -
the camera, the cars and their liveries all come off one seed - but a different
renderer build rounds antialiasing differently. Measured between the Chrome CLI
that took the first committed set and the Playwright chromium this now requires:
**1.68% of pixels differ and the largest channel delta is 1 of 255**, which is
invisible. So `git checkout` them unless a track actually changed; there is no
reason to commit a megabyte of rounding noise. If you need to know whether a
change is real, the number that matters is the max channel delta, not the file
size.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _hero  # noqa: E402
import _shots  # noqa: E402

OUT = os.path.join(ROOT, "static", "img", "tracks")
PORT = int(os.environ.get("SHOT_PORT", "5077"))


def main(argv):
    if not _shots.have_playwright():
        print("this needs Playwright and there is none in this venv. The hero\n"
              "compose is a page evaluation, so the Chrome CLI cannot take it,\n"
              "and falling back to a plain screenshot would write the wrong\n"
              "picture under the right name. `pip install playwright && "
              "playwright install chromium` into drive/venv.")
        return 1
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    wanted = [a for a in argv[1:] if not a.startswith("-")]
    wanted = wanted or [t["slug"] for t in tracks_mod.TRACKS]
    unknown = [s for s in wanted if not tracks_mod.get(s)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1

    print("shooting %d track(s) with playwright chromium" % len(wanted))
    written, failed, errors = _hero.shoot(wanted, OUT, size=_hero.CARD, port=PORT)
    # A track whose scenery throws still renders a plausible picture of the road
    # with nothing on it, so the errors matter more than the file sizes.
    for slug, msg in errors:
        print("  ! %s: %s" % (slug, msg))
    print("%d/%d written to %s"
          % (len(written), len(wanted), os.path.relpath(OUT, ROOT)))

    # The share cards are a layout over the pictures just taken, so they are
    # stale the moment those move. Re-made here rather than left to be
    # remembered: this tool already exists because nothing downstream can tell a
    # stale preview from a fresh one, and that is twice as true of a card
    # somebody only ever sees in someone else's feed. Only for the tracks that
    # were actually shot, and never for one whose shot failed.
    shot = [t for t in tracks_mod.summaries() if t["slug"] in written]
    if shot:
        import shoot_og_cards
        print("share cards")
        failed = list(failed) + shoot_og_cards.shoot(shot)

    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
