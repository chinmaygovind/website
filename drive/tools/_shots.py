"""Run the app on a spare port and photograph it, headlessly.

Shared by `shoot_tracks.py` (the switcher's previews) and `track_views.py` (the
authoring views), because everything hard about taking a picture of this game is
the same for both and it was all learned the expensive way:

* **Software GL has to be spelled exactly right.** Plain `--use-gl=swiftshader`
  is *rejected* rather than ignored, the GPU process dies, and Chrome still
  writes a PNG - of a half-initialised frame, which in practice is a picture of
  some *other* track. See `GL_FLAGS`.
* **The old picture has to be deleted first**, or a browser that never ran
  reports the previous file's size and the tool prints a comfortable `144.3 kB`
  for a shot it did not take.
* **A track takes seconds to appear.** The mesh, the sky and the scenery below
  are all built in JS on a software GL stack, and the longest tracks are three
  times the size of the shortest.

Two backends. **Playwright is preferred** and is what `drive/venv` has: it can
report console errors and page exceptions, which is the difference between "this
picture is wrong" and "this picture is wrong *because* `addBuilding` threw". The
Chrome CLI path is kept because it needs no Python driver and is what a machine
with Chrome but no Playwright will have.

Chrome is looked for on PATH and then in the macOS app bundles, which is the fix
for `shoot_tracks.py` printing "no chrome/chromium on PATH" and doing nothing on
a Mac - the state that made every track authored here authored blind.
"""

import contextlib
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Software GL, spelled the way current Chrome wants it. Plain
# `--use-gl=swiftshader` is rejected ("not found in allowed implementations:
# [(gl=egl-angle,angle=default)]") and a silently wrong photograph is the worst
# failure this tooling has, because nothing downstream can tell.
GL_FLAGS = ["--use-gl=angle", "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader"]

# Where a Mac keeps a browser. Checked after PATH, because a `which` hit is
# somebody's deliberate install.
MAC_CHROME = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_chrome():
    """A browser binary, or None."""
    for c in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    for p in MAC_CHROME:
        if os.path.exists(p):
            return p
    return None


def have_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def wait_for_server(url, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


@contextlib.contextmanager
def serving(port):
    """The app on `port`, for as long as the block runs.

    Its own process rather than a Flask test client, because the thing being
    photographed is the *browser* running the real page - the templates, the
    module graph, the WebGL. A test client can tell you the HTML is right, which
    is not the question a picture answers.
    """
    env = dict(os.environ, PORT=str(port))
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app.py")],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = "http://127.0.0.1:%d" % port
        if not wait_for_server(base + "/api/tracks"):
            raise RuntimeError("the app did not come up on port %d" % port)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:            # pragma: no cover
            proc.kill()


class Shooter:
    """Takes pictures. One browser for the whole run, not one per picture.

    Worth the class: launching Chrome is most of the cost of a shot, so a tool
    that wants five views of a track spends five times as long starting browsers
    as it does rendering if each one is its own process. Playwright can hold the
    browser open between shots; the CLI path cannot, and pays it.
    """

    def __init__(self, size=(960, 540), budget_ms=16000, prefer=None):
        self.size = size
        self.budget_ms = budget_ms
        self.errors = []
        self.backend = prefer or ("playwright" if have_playwright()
                                  else ("chrome" if find_chrome() else None))
        self._pw = self._browser = None

    def __enter__(self):
        if self.backend == "playwright":
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(args=GL_FLAGS)
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        return False

    def shoot(self, url, out):
        """Write a PNG of `url` to `out`. Returns its size, or None.

        Console errors and page exceptions from the load go on `self.errors`,
        tagged with the URL. On the CLI backend that list is always empty, which
        is why Playwright is preferred: a track whose scenery throws still
        renders a plausible-looking picture of the road with no scenery on it.
        """
        # Before the shot, not after: a browser that never ran leaves the old
        # file in place, and its size then reads as a successful picture.
        if os.path.exists(out):
            os.remove(out)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        if self.backend == "playwright":
            self._playwright_shot(url, out)
        elif self.backend == "chrome":
            self._chrome_shot(url, out)
        else:
            raise RuntimeError(
                "no way to take a picture: no Playwright in this venv and no "
                "Chrome on PATH or in /Applications. `pip install playwright && "
                "playwright install chromium` into drive/venv.")
        return os.path.getsize(out) if os.path.exists(out) else None

    def _playwright_shot(self, url, out):
        page = self._browser.new_page(
            viewport={"width": self.size[0], "height": self.size[1]})
        seen = []
        page.on("console",
                lambda m: seen.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: seen.append("uncaught: %s" % e))
        try:
            page.goto(url, wait_until="load", timeout=max(30000, self.budget_ms))
            page.wait_for_timeout(self.budget_ms)
            page.screenshot(path=out)
        finally:
            for msg in seen:
                self.errors.append((url, msg))
            page.close()

    def _chrome_shot(self, url, out):
        chrome = find_chrome()
        cmd = ([chrome, "--headless=new"] + GL_FLAGS +
               ["--hide-scrollbars",
                "--window-size=%d,%d" % self.size,
                "--virtual-time-budget=%d" % self.budget_ms,
                "--screenshot=" + out, url])
        subprocess.run(cmd, capture_output=True)


def describe_backend():
    if have_playwright():
        return "playwright chromium"
    c = find_chrome()
    return c if c else "NONE - cannot take pictures"
