"""Tokyo Drift

I wonder if you know / How they live in Tokyo
"""

slug = "tokyo"
name = "Tokyo Drift"
blurb = "I wonder if you know / How they live in Tokyo"
difficulty = 5
# Set by hand rather than cut by `tools/set_medals.py`, because one lap on the
# board is not a top five to aim at. Gold at 48.0 against a 53.66 ideal, which is
# 0.89 of it - the tight end of the 0.77-0.90 band every record on this site sits
# in, and a real ask on the pool's only difficulty-5 track. Silver and bronze
# follow the tool's own two 5% steps so the three stay three steps of one
# standard. Re-cut once the board is deep enough.
medals = (48.0, 50.4, 53.0)
ground = -1.2
order = 160
width = 12.0
rails = False
scenery = True

# The roof jump. **It flies across, it does not fall.**
#
# The first version dropped 28 units off the deck to street level and then spent
# the whole expressway climbing back to 62, which is two unrelated ideas bolted
# together: you cannot see why you went up if the first thing you do is come
# down. Now the deck, the flight and everything after it stay at altitude, and
# the only descent on the track is the one at the end that finishes it.
#
# What makes it big is the void underneath rather than the fall. The lip is 41
# up and the street is at zero, so there is nothing below the car for the whole
# flight - it just happens to land level with where it took off.
#
# Hang time is 1.2s at racing speed, against Big Red's just-under-two, which is
# the pool's ceiling: `AIR_PITCH` rotates the nose down at a constant rate for
# as long as the throttle is held, so hang time and not span is what decides how
# far past level the car has turned by touchdown.
JUMP_RISE, JUMP_KICK = 2.5, 10.0
JUMP_GAP, JUMP_DROP = 46.0, 5.0


def build(b):
    """Six movements, and the city is the whole of it.

    Alleys, a scramble, the car park helix, a jump between rooftops, the
    expressway, and one long descent back down to the street for the flag.

    **Nothing here has a barrier of any kind, and that is forced.** It is a
    ground track, so `test_barriers_are_opt_in` allows it exactly zero walled
    stations, and the armco that would otherwise line an elevated road comes
    only from `pal.terrain`, which this track cannot have - see `palette.py`.

    The height profile is built around the flat ground quad at y=-1.2: 0 through
    the streets, 39 at the top of the helix, 34 across the jump, 51 along the
    expressway, back to 2 at the flag. **Nothing ever goes below the start**,
    which is what keeps the road out of its own ground plane.
    """
    # 1. Neon alleys. Narrow, tight and linked.
    #
    #    **Half the length it was, and the cut came out of the straights.** The
    #    first pass spent 559 units and four checkpoints getting to the helix,
    #    which is a quarter of the track before the first thing worth driving,
    #    and most of it was road going in a straight line between corners. The
    #    corners are all still here; what is gone is the waiting.
    b.start(run=30)
    b.width(9.5)
    b.arc(-72, 24).straight(20)
    b.cp()
    b.arc(84, 21).straight(16)
    b.arc(-96, 23).straight(18)

    # 2. The scramble. The road opens to seventeen for one wide intersection,
    #    which is the only room the track gives you until the expressway - and a
    #    pad on the way out of it, because what follows is three storeys of
    #    hairpin and this is the last chance to carry speed at anything.
    b.width(17.0)
    b.straight(28)
    b.arc(-88, 34)
    b.boost(length=14)
    b.straight(22)

    # 3. The helix: three storeys of open-air car park ramp, tightening as it
    #    climbs. The radius taper drifts the axis about two units a storey rather
    #    than stacking perfectly concentric - invisible at this scale, and it
    #    feeds three distinct radii into the corner-variety test for free.
    #
    #    **The ramp is narrow, and that is load-bearing rather than flavour.**
    #    `gate_ceiling` is derived from the closest this track ever passes over
    #    itself, and on a helix that distance is not set by the climb - it is set
    #    by how wide the road is. Two stations count as overlapping while they
    #    are within `hw + hw` of each other in plan, so a wider ramp overlaps the
    #    turn below it across a wider arc, and the far end of that arc is where
    #    the two are furthest apart in *height*. At width 11 the worst pair came
    #    out 8.2 apart on a 10-unit storey and pinned the whole track's gate
    #    ceiling to its floor of 5. At 9.5 on a 12-unit storey it clears 10.2.
    #
    #    A car park ramp is about one and a bit cars wide in any case, so the
    #    number that fixes the checkpoints is also the one that makes it read as
    #    a car park rather than as a banked test bowl.
    b.width(9.5)
    b.straight(34, rise=3.0)
    b.cp()
    b.arc(360, 18, rise=12.0, bank=8)
    b.arc(360, 16, rise=12.0, bank=8)
    b.arc(360, 14, rise=12.0, bank=6)
    b.cp()

    # 4. Off the roof and onto the expressway, without coming down.
    #
    #    You arrive on the deck slow - three storeys of hairpin does that - and
    #    the jump needs speed, so the deck run is a straight with a pad in it.
    #    Same shape Big Red uses to feed its kickers, and it is what a pad is
    #    for: out of a slow corner, into a place the speed is usable.
    b.width(13.0)
    b.straight(30)
    b.boost(length=14)
    b.straight(40)
    b.jump(JUMP_RISE, JUMP_GAP, drop=JUMP_DROP, kick=JUMP_KICK, land=100)
    b.cp()

    # 5. The Shuto, elevated the whole way. Long fourth-gear sweeps between the
    #    towers - the only part of the track that breathes, and where the medal
    #    time is actually set.
    #    The pad goes on the long straight rather than at either end of it: a
    #    pad is a *place*, so it is worth the same second of engine wherever the
    #    car meets it, and the only thing that changes is how much road is left
    #    to spend it on.
    b.width(14.0)
    b.arc(-62, 80, rise=5.0).straight(50, rise=3.0)
    b.boost(length=16)
    b.straight(54, rise=3.0)
    b.cp()
    b.arc(74, 95, rise=6.0).straight(130)
    b.cp()

    # 6. Down. Four switchbacks off the expressway back to street level.
    #
    #    The descent is on the *straights* rather than in the corners, and that
    #    is forced rather than chosen: a hairpin is short, and `length >=
    #    sqrt(330 * rise)` turns a corner that drops much at all into a kicker.
    #    A 152-degree corner at radius 20 is 53 units of road, which buys four
    #    units of drop and no more.
    b.width(10.5)
    b.arc(-152, 20, rise=-4.0).straight(56, rise=-8.0)
    b.cp()
    b.arc(148, 18, rise=-4.0).straight(54, rise=-8.0)
    b.arc(-140, 22, rise=-4.0).straight(56, rise=-8.0)
    b.cp()
    b.arc(152, 17, rise=-4.0).straight(58, rise=-9.0)

    # Out at the bottom, one block, and the flag.
    b.width(12.0)
    b.arc(58, 40).straight(46)
    b.finish()
