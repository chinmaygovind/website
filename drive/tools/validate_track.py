"""Everything the tests and the sim know about one track, in one report.

Authoring a track means asking the same dozen questions every time - is it
drivable, how long is the lap, are the medals reachable, does it run into itself,
does the closed lap actually close, does anything throw in the browser - and each
one currently lives in a different place: a parameterized test, a laptime call, a
`self_proximity` check, a console you have to open.

    cd drive && venv/bin/python tools/validate_track.py costco
    cd drive && venv/bin/python tools/validate_track.py costco --no-browser
    cd drive && venv/bin/python tools/validate_track.py --all

Exit status is 0 when everything passed, so it works in a loop or a hook.

**What this is not.** It cannot tell you whether a track is any *good* - whether
a corner arrives too fast to read, whether the closing stretch is boring, whether
the sky washes out the kerbs. That needs a picture (`track_views.py`) and then
somebody driving it. This tool tells you the track is not broken, which is the
cheap half, and it tells you fast enough to run it after every edit.
"""

import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import _shots  # noqa: E402

PORT = int(os.environ.get("VALIDATE_PORT", "5081"))

OK, BAD, WARN = "ok  ", "FAIL", "warn"


class Report:
    def __init__(self, slug):
        self.slug = slug
        self.rows = []
        self.failed = False

    def add(self, status, label, detail=""):
        self.rows.append((status, label, detail))
        if status == BAD:
            self.failed = True

    def check(self, cond, label, detail=""):
        self.add(OK if cond else BAD, label, detail)

    def print(self):
        print("\n%s" % self.slug)
        print("-" * max(len(self.slug), 60))
        for status, label, detail in self.rows:
            print("  %s  %-38s %s" % (status, label, detail))


def geometry(track, rep):
    """The facts, and the checks that are cheap to recompute here."""
    import tracks as tracks_mod

    line = track["line"]
    length = sum(math.dist(line[i - 1]["p"], line[i]["p"])
                 for i in range(1, len(line)))
    rep.add(OK, "length", "%d units, %d stations" % (round(length), len(line)))
    rep.add(OK, "difficulty", "%d, %s"
            % (track["difficulty"],
               "closed lap" if track.get("closed") else "point to point"))
    rep.add(OK, "checkpoints", "%d" % track["checkpoints"])

    # How close the road comes to itself. The check the pool's worst bug was.
    close = tracks_mod.self_proximity(track)
    rep.check(not close, "does not run into itself",
              "worst %s" % (close[0] if close else "clear"))

    # Corner radii, because a track of identical corners is the thing the grid
    # version got wrong, and one under ~12 is not drivable.
    #
    # `curv` is signed - negative is a left-hander - so the radius is 1/|curv|.
    # Taking 1/curv straight reported Spa's tightest corner as -124 units, which
    # passes an "is it at least 12" check by being less than it in the wrong
    # direction.
    radii = sorted({round(1.0 / abs(e["curv"]), 1) for e in line
                    if e.get("curv") and abs(e["curv"]) > 1e-9})
    if radii:
        rep.check(min(radii) >= 12.0, "tightest corner",
                  "%.0f units (12 is the floor)" % min(radii))
        rep.add(OK, "corner variety",
                "%d distinct radii, %.0f-%.0f" % (len(radii), min(radii), max(radii)))

    widths = sorted({e["hw"] * 2 for e in line})
    rep.add(OK, "road width", "%.1f-%.1f" % (min(widths), max(widths)))

    ceil = track["gate_ceil"]
    rep.check(tracks_mod.GATE_CEIL_MIN <= ceil <= tracks_mod.GATE_CEIL_MAX,
              "checkpoint ceiling", "%.1f (%.0f-%.0f)"
              % (ceil, tracks_mod.GATE_CEIL_MIN, tracks_mod.GATE_CEIL_MAX))
    rep.add(OK, "pole side", track["pole_side"])

    walled = sum(1 for e in line if e.get("wl") or e.get("wr"))
    rep.add(OK, "barriers", "%d of %d stations%s"
            % (walled, len(line),
               " (declared exposed)" if track.get("exposed") else ""))


def seam(track, rep):
    """For a closed lap: does the ribbon actually meet itself?

    The one thing about a circuit that is invisible in the code and unmissable at
    40 m/s. Measured in all four ways it can be open, because they fail
    differently: a position gap is a step you hit, a heading gap is a kink, and a
    height gap is a jump nobody authored.
    """
    if not track.get("closed"):
        return
    line = track["line"]
    a, b = line[0], line[-1]
    gap = math.dist(a["p"], b["p"])
    # Along the ribbon, consecutive stations sit STATION apart, so the seam is
    # closed when the join is no worse than an ordinary step.
    import tracks as tracks_mod
    budget = tracks_mod.STATION * 1.5
    rep.check(gap <= budget, "closed lap: seam position",
              "%.4f units (budget %.2f)" % (gap, budget))

    dy = abs(a["p"][1] - b["p"][1])
    rep.check(dy <= 1.0, "closed lap: seam height", "%.4f units" % dy)

    # Heading, off the ribbon's own lateral vector rather than a stored yaw.
    dot = sum(x * y for x, y in zip(a["lat"], b["lat"]))
    off = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    rep.check(off <= 3.0, "closed lap: seam heading", "%.4f deg" % off)


def medals(track, rep):
    ideal, m = track["ideal"], track["medals"]
    rep.add(OK, "ideal lap", "%.2fs" % ideal)
    rep.add(OK, "medals", "gold %.2f  silver %.2f  bronze %.2f"
            % (m["gold"], m["silver"], m["bronze"]))
    rep.check(m["gold"] < m["silver"] < m["bronze"], "medals are ordered")
    # Gold has to be beatable by a human and the spread has to be small enough
    # that silver is not a consolation prize - see test_tracks.py.
    rep.check(m["gold"] > ideal * 0.85, "gold is reachable",
              "%.0f%% of ideal" % (100 * m["gold"] / ideal))
    rep.check(m["bronze"] / m["gold"] < 1.35, "medals are close together",
              "bronze is %.0f%% of gold" % (100 * m["bronze"] / m["gold"]))


def preview(track, rep):
    p = os.path.join(ROOT, "static", "img", "tracks", track["slug"] + ".png")
    if not os.path.exists(p):
        rep.add(BAD, "switcher preview", "missing - run tools/shoot_tracks.py %s"
                % track["slug"])
        return
    rep.add(OK, "switcher preview", "%.0f kB" % (os.path.getsize(p) / 1024.0))


def suite(slug, rep):
    """The real track tests, for this track only.

    Run rather than reimplemented: `test_tracks.py` is where the pool's authoring
    rules actually live, and every one of them is a mistake somebody already made.
    A second copy of them here would be a second thing to keep in step.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_tracks.py",
         "tests/test_closed_lap.py", "-q", "--no-header", "-p", "no:cacheprovider",
         "-k", slug],
        cwd=ROOT, capture_output=True, text=True)
    tail = [l for l in r.stdout.strip().splitlines() if l.strip()]
    summary = tail[-1] if tail else "no output"
    rep.check(r.returncode == 0, "tests/test_tracks.py -k %s" % slug, summary)
    if r.returncode != 0:
        for line in r.stdout.splitlines():
            if line.startswith("FAILED") or line.startswith("E "):
                rep.add(BAD, "  " + line[:70], "")


def browser(slug, rep, port=PORT):
    """Load the page for real and collect what the console says.

    The failure this is for is silent by construction: `buildTrack` throwing
    inside a track's scenery leaves a page that still draws the road, still lets
    you drive, and is missing a building. Nothing in the Python suite can see it,
    because the Python suite has no browser.
    """
    if _shots.describe_backend().startswith("NONE"):
        rep.add(WARN, "browser check", "skipped - no Playwright and no Chrome")
        return
    if not _shots.have_playwright():
        rep.add(WARN, "browser check",
                "skipped - the Chrome CLI cannot report console errors")
        return
    out = os.path.join(HERE, "views", slug, "_validate.png")
    with _shots.serving(port) as base, \
            _shots.Shooter(size=(640, 360), budget_ms=9000) as cam:
        size = cam.shoot("%s/solo/%s?shot=1" % (base, slug), out)
        errors = [m for _, m in cam.errors]
    rep.check(bool(size), "page renders", "%.0f kB" % (size / 1024.0) if size else "no PNG")
    rep.check(not errors, "no JS errors",
              "clean" if not errors else "%d: %s" % (len(errors), errors[0][:60]))


def one(slug, do_browser=True, port=PORT):
    import tracks as tracks_mod
    track = tracks_mod.get(slug)
    rep = Report(slug)
    if not track:
        rep.add(BAD, "no such track",
                "pool: " + ", ".join(t["slug"] for t in tracks_mod.TRACKS))
        rep.print()
        return rep
    geometry(track, rep)
    seam(track, rep)
    medals(track, rep)
    preview(track, rep)
    suite(slug, rep)
    if do_browser:
        browser(slug, rep, port)
    rep.print()
    return rep


def main(argv):
    flags = {a for a in argv[1:] if a.startswith("--")}
    args = [a for a in argv[1:] if not a.startswith("--")]

    import tracks as tracks_mod
    if "--all" in flags:
        slugs = [t["slug"] for t in tracks_mod.TRACKS]
    elif args:
        slugs = args
    else:
        print(__doc__.strip().splitlines()[0])
        print("\nusage: validate_track.py <slug>... | --all  [--no-browser]")
        return 1

    reps = [one(s, do_browser="--no-browser" not in flags, port=PORT + i)
            for i, s in enumerate(slugs)]
    bad = [r.slug for r in reps if r.failed]
    print()
    if bad:
        print("FAILED: %s" % ", ".join(bad))
        return 1
    print("all clear: %s" % ", ".join(r.slug for r in reps))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
