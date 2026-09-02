"""Dino Park

A jungle gorge, a shelf behind the waterfall, and a brachiosaur you drive over.
"""

slug = "dino"
name = "Dino Park"
difficulty = 4
ground = None
order = 210
width = 13.0
exposed = True
scenery = True

# The three set pieces are **derived, not authored**. Each one is the extreme of
# some quantity the ribbon already carries, and the layout below is written so
# that stays true:
#
#     the ledge    the only stretch at the lap's highest point
#     the herd     the only stretch wider than the road (`width(HERD_W)`)
#     the animal   the stations flagged `skin` - the ones with no road on
#                  them at all, because the creature's back is the surface
#
# So `scenery.js` finds all three by looking, and there is no pair of constants
# in two languages to drift apart - the thing this repo has been bitten by
# before. The cost is a rule on the layout rather than a number: **re-cut this
# track however you like, but do not add a second summit, a second wide stretch
# or a second narrow one**, or the set piece will be hung on whichever the scan
# reaches first. Widening the whole road is fine; the scan is relative.

# How wide the road is over the animal, and across the floor the herd walks.
# The spine is narrower than the jungle floor because it is a *back*: at the full
# 13 the body has to be so broad that it stops reading as a creature and starts
# reading as a bridge with a head on it. The herd's floor is wider because that
# is what makes room to drive around something walking across it.
HERD_W = 17.0
SPINE_W = 11.0

# The gorge crossing's rise and fall. The tail is the climb and the neck is the
# descent, so these two are what the animal's silhouette is built from: the
# scenery derives the body's height from the road over it rather than the other
# way round, which is what stops the two disagreeing after a layout change.
TAIL_RISE = 9.0
NECK_FALL = 14.0


def build(b):
    """A fast lap round a jungle gorge, with the three things you remember.

    The reference is Dino Dino Jungle, and the two things worth taking from it
    are that it is a **fast** track - long sweepers under a canopy, not a
    technical one - and that its landmarks are all *creatures and water* rather
    than architecture. So the corner radii here run 28 to 90 with most of them
    past 50, and every place the track is memorable is a place something is
    living or falling.

    The lap in order:

    - **The canopy run.** Two long sweepers off the line at 78 and 58, which is
      the fastest part of the track and deliberately the first thing you meet -
      `docs/track-defects.md` notes that a long intro reads as the track not
      having started yet, so the first corner arrives 62 units in.
    - **The river jump.** A pad, a shallow kicker and 56 units of air over the
      water at the gorge's narrow neck. Kept shallow on purpose: `AIR_PITCH`
      noses the car down at a constant rate for as long as the throttle is held,
      so a steeper lip buys nose-down attitude at touchdown rather than
      distance. The landing straight is 64 units because a real lap arrives at
      the lip at a speed that depends on how the sweeper before it was taken,
      and the authored span only tells you the jump is *reachable*.
    - **The climb to the falls**, 23 units over three legs, every one of them
      eased and every one satisfying `length >= sqrt(330 * rise)` with room -
      the one hill on this track that is not meant to launch anybody.
    - **The ledge.** A 96-degree left at radius 72 on a shelf cut into the cliff,
      with the water coming down across the outside of it for the whole corner.
      Railed on the drop side, because there is nothing under it.
    - **The descent and the station**, including the one real braking point on
      the track: a 28-radius right round the back of the ranger post. A track
      whose corners are all fast has no reference speed to judge the fast ones
      against, and `test_corner_radii_are_varied_and_drivable` says so too.
    - **The esses**, three linked corners of falling radius under the canopy.
    - **The herd.** The road opens to 17 units across the flattest, fastest part
      of the jungle floor, and the animals walking over it are the only thing
      making it difficult. It is wide because the line through it is not a line -
      it changes every lap - and a 13-wide road with something moving on it is a
      coin toss rather than a decision. There is a pad in front of it, which is
      the deliberate part: the herd is worth arriving at with speed you have to
      spend.
    - **The animal.** You climb the tail, run the spine, and come down the neck
      onto the far bank of the gorge - nine units up and fourteen down, over a
      hole the scenery digs forty units deep underneath. Railed end to end.
    - **The run to the flag**, a pad and two sweepers, cut short on purpose:
      the closing stretch is the part nobody remembers.

    **Two stretches are railed and the rest of the track has none.** This is a
    `ground = None` track whose world is built in `scenery.js`, so the pool
    default would be rails everywhere - and that is wrong here for Cloudbreak's
    reason, doubled: the jungle floor under nearly all of this road *is* in the
    collider, four units under the tarmac, so running wide is a slow scramble
    through undergrowth rather than a respawn. Time lost is the better penalty
    and it is the one this game reaches for wherever it can. The barriers are
    only where the floor genuinely is not there: the waterfall ledge, and the
    animal.
    """
    # --- the canopy run -----------------------------------------------------
    # First, and it used to be *only* fast: two long corners and a straight, over
    # in eleven seconds with nothing to get wrong. Now it is the flick section -
    # a left-right pair, a root you take airborne, and a tightening right - which
    # is what makes the boost and the river jump at the end of it feel like the
    # release they are meant to be. There is a herd walking across it as well;
    # `scenery.js` puts them here for the same reason.
    b.start(run=44)
    b.arc(62, 70)
    b.straight(26)
    b.cp()
    b.arc(-52, 64)
    b.arc(46, 44)

    # The hollow. A dry streambed the trail drops into and climbs back out of,
    # with the tightest corner on the track at the bottom of it - 24 units, and
    # the only one under 38 anywhere. It is here rather than later for two
    # reasons: it is the one place a slow corner costs nothing, because you have
    # not built any speed yet; and a lap that opens with a hairpin in a hole and
    # then never sees another one has said what kind of track it is.
    b.straight(34, rise=-3.0)
    b.arc(-128, 24, rise=-4.0)
    b.straight(48, rise=6.0)
    b.crest(3.0, 22)          # a root across the trail; small, and unsettling
    b.arc(-70, 56)
    b.straight(22)
    b.arc(58, 40)
    b.straight(28)
    b.arc(-84, 58)
    b.straight(26)

    # --- the river jump -----------------------------------------------------
    # A pad into a shallow lip. `crest` rather than `straight(rise=)` because a
    # crest is the un-eased version and the crease is the whole point.
    b.boost(18)
    b.crest(5.0, 26)
    b.gap(56, drop=8.0)
    b.straight(46)
    b.arc(28, 92)
    b.straight(22)
    b.cp()

    # --- the climb to the falls ---------------------------------------------
    # 23 units up, spread over 175 so none of it launches the car. The two rising
    # legs are near the shortest the hill rule allows for their rise (a hill needs
    # `length >= sqrt(330 * rise)` or it is a kicker), which is deliberate: this
    # is a wall of rock and it should feel like climbing one.
    b.arc(70, 64, rise=10.0)
    b.straight(52, rise=8.0)
    b.arc(-56, 46, rise=5.0)

    # --- the ledge behind the water -----------------------------------------
    # The lap's highest point, and the one place with nothing under the road -
    # which is also how `scenery.js` finds it. Railed both sides: the cliff is on
    # the inside and the drop is on the outside, and hitting rock is the same
    # mistake as falling off it.
    b.cp()
    b.arc(-96, 72, w="lr")
    b.straight(40)
    b.rail("")

    # --- down past the ranger station ---
    # **Switchbacks, not a descent.** This used to be one long falling straight
    # off the shelf, which is the cheapest way to lose 17 units and the dullest
    # part of the lap: you have just come out from behind a waterfall and the
    # next thing the track asks you is nothing. Three falling corners in
    # alternating directions ask something the whole way down, and the station
    # is on the outside of the second one where you have time to look at it.
    b.arc(64, 54, rise=-9.0)
    b.arc(-48, 60, rise=-6.0)
    b.arc(58, 46, rise=-6.0)
    b.cp()
    b.straight(24)
    b.arc(-104, 28)
    b.straight(26)

    # --- the esses ----------------------------------------------------------
    # Falling radius, so each one is slower than the last and the exit of the
    # fourth is what sets your speed onto the herd's floor.
    b.arc(-46, 56)
    b.arc(52, 56)
    b.arc(-60, 48)
    b.arc(44, 38)
    b.straight(30)

    # --- the herd -----------------------------------------------------------
    # The widest road on the track, which is how the scenery finds it, and the
    # reason it is wide: there is something walking across it and you need a
    # choice of which side to pass. The boost is at the entry rather than the
    # middle, so the speed is yours to place rather than handed to you halfway.
    b.width(HERD_W)
    b.straight(30)
    b.boost(16)
    b.straight(50)
    b.arc(58, 68)
    b.straight(34)
    b.width(13.0)
    b.cp()

    # --- the animal ---------------------------------------------------------
    # **The road stops here.** `skin` tells `trackmesh.js` to draw no surface, no
    # kerb and no slab across this stretch - only the collider quad - and
    # `scenery.js` finds these same stations and builds the creature's back
    # *through* them. So what holds the car up is a broad flat-crowned back that
    # falls away to a rounded flank either side, and you are driving on the
    # animal rather than on a road that happens to have one under it.
    #
    # No rails, and that follows from the same decision: a handrail down both
    # sides of an animal's spine is a bridge with a paint job. The back is more
    # than three times the width of the road it replaces, which is where the room
    # to get this wrong comes from instead.
    b.arc(-72, 50)
    b.straight(34)
    b.width(SPINE_W)
    b.skin(True)
    b.straight(56, rise=TAIL_RISE)               # the tail: up onto its back
    b.straight(64)                               # the spine
    b.arc(34, 90)                                # the body's own arch
    b.straight(72, rise=-NECK_FALL)              # the neck: down onto the bank
    b.skin(False)
    b.width(13.0)
    b.straight(34)

    # --- the run to the flag ------------------------------------------------
    b.cp()
    b.arc(78, 60)
    b.straight(34)
    b.arc(-64, 68)
    b.boost(18)
    b.straight(38)
    b.arc(56, 50)
    b.arc(-44, 60)
    b.straight(30)
    b.finish()
