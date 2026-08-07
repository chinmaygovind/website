"""Nobody gets a run-up before the clock starts.

The bug this file exists for was found from the leaderboard rather than from a
failure. Two drivers holding the throttle flat from the line to the first
checkpoint were finishing that split ~26ms apart, consistently, on Chicane Park
and Sandy Cove. It was not skill and it was not the spawn point - every stored
lap starts within 8mm of the same place.

It was the order of three lines in the frame loop:

    S.run.start(now)          # clock zero
    S.stepper.run(dt, ...)    # car accelerates under throttle
    S.run.update(S.car, now)  # time = now - startedAt = 0

so the car had already been accelerated for a frame when the clock recorded that
it had not moved. On top of that `Stepper.acc` carried up to one `FIXED_DT` of
time *across* the start, so the number of free substeps was 0 to 4 depending on
frame timing - which made a **low frame rate an advantage**, worth up to ~33ms of
unrecorded run-up.

`Stepper` runs for real in QuickJS here (it only moves a float about, so it needs
no world), and the two frame-loop lines are read out of `game.js`, because
reaching them needs a browser, a track and a keypress.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="quickjs is not installed")

GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")

# A Stepper and a counter for how many substeps a frame actually ran.
HARNESS = """
var stepper = new Stepper(T);
function substeps(dt) {
  var n = 0;
  stepper.run(dt, function () { n++; });
  return n;
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


@pytest.mark.parametrize("fps", [72, 90, 100, 144])
def test_a_carried_remainder_is_worth_a_whole_extra_substep(rt, fps):
    """The size of the unfairness, asserted rather than described: two frames of
    the identical length run a *different* number of physics substeps depending
    only on what was left in the accumulator beforehand.

    **Not tested at 60fps, and that is the interesting part.** `FIXED_DT` is
    1/120, so a perfect 1/60 frame is exactly two substeps and leaves nothing
    behind - at exactly 60 the remainder can never buy anything, which is why the
    first version of this test failed and why the bug is not a flat "one frame
    free for everyone". It bites when the frame length is not a whole number of
    substeps: every refresh rate that is not 60 or 120, and any real 60Hz frame
    once vsync jitter is in it.

    The behaviour itself stays correct everywhere except the start of a lap. That
    is what a fixed-step accumulator is *for* - it is only unfair when the clock
    it is being compared against starts in the middle of it.
    """
    dt = 1 / fps
    assert abs(dt / T.FIXED_DT - round(dt / T.FIXED_DT)) > 1e-9, \
        f"{fps}fps divides evenly into FIXED_DT; pick another for this test"
    rt.eval("stepper.reset();")
    clean = rt.call("substeps(%r)" % dt)
    rt.eval("stepper.acc = %r;" % (T.FIXED_DT * 0.99))
    carried = rt.call("substeps(%r)" % dt)
    assert carried == clean + 1, (
        f"at {fps}fps a carried remainder should buy one extra substep, "
        f"got {clean} then {carried}")


def test_reset_drops_the_remainder(rt):
    """So a lap can start from a known state whatever the frame before it did."""
    rt.eval("stepper.acc = %r;" % (T.FIXED_DT * 0.99))
    rt.eval("stepper.reset();")
    assert rt.call("stepper.acc") == 0


@pytest.mark.parametrize("fps", [30, 60, 120, 144])
def test_after_a_reset_every_frame_rate_starts_from_the_same_place(rt, fps):
    """The fairness property, across the range of machines people actually play on.

    After a reset, the substeps a frame runs depend only on its own length - so the
    run-up before the clock is the same story on every machine instead of a
    lottery. Checked against its own absence: without the reset a carried
    remainder makes this differ, which the first test in this file pins.
    """
    rt.eval("stepper.reset();")
    first = rt.call("substeps(%r)" % (1 / fps))
    rt.eval("stepper.reset();")
    again = rt.call("substeps(%r)" % (1 / fps))
    assert first == again
    # And it is what the frame length says it should be, not one more.
    assert first == int((1 / fps) / T.FIXED_DT)


def _frame_loop():
    """The function that starts the clock, sliced out of game.js."""
    src = open(GAME_JS).read()
    i = src.index("S.run.start(now)")
    j = src.index("const events = S.run.update(S.car, now)")
    assert i < j, "the frame loop no longer starts the clock before it updates"
    return src[i - 2000:j]


def test_the_clock_starting_resets_the_accumulator():
    """Otherwise the lap inherits whatever the previous frame had left over.

    Asserted as *adjacent to the call it guards*, not as "the string appears
    somewhere in the loop". The loose version passed with the solo reset deleted,
    because the race path resets too and that was enough to satisfy it - the same
    way a test is satisfied by any occurrence of a string it did not mean.
    """
    loop = _frame_loop()
    for start in ("S.run.start(now)", "S.run.start(S.raceT0)"):
        assert re.search(r"S\.stepper\.reset\(\);\s*\n\s*" + re.escape(start), loop), \
            f"{start} is not preceded by a stepper reset"


def test_the_car_does_not_move_on_the_frame_the_clock_starts():
    """`run.update` samples the car at the end of the frame, so if the physics ran
    it would record a moving car at t=0 - which is the whole bug. The step is
    skipped on that one frame, which costs everybody one frame of throttle and
    gives nobody a run-up."""
    loop = _frame_loop()
    assert "clockStarting = true" in loop
    assert "!S.paused && !clockStarting" in loop, \
        "the physics still runs on the frame the clock starts"
