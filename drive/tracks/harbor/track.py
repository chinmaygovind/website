"""Harbor

A haunted cove at night. Rickety docks over black water, a gangplank onto a
ghost ship and a cannon shot off its bow, a wall ride round the whirlpool and
its skull rock, a half-pipe through the wrecks, and home over the jetties.
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
WATER_DECK = 6.0

# The galleon. sqrt(330 * 18) = 77, so the gangplank is a climb, not a kicker.
PLANK = 80.0
PLANK_RISE = 18.0
DECK = 120.0
DECK_W = 20.0
BOW_KICK = (5.0, 12.0)
BOW_GAP = 50.0
BOW_DROP = 11.0

# The whirlpool: a wall of death spiralling down round the skull rock, and
# leaving underneath its own approach - the lap is a figure of eight whose
# crossing is the whirlpool, so the corners away from it sum to +270.
WALL_R = 40.0
WALL_W = 21.0
WALL_DROP = BOW_DROP - BOW_KICK[0] - PLANK_RISE


def build(b):
    b.start(run=30)
    b.straight(40)

    # The docks: loose planks and a jink between the boathouses.
    b.hump(1.4, 16)
    b.straight(16)
    b.hump(1.4, 16)
    b.arc(-30, 40)
    b.arc(30, 40)
    b.straight(70)
    b.hump(1.4, 16)
    b.straight(54)
    b.cp()
    b.arc(90, 26)

    # Up the gangplank, the length of the deck, and off the bow on the cannon.
    b.straight(80)
    b.boost(16)
    b.straight(PLANK, rise=PLANK_RISE)
    b.width(DECK_W)
    b.straight(DECK)
    b.boost(20)
    b.crest(*BOW_KICK)
    b.gap(BOW_GAP, drop=BOW_DROP)
    b.rail("lr")
    b.straight(44)
    b.width(width)
    b.cp()
    b.rail("")

    # The whirlpool. A gate straight off its foot, before the road passes
    # under the landing, so dropping off the landing skips nothing.
    b.width(WALL_W)
    b.wall(-270, WALL_R, 88.0, ramp=90, rise=WALL_DROP)
    b.width(width)
    b.cp(pre=17, post=19)

    # The wreck run: a half-pipe serpent between the hulks.
    b.straight(145)
    b.pipe(5.0, 0.34, "lr")
    b.arc(-60, 28)
    b.arc(120, 26)
    b.arc(-120, 26)
    b.arc(60, 28)
    b.flat()
    b.straight(FREE(150))
    b.cp()

    # The jetties: a hairpin north, a hop from one pier to the next, the
    # boardwalk esses, and a long sweep back onto the docks.
    b.arc(90, 18)
    b.straight(132)
    b.crest(2.5, 10)
    b.gap(22, drop=2.5)
    b.straight(36)
    b.arc(-45, 40)
    b.arc(90, 32)
    b.arc(-45, 40)
    b.straight(FREE(90), rise=FREE(10.0))
    b.arc(90, 50, rise=-10.0)
    b.straight(60)
    b.finish_at_start()
