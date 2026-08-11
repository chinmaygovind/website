"""Mount Joy

Off the valley floor on a boost pad, up onto the peak, then all the way down.
"""

slug = "mountjoy"
name = "Mount Joy"
blurb = "A boost pad, a ski jump onto the peak, then the whole mountain down."
difficulty = 4
ground = None
order = 160
width = 13.0
exposed = True
scenery = True

# The launch. `RAMP` is `(horizontal run, angle in degrees)` per step; the rise
# of each is `run * tan(angle)`, so the last angle is the launch angle and the
# whole thing climbs about 140 units.
#
# Two things make a ramp this big possible and neither is obvious.
#
# **It is a chain of kickers at increasing angle, not one steep one.** A ground
# contact kills the component of velocity into the surface (`Car.step`), so a
# road that goes from flat to sixty-four degrees in a single crease costs the
# car `1 - cos(64)` - more than half its speed, at the one place on the track
# where speed is the entire point. Five creases of ten to fourteen degrees cost
# about eight per cent between them.
#
# **Every step of it is a boost pad**, which is what lets it be long. `PAD_BOOST`
# is 1.3 seconds; the climb takes nearer three and a half, so a pad at the foot
# alone runs out a third of the way up and the rest is a car with 62 units of
# engine fighting 27 of gravity, arriving at the lip barely moving. Touching a
# pad re-arms it, so a pad *on* the ramp holds the 1.7x all the way: at sixty-
# four degrees that settles at a terminal speed of about 56 u/s, and it settles
# there whatever the ramp's length, which is the whole reason the ramp can be
# two hundred units long.
RAMP = [(20, 14.0), (18, 28.0), (16, 42.0), (16, 54.0), (24, 64.0), (22, 64.0)]

# The gap is sized so the car lands at (or just past) the top of its arc, which
# is both the softest landing available and the shortest hang time. That matters
# more than it sounds: `AIR_PITCH` noses the car down at a constant rate for as
# long as the throttle is held, so a flight that carries on past the apex only
# buys nose-down attitude at touchdown. At 56 u/s and 64 degrees the apex is
# about 42 units up and 41 along. See `docs/tracks-and-geometry.md`.
GAP = 40.0
GAP_RISE = 40.0


def build(b):
    """A mountain: the bottom of it, one enormous jump, and the way back down.

    The shape is DK Summit's and the constraint is this game's ballistics. You
    start on the valley floor, run an S at the foot of the mountain, and then
    everything funnels into one straight with a boost pad on it and a ski-jump
    ramp lit end to end with more of them. The lip is a hundred and forty-five
    units up; you leave it doing 55 and land a hundred and eighty-five over the
    start line, on a shelf near the top of the mountain. The whole of the rest
    of the track is the way back down.

    **How high the launch can go is arithmetic, not taste, and the flight is the
    small half of it.** A car leaving a lip at ``v`` and angle ``theta`` cannot
    climb past ``v^2 sin^2(theta) / 2g``, and ``v`` is capped by a pad's own top
    speed - ``MAX_SPEED * sqrt(1.7)``, about 65. That puts the *flight* at
    forty-odd units however it is authored. The ramp is what does the rest, and
    what lets the ramp be two hundred units long is that **it is a boost pad all
    the way up**: touching a pad re-arms it, so the engine is still 1.7x at the
    top, and at sixty-four degrees that settles to a terminal 56 u/s it holds
    for as long as the ramp lasts.

    That also makes the jump **deterministic**, which matters more than it
    sounds for a thing this size. Driven through the real `Car.step`, a car
    entering the pad at 34, 42 or 50 u/s all reach the same terminal speed on
    the climb and all peak within a fifth of a unit of each other - so the
    landing does not move with how well the corner before it was taken, and the
    shelf does not need to be padded out for a range of touchdown points the way
    Big Red's does.

    **A gap that lands *above* its lip has the opposite failure of an ordinary
    one.** Come up short on a normal jump and you fall into a hole; come up
    short here and you hit the mountain face below the shelf. That is what makes
    the collidable snow in `scenery.js` load-bearing rather than decoration -
    the face under the flight rises far more gently than the arc does, so an
    undershoot is a snowbank you climb out of rather than a lap you lose.

    The descent is switchbacks down one face, with **two more pads on it**,
    each in front of a kicker. Pointing down a mountain a pad buys distance
    rather than height, and it turns what would be a hop over a fold in the snow
    into eighty units of air and thirty units of the descent gone at once.

    Two rules set the spacing of the switchbacks and both come from the mountain
    rather than from the driving: any two legs at different heights have to be
    far enough apart *in plan* that the snow between them is a slope rather than
    a wall, and no leg may pass within `CROSS_CLEAR` of another. So the hairpins
    are wide and the traverses are long, which is also what a road down a
    mountain looks like. Between them are the things that stop a long traverse
    being a place to hold the throttle down and look at the view: a **half-pipe**
    round the outside of the first fast right, three **moguls** across the fall
    line, and an **ess** in the middle of each of the two longest legs.

    **A tenth of it is railed and that is on purpose.** The pool's floating
    tracks are walled almost everywhere and the exposed ones almost nowhere;
    this is neither, because the mountain changes what running wide *means*.
    Nearly everywhere the snow in `scenery.js` is in the collider four and a
    half units under the tarmac, so going off is a slow scramble back on - time
    lost rather than the lap, which is the better penalty and the one this game
    reaches for wherever it can. The barriers are only where that is not true:
    up the ski jump and across the first half of the shelf, where the road is
    seventy units of trestle over the snow, and on the two downhill jump
    landings, where the car arrives with no steering. Railing the rest would
    take the height away and leave a bobsleigh run.
    """
    # --- the valley floor ---------------------------------------------------
    # Flat, at the foot of everything. An S rather than a straight line to the
    # ramp: the mountain is in front of you on the grid, the first corner takes
    # you along the bottom of it, and the second turns you back to face it with
    # the whole climb in the windscreen.
    b.start(run=44)
    b.arc(-76, 52)
    b.straight(48)
    b.cp()
    b.arc(76, 44)
    b.straight(34)
    b.cp()

    # --- the launch ---------------------------------------------------------
    # Wide, because everything about this is committed: there is one line
    # through it and the only decision left is whether you were flat out early
    # enough. The pad sits at the foot of the ramp with no run between them -
    # `PAD_BOOST` is 1.3 seconds and the ramp is most of that at speed, so a
    # flat lead-in here is boost spent on road that does not climb.
    b.width(16.0)
    b.boost(40)
    # Railed from the moment it leaves the ground. This is the one stretch on
    # the track where the road is genuinely up in the air - by the lip it is
    # seventy units of trestle over the snow - and going over the side of a ski
    # jump is not a mistake anybody makes on purpose or recovers from.
    b.rail("lr")
    for run, deg in RAMP:
        b.boost(run, rise=_rise(run, deg), ease=False)
    b.gap(GAP, drop=-GAP_RISE, bow=_bow(GAP, GAP_RISE, RAMP[-1]))
    # ...and the first half of the shelf, which is a cliff on both sides and is
    # arrived at with no steering.
    b.straight(70)
    b.rail("")
    b.straight(60)
    b.cp()

    # --- the top ------------------------------------------------------------
    # The big road way up high. One long banked sweep off the shelf and round
    # onto the top of the face, and the one place on the track where you can
    # look down at the start line.
    b.width(15.0)
    b.arc(84, 96, rise=-10.0, bank=10)
    b.cp()

    # --- the descent: switchbacks down the east face -------------------------
    # Traverse, hairpin, traverse back, hairpin, four times over, marching away
    # from the summit each time. This is the shape the mountain forces and it is
    # worth saying why, because a spiral round the peak was tried first and had
    # to be pulled out.
    #
    # The snow between two legs is a slope at `FLANK` (0.62 - see `scenery.js`,
    # which cannot go steeper without surfacing through the big jump's flight
    # path). So two legs that are `dy` apart in height have to be at least
    # `dy / 0.62` apart *in plan*, or the upper one stands off the hill on piers
    # rather than being cut into it. A spiral gets that wrong in the worst
    # possible way: after one turn it is back over where it started, and there
    # the whole descent's worth of height has accumulated - the version before
    # this one had road forty-eight units above road twenty-three units away,
    # which is not a mountain road, it is a flyover. Switchbacks pay the same
    # bill in small change: each hairpin is a couple of its own radii wide and
    # only ever a dozen units of height, so every leg lands on the snow.
    #
    # The corners get progressively wider as the mountain does, and the first
    # one is by far the tightest thing on the track - the summit sweep before it
    # is flat out, so there has to be somewhere you actually brake.
    # There is a **boost pad in front of each of the two big downhill kickers**,
    # and they are there for the opposite reason the ramp's are. Uphill a pad
    # buys height; pointing down a mountain at a lip it buys *distance*, so what
    # would be a hop over a fold in the snow becomes eighty units of air and
    # thirty-odd units of the descent gone in one go. They are on straights with
    # a long clear run after them, which is the rule for every pad in the pool.
    # --- the half-pipe -------------------------------------------------------
    # DK Summit has one and so does this. `pipe(side='l')` curls the road's
    # cross-section up into a single banked wall on the *outside* of the corner
    # - outside of a right-hander is the left, because that is the way the car
    # is being thrown - so it is a line you can take high and drop off rather
    # than a trough you sit in. It blends in and out over `PROF_BLEND`, hence
    # opening it a station or two before the corner and closing it well before
    # the next gate: a checkpoint cannot sit on a profiled station at all, since
    # its mouth would be the chord of a curve with its posts up the walls.
    b.width(13.0)
    b.straight(56, rise=-9.0)
    b.pipe(5.2, 0.40, side="l")
    b.arc(74, 74, rise=-8.0)
    b.flat()
    b.straight(48, rise=-4.0)
    b.cp()

    # --- moguls --------------------------------------------------------------
    # Three rolls across the fall line. `hump` creases the road at the top on
    # purpose, so each one lifts the car briefly and lands it on the far side -
    # which on a descent means the back end is light exactly where you would
    # like to be braking.
    b.hump(2.8, 30)
    b.straight(40, rise=-4.0)
    b.hump(2.6, 26)
    b.straight(40, rise=-4.0)
    b.hump(2.9, 30)
    b.straight(44, rise=-5.0)
    b.cp()

    b.boost(28)
    b.crest(3.0, 40)
    b.gap(78, drop=38.0, bow=_bow_down(78, 38.0, 3.0 / 40))
    b.rail("lr").straight(58)
    b.rail("")
    b.straight(46)
    b.cp()

    # The tightest corner on the mountain, and then an ess rather than another
    # long traverse - the descent has three of these and they were all straight
    # lines, which on a road this wide is a place to hold the throttle down and
    # look at the view.
    b.arc(-158, 26, rise=-8.0)
    b.straight(58, rise=-6.0)
    b.arc(46, 50, rise=-3.0)
    b.arc(-52, 44, rise=-3.0)
    b.straight(46, rise=-4.0)
    b.cp()

    b.boost(26)
    b.crest(2.8, 36)
    b.gap(70, drop=34.0, bow=_bow_down(70, 34.0, 2.8 / 36))
    b.rail("lr").straight(54)
    b.rail("")
    b.straight(42)
    b.cp()

    b.arc(150, 44, rise=-8.0)
    b.straight(80, rise=-8.0)
    b.arc(-42, 62, rise=-3.0)
    b.arc(46, 56, rise=-3.0)
    b.straight(50, rise=-5.0)
    b.cp()

    b.width(14.0)
    b.arc(-138, 54, rise=-8.0)
    b.straight(150, rise=-12.0)
    b.cp()

    # Out of the mountain's shadow and onto the flat. **Unbanked on purpose**:
    # from here to the flag the snow comes up to meet the road (see `FLUSH` in
    # `scenery.js`) so the last corner is cut into the valley floor rather than
    # laid on top of it, and a banked road with the snow a metre under it drops
    # its outside kerb below the snow line.
    b.arc(72, 82, rise=-4.0)
    b.straight(78, rise=-3.0)
    b.finish()


def _rise(run, deg):
    """The rise of a ramp step, so the angle is what is authored."""
    import math
    return round(run * math.tan(math.radians(deg)), 3)


def _bow(length, rise, last):
    """A ballistic hint for the gap that matches the kicker's exit grade.

    `gap`'s default bow is a small capped one, fine for a jump that drops. This
    one climbs, so the default meets the kicker at a real kink in the tangent
    and `laptime.speed_profile` reads that kink as a tight corner and brakes for
    it at the lip - which is the one place on the track that ruins. Matching the
    initial slope to the ramp's exit grade removes it. See
    `docs/tracks-and-geometry.md`.
    """
    import math
    grade = math.tan(math.radians(last[1]))
    return round((length * grade - rise) / math.pi, 3)


def _bow_down(length, drop, grade):
    """The same hint for an ordinary falling jump.

    `gap`'s own default is capped at four units, which is fine for a hop and too
    flat for a thirty-eight unit fall off a pad: the shallow default bow meets
    the kicker's exit at a kink in the tangent, and `speed_profile` reads a kink
    as a tight corner and brakes for it right at the lip. Big Red's note in
    `docs/tracks-and-geometry.md` is about exactly this.
    """
    import math
    return round((drop + length * grade) / math.pi, 3)
