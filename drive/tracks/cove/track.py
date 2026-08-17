"""Sandy Cove

A coast road down to the beach and out along the pier. Long.
"""

slug = "cove"
name = "Sandy Cove"
difficulty = 4
medals = (57.7, 60.6, 63.7)
ground = -1.2
order = 100
width = 12.0
origin = (0.0, 0.0, -20.0, 0.0)

# Sandy Cove's waterline, as a world Z. The track is authored against it rather
# than the other way round: a shoreline can only read as a coast if the road
# runs *along* it, so the outbound half is pinned to a band just inland of this
# and the pier is the one thing that crosses it. `SHORE_Z` is duplicated in the
# `cove` palette in trackmesh.js, which draws the water - and a test pins the
# two together, because a waterline that drifts inland puts the road in the sea.
SHORE_Z = 170.0
SHORE_AMP = 40.0
SHORE_WAVE = 420.0

def build(b):
    """Sandy Cove: a coast road along the water, out onto a pier, then inland.

    A ground track, so running wide costs you sand rather than your lap, which
    is the right penalty on a long one. The sea is scenery and is never in the
    collider, so the pier has nothing at all under it: run off that and you fall.

    The geography is the point and it constrains the layout. The outbound half
    runs along the beach with the water on its left, close enough to see the
    whole way; the pier is a loop out over it and back; then the road turns
    inland and the return half is dunes, which is what lets it have the hairpins
    a coast road cannot.
    """
    b.start(run=40)
    b.straight(70, rise=9.0)                     # up onto the low headland
    b.cp()

    # Along the top, bending out toward the water and back.
    b.arc(30, 66, rise=4.0).straight(52)
    b.arc(-38, 58, rise=-5.0).straight(44)
    b.cp()

    b.width(14.0)
    b.arc(44, 46, bank=14).straight(72, rise=-8.0)     # down onto the sand
    b.arc(-40, 52).straight(40)
    b.cp()

    # Two inlets cut into the beach.
    b.width(11.0)
    b.straight(30)
    b.jump(rise=2.8, gap=22, drop=0.0)
    b.straight(28)
    b.jump(rise=3.0, gap=25, drop=0.0)
    b.straight(34)
    b.cp()

    # The pier: out over open water and back. Narrow, flat, no barriers, and
    # the only part of the track with nothing whatever underneath it.
    b.width(9.5)
    b.arc(58, 34).straight(210)
    b.arc(-116, 28).straight(150)
    b.cp()
    b.arc(-58, 34).straight(46)                        # back onto the sand
    b.width(13.0)
    b.arc(52, 60).straight(58)
    b.cp()

    # Turn inland. Everything from here is dunes, so it can be tighter.
    b.width(11.0)
    b.arc(-128, 24).straight(48, rise=6.0)
    b.arc(96, 30, rise=5.0).straight(44)
    b.cp()

    b.width(14.0)
    b.arc(-62, 78, rise=6.0).straight(82)
    b.hump(3.4, 30).straight(30)
    b.cp()

    # Round the rocky point: three corners and no straight worth the name.
    b.width(10.5)
    b.arc(116, 26).straight(30)
    b.arc(-102, 24).straight(28)
    b.arc(128, 22).straight(40)
    b.cp()

    # A last drop to the sand for the third inlet, then the climb to the line.
    b.width(12.0)
    b.arc(-70, 48, rise=-11.0).straight(56)
    b.jump(rise=3.2, gap=26, drop=0.0)
    b.straight(36)
    b.cp()

    b.width(13.0)
    b.arc(88, 40, rise=8.0).straight(64, rise=6.0)
    b.arc(-66, 50).straight(42)
    b.finish()
