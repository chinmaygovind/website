"""Twin Loop

Two full loops that step out sideways. Carry speed in.
"""

slug = "twist"
name = "Twin Loop"
difficulty = 3
medals = (19.4, 20.4, 21.5)
ground = None
order = 40
width = 11.0
rails = True

def build(b):
    """Two full loops, each stepping out to one side. Carry speed in."""
    b.start(run=70)
    b.loop(radius=20.0, dir="l")
    b.straight(30)
    b.cp()
    b.arc(-92, 24).straight(30)
    b.hump(4.2, 32).straight(26)
    b.cp()
    b.loop(radius=23.0, dir="r")
    b.straight(36)
    b.arc(104, 30).straight(26)
    b.cp()
    b.width(13.0)
    b.arc(-62, 56).straight(44)
    b.arc(-84, 38).straight(28)
    b.arc(58, 46).straight(26)
    b.finish()
