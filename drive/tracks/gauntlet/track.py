"""The Gauntlet

Loops, gaps, hairpins, elevation. Everything, twice over.
"""

slug = "gauntlet"
name = "The Gauntlet"
difficulty = 5
medals = (35.2, 37.0, 38.9)
ground = None
order = 90
width = 12.0
rails = True

def build(b):
    """Loops, gaps, hairpins, elevation. Everything, and twice as long."""
    b.start(run=52)
    b.loop(radius=20.0, dir="l")
    b.straight(34)
    b.cp()
    b.arc(-78, 42, rise=8.0).straight(32)
    b.arc(66, 30).straight(24)
    b.hump(4.4, 34).straight(26)
    b.cp()
    b.jump(rise=3.0, gap=24, drop=6.0, land=38)
    b.cp()
    b.arc(162, 16).straight(56, rise=-9.0)
    b.cp()
    b.width(14.0)
    b.arc(-84, 54, bank=14).straight(46)
    b.loop(radius=22.0, dir="r")
    b.straight(36)
    b.cp()
    b.arc(96, 26).straight(48, rise=6.0)
    b.jump(rise=2.4, gap=20, drop=8.0, land=34)
    b.cp()
    b.arc(-152, 18).straight(30)
    b.hump(3.6, 30).straight(24)
    b.width(11.0)
    b.arc(78, 46).straight(38)
    b.cp()
    b.arc(-90, 34).straight(30)
    b.finish()
