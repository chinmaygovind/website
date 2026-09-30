"""A lap is timed where the car crossed the line, not where the frame landed.

The board used to read `nowMs - startedAt` on the frame that noticed the finish:
the crossing plus however long that frame took to come round. Physics runs in
fixed 1/120s steps, so that was up to a frame of pure timing luck on every lap -
BotTyler's five Chicane laps sit 1.7 to 4.0ms after their crossing steps - and
it moved the board by milliseconds between laps driven identically.

`Run._finishTime` interpolates the crossing inside the step that made it. These
drive a car through the real finish gate at a known speed, frame by frame through
the real `Stepper` and `Run`, and require the reported time to be the analytic
crossing time whatever the frame rate.
"""

import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="quickjs is not installed")

GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")

# A straight run at constant speed onto the finish gate, stepped the way game.js
# steps it: the clock starts on a frame with no physics, then each frame runs
# the stepper with `noteStep` before every step and `update` after the frame.
HARNESS = """
var BUILT = null;
function lap(fps, jitter, D, v, stallAt, withStepper) {
  const track = TRACKS.find(t => t.slug === 'chicane');
  BUILT = BUILT || buildTrack(track, T);
  const run = new Run(new Course(BUILT), track);
  const g = run.finish;
  const car = {
    pos: {x: g.p[0] - g.f[0] * D, y: g.p[1] + 0.5 - g.f[1] * D, z: g.p[2] - g.f[2] * D},
    vel: {x: g.f[0] * v, y: g.f[1] * v, z: g.f[2] * v},
    fwd: {x: g.f[0], y: g.f[1], z: g.f[2]}, speed: v, steer: 0,
    quat: {x: 0, y: 0, z: 0, w: 1}, flags: () => 0, setRespawn() {},
  };
  const stepper = new Stepper(T);
  let now = 1000, seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  stepper.reset();
  run.start(now);
  run.nextCp = run.cps.length;
  run.update(car, now, null, withStepper ? stepper : undefined);
  for (let k = 0; k < 5000 && run.state !== 'done'; k++) {
    let dt = (1 / fps) * (1 + jitter * (rnd() - 0.5));
    if (k === stallAt) dt = 1.0;
    now += dt * 1000;
    stepper.run(dt, (h) => {
      run.noteStep(car, {throttle: 1}, now);
      car.pos.x += car.vel.x * h; car.pos.y += car.vel.y * h; car.pos.z += car.vel.z * h;
    });
    run.update(car, now, null, withStepper ? stepper : undefined);
  }
  return {done: run.state === 'done', time: run.time, frames: run.ghost.length,
          wall: now - 1000};
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


@pytest.mark.parametrize("fps", [60, 75, 144, 165, 240])
def test_the_time_is_the_crossing_at_every_frame_rate(rt, fps):
    # 10.3 units at 41.7/s crosses 247.0ms in: mid-step, and mid-frame at every rate.
    D, v = 10.3, 41.7
    r = rt.call("lap(%d, 0.3, %r, %r, -1, true)" % (fps, D, v))
    assert r["done"]
    assert r["time"] == round(D / v * 1000)


@pytest.mark.parametrize("fps", [60, 144, 240])
def test_the_ghost_is_exactly_as_long_as_the_lap_it_claims(rt, fps):
    """`runcheck.time_window` is exact: frames == floor(time_ms/1000*15) + 1."""
    for D in (10.3, 12.9, 17.05, 30.0):
        r = rt.call("lap(%d, 0.3, %r, 41.7, -1, true)" % (fps, D))
        assert r["frames"] == math.floor(r["time"] / 1000 * 15) + 1, D


def test_a_stall_is_still_charged(rt):
    """A one-second frame runs only `MAX_STEPS` steps and drops the rest. Counting
    steps from zero would stop charging for it, and a throttled tab would be free
    slow motion; timing off the frame's clock keeps the lost time on the lap -
    so the result is the old frame-clock time less at most one frame, not the
    one-second physics time."""
    D, v = 41.7, 41.7
    new = rt.call("lap(144, 0.0, %r, %r, 20, true)" % (D, v))
    old = rt.call("lap(144, 0.0, %r, %r, 20, false)" % (D, v))
    assert new["done"] and old["done"]
    assert new["time"] > round(D / v * 1000) + 900
    assert 0 <= old["time"] - new["time"] <= 1000 / 144 + 1000 / 120 + 1


def test_without_a_stepper_it_is_the_frame_clock(rt):
    """The bots call `update` without one, and get what every lap got before."""
    r = rt.call("lap(60, 0.0, 10.3, 41.7, -1, false)")
    assert r["done"]
    assert r["time"] == round(r["wall"])
    assert r["time"] > round(10.3 / 41.7 * 1000)


def test_the_game_hands_update_its_stepper():
    """Without the fourth argument the game silently falls back to frame timing."""
    src = open(GAME_JS).read()
    assert re.search(r"S\.run\.update\(S\.car, now, inp, S\.stepper\)", src)
