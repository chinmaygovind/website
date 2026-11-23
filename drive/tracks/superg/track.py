"""Super-G

Adopted from a community track by Brumm.
"""

slug = 'superg'
name = 'Super-G'
author = 'Brumm'
difficulty = 4
# Derived from the ribbon when this was adopted, not cut from a board.
# Re-cut with tools/set_medals.py once it has one worth cutting from.
medals = (43.6, 46.9, 50.6)
ground = -1.2
order = 375
width = 11


def build(b):
    """Super-G"""
    b.width(11)
    b.rail('lr')
    b.start(run=40)
    b.width(22.5)
    b.straight(64, rise=-6.8)
    b.width(26)
    b.arc(-99, 43, rise=-9.2)
    b.width(21.5)
    b.arc(60, 40, rise=-2.9)
    b.width(26)
    b.arc(117, 35.5, rise=-8.8)
    b.arc(-134, 28, rise=-7.1)
    b.cp()
    b.arc(99, 53.5, rise=-14.2)
    b.arc(-125, 77, rise=-30)
    b.arc(126, 40, rise=10)
    b.arc(36, 69.5, rise=-3.2)
    b.arc(-121, 80, rise=-26)
    b.arc(156, 44.5, rise=-24.5)
    b.arc(-29, 161, rise=-11.1)
    b.arc(60, 109.5, rise=-21.6)
    b.cp()
    b.arc(19, 211.5, rise=-8.2)
    b.arc(-108, 53.5, rise=-16.9)
    b.straight(66, rise=-7.3)
    b.arc(125, 58, rise=-26.7)
    b.cp()
    b.arc(-60, 106.5, rise=-20.7)
    b.arc(95, 52, rise=-12.4)
    b.arc(-95, 49, rise=-11)
    b.arc(-60, 40, rise=-2.9)
    b.arc(60, 77, rise=-10.8)
    b.arc(-60, 66.5, rise=-8.1)
    b.finish()
