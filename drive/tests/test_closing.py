"""The loop-closing solver: it closes, it refuses, and it says what it did.

Spa is the only closed track in the pool and it is a bad test of this, because it
was authored *already* closed - its angles were summed to 360 by hand and its
rises to zero, so the heading and height halves of the solve are handed a residual
of zero and correctly do nothing. That is the right outcome for Spa and no evidence
at all that the machinery works.

So these build deliberately broken loops - a square that does not quite meet, one
whose corners sum to 356 degrees, one that ends nine units above where it started -
and check the solver shuts them. And, just as important, that it *refuses* the ones
it cannot shut honestly rather than quietly distorting a corner: that failure has
already happened once here, and `_spa`'s docstring still records what it produced,
"Stavelot as a 179-degree hairpin".
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tracks import solver
from tracks.builder import FREE, Builder


def fresh(width=12.0):
    return lambda: Builder(0, 0, 0, yaw=0, width=width)


def seam(b):
    """(position gap, heading gap in degrees, height gap) at the join."""
    start = b.nodes[0]["p"]
    return (math.hypot(b.x - start[0], b.z - start[2]),
            abs(math.degrees(solver._wrap(b.yaw - b._yaw0))),
            abs(b.y - start[1]))


# ---------------------------------------------------------------------------
# It closes
# ---------------------------------------------------------------------------

def test_a_square_that_does_not_meet_is_closed():
    """A rounded square, and it does not close - for a reason worth knowing.

    `start(run=20)` lays 14 units of grid road plus the 20-unit run *before* the
    loop begins, so the walk ends 34 units past the station it started from even
    though the four sides are identical. That is the ordinary case, not a
    contrived one: it is what every closed track has to absorb somewhere, and Spa
    absorbs it in Kemmel.
    """
    def build(b):
        b.start(run=20)
        for _ in range(4):
            b.straight(300)
            b.arc(90, 30)
        b.finish_at_start()

    before = fresh()()
    build(before)
    assert 30 < seam(before)[0] < 40, "expected the start road to leave it ~34 open"

    after, report = solver.close(build, fresh())
    gap, yaw, dy = seam(after)
    assert gap < 1e-4, "position still %.4f out" % gap
    assert yaw < 1e-3 and dy < 1e-4
    assert report, "closed the loop and said nothing about it"


def test_corners_that_do_not_sum_to_a_full_turn_are_closed():
    """356 degrees of corner. Spa needed this done by hand, and by arithmetic.

    This is the half of the feature Spa cannot exercise: its angles were summed to
    exactly 360 by the author, so the heading residual it hands the solver is
    already zero.
    """
    def build(b):
        b.start(run=20)
        b.straight(300)
        b.arc(88, 30)            # 88 + 90 + 90 + 88 = 356, four degrees short
        b.straight(300)
        b.arc(90, 30)
        b.straight(300)
        b.arc(90, 30)
        b.straight(300)
        b.arc(88, 30)
        b.finish_at_start()

    before = fresh()()
    build(before)
    assert 3 < seam(before)[1] < 5, "this fixture is supposed to be 4 degrees out"

    after, report = solver.close(build, fresh())
    gap, yaw, dy = seam(after)
    assert yaw < 1e-3, "heading still %.4f degrees out" % yaw
    assert gap < 1e-4 and dy < 1e-4
    assert any(c["param"] == "deg" for c in report), \
        "closed the heading without reporting a corner change: %r" % report


def test_a_lap_that_ends_higher_than_it_started_is_closed():
    """The rises do not cancel, so the join is a step in the air."""
    def build(b):
        b.start(run=20)
        b.straight(300, rise=9.0)
        b.arc(90, 30)
        b.straight(300, rise=-4.0)
        b.arc(90, 30)
        b.straight(300, rise=0.0)
        b.arc(90, 30)
        b.straight(300, rise=0.0)
        b.arc(90, 30)
        b.finish_at_start()

    before = fresh()()
    build(before)
    assert seam(before)[2] > 4, "this fixture is supposed to end high"

    after, report = solver.close(build, fresh())
    gap, yaw, dy = seam(after)
    assert dy < 1e-4, "height still %.4f out" % dy
    assert gap < 1e-4 and yaw < 1e-3


def test_an_already_closed_lap_is_left_alone():
    """No residual, no change, nothing reported.

    The property that keeps Spa honest: it arrives closed, so the solver must not
    move it. A solver that always "corrected" something would rewrite a circuit
    whose shape is the point.
    """
    # Idempotence, tested by solving twice rather than by hand-authoring a closed
    # lap - which cannot be done reliably, because `_steps` quantises every leg to
    # the station spacing and the closed length is not a round number.
    #
    # This is the property Spa depends on. Its `track.py` is authored open and
    # solved on every load; if a second solve moved it again, its geometry would
    # drift a little further every time the pool was imported.
    def build(b):
        b.start(run=20)
        for _ in range(4):
            b.straight(300)
            b.arc(90, 30)
        b.finish_at_start()

    first, report1 = solver.close(build, fresh())
    assert report1, "the fixture is supposed to need closing once"

    # Replay the solved lengths positionally rather than by label. `_nth` counts
    # every straight including the two the grid lays and the start run, so
    # matching on "straight #N" here is arithmetic this test has no business doing.
    solved = [s["len"] for s in first.sections
              if s["t"] == "straight"][3:]     # skip the two grid legs and the run

    def build_again(b):
        b.start(run=20)
        for i in range(4):
            b.straight(solved[i])
            b.arc(90, 30)
        b.finish_at_start()

    after, report2 = solver.close(build_again, fresh())
    assert report2 == [], \
        "solving an already-solved lap moved it again: %r" % report2
    assert seam(after)[0] < 1e-4


# ---------------------------------------------------------------------------
# It refuses
# ---------------------------------------------------------------------------

def test_it_will_not_stretch_a_straight_beyond_its_budget():
    """A loop miles from closing is an authoring mistake, not a solve.

    Closing this by brute force would mean doubling a straight, which is a
    different track. The error has to say so rather than produce it.
    """
    def build(b):
        b.start(run=20)
        b.straight(300)
        b.arc(90, 30)
        b.straight(300)
        b.arc(90, 30)
        b.straight(180)          # 120 short: nowhere near closable
        b.arc(90, 30)
        b.straight(300)
        b.arc(90, 30)
        b.finish_at_start()

    with pytest.raises(solver.CannotClose) as e:
        solver.close(build, fresh())
    assert "%" in str(e.value), \
        "the error should say how far over the budget it went: %s" % e.value


def test_it_will_not_turn_a_named_corner_into_a_different_corner():
    """The Stavelot failure, as a test.

    A loop whose headings are 40 degrees from closing cannot be fixed by nudging
    one corner, and the solver must say that instead of opening a 90-degree bend
    into a 130-degree one.
    """
    def build(b):
        b.start(run=20)
        b.straight(260)
        b.arc(80, 40)            # 80 * 4 = 320, forty degrees short of a full turn
        b.straight(260)
        b.arc(80, 40)
        b.straight(260)
        b.arc(80, 40)
        b.straight(260)
        b.arc(80, 40)
        b.finish_at_start()

    # Heading only. Closing position at the same time fails on the *length* budget
    # first - a lap forty degrees out is nowhere near closing in any sense - and
    # this test is about the corner guard specifically.
    with pytest.raises(solver.CannotClose) as e:
        solver.close(build, fresh(), closes=("yaw",))
    assert "degrees" in str(e.value), e.value
    assert "Stavelot" in str(e.value), \
        "the message should say what this guard is for: %s" % e.value


def test_it_will_not_turn_a_hill_into_a_jump():
    """Height closure has to respect the rule that makes a hill a hill.

    `length >= sqrt(330 * rise)` is what `test_hills_are_eased_but_kickers_are_not`
    enforces. A solver free to put 40 units of climb on a 60-unit leg would close
    the lap and launch the car.
    """
    def build(b):
        b.start(run=20)
        b.straight(60, rise=0.0)
        b.arc(90, 20)
        b.straight(60, rise=40.0)     # ends 40 units up, on short legs
        b.arc(90, 20)
        b.straight(60, rise=0.0)
        b.arc(90, 20)
        b.straight(60, rise=0.0)
        b.arc(90, 20)
        b.finish_at_start()

    with pytest.raises(solver.CannotClose):
        solver.close(build, fresh())


# ---------------------------------------------------------------------------
# Nominating legs
# ---------------------------------------------------------------------------

def test_free_picks_the_leg_the_author_named():
    """`FREE()` beats the automatic choice, which is the point of it.

    The automatic choice takes the longest straights. Here the author nominates a
    short one instead, and the solver has to use that.
    """
    def build(b):
        b.start(run=20)
        b.straight(300)
        b.arc(90, 30)
        b.straight(300)
        b.arc(90, 30)
        b.straight(FREE(320))     # nominated, and not the longest
        b.arc(90, 30)
        b.straight(FREE(290))
        b.arc(90, 30)
        b.finish_at_start()

    after, report = solver.close(build, fresh(), closes=("pos",))
    assert seam(after)[0] < 1e-4
    moved = sorted(round(c["was"]) for c in report)
    assert moved == [290, 320], \
        "the solver moved something other than the nominated legs: %r" % report


def test_free_survives_being_read_off_a_variable():
    """It is a float subclass, so a name holding one is still marked.

    Spa keeps its two lengths in locals (`KEMMEL`, `STAV_A`) and passes them on.
    What does *not* survive is arithmetic - `FREE(330) - 34` is an ordinary float -
    and that is documented on `FREE` because it fails silently, by falling back to
    the automatic choice.
    """
    def build(b):
        a, c = FREE(320.0), FREE(290.0)
        b.start(run=20)
        b.straight(300)
        b.arc(90, 30)
        b.straight(300)
        b.arc(90, 30)
        b.straight(a)
        b.arc(90, 30)
        b.straight(c)
        b.arc(90, 30)
        b.finish_at_start()

    _after, report = solver.close(build, fresh(), closes=("pos",))
    assert sorted(round(c["was"]) for c in report) == [290, 320]


def test_arithmetic_loses_the_mark_which_is_why_it_is_documented():
    """Not a wish - a check that the documented trap behaves as documented.

    If `FREE()` ever stops being a plain float subclass this test fails, and the
    note on `FREE` and in Spa's `build` would need rewriting.
    """
    assert not isinstance(FREE(330.0) - 34.0, FREE)
    assert isinstance(FREE(330.0 - 34.0), FREE)
    assert FREE(296.0) == 296.0


# ---------------------------------------------------------------------------
# The real one
# ---------------------------------------------------------------------------

def test_spa_closes_and_says_which_leg_it_moved():
    """The pool's only closed lap, end to end through the loader."""
    import tracks as tracks_mod
    t = tracks_mod.get("spa")
    line = t["line"]
    a, b2 = line[0], line[-1]
    gap = math.hypot(a["p"][0] - b2["p"][0], a["p"][2] - b2["p"][2])
    assert gap < 3.5 * 1.5, "Spa's seam is %.4f units open" % gap
    assert abs(a["p"][1] - b2["p"][1]) < 1.0

    # It is authored with round numbers now, so it has something to report - and
    # `closure` on the track is what `tools/validate_track.py` prints.
    assert t.get("closure"), \
        "Spa is authored open and should report being closed"
    assert all(c["param"] == "len" for c in t["closure"]), (
        "the solver changed something other than a straight on Spa, whose corners "
        "are all real places: %r" % t["closure"])
