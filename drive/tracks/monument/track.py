"""Monument

Jungle ruins over a green river. Up the pyramid's stairs and through the shrine
on top, down the serpent's half-pipe, and a leap off the cliff beside the
waterfall.

The driving between the set pieces is sweepers and flicks rather than
hairpins: nothing on the lap is tighter than 30, so a pack stays strung out
instead of stacking up at a U-turn, and the height comes from crests, dips and
banked corners rather than from braking.
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
LANDED = LEDGE_RISE + LEAP_KICK[0] - LEAP_DROP


def build(b):
    b.start(run=30)
    b.straight(40)
    # A fast left-right flick off the line, lifting toward the pyramid.
    b.arc(-30, 60, rise=3)
    b.arc(30, 60, rise=-3)
    b.straight(20)
    b.cp()

    # The pyramid. The gate stands in the shrine.
    b.straight(STAIRS, rise=PYRAMID_RISE)
    b.cp(pre=SUMMIT / 2, post=SUMMIT / 2)
    b.straight(STAIRS, rise=-PYRAMID_RISE)
    b.straight(20)

    b.rail("lr")
    b.arc(50, 60, bank=8)
    b.straight(15)
    b.arc(40, 40, bank=10)
    b.straight(57)
    b.arc(-20, 100)
    b.arc(20, 100)
    b.rail("")

    # The serpent: a half-pipe through the ruins, swung left-right-left.
    b.pipe(5.0, 0.34, "lr")
    b.arc(-50, 48)
    b.arc(100, 44)
    b.arc(-50, 48)
    b.flat()
    b.straight(38)
    b.arc(25, 80, rise=3)
    b.arc(-25, 80, rise=-3)
    b.cp()

    b.arc(90, 50, bank=8)
    b.straight(20)

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

    # Off the gorge: a flick, then sweepers falling back to the river.
    b.straight(FREE(60))
    b.rail("lr")
    b.arc(25, 55)
    b.arc(-25, 55)
    b.straight(30)
    b.arc(70, 48, rise=-LANDED / 2, bank=12)
    b.arc(-40, 70)
    b.straight(40, rise=-LANDED / 2)
    b.arc(60, 60, bank=8)
    b.rail("")
    # A crest and a dip down the far bank.
    b.straight(45, rise=5)
    b.straight(45, rise=-5)
    b.cp()
    # The chicane through the ruins, then one more sweeping S.
    b.rail("lr")
    b.arc(-30, 34)
    b.arc(60, 32)
    b.arc(-30, 34)
    b.straight(10)
    b.arc(-35, 65)
    b.arc(35, 65)
    b.rail("")
    b.straight(FREE(30))
    b.rail("lr")
    b.arc(90, 42, bank=8)
    b.rail("")
    b.straight(80)
    b.finish_at_start()
