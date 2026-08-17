"""Silverstone

The British Grand Prix circuit, compressed. Flat, fast, and wide open.
"""

from tracks.builder import FREE

slug = "silverstone"
name = "Silverstone"
blurb = "The British Grand Prix circuit, compressed. Flat, fast, and wide open."
difficulty = 4
ground = -1.2
order = 180
width = 16.0
closed = True
# The old airfield's three runways, the two hangars the Hangar Straight is named
# after, the Wing's roof - and, the only part of it the stopwatch can see, a
# barrier on the inside of the arena and of Luffield. Both of those are corners
# you could otherwise simply leave out: see `scenery.js`.
scenery = True
# No `medals` here yet, deliberately. Every other track in the pool cuts its
# three times off its own board, and nobody has driven this one - so it takes the
# derivation from `ideal`, and `NO_CUT_MEDALS_YET` in tests/conftest.py is what
# says so out loud. Set a lap, run `tools/set_medals.py silverstone`, and drop the
# entry. Same shape as the missing `hotlap.json`.


def build(b):
    """Silverstone, off its own surveyed centreline, and the pool's second closed lap.

    **Nothing below was drawn by eye.** Silverstone's centreline is public survey
    data, so the geometry here was measured rather than authored: every
    ``highway=raceway`` way inside the circuit's bounding box came out of
    OpenStreetMap, the Stowe test circuit and the pit lanes and the dead
    alignments (Bridge, Priory) were dropped, and the remaining graph was walked
    from the Hamilton Straight until it closed - which admits exactly one loop,
    through all nineteen named sections, and measures **5887 m against the
    official 5891 m**. Total turning came out at exactly -360.0 degrees, which is
    the check that the walk found a real lap rather than a plausible one.

    The elevation is measured too, off the EU-DEM 25 m model sampled along the
    same line: **145.1 m to 157.9 m**, a range of 12.8 m against the published
    11.2 m, with the low point at Club and the one real gradient the drop from
    Stowe into Vale. Two scale factors turn that into this, both matched to what
    Spa already does: **0.4586 units per metre** of length (Spa is 0.4522) and
    1.41 units per metre of height - so the relief is exaggerated 2.5x against
    Spa's and still comes to 17 units against Spa's 63, because being the flat
    one is the point rather than a shortcoming.

    **Angles are not scaled at all**, and every corner below is within three
    degrees of the angle it really is. An angle is geometric truth; Spa's
    docstring is right that a solver free to move one produces a circuit that
    closes and is not the place.

    Three things have to be true at once for a closed lap, and the first two are
    true here by construction:

     * **The corner angles sum to exactly 360.** They are the measured ones, plus
       the real long-radius drift that the circuit carries along its "straights",
       folded into the nearest corner where it was under three and a half degrees
       and kept as its own gentle arc where it was more. Change one and you must
       take the same amount out of another.
     * **The rises sum to exactly zero**, because the measured profile does.
     * **The walk has to come back to the same point in plan**, and that is the
       one nobody gets by eye. The lengths and radii below were fitted to close
       by minimum-norm least squares - never the angles - so the correction
       spreads thinly (1.2% on average) across the whole circuit instead of
       landing on one straight. What is left after rounding to a tenth is a
       0.13-unit seam, which ``tracks/solver.py`` shuts with the two legs marked
       ``FREE`` below.

    Those two are the Wellington and Hangar straights: the circuit's two DRS
    zones, its two longest legs, and **103 degrees apart in heading**, so they
    span the plane between them and the solve is better conditioned than Spa's
    own pair. They are also the two legs where a few units either way is
    invisible, which is the whole reason to nominate rather than let the solver
    reach for a named corner.

    **A radius is capped at 300.** Four legs here are really very gentle
    long-radius bends - the National Straight's kink, the run down to Maggotts,
    the Hangar Straight's lean, the curve down to Vale - and at their measured
    radii (1180 to 2430) they are straights with a rounding error. Authored at
    300 they keep their real turn and their real length and stop being a runway,
    which is exactly the trade Spa made with its own nine-degree kink out of
    Stavelot.

    Where it is *not* Spa: the run-off. Spa's armco sits 26 units out past a
    gravel trap, and here that does not fit - the arena section comes within
    **22.8 units of itself** between Village and The Loop, so there is no room
    for two 26-unit offsets between them. Which is also the authentic answer:
    Silverstone's edge is acres of painted tarmac and sawtooth kerbing, not
    gravel and armco. See ``palette.py``.
    """
    # A checkpoint lays CP units of its own road (`cp`'s pre + post), so every one
    # of them comes out of the straight that hosts it. Miss that and seven
    # checkpoints walk the ribbon 238 units past its own start.
    CP = 34.0
    # `start` puts the line 14 units in and lays RUN past it, so the grid sits on
    # the same tarmac that is the last thing you cross on the lap. Both come out
    # of the pit straight's two authored halves - the run out of the leg after the
    # line, the 14 out of the leg before it.
    # RUN is 44 rather than Spa's 70 for a reason worth keeping: `start` lays its
    # run *flat*, and the pit straight climbs 5.1 units. At 70 the whole climb had
    # to fit into the 31 units left over, which is a 42-unit vertical crease and a
    # kicker on the grid - `test_hills_are_eased_but_kickers_are_not` catches it.
    # Shortening the flat run lengthens the graded leg and the hill eases itself.
    RUN, PRE = 44.0, 14.0

    # --- the Hamilton Straight, and Abbey ------------------------------------
    # The grid, and 101 units up a 5% rise to the fastest first corner in Formula
    # One. Abbey is flat out in a real car and very nearly flat here.
    b.start(run=RUN)
    b.straight(101.5 - RUN, rise=5.1)
    b.width(15.0)
    b.arc(60.2, 48.1, rise=-0.5)             # Abbey
    b.width(16.0)
    b.straight(41.1, rise=1.6)
    b.arc(-44.9, 69.7, rise=1.5)             # Farm Curve, a lazy left
    b.straight(80.7 - CP, rise=1.5)
    b.cp()

    # --- the arena: Village, The Loop, Aintree -------------------------------
    # The infield section added in 2010, and the only slow part of the circuit.
    # Village is the first braking zone; The Loop is taken at 55 mph and is the
    # slowest corner at Silverstone. Narrower through here on purpose - it is a
    # tighter piece of road than the old airfield straights either side of it.
    b.width(14.0)
    # Carries the 0.7 the straight after it used to, because a checkpoint leaves
    # only 5 units of that straight and `sqrt(330 * 0.7)` is 15: a rise has to have
    # room or it is a crease rather than a hill. Same total climb, on the leg with
    # the length for it.
    b.arc(110.0, 18.5, rise=0.9)             # Village
    # **A checkpoint inside the arena, and it is here to stop a shortcut rather
    # than to time the lap.** Village, The Loop and Aintree sat entirely between
    # the gate on the Farm Straight and the gate on the Wellington Straight, and
    # the chord across them is 81 units of grass against 258 units of road - about
    # three and a half seconds, which is not a shortcut, it is a different track.
    # A barrier cannot close it (the cut goes round the outside of the whole
    # complex, not across one apex - see `scenery.js`); a gate can, because
    # `Run._advance` will not credit a lap that missed one.
    #
    # `pre`/`post` are 13 rather than the default 17 so the whole gate fits inside
    # the 31-unit straight the real circuit has here - the requirement is ten units
    # of straight, flat road either side, and shortening the gate is much cheaper
    # than lengthening a leg and re-closing the lap for it.
    b.straight(31.4 - 26.0)
    b.cp(pre=13.0, post=13.0)
    b.arc(-139.4, 18.4, rise=1.1)            # The Loop
    b.arc(-14.6, 151.8, rise=-1.3)           # the sweep out of it
    b.width(15.0)
    b.arc(-5.9, 142.8, rise=-0.2)
    b.arc(-52.4, 33.8, rise=0.5)             # Aintree
    b.width(16.0)

    # --- the Wellington Straight, Brooklands, Luffield -----------------------
    # Solved, not authored: one of the two legs the closure solver may move.
    b.straight(FREE(273.7 - CP), rise=-2.3)
    b.cp()
    b.width(14.0)
    b.arc(-123.5, 31.2, rise=-2.5)           # Brooklands
    b.straight(22.0, rise=-0.3)
    # Luffield: 201 degrees at radius 26, which makes it the longest single
    # corner anywhere in the pool. It is one corner and not two, because the real
    # one stopped being Luffield 1 and Luffield 2 a long time ago.
    # Same trade as Village: the -1.4 that was on the straight after it moves here,
    # because a checkpoint leaves 21 units of that straight and `sqrt(330 * 1.4)` is
    # 21.5 - a hair too short, which is still a crease.
    b.arc(200.9, 26.3, rise=-0.4)
    b.width(16.0)
    # And one on the way out of Luffield, for the same reason and a worse case:
    # Brooklands, Luffield and Woodcote make a loop whose mouth is 81 units across
    # and whose road is 279 - a 3.4x cut, the biggest on the lap, and it was legal.
    # This one fits the default gate inside the straight that is already here.
    b.straight(55.4 - CP)
    b.cp()

    # --- Woodcote, and the National Straight ---------------------------------
    # Woodcote is four arcs because that is how it is actually shaped: a long
    # opening right that was the final corner of the British Grand Prix from 1950
    # to 2009 and is barely a corner in a modern car.
    b.arc(12.5, 84.5, rise=-0.8)
    # The measured centreline splits this middle stretch in two at 7.1 and 7.3
    # degrees; it is one bend and is authored as one, which is also one fewer
    # corner in a count that is already the pool's highest.
    b.arc(14.4, 147.0)
    b.arc(24.9, 90.0, rise=2.2)
    b.arc(9.2, 300.0, rise=0.7)              # the old pit straight's own lean
    b.straight(149.4 - CP, rise=2.1)
    b.cp()

    # --- Copse ---------------------------------------------------------------
    # 180 mph in a real car, and the highest ground on the circuit is just past
    # its exit.
    b.width(15.0)
    b.arc(70.4, 47.2, rise=1.6)
    b.width(16.0)
    b.arc(16.8, 300.0, rise=0.6)             # the bend down toward Maggotts
    b.straight(109.7 - CP, rise=0.7)
    b.cp()

    # --- Maggotts, Becketts and Chapel --------------------------------------
    # The reason anybody comes here: five direction changes in about 240 units,
    # left-right-left-right-left, all of them fast. No checkpoint anywhere in it -
    # a gate in the middle of this would be cut by the racing line and is the one
    # place on the lap where the line itself is the whole decision.
    b.width(15.0)
    b.arc(-27.3, 97.0, rise=0.1)             # Maggotts
    b.arc(50.3, 37.5, rise=-1.5)             # Becketts
    b.straight(31.1, rise=-2.2)
    b.arc(-56.7, 51.4, rise=0.7)             # Becketts
    b.straight(12.9)
    b.arc(96.7, 38.0, rise=-2.9)             # Becketts, the tight one
    b.width(16.0)
    b.straight(27.3, rise=-1.3)
    b.arc(-29.0, 61.1, rise=-0.5)            # Chapel Curve, onto the back straight

    # --- the Hangar Straight, and Stowe -------------------------------------
    # The longest leg on the lap, and the other one the solver may move. Named
    # after the two RAF hangars that stood beside it, which are back - see
    # `scenery.js`.
    b.arc(8.0, 300.0, rise=-0.4)             # its own gentle lean
    b.straight(FREE(292.0 - CP - 30.0 - 60.0), rise=-2.6)
    # Stowe has a blind entry over a crest, which is most of why it is the hardest
    # corner here to commit to. `hump` is a deliberate crease and nets to zero
    # height; `straight(rise=)` smoothsteps and would keep the wheels down. It is
    # 94 units back from the corner rather than on top of it, so the car goes
    # light, settles, and *then* brakes - a crest in a braking zone is a defect
    # (see docs/track-defects.md), and a crest before one is the point of the place.
    b.hump(1.2, 30.0)
    b.cp()
    b.straight(60.0)
    b.width(15.0)
    b.arc(118.5, 43.9, rise=3.2)             # Stowe

    # --- Vale and Club, and back onto the line ------------------------------
    # The one real gradient on the circuit: 8 units down off Stowe's exit into
    # the hardest stop in Formula One, which is downhill and is why it is the
    # hardest stop in Formula One.
    b.width(16.0)
    # The measured split is -4.8 here and -3.4 on the straight; -6.5/-1.7 instead,
    # for the same total. A checkpoint takes 34 of the straight's 61 units and
    # `sqrt(330 * 3.4)` is 33.5, so what is left cannot carry its share of the drop
    # without becoming a crease. The curving leg is 88 units and has room, and it
    # is also where the road really falls away - so the fall moves onto it rather
    # than the drop being flattened.
    b.arc(-16.9, 300.0, rise=-6.5)
    b.straight(60.6 - CP, rise=-1.7)
    b.cp()
    b.width(14.0)
    b.arc(-93.6, 18.9, rise=-0.3)            # Vale
    b.arc(94.6, 25.2, rise=0.3)              # Club, first apex
    b.width(15.0)
    b.arc(77.0, 50.7, rise=-1.6)             # Club, opening onto the line
    b.width(16.0)
    b.straight(114.5 - PRE - CP, rise=5.5)
    b.cp()

    # The ribbon is now back on top of station 0, and the line is already there.
    b.finish_at_start()
