"""Starport

A neon space station adrift in the void. Boost-fed leaps between station
modules, a wall ride round the reactor, and a half-pipe tube down the spine.
"""

from tracks.builder import FREE

slug = "starport"
name = "Starport"
difficulty = 5
ground = None
order = 310
width = 15.0
rails = False
exposed = True
closed = True
scenery = True

# The lap is a figure of eight whose crossing is the reactor: the ring climbs
# 12 round the core and leaves over its own approach.
RING_W = 21.0
RING_R = 40.0
RING_RISE = 12.0


def build(b):
    b.start(run=30)
    b.straight(60)

    # Out of the dock, a third-gear left climbing onto the first module.
    b.arc(-90, 34, rise=6)
    b.straight(30)
    b.cp()

    # Module leap: pad, lip, and across to the next module.
    b.boost(24)
    b.straight(10)
    b.crest(5.0, 12.0)
    b.gap(40.0, drop=5.0)
    b.rail("lr")
    b.straight(50)
    b.rail("")

    # A fast kink lining up the reactor.
    b.arc(45, 60)
    b.arc(-45, 60)
    b.straight(70)

    # The reactor ring: a wall of death round the core, leaving over the road
    # that came in.
    b.width(RING_W)
    b.wall(-270, RING_R, 88.0, ramp=90, rise=RING_RISE)
    b.width(width)
    b.cp(pre=17, post=19)

    # The spine: a half-pipe tube through a serpent.
    b.straight(20)
    b.pipe(5.0, 0.34, "lr")
    b.arc(-50, 30)
    b.arc(100, 26)
    b.arc(-50, 30)
    b.flat()
    b.straight(30)
    b.cp()

    # Top of the station, a tight right onto the long gantry.
    b.arc(90, 18)
    b.straight(40)

    # The long leap: the biggest gap on the lap, fed by the longest pad.
    b.boost(30)
    b.straight(10)
    b.crest(6.0, 14.0)
    b.gap(56.0, drop=12.0, bow=11.5)
    b.rail("lr")
    b.straight(90)
    b.rail("")
    b.cp()
    b.straight(40)
    b.arc(-25, 70)
    b.arc(25, 70)
    b.straight(20)

    # The hangar sweep: a long banked right, outside wall up.
    b.pipe(4.0, 0.4, "l")
    b.arc(90, 50)
    b.flat()
    b.straight(40)

    # Down the south side through a chicane, losing the height.
    b.straight(FREE(192), rise=FREE(-12))
    b.arc(-30, 32)
    b.arc(60, 28)
    b.arc(-30, 32)
    b.straight(60)
    b.cp()

    # Home: up the west side, a hairpin round the dock, and down onto the line.
    b.arc(90, 36)
    b.straight(FREE(196))
    b.rail("l")
    b.arc(180, 21)
    b.rail("")
    b.straight(90)
    b.arc(FREE(-90), 30)
    b.straight(30)
    b.finish_at_start()
