"""Big Red

A sheer dive on boost pads, launched twice over a drowned city.
"""

slug = "bigred"
name = "Big Red"
blurb = "A sheer dive on boost pads, launched twice over a drowned city."
difficulty = 4
medals = (60.0, 63.0, 66.2)
ground = None
order = 150
width = 14.0
exposed = True

def build(b):
    """Big Red: a sheer dive through a sunset sky, over a city drowned in cloud.

    The shape is the whole idea, and it is Big Blue's: you start at the top and
    the track spends the rest of itself going *down* - over 220 units of it
    across 3300, so the finish sits nearly three loops' height below the start
    and the one real climb on the whole track is the loop itself, the moment it
    hauls you back up rather than a trick sitting in the middle of a flat road.

    Five moments are genuinely airborne rather than just steep, and four of
    them are the same big jump repeated: a pad feeds a long, shallow kicker
    into a gap wide enough that the car is in the air for the best part of two
    seconds, dropping onto a stretch of road well under where it left - the
    one place on the track where "down" is something you fly rather than
    corner your way through. One is small, in the middle, the same idea in
    miniature. The other three are the real thing, and the back third of the
    lap is built around them: off the first slow hairpin, then a closing run
    of hairpin-into-jump repeated twice more, each hairpin resetting the
    speed for a pad that feeds the next jump, so the last stretch of the track
    is a hairpin, a jump, a hairpin, a jump, and the flag. All five gaps are
    pure ballistics: ``gap``'s own bow is too gentle for a fall this size and
    reads as a kink the lap model brakes hard for, so each is authored with an
    explicit ``bow`` that matches the kicker's exit angle and lets the model
    see the same rising-then-falling arc the car actually flies.

    None of the big jumps is as long as it could be made to look on paper.
    ``AIR_PITCH`` noses the car down at a constant rate for as long as the
    throttle is held in the air - which is how the pool's other jumps are
    flown, and how these are too - so hang time is what decides how far past
    level the nose has rotated by the time the wheels come back down, not
    distance or drop. A shallow kicker (a 4-unit rise over 50, on all four)
    buys most of that budget back: pitch grows with time in the air, not with
    how far it falls, so a launch angle close to flat gets a deep drop and a
    long carry for the same rotation a steeper, shorter kicker would spend on
    height it does not need. It also has to stay short enough that the pad is
    still live at the lip - `PAD_BOOST` is 1.3s, and a kicker long enough to
    run the car out of it arrives much slower, which is most of a jump's real
    reach gone before the ballistics get a say. The landing straight after
    each gap is long - 140 units before the next gate - on purpose: real
    speed at the lip varies with how the corner before it was driven, so the
    touchdown point moves around, and the gate needs room to be past it every
    time rather than only on the one lap that matched the model exactly.

    Corners are big and banked because a descent is fast and a fast corner you
    can lean on is what carries speed rather than scrubbing it; the tight
    hairpins exist so the big ones have something to be big *against*. It is
    in ``EXPOSED`` and keeps barriers in only five places - the loop, and the
    landing straight after each of the four big jumps, all of them being where
    a car arrives with no chance to correct rather than an ordinary corner
    exit. Everywhere else the edge is just the edge, including every one of
    the closing hairpins: a downhill track built around how far down it is
    loses the point of itself walled all the way round.

    The six boost pads are the only ones in the pool. They are all on
    straights and all with a long run to the next braking point - out of each
    slow corner and into the jump that follows it, and onto the loop - because
    a pad is worth about a second of unarguable speed and the place for that
    is somewhere you can use it, never into a corner where all it does is take
    the corner away.
    """
    b.start(run=46)
    b.boost(20)                              # off the line, before anything else
    b.straight(95, rise=-16.0)               # the drop off the top

    b.arc(-64, 92, rise=-18.0, bank=16)      # the first big banked left, falling
    b.cp()
    b.straight(75, rise=-10.0)
    b.arc(80, 62, bank=18, rise=-14.0)
    b.straight(34)
    b.cp()

    # The slow one. Everything either side of it is fourth gear or better, so
    # this is the only place on the track anybody has to think about braking.
    b.width(12.0)
    b.arc(-120, 26, rise=-6.0)
    b.straight(26)
    b.cp()

    # The big jump. A pad and a short runway to speed, a long shallow kicker,
    # and a gap wide enough that the fall is the point: 90 units of nothing
    # and a 30-unit drop to the far side. ``bow`` is authored by hand rather
    # than left to default - see the docstring above - so the lap model's own
    # ballistics see the same climb-then-fall the car does and do not brake
    # for it as if it were a corner. The landing straight is long on purpose -
    # see the docstring - so the gate is well clear of the touchdown however
    # the lip was actually hit, and it is the one place either side of the
    # loop that gets its rails back: the car arrives with no steering, so
    # a wide touchdown is not a decision anybody made.
    b.width(13.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.width(14.0)
    b.arc(96, 66, bank=20, rise=-16.0)       # the longest corner on the track
    b.straight(40)
    b.cp()

    # The small jump, the same idea in miniature - and its landing gets the
    # same short-lived rail for the same reason.
    b.crest(3.4, 9.0)
    b.gap(26.0, drop=9.4)
    b.rail("lr").straight(32.0)
    b.rail("")
    b.arc(-88, 48, rise=-10.0).straight(36)
    b.cp()

    # The loop, and the one climb. It is fed by a pad and a straight because a
    # loop is a speed check before it is anything else - arrive slow and the car
    # comes off the roof of it. It keeps its rails too: a loop without them is
    # a fall at the top rather than a corner, which is not exposure, it is a
    # broken corner.
    b.boost(20)
    b.rail("lr").straight(30)
    b.loop(radius=22.0, dir="l")
    b.straight(40)
    b.rail("")
    b.cp()

    b.arc(70, 58, rise=-12.0, bank=15).straight(44)
    b.width(12.0)
    b.arc(-140, 22).straight(34)             # the hairpin, and the last slow bit
    b.cp()

    # The third jump, off the last pad - the same shallow kicker and the same
    # margins as the first, closing the lap the way it opened: in the air.
    b.boost(20)
    b.width(14.0)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    # A closing run of hairpin-into-jump, twice over, each jump the same size
    # as the others and fed the same way - a hairpin to reset the speed, a
    # pad, the same shallow kicker and gap. None of these last corners are
    # railed: by here the track has committed to being run at the edge, and a
    # hairpin taken wide is a fall rather than a save either way.
    b.width(12.0)
    b.arc(128, 24, rise=-6.0)
    b.straight(24)
    b.cp()

    b.width(14.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.width(12.0)
    b.arc(-136, 20, rise=-5.0)
    b.straight(24)
    b.cp()

    b.width(14.0)
    b.boost(24)
    b.straight(10)
    b.crest(4.0, 50)
    b.gap(90.0, drop=30.0, bow=11.8)
    b.rail("lr").straight(140)
    b.rail("")
    b.cp()

    b.arc(86, 42).straight(34)
    b.finish()
