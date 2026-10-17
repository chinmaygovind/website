"""Frost

Out of the ski lodge, up the switchbacks, off the summit in one long leap,
through the ice cave and round the frozen lake.
"""

from tracks.builder import FREE

slug = "frost"
name = "Frost"
difficulty = 3
ground = -1.2
order = 320
width = 17.0
rails = False
closed = True
scenery = True

# The switchbacks: three climbing legs joined by two hairpins. HAIRPIN_R sets how
# far apart the legs run (2r between centrelines), which has to leave room for
# the run-off on both and keep the terrain between them a slope, not a cliff.
LEG = 140.0
LEG_RISE = 14.0               # sqrt(330 * 14) = 68, so a hill, not a kicker
HAIRPIN_R = 26.0


def build(b):
    b.start(run=30)
    b.straight(130)
    b.arc(90, 45)
    b.straight(50)
    b.arc(-40, 60)
    b.arc(40, 60)
    b.cp()

    # The switchbacks.
    b.straight(LEG, rise=LEG_RISE)
    b.arc(-180, HAIRPIN_R, rise=4)
    b.straight(LEG, rise=LEG_RISE)
    b.arc(180, HAIRPIN_R, rise=4)
    b.straight(200, rise=LEG_RISE)
    b.cp()

    # The summit and the leap: a kicker at the top, then the road falls away
    # steeper than the car does and it lands on the slope.
    b.arc(90, 40)
    b.straight(30)
    b.boost(20)
    b.crest(3, 12)
    b.crest(-14, 50)
    b.straight(86, rise=-10)
    b.cp()

    # The ice cave: a half-pipe through gentle bends, under a vault.
    b.straight(20)
    b.pipe(4.5, 0.4, "lr")
    b.arc(-30, 80, rise=-4)
    b.arc(60, 80, rise=-6)
    b.arc(-30, 80, rise=-4)
    b.flat()
    b.straight(30)
    b.cp()

    # Down to the frozen lake, then one long sweeper across the ice. The lake
    # is the lowest ground on the lap, level with the lodge.
    b.arc(90, 32)
    b.straight(112, rise=FREE(-15))
    b.arc(-50, 90)
    b.arc(100, 85)
    b.straight(FREE(90))
    b.cp()

    # The pine esses, back down to the lodge.
    b.arc(-45, 38)
    b.arc(70, 34)
    b.arc(15, 60)
    b.straight(FREE(80))
    b.finish_at_start()
