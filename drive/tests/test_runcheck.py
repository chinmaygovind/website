"""Ghost packing and submitted-time validation."""

import bisect
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import runcheck
import tracks as tracks_mod
import tuning as T

TRACK = tracks_mod.get("sunrise")


def frame_count(seconds, hz=None):
    """How many frames `Run._recordGhost` writes for a lap of `seconds`.

    It pushes while ``_ghostN / hz <= t``, so a lap ending at `t` has written
    every index from 0 to floor(t * hz) - one more than the obvious answer, and
    the relation `runcheck.time_window` inverts. The fixtures below have to agree
    with it or they are testing a client that does not exist.
    """
    hz = hz or runcheck.GHOST_HZ
    return max(2, int(seconds * hz) + 1)


def synth_run(track, seconds=None, hz=None):
    """A replay that would pass: it drives the track.

    Down the middle of the ribbon at a constant speed, from the start to the
    finish gate. It used to be a straight line along +X from the spawn, which was
    fine while nothing compared a replay to the course - and which was, exactly,
    the replay-synthesis hole `follows_the_track` exists to close. Every test that
    wants an *acceptable* run needs one that really goes round.
    """
    hz = hz or runcheck.GHOST_HZ
    seconds = seconds or track["ideal"]
    pts = [st["p"] for st in track["line"]]
    fin = next((g for g in track["gates"] if g["kind"] == "finish"), None)
    if fin is not None:                    # stop at the flag, not at the end of
        pts = pts[:fin["si"] + 1]          # the ribbon, which runs on past it
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    total = cum[-1]
    n = frame_count(seconds, hz)
    frames = []
    for i in range(n):
        s = total * i / (n - 1)
        j = min(bisect.bisect_right(cum, s) - 1, len(pts) - 2)
        u = (s - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        p = [pts[j][k] + (pts[j + 1][k] - pts[j][k]) * u for k in range(3)]
        frames.append([p[0], p[1] + T.RIDE_HEIGHT, p[2], 0, 0, 0, 1])
    return frames


def straight_line_run(track, seconds=None, hz=None):
    """The synthesis attack: right duration, right start, no track under it."""
    hz = hz or runcheck.GHOST_HZ
    seconds = seconds or track["ideal"]
    n = frame_count(seconds, hz)
    sp = track["spawn"]["p"]
    step = 20.0 / hz
    return [[sp[0] + i * step, sp[1] + 0.45, sp[2], 0, 0, 0, 1] for i in range(n)]


def splits_for(track, time_ms, frames=None):
    """The splits that go with a replay.

    Read off the replay's own gate crossings when there is one, because that is
    now a thing the server checks. Without frames it falls back to spacing them
    evenly, which is all the tests that never get as far as the geometry need.
    """
    n = track["checkpoints"]
    if frames is None:
        return [int(time_ms * (i + 1) / (n + 1)) for i in range(n)]
    cps, _ = runcheck._gates_of(track)
    ceil = track.get("gate_ceil") or 5.0
    out, at = [], 0
    for gate in cps:
        hits = [i for i in runcheck._crossings(gate, frames, ceil) if i >= at]
        at = hits[0] if hits else at
        out.append(int(round(at / runcheck.GHOST_HZ * 1000)))
    return out


def test_ghost_round_trips():
    frames = synth_run(TRACK)
    out = runcheck.unpack_ghost(runcheck.pack_ghost(frames))
    assert len(out) == len(frames)
    for a, b in zip(frames, out):
        assert abs(a[0] - b[0]) < 0.02 and abs(a[2] - b[2]) < 0.02
        assert abs(a[6] - b[6]) < 0.001


def test_a_ghost_carries_the_flags_it_was_driven_with():
    """The lamps on a replay are the driver's, not a guess at the driver's."""
    frames = synth_run(TRACK, seconds=4)
    for i, f in enumerate(frames):
        f.append(9 if i % 2 else 0)       # BRAKE|DRIFT on alternate frames
    out = runcheck.unpack_ghost(runcheck.pack_ghost(frames))
    assert [f[7] for f in out] == [f[7] for f in frames]


def test_a_ghost_from_before_flags_existed_still_unpacks():
    """Every lap already on the board is seven wide, records included. They keep
    working and simply have no lamps - which is why the stride is stored rather
    than assumed."""
    frames = synth_run(TRACK, seconds=4)
    assert all(len(f) == 7 for f in frames)
    out = runcheck.unpack_ghost(runcheck.pack_ghost(frames))
    assert len(out) == len(frames) and all(len(f) == 7 for f in out)


def test_ghost_packing_is_compact():
    """A ghost is stored per player per track, so it has to stay small."""
    frames = synth_run(TRACK, seconds=60)
    blob = runcheck.pack_ghost(frames)
    assert len(blob) < 40_000, "a one-minute ghost should compress to a few kB"


def test_unpack_rejects_rubbish():
    assert runcheck.unpack_ghost("not base64 at all!!") is None
    assert runcheck.unpack_ghost("") is None
    assert runcheck.unpack_ghost(None) is None


def test_a_plausible_run_is_accepted():
    ms = int(TRACK["ideal"] * 1000)
    frames = synth_run(TRACK)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert ok, why


@pytest.mark.parametrize("ms_factor", [0.95, 0.85, 0.75])
def test_a_lap_faster_than_the_estimate_is_still_accepted(ms_factor):
    """Being quick is not evidence of cheating.

    `ideal` is what `laptime.py` derives from a relaxed racing line, and it is
    beatable - so a lap well inside it is a good lap, not a rejected one. This
    used to be the opposite test: anything under 0.8 of ideal was thrown away,
    which meant the floor punished exactly the people who had learned the track.
    A replay that holds up is what makes a time acceptable now.

    Note the fixture drives the *centreline*, which is longer than any racing
    line, so it carries more speed than a real lap at the same fraction of ideal
    does - the quickest real lap on the board is 0.754 of ideal and medians 48.2.
    """
    ms = int(TRACK["ideal"] * 1000 * ms_factor)
    frames = synth_run(TRACK, seconds=ms / 1000)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert ok, why


def test_missing_checkpoints_are_rejected():
    ms = int(TRACK["ideal"] * 1000)
    ok, why = runcheck.validate(TRACK, ms, [], synth_run(TRACK))
    assert not ok and "checkpoint" in why


def test_out_of_order_splits_are_rejected():
    ms = int(TRACK["ideal"] * 1000)
    bad = splits_for(TRACK, ms)
    bad[0], bad[-1] = bad[-1], bad[0]
    ok, why = runcheck.validate(TRACK, ms, bad, synth_run(TRACK))
    assert not ok and "order" in why


def test_splits_after_the_finish_are_rejected():
    ms = int(TRACK["ideal"] * 1000)
    bad = splits_for(TRACK, ms)
    bad[-1] = ms + 500
    ok, why = runcheck.validate(TRACK, ms, bad, synth_run(TRACK))
    assert not ok


def test_a_run_with_no_replay_is_rejected():
    ms = int(TRACK["ideal"] * 1000)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), None)
    assert not ok and "replay" in why


def test_a_replay_that_does_not_match_the_time_is_rejected():
    """Claiming a fast time with a long replay, or vice versa."""
    ms = int(TRACK["ideal"] * 1000)
    short = synth_run(TRACK, seconds=TRACK["ideal"] * 0.4)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), short)
    assert not ok and "match" in why


def test_the_clock_is_pinned_to_the_frame_count():
    """A replay of n frames may claim the one 1/15s window that produced it.

    The recorder writes floor(t * 15) + 1 frames, so the window is a frame wide
    and `FRAME_SLACK` widens it by one either side. What matters is the far edge:
    the band this replaced was ±25%, and 25% of a lap is seconds.
    """
    frames = synth_run(TRACK)
    n = len(frames)
    lo, hi = runcheck.time_window(n)
    assert (hi - lo) / 1000.0 * runcheck.GHOST_HZ == pytest.approx(
        1 + 2 * runcheck.FRAME_SLACK)

    honest = int((n - 1) / runcheck.GHOST_HZ * 1000)
    ok, why = runcheck.validate(TRACK, honest, splits_for(TRACK, honest, frames), frames)
    assert ok, why

    for ms in (int(lo) - 1, int(hi) + 1):
        ok, _ = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
        assert not ok, "a lap %dms outside its own window was accepted" % (
            ms - honest)


@pytest.mark.parametrize("slug", [t["slug"] for t in tracks_mod.TRACKS])
def test_an_honest_lap_cannot_be_relabelled_faster(slug):
    """The hole both of the tightened windows existed to close.

    Take a replay that really drives the track - your own, or any of the ones
    `/api/ghost` hands out to anybody who asks - and change nothing about it.
    Shift every split down by the split tolerance and claim a finish one
    millisecond after the last of them. Nothing here looked at the relationship
    between the clock and the frames closely enough to notice: the duration band
    was ±25% and the split tolerance was nine frames, so the lap came back
    **3.5 to 6.9 seconds faster** on every track in the pool, and on the two
    long ones that is most of the gap between first and last on the board.

    Measured with the tolerances this test is written against, the same attack is
    worth under 0.25s - which is the quantisation of the recorder, and the point
    below which there is nothing left to take.
    """
    track = tracks_mod.get(slug)
    honest_s = track["ideal"]
    frames = synth_run(track, honest_s)
    honest_ms = int(honest_s * 1000)
    splits = splits_for(track, honest_ms, frames)
    ok, why = runcheck.validate(track, honest_ms, splits, frames)
    assert ok, "%s: the honest lap was refused: %s" % (slug, why)

    faked = [max(1, s - (runcheck.SPLIT_TOL_MS - 1)) for s in splits]
    for i in range(1, len(faked)):
        faked[i] = max(faked[i], faked[i - 1] + 1)
    lo, _ = runcheck.time_window(len(frames))
    claim = max(faked[-1] + 1, int(lo))

    ok, _ = runcheck.validate(track, claim, faked, frames)
    gain = (honest_ms - claim) / 1000.0
    assert not ok or gain < 0.25, (
        "%s: an honest %.3fs lap was accepted as %.3fs - %.3fs of it forged"
        % (slug, honest_ms / 1000.0, claim / 1000.0, gain))


def test_a_teleporting_replay_is_rejected():
    ms = int(TRACK["ideal"] * 1000)
    frames = synth_run(TRACK)
    frames[len(frames) // 2][0] += 5000     # a single impossible jump
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), frames)
    assert not ok and "teleport" in why


def test_a_replay_that_does_not_start_on_the_line_is_rejected():
    ms = int(TRACK["ideal"] * 1000)
    frames = synth_run(TRACK)
    for f in frames:
        f[0] += 400
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), frames)
    assert not ok and "start" in why


def test_medal_boundaries():
    m = TRACK["medals"]
    assert runcheck.medal_for(TRACK, int(m["gold"] * 1000)) == "gold"
    assert runcheck.medal_for(TRACK, int(m["silver"] * 1000)) == "silver"
    assert runcheck.medal_for(TRACK, int(m["bronze"] * 1000)) == "bronze"
    assert runcheck.medal_for(TRACK, int(m["bronze"] * 1000) + 2000) is None
    # gold is the top of the scale: beating it by a mile is still a gold, and
    # nothing above it exists to be awarded
    assert runcheck.medal_for(TRACK, int(m["gold"] * 1000) - 50) == "gold"
    assert runcheck.medal_for(TRACK, int(m["gold"] * 1000 * 0.85)) == "gold"
    assert runcheck.medal_for(TRACK, int(m["gold"] * 1000) + 50) == "silver"


def test_medal_rank_orders_medals():
    ranks = [runcheck.medal_rank(m) for m in ("bronze", "silver", "gold")]
    assert ranks == sorted(ranks) and runcheck.medal_rank(None) == 0
    assert runcheck.medal_rank("author") == 0, "the author medal is retired"


def test_distance_is_clamped_to_something_possible():
    import laptime
    length = laptime.line_length(TRACK)
    assert runcheck.clamp_distance(TRACK, 1e9) <= length * 4 + 1
    assert runcheck.clamp_distance(TRACK, -5) == 0
    assert runcheck.clamp_distance(TRACK, "nonsense") == 0
    assert runcheck.clamp_distance(TRACK, length) == pytest.approx(length)


def test_tuning_exports_everything_the_client_needs():
    """The browser physics reads these by name; a missing one is a crash."""
    d = T.as_dict()
    for key in ("CELL", "ROAD_W", "GRAVITY", "MAX_SPEED", "ACCEL", "BRAKE", "GRIP",
                "DRIFT_GRIP", "SNAP", "SUSP", "STICK_FORCE", "STICK_TILT",
                "FIXED_DT", "CAR_RADIUS", "CAR_PUSH", "CAR_BUMP_SCRUB"):
        assert key in d, f"tuning does not export {key}"
    assert T.DRAG == pytest.approx(T.ACCEL / (T.MAX_SPEED ** 2)), \
        "drag must be the value that makes MAX_SPEED the actual top speed"


# ---------------------------------------------------------------------------
# The speed ceilings
# ---------------------------------------------------------------------------
#
# These exist because a 12.288s Twin Loop went on the board in August 2026, set
# by a browser running retuned physics. It passed every check there was: real
# checkpoints in order, a replay whose length matched its clock, a start on the
# line. What it could not do was hide the speed in the replay.

def centreline_len(track):
    pts = [st["p"] for st in track["line"]]
    fin = next((g for g in track["gates"] if g["kind"] == "finish"), None)
    if fin is not None:
        pts = pts[:fin["si"] + 1]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def lap_at_speed(track, u_per_s):
    """A replay that really drives the track, at a chosen speed.

    Built on `synth_run` rather than on a straight line, so that a test about a
    *speed* fails for a speed reason - a straight line into the void is refused
    by the geometry first, and would pass a speed test that had stopped working.
    """
    secs = centreline_len(track) / u_per_s
    return synth_run(track, seconds=secs), int(round(secs * 1000))


def test_the_speed_ceiling_is_the_physics_own_clamp():
    """Not a round number - the one figure the simulation cannot exceed.

    It was `MAX_SPEED * 2.2`, which handed away 25 u/s over a clamp of 85 and is
    the gap the cheated lap drove through.
    """
    assert runcheck.SPEED_CEIL < T.MAX_SPEED * 1.7 * 1.05, \
        "the ceiling must sit just above the clamp, not a third above it"
    assert runcheck.SPEED_CEIL > T.MAX_SPEED * 1.7, \
        "and just above it, so quantisation on a 15Hz ghost cannot fail an honest lap"


def test_a_lap_driven_faster_than_the_car_can_go_is_rejected():
    """The cheated lap's own shape: sustained speed no engine here produces.

    83 u/s is what the 12.288s Twin Loop actually medianed. Driven round the real
    course, so this is refused for being too quick and not for being nowhere.
    """
    frames, ms = lap_at_speed(TRACK, 83.0)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert not ok and "faster than the car" in why


def test_the_median_catches_what_a_single_frame_ceiling_cannot():
    """A cheat that sits just under the frame ceiling still cannot hold a lap.

    This is the check that is not dodgeable by staying under a number: gravity
    lifts a car over MAX_SPEED down a descent, which is why the top speed alone
    is blunt, but nothing holds it there from the line to the flag.
    """
    frames, ms = lap_at_speed(TRACK, runcheck.SPEED_CEIL * 0.98)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert not ok and "faster than the car" in why


def test_the_ceilings_leave_an_honest_lap_alone():
    """Every real lap on the board tops out at 62.5 and medians under 49.5."""
    frames, ms = lap_at_speed(TRACK, 42.1)          # sunrise at its ideal lap
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert ok, why
    # And a brief excursion over MAX_SPEED - a descent - is not a rejection.
    # 62.5 is the fastest single frame on the real board and it has to survive:
    # shift one frame *and everything after it*, so exactly one interval is quick
    # and the rest of the lap is unchanged.
    bump = (62.5 - 42.1) / runcheck.GHOST_HZ
    for f in frames[len(frames) // 2:]:
        f[1] += bump                                 # straight up, off a crest
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, frames), frames)
    assert ok, why


# ---------------------------------------------------------------------------
# The input stream
# ---------------------------------------------------------------------------

def test_every_input_the_car_can_be_given_survives_a_byte():
    from itertools import product
    for t, b, s, h in product((0, 1), (0, 1), (-1, 0, 1), (False, True)):
        f = runcheck.input_fields(runcheck.input_byte(t, b, s, h))
        assert (f["throttle"], f["brake"], f["steer"], f["handbrake"]) == (t, b, s, h)


def test_both_arrows_at_once_is_no_steer():
    """The same answer `readInput` gives: steer is right minus left."""
    assert runcheck.input_fields(runcheck.input_byte(0, 0, 0, False))["steer"] == 0
    assert runcheck.input_fields(8 | 16)["steer"] == 0


def _fake_anchors(n=220):
    """[t, pos, quat, vel, steer] per anchor, at roughly the rates a lap has."""
    return [[round(i * 1000 / runcheck.GHOST_HZ),
             i * 0.5, 3.25, -i * 0.01,
             0.0, 0.3826834, 0.0, 0.9238795,
             38.5, -0.02, i * 0.001, (i % 20 - 10) / 10.0] for i in range(n)]


def test_a_lap_of_inputs_round_trips_and_is_small():
    """A driver holds the throttle for seconds, so run-length does the work."""
    inputs = [0] * 300 + [1] * 900 + [1 | 16] * 400 + [2 | 4] * 120
    anchors = _fake_anchors()
    back = runcheck.unpack_verify(runcheck.pack_verify(inputs, anchors))
    assert back["inputs"] == inputs
    for a, b in zip(anchors, back["anchors"]):
        assert all(abs(x - y) < 0.001 for x, y in zip(a, b))
    assert len(runcheck.pack_verify(inputs, anchors)) < len(inputs) * 2


def test_an_anchor_keeps_the_precision_the_re_simulation_needs():
    """Millimetres, not centimetres, and the reason is not tidiness.

    Half a centimetre of seeding error is enough to put a car on the other side
    of the "am I touching the ground" threshold, which is the one difference
    inside a step that is not small - and the whole verdict is a measurement of
    differences far below that. See `verify.MEDIAN_TOL`.
    """
    a = [1234, 101.2345, -7.6543, 55.5555,
         0.1234567, -0.2345678, 0.3456789, 0.8765432,
         41.2345, -0.6789, 12.3456, -0.123456]
    back = runcheck.unpack_verify(runcheck.pack_verify([1, 1], [a]))["anchors"][0]
    def within(q, *ix):
        # Half a grid step is the worst a round trip can do; the hair on the end
        # is because the halfway point is not exactly representable.
        return all(abs(a[k] - back[k]) <= 0.5 / q + 1e-9 for k in ix)

    assert back[0] == 1234
    assert within(runcheck.A_POS_Q, 1, 2, 3)
    assert within(runcheck.A_ROT_Q, 4, 5, 6, 7)
    assert within(runcheck.A_VEL_Q, 8, 9, 10)
    assert within(runcheck.A_STEER_Q, 11)
    # And the grids themselves are fine enough to be worth having: a millimetre
    # of position, and an orientation far below anything that could be driven.
    assert runcheck.A_POS_Q >= 1000 and runcheck.A_ROT_Q >= 32768


def test_a_frame_is_exactly_eight_steps():
    """The alignment anchored verification depends on: 1/120 into 1/15."""
    assert runcheck.STEPS_PER_FRAME == int(round((1.0 / runcheck.GHOST_HZ) / T.FIXED_DT))


def test_verify_blob_rejects_rubbish():
    assert runcheck.unpack_verify(None) is None
    assert runcheck.unpack_verify("not a blob") is None
    assert runcheck.unpack_inputs([1, 2, 3]) is None      # odd length
    # `/api/run` hands the wire straight to this one, so "unreadable" has to
    # cover anything a JSON body can hold rather than only the shapes a browser
    # would have sent.
    for rubbish in ("a string!!", ["x", 1], [None, None], [1, "many"], {}, 7):
        assert runcheck.unpack_inputs(rubbish) is None


def test_an_anchor_that_is_the_wrong_shape_is_not_half_read():
    """A blob with a partial anchor on the end is unreadable, not truncatable.

    Reading what fits and dropping the rest would hand the verifier a lap that
    is a few windows shorter than the one that was submitted, which is the
    coverage check's problem to catch and should never get that far.
    """
    good = runcheck.pack_verify([1, 1], _fake_anchors(4))
    assert len(runcheck.unpack_verify(good)["anchors"]) == 4
    import base64 as b64, json as js, zlib
    obj = js.loads(zlib.decompress(b64.b64decode(good)))
    obj["a"] = obj["a"][:-3]
    bad = b64.b64encode(zlib.compress(js.dumps(obj).encode())).decode()
    assert runcheck.unpack_verify(bad) is None


# ---------------------------------------------------------------------------
# Does the replay drive the track?
# ---------------------------------------------------------------------------
#
# The second hole. `validate` checked that the splits were increasing integers
# and that frame 0 was near the spawn, and never looked at the course again - so
# a replay could be a straight line into the void with three plausible numbers
# beside it. The splits were the half that mattered: the board draws its
# checkpoint comparison from them and nothing tied them to the frames.

def test_a_replay_that_never_drives_the_track_is_rejected():
    """The synthesis attack: right duration, right start, no course under it.

    This is the exact fixture every acceptance test in this file used to use,
    which is how the hole stayed open - the thing being sent as proof of a lap
    was the thing the tests called a valid lap.
    """
    ms = int(TRACK["ideal"] * 1000)
    frames = straight_line_run(TRACK)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), frames)
    assert not ok and ("checkpoint" in why or "course" in why)


def test_splits_have_to_be_where_the_replay_actually_is():
    """A real lap with invented splits. The frames are the evidence now."""
    frames = synth_run(TRACK)
    ms = int(TRACK["ideal"] * 1000)
    good = splits_for(TRACK, ms, frames)
    assert good == sorted(good) and all(0 < s < ms for s in good)
    moved = [max(1, s - 3000) for s in good]          # claim each one 3s earlier
    ok, why = runcheck.validate(TRACK, ms, moved, frames)
    assert not ok and "not where the replay is" in why


def test_the_split_tolerance_is_the_recorders_and_not_a_round_number():
    """Both edges of `SPLIT_TOL_MS`, because only the far one used to be tested.

    A 3-second invention is refused whatever this constant says, so the test
    above went on passing while the tolerance was nine frames wide - and nine
    frames is most of a second to move a checkpoint by, which is the half of the
    relabelling attack the clock does not already cover.

    So this pins the number from both sides. An honest lap has to survive the
    worst disagreement one can actually produce: the split is stamped on the
    render frame that spots the crossing and the crossing is found on the 15Hz
    ghost grid, which measured across the twelve tracks is never worse than 59ms.
    And a split moved by more than twice that has to be refused, which is the
    assertion that fails if this is ever widened back toward where it was.
    """
    frames = synth_run(TRACK)
    ms = int(TRACK["ideal"] * 1000)
    good = splits_for(TRACK, ms, frames)

    honest = [max(1, s - 59) for s in good]
    ok, why = runcheck.validate(TRACK, ms, honest, frames)
    assert ok, "the measured worst honest disagreement was refused: %s" % why

    forged = [max(1, s - 400) for s in good]
    ok, _ = runcheck.validate(TRACK, ms, forged, frames)
    assert not ok, "a checkpoint moved by 400ms was accepted as the replay's own"


def test_a_lap_that_skips_a_checkpoint_is_rejected():
    """Cut the middle out of the lap and the gate it contained goes with it."""
    frames = synth_run(TRACK)
    n = len(frames)
    cut = frames[:n // 3] + frames[2 * n // 3:]
    ms = int(len(cut) / runcheck.GHOST_HZ * 1000)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), cut)
    assert not ok


def test_a_replay_that_stops_short_of_the_finish_is_rejected():
    """Ending anywhere else is not a lap, however long it lasted."""
    frames = synth_run(TRACK)
    short = frames[:int(len(frames) * 0.8)]
    ms = int(len(short) / runcheck.GHOST_HZ * 1000)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms, short), short)
    assert not ok and "finish" in why


def test_the_gate_rule_is_the_games_own():
    """Same numbers as `Run._withinGate` / `Course.gateNear` in course.js.

    If the game credits a gate on one rule and the server insists on another,
    the disagreement is somebody's real lap refused - so these are a contract
    with that file, not independent choices.
    """
    js = open(os.path.join(os.path.dirname(__file__), "..",
                           "static", "js", "course.js")).read()
    assert "this.gateNear = %d" % int(runcheck.GATE_NEAR) in js
    assert "gate.hw + %s" % ("%.1f" % runcheck.GATE_SIDE_PAD) in js
    assert "dy > %s" % ("%.1f" % runcheck.GATE_FLOOR) in js


@pytest.mark.parametrize("slug", [t["slug"] for t in tracks_mod.TRACKS])
def test_every_track_accepts_a_lap_of_itself(slug):
    """A lap round each track's own ribbon passes on every track in the pool.

    The corridor and the gate windows are one set of numbers for twelve very
    different courses - loops, gaps, half-pipes - so this is what says they are
    not tuned to whichever one happened to be tested.
    """
    track = tracks_mod.get(slug)
    frames, ms = lap_at_speed(track, 42.0)
    ok, why = runcheck.validate(track, ms, splits_for(track, ms, frames), frames)
    assert ok, "%s: %s" % (slug, why)
