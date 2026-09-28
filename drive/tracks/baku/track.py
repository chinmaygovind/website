"""Baku

The Baku City Circuit: two kilometres flat out along the Caspian, four
city-block right angles, and a castle wall you squeeze past two cars wide.
"""

from tracks.builder import FREE

slug = "baku"
name = "Baku"
difficulty = 5
# **Monaco's architecture, for a different reason.** Baku does not cross itself,
# so `pal.terrain` would fit - but a ground track may not carry a ribbon `rail`
# (`test_barriers_are_opt_in`), and a street circuit is walls on both kerbs for
# the whole lap. So the world is built in `scenery.js` on Mount Joy's lower
# envelope and the engine is told there is no ground. The walls are the rails;
# `scenery.js` wraps them in each section's colour and stands the catch fence
# on top.
ground = None
rails = True
order = 260
width = 13.0
closed = True
# Government House, the Old City wall and the Maiden Tower, the Flame Towers,
# the boulevard and the sea - and the walls, which are the only part of it the
# stopwatch can see.
scenery = True


def build(b):
    """Baku, off its own surveyed centreline.

    **Nothing below was drawn by eye**; it is Monaco's method. OpenStreetMap
    carries the circuit as relation 11266687 (``type=circuit``). Its 49 street
    ways were chained from the ``start`` node with the pit lane dropped, and they
    closed on the first try: **5968 m against the official 6003 m**, total
    turning +360.2 degrees (anticlockwise, which is the way Baku runs).

    The line was resampled at 1 m, Gaussian-smoothed at sigma 4 m and segmented
    on curvature: a straight where the radius is over 700 m, a corner where it
    is not, and a corner split wherever its sign flips. Arcs under 6 degrees were
    folded into the straight they sit in, and the turning the straights carry
    (5.3 degrees in all) was spread back over the corners in proportion to their
    angle, so the angles below sum to exactly 360.

    **Sigma is the knob that decides how tight the corners come out**, and 4 was
    chosen over 9 on purpose. OSM draws a city junction as two or three nodes,
    so heavier smoothing rounds a 90-degree street corner into a 55 m sweep; at
    4 the four right angles of the first sector land at 31-40 m, which is what
    they drive like on the onboard (second and third gear).

    Lengths are **0.586 units per metre**, which puts the lap at about 3500
    units, Suzuka's scale. At that scale the Turn 8 castle corner measures radius
    12.6, just over the engine's floor of 12, and nothing had to be opened.
    Heights are the mean of SRTM and ASTER sampled every 20 m, smoothed over
    +/-140 m, at 0.8 units per metre: flat along the sea, a 25-unit climb from
    the castle to Turn 13, and down through Turns 14-16.

    **Width is authored from the footage, not the survey.** The boulevard and
    the start straight are 15, the city 12-13, and Turns 8 to 12 are **7.5** -
    Baku's castle section is 7.6 m wide against 13-15 m elsewhere, and "55% of
    the rest" is the brief.

    **Two carriageways of one avenue.** The lap runs out to Turn 7 along one
    side of Neftchilar Avenue and back along the other, 10-12 m apart in real
    life - so at 0.586 the fitted run to Turn 7 laid its road straight over the
    start straight's and `self_proximity` failed 437 station pairs. The lengths
    were therefore solved, not just scaled: a Newton least-squares over *every*
    straight at once, minimum-norm in fractional change, with four residuals -
    the lap's end in x and z, and the Turn 7 approach held 14.5 units centre to
    centre from the boulevard both along its run and at its end. The worst leg
    moves 19%; spread that way nothing reads as moved. The fit and the solve are
    `~/Scripts/Drive/baku_fit.py`, `baku_gen.py`, `baku_emit.py`, `baku_code.py`,
    and the block between the BEGIN/END markers below is their output.

    What is left for `tracks/solver.py` is a rounding error, shut with `FREE`
    on the straight after Turn 2 and on the descent after Turn 15, 117 degrees
    apart. The start straight and the Turn 2 straight are nearly anti-parallel
    and would be singular, Monaco's lesson.

    Six gates, each hosted in the middle of a straight that pays for its 34
    units. Walls on both kerbs the whole lap is what closes every shortcut.
    """
    CP = 34.0
    RUN, PRE = 30.0, 14.0

    # --- the start straight, Neftchilar Avenue ---------------------------
    b.width(15.0)
    b.start(run=RUN)
    # BEGIN generated
    b.straight(108.4 - RUN, rise=-0.9)

    # --- the right angles: Turns 1 to 4 ----------------------------------
    b.width(13.0)
    b.arc(-89.6, 18.7, rise=-0.1)   # Turn 1
    b.straight(78.2, rise=1.4)
    b.cp()
    b.straight(78.2, rise=1.4)
    b.arc(-90.5, 18.2, rise=0.6)   # Turn 2
    b.straight(FREE(219.4), rise=0.8)
    b.cp()
    b.straight(219.4, rise=0.8)
    b.arc(-86.6, 19.4, rise=-0.1)   # Turn 3
    b.straight(88.7, rise=0.9)
    b.arc(86.5, 23.7, rise=0.6)   # Turn 4
    b.straight(73.2, rise=1.1)
    b.arc(-8.1, 103.4, rise=0.2)
    b.straight(62.7, rise=0.5)

    # --- Turns 5 and 6, and the run to Turn 7 ----------------------------
    b.arc(-74.9, 29.6)   # Turn 5
    b.straight(8.1)
    b.width(12.0)
    b.arc(68.1, 21.7, rise=-0.1)   # Turn 6
    b.straight(98.2, rise=-1.1)
    b.cp()
    b.straight(98.2, rise=-1.1)
    b.width(11.0)
    b.arc(109.7, 15.6)   # Turn 7
    b.straight(107.7, rise=1.5)

    # --- the castle: Turns 8 to 12, past the Old City wall ---------------
    b.width(7.5)
    b.arc(-82.5, 12.6, rise=0.4)   # Turn 8
    b.arc(38.5, 19.2, rise=0.4)   # Turn 9
    b.straight(2.3, rise=0.1)
    b.arc(-34.1, 29.6, rise=0.6)   # Turn 10
    b.straight(2.4, rise=0.1)
    b.arc(75.0, 22.4, rise=1.2)   # Turn 11
    b.straight(16.7, rise=0.8)
    b.arc(-93.3, 17.3, rise=1.7)   # Turn 12
    b.width(10.0)
    b.straight(193.9, rise=11.4)

    # --- over the top, and the drop: Turns 13 to 16 ----------------------
    b.width(12.0)
    b.arc(-42.6, 52.8, rise=1.0)   # Turn 13
    b.straight(28.3, rise=-0.1)
    b.cp()
    b.straight(28.3, rise=-0.1)
    b.arc(-20.5, 88.4, rise=-0.9)   # Turn 14
    b.straight(121.7, rise=-6.7)
    b.arc(-63.9, 17.4, rise=-1.7)   # Turn 15
    b.straight(FREE(89.1), rise=-5.7)
    b.cp()
    b.straight(89.1, rise=-5.7)
    b.arc(-89.1, 23.0, rise=-0.6)   # Turn 16
    b.straight(103.8, rise=-0.3)

    # --- the boulevard: Turns 17 to 20, flat out along the sea -----------
    b.width(14.0)
    b.arc(18.9, 60.5)   # Turn 17
    b.straight(91.3, rise=0.3)
    b.width(13.0)
    b.arc(-31.0, 103.0, rise=0.4)   # Turn 18
    b.straight(36.2, rise=0.4)
    b.arc(40.0, 62.9, rise=0.7)   # Turn 19
    b.straight(83.9, rise=0.4)
    b.cp()
    b.straight(83.9, rise=0.4)
    b.arc(10.1, 159.6, rise=-0.4)   # Turn 20
    b.width(15.0)
    b.straight(586.1 - PRE, rise=-4.4)
    # END generated

    b.finish_at_start()
