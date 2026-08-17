"""Skyline Sprint

Up and over a floating skyline. Miss a corner and you fall.
"""

slug = "skyline"
name = "Skyline Sprint"
difficulty = 1
medals = (18.0, 18.9, 19.9)
ground = None
order = 30
width = 11.0
rails = True

def build(b):
    """Elevation over a floating track. Run wide and you fall."""
    b.start(run=34)
    b.straight(56, rise=9.0)
    b.cp()
    b.arc(-80, 34, rise=4.0).straight(26)
    b.arc(70, 42, rise=-6.0).straight(22)
    b.cp()
    b.width(13.0)
    b.arc(95, 28, bank=16).straight(52, rise=8.0)
    b.hump(4.6, 32).straight(26)
    b.cp()
    b.arc(-72, 54, rise=-12.0).straight(26)
    b.width(10.0)
    b.arc(-104, 22).straight(48, rise=-5.0)
    b.cp()
    b.arc(88, 46).straight(34)
    b.finish()
