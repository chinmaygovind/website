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

**It is two budgets, on CPU and on waiting, and it used to be one on the wall
clock.** That mattered the moment drive started running as sixteen pytest
processes at once (`scripts/parallel_pytest.py`): a test that takes 2.2s alone
takes 12.7s when it is sharing eight cores with fifteen other processes, and the
old single wall-clock budget failed four honest tests on the first parallel run.
Raising it was the documented remedy and it is the wrong one - the sleep that
started all this was twelve seconds, so a budget loose enough to survive
contention is one that would have missed the bug it was written for.

Splitting it fixes that, because **neither half is inflated by contention**:

- `CPU_BUDGET_S` is `time.process_time()` across the call - work actually done.
  A starved process does not accumulate CPU while it waits for a core, so this
  number is the same whether the machine is idle or oversubscribed. This is the
  half that catches **a loop that grew**.
- `WAIT_BUDGET_S` is wall minus CPU - time the test spent not computing. This is
  the half that catches **a real sleep**, which is pure wait and no CPU.

Contention lands in the second one, which is why it is the looser of the two, and
why it is still nowhere near twelve seconds. A `sleep(12)` shows up as ~12s of
wait against ~0s of CPU and is caught by a mile; sixteen processes queueing for
eight cores cost a couple of seconds of wait on a test that does a couple of
seconds of work.

**Failing the offending test rather than the session** is deliberate. It was
written when `drive` ran under `pytest-xdist`, where `pytest_sessionfinish` runs
once per worker and an exit status set there does not reliably reach the
controller. Drive runs as separate processes now - see `drive/docs/testing.md`
for why xdist cannot work in this module at all - and the reasoning holds for
that too: a failed report names the culprit, where a session-level status would
be one process of forty-nine exiting non-zero without saying which test did it.

Mark a test `@pytest.mark.slow` to opt out, which is a decision somebody should make
on purpose. **Two tests in drive need it**, and they are the same kind:
`test_the_cap_model_changes_nothing_on_a_track_without_any` and
`test_a_point_to_point_track_is_unaffected` both work over the whole track pool,
so they are O(pool) rather than slow by accident, and they grow every time a
track is added. That is the honest use of the marker - the guard is for a sleep
or a loop that grew *unnoticed*, and a test whose cost is the point is neither.
"""

import os
import sys
import tempfile
import time

import pytest

# **Two budgets, and the reasoning for both is in the module docstring above.**
#
# CPU: the slowest honest test does about 2.2s of real work
# (`test_a_lap_the_physics_drove_is_accepted[bigred]`, which drives a lap of the
# longest track in the pool and re-drives it). 10s is four and a half times that
# and well under the twelve-second sleep that prompted any of this. It does not
# move with machine load, so unlike the wall-clock budget it replaced there is no
# reason to keep raising it.
CPU_BUDGET_S = 10.0

# Waiting: wall minus CPU. Nothing here is supposed to block on anything - no
# network, no real sleeps, SQLite on a local file - so in a serial run this is
# near zero for every test. It is set at 8s to leave room for sixteen processes
# queueing for eight cores, which costs a second or two on the tests that do the
# most work. A real `eventlet.sleep(12)` is 12s of pure wait and is still caught
# with four seconds to spare.
WAIT_BUDGET_S = 8.0

# Kept as the name the old single budget had, since `docs/testing.md` and the
# messages below refer to "the budget". It is the CPU one.
SLOW_TEST_BUDGET_S = CPU_BUDGET_S

# CPU time consumed by each test's call phase, filled in by the hook below.
# `report.duration` is wall clock and pytest offers no CPU equivalent.
_cpu_used = {}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: this test is allowed to exceed the per-test time budget")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Record how much CPU the call phase actually burned."""
    started = time.process_time()
    try:
        yield
    finally:
        _cpu_used[item.nodeid] = time.process_time() - started


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.when != "call" or not report.passed:
        return                       # a failure already has something to say
    if item.get_closest_marker("slow"):
        return

    cpu = _cpu_used.pop(item.nodeid, None)
    if cpu is None:
        return                       # never ran the call phase; nothing to judge
    wait = max(0.0, report.duration - cpu)

    if cpu > CPU_BUDGET_S:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} used {cpu:.2f}s of CPU, over the "
            f"{CPU_BUDGET_S:.0f}s budget (wall {report.duration:.2f}s).\n\n"
            "This is work actually done, not time waiting, so it is not the "
            "machine being busy - it is almost always a loop that grew.\n"
            "If the test genuinely needs the time, mark it @pytest.mark.slow "
            "and say why."
        )
    elif wait > WAIT_BUDGET_S:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} spent {wait:.2f}s not computing "
            f"(wall {report.duration:.2f}s, CPU {cpu:.2f}s), over the "
            f"{WAIT_BUDGET_S:.0f}s budget.\n\n"
            "Almost always a real sleep on a code path a test calls "
            "synchronously - see _close_race / RESULTS_HOLD_S in app.py for the "
            "one that prompted this budget.\n"
            "If the machine was simply overloaded this can be a false alarm; if "
            "the test genuinely needs to wait, mark it @pytest.mark.slow and say "
            "why."
        )


# ---------------------------------------------------------------------------
# What counts as a track folder on disk
# ---------------------------------------------------------------------------

# The name `test_track_folders.py` writes its deliberately-broken folders under,
# with the xdist worker id appended so sixteen of them do not collide.
SCRATCH_PREFIX = "zzscratch"

TRACKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tracks")


def track_folders():
    """Every real track folder in `tracks/`, newest listing, scratch excluded.

    **Four test files used to list that directory themselves and all four were a
    race.** `test_track_folders.py` writes a folder into the live `tracks/` tree
    and takes it away again - which is the only honest way to test that a broken
    folder cannot take the pool down - and while it is there, anything else
    reading the directory sees a track that is about to stop existing. Serially
    that is invisible, because the writer and the readers never overlap. Run the
    suite in parallel processes and it is a `FileNotFoundError` on
    `tracks/zzscratch/track.py` in a test that has nothing to do with any of it.

    So the exclusion lives here, once, rather than in each caller: a scratch
    folder is the suite's own scaffolding and was never a track. The one file
    that *is* about those folders looks for them by name and does not use this.
    """
    return sorted(d for d in os.listdir(TRACKS_DIR)
                  if not d.startswith(SCRATCH_PREFIX)
                  and os.path.exists(os.path.join(TRACKS_DIR, d, "track.py")))


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
# Building a track in QuickJS once per runtime instead of once per test
# ---------------------------------------------------------------------------

# **`buildTrack` is the most expensive call in the suite and most of the calls
# are for a track that was already built.** It is a second for Spa, 0.9s for
# Monaco, 0.7s for the Costco - it lays every quad of the mesh and every
# triangle of the collider - and files like `test_closed_lap.py` call it once
# per test for the same three circuits, so the same second is paid nine times.
#
# `Course` copies six references off the result and adds nothing to it, and
# nothing in `Run` writes to `gates`, `line` or `collider` - they are read
# straight through - so two tests can share one built track. That is checked
# rather than assumed: break any of the behaviour these files pin and they still
# go red, because what they walk through a gate is their own stub car and their
# own fresh `Run`.
#
# **Keyed on the track object, not on its slug.** A slug is not unique to a
# document - the editor reuses `draft` for every draft in flight, and
# `from_document` can hand back a different track under a slug that is already
# in the pool - so a slug key could serve one track's mesh for another's. Two
# calls with the same object are asking for the same thing; two documents are
# two objects, and each gets built.
#
# Opt-in, per runtime, and only from a fixture: `verify.py`'s runtime is the
# anti-cheat's and must keep building exactly what it is asked to build.
# **Capped, because a built track is big and the context is not.** Holding the
# whole pool at once is an `InternalError: out of memory` out of QuickJS's 512MB
# - `test_a_point_to_point_track_is_unaffected` builds all 22 in one expression
# and found it immediately. Four is chosen off the shape of the callers rather
# than as a round number: the files that repeat a build repeat it over the three
# closed circuits, so the working set is three, and a sweep over the pool churns
# through the cap and keeps no more resident than not memoizing would.
MEMO_BUILD_TRACK = """
(function () {
  var real = buildTrack;
  var memo = new Map();
  var CAP = 4;
  buildTrack = function (track, T) {
    if (!track || typeof track !== 'object') return real(track, T);
    if (memo.has(track)) {
      var hit = memo.get(track);      // freshen: Map keeps insertion order,
      memo.delete(track);             // so re-inserting makes this the newest
      memo.set(track, hit);
      return hit;
    }
    var built = real(track, T);
    memo.set(track, built);
    while (memo.size > CAP) memo.delete(memo.keys().next().value);
    return built;
  };
})();
"""


def memoize_build_track(rt):
    """Make `buildTrack` in this runtime build each track object once.

    For a fixture that hands one runtime to many tests. Returns the runtime so
    it can be used inline.
    """
    rt.eval(MEMO_BUILD_TRACK)
    return rt


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
# Empty, and kept rather than deleted: it is the escape hatch the *next* brand
# new folder needs on the commit that adds it, since a track nobody has driven
# has no record to cut a line off. Every track in the pool has one now.
NO_HOTLAP_YET = {"dino"}

# Waiting on a board deep enough to cut a standard from - five or so distinct
# players. Drop the entry, then, on the box:
#     venv/bin/python tools/set_medals.py --db instance/tickettoride.db --write
# Empty: every track in the pool now declares its own three times. Kept rather
# than deleted because it is the escape hatch a brand-new folder needs on the
# commit that adds it - a track nobody has driven has no board to cut from.
NO_CUT_MEDALS_YET = {"silverstone", "monaco", "dino"}


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
    # Switch off the background room sweep. It is spawned at import, so every
    # boot below would otherwise leave behind another greenlet sleeping five
    # minutes in a loop that never returns - hundreds of them over a full run,
    # and a process that will not exit promptly. See the note beside
    # `eventlet.spawn(_stale_cleanup)` in app.py, including what it is *not*.
    os.environ["DRIVE_SWEEP"] = "0"
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

    **The `-wal` and `-shm` sidecars are deleted too, and leaving them out was a
    13GB leak.** SQLite in WAL mode keeps its journal in `<path>-wal` and its
    index in `<path>-shm`, both created beside the database and neither named by
    `mkstemp`. Unlinking only `path` left the two of them behind on every one of
    the ~500 boots a full run does, and `/tmp` here is a **tmpfs** - so the
    droppings were not on a disk with 300GB spare, they were in RAM. Eight
    thousand of each had accumulated to 13GB of a 16GB `/tmp`, which is where
    the "out of disk" and the machine's missing memory came from.

    `missing_ok`, because the sidecars only exist if the connection was in WAL
    mode and had something to journal - a test that booted the app and never
    wrote leaves neither.
    """
    if verify is not None:
        os.environ.pop("DRIVE_VERIFY", None)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass
