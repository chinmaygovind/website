"""Rainbow Road

Half-pipes in deep space, and almost no barriers. Do not fall.
"""

slug = "rainbow"
name = "Rainbow Road"
blurb = "Half-pipes in deep space, and almost no barriers. Do not fall."
difficulty = 5
ground = None
order = 120
width = 13.0
exposed = True

def build(b):
    """Rainbow Road: half-pipes, a loop, and almost nothing to stop you falling.

    The three long tracks are meant to be endurance tests, and this one takes
    its difficulty from exposure. It is deliberately the only track in the pool
    with barriers almost nowhere (see ``EXPOSED``): the pipes catch you where
    there are pipes, and everywhere else running wide is a fall.
    """
    b.start(run=44)
    b.straight(58)
    b.cp()

    # The one full half-pipe on the track: walls both sides, swing up either and
    # drop back in. Everywhere else the profile is one-sided (see below), which
    # is a corner you can lean on rather than a trough you sit in - so this is
    # the section that shows what the cross-section can do, and it is deliberately
    # the only one of its kind.
    b.pipe(5.5).straight(96).arc(-38, 95).straight(64)
    b.flat().straight(32)
    b.cp()

    # A fast left with a wall only on its outside, so the high line exists.
    b.pipe(4.8, floor=0.28, side="r").arc(-98, 48).flat().straight(38)
    b.cp()

    # Out over nothing.
    b.straight(34)
    b.jump(rise=3.6, gap=27, drop=0.0)
    b.straight(34)
    b.cp()

    # The loop keeps its rails - a loop without them is a fall at the top
    # rather than a corner, and that is not exposure, it is a broken corner.
    b.loop(radius=22.0, dir="r", w="lr")
    b.rail("").straight(44)
    b.cp()

    # A long right-hander banked up its outside - the left - so the high line
    # through it is a real choice rather than a wall to avoid.
    b.width(15.0)
    b.pipe(6.2, side="l").arc(76, 58).straight(72)
    b.flat().width(12.0).straight(34)
    b.cp()

    # Then the exposed part, with nothing either side of it.
    b.arc(-128, 23).straight(42)
    b.hump(4.2, 34).straight(30)
    b.cp()

    # A chicane out in the open, then a climb away.
    b.arc(58, 30).arc(-62, 28).straight(60, rise=9.0)
    b.arc(96, 40, rise=6.0).straight(52)
    b.cp()

    # The deepest wall on the track, and again only on the corner's outside. It
    # opens at the corner rather than on the straight before it, so the bank
    # arrives with the turn.
    b.width(14.0)
    b.straight(58)
    b.pipe(6.8, floor=0.26, side="r").arc(-84, 44).straight(66)
    b.flat().width(12.0).straight(34)
    b.cp()

    # The second loop, then the long exposed run home.
    b.loop(radius=24.0, dir="l", w="lr")
    b.rail("").straight(66, rise=-11.0)
    b.cp()

    b.arc(-142, 21).straight(48)
    b.arc(78, 54, rise=-8.0).straight(62)
    b.hump(3.8, 32).straight(34)
    b.cp()

    b.arc(92, 42).straight(56)
    b.arc(-64, 68).straight(34)
    b.finish()
