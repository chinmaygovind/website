"""The anti-cheat, tested against laps the physics actually drove.

`verify.py` re-drives a submitted lap through the game's own `Car.step` and
decides whether the car could have done that. There is no browser in CI, so the
laps here are driven by `tests/driver.js` - the real `Car`, the real collider,
the real `Run`, and the frame loop from `game.js` in the same order, on the
keyboard. What comes out is exactly what a browser would have posted to
`/api/run`.

**The load-bearing test in this file is the first one**, and it is the one that
would have been worth having before any of this shipped: a lap somebody really
drove has to be accepted. A false rejection is far worse than a missed cheat -
it takes a record off the person who set it, and they have no way to argue.

The rest of the file is the other direction: a car with 2% more engine in it, a
replay downloaded from `/api/ghost` and stapled to an honest lap of somebody's
own, evidence that stops before the flag, evidence from a different track.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import runcheck
import tracks as tracks_mod
import tuning as T
import verify

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

DRIVER_JS = os.path.join(os.path.dirname(__file__), "driver.js")


@pytest.fixture(scope="module")
def rt():
    """A runtime that can drive, with the racing lines the tests need in it."""
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    # The decoder the recorder is checked against, from the packer itself: a
    # driver that steps the car with anything other than the byte it wrote down
    # would be recording a lap it did not drive.
    r.eval("var FIELDS = %s;" %
           json.dumps([runcheck.input_fields(b) for b in range(256)]))
    with open(DRIVER_JS) as f:
        r.eval(f.read())
    # The laps below are driven on a handful of tracks and each `drive` builds
    # one. The verifier's own runtime is untouched - see `memoize_build_track`.
    from conftest import memoize_build_track
    return memoize_build_track(r)


@pytest.fixture(scope="module")
def verifier():
    return verify.Verifier()


@pytest.fixture(scope="module")
def honest(rt):
    """One clean lap of Sunrise, shared by everything that only needs a lap.

    Module scoped because driving one is a second and a bit of real simulation
    and most of the tests below are about what is done *with* a lap rather than
    about the driving.
    """
    return drive(rt, "sunrise", fps=60)


def drive(rt, slug, **opts):
    """One lap, as the browser would have submitted it."""
    rt.load_racing_line(slug)
    r = rt.call("driveLap(%s, %s)" % (json.dumps(slug), json.dumps(opts)))
    assert r["finished"], (
        "the test driver did not get round %s (%d/%d checkpoints, %.0f%% of the "
        "way). Something has changed about the track or the car, and every "
        "assertion in this file is about a lap that happened."
        % (slug, r["cps"], r["needCps"], 100 * r["progress"]))
    # Through the same packing the server does, so what is checked is what would
    # have been stored rather than the floats that went into it.
    r["frames"] = runcheck.unpack_ghost(runcheck.pack_ghost(r["ghost"]))
    r["blob"] = runcheck.pack_verify(
        runcheck.unpack_inputs(r["verify"]["i"]), r["verify"]["a"])
    return r


def check(verifier, slug, lap, frames=None, time_ms=None, blob=None, splits=None):
    return verify.check(tracks_mod.get(slug), time_ms or lap["time"],
                        splits or lap["splits"], frames or lap["frames"],
                        blob or lap["blob"], verifier=verifier)


def retuned(rt, what, mult):
    """A browser with a different car in it, for the length of a `with` block."""
    class _Ctx:
        def __enter__(self):
            rt.eval("T.%s = %r;" % (what, getattr(T, what) * mult))

        def __exit__(self, *a):
            rt.eval("T.%s = %r;" % (what, getattr(T, what)))
    return _Ctx()


@pytest.mark.slow
def test_every_track_can_be_built_without_a_browser(rt):
    """`buildTrack` has to survive in QuickJS, for every track in the pool.

    **Marked `slow` on purpose**, which `conftest.py` asks to be a decision
    somebody makes rather than a reflex. This is the one test in drive whose
    cost is O(the pool): it builds *every* track, and at sixteen it takes about
    11.5s against the 10s per-test budget. There is no sleep in it and no loop
    that grew - the loop is the point - so the budget is measuring the size of
    the game here rather than a mistake, and it will only drift further with the
    next track. The guard still covers the other 1,100 tests, which is what it
    was for.

    The verifier re-drives a submitted lap through the game's own `static/js`
    (`jsrt.bundle`), and the first thing it does is `buildTrack` - so anything
    in there that reaches for a browser API takes the anti-cheat down with it.
    There is no `document` in QuickJS.

    The failure this exists for is silent in the worst way. Spa's sponsor
    hoardings are canvas textures, and `signTexture` called
    `document.createElement`; the track rendered perfectly in a browser and
    threw the moment the verifier touched it. Nothing goes red - a lap that
    would place just waits in `drive_run_checks` forever and never reaches the
    board, on that track only.

    The deep driving tests below are parametrized over two tracks because a lap
    is a second of real simulation each. This one is the cheap sweep that covers
    the other twelve, and it is the one that would have caught it.
    """
    built = rt.call("TRACKS.map(t => { const b = buildTrack(t, T);"
                    "  return [t.slug, b.gates.length, b.line.length]; })")
    assert len(built) == len(tracks_mod.TRACKS)
    for slug, gates, stations in built:
        assert gates >= 3, "%s built no gates" % slug
        assert stations > 40, "%s built no ribbon" % slug


# ---------------------------------------------------------------------------
# A lap that was really driven
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug", ["sunrise", "bigred"])
def test_a_lap_the_physics_drove_is_accepted(rt, verifier, honest, slug):
    """The one that matters. Both halves of the submission, end to end.

    Big Red is in here as well as the easy one because it is the only track with
    **boost pads**, and `padBoost` is the one piece of carried state the verifier
    keeps for itself rather than being told (a number a client can set is a
    number a client can set to `PAD_BOOST` for the whole lap). If the verifier
    ever loses track of a pad, this is where it shows: the windows after one
    would all be short of engine.
    """
    lap = honest if slug == "sunrise" else drive(rt, slug, fps=60)
    ok, why = runcheck.validate(tracks_mod.get(slug), lap["time"], lap["splits"],
                                lap["frames"])
    assert ok, why
    res = check(verifier, slug, lap)
    assert res["ok"], "%s: %s %s" % (slug, res["reason"], res["stats"])
    # And not marginally. The honest floor is the quantisation of an anchor, and
    # it is the same on every track - if this ever creeps up, the thresholds in
    # verify.py were calibrated against something that has moved.
    assert res["stats"]["median"] < verify.MEDIAN_TOL / 3
    # Big Red spends a fraction of its budget on two genuinely discontinuous
    # moments; Sunrise spends none of it. Either way an honest lap is nowhere
    # near the line, which is the property worth pinning.
    assert res["stats"]["slip"] < res["stats"]["budget"] / 5


@pytest.mark.parametrize("fps,hitch", [(144, 0), (30, 0), (12, 0), (60, 40)])
def test_the_frame_rate_is_not_evidence_of_anything(rt, verifier, fps, hitch):
    """The same lap on a fast machine, a slow one and one that stutters.

    This is here because the recording is made on two clocks that do not tick
    together. Steps are fixed at 1/120 and anchored every eighth; the lap clock
    is real time. A frame longer than `MAX_STEPS` steps drops the rest, so after
    one stutter the step count is permanently behind the clock - which is why an
    anchor carries its own timestamp instead of being matched to the replay by
    index. **12fps drops steps on every single frame** and is the case that
    proves it: without the timestamps the anchors would drift a second and a
    half clear of the replay by the flag.
    """
    lap = drive(rt, "sunrise", fps=fps, hitchEvery=hitch)
    res = check(verifier, "sunrise", lap)
    assert res["ok"], "%dfps: %s %s" % (fps, res["reason"], res["stats"])
    assert res["stats"]["median"] < verify.MEDIAN_TOL / 3


def test_a_fall_and_a_respawn_is_not_a_teleport(rt, verifier):
    """The one moment a car is *put* somewhere rather than driven there.

    `Run` puts a fallen car back at the last checkpoint it credited, so the
    verifier has to know which one that was - and the assertion is written
    against its own absence, because getting it wrong does not fail quietly.
    Told the wrong gate, two perfectly honest windows read as an 800-unit
    teleport, which is what this check is for and would have thrown away
    somebody's lap.

    (A replay with a respawn in it is refused by `runcheck.validate` before it
    ever reaches here - the jump back to the checkpoint is a teleport by the
    speed ceiling. This is defence for the day that changes; the cost of being
    ready is one array.)
    """
    lap = drive(rt, "heights", fps=60, crash=[13000, 13900, 1])
    assert lap["respawns"] >= 1, "the crash did not put the car off the track"

    track = tracks_mod.get("heights")
    ev = runcheck.unpack_verify(lap["blob"])
    anchors, inputs = ev["anchors"], ev["inputs"]
    need = (len(anchors) - 1) * runcheck.STEPS_PER_FRAME
    gates, resp = verify._respawn_points(track, lap["splits"], anchors)

    right = verifier.walk("heights", anchors, inputs[:need], resp, gates)
    assert max(right["err"]) < verify.HARD_TOL, "a respawn read as a teleport"

    wrong = verifier.walk("heights", anchors, inputs[:need], [0] * len(resp), gates)
    assert max(wrong["err"]) > 100, (
        "putting the car back in the wrong place made no difference, so this "
        "test is not measuring the thing it is named after")


# ---------------------------------------------------------------------------
# A lap that was not
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mult", [1.02, 1.10, 1.40])
def test_a_car_with_more_engine_in_it_is_refused(rt, verifier, mult):
    """The attack this exists for, at three sizes.

    1.4 is about the lap that started all this: a 12.288s Twin Loop set by a
    browser running retuned physics, which passed every check `runcheck` had.
    **1.02 is the interesting one** - two percent more engine is worth a couple
    of tenths a lap and is nowhere near anything `runcheck` could see, and it is
    still four times the honest floor here.
    """
    with retuned(rt, "ACCEL", mult):
        lap = drive(rt, "sunrise", fps=60)
    # It gets past everything that was there before, which is the point.
    ok, _ = runcheck.validate(tracks_mod.get("sunrise"), lap["time"],
                              lap["splits"], lap["frames"])
    assert ok, "the cheated lap should still be a well-formed replay"
    res = check(verifier, "sunrise", lap)
    assert not res["ok"], "ACCEL x%.2f was accepted: %s" % (mult, res["stats"])
    assert "not the one the game simulates" in res["reason"]


def test_a_car_with_more_grip_in_it_is_refused(rt, verifier):
    """Not only the engine: the same measurement sees any retuning at all."""
    with retuned(rt, "GRIP", 1.5):
        lap = drive(rt, "sunrise", fps=60)
    assert not check(verifier, "sunrise", lap)["ok"]


def test_somebody_elses_replay_cannot_be_stapled_to_your_own_lap(rt, verifier, honest):
    """`/api/ghost` is public and hands out the record's own frames and splits.

    Without the binding check the two halves of a submission come apart: an
    honest lap of your own supplies an input stream that re-drives perfectly,
    the stolen replay supplies the time, and neither half is wrong on its own.
    The lap and the record here are 300ms apart and the anchors still end up
    hundreds of units from the replay, because a faster lap is somewhere else on
    the road from the first corner onwards.
    """
    with retuned(rt, "ACCEL", 1.4):
        stolen = drive(rt, "sunrise", fps=60)
    assert stolen["time"] < honest["time"]

    res = check(verifier, "sunrise", honest,
                frames=stolen["frames"], time_ms=stolen["time"],
                splits=stolen["splits"])
    assert not res["ok"]
    assert "not the lap the replay shows" in res["reason"]


def test_the_evidence_has_to_reach_the_flag(rt, verifier, honest):
    """Otherwise the last part of a lap is unverified and free.

    Cutting the tail off the evidence is the cheapest possible version of that,
    and it has to be refused for a reason of its own rather than by whatever the
    re-simulation happens to make of a short stream.
    """
    lap = honest
    ev = runcheck.unpack_verify(lap["blob"])
    short = runcheck.pack_verify(ev["inputs"][:-8 * 60], ev["anchors"][:-60])
    res = check(verifier, "sunrise", lap, blob=short)
    assert not res["ok"]
    assert "before the flag" in res["reason"]


def test_evidence_from_a_different_lap_is_refused(rt, verifier, honest):
    """The mirror of the stolen replay: honest replay, somebody else's inputs."""
    other = drive(rt, "chicane", fps=60)
    res = check(verifier, "sunrise", honest, blob=other["blob"])
    assert not res["ok"]


def test_a_lap_with_no_evidence_at_all_is_refused(rt, verifier, honest):
    """A missing input stream and an unreadable one are the same answer.

    They have to be: the caller's question is "can this be checked", and two
    ways of saying no would be two code paths in `/api/run` that could disagree.
    """
    for blob in (None, "", "not a blob", runcheck.pack_verify([], [])):
        res = check(verifier, "sunrise", honest, blob=blob or "x")
        assert not res["ok"]


def test_a_parked_car_cannot_stand_in_for_a_lap(rt, verifier, honest):
    """The degenerate evidence: anchors that never move.

    A stationary car re-drives perfectly - eight steps of nothing land exactly
    where they started - so the physics check alone would wave it through. It is
    the binding to the replay that answers it, which is worth a test of its own
    because the two rules look like belt and braces and are not.
    """
    lap = honest
    ev = runcheck.unpack_verify(lap["blob"])
    parked = [list(ev["anchors"][0]) for _ in ev["anchors"]]
    for i, a in enumerate(parked):
        a[0] = ev["anchors"][i][0]           # keep the clock honest, move nothing
    res = check(verifier, "sunrise", lap,
                blob=runcheck.pack_verify([0] * len(ev["inputs"]), parked))
    assert not res["ok"]
    assert "not the lap the replay shows" in res["reason"]


# ---------------------------------------------------------------------------
# The two ends of the input byte
# ---------------------------------------------------------------------------

def test_the_input_byte_means_the_same_thing_in_both_languages(rt):
    """`course.js` writes the stream and `runcheck.py` reads it.

    A drift here does not fail, it *verifies the wrong lap*: the handbrake and
    the brake are one bit apart, and a car re-driven with the wrong one of them
    is a car that misses every corner. So the two are compared on every value a
    byte can take, in the direction that matters - encode there, decode here.
    """
    for throttle in (0, 1):
        for brake in (0, 1):
            for steer in (-1, 0, 1):
                for hand in (False, True):
                    inp = {"throttle": throttle, "brake": brake,
                           "steer": steer, "handbrake": hand}
                    js = rt.call("inputByte(%s)" % json.dumps(inp))
                    assert js == runcheck.input_byte(throttle, brake, steer, hand)
                    back = runcheck.input_fields(js)
                    assert back == {"throttle": throttle, "brake": brake,
                                    "steer": steer, "handbrake": hand}


def test_the_recorder_rounds_to_the_grid_the_packer_uses():
    """`course.js` quantises an anchor before sending it; `runcheck.py` quantises
    what it is sent. The same grid, or the finer of the two is thrown away.

    A drift here is silent in the direction that matters: a *coarser* constant in
    the browser costs precision the verdict is measured in - the honest floor is
    the quantisation and nothing else - and no test that only round-trips the
    Python would notice, because the numbers would arrive already rounded.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "course.js")).read()
    for name, want in (("A_POS_Q", runcheck.A_POS_Q), ("A_ROT_Q", runcheck.A_ROT_Q),
                       ("A_VEL_Q", runcheck.A_VEL_Q),
                       ("A_STEER_Q", runcheck.A_STEER_Q),
                       ("STEPS_PER_FRAME", runcheck.STEPS_PER_FRAME),
                       ("MAX_INPUT_STEPS", runcheck.MAX_INPUT_STEPS)):
        m = re.search(r"\b%s\s*=\s*([0-9*\s]+?)[,;]" % name, src)
        assert m, "%s is not in course.js any more" % name
        assert eval(m.group(1)) == want, "%s: course.js says %s, runcheck.py says %r" % (
            name, m.group(1).strip(), want)


def test_a_frame_is_exactly_eight_steps():
    """The integer alignment the whole thing is built on.

    An anchor every `STEPS_PER_FRAME` steps is only a fifteenth of a second if
    `FIXED_DT` divides into it, and `verify.py` steps exactly that many times per
    window. Retune either and the windows stop lining up with the clock.
    """
    assert runcheck.STEPS_PER_FRAME == round((1.0 / runcheck.GHOST_HZ) / T.FIXED_DT)
    assert abs(runcheck.STEPS_PER_FRAME * T.FIXED_DT - 1.0 / runcheck.GHOST_HZ) < 1e-12


def test_the_recorder_writes_an_anchor_every_eighth_step(rt, honest):
    """And the anchors and the input stream have to agree about how many.

    Checked on a real lap rather than by reading the source, because "one anchor
    per eight steps" is the sentence the whole re-simulation is seeded from: the
    verifier trusts that inputs 8i..8i+7 are the ones that carry anchor i to
    anchor i+1, and nothing else in the format says so.
    """
    lap = honest
    ev = runcheck.unpack_verify(lap["blob"])
    n, steps = len(ev["anchors"]), len(ev["inputs"])
    assert n == (steps + runcheck.STEPS_PER_FRAME - 1) // runcheck.STEPS_PER_FRAME
    # And the clock on them advances at the rate a window does, give or take the
    # frame it was stamped on.
    for i in range(1, n):
        gap = ev["anchors"][i][0] - ev["anchors"][i - 1][0]
        assert 0 <= gap < 200, "anchor %d is %.0fms after the one before" % (i, gap)
