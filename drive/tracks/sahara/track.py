"""Sahara

Out across the dunes, in at the great pyramid's door, up through its dark heart
to the King's chamber, down the Grand Gallery and out of its face in one leap -
and back across the dunes to the flag.
"""

from tracks.builder import FREE

slug = "sahara"
name = "Sahara"
difficulty = 5
ground = -1.2
order = 340
width = 15.0
closed = True
scenery = True

# The grid is on the far side of the desert from the pyramid, so the lap is
# sand, then the pyramid, then sand. `origin` puts it there in world space, which
# is what keeps the pyramid where its plan below says it is.
origin = (636.95, 0.0, -347.74, 180.0)

# The pyramid, in absolute world coordinates, and authored rather than derived.
# Costco's trade for Costco's reason: the road is laid *against* the building,
# so the plan is stated once, here, and `palette.py` and `scenery.js` read it.
#
#   PYR_X, PYR_Z  the centre of the base. The door is on the west face, on the
#                 grid's own line, so the first thing in frame is the way in.
#   PYR_B         half the base. Three ramps climb the south inner wall and
#                 the faces lean in over them, so the top ramp's headroom is
#                 what sets this.
#   PYR_H         the apex: Giza's slope, near enough.
#   CHAMBER       the burial chamber the hall's road drives round and the
#                 secret lane drives through: (x0, x1, z0, z1, top).
#
# The inside of the lap, in order: the entrance tunnel, the hall round the
# chamber (the sliding stones, and the crack), the serpent tunnel, three ramps
# up the south wall into the dark, the north run over the chamber's roof, the
# King's chamber at the top, and the Grand Gallery down and out of the east
# face. Every road twelve wide inside the pyramid is a tunnel: `scenery.js`
# walls and roofs exactly those stations, so the width is the declaration.
PYR_X, PYR_Z = 330.0, 0.0
PYR_B = 200.0
PYR_H = 250.0
CHAMBER = (232.0, 316.0, -34.0, 36.0, 24.0)
TUNNEL_W = 12.0

# The shortcut, as two fractions of the lap: where it leaves the road and where
# it rejoins it. Read by `scenery.js` (the crawlway cut through the chamber) and
# by `app._boxes_for` (the one item box inside it), and both turn a fraction
# into a station the same way, `round(f * (n - 1))`. Re-measure after any change
# to the layout: a fraction is not a place.
LANE = (0.35541, 0.42631)


def build(b):
    """Sand, then the pyramid, then sand."""
    # --- the start, and the desert out to the pyramid ------------------------
    # Easy on purpose: fast sweepers and dunes, nothing to brake for, so the
    # pyramid is where the lap gets hard.
    b.start(run=30)
    b.straight(FREE(75))
    b.straight(90, rise=7)
    b.straight(90, rise=-7)
    b.arc(36, 90)
    b.arc(-36, 90)
    b.straight(60)
    b.cp()
    b.arc(-30, 90)
    b.arc(30, 90)
    b.straight(60)
    b.arc(-90, 100)
    b.straight(60)
    b.cp()
    b.straight(74)
    b.arc(-90, 90)
    b.straight(120)                             # the approach

    # --- the entrance tunnel --------------------------------------------------
    b.width(TUNNEL_W)
    b.straight(36)                              # in at the door
    # The pad points straight at the crack in the chamber wall: carried into
    # the lane it makes the sand pay, taken round the road it is just speed.
    # It ends a full braking distance before the hall's first corner, which is
    # the pool's rule for every pad (`test_boost`) - so the fork, where the
    # road turns and the lane does not, is 38 units on, exactly where it was.
    b.boost(16)
    b.straight(38)
    # --- the hall: round the burial chamber -----------------------------------
    b.width(18.0)
    b.arc(90, 24)
    b.straight(14)
    b.arc(-90, 24)
    # The narrows: an S through the hall's long side, tight and walled. The
    # three arcs are symmetric, so it comes out on the line it went in on and
    # the rest of the hall does not move.
    b.width(14.0)
    b.straight(14)
    b.arc(-35, 30)
    b.arc(70, 30)
    b.arc(-35, 30)
    b.straight(13.17)
    b.width(18.0)
    b.arc(-90, 24)
    b.straight(36)                              # the crack comes out here
    b.cp()
    # --- the serpent tunnel ---------------------------------------------------
    b.width(TUNNEL_W)
    b.arc(90, 22)
    b.arc(-28, 50)
    b.arc(28, 50)
    b.straight(14)
    b.width(15.0)
    b.arc(-180, 46)                             # out into the dark, and up
    # --- three ramps up the south wall ---------------------------------------
    # Each a single long climb, and the gates on the flat at the top of the
    # first and the last. A gate in the middle of a climb splits it into two
    # short hills, and a short hill's crest throws the car at full speed: an
    # eased rise crests at a radius of length^2 / (6 rise), and the car needs
    # v^2 / g - 85 flat out, 140 on a pad. 132 over 20 is 145.
    b.width(13.0)
    b.straight(132, rise=20)
    b.cp()
    b.arc(-180, 14)
    b.straight(166, rise=20)
    b.arc(180, 14)
    b.straight(132, rise=20)
    b.cp()
    # --- over the chamber's roof to the King's chamber ------------------------
    b.arc(-90, 26)
    b.straight(54)
    b.arc(-90, 26)
    b.width(16.0)
    b.straight(20)
    b.cp()                                      # the King's chamber
    b.straight(16)
    # --- the Grand Gallery, down and out --------------------------------------
    # No pad at the top: 65 u/s into the crest of a dive throws the car
    # however gentle the dive is. The pad is at the bottom, into the jump.
    b.width(TUNNEL_W)
    b.straight(16)
    b.straight(200, rise=-30)
    b.boost(14)
    b.width(15.0)
    b.straight(14)
    b.gap(56, drop=14.0)
    b.straight(14)
    b.straight(130, rise=-16)
    b.cp()

    # --- the desert home ------------------------------------------------------
    b.arc(-90, 70)
    b.straight(FREE(54), rise=3)
    b.cp()
    b.straight(84, rise=-3)
    b.arc(-90, 110)
    b.straight(146)
    b.finish_at_start()
    return b
