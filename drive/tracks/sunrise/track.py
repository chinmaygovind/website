"""Sunrise Circuit

Wide, flowing and forgiving - the one to learn the car on.
"""

slug = "sunrise"
name = "Sunrise Circuit"
difficulty = 1
medals = (16.4, 17.3, 18.2)
ground = -1.2
order = 10
width = 13.0

def build(b):
    """Wide, flowing, on the ground. The one to learn the car on."""
    b.start(run=44)
    b.arc(72, 58).straight(30)          # fast, barely a lift
    b.cp()
    b.arc(-100, 30).straight(38)        # third gear, hook it in
    b.width(11.0)
    b.arc(-66, 44).straight(24)
    b.cp()
    b.arc(84, 26).straight(20)          # the slow one
    b.width(14.0)
    b.hump(4.0, 34).straight(26)        # over the brow, both wheels off

    b.arc(64, 52, rise=6.0)             # long sweep, climbing
    b.straight(46, rise=-6.0)
    b.cp()
    b.arc(-58, 38).straight(42)
    b.arc(-96, 34).straight(30)
    b.finish()
