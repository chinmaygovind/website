"""Rickety Rails

A mine-cart line, driven. Down the drift, over the winze, and back up the
haulage way - with nothing under any of it.
"""

slug = "railway"
name = "Rickety Rails"
difficulty = 5
# Set by hand rather than cut by `tools/set_medals.py`, for Tokyo Drift's reason:
# there is no board to cut from yet, and the tool's fallback derivation makes a
# poor standard - it is out by 0.744 to 0.888 of itself depending on the track.
#
# Gold at 60.0 against a 69.93s ideal is 0.858 of it, which sits in the 0.77-0.90
# band every record actually set on this site falls in, and toward the hard end
# of it - which is right for the pool's only difficulty-5 point-to-point with no
# barriers. Silver and bronze are 2 and 3 seconds off rather than the tool's two
# 5% steps: on a seventy second lap 5% is three and a half seconds, and these
# three want to be one standard in three steps rather than three standards.
# Re-cut once the board is deep enough.
medals = (60.0, 62.0, 65.0)
ground = None
order = 200
width = 12.0
rails = False
exposed = True
scenery = True

# The road is a mine-cart trestle, and that is why this track has no ground.
#
# Wario's Gold Mine is the reference and the thing to take from it is not the
# palette, it is the *structure*: the road there is a plank deck on stilts over
# a hole. `buildTrack` already draws a slim leg under every station of a
# groundless track, so a `ground = None` track in a cave is a trestle for free.
# What `scenery.js` builds is the hole - a floor a long way under the trestles
# and a roof over them, both envelopes of cones off the ribbon, so neither can
# reach the road whatever the layout does.
#
# **It is `exposed` rather than railed, and that is the whole character of it.**
# The first version had `rails = True`, which is the pool's default for a
# floating track and which put a side beam down 96% of the lap - a bobsleigh
# run, and boring to drive precisely because the barrier answers the only
# question a corner asks. Cloudbreak's note in `docs/tracks-and-geometry.md` is
# about exactly this trade and it applies twice as hard here, because the thing
# under the road is a ravine that goes black: railing it hides the drop, and the
# drop is the track. `test_barriers_are_opt_in` holds the claim to under 25% of
# stations; this runs at about 4%, and every one of them is a place you arrive
# with no steering.

# How far the winze drops.
WINZE = 28.0


def build(b):
    """A mine, driven the way a mine is dug: down the seam and back out.

    Six movements. The elevation is what strings them together rather than the
    corners - the lap falls to the floor of the sump and climbs back out - but
    what makes it *hard* is that almost none of it is walled and the floor is
    forty-six units down and unlit.

    **Where the difficulty is spent.** Three hairpins under radius 20 and the
    tightest corner in the pool at 14, all of them either downhill or arrived at
    off the fastest thing on the track; two half-pipes on the *inside* of
    corners, which are a line to take rather than a wall to lean on; and one
    twenty-eight unit fall onto the level below. The only barriers are the two
    jump landings.

    **The descent is spent in two very different currencies.** The first sixty
    units are given away a few at a time, on corners you brake for; the last
    twenty-eight go at once, off a pad and a kicker into the winze.

    **The sump is the tightest thing on the track and it is at the bottom on
    purpose.** You arrive with the most speed you have carried all lap, off the
    longest drop, and the road immediately goes to 10.5 units wide with a
    15-radius hairpin in it, over a hole, with nothing at the edge.
    """
    # --- the adit -----------------------------------------------------------
    # In through the mouth, and it starts working immediately. The first version
    # opened with seventy units of straight and two gentle sweeps, which reads
    # as the track not having started yet - so this is a chicane at radius 20
    # inside the first two hundred units, in the one place on the track where
    # the roof is low enough to see it coming.
    b.start(run=44)
    b.straight(48, rise=-4)
    b.cp()
    b.arc(-64, 34, rise=-4)
    b.straight(40, rise=-4)
    b.arc(88, 20, rise=-2)
    b.straight(36, rise=-4)
    b.arc(-72, 26, rise=-3)
    b.straight(44, rise=-5)

    # --- the gallery --------------------------------------------------------
    # The worked-out seam. Wide and fast, and the half-pipe here is on the
    # **inside** of the right-hander rather than the outside.
    #
    # That is the opposite of the pool's other three, and it is a different
    # thing to drive. `pipe(side='r')` on a right turn curls the edge the car is
    # being thrown *away* from, so it is not a wall that catches a wide moment -
    # it is a bank on the apex you can drop into and come off carrying speed, or
    # climb too far up and lose the exit. A line to take rather than a wall to
    # lean on.
    #
    # Then the first real brake point on the track: a 17-radius hairpin, taken
    # downhill, with the pipe's exit feeding straight into it.
    b.width(13.0)
    b.straight(56, rise=-5)
    b.pipe(4.6, 0.40, side="r")
    b.arc(96, 46, rise=-6)
    b.flat()
    b.straight(40, rise=-4)
    b.arc(-150, 17, rise=-5)
    b.straight(46, rise=-4)
    b.cp()
    b.arc(58, 62, rise=-4, bank=6)
    b.arc(-64, 40, rise=-5)
    b.straight(42, rise=-4)

    # --- the winze ----------------------------------------------------------
    # A winze is a shaft sunk from one level to the next. The trestle simply
    # stops: pad, kicker, sixty-six units of nothing, and the road again
    # twenty-eight units down on the level below.
    #
    # The explicit `bow` is what stops `laptime.speed_profile` braking at the
    # lip. `gap`'s default is capped at four units, which for a twenty-eight
    # unit fall meets the kicker's exit at a real kink in the tangent, and the
    # model reads a kink as a tight corner. See `docs/tracks-and-geometry.md`.
    b.boost(28)
    b.crest(2.6, 32)
    b.gap(66, drop=WINZE, bow=_bow(66, WINZE, 2.6 / 32))
    # **Railed, and one of only two places that is.** You arrive here with no
    # steering, off the longest drop on the track, at a speed that depends
    # entirely on how the corner before the pad went - `test_every_gap_is_
    # clearable` says the ballistics reach the far side and says nothing about
    # where a fast entry actually touches down. Ninety-six units of landing so
    # the gate is past even a no-lift approach, and beams on it so an exposed
    # track does not take the lap for a jump you cleared.
    b.rail("lr")
    b.straight(70)
    b.rail("")
    b.straight(20)
    b.cp()

    # --- the sump -----------------------------------------------------------
    # The bottom of the mine, and the tightest driving in the pool. Two hairpins
    # round rock pillars with an ess between them, on the narrowest road here,
    # over the deepest part of the ravine, with nothing at the edge of it. The
    # 14 is the tightest corner in the pool by a clear margin - 12 is the floor
    # `test_corner_radii_are_varied_and_drivable` sets - and it is first gear.
    b.width(10.5)
    b.arc(-156, 15)
    b.straight(50)
    b.arc(52, 26)
    b.arc(-48, 22)
    b.straight(36)
    b.cp()
    b.arc(164, 14)
    b.straight(38)

    # --- the plank crossing -------------------------------------------------
    # Seven units of road over the deepest part of the ravine, with nothing at
    # the edge of it. The pool's narrowest is the Costco's 8.5 checkout run and
    # that is a corridor with walls; this is a plank over a hole, and at 7 it
    # leaves 2.5 units either side of a car that is 1.9 wide.
    #
    # **It bends, and that is the whole point.** A thin straight is a test of
    # nerve and nothing else - you point the car and hold it. Putting a 54-radius
    # bend in the middle makes it a test of placement, because the width that is
    # left is smaller than the line's own error, and it has to be driven rather
    # than committed to. Gentle enough to be taken at speed by somebody who
    # looked at it, which is what stops it being a lottery.
    b.width(7.0)
    b.straight(26)
    b.arc(30, 54)
    b.straight(26)

    b.width(10.5)
    b.arc(-44, 28)
    b.arc(50, 24)
    b.straight(40)
    b.cp()

    # --- the crystal vault --------------------------------------------------
    # The big room, and the one place you get a rest: a hundred and four degrees
    # at radius 88, banked, taken flat, with a banked wall up the **outside**.
    # That is the other kind of pipe and it is here for the contrast - outside of
    # a right-hander is the left, because that is the way the car is being
    # thrown, so this one *is* a catch and the two in the drifts are not.
    #
    # It is also where `scenery.js` puts the daylight shaft, so it is the only
    # corner on the track lit by anything but a work lamp - and then it is paid
    # for immediately with a 24-radius left out of the far side.
    b.width(13.5)
    b.straight(60, rise=4)
    b.pipe(5.0, 0.38, side="l")
    b.arc(96, 80, rise=7, bank=8)
    b.flat()
    b.straight(44, rise=4)
    b.cp()

    # A runaway cart's loop, in the one room with the ceiling for it. The vault's
    # roof stands 52 units over the road (see `HEAD` in `scenery.js`) and a
    # radius-23 loop is 46 of them, so this is the only place on the track it
    # fits at all.
    #
    # **Radius is not a free choice**: over the top the road curves away and only
    # gravity plus `STICK_FORCE` hold the car on, against `v^2/R`. 20 is the
    # floor at racing speed, and this is entered off a banked 104-degree sweeper
    # taken flat, which is the fastest the car is moving anywhere in the second
    # half of the lap. **`loop` leaves its rails on**, so the `rail("")` after it
    # is load bearing - without it the whole run to the flag is walled and the
    # track stops being `exposed` both in the test and at the wheel.
    # **Railed down the left, and that is a shortcut fix rather than safety.**
    # `loop` slides its exit sideways so the descent does not land on the climb,
    # and the side it slides to is the side you can then drive straight across:
    # `tools/cut_check.py` found a 31-unit chord here skipping 161 units of road,
    # worth 100 units, with nothing standing in it. That is Silverstone's "a
    # corner you can simply leave out" in `docs/track-defects.md`, and on a loop
    # it is worse than on a corner, because the thing being skipped is the whole
    # reason the room is that tall.
    #
    # A barrier rather than a checkpoint: a gate has to sit on flat unprofiled
    # road and there is none between the two ends. The rail runs from the
    # lead-in to the far side of the hairpin after it, because the chords that
    # pay go round the *outside* of the whole complex and not over one apex.
    b.rail("lr")
    b.straight(28)
    b.loop(radius=23)
    b.rail("lr")
    b.straight(26)
    # **And a checkpoint on the way out, which is the half the barrier cannot
    # do.** The rail closes every chord across the loop *on the ground*; it
    # cannot close one through the air, and `cut_check` still found a 98-unit
    # line from a third of the way up the climb to past the exit - which is what
    # falling off a slow loop and landing beyond it looks like. A gate here kills
    # anything that spans the loop at any height, because a chord over it skips
    # it. Both fixes, because they fail differently - `docs/track-defects.md`
    # says so under Silverstone, and this is the case that proves it.
    b.cp()
    b.rail("l")

    b.arc(-118, 24, rise=3)
    b.rail("")
    b.straight(46, rise=3)

    # --- the haulage way ----------------------------------------------------
    # The way ore leaves a mine, so the way out, and the movement that was wrong
    # in the first version: a hundred and twenty units of straight, two gentle
    # sweeps and a flag. It is the longest movement on the track, so it was also
    # the largest single piece of it with nothing to do.
    #
    # It is now the climb with the most corners on it - a tight uphill right, an
    # 18-radius uphill hairpin, a half-pipe on the inside of the left after it,
    # and the broken trestle - and the pad at the foot is what pays for all of
    # them, because a pad pointed uphill buys the climb.
    b.boost(26)
    b.straight(76, rise=12)
    b.arc(66, 30, rise=3)
    b.straight(48, rise=6)
    b.hump(2.8, 30)
    b.arc(-142, 18, rise=5)
    b.straight(56, rise=7)
    b.cp()
    # Inside of a left-hander is the left, so this is the second of the two.
    b.pipe(4.4, 0.42, side="l")
    b.arc(-92, 38, rise=7)
    b.flat()
    b.straight(40, rise=4)
    # The broken trestle. The kicker is steep for its size and the far side is
    # ten units down, and both are the gap test rather than taste: a shallower
    # version, 46 units across and dropping six, only carried 39 of the 50 it
    # had to. A hop over a hole has to *fall*, or arrival speed is the only
    # thing clearing it.
    b.crest(3.0, 24)
    b.gap(40, drop=10, bow=_bow(40, 10.0, 3.0 / 24))
    b.rail("lr")
    b.straight(44)
    b.rail("")
    b.straight(40, rise=4)
    b.arc(76, 40, rise=6)
    b.straight(48, rise=6)
    b.cp()
    b.arc(-58, 34, rise=3)
    b.straight(38, rise=4)
    b.finish()


def _bow(length, drop, grade):
    """A ballistic hint matching the kicker's exit grade.

    `gap`'s own default bow is capped at four units, which is fine for a hop and
    too flat for a real fall: the shallow default meets the kicker's exit at a
    kink in the tangent, and `laptime.speed_profile`'s curvature cap reads a kink
    as a tight corner and brakes for it right at the lip - independent of the
    kicker's own angle, since the kink is in the seam and not in the ramp.
    """
    return round((drop + length * grade) / 3.141592653589793, 3)
