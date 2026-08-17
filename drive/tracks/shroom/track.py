"""Shroom Street

A gorge road with a circuit's corners on it, and mushrooms where the road runs out.
"""

slug = "shroom"
name = "Shroom Street"
difficulty = 2
# Cut against the first real lap driven here, 41.109 by Chinmay, rather than
# derived from `laptime.ideal_lap` - see `tools/set_medals.py` for why the
# estimate makes a poor standard.
#
# **Gold is set by hand at 42.0 and that is a tighter call than the tool's.**
# `set_medals.py` would say 43.6 (the record capped at `WR x 1.06`, since with one
# lap on the board there is no fifth-best to aim at); 42.0 asks for the record
# beaten by 0.9s instead of 2.5s. Silver and bronze then follow the tool's own two
# 5% steps, so the three medals stay three steps of one standard rather than three
# separate opinions. Re-cut with `tools/set_medals.py --db ... --write` once the
# board is deep enough to have a real top five.
medals = (42.0, 44.1, 46.4)
ground = None
order = 170
width = 15.5
exposed = True
scenery = True

# --- the crossings ---------------------------------------------------------
#
# **The whole crossing is arithmetic around one number**, and it is `BOUNCE_VEL`.
# A cap throws the car straight up its own normal at 21 u/s regardless of how it
# was arrived at, which puts the apex 7.4 units up and the car back down 1.4
# seconds later - and 1.4 seconds is where the pool's jumps top out, for the
# reason `AIR_PITCH` gives: the nose keeps rotating down for as long as the
# throttle is held in the air, so a longer flight lands further past level rather
# than further downrange.
#
# So hang time is fixed and **reach is purely a function of the speed you leave
# with**: 1.4 seconds at 34 u/s is 48 units, at 48 u/s it is 67. That is a
# nineteen-unit spread on where the car touches down, and it is not something a
# player can be asked to trim - the speed they arrive with is set by how the
# corner two hundred units back went.
#
# Hence the two rules every cap here obeys:
#
# **A cap is long.** 26 units, seven stations, against the 14 a `boost` pad gets.
# Sized off that spread, not off what a mushroom looks like: with GAP_MID at 44,
# a 26-unit cap catches everything between 31 and 50 u/s, which is the whole
# realistic range. Big Red's landing straight learned this the expensive way - a
# 46-unit zone that the ideal line landed in and a fast entry flew clean over.
#
# **A cap is wider than the road.** 24 against 15.5. The car arrives out of the
# air with `AIR_STEER`'s fraction of its steering authority, so a cap is aimed at
# rather than steered onto.
CAP_LEN = 26.0
CAP_W = 24.0

# The entry gap is the only one the *geometry* has to carry, because the lip is
# ordinary road and there is no cap behind it to do the throwing. So it is short
# and it drops.
GAP_IN = 30.0
DROP_IN = 12.0

# Cap to cap, level. 44 rather than the 53 the ideal line actually reaches, which
# is deliberate: landing at 53 into a cap that starts at 44 puts the car nine
# units onto a 26-unit disc, so slow arrivals still land on it and fast ones have
# seventeen units of cap left in front of them.
GAP_MID = 44.0

# `bow` is the racing line's arc through a gap and the default is a small capped
# ballistic hint - fine for a kicker, wrong for a cap, where the real arc peaks at
# BOUNCE_VEL^2 / 2g = 7.4 units. Left at the default the line through the gap is a
# near-chord, the tangent kinks at the lip, and `speed_profile`'s curvature cap
# reads that kink as a tight corner and brakes for it - the same failure Big Red's
# main jump has a note about.
BOW = 7.0

# Coming off the last cap the road is *above* it, so the exit gap has a negative
# drop.
GAP_OUT = 38.0
RISE_OUT = -4.0


def build(b):
    """Spa's shape, in a gorge, with mushrooms where the road runs out.

    **The corners are the track and the mushrooms are the event**, which is the
    other way round from how this started. The first version was 2900 units with
    two full crossings in it and about a third of the lap spent in the air, and
    what that costs is the driving: a car in flight is not being steered, so air
    time is time the track is not asking you anything. Cut to 2200 with one big
    crossing and one single-cap hop, and the room that bought went into corner
    sequences.

    Those sequences are Spa's, because Spa is the circuit whose corners are all
    *different questions* - and that is the thing worth copying, more than any
    individual corner:

    - **La Source**, a hairpin off the line, so the lap opens by taking all the
      speed away and making you build it again.
    - **Eau Rouge**, a plunge into a left, a hard right and a climb, taken blind
      over a crest. The one place on the track with rails on a fast corner.
    - **Kemmel**, the long straight that only exists to make the next corner a
      braking decision.
    - **Les Combes**, right-left-right, tight, all three at different radii so
      none of them is the same corner twice.
    - **Pouhon**, a fast double-apex left you commit to on entry.
    - **Blanchimont**, an 86-radius sweeper that barely slows you at all.
    - **the Bus Stop**, two 17-radius corners back to back before the flag.

    The gorge crossing sits between Les Combes and Pouhon, at the bottom of the
    descent, which is where the road would run out if a gorge were really there.
    """
    # --- La Source, and the plunge into Eau Rouge -------------------------
    b.start(run=42)
    b.arc(-155, 20)
    b.boost(20)
    b.straight(64, rise=-5)
    b.arc(34, 46, rise=2)
    # Rails on the hard right and over the brow, and nowhere else on this
    # movement. Big Red's rule: an exposed track keeps them where going off is
    # not an avoidable mistake, and this is a blind uphill right taken flat.
    b.rail("lr")
    b.arc(-62, 48, rise=5)
    b.crest(4, 30)
    b.rail("")
    b.cp()

    # --- Kemmel, into Les Combes -----------------------------------------
    b.straight(124)
    b.rail("lr")
    b.arc(78, 25)
    b.arc(-84, 23)
    b.arc(56, 29)
    b.rail("")
    b.straight(70, rise=-6)
    b.cp()

    # --- the gorge: three caps -------------------------------------------
    b.straight(56, rise=-7)
    _crossing(b, caps=3)

    # --- Pouhon, and a quick chicane out of it ---------------------------
    b.arc(86, 48, rise=9)
    b.cp()
    b.arc(54, 64)
    b.arc(44, 46)
    b.straight(58)
    b.rail("lr")
    b.arc(-48, 21)
    b.arc(52, 21)
    b.rail("")
    b.boost(20)
    b.straight(86)
    b.cp()

    # --- one cap, back across the same gorge ------------------------------
    # A single mushroom rather than a second full crossing. By now you know what
    # a cap does, so the interesting question has moved from "can I land on it"
    # to "how much speed can I carry onto it" - and one cap asks that in a
    # hundred units where three would take three hundred and fifty.
    #
    # It is the *same* gorge, not a second one, which is why the carve in
    # `scenery.js` takes its depth from the nearest crossing station rather than
    # from a global floor: the road comes back to the chasm a couple of hundred
    # units along it and both crossings have to sit over one canyon.
    _crossing(b, caps=1, cap_len=24.0, gap_in=26.0, drop_in=8.0,
              gap_out=34.0, rise_out=-3.0, land=80.0)

    # --- Blanchimont, and the Bus Stop -----------------------------------
    b.arc(-76, 86)
    b.straight(54)
    b.hump(6, 54)
    b.arc(64, 42)
    b.straight(62)
    b.rail("lr")
    b.arc(88, 17)
    b.arc(-92, 17)
    b.rail("")
    b.cp()
    b.straight(48)
    b.finish()


def _crossing(b, caps, cap_len=CAP_LEN, gap_in=GAP_IN, drop_in=DROP_IN,
              gap_mid=GAP_MID, gap_out=GAP_OUT, rise_out=RISE_OUT, land=92.0):
    """Lip, `caps` mushrooms with gaps between them, landing.

    Written once and called twice rather than laid out inline both times, because
    the five numbers here are related to each other by the ballistics above, and
    the failure mode of getting one of them wrong by hand on the second call only
    is a gap that clears on the ideal line and not on a real one.
    """
    b.width(CAP_W)
    b.gap(gap_in, drop=drop_in)
    for i in range(caps):
        b.bounce(cap_len)
        if i < caps - 1:
            b.gap(gap_mid, bow=BOW)
    b.gap(gap_out, drop=rise_out, bow=BOW)
    b.width(width)
    # The one place a crossing gets barriers. Everything else out here is unrailed
    # and that is the track - but the car lands off the last cap with `AIR_STEER`'s
    # steering and whatever attitude the flight left it, which is exactly where
    # Big Red keeps its own.
    b.rail("lr").straight(land)
    b.rail("")
