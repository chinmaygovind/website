"""Monza

The Temple of Speed. Four straights, three chicanes, and a ruin overhead.
"""

from tracks.builder import FREE

slug = "monza"
name = "Monza"
difficulty = 4
ground = -1.2
order = 220
# Fifteen, against Silverstone's sixteen and Monaco's twelve, and it opens to
# **twenty through the Parabolica** - the widest road anywhere in the pool. That
# is the one width here chosen for the driving rather than for the place: the
# corner is a 166-degree increasing-radius sweep onto the longest straight in
# the game, so the line through it is worth making a choice rather than a path.
# The chicanes go the other way, down to thirteen, because a chicane you can
# take two ways is not a chicane.
width = 15.0
closed = True
# The Sopraelevata roofing the Serraglio, the braking boards, and the Alps. See
# `scenery.js` - the banking is the only derelict structure in the game, and the
# reason Monza is worth building rather than being a third fast circuit.
#
# **One change here is outside this folder, which is the thing that is supposed
# to need saying.** The scatter's tree kinds were conifer, bigpine, deadtree,
# palm and rock - every tree in the game was a conifer, and a wood full of
# conifers is the Ardennes, which is Spa. The Parco di Monza is oak and
# hornbeam, so `broadleaf` was added to `addScenery` in `trackmesh.js`: a bare
# trunk that forks, one wide crown, and the bottom third clear, which is the
# whole difference from a conifer at any distance.
#
# It is a new *branch*, not a new `export`, so it is not the deploy hazard that
# file's un-tokened `import` usually is - a cached copy that has never heard of
# the kind matches nothing and draws no tree, so for up to nginx's hour this
# track's wood is thin and every other track is untouched. `CACHE` in `sw.js`
# was bumped in the same change.
scenery = True
# No `medals` yet and no `hotlap.json`: both are cut from a lap somebody has
# actually driven and nobody has driven this. `NO_CUT_MEDALS_YET` in
# tests/conftest.py is what says so out loud. Set a lap, run
# `tools/set_medals.py monza` and `tools/hotlap.py monza`, and drop the entry.


def build(b):
    """Monza, off its own surveyed centreline, and the pool's fourth closed lap.

    **Nothing below was drawn by eye.** Same method as Silverstone and Monaco,
    and the same reason: every corner here is a real place, and a corner authored
    by feel is a corner that is not Monza. OpenStreetMap carries the circuit as
    relation **284565** (``type=circuit``); its twenty member ways were walked
    from the start-finish node with the pit lane dropped, and **the graph closed
    on the first try** - every endpoint degree two, no odd nodes, all twenty ways
    used. It measures **5798.1 m against the official 5793 m**, 0.09% out, with
    total turning of exactly **-360.00 degrees**, which is the check that the
    walk found a real lap rather than a plausible one. Every named corner came
    back out of the data with its own name on it.

    The centreline was resampled at one metre and segmented on curvature. Three
    passes on top of that, and each one changed the answer:

     * **One curvature field cannot see this circuit.** The chicanes are 19-unit
       radii over 30 units of road and need a short baseline; Curva Grande is a
       192-unit radius held for 268 units, and at that same short baseline its
       surveyors' node jitter reads as *twenty* corners. A single field either
       shatters the Curva or misses the chicanes. So there are two - a fine one
       to find anything tighter than radius 60, a coarse one to measure
       everything else - and Curva Grande comes back as the single arc it is.
     * **Angles are measured off heading change, not off curvature.** Averaging
       the curvature over an arc and multiplying by its length put **63 degrees**
       of this lap in legs too gentle to be corners, which folded back would have
       grown every corner by a fifth. Taking each leg's angle as the exact
       heading change between its ends puts the drift at **5.31 degrees**, and
       that is the real number. It is spread back across the arcs in proportion
       to their turn, so the angles below still sum to exactly 360 and no corner
       is more than **1.5%** off the angle it really is.
     * **The resampler dropped a step at every original node.** 5798 m came back
       as 5507, which is one metre per node across 293 of them - and because the
       nodes are dense in the corners and sparse down the straights, it was
       shortening the corners preferentially. It is cumulative-arclength now.

    **Lengths are scaled at 0.55 units per metre** - Silverstone is 0.4586, Spa
    0.4522, Monaco 0.75 - and that number is the whole argument of this track.
    At Silverstone's scale the Variante del Rettifilo comes out at **radius 10**,
    under the engine's hard floor of 12, and all three chicanes would have to be
    authored rather than measured, which is to say invented. At Monaco's the lap
    is 4340 units, a third longer than Big Red. At 0.55 the lap is **3192 units**
    - second in the pool, beside Spa's 3167 - and the tightest corner on it is
    **19.2**, which clears the floor with room to spare. Nothing here is
    authored round a limit.

    Heights are the EU-DEM 25 m model sampled every 20 m along the same line and
    smoothed over +/-100 m, at **0.80 units per metre**: **8.0 units** of total
    relief, against Silverstone's 17 and Spa's 63. Being the flat one is the
    point rather than a shortcoming - it is what makes this a speed circuit.
    **The raw model is wrong here in the way Monaco's was wrong over the tunnel,
    and for the same class of reason**: it returned an 18.7 m range across a site
    whose published relief is about 10, because Monza is a wood and the trees are
    20-30 m tall, so in the closed canopy a 25 m DEM is reading treetops. The
    profile is rescaled onto the published range rather than trusted at its
    peaks. What survives that is the right shape: the low point is the
    Parabolica, the high point the Lesmo woods, which is the real place.

    Closure, and the three things that have to be true at once:

     * **The angles sum to exactly 360**, by construction - see the drift note.
     * **The rises sum to exactly zero**, and the residual is put on the longest
       leg rather than spread, because a rise needs ``length >= sqrt(330 * rise)``
       or it is a crease. Nothing here comes close: the worst leg needs 38 units
       and has 500. **The rise is distributed only across legs that can carry
       it** - ``start`` and ``cp`` lay their road *flat*, so rise handed to a
       gate is silently dropped and the lap stops closing in height.
     * **The walk has to come back to the same point in plan.** The raw fit was
       **19.0 units out, 0.6% of the lap** - against Monaco's 59.7 and 2.4% -
       and the lengths, never the angles, were then corrected by minimum-norm
       least squares. What is left after rounding is what ``tracks/solver.py``
       shuts with the two ``FREE`` legs.

    Those two are the pit straight and the Serraglio, and they were chosen by
    **maximising heading separation against length** rather than by taking the
    two longest, which is the trap Monaco's docstring records: two long straights
    that happen to run anti-parallel span one direction rather than the plane,
    and the solve runs away. These are **43.6 degrees apart**.

    **The lap does not end mid-corner, and it took a fold to arrange that.** The
    survey's last leg was a 2.79-degree arc at radius 339 - nearly straight, but
    an arc, and the road either side of the seam has to be going the same way.
    Legs 24 and 26 were both Curva Alboreto with the Parabolica exit straight
    between them, so the trailing 2.79 degrees is folded into leg 24, which keeps
    the angle total and the length total exactly and leaves the exit straight
    closing the lap - which is what it is in reality.

    **The four boost pads are the one thing here that is not Monza.** They were
    asked for, and they run against the rule in ``Builder.boost``'s own
    docstring: a pad belongs where the speed is usable, and never into a braking
    zone, where all it does is take away the decision the corner was for. This is
    the exception, and it is worth having because at Monza the decision *is* the
    braking. **Every pad stops 110 units short of its corner**, which is the real
    200-metre board at this scale - so the speed is carried in and the braking is
    still yours. ``scenery.js`` puts the boards themselves at 110, 83, 55 and 28,
    and they are the reason this is a skill rather than a memory test: without
    them a pad into a chicane is a corner you learn by failing.

    **The chicane-escape barriers this track was going to need do not exist, and
    that is a measurement rather than an omission.** `tools/cut_check.py` finds
    **633 chords on this lap that would pay** as a shortcut - three chicanes is
    exactly the shape that produces them, and Silverstone needed two hand-built
    barriers in `scenery.js` for the same reason - and **none of them is open**.
    The armco backstop at 30 units already stands across every one. Adding walls
    would have been dead geometry in the collider and a slower anti-cheat.

    Two consequences worth stating out loud. **Medals get harder, not easier** -
    ``laptime.py`` models pads when it derives the three times, so it will assume
    the speed is carried and the braking is perfect, and gold will mean using all
    four. And **a pad does not compound a tow**: the two take the larger of the
    pair rather than the product, which matters here more than anywhere in the
    pool, because a 520-unit straight makes this the one track where people are
    really slipstreaming.
    """
    # A checkpoint lays 34 units of its own road (`cp`'s pre + post), and `start`
    # lays 14 before the line and `run` after it. All of that comes out of the
    # leg that hosts it, and the lengths below are already net of it - unlike
    # Spa and Monaco, which carry the subtraction in the source. It is done here
    # because this lap was emitted from the survey rather than typed, and a
    # `- CP` in a generated line is arithmetic nobody can check against the
    # measurement it came from.
    #
    # **Five gates, and not one of them is inside a corner.** That is this
    # circuit rather than care: its straights are long enough that there was
    # always somewhere to put one, which is exactly what Monaco could not say.

    # --- Rettifilo Tribune: the start/finish straight, and the first pad ----
    b.start(run=30.0)
    b.boost(45.0, rise=0.21)
    b.straight(80.0, rise=0.37)
    b.boost(50.0, rise=0.23)
    b.straight(FREE(130.7), rise=0.60)
    b.boost(60.0, rise=0.28)
    b.straight(110.0, rise=0.51)

    # --- Variante del Rettifilo (T1-2) --------------------------------------
    b.width(13.0)
    b.arc(91.81, 19.6, rise=0.47)   # Variante del Rettifilo
    b.arc(-111.83, 19.2, rise=0.42)   # Variante del Rettifilo
    b.width(15.0)
    b.boost(20.0, rise=0.22)
    b.straight(8.6, rise=0.10)

    # --- the sweep into Curva Grande, nee Curva Biassono (T3) ---------------
    b.arc(19.21, 188.7, rise=0.99)
    b.straight(4.0, rise=0.14)
    b.cp()
    b.straight(18.6, rise=0.66)
    b.width(16.0)
    b.arc(80.19, 191.8, rise=-0.25)   # Curva Biassono

    # --- the run to the Roggia, and the second pad --------------------------
    b.width(15.0)
    b.straight(32.7, rise=0.13)
    b.boost(45.0, rise=0.17)
    b.straight(110.0, rise=0.42)

    # --- Variante della Roggia (T4-5) ---------------------------------------
    b.width(13.0)
    b.arc(-68.68, 28.0, rise=-0.38)   # Variante della Roggia
    b.arc(60.25, 31.9, rise=-0.35)   # Variante della Roggia
    b.width(15.0)
    b.arc(-7.22, 235.7, rise=-0.19)

    # --- Curva di Lesmo 1 and 2 (T6-7) --------------------------------------
    b.straight(20.0, rise=0.38)
    b.cp()
    b.boost(28.0, rise=0.54)
    b.straight(18.3, rise=0.35)
    b.width(14.0)
    b.arc(104.13, 52.4, rise=-1.26)   # Lesmo 1
    b.width(15.0)
    b.boost(35.0, rise=-0.29)
    b.straight(65.8, rise=-0.55)
    b.width(14.0)
    b.arc(17.32, 63.7, rise=0.59)   # Lesmo 2
    b.arc(49.87, 35.4, rise=1.02)   # Lesmo 2

    # --- Curva del Serraglio, and the third pad -----------------------------
    b.width(15.0)
    b.straight(40.0, rise=0.18)
    b.boost(50.0, rise=0.22)
    b.straight(77.9, rise=0.35)
    b.arc(-11.48, 326.7, rise=-0.19)   # Curva del Serraglio
    b.straight(23.0, rise=-0.18)
    b.cp()
    b.boost(35.0, rise=-0.27)
    b.straight(FREE(62.8), rise=-0.48)
    b.boost(50.0, rise=-0.38)
    b.straight(110.0, rise=-0.84)

    # --- Curva Vialone into the Variante Ascari (T8-9-10) -------------------
    b.width(14.0)
    b.arc(-55.84, 41.8, rise=-0.29)   # Curva Vialone
    b.arc(58.56, 68.9, rise=-0.21)   # Variante Ascari
    b.arc(-45.13, 48.9, rise=-0.51)   # Variante Ascari

    # --- the back straight, and the fourth pad ------------------------------
    b.width(15.0)
    b.boost(40.0, rise=-0.37)
    b.straight(70.0, rise=-0.65)
    b.boost(45.0, rise=-0.42)
    b.straight(94.0, rise=-0.88)
    b.cp()
    b.straight(46.7, rise=-0.44)
    b.boost(60.0, rise=-0.56)
    b.straight(110.0, rise=-1.03)

    # --- Curva Parabolica, since 2021 Curva Alboreto (T11) ------------------
    b.width(20.0)
    b.arc(165.64, 69.1, rise=-0.15)   # Curva Alboreto
    b.arc(13.20, 157.6, rise=0.56)   # Curva Alboreto
    b.width(15.0)
    # **No gate on the Parabolica exit.** There was one 70 units before the
    # line, which on a lap whose finish *is* its start line is a gate you cross
    # twice within four seconds and which credits nothing the finish does not
    # already credit. Four gates now, at 701, 1373, 1910 and 2617, and the long
    # closing sector is the Parabolica and the pit straight - which is how the
    # real circuit is timed too.
    b.boost(45.0, rise=0.37)
    b.straight(77.1, rise=0.64)

    # The ribbon is back on station 0 and the line is already there.
    b.finish_at_start()