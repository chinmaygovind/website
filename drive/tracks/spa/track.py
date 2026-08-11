"""Spa-Francorchamps

The Ardennes circuit, compressed. Wide, fast, and a full closed lap.
"""

from tracks.builder import FREE

slug = "spa"
name = "Spa-Francorchamps"
blurb = "The Ardennes circuit, compressed. Wide, fast, and a full closed lap."
difficulty = 4
ground = -1.2
order = 130
width = 16.0
closed = True

def build(b):
    """Spa-Francorchamps: the real circuit, compressed, and the only closed lap.

    Every other track in the pool is point-to-point, because a turtle that ends
    where it started is a turtle you have to solve for rather than author. This
    one closes: the finish line *is* the start line (``finish_at_start``), and
    the ribbon is a ring whose seam is station 0, fourteen units behind the grid.

    Three things had to be true at once for that to work and they are worth
    knowing before moving anything:

     * **The corner angles sum to exactly 360.** They are fixed, so yaw closes
       by construction and the solver can never reach for a named corner and
       distort it - the first attempt left Stavelot as a 179-degree hairpin.
       Change one angle and you must take the same amount out of another.
     * **Two straights are solved, not authored.** ``KEMMEL`` and the two halves
       of the Stavelot run are whatever closes the position, found offline by
       Newton on the plan-view walk and baked here. They are the two long legs
       of the circuit's triangle, so they span the plane between them and the
       solve is well conditioned. Change any other length and they must be
       re-solved or the ribbon will not meet itself.
     * **The rises sum to exactly zero**, or the road arrives at the line at the
       wrong height. ``test_spa_closes`` pins all of it.

    The shape is Spa's and so is the elevation: the grades are real, which on a
    circuit compressed to 2800 units puts 63 units between the top of the hill
    at Les Combes and the bottom at Campus. It climbs to La Source, plunges to
    Eau Rouge, climbs all the way up Raidillon and Kemmel to the highest point,
    then falls continuously for the whole middle of the lap to Stavelot before
    the long blast home lifts it back to the line.

    It is wide - 16 units, the widest in the pool - because a Grand Prix circuit
    is, and because the run-off does the punishing here rather than the kerb.
    There are no barriers on the road edge at all: what catches a car is the
    armco set back beyond the gravel, which is drawn and collided in trackmesh
    off the ribbon rather than authored corner by corner.
    """
    # A checkpoint lays CP units of its own road (`cp`'s pre + post), so every
    # one of them is subtracted from the straight that hosts it. Miss that and
    # eight checkpoints walk the ribbon 272 units past its own start.
    CP = 34.0
    # The two legs the solver is allowed to move, marked with `FREE()` rather
    # than left to its own choice. Every corner here is a real place with a real
    # name, and a solver free to pick would sooner lengthen the pit straight by
    # 12% - which closes the lap and stops it being Spa. These two are the long
    # legs of the circuit's triangle and point in very different directions, so
    # they span the plane between them and the solve is well conditioned.
    #
    # Round numbers on purpose. They used to be 334.35 and 355.50, solved offline
    # by `tools/close_spa.py` and pasted in, with a docstring warning that
    # changing any *other* length or angle silently invalidated them. That tool
    # is gone: these are what the circuit wants to be and `tracks/solver.py`
    # finds what it has to be, every time the pool loads.
    # Note where `FREE` sits: around the *whole* expression, including the `- CP`
    # a checkpoint costs. It is a float subclass, so `FREE(330) - CP` is an
    # ordinary 296 by the time `straight` sees it and the mark is silently gone -
    # which is not an error, just a leg the solver picks for itself instead.
    # `STAV` is the authored length of the whole run out of Stavelot, split 55/45
    # by where the kink falls. Only the first half is nominated: with everything
    # else fixed, two straights and two position equations have a unique solution,
    # so which half carries the correction does not change the answer - it changes
    # where the kink ends up, and the kink is authored.
    KEMMEL, STAV = 330.0, 355.5
    STAV_A, STAV_B = STAV * 0.55, STAV * 0.45


    # --- the pit straight, and up to La Source ------------------------------
    # `start` puts the line 14 units in and lays `run` past it, so the grid sits
    # on the same tarmac that is the last thing you cross on the lap.
    b.start(run=70.0)
    b.straight(69.0, rise=11.0)
    b.cp()
    b.straight(62.0)

    # La Source. A big slow right through 170 degrees that points you down the
    # hill - the one place on the circuit you are properly slow.
    b.width(14.0)
    b.arc(170, 22.10, rise=2.0)
    b.width(16.0)

    # --- the plunge, Eau Rouge and Raidillon --------------------------------
    b.straight(143.0 - CP, rise=-26.0)
    b.cp()
    b.arc(-25, 62.40, rise=-2.0)         # Eau Rouge, at the bottom
    b.arc(50, 52.00, rise=6.0)           # Raidillon, turning up the hill
    b.straight(62.0, rise=9.0)
    # The car goes light over the top and settles again, which is the whole
    # sensation of the place. `crest` is a deliberate crease; `straight(rise=)`
    # smoothsteps and would keep the wheels down.
    b.crest(2.0, 24.0)
    b.straight(20.0)
    b.arc(-28, 84.50, rise=4.0)          # the kink at the top

    # --- Kemmel, the longest straight on the circuit ------------------------
    b.straight(FREE(KEMMEL - CP), rise=14.0)
    b.cp()

    # --- Les Combes, and the top of the hill --------------------------------
    b.width(14.0)
    b.arc(78, 33.80, rise=-1.0)
    b.arc(-80, 31.20, rise=-1.0)
    b.width(16.0)
    b.straight(71.50, rise=-5.0)

    # --- the long descent: Malmedy, Rivage, Speaker's -----------------------
    b.arc(58, 58.50, rise=-4.0)          # Malmedy
    b.straight(65.0, rise=-5.0)
    b.width(14.0)
    b.arc(152, 23.40, rise=-7.0)         # Rivage, tight and downhill
    b.width(16.0)
    b.straight(58.50, rise=-5.0)
    b.arc(-75, 44.20, rise=-4.0)         # Speaker's Corner
    b.straight(78.0 - CP, rise=-4.0)
    b.cp()

    # --- Pouhon: the fast double-left, still falling ------------------------
    b.width(17.0)
    b.arc(-105, 71.50, rise=-11.0, bank=8)
    b.width(16.0)
    b.straight(91.0 - CP, rise=-6.0)
    b.cp()

    # --- Fagnes, Campus, and the bottom of the circuit ----------------------
    b.width(14.0)
    b.arc(72, 35.10, rise=-2.0)
    b.arc(-70, 32.50, rise=-2.0)
    b.width(16.0)
    b.straight(71.50, rise=-3.0)
    b.arc(88, 41.60, rise=-2.0)          # Campus
    # 150 rather than the ~78 the shape wants, and the extra 72 units are load
    # bearing: they push the bottom of the circuit clear of the Blanchimont
    # return leg. At 78 the Pouhon exit and Blanchimont A ran 6.5 units apart in
    # plan with 4 units of height between them, which is not a crossing, it is a
    # car trap - two surfaces the ground probe cannot choose between. Clearing
    # `self_proximity` was not enough either: at 110 the two roads' centres were
    # 15 units apart, so their kerbs touched and there was physically nowhere to
    # put the gravel and the armco this track is supposed to have. At 150 the
    # closest the circuit comes to itself anywhere is La Source's own hairpin,
    # which is a corner doubling back and has nothing between its ends anyway.
    b.straight(150.0 - CP, rise=-1.0)
    b.cp()

    # --- Stavelot, and the long blast home ----------------------------------
    b.arc(130, 44.20, rise=2.0)
    b.straight(FREE(STAV_A), rise=14.0)
    b.arc(9, 286.00, rise=2.0)           # a gentle kink, so it is not a runway
    b.straight(STAV_B - CP, rise=11.0)
    b.cp()

    # Blanchimont: flat out, and barely a corner at this radius.
    b.arc(-43, 123.50, rise=4.0)
    b.straight(97.50, rise=5.0)
    b.arc(-26, 117.00, rise=2.0)
    b.straight(84.50 - CP, rise=3.0)
    b.cp()

    # --- the Bus Stop, and back onto the line -------------------------------
    b.width(13.0)
    b.arc(90, 19.50)
    b.arc(-85, 19.50)
    b.width(16.0)
    b.straight(123.50)

    # The ribbon is now back on top of station 0, and the line is already there.
    b.finish_at_start()
