"""BOO!

Along the graveyard wall, in at the great door, and out through the roof - into
a crypt nobody meant you to find.
"""

slug = "boo"
name = "BOO!"
difficulty = 5
ground = None
order = 240
width = 14.0
rails = False
exposed = True
scenery = True

# No `origin`: the turtle starts at the world origin facing +X, which is
# straight down the chapel's own axis at the great door. **That is the whole
# reason the approach is shaped the way it is.** Coming in along the flank and
# turning in at the west front shows the building off better in a still and is
# worse to start a lap on, because from the grid you are looking at a wall.
# Here the first thing in frame is the door you are going to drive through, and
# the churchyard weaves either side of the axis without ever losing it.

# The chapel, in absolute world coordinates, and authored rather than derived.
# ---------------------------------------------------------------------------
# This is Costco's trade for Costco's reason: Python cannot draw a building and
# the JS cannot lay a road, and *the track is authored against the plan* - so
# the plan is stated once, here, and `palette.py` and `scenery.js` read it.
# Fitting a shell round whichever stations happen to be indoors is what the
# first version of this track did, and it is why it read as a tunnel instead of
# a chapel: a corridor grown out of the road is the same distance from the road
# everywhere, so the nave, the aisle and the gallery all looked identical.
#
# It is an aisled basilica with a square east end, which is what a chapel is:
#
#            z=-49  ......................................  outer wall
#            z=-44  +------------------------------+
#                   |   north aisle  (road, y=0)   |          aisle vault y=20
#            z=-24  +---||----||----||----||----||-+          arcade
#                   |                              |
#            z=  0  |   n a v e     (road, y=0)    |          nave vault y=42
#                   |                              |
#            z= 24  +---||----||----||----||----||-+          arcade
#            z= 44  |   south aisle / TRIFORIUM    |          road at y=24
#            z= 49  ......................................
#                     x=420      narthex     x=464      x=790  bay  x=847
#
# Every number below is a fact about the building. The road's job is to stay
# inside it, which `_fits` at the foot of this file checks on every load.
WEST_X = 420.0            # inner face of the west front: the great door
NARTHEX_X = 464.0         # narthex ends, the arcade begins
EAST_X = 790.0            # the arcade ends, the sanctuary bay begins
BACK_X = 847.0            # inner face of the east wall, behind the altar
NAVE_HW = 19.0            # nave clear half-width
COL_HW = 21.5             # arcade pier centres
AISLE_HW = 44.0           # inner face of the outer walls
NAVE_CEIL = 42.0          # underside of the nave vault
AISLE_CEIL = 20.0         # underside of the aisle vault, and so of the triforium
FLOOR_Y = 0.0             # the chapel floor, and the churchyard with it
EAVES = 36.0              # top of the outer walls, where the aisle roofs land.
                          # **This is the triforium's headroom and nothing else
                          # sets it.** At 32 the gallery road had six units of
                          # air over it and rendered as a tunnel: the deck is at
                          # 24, the roof lands 1.4 under the eaves, and the
                          # chase camera alone wants 4.3.
RIDGE = 62.0              # the nave roof's ridge. **26 units over the eaves
                          # across a 26.5 half-span is about 45 degrees, which
                          # is a roof.** At 50 it was 14 units over 26.5, drawn
                          # as seven steps - so each tread was 3.8 units wide
                          # and two deep, and from anywhere above the building
                          # it read as a flat-topped ziggurat rather than a
                          # pitch. Nothing drives above 26, so every number from
                          # here up is decoration and free to be the shape it
                          # should be.
TOWER_TOP = 80.0          # the parapet of the west tower, over the narthex
SPIRE_TOP = 148.0         # the tip of the needle on top of it. **Nothing up
                          # here is clipped by anything - there is no cloud
                          # layer on this track.** What looked like one is the
                          # sky dome's bright band at u=0.58, which the palette
                          # puts just over the horizon so that every silhouette
                          # on the track is read against it. Above that band the
                          # sky closes to a deep violet, so a spire drawn in
                          # shaded masonry is dark on dark and its top dissolves
                          # - which is a lighting problem and not a height one,
                          # and is why the needle is `lit`.
WALL_T = 5.0              # every wall's thickness, inside and out
DOOR_HW = 15.0            # half-width of the great west door. Wider than the
                          # road by seven, because the chase camera trails the
                          # car by up to 11.6 and swings out as it comes through.
DOOR_H = 19.0
TRIF_Y = 24.0             # the triforium deck, over the south aisle

# The crypt. Forty units under the nave, with nothing under *it*: `ground` is
# None and the palette's `below` is a void, so the floor of the world is the
# apron `scenery.js` lays round the road and the chapel, and the crypt is what
# is beneath the one bit of lid there is.
CRYPT_Y = -40.0
CRYPT_Z = -4.0            # its centreline, near enough under the nave's

# The two radii the plan is made of, and both are forced.
#
# SANCT is half the offset from the nave's centreline to the aisle's, because a
# 180-degree turn offsets by exactly 2R - so the aisle lands beside the nave
# with nothing measured twice, the same arithmetic as Costco's AISLE. It is also
# the floor on how wide the nave may be: at 17 the aisle centre is 34, and
# MIN_RADIUS is 12, so a narrower nave than this cannot be turned round at all.
# That is why the chapel is cathedral-scaled against the car rather than
# parish-scaled - real basilica proportions put this corner under the radius the
# car can drive.
SANCT = 17.0
NARTH = 20.0              # the two quarter-turns across the west gallery
AISLE_Z = -2.0 * SANCT    # the north aisle's centreline
TRIF_Z = -AISLE_Z         # and the triforium's, by symmetry
NARTH_CROSS = 2.0 * TRIF_Z - 2.0 * NARTH
assert NARTH_CROSS > 7.0, "the gallery crossing has to be longer than a station"

RAMP = 100.0              # up to the gallery. sqrt(330 * 24) = 89, so a hill
NAVE_W = 16.0
AISLE_W = 11.0
TRIF_W = 10.0


def build(b):
    """Down the flank, in at the door, out through the roof, under the floor.

    One building, seen five times: from outside along its whole length, then
    down the nave, then again through the arcade from the aisle, then from
    above off the gallery - and finally from *underneath*, because the crypt
    runs the length of it forty units down with the chapel's own floor as its
    ceiling. That is the whole of why this track reads and the first one did
    not: every beat is a named part of one place, in the order you would walk
    them.

    Three rules the layout exists to keep, all invisible until you drive it:

    * **Nothing indoors is ever over anything else.** The triforium runs above
      the *south* aisle, which the lap never touches, so there is no crossing
      inside the chapel at all. The one crossing on the track is the crypt
      under the nave, and that is forty units of clearance.
    * **Every wall is crossed square, on a straight**, because the chase camera
      trails the car by up to 11.6 units and comes through a doorway half a
      second late. Turning in an opening puts masonry between the two.
    * **The wall of death climbs.** A descending helix puts its own exit under
      its wrap, so dropping off the top lands on the road out and the whole
      three hundred and sixty degrees becomes optional - which
      `tools/cut_check.py` cannot see, because it ignores any chord with more
      than six units of height between its ends.
    """

    # --- the churchyard -----------------------------------------------------
    # Straight at the west front from the first frame, and every corner in it is
    # a *pair* - each S puts the car back on the chapel's axis pointing at the
    # door, so the building never leaves the windscreen and the lap still has
    # four corners before it gets there. A pad, then the lane narrows between
    # the tombs.
    #
    # **Dead flat, and the brow that used to be here is gone.** A `crest` up 7
    # and a `straight(48, rise=-7)` back down took the church out of the
    # windscreen for about a second, which read on paper as a reveal and drove
    # as a pitch upset in the one place the car is doing nothing but
    # accelerating. The whole churchyard is at FLOOR_Y now, which is also the
    # height of the chapel floor and of the apron, so there is not a step
    # anywhere between the line and the nave.
    b.start(run=34)
    b.straight(30)
    b.boost(22)
    b.straight(98)
    b.arc(-40, 52)
    b.arc(40, 52)                       # out round the yews...
    b.width(10.5)
    b.straight(30)                      # ...and through the gap in the tombs
    b.width(14.0)
    b.arc(40, 52)
    b.arc(-40, 52)
    b.straight(18)
    b.cp()

    # --- the nave -----------------------------------------------------------
    # In under the gallery, square on and at speed, and then something is
    # waiting in the dark. The bounce is past the narthex on purpose: the loft
    # over the door is at 20 and the nave vault is at 42, so this is the first
    # place in the building there is room to be thrown.
    b.width(NAVE_W)
    b.straight(46)
    # **A cap has to be a zone, not a point.** Hang time is fixed by
    # `BOUNCE_VEL`, so how far you reach scales with the speed you arrive with
    # and the touchdown moves about nineteen units across the range a car
    # actually turns up at - which is why `test_every_cap_is_wide_enough_to_
    # land_on` wants more than 18 units of it and a road at least 16 wide to
    # aim at. 16 units of pad measured 12.8 between its first and last station.
    b.bounce(26)                        # BOO
    b.straight(150)
    b.cp()
    b.straight(124)

    # --- the sanctuary ------------------------------------------------------
    # The turn behind the altar. 2 x SANCT is the aisle offset, which is the
    # only reason the aisle is where it is.
    #
    # **Flat, and that is not a taste call.** This turn is on the chapel's own
    # floor, and a banked cross-section sinks its inner edge by `hw * sin(bank)`
    # - eight units of half-width at nine degrees is 1.25 below the slab the
    # nave is standing on. So every lap scraped up onto the floor round the
    # inside of the sanctuary. Bank a corner indoors only if the floor under it
    # is banked too.
    b.arc(-180, SANCT)

    # --- the north aisle ----------------------------------------------------
    # Back west, narrow, between the piers and the outer wall, with the nave
    # flickering past through the arcade. Tight enough that the arcade is a
    # hazard rather than scenery.
    b.width(AISLE_W)
    b.straight(100)
    b.cp()
    b.straight(103)

    # --- up over the fallen bays --------------------------------------------
    # The aisle vault has gone at the west end, so the aisle is open to the
    # roof and the road climbs the rubble. 100 units for 24 of rise, against
    # the 89 that stops it being a hill and starts it being a kicker.
    b.width(TRIF_W)
    b.straight(RAMP, rise=TRIF_Y)

    # --- the west gallery ---------------------------------------------------
    # Across the organ loft, above the door you came in through, and it is the
    # best view in the building: the whole nave, end on, from over the top of
    # it. Both turns are in the open narthex, where there are no piers.
    b.arc(-90, NARTH)
    b.straight(NARTH_CROSS)
    b.arc(-90, NARTH)

    # --- the triforium ------------------------------------------------------
    # The gallery over the south aisle, open to the nave on the left the whole
    # way. No rail: the balustrade is collider geometry in `scenery.js`.
    b.straight(150)
    b.cp()
    b.straight(156)
    # The last bay, where the gallery opens out into the ruin at the east end -
    # and it has to open out, because a cap wants sixteen units of road to land
    # on and the triforium is ten. There is exactly room: the deck runs from the
    # balustrade at 21.5 to the outer wall at 44, so a 16-wide road on its
    # centreline leaves two and a half units each side.
    b.width(16.0)
    b.straight(18)
    b.bounce(26)                        # BOO again, and this one is the trap

    # --- out through the fallen gable ---------------------------------------
    # **The point of the second cap.** Without it this is a jump out of a hole
    # in the east wall onto the grass, which is where the track used to end and
    # was the dullest thing on it. With it you leave the gallery going up rather
    # than out, every bit of speed you had goes into height instead of distance,
    # and the ground you were expecting is sixty-four units further down than
    # the ground you get.
    b.gap(96, drop=FLOOR_Y - CRYPT_Y + TRIF_Y)

    # --- the crypt ----------------------------------------------------------
    # Under the chapel, with the chapel's own floor as the ceiling and nothing
    # at all underneath. Railed, because the only way off is into the void.
    b.width(13.0)
    b.rail("lr")
    b.straight(40)
    b.cp()
    b.arc(-180, 19, bank=12)            # back west, under the nave
    # Unrailed from here to the top of the helix. `test_barriers_are_opt_in`
    # caps an `exposed` track at a quarter of its stations, and railing the
    # whole crypt spent 26% of them on the two places a barrier is worth least:
    # a straight under a ceiling, and a wall of death, where `STICK_FORCE` is
    # already holding the car on and a kerb rail would only be something to
    # catch. It goes back on for the landings either side.
    b.rail("")

    # **Three esses west under the chapel, where 240 units of nothing used to
    # be.** That straight was 44% of the way through the lap and the one place
    # on the track where the only input is the throttle - it is where Chinmay's
    # lap was at t=45s and the complaint was that this whole section drags. An
    # arc pair `(-a, +a)` at radius R comes out on the entry heading, offset
    # `2R(1 - cos a)` sideways and `2R sin a` along, so alternating the sign of
    # the pairs walks the road west in the same corridor rather than wandering
    # off it - which matters here, because the wall's own cylinder is 80 units
    # across and sits at the end of this run.
    #
    # **The laterals have to cancel, and that is what sets the middle pair.** A
    # run of equal pairs with alternating signs does not come back to the
    # centreline unless there is an even number of them, and everything
    # downstream of here - the two walls, the hairpin, the cutting - is placed
    # by where this run ends. Three pairs, with the middle one turning the other
    # way and wide enough to undo both its neighbours: 2R(1 - cos 64) is twice
    # 2R(1 - cos 44), so left, right-twice, left comes out on the axis it went
    # in on and nothing after this had to move.
    #
    # 204 units against 240, so the section gets shorter as well as busier.
    # Radius 38 at the ~46 u/s the car arrives with is a corner you lift for and
    # do not brake for, which is the only kind worth putting six of in a row.
    b.straight(15)
    b.arc(-44, 38)
    b.arc(44, 38)
    b.arc(64, 38)
    b.arc(-64, 38)
    b.arc(-44, 38)
    b.arc(44, 38)
    b.straight(15)

    # The wall of death, and it is a full turn so it comes out heading the way
    # it went in. **It climbs**, for the reason in the docstring above. Half of
    # its circle is under the chapel floor and half is not, which is what the
    # hole in the churchyard is: the vault over this end of the crypt has gone,
    # so the helix carries you up out from under the building and back in.
    #
    # **Its three numbers are Playground's, and they are not free.** A 13-wide
    # road at radius 34 with an 80-unit roll-up was undrivable: the hold speed
    # on a wall is `sqrt(radius * STICK_FORCE)`, so a tight radius caps it low
    # and anything faster slides down the tilt, and the road's width is the
    # budget for that slide rather than generosity. 21 wide at radius 40 over a
    # 90-unit ramp is what the three walls on Playground were measured at.
    b.width(21.0)
    b.wall(360, 40, 84, ramp=90, rise=16)
    # **The run-out off the wall is unrailed, and that is not the usual
    # "barriers are opt-in" argument.** The road narrows from 21 to 13 at the
    # moment the roll-down hands the car back, and a car leaving a helix is
    # never straight - it comes off with whatever line the wall left it on, four
    # units of lateral it has to give back. Rails on a 13-wide exit turn that
    # into a wall on one side or the other, so the wall of death was being
    # failed by the road after it rather than by itself. The landing at the far
    # end still gets them.
    b.rail("")
    b.width(13.0)
    b.straight(60)

    # --- out from under -----------------------------------------------------
    # The 180 carries the crypt out from beneath the chapel's own floor and
    # into the collapsed cutting east of it, which is the only place the road
    # can climb back to the surface without coming up through the churchyard.
    # R is what puts it there: 2R has to clear AISLE_HW and the flight path of
    # the jump that got you down here, and nothing else sets it.
    b.arc(-180, 39, bank=14)
    b.straight(40)
    # **A checkpoint in the middle of the climb out, and it is the only thing
    # that closes the last cut.** The 180 and the two straights either side of
    # it are the road coming back east forty units down and then rising to meet
    # the churchyard, so a car that leaves the crypt roof can cross the whole
    # of it through open air - 471 units of road for a 266-unit chord, and no
    # geometry at any height stands in the way. A gate does, the way Rickety
    # Rails' loop exit does.
    b.cp()
    b.straight(30)

    # --- the second wall of death -------------------------------------------
    # **In the open cutting, and that is the only place on this track a second
    # one fits.** It was first put on the link straight between wall one and the
    # hairpin, which is wrong twice over. A 360 comes out on the heading it went
    # in on, so two of them on one straight run their ramps alongside each other
    # at the same height - 18 units apart in plan against 21 of combined
    # half-width, which `test_track_does_not_run_too_close_to_itself` reads as a
    # car trap and is one. And a helix under the nave has a ceiling: a station
    # on an 84-degree bank carries its road `hw * sin(84)` above its own
    # centreline, 10.4 units on a 21-wide one, so a second climb put the road
    # through the chapel's floor slab at y=-3.2 - inside the building, where
    # `_fits` cannot see it, because that only looks between the great door and
    # the gap.
    #
    # Here there is no lid at all. The cutting is east of the east wall and the
    # apron punches itself open around anything below y=-6, so the helix climbs
    # up out of the ground in the middle of the graveyard and back down into it.
    # **Turning the +z way on purpose**: that swings the cylinder to z=154 and
    # away from the chapel, whose aisles end at 49. The other hand would put
    # eighty units of wall under the south aisle.
    b.rail("")
    b.width(21.0)
    b.wall(360, 40, 84, ramp=90, rise=16)
    b.width(13.0)
    b.rail("lr")
    b.straight(30)

    b.rail("")
    # Eight of climb, not twenty-four: the second wall has done the other
    # sixteen. `test_hills_are_eased_but_kickers_are_not` wants about
    # sqrt(330 * rise) of run under a hill, which is 51 here, so 120 is a hill
    # with room to spare.
    b.straight(120, rise=8.0)           # up the rubble and out
    b.cp()

    # --- back through the graveyard -----------------------------------------
    # **The closing stretch, and it used to be two 52-degree corners at radius
    # 58 with straights between them.** Nothing in that is a decision you make:
    # 58 at the ~60 u/s you arrive with is a corner you hold flat, so the last
    # 230 units of the lap were a throttle pedal and a view. The note in
    # `docs/track-defects.md` says cutting the last movement off a track is
    # almost always free - this is the other answer to the same complaint, which
    # is to make it the part you actually lose the lap in.
    #
    # One fast corner to carry the speed off the rubble, and then **two
    # hairpins**, which is the only thing on this track you have to come almost
    # to a stop for. 16 and 15 against a pool that runs 13 to 26 at its
    # tightest, and against the 17 the sanctuary turns at indoors - and turning
    # 152 and 168 degrees rather than the 84 and 96 they replaced, so the road
    # doubles back on itself twice instead of jinking. That is the difference
    # between a corner you place the car for and a corner you *stop* for: at
    # the ~60 u/s you come off the rubble with, the first one is third gear and
    # a late apex or it is the graveyard.
    #
    # The tombs are already here - it is the one stretch of churchyard with
    # scenery standing in it - so the road threads them instead of sweeping
    # past, and this is where the two ghosts taken off the walls of death now
    # stand (`scenery.js`, the closing band): on a hairpin there is a line
    # round one, which is the whole difference from a helix.
    b.arc(-60, 46)
    b.straight(20)
    b.width(11.5)
    b.arc(152, 16)                      # hairpin right, round the mausoleum
    # **A gate between the two hairpins, and it is what makes them corners.**
    # A hairpin is the one shape you can ignore: the exit is thirty units from
    # the entry and pointing the other way, so with nothing between them the
    # quick line through here was across the grass in a straight line, and the
    # closing stretch was a chicane you did not have to take. `pre`/`post` are
    # cut to fit the straight that was already there rather than added to it -
    # `cp` lays its own run-up, and the default 17/17 would have put 34 units of
    # extra road between two corners whose whole point is that there is none.
    b.cp(pre=13, post=15)
    b.arc(-168, 15)                     # and straight back the other way
    b.straight(22)
    b.width(14.0)
    b.arc(64, 34)
    b.straight(26)
    b.finish()

    # **Guarded, because `build` is run against two different turtles.** The
    # track maker replays it through `tracks/moves.Recorder`, which records the
    # primitives as a document and lays no ribbon at all - so it has no `nodes`,
    # and an unguarded read of them is an AttributeError that takes the whole
    # recording path down. Same shape of trap as `Recorder` having no `pos`,
    # which is why Playground does its alignment arithmetic in constants.
    if getattr(b, "nodes", None):
        _fits(b.nodes)


# --- the one check that matters ------------------------------------------
# The plan above is absolute world coordinates, so a leg lengthened by twenty
# units fails nothing - it quietly puts the road through a wall, and the only
# symptom is driving into masonry. This is Costco's
# `test_the_warehouse_fits_inside_its_own_walls`, kept in the folder so it runs
# on every load rather than only under pytest.
INDOOR_PAD = 1.5          # how close a kerb may come to a wall it must not touch


def _fits(nodes):
    def bad(i, e, why):
        x, y, z = e["p"]
        raise ValueError(f"boo: station {i} at x={x:.0f} y={y:.0f} z={z:.1f} "
                         f"(hw {e['hw']:.1f}) {why}")

    # Which stations are indoors is the ribbon's own answer, not a bounding box:
    # the lap enters at the great door and leaves through the hole in the roof,
    # so it is everything from the first station past WEST_X up to the gap. A
    # box would also catch the flank run and the crypt, which pass the whole
    # building at z=-112 and forty units underneath it.
    i0 = next(i for i, e in enumerate(nodes) if e["p"][0] >= WEST_X
              and abs(e["p"][2]) < AISLE_HW)
    i1 = next(i for i, e in enumerate(nodes) if e.get("air") and i > i0)
    for i in range(i0, i1):
        e = nodes[i]
        x, y, z = e["p"]
        hw = e["hw"] + INDOOR_PAD
        if abs(z) + hw > AISLE_HW:
            bad(i, e, f"is through an outer wall at z=+-{AISLE_HW:.0f}")
        if NARTHEX_X <= x <= EAST_X:
            # Between the arcades: wholly in the nave, or wholly in one of the
            # two aisle bands. Anywhere in between is inside a pier, at any
            # height - the piers run from the floor to the nave vault, so the
            # triforium deck and the climb up to it are bound by them too.
            #
            # There is deliberately no headroom rule here. What is over the road
            # is not authored: `scenery.js` vaults each aisle only where the lap
            # does not run above it, so the bays the road climbs out of are
            # exactly the bays whose roof has fallen in. A number here would be
            # a third copy of that fact and the one nothing would keep in step.
            in_nave = -NAVE_HW <= z - hw and z + hw <= NAVE_HW
            in_aisle = COL_HW <= abs(z) - hw and abs(z) + hw <= AISLE_HW
            if not (in_nave or in_aisle):
                bad(i, e, "is inside the arcade piers")
