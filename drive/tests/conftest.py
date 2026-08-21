"""A budget on how long one test may take.

This exists because of a bug that cost nothing but time and was therefore invisible.
`_close_race` had an inline `eventlet.sleep(12)` - correct in production, where it
runs in a greenlet, and twelve real seconds in the two tests that called it
synchronously. That was **24s of a 56s suite**, so most of why a deploy felt slow,
and *every test passed the whole time*. There was no failure to chase: the only
symptom was the clock, and nobody reads the clock.

So the clock gets an assertion. A test that suddenly takes seconds is nearly always
one of two things - a real sleep, or a loop that grew - and both are worth being told
about at the moment they land rather than a month later.

**Failing the offending test rather than the session** is deliberate: `drive` runs
under `pytest-xdist` (`-n 4 --dist loadfile`), where `pytest_sessionfinish` runs once
per worker and an exit status set there does not reliably reach the controller. A
failed report does, and it names the culprit instead of just the total.

Mark a test `@pytest.mark.slow` to opt out, which is a decision somebody should make
on purpose. **Exactly one test in drive has needed it**, and it is worth knowing which
kind: `test_the_cap_model_changes_nothing_on_a_track_without_any` speed-profiles the
whole track pool twice, so it is O(pool) rather than slow by accident, and it grows
every time a track is added. That is the honest use of the marker - the guard is for
a sleep or a loop that grew *unnoticed*, and a test whose cost is the point is neither.
"""

import os
import sys
import tempfile

import pytest

# Six times the slowest honest test (`test_a_real_lap_passes_the_anti_cheat[rainbow]`,
# ~1.6s) and still under the 12s sleep that prompted this.
#
# **It was 5s, and 5s produced a false failure.** A wall-clock budget is sensitive to
# whatever else the machine is doing: with a stuck earlier run competing for cores,
# the rainbow sim went from 1.6s to over 5s and this guard failed it. Nothing was
# wrong with the test. CI runners are noisy in exactly that way, and a guard that
# fails a deploy for load is worse than the slow suite it was added to prevent.
#
# 10s keeps the thing it was for - a real sleep is a second or more, and the one that
# started this was twelve - while leaving enough room that ordinary contention cannot
# trip it. If it ever false-fails again, raise it rather than deleting it, or mark the
# offending test `slow`.
SLOW_TEST_BUDGET_S = 10.0


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: this test is allowed to exceed the per-test time budget")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.when != "call" or not report.passed:
        return                       # a failure already has something to say
    if item.get_closest_marker("slow"):
        return
    if report.duration > SLOW_TEST_BUDGET_S:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} took {report.duration:.2f}s, over the "
            f"{SLOW_TEST_BUDGET_S:.0f}s per-test budget.\n\n"
            "Almost always a real sleep on a code path a test calls synchronously "
            "(see _close_race / RESULTS_HOLD_S in app.py for the one that prompted "
            "this budget), or a loop that grew.\n"
            "If the test genuinely needs the time, mark it @pytest.mark.slow and "
            "say why."
        )


# ---------------------------------------------------------------------------
# A replay that actually drives the track
# ---------------------------------------------------------------------------
#
# `runcheck.validate` compares a submitted replay against the course now - past
# every gate, when the splits say, without leaving the corridor - so a test that
# wants an *acceptable* run can no longer hand it a straight line from the spawn.
# It lives here rather than in either test file because both need it and this
# repo would rather have one copy than two that agree.

def lap_frames(track, seconds=None, hz=None):
    """Down the middle of the ribbon at a constant speed, start gate to finish."""
    import bisect
    import math
    import runcheck
    import tuning as T

    hz = hz or runcheck.GHOST_HZ
    seconds = seconds or track["ideal"]
    pts = [st["p"] for st in track["line"]]
    fin = next((g for g in track["gates"] if g["kind"] == "finish"), None)
    # Stop at the flag; the ribbon runs past it. On a closed track the flag is
    # the start line and the whole ribbon is the lap, so there is nothing to cut.
    if fin is not None and not track.get("closed"):
        pts = pts[:fin["si"] + 1]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    total = cum[-1]
    # One more than the obvious count: `Run._recordGhost` writes a frame while
    # `_ghostN / hz <= t`, which `runcheck.time_window` now depends on exactly.
    n = max(2, int(seconds * hz) + 1)
    out = []
    for i in range(n):
        s = total * i / (n - 1)
        j = min(bisect.bisect_right(cum, s) - 1, len(pts) - 2)
        u = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        p = [pts[j][k] + (pts[j + 1][k] - pts[j][k]) * u for k in range(3)]
        out.append([p[0], p[1] + T.RIDE_HEIGHT, p[2], 0, 0, 0, 1])
    return out


def lap_splits(track, frames):
    """The splits that replay really sets, read off its own gate crossings."""
    import runcheck
    cps, _ = runcheck._gates_of(track)
    ceil = track.get("gate_ceil") or 5.0
    out, at = [], 0
    for gate in cps:
        hits = [i for i in runcheck._crossings(gate, frames, ceil) if i >= at]
        at = hits[0] if hits else at
        out.append(int(round(at / runcheck.GHOST_HZ * 1000)))
    return out


# ---------------------------------------------------------------------------
# Tracks that have landed but are not yet cut to anybody's pace
# ---------------------------------------------------------------------------

# **Two things in this suite are cut from times people have actually driven**,
# and neither can exist on the commit that adds a track: `tools/hotlap.py` reads
# the standing record off a running site, and `tools/set_medals.py` reads the
# board. Both have a documented fallback - the relaxed line for the quick bots,
# and derived medals from `laptime.ideal` - so a new track works, it is just not
# yet tuned to anybody's pace. Without somewhere to say that, a new track cannot
# ship at all: the site has to be live for anyone to drive it and the deploy is
# gated on this suite.
#
# **These are two lists and not one, because the two become available at
# different times.** A hot lap needs exactly one lap to exist. Cut medals need a
# *board*: gold is `min(5th best, WR x 1.06)`, and on a one-row board the fifth
# best degenerates to the record itself, so gold comes out equal to the record
# and nobody but its holder can ever earn it - strictly worse than the soft
# derived gold it replaced. `drive_times` holds one row per user per track, so a
# thin board is not fixed by driving more laps; it is fixed by more people
# playing. Tokyo Drift is the track that found this: it had a hot lap the day it
# shipped and could not have honest medals for weeks.
#
# Each test asserts the *absence* of what it is waiting for, so an entry left
# behind after the real thing lands fails loudly instead of quietly disabling a
# check.

# Waiting on a single lap. Drop the entry, then:
#     venv/bin/python tools/hotlap.py <slug> --site https://drive.cgovind.com
# Empty: every track in the pool has a lap on the board and a fast line cut from
# it. Kept rather than deleted because it is the escape hatch a brand-new folder
# needs on the commit that adds it - a track nobody has driven has no record to
# cut a line off.
NO_HOTLAP_YET = {"silverstone"}

# Waiting on a board deep enough to cut a standard from - five or so distinct
# players. Drop the entry, then, on the box:
#     venv/bin/python tools/set_medals.py --db instance/tickettoride.db --write
# Empty: every track in the pool now declares its own three times. Kept rather
# than deleted because it is the escape hatch a brand-new folder needs on the
# commit that adds it - a track nobody has driven has no board to cut from.
NO_CUT_MEDALS_YET = {"silverstone"}


# ---------------------------------------------------------------------------
# Booting the app under test
# ---------------------------------------------------------------------------
#
# This replaced fifteen hand-maintained copies of the same fixture, one per test
# file. They agreed on the hard part and disagreed on the list below, which is
# the part that has to be right.

# The modules re-imported for every test that boots the app.
#
# `app` and `models` are the obvious two: the fixture gives each test its own
# SQLite file, so it needs its own `db` and its own Flask app on top of it.
#
# **`portal` is the one that was easy to miss, and was missed.** It does
# `from models import ..., db` at module level, so it captures whichever `db`
# object was live the first time it was imported. Only three of the fifteen
# fixtures popped it, and they were the three that exercise portal
# (`test_make`, `test_portal`, `test_publish`) - so the other twelve ran any
# portal code path against a `db` bound to a SQLite file that had already been
# deleted. It had been managed correctly, by hand, per file, and silently.
# Popping it here is a fix, not just a tidy-up.
#
# **`botsim` is deliberately absent.** It holds `_rt`, a QuickJS runtime that
# costs up to `BUILD_LIMIT_S` (30 seconds) to build, and it holds no `db`
# reference at all - so keeping it across tests is both safe and most of why
# `test_bots.py` is not unbearable. Tests that need its *worlds* cleared do that
# in their own teardown with `botsim.drop()`, which is the narrow fix rather
# than throwing the runtime away.
#
# **Anything split out of `app.py` belongs in this list.** A module left out
# stays cached while `app` is re-imported fresh, holding the previous test's
# `app`, `db` and module globals. That is order-dependent contamination: it
# shows up as tests that pass alone and fail together, or worse, pass wrongly.
# Popping a module that was never imported is a no-op, so there is no cost to
# naming one here early.
RELOADED = ("app", "maker", "models", "portal", "backfill_race_activity")


def boot_app(verify=None, **environ):
    """A fresh `app` and `db` on a throwaway SQLite file. Returns `(A, path)`.

    `A` is the `app` *module*, not the Flask object - the suite reaches through
    it for module globals (`A._rooms`, `A._seat_bot`, and `A.maker.ADMIN_NAMES`
    for the half that now lives in `maker.py`), which is
    also why the import has to be genuinely fresh rather than a config poke.

    `verify` sets `DRIVE_VERIFY` ("0" to switch the re-simulation off, "1" to
    switch it on) and is read at import, so it cannot be changed afterwards.
    Pass it here or not at all. Anything else in `environ` is set the same way,
    with `None` meaning "remove this variable".

    Pair every call with `close_app`.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path
    if verify is not None:
        os.environ["DRIVE_VERIFY"] = verify
    for key, value in environ.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    for mod in RELOADED:
        sys.modules.pop(mod, None)
    import app as A
    A.app.config["TESTING"] = True
    with A.app.app_context():
        A.db.drop_all()
        A.db.create_all()
    return A, path


def close_app(path, verify=None):
    """Undo `boot_app`: drop the `DRIVE_VERIFY` override, delete the database.

    `verify` only has to be truthy-or-not here; it is passed as the same value
    the boot used so the two calls read as a pair.
    """
    if verify is not None:
        os.environ.pop("DRIVE_VERIFY", None)
    os.unlink(path)
