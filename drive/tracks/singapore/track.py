"""Singapore

The Marina Bay Street Circuit under the floodlights: round the Flyer, down
Raffles Boulevard and Nicoll Highway, past the Padang, over Anderson Bridge
to the hairpin, back across the bay and home along the water.
"""

from tracks.builder import FREE

slug = "singapore"
name = "Marina Bay"
difficulty = 5
# **Baku's architecture, for Baku's reason**: a street circuit is walls on both
# kerbs for the whole lap, a ground track may not carry a ribbon `rail`
# (`test_barriers_are_opt_in`), so the world is built in `scenery.js` and the
# engine is told there is no ground. The walls are the rails.
ground = None
rails = True
order = 290
width = 14.0
closed = True
# The floodlights and the catch fence, the walls wrapped per section, the
# Flyer, Marina Bay Sands across the water, the Esplanade's two domes, Anderson
# Bridge and the Fullerton, the Padang, the CBD towers and the bay.
scenery = True


def build(b):
    """Marina Bay, off its own surveyed centreline.

    **Nothing below was drawn by eye**; it is Baku's method. OpenStreetMap
    carries the circuit as relation 421263 (``type=circuit``). Its 99 ways,
    chained from the ``start`` node with the pit lane dropped, closed on the
    first try at **4966 m against the official 4940 m** - the 2023 layout,
    with the old Turns 16-19 under the Bay grandstand replaced by the straight
    along the water (the pre-2023 lap was 5063 m). Total turning +360
    degrees: anticlockwise, which is the way Singapore runs.

    **The start/finish is the timing line, not OSM's ``start`` node**, and the
    turn numbers are the official ones. Both come from F1's own data: George
    Russell's 2025 pole lap telemetry (via FastF1) registered onto this line
    with a 7.5 m mean residual, which puts the timing line 94 m before the node
    OSM tags ``start`` (that is the grid) and every one of the nineteen corners
    from the circuit info on a fitted arc.

    The line was resampled at 1 m, Gaussian-smoothed at sigma 4 m and
    segmented on curvature (``~/Scripts/Drive/baku_fit.py``). Arcs under 6
    degrees were folded into their straights and the turning spread back over
    the corners, so the angles below sum to exactly 360.

    Lengths are **0.586 units per metre**, Baku's scale, so the two street
    circuits drive alike. At that scale five corners come out under the
    engine's floor of 12 - Turn 8 at 7.9, Turn 14 at 8.2, the Turn 13 hairpin
    at 9.9, Turns 7 and 11 at 10.7 and 11.0 - and are held at 12; the closure
    is solved with them held there, so nothing downstream moves.

    **Heights are not the survey.** SRTM and ASTER read 0 to 45 m of noise
    round a lap that is flat reclaimed land, because both are surface models
    and the CBD is rooftops and rain trees. So the lap is flat except where the
    real road rises: Anderson Bridge (+1.5 m) and Esplanade Bridge (+3.5 m),
    each a cosine hump split at its crown, at 0.8 units per metre.

    **Nicoll Highway and Esplanade Drive meet at the same junction** - Turns 8
    and 14 are about 20 m apart in the city, and at 0.586 the two roads ran
    13.5 units apart centre to centre against 14 of combined half-width.
    So the straights were solved, not just scaled: a min-norm least-squares
    over every straight at once (fractional change), closing the lap in x and
    z and holding those two stretches 17 apart. The worst leg moves 9%.
    ``~/Scripts/Drive/singapore_gen.py`` writes the block between the markers.

    **Width is authored from the onboard, not the survey**: 14 on the pit
    straight, Raffles Boulevard, Nicoll Highway and Esplanade Bridge, 12-13
    through the city, 10-11 down Connaught Drive and round the hairpin, and 9
    over Anderson Bridge, which is a narrow two-lane steel bridge with a wall
    on each side.

    Six gates, each in the middle of a straight that pays for its 34 units.
    What is left for ``tracks/solver.py`` is rounding, shut with ``FREE`` on
    Nicoll Highway and on Raffles Avenue, 135 degrees apart.
    """
    CP = 34.0
    RUN, PRE = 30.0, 14.0

    b.start(run=RUN)
    # BEGIN generated
    b.straight(238.3 - RUN)

    # --- Turns 1 to 3, under the East Coast Parkway ----------------------
    b.width(13.0)
    b.arc(-86.4, 18.3)   # Turn 1
    b.straight(0.6)
    b.arc(29.6, 51.1)
    b.straight(3.5)
    b.arc(34.8, 29.0)   # Turn 2
    b.straight(0.6)
    b.arc(-146.5, 23.4)   # Turn 3
    b.straight(20.9)

    # --- Republic Boulevard and Turn 5 -----------------------------------
    b.arc(-28.2, 82.2)   # Turn 4
    b.straight(55.6)
    b.arc(8.3, 121.9)
    b.straight(34.0)
    b.width(14.0)
    b.arc(100.6, 39.7)   # Turn 5

    # --- Raffles Boulevard -----------------------------------------------
    b.straight(35.5)
    b.arc(-7.3, 97.0)
    b.straight(37.8)
    b.arc(8.0, 92.2)
    b.straight(45.0)
    b.cp()
    b.straight(45.0)
    b.arc(10.4, 87.3)   # Turn 6
    b.straight(3.5)
    b.arc(9.0, 78.4)
    b.straight(204.2)

    # --- Nicoll Highway, Turns 7 and 8 -----------------------------------
    b.arc(-88.1, 12.0)   # Turn 7
    b.straight(FREE(37.3))
    b.cp()
    b.straight(37.3)
    b.width(12.0)
    b.arc(111.1, 12.0)   # Turn 8
    b.straight(72.4)
    b.arc(-11.5, 64.0)
    b.straight(9.4)

    # --- St Andrew's Road, past the Padang -------------------------------
    b.arc(-93.6, 26.5)   # Turn 9
    b.straight(85.7)
    b.cp()
    b.straight(85.7)

    # --- Turns 10 to 12, onto Anderson Bridge ----------------------------
    b.width(11.0)
    b.arc(-80.3, 14.6)   # Turn 10
    b.straight(55.2)
    b.arc(10.9, 52.3)
    b.straight(2.3)
    b.width(10.0)
    b.arc(48.8, 12.0)   # Turn 11
    b.arc(-24.6, 42.4)
    b.straight(3.5)
    b.arc(-30.4, 38.7)   # Turn 12
    b.width(9.0)
    b.straight(37.3, rise=1.2)
    b.straight(14.8, rise=-0.7)
    b.arc(18.0, 44.8, rise=-0.5)
    b.straight(0.6)
    b.arc(-6.1, 65.7)
    b.width(10.0)
    b.straight(19.9)

    # --- the Turn 13 hairpin and Esplanade Bridge ------------------------
    b.arc(-132.9, 12.0, rise=0.1)   # Turn 13
    b.width(14.0)
    b.straight(84.2, rise=2.7)
    b.straight(82.8, rise=-2.7)
    b.arc(9.1, 77.3, rise=-0.1)
    b.straight(50.4)
    b.cp()
    b.straight(50.4)

    # --- Raffles Avenue, past the Esplanade ------------------------------
    b.width(13.0)
    b.arc(110.9, 12.0)   # Turn 14
    b.straight(111.7)
    b.arc(-39.6, 84.8)   # Turn 15
    b.straight(FREE(93.3))
    b.cp()
    b.straight(93.3)

    # --- Turns 16 and 17, and the straight along the bay -----------------
    b.width(12.0)
    b.arc(86.8, 23.2)   # Turn 16
    b.straight(1.8)
    b.arc(-82.5, 30.1)   # Turn 17
    b.straight(49.5)
    b.cp()
    b.straight(49.5)

    # --- Turns 18 and 19, round the Flyer and onto the pit straight ------
    b.width(13.0)
    b.arc(-59.5, 24.3)   # Turn 18
    b.straight(31.3)
    b.arc(-38.6, 48.7)   # Turn 19
    b.width(14.0)
    b.straight(76.8 - PRE)
    # END generated

    b.finish_at_start()
