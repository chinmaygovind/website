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
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


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


def test_a_point_to_point_track_is_unaffected(rt):
    """Nothing here may touch the thirteen tracks that are not rings."""
    flags = rt.call(
        "TRACKS.map(function (t) {"
        "  var c = new Course(buildTrack(t, T));"
        "  return [t.slug, !!new Run(c, t).closed]; })")
    closed = sorted(s for s, c in flags if c)
    assert closed == sorted(CLOSED), \
        "Run.closed disagrees with tracks.CLOSED: %r" % (flags,)
