"""Spiral Ascent

A long banked spiral to the top and a dive down the outside.
"""

slug = "spiral"
name = "Spiral Ascent"
blurb = "A long banked spiral to the top and a dive down the outside."
difficulty = 4
ground = None
order = 70
width = 11.0
rails = True

def build(b):
    """A long climbing spiral, then a dive down the outside of it."""
    b.start(run=40)
    b.arc(180, 42, rise=14.0, bank=12)
    b.cp()
    b.straight(30)
    b.arc(180, 32, rise=13.0, bank=14)
    b.cp()
    b.straight(28)
    b.width(13.0)
    b.arc(120, 26, rise=5.0)
    b.straight(56, rise=-9.0)
    b.cp()
    b.arc(-140, 48, rise=-16.0, bank=16)
    b.straight(50, rise=-7.0)
    b.cp()
    b.arc(88, 38).straight(26)
    b.hump(4.0, 32).straight(26)
    b.arc(-60, 54).straight(26)
    b.finish()
