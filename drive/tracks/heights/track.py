"""Hairpin Heights

A climb made of hairpins, then a fast plunge back down.
"""

slug = "heights"
name = "Hairpin Heights"
difficulty = 4
medals = (19.5, 20.5, 21.6)
ground = None
order = 50
width = 11.0
rails = True

def build(b):
    """A climb out of hairpins, then a fast plunge back down."""
    b.start(run=36)
    b.straight(54, rise=8.0)
    b.cp()
    b.arc(158, 17, rise=6.0).straight(50, rise=7.0)
    b.cp()
    b.arc(-150, 19, rise=6.0).straight(44, rise=5.0)
    b.cp()
    b.width(13.0)
    b.arc(90, 36).straight(78, rise=-18.0)
    b.hump(3.8, 30).straight(28)
    b.cp()
    b.arc(-72, 52, rise=-6.0).straight(30)
    b.arc(-96, 28).straight(30)
    b.arc(64, 44).straight(24)
    b.finish()
