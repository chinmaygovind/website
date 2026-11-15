"""Harvest

A country lap at golden hour: rolling hills, a tunnel of red maples, and piles
of fallen leaves on the road that burst when you drive through them.
"""

from tracks.builder import FREE

slug = "harvest"
name = "Harvest"
difficulty = 2
ground = -1.2
order = 350
width = 14.0
closed = True
scenery = True


def build(b):
    # --- the lane out of the village ------------------------------------------
    b.start(run=30)
    b.straight(150)
    b.arc(90, 40)
    b.straight(90, rise=6)
    # Flowing esses over the first hill.
    b.arc(-35, 70)
    b.arc(35, 70)
    b.cp()
    # --- the maple tunnel -----------------------------------------------------
    # One long gentle descent under the canopy, with a sweeper at each end so
    # the whole tunnel comes into view at once. `scenery.js` finds this as the
    # longest straight on the lap, so it needs no fraction kept in sync.
    b.arc(60, 50)
    b.straight(240, rise=-4)
    b.arc(30, 80)
    b.cp()
    # --- the farm corner and the hill -----------------------------------------
    # The one real braking point on the lap.
    b.arc(90, 22)
    b.straight(130, rise=8)
    b.hump(2, 50)                               # the small crest
    b.cp()
    # --- the orchard --------------------------------------------------------
    b.arc(-90, 45)
    b.straight(110, rise=-6)
    b.arc(-100, 30)
    b.straight(60)
    b.arc(70, 40)
    b.cp()
    b.arc(80, 34)
    b.straight(120, rise=-8)
    b.arc(-30, 70)
    b.arc(120, 50)
    b.cp()
    # --- home along the valley ----------------------------------------------
    b.straight(FREE(96))
    b.arc(40, 60)
    b.straight(130, rise=4)
    b.arc(20, 120)
    b.arc(-20, 120)
    b.straight(FREE(106))
    b.finish_at_start()
    return b
