"""Starport

An orbital station over a planet: sweepers along the solar wings, chicanes
through the gantries, a boost-fed leap between two modules and a drop off the
docking spine onto the lower deck.
"""

from tracks.builder import FREE

slug = "starport"
name = "Starport"
difficulty = 4
ground = None
order = 310
width = 15.0
rails = False
exposed = True
closed = True
scenery = True


def build(b):
    # The main deck, under the docking ring.
    b.start(run=30)
    b.straight(60)

    # Off the deck: a fast right falling toward the solar wing.
    b.arc(55, 60, rise=-8)
    b.straight(30)

    # Gantry chicane: quick left-right-left flicks.
    b.rail("lr")
    b.arc(-30, 34)
    b.arc(60, 32)
    b.arc(-30, 34)
    b.rail("")
    b.straight(20)
    b.cp()

    # Climbing banked right onto the habitat spine.
    b.arc(80, 55, rise=16, bank=10)
    b.straight(24)

    # The leap: pad, lip, and across to the next module.
    b.boost(24)
    b.straight(8)
    b.crest(5.0, 12.0)
    b.gap(42.0, drop=8.0)
    b.rail("lr")
    b.straight(56)
    b.rail("")
    b.cp()

    # Along the solar wings: a left kink into a long banked right.
    b.arc(-40, 55)
    b.arc(95, 44, bank=12)
    b.straight(20)

    # A dip and a crest between the arrays.
    b.straight(72, rise=-15)
    b.straight(60, rise=10)
    b.hump(1.6, 30)
    b.straight(20)
    b.cp()

    # The drop: off the end of the docking spine onto the lower deck.
    b.straight(20)
    b.crest(2.0, 10.0)
    b.gap(32.0, drop=14.0, bow=4.5)
    b.rail("lr")
    b.straight(50)
    b.rail("")

    # Esses past the docked freighters.
    b.rail("lr")
    b.arc(45, 40)
    b.arc(-70, 36)
    b.arc(45, 40)
    b.rail("")
    b.straight(FREE(92), rise=FREE(12))
    b.cp()

    # Round the back of the station.
    b.arc(70, 58, bank=8)
    b.straight(135)
    b.arc(60, 52, bank=8)
    b.straight(30)

    # The top of the station: an S over the reactor and a crest down onto
    # the deck.
    b.arc(-30, 46)
    b.arc(FREE(50), 40)
    b.straight(FREE(92), rise=10)
    b.arc(-35, 38)
    b.arc(35, 38)
    b.straight(70)
    b.arc(25, 55)
    b.arc(-25, 55)
    b.straight(65)
    b.straight(70, rise=-10)
    b.straight(30)
    b.finish_at_start()
