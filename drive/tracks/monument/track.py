"""Monument

Jungle ruins over a green river. Up the pyramid's stairs and through the shrine
on top, down the serpent's half-pipe, and a leap off the cliff beside the
waterfall.
"""

from tracks.builder import FREE

slug = "monument"
name = "Monument"
difficulty = 4
ground = None
order = 300
width = 16.0
rails = False
exposed = True
closed = True
scenery = True

# The river is the floor of the world and touching it is a respawn
# (`below.kill`), WATER_DECK under the lowest road on the lap.
WATER_DECK = 9.0

# The pyramid: straight up the front stairs, across the shrine on the summit,
# straight down the back. scenery.js finds the summit as the highest flat run.
STAIRS = 90.0
PYRAMID_RISE = 24.0           # sqrt(330 * 24) = 89, so a hill, not a kicker
SUMMIT = 50.0

# The waterfall leap: up onto the cliff ledge, off the lip, down over the gorge.
LEDGE = 90.0
LEDGE_RISE = 18.0
LEAP_KICK = (5.0, 12.0)
LEAP = 48.0
LEAP_DROP = 12.0


def build(b):
    b.start(run=30)
    b.straight(60)
    b.arc(60, 50)
    b.straight(40)
    b.cp()
    b.arc(-60, 40)
    b.straight(30)

    # The pyramid. The gate stands in the shrine.
    b.straight(STAIRS, rise=PYRAMID_RISE)
    b.cp(pre=SUMMIT / 2, post=SUMMIT / 2)
    b.straight(STAIRS, rise=-PYRAMID_RISE)
    b.straight(30)

    b.arc(90, 24)
    b.straight(40)

    # The serpent: a half-pipe through the ruins.
    b.pipe(5.0, 0.34, "lr")
    b.arc(-60, 28)
    b.arc(120, 26)
    b.arc(-120, 26)
    b.arc(60, 28)
    b.flat()
    b.straight(40)
    b.cp()

    b.arc(90, 40)
    b.straight(30)

    # The waterfall leap.
    b.straight(LEDGE, rise=LEDGE_RISE)
    b.boost(20)
    b.straight(10)
    b.crest(*LEAP_KICK)
    b.gap(LEAP, drop=LEAP_DROP)
    b.rail("lr")
    b.straight(50)
    b.rail("")
    b.cp()

    b.straight(FREE(110))
    b.arc(-40, 34)
    b.arc(40, 34)
    b.straight(100)
    b.arc(90, 36)
    b.straight(80, rise=-(LEDGE_RISE + LEAP_KICK[0] - LEAP_DROP))
    # The terraces: a switchback into the ruins and back out.
    b.arc(90, 20)
    b.straight(90)
    b.arc(-180, 16)
    b.straight(56)
    b.cp()
    b.arc(90, 20)
    b.straight(40)
    b.arc(-30, 80)
    b.arc(30, 80)
    b.straight(FREE(89))
    b.arc(90, 45)
    b.straight(40)
    b.finish_at_start()
