"""Costco Wholesale

Welcome to Costco!
"""

slug = "costco"
name = "Costco Wholesale"
difficulty = 3
medals = (44.6, 46.9, 49.3)
ground = -1.2
order = 140
width = 13.0
scenery = True

# Costco Wholesale
# ----------------
# The only track in the pool that goes *indoors*, so it is the only one whose
# layout is constrained by a building standing on it. Four numbers do that work
# and all four are read by `addBuilding` in trackmesh.js as well as by this
# function, which is why they are named here rather than written into the arcs:
#
#   AISLE       the Z spacing of the warehouse aisles. It is 2 x the hairpin
#               radius, because a 180-degree hairpin is exactly what puts the
#               next aisle beside the last one - so the racking between them has
#               `AISLE - ROAD` units to live in and nothing has to be measured
#               twice. `self_proximity` only needs 16 here (two half-widths plus
#               CROSS_CLEAR); the rest is room for the shelves, which is a
#               separate budget the check knows nothing about.
#   DECK        the rooftop car park's surface height. It passes over the whole
#               warehouse floor, so it alone sets `gate_ceiling`: the ceiling
#               comes out at DECK - GATE_CEIL_MARGIN.
#   RAMP        how long the travelator takes to climb to DECK. A hill needs
#               `length >= sqrt(330 * rise)` or it stops being a hill and starts
#               launching the car - see `test_hills_are_eased_but_kickers_are_not`.
#   HAIRPIN     the aisle-end radius. 12 is the floor the drivability test sets.
AISLE = 28.0
DECK = 19.0
RAMP = 86.0
HAIRPIN = AISLE / 2.0

# The warehouse shell, in absolute world coordinates, and that is deliberate.
#
# `addBuilding` in trackmesh.js draws the walls and the roof from these four
# numbers and cuts a doorway wherever the road crosses one - so they are two
# copies of one fact, which is the same trade Sandy Cove's waterline makes and
# it is the right one for the same reason: Python cannot draw a building and the
# JS cannot lay a road, and *the track is authored against the shell*. Deriving
# the box from whichever stations happen to be indoors instead sounds tidier and
# is circular - the wall position then depends on the set of stations you are
# using to decide where the wall is, and a doorway lands mid-descent or halfway
# round a corner depending on the margin. `test_the_costco_shell_agrees_with_the_track`
# holds the two copies together, exactly as `test_the_waterline_agrees_with_the_track`
# does for the sea.
#
# Everything indoors has to fit: the aisles, both ramps and the whole rooftop
# deck. `test_the_warehouse_fits_inside_its_own_walls` is what checks it, and
# what will fail if a leg is lengthened past the wall it is meant to stop short of.
SHELL_X = (250.0, 490.0)
SHELL_Z = (-110.0, 78.0)
# The underside of the roof. Two things bound it and they pull opposite ways.
# The chase camera rides 4.3 units over the car, so anything under about 7 puts
# the roof through the lens. And the rooftop deck is road at DECK, which the roof
# has to clear by enough that `addBuilding`'s "is the road punching through here"
# test can tell the travelator coming *through* the roof apart from the deck
# merely passing *over* it - much under 3 and it cannot, so the whole deck tears a
# hole in the roof it is supposed to be standing on.
#
# So the two move together: the roof cannot be raised without raising the deck
# over it, and raising the deck lengthens both travelators, because a hill needs
# `length >= sqrt(330 * rise)` before it stops being a hill. 15 and 19 leaves the
# 4 units of gap the test needs and gives the shed some height off the car park.
SHELL_CEIL = 15.0

def build(b):
    """In the front doors, round the aisles, up the travelator to the roof.

    Point-to-point, like every track here but Spa: the lap starts in the car
    park, spends its middle inside the warehouse, and finishes back outside. The
    building itself is not authored here at all - `addBuilding` fits it around
    whichever stations fall inside `building.inside`, so the shell can never end
    up somewhere the road is not.

    Two rules the layout exists to obey, both of them about things that are
    invisible until you drive it:

    * **Every wall is crossed square, on a straight.** The chase camera trails
      the car by up to 11.6 units, so it goes through a doorway about half a
      second after the car does. Straight through a wide opening and it follows
      the car through; turning in the doorway puts a wall between the two.
    * **Nothing passes over anything else below DECK.** The deck is the only
      legitimate crossing on the track, and it clears the floor by the whole of
      DECK. Both ramps therefore climb along rows the deck does not reach.
    """

    # --- the car park -------------------------------------------------------
    # Wide and flat, and it opens with a sweep rather than a straight so the
    # grid has a first corner to put pole on the inside of.
    b.start(run=70)
    b.arc(-52, 46)
    b.straight(44)
    b.cp()
    b.arc(52, 46)
    # Square up on the doors, and stay square: this is the run the camera has to
    # follow the car through the west wall on.
    b.straight(60)

    # --- in through the front doors -----------------------------------------
    # Narrower inside than the lot road - a vestibule, and it makes the doorway
    # read as a doorway rather than as a gap the track happens to pass through.
    # SHELL_X[0] falls in the middle of this straight, which is the whole point:
    # the camera trails the car by 11.6 units and has to come through the same
    # opening a moment later.
    b.width(11.0)
    b.straight(40)
    b.cp()                                  # the membership card check

    # --- the warehouse floor ------------------------------------------------
    # Four aisles, marching north, each one a hairpin from the last. The road
    # changes width down them because a Costco aisle does: wide where the pallets
    # are stacked out, tight where the racking closes in.
    # The bump sits at the far end of the aisle rather than the near one, and
    # deliberately: the rooftop deck's northbound leg crosses this aisle, and
    # anything standing 2.6 units up under it is what sets `gate_ceiling` for the
    # whole track. Out here it is clear of that leg and the ceiling stays at
    # DECK - GATE_CEIL_MARGIN.
    b.straight(76)
    b.hump(2.6, 24)                         # a loading ramp across the aisle
    b.straight(32)
    b.arc(178, HAIRPIN)                     # end of aisle one

    b.width(9.5)
    b.straight(64)
    b.cp()
    b.straight(68)
    b.arc(-178, HAIRPIN)                    # end of aisle two

    # Aisle three is the short one, and it has to be: it runs east, and a 178
    # degree hairpin bulges a whole radius past the leg that fed it. Give this
    # leg the length the west-running ones get and the turn at the end of it
    # leaves the building through the east wall.
    b.width(12.0)
    b.boost(16)                             # a travelator down the middle aisle
    b.straight(50)
    b.hump(2.2, 22)
    b.straight(48)
    b.arc(178, HAIRPIN)                     # end of aisle three

    b.width(10.5)
    b.straight(66)
    b.cp()
    b.straight(70)
    b.arc(-178, HAIRPIN)                    # end of aisle four

    # --- the food court, and the travelator up ------------------------------
    # The far north row, which is the one row of the building with no aisle in
    # it - so the travelator can climb the whole of DECK without ever passing
    # over road. A pad out of a slow corner is the one place a pad belongs, and
    # this one feeds the ramp.
    b.width(13.0)
    b.boost(18)
    b.straight(18)
    # Up to the roof. Long and shallow, which is both what the hill rule wants
    # (`length >= sqrt(330 * rise)`) and what a car travelator actually is.
    b.straight(RAMP, rise=DECK)

    # --- the rooftop car park -----------------------------------------------
    # Wide, banked and open, and it stays inside SHELL_X/SHELL_Z because it is
    # standing on the roof. Round the outside first - down the east side, then
    # west along the south - both of them clear of the aisles below, and then the
    # one leg that matters: back north straight over the top of them. The aisles
    # run east to west, so this is the only heading that crosses them, and every
    # crossing on the track is made here at the full DECK of clearance.
    b.width(14.0)
    b.arc(-90, 28, bank=8)                  # off the ramp, down the east side
    b.straight(60)
    b.arc(-90, 30, bank=8)                  # west along the south side
    b.straight(96)
    b.arc(-90, 32, bank=8)                  # and back north, over the aisles
    b.straight(54)
    b.cp()

    # --- down the exit ramp -------------------------------------------------
    # Turns east off the deck and comes down the north row, which is the row the
    # travelator climbed and so the row with nothing else in it. Landing inside
    # the shell matters: a descent that reached the wall still falling would put
    # the doorway three units up in the air.
    b.arc(-90, 30)
    b.width(12.0)
    b.straight(RAMP, rise=-DECK)

    # --- the checkouts, and out ---------------------------------------------
    # The tightest road on the track, and a chicane rather than a straight,
    # because a till you can take flat out is not a till.
    b.width(8.5)
    b.arc(22, 34)
    b.arc(-22, 34)
    b.cp()                                  # the receipt check, on the way out
    b.width(11.0)
    b.straight(40)                          # square out through the east wall

    # --- back into the car park --------------------------------------------
    # South into the far end of the same lot, down the building's east flank.
    b.width(13.0)
    b.arc(-70, 44)
    b.straight(130)
    b.finish()
