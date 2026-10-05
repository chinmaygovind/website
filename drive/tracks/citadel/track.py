"""Citadel

A fortress standing in a lake of lava. Grates over the fire, a hall you can
leave through its own ceiling, a wall of death round the keep, and geysers.
"""

from tracks.builder import FREE

slug = "citadel"
name = "Citadel"
difficulty = 5
ground = None
order = 280
width = 16.0
rails = False
exposed = True
closed = True
scenery = True

# **The lava is the floor of the world, and touching it is a respawn.** It sits
# `LAVA_DECK` under the lowest road on the lap (`below.deck` in the palette reads
# this), and `below.kill` puts `killY` on its surface rather than twenty-six units
# past it - so a jump that comes up short ends in the fire you can see, not in a
# fall through it.
LAVA_DECK = 7.0

# The grate road. Wider than the tarmac, because a grate is where a geyser can
# come up through the road and the width is what makes a column something you
# steer round rather than something you wait behind - Dino Park's rule.
GRATE_W = 20.0

# **The Hall.** The lap's first long straight runs under its own later climb:
# hairpin left, climb back the way you came, hairpin left again, and the
# rampart is laid directly over the hall's roofline. It is the shortcut's whole
# geometry, and the numbers below are the alignment.
HALL = 150.0
HAIRPIN_R = 15.0
STAIR = 80.0                  # the climb between the two hairpins
STAIR_RISE = 20.0             # sqrt(330 * 20) = 81, so this is a hill, not a kicker
TURN_RISE = 6.0               # the second hairpin climbs too

# The rampart's hole: a kicker and a gap over the end of the hall. A car on the
# rampart jumps it; a car in the hall can come up *through* it on the geyser
# that stands underneath, and land on the rampart past the far lip.
HOLE = 46.0
HOLE_KICK = (5.0, 10.0)


def build(b):
    b.start(run=30)
    b.straight(30)

    # Over the moat on a plain causeway. It was a pad-fed jump, and the first
    # thing on the lap is the worst place for one: the whole grid arrives at it
    # together and the bots went into the lava off it.
    b.straight(82)
    b.arc(90, 22)
    b.straight(24)
    b.cp()

    # The Hall, on grates. The geyser stands over the last thirty units of it.
    b.width(GRATE_W)
    b.skin(True)
    b.straight(HALL)
    b.skin(False)
    b.width(width)
    b.arc(-180, HAIRPIN_R)
    b.straight(STAIR, rise=STAIR_RISE)
    b.arc(-180, HAIRPIN_R, rise=TURN_RISE)

    # The rampart, over the Hall. **No checkpoint between the Hall and the
    # rampart's landing**: that is the stretch the geyser skips, and a gate on
    # it would make the shortcut a missed checkpoint.
    b.boost(24)
    b.straight(12)
    b.crest(*HOLE_KICK)
    b.gap(HOLE, drop=HOLE_KICK[0])
    b.width(22.0)
    b.rail("lr")
    b.straight(100)
    b.width(width)
    # The barrier runs on through the gate to the foot of the wall: the leap's
    # run-up passes ten units under this deck, and without it you could drop
    # off the edge onto it and skip the whole keep.
    b.cp()
    b.rail("")

    # The keep: a wall of death round the tower, coming down.
    b.width(21.0)
    b.wall(270, 40, 88.0, ramp=90, rise=-10)
    b.width(width)
    # A gate straight off the wall's foot, *before* the run-up passes under
    # the rampart. Dropping off the rampart lands you past it, so skipping the
    # keep is a missed checkpoint whichever edge you went over - a barrier only
    # moved the problem to the next stretch without one.
    b.cp(pre=17, post=19)

    # The leap: off the keep's foot and down over the lake.
    b.boost(26)
    b.crest(5.0, 12.0)
    b.gap(46.0, drop=12.0)
    b.rail("lr")
    b.straight(46)
    b.rail("")
    b.cp()

    # The forge: two grate corners over the lava river, each with a geyser
    # standing on the apex.
    b.width(GRATE_W)
    b.skin(True)
    b.arc(-90, 28)
    b.straight(30)
    b.arc(90, 32)
    b.skin(False)
    b.width(width)
    b.cp(pre=26, post=17)
    b.arc(-90, 20)

    # The Switchbacks: a half-pipe serpent down the east side. Ride the walls
    # for a straighter line, or stay low and take every bend.
    b.straight(20)
    b.pipe(5.0, 0.34, "lr")
    b.arc(-60, 28)
    b.arc(120, 26)
    b.arc(-120, 26)
    b.arc(60, 28)
    b.flat()
    b.straight(FREE(42))

    # The Geyser Run: three grate bends over the lava, a column on every apex.
    b.width(GRATE_W)
    b.skin(True)
    b.arc(40, 40)
    b.arc(-80, 34)
    b.arc(40, 40)
    b.skin(False)
    b.width(width)
    b.straight(30)

    # The outer bailey, coming home: west under the curtain wall, down the
    # last of the height.
    b.arc(-90, 30)
    b.straight(60, rise=FREE(-4.5))
    b.hump(2.5, 30)
    b.cp(pre=6, post=17)
    b.arc(30, 34)
    b.arc(-30, 34)
    b.straight(40, rise=-4.5)
    b.width(GRATE_W)
    b.skin(True)
    b.arc(-45, 44)
    b.arc(45, 44)
    b.skin(False)
    b.width(width)
    b.straight(FREE(73))
    # The slalom, through the gatehouse towers on the way back to the line.
    b.arc(-35, 46)
    b.arc(70, 38)
    b.arc(-35, 46)
    b.straight(24)
    b.arc(-90, 26)
    b.straight(60)
    b.arc(FREE(-90), 26)
    b.straight(40)
    b.finish_at_start()
