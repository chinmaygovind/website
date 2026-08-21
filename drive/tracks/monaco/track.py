"""Monaco

The Circuit de Monaco, compressed. Armco on both sides for two and a half
thousand units, a first-gear hairpin, and a tunnel.
"""

from tracks.builder import FREE

slug = "monaco"
name = "Monaco"
difficulty = 5
# **No ground plate and no `pal.terrain`, and this is the one architectural
# decision on the track.** Monte Carlo is built on a hillside and the circuit
# crosses over itself: Beau Rivage climbs directly above the harbour front, the
# two roads' *tarmac* overlapping in plan - 12 units of combined width across a
# 9.3-unit gap - with 9.2 units of air between them. That is a hillside terrace
# and it is genuinely what the place is.
#
# A height field is single-valued, so it cannot describe that, and `pal.terrain`
# was tried first and fails exactly the way `docs/track-defects.md` says it does:
# it drew Beau Rivage's road and run-off as a solid slab across the harbour-front
# road, which from the car is a ceiling you drive into. No `apron` setting reaches
# it, because it is the road surfaces themselves that overlap.
#
# So this is **Mount Joy's pattern instead**: the world is built in `scenery.js`,
# on a rule that cannot come up through any road, and the engine is told there is
# no ground at all. Two things follow, and both are wanted here rather than
# tolerated:
#
#  * `rails = True`. A floating track carries barriers by default and
#    `test_barriers_are_opt_in` *requires* them - which is the opposite of the
#    fight a ground track has, and Monaco wants armco on both sides of the road
#    for the whole lap. It is the only circuit in the pool where that is correct.
#  * the scatter goes away. `density`/`props` only apply to a ground track, and
#    a thin scatter of crates and palms across an empty plain was most of what
#    made the first render read as a quarry rather than a city. The palms are
#    planted along the harbour by `scenery.js` now, where they belong.
ground = None
rails = True
order = 190
# Twelve, against Silverstone's sixteen. Monaco's streets are 9-11 metres wide
# and its corners are the tightest in Formula One, so the road is authored narrow
# and narrows further: 13 down the pit straight and through the tunnel, 9.5 round
# the hairpin. Width is most of why this drives nothing like the other two
# circuits at the same corner radius.
width = 12.0
closed = True
# The city, the harbour and its yachts, the tunnel, the Casino, the swimming
# pool - and the armco, which is the only part of it the stopwatch can see.
scenery = True
# No `medals` yet, and no `hotlap.json`: both are cut from a lap somebody has
# actually driven and nobody has driven this. `NO_CUT_MEDALS_YET` in
# tests/conftest.py is what says so out loud. Set a lap, run
# `tools/set_medals.py monaco` and `tools/hotlap.py monaco`, and drop the entry.


def build(b):
    """Monaco, off its own surveyed centreline, and the pool's third closed lap.

    **Nothing below was drawn by eye.** Same method as Silverstone, and the same
    reason: every corner here is a real place, and a corner authored by feel is a
    corner that is not Monaco. OpenStreetMap carries the circuit as relation
    148194 (``type=circuit``, ``length=3337``); its member ways were walked from
    the start-finish node, the pit lane and the pit exit dropped, and the graph
    closed on the first try - **3323 m against the official 3337 m**, with total
    turning of exactly **-360.00 degrees**, which is the check that the walk found
    a real lap rather than a plausible one.

    The centreline was then resampled at one metre, smoothed over +/-4 m to take
    the surveyors' node jitter out, and segmented on curvature into straights and
    constant-radius arcs. Two passes on top of that, both of which changed the
    answer:

     * **Segmenting on the sign of the curvature alone merges corners.** Tabac and
       the Swimming Pool entry are both lefts with a kink between them, and a
       sign-only fit reads them as one 195 m corner at radius 83 - which closes
       the lap and is not the place. Long arc runs are subdivided again wherever
       the radius sustains a change of more than 1.75x.
     * **A circuit carries real drift along its straights.** 11.7 degrees of this
       lap is in legs too gentle to be corners (radius over 950 m). Rather than
       lose it, it is spread back across the arcs in proportion to their turn, so
       the angles below still sum to exactly 360.

    **Angles are not scaled**, for the reason Spa's docstring gives. Lengths are
    scaled by **0.75 units per metre** - Silverstone is 0.4586 and Spa 0.4522 -
    and that is a deliberate break with both. At Silverstone's scale Monaco is
    1531 units, which would make it the shortest track in the pool, and the
    hairpin comes out at **radius 8**, under the engine's hard minimum of 12. At
    0.75 the lap is 2434 units and the hairpin is 12.1, which clears the floor
    and has no margin - so it is the one corner here authored rather than
    measured, opened to **14**. Everything else is the radius it really is.

    Heights are the EU-DEM/SRTM average sampled every 20 m along the same line,
    smoothed over +/-100 m, at **1.05 units per metre**: a 43.7-unit fall from
    Casino Square down to the harbour, against Silverstone's 17 and Spa's 63.
    Two corrections, because the raw model is wrong in two knowable places and
    both are the kind of wrong that looks plausible:

     * **A 30 m DEM over a tunnel returns the hillside above it.** The run under
       the Fairmont read 18-20 m where the road is nearer 8, which would have put
       a hill through the middle of the tunnel. Portier's own 9 m is measured and
       right, so the tunnel is interpolated between its ends instead.
     * **In the dense parts it returns rooftops.** Casino Square came out at 53 m
       against a published 42. The profile is rescaled onto the published range
       rather than trusting the peak.

    Closure, and the three things that have to be true at once:

     * **The angles sum to exactly 360**, by construction - see the drift note.
     * **The rises sum to exactly zero.** Any residual is put on the leg with the
       most room to carry it, never spread, because a rise needs
       ``length >= sqrt(330 * rise)`` or it is a crease.
     * **The walk has to come back to the same point in plan.** The raw fit was
       59.7 units out, 2.4% of the lap. The lengths below - never the angles -
       were then corrected by minimum-norm least squares: lengthening a straight
       translates everything downstream along its own heading, so this is two
       equations in fifteen knobs, and what is left after rounding is what
       ``tracks/solver.py`` shuts with the two ``FREE`` legs.

    Those two are the harbour front and the pit straight, and **the first pair
    tried was singular.** Beau Rivage and the harbour front are the lap's two
    longest straights, which is what Silverstone's rule picks - but at Monaco they
    run back down the same side of the harbour, near enough anti-parallel that
    between them they span one direction rather than the plane, and the solve ran
    away to a negative length. The pair below is **85 degrees apart**, chosen by
    maximising heading separation against length rather than by taking the two
    longest. Neither is a named corner, which is the whole reason to nominate
    rather than let the solver reach for one.

    One more thing this fit got wrong first, worth writing down because it looked
    fine: **a checkpoint hosted inside a corner has to keep the corner's angle.**
    The tunnel and the run between the two halves of the Swimming Pool are both
    curves, and splitting one into two arcs either side of a gate by holding the
    *radius* and shortening the arcs quietly drops the angle the gate's straight
    now occupies - 9 degrees of the lap's 360 across the two of them. The heading
    then does not close, the position is a hundred units out, and the solver
    refuses. Split by holding the **angle** and letting the radius take it.

    **Three numbers here sit outside the pool's range, and all three are the same
    fact.** `tools/pool_stats.py` flags 48 corners against a pool that tops out at
    26, a median radius of 68 against 53, and a maximum of 589 against 300. A
    street circuit surveyed at one metre resolves into more arcs than a
    purpose-built one does, and a lot of them are the long shallow drift a city
    street carries - so the count is high and the median is dragged up by bends
    nobody would call corners.

    **Unlike Silverstone, the radius is deliberately not capped at 300.** That cap
    is right there and would be wrong here, and the reason is the scale: at
    0.4586 units per metre Silverstone's gentle bends measured 1180 to 2430 units
    and were straights with a rounding error. At 0.75 the same real radius is
    two-thirds larger a number for a bend a third as gentle - Monaco's biggest is
    589 units carrying 9.6 degrees over 99 units, which is a sweep you can see out
    of the car rather than a runway. Capping it would tighten a real road for the
    sake of a statistic.

    **There is no run-off anywhere and that is the track.** Every other circuit
    in the pool can be run wide for the price of some grass or gravel; here the
    barrier is on the kerb for the whole lap, as a ribbon ``rail``, and going off
    line costs the lap rather than a second. See the note on ``ground`` above for
    why that is the sanctioned path here and a fight everywhere else.

    It also settles the thing Silverstone had to be fixed for. ``tools/cut_check.py``
    finds **216 chords on this lap that would pay** as a shortcut - the road they
    skip is more than twice their own length - and **none of them is open**. On
    Silverstone two whole complexes could be driven across and it took a
    checkpoint and a barrier in ``scenery.js`` to close them; here the walls do it
    everywhere, for free, because there is nowhere on the lap that is not walled.
    """
    # A checkpoint lays CP units of its own road (`cp`'s pre + post), and `start`
    # lays PRE before the line and RUN after it. All three come out of the leg
    # that hosts them, or the six gates on this lap walk the ribbon 200 units past
    # its own start. RUN is 30 rather than Silverstone's 44 because `start` lays
    # its run *flat* and there is only so much pit straight before the harbour
    # bend. **Two of the five checkpoints are hosted inside corners** - the tunnel
    # and the run between the halves of the Swimming Pool - because those are the
    # only stretches long enough, and see the note above about what that costs.
    CP = 34.0
    RUN, PRE = 30.0, 14.0

    # --- the pit straight - Boulevard Albert 1er, along the harbour ----
    b.start(run=RUN)
    b.arc(9.3, 372.5, rise=2.2)
    b.arc(8.5, 156.1, rise=1.5)
    b.straight(11.1, rise=0.3)
    b.arc(-8.3, 87.6, rise=0.5)
    b.straight(8.3, rise=0.2)

    # --- Sainte Devote, and the climb up Beau Rivage -------------------
    b.width(12.0)
    b.arc(73.4, 20.5, rise=0.3)   # Sainte Devote
    b.straight(163.9 - CP, rise=6.8)
    b.cp()
    b.arc(6.7, 129.2, rise=0.1)
    b.straight(28.9, rise=2.3)
    b.arc(-19.2, 67.0, rise=1.4)
    b.straight(41.6, rise=4.3)
    b.arc(10.3, 117.3, rise=1.2)
    b.straight(18.9, rise=0.7)
    b.arc(8.9, 77.4)
    b.straight(28.9, rise=1.7)

    # --- Massenet and Casino Square - the top of the hill --------------
    b.width(11.0)
    b.arc(-51.3, 71.2, rise=5.5)   # Massenet
    b.arc(-34.1, 36.5)   # Massenet
    b.arc(-44.1, 66.2, rise=5.2)   # Massenet
    b.straight(9.5)
    b.arc(70.4, 30.5, rise=1.1)   # Casino
    b.arc(13.3, 64.8, rise=-0.3)

    # --- Mirabeau, the hairpin, and the drop to the sea ----------------
    b.straight(116.0 - CP, rise=-7.0)
    b.cp()
    b.width(10.5)
    b.arc(140.7, 20.2, rise=-3.8)   # Mirabeau Haute
    b.arc(-30.9, 43.2, rise=-1.1)
    b.straight(13.8)
    b.arc(10.6, 68.8)
    b.width(9.5)
    b.arc(-198.8, 14.0, rise=-4.5)   # the Grand Hotel hairpin
    b.arc(7.2, 83.7, rise=-0.3)
    b.straight(8.9, rise=-0.2)
    b.width(10.5)
    b.arc(112.8, 20.2, rise=-4.4)   # Mirabeau Bas
    b.arc(-7.9, 75.8, rise=-0.3)
    b.arc(6.4, 141.3, rise=-0.7)
    b.arc(20.6, 31.2, rise=-0.4)
    b.arc(87.7, 13.7, rise=-1.2)   # Portier

    # --- the Tunnel ----------------------------------------------------
    b.width(13.0)
    b.arc(31.4, 294.9, rise=-8.0)   # the Tunnel
    b.cp()
    b.arc(31.4, 294.9, rise=-6.6)
    b.arc(7.8, 82.8, rise=-0.1)
    b.arc(9.6, 589.0, rise=6.4)

    # --- the Nouvelle Chicane, and the harbour front -------------------
    b.width(11.0)
    b.arc(-77.0, 13.4)   # Nouvelle Chicane
    b.arc(114.1, 15.1, rise=-1.7)   # Nouvelle Chicane
    b.arc(-34.1, 25.2)   # Nouvelle Chicane
    b.width(12.5)
    b.straight(FREE(124.6 - CP), rise=-2.9)
    b.cp()

    # --- Tabac and the Swimming Pool -----------------------------------
    b.width(11.0)
    b.arc(-56.9, 38.5, rise=-0.6)   # Tabac
    b.arc(-7.6, 129.6, rise=-0.4)
    b.arc(-21.0, 155.3, rise=-2.5)   # Piscine, entry
    b.arc(-17.1, 50.1, rise=-0.3)
    b.arc(-31.3, 34.3, rise=-0.4)   # Piscine, entry
    b.arc(46.3, 30.6, rise=-0.6)   # Piscine
    b.arc(-3.0, 358.4, rise=-0.9)
    b.cp()
    b.arc(-3.0, 358.4, rise=-0.9)
    b.arc(72.1, 18.5, rise=0.4)   # Piscine, exit
    b.arc(-77.2, 23.4, rise=0.4)   # Piscine, exit
    b.arc(-8.0, 242.0, rise=0.4)
    b.arc(-36.7, 100.6, rise=3.1)

    # --- La Rascasse, Anthony Noghes, and back onto the line -----------
    b.width(10.5)
    b.arc(139.3, 17.3, rise=2.8)   # La Rascasse
    b.straight(10.4)
    b.arc(17.7, 80.1, rise=1.0)
    b.arc(79.1, 17.9, rise=1.2)   # Anthony Noghes
    b.arc(-29.0, 56.3, rise=0.6)
    b.arc(6.1, 105.8, rise=-0.4)
    b.straight(12.0, rise=-0.4)
    b.width(12.5)
    b.arc(15.2, 101.9, rise=-0.5)
    b.straight(FREE(97.8 - PRE), rise=-0.3)

    # The ribbon is back on top of station 0, and the line is already there.
    b.finish_at_start()
