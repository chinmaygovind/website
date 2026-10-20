"""Harbor

A haunted cove at night. Fast sweepers along rickety docks over black water,
a gangplank onto a ghost galleon and a cannon shot off its bow, a long banked
sweep round the whirlpool and its skull rock, a flick-flick chicane through
the wrecks, a hop between the jetties, and a fast run home along the quay.
"""

from tracks.builder import FREE

slug = "harbor"
name = "Harbor"
difficulty = 4
ground = None
order = 330
width = 14.0
rails = False
exposed = True
closed = True
scenery = True

# The water is the floor of the world and touching it is a respawn, as
# Citadel's lava is: `below.deck` in the palette reads this.
WATER_DECK = 5.0

# Where `pal.lamps` hangs a light: every LAMP_EVERY stations, LAMP_OFF either
# side of the centreline, LAMP_UP above it. scenery.js stands a lantern on a
# mooring post at the same spots and keeps its own copy of the numbers.
LAMP_EVERY = 18
LAMP_OFF = 11.0
LAMP_UP = 4.2

# The galleon. sqrt(330 * 15) = 70, so an 80-unit gangplank is a climb, not a
# kicker. The deck is wider than the road so it reads as a deck.
PLANK = 80.0
PLANK_RISE = 15.0
DECK = 104.0
DECK_W = 20.0
BOW_KICK = (4.0, 12.0)
BOW_GAP = 44.0
BOW_DROP = 10.0


def build(b):
    b.start(run=30)
    b.straight(24)
    b.rail("lr")

    # The docks: a left-right flick between the boathouses, a dip along the
    # boardwalk and a fast right that climbs back up.
    b.arc(-24, 52)
    b.arc(46, 42)
    b.arc(-22, 52)
    b.straight(40, rise=-3.0)
    b.straight(50, rise=3.0)
    b.arc(30, 55)
    b.arc(-60, 45)
    b.arc(30, 55)
    b.straight(60)
    b.arc(85, 58, bank=8)
    b.rail("")
    b.cp()

    # Up the gangplank, the length of the deck, and off the bow on the cannon.
    b.boost(14)
    b.straight(PLANK, rise=PLANK_RISE)
    b.width(DECK_W)
    b.straight(DECK)
    b.boost(16)
    b.crest(*BOW_KICK)
    b.gap(BOW_GAP, drop=BOW_DROP)
    b.rail("lr")
    b.straight(FREE(105))
    b.rail("")
    b.width(width)
    b.cp()

    # Down off the rocks and round the whirlpool: one long banked sweep with
    # the skull rock on the inside.
    b.arc(70, 52, rise=-6.0, bank=10)
    b.straight(90, rise=-3.0)
    b.arc(-26, 60)
    b.arc(26, 60)
    b.straight(70)
    b.arc(22, 64)
    b.arc(-44, 50)
    b.arc(22, 64)
    b.straight(170)
    b.width(16.0)
    b.arc(95, 46, rise=-2.0, bank=16)
    b.width(width)
    b.straight(30)
    b.cp()

    # The wreck run: over a hull's back, then a flick-flick between the hulks.
    b.straight(200)
    b.straight(80, rise=7.0)
    b.straight(80, rise=-7.0)
    b.rail("lr")
    b.arc(38, 40)
    b.arc(-76, 30)
    b.arc(38, 40)
    b.rail("")
    b.straight(30)
    b.arc(55, 56, bank=8)
    b.cp()

    # The jetties: a hop from one pier to the next, a sweeper, and home.
    b.straight(30)
    b.crest(2.0, 10)
    b.gap(20, drop=2.0)
    b.straight(40)
    b.rail("lr")
    b.arc(-30, 50)
    b.arc(58, 44)
    b.arc(27, 80, rise=FREE(2.0))
    b.rail("")
    b.straight(FREE(58))
    b.finish_at_start()
