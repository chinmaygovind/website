"""Cloudbreak

Threaded between rock spires, miles above the cloud.
"""

slug = "pillars"
name = "Cloudbreak"
difficulty = 5
medals = (49.8, 52.3, 55.0)
ground = None
order = 110
width = 11.5
exposed = True

def build(b):
    """Cloudbreak: threaded between rock spires, a long way above anything.

    The spires are scenery (see the ``pillars`` world in trackmesh.js) - they
    are placed clear of the road, so what actually catches you out here is the
    elevation and the corner radii, not hitting one.

    Barriers are the exception rather than the rule here (it is in ``EXPOSED``).
    Railing the whole thing made it a bobsleigh run: on a track whose entire
    subject is how far down the ground is, a wall along every corner is the one
    thing that takes the height away. So they are kept for the three places
    where going off is not a mistake you could have avoided - the two jump
    landings, where you arrive with no steering, and the narrow bridge, which is
    barely wider than the car.
    """
    b.start(run=40)
    b.straight(56, rise=7.0)
    b.cp()

    b.arc(-92, 38, rise=5.0).straight(44)
    b.arc(104, 30, rise=-3.0).straight(36)
    b.cp()

    b.width(13.0)
    b.arc(-74, 56, bank=17).straight(70, rise=10.0)
    b.cp()

    b.width(10.5)
    b.arc(148, 18, rise=4.0).straight(40)              # hairpin between spires
    b.arc(-136, 20).straight(58, rise=-8.0)
    b.cp()

    # Across the gorge. Rails on the landing only: you come down with no
    # steering authority, which is not a mistake, it is the jump.
    b.straight(28)
    b.jump(rise=4.0, gap=30, drop=6.0)
    b.rail("lr").straight(36)
    b.rail("").cp()

    b.width(13.5)
    b.arc(88, 52, rise=-6.0).straight(58)
    b.hump(4.4, 34).straight(30)
    b.cp()

    b.arc(-116, 26).straight(60, rise=-9.0)
    b.arc(96, 34).straight(40)
    b.cp()

    # A long banked spiral down between the spires.
    b.width(12.5)
    b.arc(-132, 42, rise=-14.0, bank=19).straight(54, rise=-6.0)
    b.arc(-118, 38, rise=-11.0, bank=17).straight(52)
    b.cp()

    # The narrow bridge - 9.5 wide, so it keeps its rails - and the second gorge.
    b.width(9.5)
    b.rail("lr").straight(72)
    b.arc(86, 28).straight(34)
    b.rail("").jump(rise=3.6, gap=28, drop=0.0)
    b.rail("lr").straight(34)
    b.rail("").cp()

    b.width(13.0)
    b.arc(-98, 44, rise=7.0).straight(66, rise=8.0)
    b.hump(4.0, 32).straight(30)
    b.cp()

    b.width(11.5)
    b.arc(-68, 60, rise=-5.0).straight(62)
    b.arc(74, 44).straight(38)
    b.finish()
