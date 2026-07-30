"""Structural tests on the track pool.

Every failure mode in here is one that actually happened while the pool was being
authored, and each one made a track quietly unfinishable rather than obviously
broken - which is exactly the kind of thing a test should be holding down.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import laptime
import tracks as tracks_mod
import tuning as T

ALL = tracks_mod.TRACKS
IDS = [t["slug"] for t in ALL]


def _rot(r, x, y, z):
    return [(x, y, z), (-z, y, x), (-x, y, -z), (z, y, -x)][r & 3]


def gate_frame(b):
    """World position and axes of a gate, mirroring trackmesh.addGate."""
    dy_h = b.get("dy", 0) * T.LEVEL
    off = _rot(b["r"], 0, dy_h / 2, 0)
    p = [b["p"][0] * T.CELL + off[0], b["p"][1] * T.LEVEL + off[1],
         b["p"][2] * T.CELL + off[2]]
    return p, _rot(b["r"], 1, 0, 0), _rot(b["r"], 0, 0, 1)


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_track_is_well_formed(track):
    assert track["spawn"], "no start block"
    assert track["checkpoints"] >= 1
    assert any(b.get("gate") == "finish" for b in track["blocks"])
    kinds = {b.get("gi") for b in track["blocks"] if b.get("gate") == "cp"}
    # checkpoint indices are 1..n with no gaps, which is what the in-order
    # crossing check in course.js assumes
    assert kinds == set(range(1, track["checkpoints"] + 1))


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_track_does_not_cross_itself_at_the_same_height(track):
    """Two road surfaces in one cell a metre apart is a car trap, not a bridge."""
    bad = tracks_mod.overlaps(track)
    assert not bad, f"{track['slug']} overlaps itself: {bad[:4]}"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_every_gate_sits_on_the_racing_line(track):
    """A gate the driving line does not pass through can never be crossed.

    The line is the relaxed racing line, not the centreline, because that is what
    a driver actually follows - a gate placed just before a corner gets cut and
    missed, which is how four tracks were briefly unfinishable.
    """
    pts, _, _ = laptime.speed_profile(track)
    for b in track["blocks"]:
        if not b.get("gate"):
            continue
        p, f, r = gate_frame(b)
        near = min(pts, key=lambda q: sum((q[i] - p[i]) ** 2 for i in range(3)))
        lx = (near[0] - p[0]) * r[0] + (near[2] - p[2]) * r[2]
        dy = near[1] - p[1]
        label = f"{track['slug']} {b.get('gate')}{b.get('gi', '')}"
        assert abs(lx) <= T.CELL / 2 + 2.5, f"{label}: line passes {lx:.1f} wide of it"
        assert -2.5 < dy < 5.0, f"{label}: line passes {dy:.1f} above/below it"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_gates_have_room_either_side(track):
    """Two cells of straight before and after every gate.

    Corners are a single cell, so the line through one cuts hard across the cells
    next to it. A gate needs a settled run at it.
    """
    blocks = track["blocks"]
    for i, b in enumerate(blocks):
        if not b.get("gate"):
            continue
        before = blocks[max(0, i - 2):i]
        after = blocks[i + 1:i + 3]
        label = f"{track['slug']} {b.get('gate')}{b.get('gi', '')}"
        assert all(x["t"] in ("road", "kick") for x in after), \
            f"{label}: a corner follows too closely"
        if b.get("gate") != "start":
            assert all(x["t"] in ("road", "kick") for x in before), \
                f"{label}: a corner leads into it too closely"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_loops_are_stretched_enough_not_to_trap_a_car(track):
    """A loop whose advance is much under pi*rad folds back onto itself closely
    enough that a car coming down the back finds the ascending surface inside its
    ground probe and gets carried round forever."""
    for b in track["blocks"]:
        if b["t"] != "loop":
            continue
        advance = b["length"] * T.CELL
        assert advance >= math.pi * b["rad"] - 1e-6, \
            f"{track['slug']}: loop advance {advance:.1f} < pi*rad {math.pi * b['rad']:.1f}"


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_every_jump_is_clearable(track):
    """Ballistics on the speed the lap sim says you arrive at the lip with."""
    pts, speeds, _ = laptime.speed_profile(track)
    line = track["line"]
    for i, e in enumerate(line):
        if not e.get("air") or (i and line[i - 1].get("air")):
            continue                      # only the first sample of each gap
        gap = 0
        j = i
        while j < len(line) and line[j].get("air"):
            gap += 1
            j += 1
        v = speeds[max(0, i - 1)]
        # the kicker before the gap sets the launch angle
        kick = next((b for b in track["blocks"] if b["t"] == "kick"), None)
        rise = (kick.get("dy", 1.0) if kick else 1.0) * T.LEVEL
        theta = math.atan2(rise, T.CELL)
        reach = v * v * math.sin(2 * theta) / T.GRAVITY
        needed = gap * T.CELL
        assert reach >= needed * 0.85, (
            f"{track['slug']}: a {needed:.0f}-unit gap entered at {v:.0f} u/s "
            f"only carries {reach:.0f} units")


@pytest.mark.parametrize("track", ALL, ids=IDS)
def test_medal_times_are_ordered_and_reachable(track):
    m = track["medals"]
    assert m["author"] < m["gold"] < m["silver"] < m["bronze"]
    # the anti-cheat floor must sit below the hardest medal, or an author lap
    # would be rejected as impossible
    assert track["ideal"] * T.MIN_PLAUSIBLE < m["author"]
    assert 8 < track["ideal"] < 120, "ideal lap outside a sane range"


def test_pool_has_a_difficulty_spread():
    diffs = sorted(t["difficulty"] for t in ALL)
    assert diffs[0] <= 2 and diffs[-1] >= 4, "no easy or no hard tracks"
    assert len(ALL) >= 8


def test_summaries_do_not_ship_block_lists():
    """The track-select page gets metadata only; blocks are a per-track fetch."""
    for s in tracks_mod.summaries():
        assert "blocks" not in s and "line" not in s
        assert s["medals"] and s["ideal"] > 0
