"""Snowy Night

Adopted from a community track by Brumm.
"""

slug = 'snowynight'
name = 'Snowy Night'
difficulty = 1
# Derived from the ribbon when this was adopted, not cut from a board.
# Re-cut with tools/set_medals.py once it has one worth cutting from.
medals = (28.2, 30.3, 32.8)
ground = -1.2
order = 370
width = 11


def build(b):
    """Snowy Night"""
    b.width(11)
    b.rail('')
    b.start(run=40)
    b.jump(2.6, 20, land=34)
    b.arc(-60, 40, rise=5.4)
    b.cp()
    b.straight(40, rise=3)
    b.straight(40, rise=3.2)
    b.arc(75, 38.5, rise=0.8)
    b.cp()
    b.boost(48, rise=-6.4)
    b.straight(22)
    b.gap(18, drop=4)
    b.straight(20)
    b.arc(119, 12)
    b.cp()
    b.hump(0.2, 4)
    b.arc(-147, 12)
    b.straight(15)
    b.arc(156, 12)
    b.cp()
    b.arc(-60, 40, rise=-1)
    b.arc(95, 37, rise=3.8)
    b.straight(40)
    b.boost(127)
    b.jump(2.6, 60, drop=5, land=34)
    b.arc(-110, 18)
    b.cp()
    b.arc(-126, 27)
    b.cp()
    b.arc(-49, 77)
    b.finish()
