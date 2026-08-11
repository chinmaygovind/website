"""Figure Eight

Short, and it crosses over itself.
"""

slug = "eight"
name = "Figure Eight"
blurb = "Short, and it crosses over itself."
difficulty = 2
ground = -1.2
order = 80
width = 12.0

def build(b):
    """Short, and it really does cross over itself."""
    b.start(run=40)
    b.straight(40)                      # this is the road it comes back over
    # Three quarters of a turn, climbing. Ending a 270 degree arc of radius R
    # puts you one radius back down the road you came in on, heading across it -
    # which is what makes the crossing happen rather than hoping for it.
    b.arc(270, 34, rise=14.0)
    b.hump(3.4, 30).straight(24)        # over the deck, above the start straight
    b.cp()
    b.straight(30)
    b.straight(68, rise=-14.0)          # back down to ground level
    b.arc(-98, 24).straight(44)
    b.cp()
    b.arc(-86, 52).straight(54)
    b.cp()
    b.arc(94, 38).straight(28)
    b.finish()
