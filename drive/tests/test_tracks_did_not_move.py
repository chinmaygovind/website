"""The pool still builds the geometry it built before.

Every other test in `test_tracks.py` asks whether a ribbon is *well formed*. None
of them can notice that a ribbon is well formed **somewhere else** - a track
shifted ten units sideways, a corner opened by two degrees, a straight three
units longer. Those pass every structural check and change every time on the
board, because `laptime` derives the medal times from the geometry and the
leaderboard is only comparable against geometry that has not moved.

So this compares against `tests/data/tracks_snapshot.json`, written by
`tools/snapshot_tracks.py`. It was taken before the pool was split into one
folder per track, and it is what proved that refactor moved nothing.

**When a geometry change is deliberate**, re-run the tool, commit the new
snapshot as its own change, and say in the message which track moved and why.
Do not reach for `TOLERANCE` to make a red test green - that is for a change
whose *size* is the point, and it needs the number and the reason written next
to it, as Spa's does.
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import snapshot_tracks
import tracks as tracks_mod

SNAP = os.path.join(os.path.dirname(__file__), "data", "tracks_snapshot.json")

# How far a track's stations are allowed to have moved, in units, and why.
#
# Each entry says the number and the reason, because "we allowed this one to
# drift" is only defensible if the next person can see what was traded for what.
TOLERANCE = {
    # Spa closes itself now. Its two long straights used to be solved offline by
    # `tools/close_spa.py` and pasted in as `334.35` and `355.50`; `tracks/solver.py`
    # derives them on every load and gets `334.3534`, because the pasted numbers
    # were the true answer rounded to two decimals.
    #
    # Measured, not allowed for: **0.0141 units** of station shift at the very
    # worst, an ideal lap of 71.339 -> 71.340, and **gold, silver and bronze all
    # identical to the hundredth**. That last part is why this is acceptable at
    # all - every Spa time on the board was graded against those three numbers,
    # and a hundredth of a unit of road is a fortieth of the car's width.
    #
    # `test_the_medal_times_did_not_move` has no tolerance and never will.
    "spa": 0.02,
}

with open(SNAP) as _f:
    OLD = {t["slug"]: t for t in json.load(_f)}

NEW = {t["slug"]: {k: snapshot_tracks._round(t[k])
                   for k in snapshot_tracks.KEYS if k in t}
       for t in tracks_mod.TRACKS}

IDS = sorted(set(OLD) | set(NEW))


def _drift(a, b):
    """How far apart two snapshot values are, or None if they changed shape.

    Recursive because a station's ``pf`` - the baked half-pipe cross-section - is
    a list of ``[u, rise]`` pairs rather than a flat vector, and Rainbow Road
    carries one on every station. A flat comparison silently succeeded on the
    other fourteen tracks and raised a TypeError on that one, which is the wrong
    way round for a test whose whole job is noticing small changes.

    Returns a float for anything numeric, 0.0 for equal non-numerics, and None
    when the two are not comparable at all - a list that changed length, a flag
    that appeared, a float that became null.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return 0.0 if a == b else None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return None
        worst = 0.0
        for x, y in zip(a, b):
            d = _drift(x, y)
            if d is None:
                return None
            worst = max(worst, d)
        return worst
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return None
        worst = 0.0
        for k in a:
            d = _drift(a[k], b[k])
            if d is None:
                return None
            worst = max(worst, d)
        return worst
    return 0.0 if a == b else None


def test_the_pool_is_the_same_set_of_tracks():
    """A track appearing or vanishing is a decision, not a side effect.

    Worth its own test rather than being folded into the per-track ones: a
    parametrize over the union would report a *missing* track as a KeyError
    inside some other assertion, which reads as a broken test rather than as a
    track that is no longer in the pool.
    """
    assert sorted(NEW) == sorted(OLD), (
        "the pool changed: added %r, removed %r. If that is deliberate, re-run "
        "tools/snapshot_tracks.py and commit the snapshot as its own change."
        % (sorted(set(NEW) - set(OLD)), sorted(set(OLD) - set(NEW))))


def test_the_pool_order_is_unchanged():
    """`TRACKS[0]` is the fallback track in five places in app.py.

    And the home page is asserted to list the pool in order
    (`test_app.py::test_the_home_page_lists_every_track`), so the sequence is
    load bearing in a way the individual tracks are not.
    """
    was = [t["slug"] for t in json.load(open(SNAP))]
    now = [t["slug"] for t in tracks_mod.TRACKS]
    assert now == was, "the pool order changed:\n  was %r\n  now %r" % (was, now)


@pytest.mark.parametrize("slug", IDS)
def test_the_medal_times_did_not_move(slug):
    """The one that would silently re-grade laps somebody already drove.

    Checked before the geometry, and separately from it, because this is the
    consequence that reaches a player. A track may be allowed to shift by a
    hundredth of a unit (see `TOLERANCE`); its gold time may not move at all.
    """
    if slug not in OLD or slug not in NEW:
        pytest.skip("covered by test_the_pool_is_the_same_set_of_tracks")
    assert NEW[slug]["medals"] == OLD[slug]["medals"], (
        "%s: medal times moved from %s to %s. Every lap on the board for this "
        "track was graded against the old ones."
        % (slug, OLD[slug]["medals"], NEW[slug]["medals"]))
    # The ideal lap gets the track's tolerance where the medals get none. It is a
    # raw simulation result at full precision, so a hundredth of a unit of road
    # shows up in it; the medals are rounded to 1/100s and are what a player is
    # actually graded against. Spa moves 71.339 -> 71.340 and its golds do not
    # move at all, which is exactly the distinction worth drawing.
    slack = 0.05 if slug in TOLERANCE else 0.0
    assert abs(NEW[slug]["ideal"] - OLD[slug]["ideal"]) <= slack, (
        "%s: the ideal lap moved %.3f -> %.3f, so the medals are about to."
        % (slug, OLD[slug]["ideal"], NEW[slug]["ideal"]))


@pytest.mark.parametrize("slug", IDS)
def test_the_ribbon_did_not_move(slug):
    if slug not in OLD or slug not in NEW:
        pytest.skip("covered by test_the_pool_is_the_same_set_of_tracks")
    old, new = OLD[slug], NEW[slug]

    assert len(new["line"]) == len(old["line"]), (
        "%s: %d stations, was %d. A station count change is a geometry change - "
        "a leg got longer or STATION moved."
        % (slug, len(new["line"]), len(old["line"])))

    tol = TOLERANCE.get(slug, 0.0)
    worst, where = 0.0, -1
    for i, (a, b) in enumerate(zip(old["line"], new["line"])):
        d = math.dist(a["p"], b["p"])
        if d > worst:
            worst, where = d, i
    assert worst <= tol, (
        "%s: station %d moved %.6f units (tolerance %.6f). Re-run "
        "tools/snapshot_tracks.py --check to see the whole pool."
        % (slug, where, worst, tol))

    # The rest of a station: the normal, the lateral, the width and every flag.
    # A station in the right place with the wrong normal is a piece of road that
    # is banked when it should be flat, which nothing else here would catch.
    for i, (a, b) in enumerate(zip(old["line"], new["line"])):
        for k in sorted(set(a) | set(b)):
            if k == "p":
                continue
            drift = _drift(a.get(k), b.get(k))
            assert drift is not None, (
                "%s: station %d %r changed shape\n  was %r\n  now %r"
                % (slug, i, k, a.get(k), b.get(k)))
            assert drift <= tol, (
                "%s: station %d %r moved by %.6f (tolerance %.6f)"
                % (slug, i, k, drift, tol))


@pytest.mark.parametrize("slug", IDS)
def test_everything_derived_from_the_ribbon_did_not_move(slug):
    """Gates, spawn, sections, and the two things `_assemble` works out itself.

    `pole_side` and `gate_ceil` are derived rather than authored, so they are the
    cheapest possible check that the ribbon feeding them is the same ribbon - and
    `gate_ceil` in particular is the checkpoint window's roof, which is what
    stops a gate being credited from a road passing overhead.
    """
    if slug not in OLD or slug not in NEW:
        pytest.skip("covered by test_the_pool_is_the_same_set_of_tracks")
    old, new = OLD[slug], NEW[slug]
    tol = TOLERANCE.get(slug, 0.0)
    # `sections` is the authored primitives, so on a self-closing track it records
    # what the solver derived rather than what the author typed - Spa's Kemmel is
    # 300.353274 where the snapshot has the old pasted 300.35. Numeric drift is
    # held to the same tolerance as the stations; anything that is not a number
    # still has to match exactly.
    for k in ("name", "blurb", "ground", "difficulty", "exposed", "closed",
              "cell", "level", "station", "checkpoints", "spawn", "sections",
              "gates", "pole_side", "gate_ceil"):
        if k not in old and k not in new:
            continue
        drift = _drift(old.get(k), new.get(k))
        assert drift is not None, (
            "%s: %r changed shape\n  was %r\n  now %r"
            % (slug, k, old.get(k), new.get(k)))
        assert drift <= tol, (
            "%s: %r moved by %.6f (tolerance %.6f)" % (slug, k, drift, tol))
