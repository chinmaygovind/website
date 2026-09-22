"""Driving off the grid on a ring is not missing a checkpoint.

Spa is the one closed circuit in the pool, which means its finish gate *is* its
start gate (`Builder.finish_at_start`) and the first thing any lap does is cross
the line. `Run._advance` already knew not to *finish* there - it will not credit
a finish until every checkpoint is behind you - but the other half of that
branch was never told, so the same crossing fell through to "you skipped one"
and every attempt at Spa opened with **Missed a checkpoint!** before the car had
reached the first corner.

`Run` runs for real in QuickJS here against a stub car. It only reads a
position, a heading, a speed and a quaternion off it, so this needs no physics
and no world - which is what makes it cheap enough to walk a car through a gate
a sample at a time and watch the event stream.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="quickjs is not installed")

# A car with nothing on it but the six things `Run.update` reads, and a walk
# that carries one through a gate along that gate's own normal. Offsets are
# fractions of `gateNear` because outside that band the gate is not tracked at
# all, so a walk in absolute units would silently stop testing anything.
HARNESS = r"""
function stubCar(p, f) {
  return {
    pos: { x: p[0], y: p[1], z: p[2] },
    fwd: { x: f[0], y: f[1], z: f[2] },
    speed: 30,
    quat: { x: 0, y: 0, z: 0, w: 1 },
    flags: function () { return 0; },
    setRespawn: function () {},
  };
}

function makeRun(slug) {
  var track = TRACKS.find(function (t) { return t.slug === slug; });
  var course = new Course(buildTrack(track, T));
  var run = new Run(course, track);
  run.start(1000);
  return { run: run, course: course, track: track };
}

/** Walk a car through a gate and hand back every event it produced. */
function through(ctx, gate) {
  var near = ctx.course.gateNear;
  var out = [];
  ctx.run._sides.clear();          // arrive fresh, as if from down the road
  var at = [-0.8, -0.4, -0.1, 0.1, 0.4, 0.8];
  for (var i = 0; i < at.length; i++) {
    var d = at[i] * near;
    var p = [gate.p[0] + gate.f[0] * d,
             gate.p[1] + 0.6 + gate.f[1] * d,
             gate.p[2] + gate.f[2] * d];
    var ev = ctx.run.update(stubCar(p, gate.f), 2000 + i * 50);
    for (var k = 0; k < ev.length; k++) out.push(ev[k]);
  }
  return out;
}
"""


@pytest.fixture(scope="module")
def rt():
    # **The memory limit is a function of how many closed circuits there are.**
    # `memoize_build_track` keeps every track it has built alive in this one
    # context, which is what makes the suite quick - `makeRun` builds the track
    # on every call and Spa alone is a second a time - but it also means the
    # meshes accumulate rather than being collected between tests. A circuit of
    # this size wants 128-160MB to build, so the default 512 covered four and
    # ran out on the fifth: Suzuka arrived and monza, monaco and suzuka started
    # failing with `InternalError: out of memory` inside `addScenery`, which
    # reads as a fault in whichever track happened to be built last rather than
    # as the ceiling it is.
    #
    # Raising it is the right fix and not a mask, because nothing in production
    # builds more than one track per context: `verify.py` runs at
    # `MEMORY_MB = 256` and re-drives one lap on one circuit, and both Spa and
    # Suzuka build inside that on their own. The number below is the *test
    # harness's* cost of memoizing the whole closed-lap pool, so it goes up
    # again with the sixth one.
    r = jsrt.Runtime(memory_mb=1280)
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    from conftest import memoize_build_track
    return memoize_build_track(r)


def closed_slugs():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import tracks as tracks_mod
    return [t["slug"] for t in tracks_mod.TRACKS if t.get("closed")]


CLOSED = closed_slugs()


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_leaving_the_grid_is_not_a_missed_checkpoint(rt, slug):
    """The one that was wrong: cross your own start line with nothing behind you."""
    events = rt.call(
        "(function () { var c = makeRun(%s);"
        " return through(c, c.course.finishGate()); })()" % json.dumps(slug))
    assert "missed" not in events, (
        "%s warns about a missed checkpoint as the car leaves the grid: %r"
        % (slug, events))


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_crossing_the_line_early_does_not_finish_the_lap(rt, slug):
    """The other half of the same crossing, and the older guard.

    If this ever goes, a closed track finishes the instant it starts.
    """
    state = rt.call(
        "(function () { var c = makeRun(%s);"
        " through(c, c.course.finishGate());"
        " return { state: c.run.state, cps: c.run.nextCp }; })()" % json.dumps(slug))
    assert state["state"] == "running"
    assert state["cps"] == 0


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_coming_back_round_having_skipped_one_still_warns(rt, slug):
    """The suppression is `nextCp === 0`, not "this track is a ring".

    Pinning it this way is the difference between not telling somebody off for
    starting and never telling them anything. Reach the line part way through
    the checkpoints and it is a real skip, on a ring exactly as anywhere else.
    """
    events = rt.call(
        "(function () { var c = makeRun(%s);"
        " c.run.nextCp = 3;"        # part way round, several gates behind you
        " return through(c, c.course.finishGate()); })()" % json.dumps(slug))
    assert "missed" in events, (
        "%s says nothing when you cross the line having skipped one: %r"
        % (slug, events))


@pytest.mark.slow
def test_a_point_to_point_track_is_unaffected(rt):
    """Nothing here may touch the tracks that are not rings.

    **Marked `slow` for the same reason as
    `test_every_track_can_be_built_without_a_browser`**, and it is the same
    shape: a `buildTrack` over the entire pool, which at sixteen tracks is about
    11s against the 10s budget. The two of them are the only tests in drive that
    cost O(the pool), which is why they are the only two carrying this marker -
    and why which of them trips the budget first depends on what else the
    machine is doing rather than on either of them changing.
    """
    flags = rt.call(
        "TRACKS.map(function (t) {"
        "  var c = new Course(buildTrack(t, T));"
        "  return [t.slug, !!new Run(c, t).closed]; })")
    closed = sorted(s for s, c in flags if c)
    assert closed == sorted(CLOSED), \
        "Run.closed disagrees with tracks.CLOSED: %r" % (flags,)


# ---------------------------------------------------------------------------
# Multi-lap races
# ---------------------------------------------------------------------------
# A room on a circuit races several laps of it (`Laps` in the room drawer), and
# `Run.laps` is the whole of what that means to the car: crossing the line with
# every checkpoint behind you is a *lap* until the last one, and only then a
# finish. These are the two sides of that branch, plus the thing the branch is
# not allowed to do to the progress the standings are ordered by.


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_a_lap_of_a_multi_lap_race_is_not_the_finish(rt, slug):
    """Cross the line with everything behind you, with laps still to run."""
    state = rt.call(
        "(function () { var c = makeRun(%s);"
        " c.run.laps = 3; c.run.nextCp = c.run.cps.length;"
        " var ev = through(c, c.course.finishGate());"
        " return { ev: ev, state: c.run.state, lap: c.run.lap,"
        "          cps: c.run.nextCp }; })()" % json.dumps(slug))
    assert state["ev"] == ["lap"], state["ev"]
    assert state["state"] == "running"
    assert state["lap"] == 1
    # And the checkpoints have to be taken again, or the second lap is a
    # formality that ends the moment the car reaches the line.
    assert state["cps"] == 0


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_the_last_lap_of_a_multi_lap_race_finishes(rt, slug):
    """And the other side of it: the third crossing of a three-lap race."""
    state = rt.call(
        "(function () { var c = makeRun(%s);"
        " c.run.laps = 3; c.run.lap = 2; c.run.nextCp = c.run.cps.length;"
        " var ev = through(c, c.course.finishGate());"
        " return { ev: ev, state: c.run.state }; })()" % json.dumps(slug))
    assert "finish" in state["ev"], state["ev"]
    assert state["state"] == "done"


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_progress_keeps_climbing_past_the_length_of_the_lap(rt, slug):
    """`bestS` is the race, not the lap - and it is signed.

    It is what the standings are ordered by and what the catch-up boost measures
    a gap with, so a car on lap three has to read as ahead of one on lap two.
    The wrap is found from the position jumping most of a lap, which is also why
    driving back over the line has to give the lap back rather than bank one:
    read as a wrap, a car that rolled backwards over its own finish line would
    gain a full lap of progress and the lead with it.

    The car is walked down the ribbon itself, two stations at a time. Note that
    the wrap is not seen the instant the line is crossed - `locate` is
    forward-biased and a ring's last station sits on top of its first, so it
    holds on to the old end of the line for the thirty-odd units it takes the
    window to fail - which is why this drives some way past it.
    """
    out = rt.call(
        "(function () { var c = makeRun(%s), total = c.course.total;"
        " var line = c.course.line, n = line.length, t = 2000;"
        " function at(i) {"
        "   var p = line[i].p;"
        "   c.run.update(stubCar([p[0], p[1] + 0.6, p[2]], [0, 0, 1]), t += 30);"
        " }"
        " var i;"
        " for (i = 0; i < n; i += 2) at(i);"          # one lap
        " for (i = 0; i < 40; i += 2) at(i);"         # and well into the next
        " var wrapped = c.run.bestS;"
        " for (i = 38; i >= 0; i -= 2) at(i);"        # back over the line
        " for (i = n - 1; i > n - 40; i -= 2) at(i);" # and away up the old end
        " return { total: total, wrapped: wrapped, after: c.run.bestS }; })()"
        % json.dumps(slug))
    # A whole lap and a little more, rather than being pinned at the length.
    assert out["wrapped"] > out["total"], out
    assert out["wrapped"] < out["total"] * 1.1, out
    # Going back round the far side of the line banks nothing.
    assert out["after"] == pytest.approx(out["wrapped"], rel=0.02), out


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_a_resumed_run_finishes_on_the_lap_it_came_back_on(rt, slug):
    """`Run.resumeAt` is what a reload mid-race puts back.

    It has to survive `start`, which is what clears the two counters, and it has
    to leave the run finishing on the crossing the race is actually decided by -
    a car that came back on lap three of three finishes at the next line, not
    two laps later.
    """
    state = rt.call(
        "(function () { var c = makeRun(%s);"
        " c.run.laps = 3;"
        " c.run.start(1000);"                    # the race clock, as on resume
        " c.run.resumeAt(2, c.run.cps.length);"  # back on the last lap, all gates
        " var ev = through(c, c.course.finishGate());"
        " return { ev: ev, state: c.run.state, lap: c.run.lap,"
        "          sLap: c.run.sLap }; })()" % json.dumps(slug))
    assert "finish" in state["ev"], state["ev"]
    assert state["state"] == "done"
    # The distance counter comes back with it, or the car reports itself most of
    # two laps down and is handed the catch-up boost for a gap it does not have.
    assert state["sLap"] == 2


@pytest.mark.parametrize("slug", CLOSED, ids=CLOSED)
def test_every_gate_of_a_race_has_its_own_index(rt, slug):
    """The stride is `cps + 1`, and the spare slot is the line.

    `_lap_progress` divides this back into a lap and a checkpoint, so two gates
    sharing a number is a reload that comes back in the wrong place - and
    `on_split` keeps the first time it is given for an index, so it is also a
    delta measured against a gate on a different lap.
    """
    seen = rt.call(
        "(function () { var c = makeRun(%s), n = c.run.cps.length, out = [];"
        " for (var lap = 0; lap < 4; lap++) {"
        "   c.run.lap = lap;"
        "   for (var i = 0; i <= n; i++) { c.run.nextCp = i; out.push(c.run.cpIndex()); }"
        " }"
        " return out; })()" % json.dumps(slug))
    assert len(seen) == len(set(seen)), "two gates share an index"
    assert seen == sorted(seen), "a later gate is numbered before an earlier one"
