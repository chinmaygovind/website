"""Take the track switcher's preview pictures.

The switcher shows a photograph of each track rather than a drawing of it,
which means the pictures have to come from the game itself - the sky, the
lighting and whatever is floating underneath are most of what tells two tracks
apart, and none of that survives a line drawing of the centreline.

So this starts the app on a spare port, loads every track with ``?shot=1``
(see ``S.shot`` in game.js - HUD off, car hidden, camera pulled back to hold the
whole track in frame) and screenshots it with headless Chrome.

    cd drive && venv/bin/python tools/shoot_tracks.py            # all of them
    cd drive && venv/bin/python tools/shoot_tracks.py twist      # just one

**Re-run this whenever a track's geometry or palette changes**, or the switcher
will keep showing the old one. That staleness is the price of a real picture;
nothing in the test suite can notice it, because nothing in the test suite can
see.
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "static", "img", "tracks")
PORT = int(os.environ.get("SHOT_PORT", "5077"))
# 16:9 to match the card. Big enough to look sharp on a dense screen, small
# enough that nine of them are not a burden in the repo.
SIZE = (960, 540)
# Long enough for the track mesh, the sky and the scenery below to be built and
# for the first frames to settle - these are rendered on a software GL stack,
# and the longest tracks in the pool are three times the size of the shortest.
BUDGET_MS = 16000

# Software GL, spelled the way current Chrome wants it. Plain
# `--use-gl=swiftshader` is *rejected* rather than ignored ("not found in
# allowed implementations: [(gl=egl-angle,angle=default)]"), the GPU process
# dies, and Chrome still writes a PNG - of a half-initialised frame, which in
# practice meant a picture of some *other* track. A silently wrong photograph is
# the worst possible failure for this tool, since nothing downstream can tell.
GL_FLAGS = ["--use-gl=angle", "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader"]

CHROME = next((c for c in ("google-chrome", "chromium", "chromium-browser")
               if subprocess.run(["which", c], capture_output=True).returncode == 0), None)


def wait_for_server(url, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def shoot(slug):
    out = os.path.join(OUT, slug + ".png")
    url = "http://127.0.0.1:%d/solo/%s?shot=1" % (PORT, slug)
    cmd = ([CHROME, "--headless=new"] + GL_FLAGS +
           ["--hide-scrollbars", "--window-size=%d,%d" % SIZE,
            "--virtual-time-budget=%d" % BUDGET_MS,
            "--screenshot=" + out, url])
    # Take the old picture away first, or a Chrome that never runs reports the
    # *previous* file's size and the tool prints a comfortable "144.3 kB" for a
    # shot it did not take. That is the worst failure this tool has, because the
    # whole reason to run it is that nothing downstream can tell a stale preview
    # from a fresh one - and it is what a wrong CHROME path looks like.
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(cmd, capture_output=True)
    if not os.path.exists(out):
        return None
    return os.path.getsize(out)


def main(argv):
    if not CHROME:
        print("no chrome/chromium on PATH - cannot take pictures")
        return 1
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    wanted = argv[1:] or [t["slug"] for t in tracks_mod.TRACKS]
    unknown = [s for s in wanted if not tracks_mod.get(s)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1

    os.makedirs(OUT, exist_ok=True)
    env = dict(os.environ, PORT=str(PORT))
    server = subprocess.Popen([sys.executable, os.path.join(ROOT, "app.py")],
                              cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_server("http://127.0.0.1:%d/api/tracks" % PORT):
            print("the app did not come up on port %d" % PORT)
            return 1
        failed = []
        for slug in wanted:
            size = shoot(slug)
            if size:
                print("  %-16s %6.1f kB" % (slug, size / 1024.0))
            else:
                print("  %-16s FAILED" % slug)
                failed.append(slug)
        print("%d/%d written to %s" % (len(wanted) - len(failed), len(wanted), OUT))
        return 1 if failed else 0
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
