"""Playground

Nothing under it, nothing over it, and four walls of death. Sideways for most
of the lap, and a jump that goes uphill.
"""

import math as _math

slug = "playground"
name = "Playground"
difficulty = 5
# Set by hand rather than cut by `tools/set_medals.py`, for Rickety Rails' and
# Tokyo Drift's reason: there is no board to cut from yet, and the tool's
# fallback derivation makes a poor standard - it is out by 0.744 to 0.888 of
# itself depending on the track.
#
# Gold is 0.85 of the ideal (87.6s), which sits in the 0.77-0.90 band every record
# actually set on this site falls in, and toward the hard end of it - which is
# right for a track whose fastest line is a *higher* line on four walls, and
# where the model assumes you are on none of them. Re-cut once there is a board.
medals = (74.5, 77.0, 80.5)
ground = None
order = 230
width = 15.0
rails = False
exposed = True
scenery = True

# The road is the whole world, and `below: void` means what you fall into is
# nothing rather than a grey plate a long way down.
#
# **That is a decision about the geometry, not about the art.** Every other
# floating track in the pool gives you something to read height against - Big
# Red's drowned city, Cloudbreak's spires, Rickety Rails' cave floor - and this
# one deliberately does not, because most of its set pieces rotate the road
# instead of moving it. A wall of death is only legible if the road is the only
# thing in frame with an orientation; put a horizon of mesas behind one and the
# eye reads the world as tilting rather than the car.
#
# What `scenery.js` puts there instead is **poles** - a rank of posts just off
# each kerb, solid, in the collider. They are the barrier on a track that has no
# ribbon `rail` anywhere, for Rickety Rails' reason: `exposed` with nothing at
# all at the edge means a respawn every time you are half a metre wide, which
# punishes precisely the thing this track is asking you to do. They also do the
# job a horizon would have done - on a road in empty sky, an unlit knob on a pole
# is the only thing that tells you where the next corner is before you can see
# the road under it.

# How wide a wall is. The car slides down one for as long as it is on it (see
# `WALL_BANK`), so the width is the budget for that slide and not generosity.
WALL_W = 21.0

# **Every wall on this track is banked 88 degrees, and none of them is long.**
#
# Both halves are a physics result rather than taste, and they were measured by
# driving the thing rather than by looking at it.
#
# On a banked corner the car needs `v^2/R` toward the middle; the bank supplies
# it and gravity pulls down the slope, and the balance sits at
# `tan(bank) = v^2 / (g*R)`. At 88 degrees that wants 185 u/s against a
# `MAX_SPEED` of 50, so the road is always far steeper than the speed can hold
# and the car is *always* sliding down it. `STICK_FORCE` does not help: it pulls
# the car into the road, never up it. What is left is `GRIP`, which is a damper
# rather than a limit, so the car settles at a steady
# `(g*sin(bank) - (v^2/R)*cos(bank)) / GRIP` down the wall - a touch over two
# units a second - for as long as the wall lasts.
#
# So a wall's length is a budget: **slide = that rate times the time on it**,
# and the time is `arc / v`. A hundred and eighty degrees at radius 40 spends
# 5.8 units of a 7.5-unit half-width and the car goes off the bottom, which is
# exactly what the first version did. A hundred and forty at radius 30 spends
# under three.
#
# **And that is the skill the track is actually about.** The slide is not a
# defect to be engineered away - it is why a wall is something you drive rather
# than something you hold the throttle through. You counter-steer up the wall,
# and how high you enter decides whether you are still on it at the exit.
#
# **Every wall is also a helix, and which way it climbs decides whether it can
# be skipped.** A wall that *descends* puts its own exit road underneath the
# wrap, so dropping off the top of the cylinder lands you on it and the whole
# three hundred degrees is optional - found by driving, not by
# `tools/cut_check.py`, which will not even consider a chord with more than six
# units of height between its ends and so cannot see this class at all. A wall
# that *climbs* puts the exit above the wrap instead, and dropping off it buys
# nothing but the void.
#
# So they climb. The Drum is the exception and it is forced: it is the last
# thing before the flag and the run to the line has to pass under its lead-in,
# which only works if the Drum spends the height. What defends that one is that
# there is nowhere to land - see its own note.
WALL_BANK = 88.0

# Mushroom geometry, lifted wholesale from Shroom Street because the numbers are
# about the car and not about that track: 26 units of cap catches every arrival
# between 31 and 50 u/s, and the disc is far wider than the road because a car
# comes at one out of the air with `AIR_STEER`'s fraction of its steering.
CAP_LEN = 26.0
CAP_W = 24.0
BOW = 7.0

# The Climb: a chain of steepening kickers with a boost pad on every one, which
# is Mount Joy's ski jump and the only way to get a car up something this steep.
#
# **A pad re-arms itself for as long as you stay on it**, so the engine is still
# 1.7x at the lip - 105 u/s^2 against the 29.5 that gravity takes back along a
# 72-degree ramp. `PAD_BOOST` is 1.3 seconds, so a ramp long enough to be worth
# climbing would run out of boost half way up without one pad per step.
#
# **Sixty-eight degrees is the ceiling, and it is set by the ribbon rather than by
# the car.** `_steps` decides how many stations a leg gets from its *horizontal*
# run, so a step at angle `d` lays them `run/steps / cos(d)` apart along the road
# it actually builds: 8 units at Mount Joy's 64 degrees, 10.5 at 70 and 11.6 at
# 72 - both past the 10.5 that `test_stations_are_a_continuous_ribbon` calls a
# hole in the road.
# Fixing that properly means measuring a leg in three dimensions, which moves
# every track in the pool that has ever used `rise`, so this stops at 68 - still
# the steepest ramp in the game, and near enough vertical from the car that the
# sky is the whole windscreen.
#
# **It tops out there and then simply stops, and that is forced rather
# than chosen.** A steep ramp cannot level off: to follow a road that flattens,
# the car needs the road to curve no faster than gravity can hold it down, which
# at 40 u/s is a vertical radius of 53 units and therefore about seventy units of
# arc to give back 72 degrees - and `straight(rise=)` cannot do it anyway, since
# its smoothstep *starts* at zero grade. So the ramp ends at the top and you fly
# off it, which is what Mount Joy does with the same problem.
CLIMB = [(20, 18.0), (18, 34.0), (16, 48.0), (16, 60.0), (20, 64.0), (18, 68.0)]

# Off a 72-degree lip almost all of the car's speed is vertical: at 50 u/s that
# is 47 up against 15 along, so the apex is some thirty-six units above the lip
# and only twenty-odd beyond it. A short, very tall hop - which is why the
# landing is close and high rather than far and low.
# **The platform goes at the apex, not below it**, which is the opposite of the
# instinct and is what keeps the hang time sane. Off a 70-degree lip at 50 u/s
# the car leaves with 47 up and 17 along: the apex is 37 units above the lip and
# only 27 beyond it, and landing *there* is a 1.6-second flight. Authoring the
# platform twelve units up instead - the more obvious "it climbs a bit" - makes
# the car fly all the way over the top and back down past it, 2.9 seconds, and
# `AIR_PITCH` noses it into the deck. Shorter flights come from landing higher.
CLIMB_GAP = 30.0
CLIMB_RISE = 34.0

# The Slot: the hole in the road at the foot of the ramp.
#
# **The whole of this is one alignment, and it is arithmetic rather than
# eyeballing.** You jump a hole on the way in, climb the ramp, turn round at the
# top and come back down the line you arrived on - and fall through the same
# hole into the level below. For that to work the descent has to end up directly
# over the hole, in both axes, and a turtle cannot be asked where it is: the
# `Recorder` that `tracks/moves.py` records a track with has no `pos` at all, on
# purpose, so a `build` that read its own position could not be turned into a
# document. So the numbers are computed here from each other instead.
#
# **Across the road** is the easier half. A 180-degree turn of radius `R` leaves
# the car travelling back the way it came, exactly `2R` to the side - so the
# ramp has to sit `2R` off the line of the hole, and an S of two opposite arcs
# puts it there: `2 * SHIFT_R * (1 - cos SHIFT_A)`, which is `2 * TURN_R` by the
# choice of 60 and 60 below.
#
# **Along the road** is a running total: every horizontal length between the
# hole and the turn, added up, is how far back the descent has to travel. The
# climb's steps contribute their `run` and not their length, which is the one
# thing about `boost(run, rise=...)` that makes this tractable at all.
TURN_R = 18.0
SHIFT_R = 36.0
SHIFT_A = 60.0
# **The hole has to be jumpable on the way in, and that is a kicker rather than
# a width.** A *level* gap carries the car `v^2 sin(2*theta) / g` and a road with
# no launch angle has `theta` of zero - so a flat 60-unit hole entered at 45 u/s
# reaches *four* units, which is to say the car drives straight into it. Thirty-six
# units off a 17-degree brow reaches forty-one, which clears it with room.
HOLE = 36.0
HOLE_KICK = 8.0
HOLE_KICK_RUN = 26.0
AFTER_HOLE = 56.0
TO_PAD = 20.0
PAD_RUN = 34.0
PLATFORM = 64.0
CP_RUN = 34.0            # `cp()` lays 17 units either side of its gate

# How far the S carries the road forward while it is shifting it sideways.
SHIFT_FWD = 2.0 * SHIFT_R * _math.sin(_math.radians(SHIFT_A))
# ...and the check that it shifts it by the right amount. A silent mismatch here
# is a descent that comes down beside the hole instead of through it, which
# looks like nothing at all going wrong.
assert abs(2.0 * SHIFT_R * (1.0 - _math.cos(_math.radians(SHIFT_A)))
           - 2.0 * TURN_R) < 1e-6, "the S must offset the ramp by the turn's own 2R"

# Everything between the middle of the hole and the entry to the turn.
CLIMB_RUN = sum(run for run, _deg in CLIMB)
OUT_RUN = (HOLE / 2.0 + AFTER_HOLE + SHIFT_FWD + TO_PAD + PAD_RUN
           + CLIMB_RUN + CLIMB_GAP + PLATFORM + CP_RUN)

# The descent stops short of the hole, because the car has to be *falling* by
# the time it gets there - a road that ran to the lip would simply drive over
# it. How far short is ballistics: `ease=True` takes the grade back to zero at
# the end, so the car leaves level, and from `RETURN_MARGIN` up it needs
# `sqrt(2h/g)` seconds to reach the plane of the road below - about 1.1s, or
# fifty units at racing speed. Which puts it through the hole at the middle.
DROP_SHORT = 50.0
RETURN_RUN = OUT_RUN - DROP_SHORT

# How high the platform stands over the road the hole is in: the ramp's own
# climb, plus the hop off its lip.
CLIMB_TOP = sum(run * _math.tan(_math.radians(deg))
                for run, deg in CLIMB) + CLIMB_RISE
# The descent gives back all but `RETURN_MARGIN` of it, which is the height the
# road still has in hand when it runs out. Not zero, for two reasons and the
# second is the one that set the number: the return runs directly above the road
# it started on, and `self_proximity` calls two roads within five units of each
# other a car trap rather than a crossing - but `gate_ceiling` is derived from
# the *closest* the track ever passes over itself, so at ten units it was legal
# and quietly collapsed every checkpoint window on the track from 14 to 5.3.
# Eighteen units of clearance is what buys the full ceiling back; 24 leaves
# margin, since the road underneath is not level.
RETURN_MARGIN = 24.0
RETURN_DROP = CLIMB_TOP - RETURN_MARGIN

# And the fall through the hole itself into the level below.
SLOT_GAP = 74.0
SLOT_DROP = 50.0

# And the bow by ballistics rather than by the lip's grade. Mount Joy's
# `_bow`-style formula is `(rise + length * tan(angle)) / pi`, which is a decent
# hint at 64 degrees and returns **46** at 70 - a modelled arc bulging 46 units
# over its own chord, which spreads the gap's stations 15 units apart and reads
# to `test_stations_are_a_continuous_ribbon` as a hole in the road. The real
# bulge over this chord is about seven.
CLIMB_BOW = 7.0


def build(b):
    """Four walls, a loop, a jump that climbs, a mushroom and a half-pipe.

    **The lap is built around one move done four different ways.** A wall of
    death is the thing this track has that nothing else in the pool does, so it
    opens with one and closes with one, and the two in between are a left-hander
    and a three-quarter turn - genuinely different problems, because the slide
    is always toward the inside and the inside changes sides.

    **What is deliberately not here.** A barrel roll on a straight, which was
    the first version's centrepiece and is undrivable - there is nothing at all
    opposing gravity down the tilt when the road is not turning, so the car
    slides off however fast or slow the roll is. And a rattle of crests off the
    line, which was just holding the throttle. `docs/track-defects.md` has both.

    **Where the difficulty is.** Almost none of it is in the corners, which is
    what makes this a 5 that shares nothing with Monaco's 5. It is in *height* -
    how high up a wall you are when it runs out, how high over the deck you are
    when the Cannon lands - and in the fact that the fast line is never the one
    the road is pointing at.
    """
    # --- the Drop ------------------------------------------------------------
    # Onto a wall immediately, before the car has finished accelerating. The
    # first version opened with six crests, which is a hundred and ninety units
    # of holding the throttle down - the track announcing itself and asking
    # nothing. This asks on the second corner.
    b.start(run=44)
    b.boost(22)
    b.straight(44)
    b.width(WALL_W)
    b.wall(300, 44, WALL_BANK, ramp=90, rise=16)
    b.width(width)
    b.straight(30)
    b.cp()

    # --- the Zed --------------------------------------------------------------
    # Two hairpins of opposite hand with a short diagonal between them, which is
    # the one shape on this track that is about *placing* the car rather than
    # about holding on to it.
    #
    # **It replaced a loop, and the loop was the problem rather than the fix.**
    # A loop is a corner the track drives for you: there is one line through it,
    # no braking decision, and the only input that matters is arriving fast
    # enough. On a lap already made of walls - which are also a fixed line taken
    # flat - it was a third helping of the same thing. The Zed asks the opposite
    # question: the first hairpin's exit is the second one's entry, so how early
    # you get the car straight decides everything, and the diagonal is too short
    # to fix a bad one.
    #
    # The two radii are deliberately different. Same-radius hairpins back to back
    # are one corner driven twice; 20 into 26 means the second opens where the
    # first tightened, and the line that suits one is wrong for the other. 20 is
    # the tightest corner on the track by some way - `MIN_RADIUS` is 12 - and it
    # is the only first-gear moment in the lap.
    #
    # **Railed on the insides**, which is where a hairpin pair is cuttable: the
    # apex of each one sits inside the other's arc, so the chord across the Z is
    # short and pays. Rails on the ground close it; the gate on the exit closes
    # anything through the air. Silverstone's arena barriers are the same idea
    # and `docs/track-defects.md` names it "a corner you can simply leave out".
    b.arc(-64, 46, rise=4)
    b.straight(34)
    b.rail("r")
    b.arc(-155, 20, rise=-3)
    b.rail("")
    b.straight(46)
    b.rail("l")
    b.arc(155, 26, rise=-3)
    b.rail("")
    b.straight(20)
    b.cp()
    b.straight(20)

    # --- the Cannon ----------------------------------------------------------
    # Every other gap in the pool falls. This one climbs, and a gap that climbs
    # reads as a completely different object from the cockpit - the far side is
    # above the horizon on the way to it.
    #
    # **The numbers are ballistics and there is no slack in them.** `GRAVITY` is
    # 30 against a `MAX_SPEED` of 50, which puts the flat-ground range of a
    # 45-degree launch at about 83 units, so height is expensive and has to be
    # bought with both a pad and a steep kicker. Off the pad the car reaches the
    # lip at 54 and a 30-degree kicker puts the apex twelve units up, so the deck
    # goes at six - low enough that the car is past the top and *descending* onto
    # it. Landing on the way up puts the nose into the face of the platform.
    #
    # **Six rather than the eight this was first built at, and the two units are
    # the whole margin.** A gap that climbs is the one shape
    # `test_every_gap_is_clearable` cannot check - it takes `max(0, drop)`, so an
    # uphill landing reads to it as a level one and every version of this passed.
    # Worked by hand instead, across the range of speed a real lip sees rather
    # than at the ideal one: at eight units anything arriving under 51 u/s came
    # up short and hit the *face* of the platform, and 51 is an ordinary
    # consequence of fluffing the corner before the pad. At six, 46 u/s lands two
    # units onto the deck and 60 lands forty-six on.
    b.arc(56, 50)
    b.straight(40)
    b.boost(30)
    b.straight(22)
    b.crest(12.0, 21.0)
    b.gap(42.0, drop=-6.0, bow=5.7)
    # Ninety-six units of deck, railed, with the gate pushed out past where even
    # a no-lift approach lands. Big Red's landing straight is the pool's
    # cautionary tale: 46 units that the ideal line landed in and a fast entry
    # flew clean over, and past the far end the car was landing on whatever
    # happened to be next rather than on flat road.
    b.rail("lr")
    b.straight(96)
    b.rail("")
    b.cp()

    # --- the Mushroom --------------------------------------------------------
    # One cap, not three. Shroom Street's own note is the argument: a car in
    # flight is not being steered, so air time is time the track is not asking
    # you anything, and a chain of three is six seconds of watching.
    b.arc(74, 38)
    b.straight(30)
    # **A pad on a ramp pointed *down* at it, which is what makes this cap throw
    # you a hundred units instead of forty.**
    #
    # A cap returns `max(BOUNCE_VEL, -vn * BOUNCE_REST)` and takes the larger,
    # never the sum. `BOUNCE_VEL` is 21 and `BOUNCE_REST` is 0.68, so the
    # reflection only beats the floor once the car is arriving at better than 31
    # u/s *into* the disc - and an ordinary hop off a ten-unit drop arrives at
    # 24.5, which loses. Every gentle cap in the game gives the same flat 21
    # whatever you do on the way in, which is exactly what this looked like.
    #
    # So the cap has to be *fallen onto*, and the fall is the only thing that
    # can do it. **A ramp angled down at it cannot**, which was the first
    # attempt: a `boost` with a negative rise and `ease=False` is a crest, the
    # road drops away from under the car at the top of it, and the car launches
    # off the lip and never touches the sloping part at all. That is not a bug in
    # the ramp, it is what a convex brow *is* - and it is unavoidable, because
    # any road that steepens downward bends away from a car travelling straight.
    # There is no geometry that aims a car downward; there is only falling.
    #
    # So: a pad on the level, the road stops, and twenty-four units of fall onto
    # the disc. The car arrives at 38 u/s downward, which the cap returns as 26
    # against a floor of 21 - and the pad has meanwhile put the *forward* speed
    # near 62, so the flight off it is both faster and flatter than any other cap
    # in the pool, and about a hundred units long against Shroom Street's forty.
    b.boost(30)
    b.width(CAP_W)
    b.straight(14)
    b.gap(58.0, drop=24.0)
    b.bounce(CAP_LEN)
    # And the flight. Both gaps here are authored well short of what the car
    # actually carries, which is Shroom Street's rule and it bites twice.
    # `test_every_gap_is_clearable` credits a cap only `BOUNCE_VEL`, never the
    # reflection, so it will not sign off a span the real bounce clears easily -
    # and more to the point the arrival speed is set by a corner a long way back,
    # so the landing point moves by thirty units between a good lap and a scruffy
    # one. Sized off the *slow* end: at 50 u/s the car lands fourteen units onto
    # the deck and at 62 it lands thirty-five on.
    b.gap(72.0, drop=-2.0, bow=BOW)
    b.width(width)
    # Railed for the part of the deck the car can actually land on, then not.
    # `test_barriers_are_opt_in` gives an `exposed` track a quarter of its
    # stations and this lap spends most of that on the loop and the ramp, so a
    # barrier past where anybody touches down is a barrier taken from somewhere
    # it is needed.
    b.rail("lr")
    b.straight(52)
    b.rail("")
    b.straight(28)

    # **There was a third wall here and it has gone.** A left-hander, on the
    # argument that the slide is always toward the inside so a left one catches
    # you where a right one dropped you. True, and not worth four hundred units:
    # by the time you reach it the track has already asked the wall question
    # twice, and the lap was the longest in the pool by a third. What is left in
    # its place is the corner that was its lead-in, which the Slide needed
    # anyway.
    b.arc(-52, 34)
    b.straight(40)
    b.cp()

    # --- the Slide -----------------------------------------------------------
    # A deep trough held through a left and a right, which is the one shape the
    # pool does not have: Rainbow Road's three profiles are one full trough and
    # two one-sided banks, and all three sit on a single corner.
    #
    # Deep enough and with little enough floor that there is no flat line
    # through it - 8.5 units of wall on a road whose flat middle is three units
    # wide - so the direction change is made by crossing the trough rather than
    # by steering across a floor.
    b.arc(46, 60)
    b.straight(36)
    # **A gate before the trough as well as after it, and the pair is what makes
    # the Cut below a shortcut rather than a hole in the track.** A checkpoint
    # defends every chord that reaches past it, so two of them put a hard bound
    # on how much of the lap any line through here can leave out: without the
    # near one, `cut_check` found a fifty-unit chord skipping 252 units - a fifth
    # of the track, which is not a cut, it is the corner you can simply leave
    # out. Between these two there is about 160 units to play with and the
    # hairpin is most of it.
    b.cp()
    b.pipe(9.0, 0.18, side="lr")
    b.arc(-70, 46)
    b.arc(80, 38)
    b.flat()

    # --- the Cut -------------------------------------------------------------
    # **The one deliberate shortcut on the track, and the reason the half-pipe is
    # where it is.** Chinmay's 59.859 on Rickety Rails was measured against that
    # track's own ribbon to find out what it actually does differently, and the
    # answer was not the jumps: its three longest excursions are all in
    # *half-pipes*, up to 3.4 half-widths outside the kerb and ten units above
    # the road, for a second and a half at a time. The record rides the pipe
    # walls and comes off the top of them.
    #
    # So this gives that somewhere to go. The trough runs out into a hairpin at
    # radius 24, and the chord across it is about fifty units - which is what a
    # car leaving the pipe's lip eight units up at forty-five can just carry, and
    # what a car that stayed on the floor cannot carry at all. The hairpin drops
    # six, so the landing comes up to meet you.
    #
    # It is worth about a fifth of a second, which is the right size: enough that
    # the board sorts by whether you take it, not so much that a lap without it
    # is not a lap. `tools/cut_check.py` sees it, and `scripts` note in
    # `docs/track-defects.md` explains why it sees six hundred others that are
    # not real.
    b.straight(22)
    # And the third gate, between the trough and the hairpin. Two were not
    # enough: the Slide turns through 175 degrees all told, so its exit comes
    # back alongside its entry and a fifty-unit chord from one gate to the other
    # skipped the whole of it - the half-pipe included, which is the part worth
    # driving. With this here the only thing a line through the air can leave out
    # is the hairpin, which is what was on offer.
    b.cp()
    # Radius 26 rather than 24, and it is the drop that sets it: a hairpin
    # dropping sixteen needs `sqrt(330 * 16)` = 73 units of arc not to be a
    # kicker, and 165 degrees at radius 24 is only 69. The drop is worth
    # having - see `gate_ceil` in the note below.
    b.arc(165, 26, rise=-16)
    b.straight(34)
    b.cp()

    # --- the Climb, the Turn and the Slot ------------------------------------
    # Jump a hole in the road, climb a pad-fed ramp until it is nearly vertical,
    # turn round at the top, come back down the line you arrived on, and fall
    # through the same hole into the level below.
    #
    # The arithmetic that makes the descent land on the hole is up with the
    # constants. What is worth saying here is the bit that is not arithmetic:
    #
    # **The gate is on the platform, not on the ramp.** A checkpoint is a plane
    # of fixed width across the road, and while `_side` in course.js takes the
    # full three-dimensional forward vector - so a gate on a *slope* is square to
    # it and works fine - the ramp is not a slope by the time it is worth putting
    # one on. It is 68 degrees of un-eased kicker, and `_gate` wants flat
    # unprofiled road with a settled run either side. The hop off the lip is what
    # puts a piece of level road at the top to hang one on.
    #
    # **And the turn is on that platform rather than on the ramp face**, which is
    # the one part of this that is a compromise and not a choice. `arc` lays a
    # *horizontal* circle with height applied separately, so a 180 on a tilted
    # plane comes out as a helix rather than as a turn lying in the slope. There
    # is no primitive for the second thing.
    # **Aimed away from the middle of the track before anything else happens.**
    # The Climb is a thousand units of road that goes out and comes back over
    # itself, so it needs a clear corridor about four hundred long and sixty
    # wide, and pointed the way it arrived it laid that corridor straight across
    # the mushroom's landing and the run to the Left Wall - 310 pairs of road
    # within touching distance at the same height. Fifty degrees of lead-in is
    # what puts it over open sky instead.
    b.arc(-50, 60)
    # The lead-in climbs, and that is clearance rather than character: the S
    # below carries the road back across the ground the mushroom's landing deck
    # is on, and at the height it arrived they passed fourteen units apart in
    # plan and four in height - two roads a car can be on at once. Seventy units
    # for sixteen of climb, because a hill needs `sqrt(330 * rise)` of length or
    # it stops being a hill.
    b.straight(72, rise=16)
    # The hole. Cleared on the way in - it is 60 units at the far end of a
    # straight, so it arrives as an ordinary jump and nothing announces that it
    # is going to matter again.
    b.rail("")
    b.crest(HOLE_KICK, HOLE_KICK_RUN)
    b.gap(HOLE, bow=_bow_down(HOLE, 0.0, HOLE_KICK / HOLE_KICK_RUN))
    b.straight(AFTER_HOLE, rise=-HOLE_KICK)

    # The S that puts the ramp `2 * TURN_R` to the side of the hole. Left first,
    # because the turn at the top goes right and therefore comes back to the
    # left of where it went in.
    b.arc(-SHIFT_A, SHIFT_R)
    b.arc(SHIFT_A, SHIFT_R)
    b.straight(TO_PAD)

    b.width(16.0)
    b.boost(PAD_RUN)
    # Railed from the third step, not the first. `test_barriers_are_opt_in`
    # allows an `exposed` track a quarter of its stations and this lap is close
    # to it; the opening two steps are 18 and 34 degrees with the road barely off
    # the level it started on, so a barrier there is spent on the one part of the
    # ramp you could survive leaving.
    for k, (run, deg) in enumerate(CLIMB):
        if k == 2:
            b.rail("lr")
        b.boost(run, rise=_rise(run, deg), ease=False)
    b.gap(CLIMB_GAP, drop=-CLIMB_RISE, bow=CLIMB_BOW)
    # The platform. Long, for Big Red's reason: the speed at the lip is set by
    # how the corner before the pad went, so where the car lands moves with it.
    # A pad the moment you land, so the hairpin is arrived at rather than
    # coasted to. It goes at the *near* end of the platform and not against the
    # corner: `test_a_pad_is_never_the_last_thing_before_a_braking_zone` wants a
    # clear run of about 36 units after a pad before anything tighter than radius
    # 30, and the hairpin is 18 - which is the rule doing its job rather than
    # getting in the way, because a pad spent directly into a first-gear corner
    # is a second of engine you brake straight back off. From here there are
    # sixty-four units to use it in.
    b.boost(PAD_RUN)
    b.straight(PLATFORM - PAD_RUN)
    b.cp()

    # **The Turn.** A hairpin, and exactly 180 - the angle is load bearing rather
    # than tidy, because anything else leaves the descent running at a slight
    # angle to the road it has to come down onto, and a degree of drift over four
    # hundred units of descent is the hole missed.
    #
    # **Radius 18 rather than 30, and it pays for itself twice.** It is the
    # tightest corner on the track, which is what makes it a hairpin and not a
    # loop of the platform - you arrive having just landed off the ramp, so it is
    # a first-gear corner in a place with nothing else to do. And `TURN_R` is the
    # number the whole out-and-back is built on: the S has to offset the ramp by
    # `2 * TURN_R`, so tightening the turn shortens the S by forty units *and*
    # takes the same forty off the return, which has to travel the out-run back.
    b.arc(180, TURN_R)
    b.rail("")

    # **The Slot.** Four hundred units of descent, straight, directly above the
    # road that arrives - which is a long way to go in one line and it has to be,
    # because any corner in it would move the far end off the hole. What it buys
    # is the view: the whole of the way in is underneath you on the way down.
    #
    # A pad at the top, because a descent with the throttle already pinned is the
    # one place on the track where more speed costs nothing - and because the
    # faster the car is going when the road runs out, the flatter it goes through
    # the hole.
    # The pad is level. It wanted a grade on it - a pad pointed downhill is free
    # speed - and `sqrt(330 * 12)` is 63 units against the 34 a pad gets, so it
    # was a 35-unit vertical crease and a launch rather than a hill. All of the
    # descent is in the one long leg instead, which has the length to ease it.
    b.boost(PAD_RUN)
    b.straight(RETURN_RUN - PAD_RUN, rise=-RETURN_DROP)

    # And through it. The road simply stops forty units short of the hole's
    # middle; from ten units up at racing speed the car is through the plane of
    # the road below well before the far lip, which is the whole picture - you
    # come down through a slot in a road you drove along a minute ago.
    b.gap(SLOT_GAP, drop=SLOT_DROP, bow=_bow_down(SLOT_GAP, SLOT_DROP, 0.0))
    b.rail("lr")
    b.straight(70)
    b.rail("")
    b.cp()

    # --- the Drum ------------------------------------------------------------
    # The big one, and the last thing before the flag: three-quarters of a turn
    # on the inside of a cylinder. It is the longest wall on the track and so the
    # one with the largest slide to pay for, which is what the extra width and
    # the bigger radius are for - at radius 36 the car holds a higher line for
    # longer, and it needs to, because there is nothing after it to recover on.
    b.arc(64, 56, rise=-4)
    b.straight(56)
    b.width(WALL_W + 3.0)
    # **And it descends**, which is both the reason it fits and the best thing
    # about it. Three quarters of a turn brings the exit back across its own
    # entry - `self_proximity` had them thirteen units apart at exactly the same
    # height, which is two roads a car can be on at once - and eighteen units of
    # drop makes that an over-and-under with room to spare. What it looks like is
    # a spiral: a wall of death you come out of the bottom of.
    b.wall(360, 40, WALL_BANK, ramp=90, rise=-18)
    b.width(width)
    b.straight(40)
    b.arc(-38, 64)
    b.straight(36)
    b.finish()


def _rise(run, deg):
    """The rise of a ramp step, so the angle is what is authored."""
    import math
    return round(run * math.tan(math.radians(deg)), 3)




def _bow_down(length, drop, grade):
    """The same, for a gap that falls. See Rickety Rails' winze."""
    import math
    return round((drop + length * grade) / math.pi, 3)
