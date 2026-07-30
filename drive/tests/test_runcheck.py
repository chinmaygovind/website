"""Ghost packing and submitted-time validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import runcheck
import tracks as tracks_mod
import tuning as T

TRACK = tracks_mod.get("sunrise")


def synth_run(track, seconds=None, hz=None):
    """A replay that would pass: starts on the line, moves at a sane speed."""
    hz = hz or runcheck.GHOST_HZ
    seconds = seconds or track["ideal"]
    n = max(2, int(seconds * hz))
    sp = track["spawn"]["p"]
    step = 20.0 / hz                       # 20 u/s along +X, comfortably legal
    return [[sp[0] + i * step, sp[1] + 0.45, sp[2], 0, 0, 0, 1] for i in range(n)]


def splits_for(track, time_ms):
    n = track["checkpoints"]
    return [int(time_ms * (i + 1) / (n + 1)) for i in range(n)]


def test_ghost_round_trips():
    frames = synth_run(TRACK)
    out = runcheck.unpack_ghost(runcheck.pack_ghost(frames))
    assert len(out) == len(frames)
    for a, b in zip(frames, out):
        assert abs(a[0] - b[0]) < 0.02 and abs(a[2] - b[2]) < 0.02
        assert abs(a[6] - b[6]) < 0.001


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
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms), synth_run(TRACK))
    assert ok, why


def test_a_lap_quicker_than_gold_is_accepted():
    """The floor must not reject the best legitimate time on the board. Gold is
    the top medal but emphatically beatable, so the floor sits well under it."""
    ms = int(TRACK["medals"]["gold"] * 1000 * 0.9)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms),
                                synth_run(TRACK, seconds=ms / 1000))
    assert ok, why


@pytest.mark.parametrize("ms_factor", [0.5, 0.75])
def test_impossibly_fast_times_are_rejected(ms_factor):
    ms = int(TRACK["ideal"] * 1000 * ms_factor)
    ok, why = runcheck.validate(TRACK, ms, splits_for(TRACK, ms),
                                synth_run(TRACK, seconds=ms / 1000))
    assert not ok and "allow" in why


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
