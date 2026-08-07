"""Scratch harness: drive the abandon paths in a real browser.

Not a test and deliberately not in tests/. Every path that reports a run is
input-driven - a key, a click, a tab closing - and the suite can only prove the
call is *wired*. Whether `navigator.sendBeacon` actually lands on a Flask route
that reads a `text/plain` body is a question about a browser, so it takes one.

It watches the network and the database rather than the game's own state:
`game.js` is an ES module, so `S` is module-scoped and there is nothing on
`window` to read. That is the better check anyway - what matters is the request
that leaves and the row that moves, not what the client believed.

Needs a server with a login route, started separately (a backgrounded `&` inside
one shell call does not survive it):

    cat > /tmp/_srv.py <<'PY'
    import os, sys
    sys.path.insert(0, "<repo>/drive")
    os.environ["DATABASE_URL"] = "sqlite:////tmp/activity_check.db"
    import app as A
    from models import db, User
    from flask import session, redirect

    @A.app.route("/_be/<name>")
    def _be(name):
        u = User.query.filter_by(username=name).first()
        if u is None:
            u = User(username=name, email=name + "@x.com"); u.set_password("password123")
            db.session.add(u); db.session.commit()
        session["user_id"] = u.id
        session.permanent = True      # or the cookie dies with the headless run
        return redirect("/solo/sunrise")

    with A.app.app_context():
        db.create_all()
    A.app.run(host="127.0.0.1", port=5077, debug=False, threaded=True)
    PY
    venv/bin/python /tmp/_srv.py &          # in its own shell
    venv/bin/python tools/_scratch_activity_check.py

The plain Flask server rather than `socketio.run`, because `eventlet.monkey_patch()`
hangs the app's import here and solo mode needs no live socket.
"""

import json
import sqlite3
import sys
import time

PORT = 5077
DB = "/tmp/activity_check.db"
LOG = "/tmp/activity_log.jsonl"

# Distance is not asserted on. Under swiftshader the page runs at a few frames a
# second and `Stepper` will not let the accumulator run away, so a real 2.5s of
# held throttle simulates a fraction of that and the car covers a metre or two.
# That is an artifact of the harness, not of the game - what is being checked here
# is which requests leave and how many, and the seconds are wall-clock either way.


def log_since(n):
    """Every POST /api/* the server has seen past the first `n`, and the new count."""
    try:
        lines = [ln for ln in open(LOG).read().splitlines() if ln.strip()]
    except FileNotFoundError:
        return [], 0
    return [json.loads(ln) for ln in lines[n:]], len(lines)


def stats():
    con = sqlite3.connect(DB)
    try:
        row = con.execute("SELECT drive_time, distance FROM drive_stats").fetchone()
    except sqlite3.OperationalError:
        return (0.0, 0.0)
    finally:
        con.close()
    return (round(row[0] or 0.0, 3), round(row[1] or 0.0, 1)) if row else (0.0, 0.0)


def main():
    ok = True
    seen = [0]          # how many POSTs the server had logged as of the last check

    def note(label, want_activity, before, why=None, want_ct=None):
        """want_activity: True = exactly one report, False = none at all."""
        nonlocal ok
        time.sleep(1.6)
        after = stats()
        d_s = after[0] - before[0]
        fresh, seen[0] = log_since(seen[0])
        mine = [p for p in fresh if p["path"] == "/api/activity"]
        got_ct = (mine[0]["ct"] or "-").split(";")[0] if mine else "-"
        got_why = mine[0]["body"].get("why") if mine else "-"
        if want_activity:
            good = len(mine) == 1 and d_s > 0.4
            if good and why:
                good = got_why == why
            if good and want_ct:
                good = got_ct == want_ct
        else:
            good = len(mine) == 0 and abs(d_s) < 0.01
        print("  %-26s %d report  %+6.2fs  why=%-15s ct=%-16s %s"
              % (label, len(mine), d_s, got_why, got_ct, "OK" if good else "WRONG"))
        ok = ok and good
        return after

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader", "--disable-gpu-sandbox",
        ])
        ctx = br.new_context(viewport={"width": 1100, "height": 700})

        page = ctx.new_page()
        page.goto("http://127.0.0.1:%d/_be/chinmay" % PORT, wait_until="load")
        page.wait_for_selector("#tGrid button.tcard2", state="attached", timeout=60000)
        page.wait_for_selector("canvas", state="attached", timeout=60000)
        # A click first: keystrokes go to `window`, but the page has to be the thing
        # receiving them, and on a fresh headless tab it is not reliably focused.
        page.mouse.click(550, 400)
        time.sleep(8)         # swiftshader needs a moment to build the track

        def drive(pg, secs=2.5):
            pg.keyboard.down("w")
            time.sleep(secs)
            pg.keyboard.up("w")

        base = stats()
        print("start: drive_time=%.2fs distance=%.1fm" % base)

        # The clock has to be running, or nothing below means anything - and under
        # swiftshader how long the track takes to build is not a number, so this
        # holds the throttle until `/api/start` actually lands rather than guessing.
        started = []
        for attempt in range(12):
            drive(page, 1.2)
            time.sleep(0.8)
            fresh, seen[0] = log_since(seen[0])
            started = [q for q in fresh if q["path"] == "/api/start"]
            if started:
                break
        print("  %-26s %d /api/start after %d tr%s%s"
              % ("clock started at all", len(started), attempt + 1,
                 "y" if attempt == 0 else "ies",
                 "   OK" if started else "   GAME NEVER STARTED"))
        if not started:
            page.screenshot(path="/tmp/activity_check_fail.png")
            br.close()
            return 1
        page.keyboard.press("r")      # clean slate: that warm-up run is not a path
        time.sleep(1.6)
        _, seen[0] = log_since(seen[0])
        base = stats()

        # 1. R, the common abandon.
        drive(page)
        page.keyboard.press("r")
        base = note("R (restart)", True, base, why="restart")

        # 2. R again straight away: the new run is under MIN_REPORTED_MS and the
        #    old one is already claimed. Rolling off the line is not an attempt.
        page.keyboard.press("r")
        base = note("R again (nothing driven)", False, base)

        # 3. T keeps the clock running, so it is the same run - reporting there
        #    would count it twice when the lap eventually ends.
        drive(page)
        page.keyboard.press("t")
        base = note("T (back to checkpoint)", False, base)

        # 4. switching track mid-run.
        page.keyboard.press("p")
        page.wait_for_timeout(600)
        page.evaluate("""() => {
          const cards = [...document.querySelectorAll('#tGrid button.tcard2')];
          const here = document.querySelector('#tGrid .tcard2.active');
          (cards.find(c => c !== here) || cards[1]).click();
        }""")
        base = note("switch track", True, base, why="switched track")

        # 5. the tab going away - the sendBeacon path, and the whole reason
        #    /api/activity accepts a text/plain body.
        page.wait_for_selector("#tGrid button.tcard2", state="attached", timeout=60000)
        time.sleep(7)
        drive(page)
        page.close()
        base = note("close tab (beacon)", True, base, why="page hidden",
                    want_ct="text/plain")

        br.close()

    print("\n%s" % ("every path banks its run, and only once"
                    if ok else "SOMETHING IS WRONG"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
