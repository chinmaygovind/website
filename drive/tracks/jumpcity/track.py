"""Jump City

Four gaps with nothing under them. Launch, land, repeat.
"""

slug = "jumpcity"
name = "Jump City"
blurb = "Four gaps with nothing under them. Launch, land, repeat."
difficulty = 4
medals = (20.8, 21.9, 23.0)
ground = None
order = 60
width = 12.0
rails = True

def build(b):
    """Gaps with nothing under them. Launch, land, repeat."""
    b.start(run=54)
    b.jump(rise=2.6, gap=20, drop=0.0, land=34)
    b.cp()
    b.arc(-84, 30).straight(50)
    b.jump(rise=3.4, gap=26, drop=5.0, land=38)
    b.cp()
    b.arc(80, 46).straight(52, rise=7.0)
    b.jump(rise=2.2, gap=22, drop=10.0, land=40)
    b.cp()
    b.arc(96, 24).straight(52)
    b.jump(rise=3.0, gap=24, drop=4.0, land=36)
    b.cp()
    b.arc(-64, 56).straight(30)
    b.arc(-88, 36).straight(26)
    b.finish()
