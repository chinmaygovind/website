"""Sepang

The Malaysian Grand Prix circuit: two kilometre-long straights back to back
either side of the umbrella grandstand, a hairpin at each end of them, and
the fast esses climbing through the palm oil.
"""

from tracks.builder import FREE

slug = "sepang"
name = "Sepang"
difficulty = 4
ground = -1.2
order = 270
# The start straight is 19 wide and the corners 16 - Sepang is a 16-metre
# road with 22 to 25 on its two big straights, and the brief was "as wide as
# Sepang" at Silverstone's scale, so width is authored from the place and not
# scaled with the lap.
width = 19.0
closed = True
# The umbrella grandstand between the two straights, the pit building and its
# tower, the flag-striped run-off at the hairpins and the palm oil plantation.
scenery = True


def build(b):
    """Sepang, off its own surveyed centreline.

    **Nothing below was drawn by eye**; it is Baku's method. OpenStreetMap
    carries the circuit as relation 284496 (``type=circuit``); its twenty ways,
    chained from the ``start`` node with the pit lane dropped, closed on the
    first try at **5546 m against the official 5543 m**, total turning -360.7
    degrees (clockwise, which is the way Sepang runs).

    The line was resampled at 1 m, Gaussian-smoothed at sigma 4 m and segmented
    on curvature, as Baku was (``~/Scripts/Drive/baku_fit.py``). Arcs under 12
    degrees were folded into the straight they sit in and their turning spread
    back over the corners, so the angles below sum to exactly 360. That leaves
    sixteen corners, which are the official fifteen plus Turn 3 in its two real
    radii.

    Lengths are **0.4586 units per metre**, Silverstone's scale, and closed in
    plan by a min-norm least-squares over every straight at once (fractional,
    so the correction spreads thinly rather than landing on one leg).
    Heights are the lower of SRTM and ASTER every 20 m - the lower, because both
    are surface models and the higher one is the grandstand roof and the palm
    canopy - smoothed over +/-140 m, at 0.8 units per metre. The low point is
    Turn 4's braking zone and the high point the hill past Turn 11.
    ``~/Scripts/Drive/sepang_gen.py`` writes the block between the markers.

    What is left for ``tracks/solver.py`` is rounding, shut with ``FREE`` on
    the Turn 8-9 straight and the back straight.
    """
    CP = 34.0
    RUN, PRE = 44.0, 14.0

    b.start(run=RUN)
    # BEGIN generated
    b.straight(271.0 - RUN, rise=-2.7)
    b.width(16.0)

    # --- Turns 1 and 2, the hairpin pair ---------------------------------
    b.arc(203.3, 18.7, rise=-1.6)   # Turn 1
    b.straight(6.0, rise=-0.1)
    b.arc(-150.7, 17.8, rise=-2.5)   # Turn 2
    b.straight(1.4)

    # --- Turn 3, the long right ------------------------------------------
    b.arc(38.1, 60.7, rise=-2.4)   # Turn 3
    b.straight(10.9, rise=-0.2)
    b.arc(6.3, 82.8, rise=-0.1)
    b.straight(7.3, rise=-0.1)
    b.arc(63.6, 81.0, rise=-3.8)   # Turn 3, the long right
    b.straight(159.3 - CP, rise=6.7)
    b.cp()

    # --- Turn 4, and the climb to the esses ------------------------------
    b.arc(104.9, 13.5, rise=0.9)   # Turn 4, Langkawi
    b.straight(104.0, rise=2.6)
    b.arc(-127.5, 56.5, rise=1.1)   # Turn 5
    b.straight(1.8)
    b.arc(97.7, 50.8, rise=-0.1)   # Turn 6, Genting
    b.straight(132.4 - CP, rise=-0.4)
    b.cp()

    # --- Turns 7 and 8, the double right ---------------------------------
    b.arc(62.6, 20.6, rise=-0.1)   # Turn 7
    b.straight(29.3, rise=-0.2)
    b.arc(63.8, 20.6, rise=-0.2)   # Turn 8
    b.straight(FREE(195.2 - CP), rise=0.4)
    b.cp()

    # --- the Turn 9 hairpin, and the hill --------------------------------
    b.arc(-140.6, 12.3, rise=0.9)   # Turn 9, Berjaya Tioman
    b.straight(24.8, rise=0.9)
    b.arc(79.6, 58.8, rise=3.5)   # Turn 10
    b.straight(11.6, rise=0.2)
    b.arc(9.2, 60.1, rise=0.1)
    b.straight(4.6)
    b.arc(94.9, 22.7, rise=-0.6)   # Turn 11, Kenyir Lake
    b.straight(102.1 - CP, rise=-5.6)
    b.cp()

    # --- Turns 12 to 14, onto the back straight --------------------------
    b.arc(-67.0, 34.9, rise=-1.5)   # Turn 12
    b.straight(27.9, rise=-0.5)
    b.arc(37.7, 69.0, rise=-0.3)   # Turn 13
    b.straight(2.3)
    b.arc(10.4, 55.5)
    b.straight(1.8)
    b.arc(9.8, 59.2)
    b.straight(0.9)
    b.arc(137.3, 27.9, rise=0.6)   # Turn 14, Sunway Lagoon
    b.width(19.0)
    b.straight(FREE(361.3 - CP), rise=6.8)
    b.cp()

    # --- Turn 15, and the run to the line --------------------------------
    b.arc(-173.5, 20.1, rise=-1.2)   # Turn 15, Pangkor Laut
    b.straight(140.5 - PRE, rise=-0.2)
    # END generated

    b.finish_at_start()
