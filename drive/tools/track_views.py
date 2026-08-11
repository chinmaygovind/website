"""Look at a track you are authoring: a plan view, and several from the road.

This is the tool that exists because **there is no browser in CI and there was no
browser on the laptop either.** `shoot_tracks.py` shelled out to `google-chrome`
via `which`, found nothing on a Mac, printed one line and did nothing - so every
track in the pool was authored blind, by proposing geometry, shipping it, and
waiting for somebody to drive it and describe what was wrong. That loop costs
four or five rounds per track, and the git history of Big Red is what it looks
like: `add` then `Rebuild: taller descent, kinder sky` then `two more jumps,
revert the sky`.

    cd drive && venv/bin/python tools/track_views.py costco
    cd drive && venv/bin/python tools/track_views.py costco --n 8
    cd drive && venv/bin/python tools/track_views.py spa --at 0.42

Writes to `tools/views/<slug>/` (gitignored - these are working pictures, not
assets):

    plan.png      straight down, whole track, north up
    at-000.png    on the road at the start
    at-020.png    ...a fifth of the way round
    ...

**What each view is for.** The plan is the one that finds mistakes: a leg that
left the building, a hairpin that bulged into the aisle beside it, a closing
stretch that is half as long as it read in the code, a crossing that is not where
it was meant to be. The road views are the one that finds *feel*: a corner that
arrives with no warning, a crest that hides the next braking point, a sky that
washes the kerbs out, a ceiling the camera is about to clip.

The road views use the **real chase camera** with the car parked on the
centreline, not a camera written for this tool. That is deliberate and it is most
of their value: on Costco the whole question is whether the lens clears a
15-unit ceiling and follows the car through a doorway 11.6 units after it, and a
bespoke authoring camera would be answering that question about itself.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _shots  # noqa: E402

OUT = os.path.join(HERE, "views")
PORT = int(os.environ.get("VIEW_PORT", "5079"))
# Bigger than the switcher's card, because these are looked at rather than shown.
SIZE = (1280, 720)
BUDGET_MS = 14000
# Five is enough to walk a lap and few enough to look at all of them. The plan is
# what catches layout mistakes; these catch the ones only a driver would.
DEFAULT_N = 5


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = {}
    it = iter(argv[1:])
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it, "")

    if not args:
        print(__doc__.strip().splitlines()[0])
        print("\nusage: track_views.py <slug> [--n 5] [--at 0.42] [--plan-only]")
        return 1
    slug = args[0]

    if _shots.describe_backend().startswith("NONE"):
        print("no way to take pictures: no Playwright in this venv and no "
              "Chrome on PATH or in /Applications")
        return 1

    sys.path.insert(0, ROOT)
    import tracks as tracks_mod
    track = tracks_mod.get(slug)
    if not track:
        print("no such track: %s\n  pool: %s"
              % (slug, ", ".join(t["slug"] for t in tracks_mod.TRACKS)))
        return 1

    if "at" in opts:
        fracs = [float(opts["at"])]
    elif "plan-only" in opts:
        fracs = []
    else:
        n = int(opts.get("n") or DEFAULT_N)
        # Evenly round the lap, and *not* including 1.0: the last station is the
        # finish line, where the camera is looking at the flag rather than at
        # any road, so it is the one view that tells you nothing.
        fracs = [i / float(n) for i in range(n)]

    where = os.path.join(OUT, slug)
    print("%s: %d units, %d stations, ideal %.2fs, plan + %d road view(s)"
          % (slug, _length(track), len(track["line"]), track["ideal"], len(fracs)))
    print("  %s -> %s" % (_shots.describe_backend(), os.path.relpath(where, ROOT)))

    with _shots.serving(PORT) as base, \
            _shots.Shooter(size=SIZE, budget_ms=BUDGET_MS) as cam:
        shots = [("plan.png", "%s/solo/%s?shot=plan" % (base, slug))]
        for f in fracs:
            shots.append(("at-%03d.png" % round(f * 100),
                          "%s/solo/%s?shot=at:%.4f" % (base, slug, f)))
        for name, url in shots:
            size = cam.shoot(url, os.path.join(where, name))
            print("    %-14s %s" % (name, "%6.1f kB" % (size / 1024.0)
                                    if size else "FAILED"))
        errors = list(cam.errors)

    if errors:
        print("\n  JS errors - a track whose scenery throws still renders the road:")
        for url, msg in errors:
            print("    ! %s" % msg)
        return 1
    return 0


def _length(track):
    import math
    line = track["line"]
    return round(sum(math.dist(line[i - 1]["p"], line[i]["p"])
                     for i in range(1, len(line))))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
