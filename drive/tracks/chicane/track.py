"""Chicane Park

Quick direction changes and two very slow hairpins.
"""

slug = "chicane"
name = "Chicane Park"
blurb = "Quick direction changes and two very slow hairpins."
difficulty = 2
ground = -1.2
order = 20
width = 11.0

def build(b):
    """Direction changes, two proper hairpins, all on the ground."""
    b.start(run=44)
    b.arc(-42, 30).arc(48, 26).straight(18)
    b.cp()
    b.arc(150, 15).straight(40)
    b.cp()
    b.width(13.0)
    b.hump(3.4, 30).straight(24)
    b.arc(-64, 56).arc(58, 48).straight(26)
    b.arc(-88, 30).straight(22)
    b.cp()
    b.width(10.0)
    b.arc(-165, 14).straight(46)
    b.arc(64, 40).straight(24)
    b.finish()
