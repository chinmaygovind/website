"""Suzuka

The figure-eight. Japan's only crossover circuit, compressed, and the one
track in the pool that drives over itself.
"""

slug = "suzuka"
name = "Suzuka"
difficulty = 4
ground = -1.2
order = 250
width = 14.0
closed = True
# The crossover bridge, the wall across the Casio chicane, and the Ferris
# wheel behind the esses. Everything else this track wears - grandstands,
# hoardings, armco, the pit building - is Spa's `furniture` block, which is
# general and needed nothing new.
scenery = True


def build(b):
    """Suzuka, traced from the circuit rather than remembered.

    The other real circuits in this pool were authored from a mental picture of
    the place, and it shows the moment you hold one next to a map. This one was
    not. The centreline was lifted out of the published circuit diagram,
    resampled at four units, and cut into constant-curvature runs by measuring
    the turning of the actual line; the angles and radii below are what came
    out of that, scaled by 0.88. So Degner 2 really is 82 degrees on a 29
    radius, and 130R really does open from 60 to 160, because that is what the
    circuit does - not what a corner of that name felt like it ought to do.

    Four things fall out of the tracing and all of them are load bearing:

     * **The corner angles sum to exactly zero**, not to 360. A figure-eight is
       an immersed curve of rotation number 0: one lobe is walked clockwise and
       the other anticlockwise, and they cancel. Spa closes its heading by
       summing to a full turn; this closes by summing to none. Change one angle
       and you must take the same amount out of another, or the seam is a kink
       and no solver will save you - `tracks/solver.py` moves lengths, not the
       sum of the angles.
     * **Almost none of the "straights" are straight.** The run out of the
       hairpin bends, the run to Spoon bends, and the back straight is a
       1172-radius left for its entire length. Transcribing those as straights
       and pushing their turning into the neighbouring corners is the obvious
       simplification, and it is wrong by 108 units - that is how far off its
       own start the ribbon lands. They are arcs here because they are arcs
       there.
     * **The lengths are solved, not authored.** With the angles fixed, the end
       position is an exactly linear function of the straight lengths, so the
       closure was solved as a minimum-norm correction spread across every
       straight at once instead of dumped on one or two. That is why nothing is
       visibly distorted: the worst leg moves 12%, where closing on a single
       pair of legs needed 55% and closing on the pit straight alone needed
       more than the solver's own guard allows.
     * **A checkpoint here costs no road.** Every gate lays 34 units of its own
       straight, and nine of those is 306 units the circuit did not have. The
       first attempt let the lap grow and re-closed it, which squeezed the
       shape: where the Degner run passes the 130R run the real gap is 36 units
       and the ribbon came out with 8, which `self_proximity` correctly called a
       car trap. So each gate is paid for by the leg that hosts it - a straight
       gives up 34 units of length, and an arc gives up 34 units of length by
       shrinking its radius while keeping its angle, which leaves both the
       turning and the total length exactly where they were.

    The elevation is the real profile, and it is most of why the place drives
    the way it does. It climbs the whole way from the first corner through the
    esses to Dunlop, which is the high point; falls off the edge of the hill at
    Degner; bottoms out at the hairpin; and then climbs for the entire length
    of the back straight - which is what puts that straight over the top of the
    Degner exit rather than into it.
    """
    b.start(run=199.79)
    b.arc(186.22, 54.15, rise=2.13)  # T1-T2 First Turn
    b.straight(14.42, rise=0.63)
    b.cp()
    b.straight(14.42, rise=0.23)
    b.width(12.5)
    b.arc(-62.55, 51.59, rise=2.19)  # T3
    b.arc(81.85, 64.07, rise=3.57)  # T4
    b.arc(-73.59, 65.77, rise=3.29)  # T5
    b.arc(109.90, 66.06, rise=4.94)  # T6
    b.width(14.0)
    b.arc(-80.06, 83.56, rise=3.99)  # T7 Dunlop
    b.cp()
    b.arc(-80.06, 83.56, rise=-6.99)
    b.straight(58.07, rise=-4.01)
    b.arc(42.33, 42.88, rise=-2.48)  # T8 Degner 1
    b.straight(37.06, rise=-3.50)
    b.width(13.0)
    b.arc(82.05, 29.50, rise=-4.01)  # T9 Degner 2
    b.straight(61.02, rise=-2.71)  # under the bridge
    b.cp()
    b.straight(61.02, rise=-1.28)
    b.arc(32.58, 68.10, rise=-0.45)  # T10
    b.straight(48.11, rise=-0.55)
    b.arc(-174.93, 21.91, rise=-1.00)  # T11 Hairpin
    b.width(14.0)
    b.arc(6.13, 274.26, rise=1.38)
    b.cp()
    b.arc(72.50, 130.75, rise=3.61)  # T12a
    b.arc(9.05, 312.01, rise=1.22)
    b.arc(42.33, 152.46, rise=2.78)  # T12b
    b.straight(17.35, rise=0.76)
    b.cp()
    b.straight(17.35, rise=0.24)
    b.arc(-204.67, 56.17, rise=-1.99)  # T13-T14 Spoon
    b.width(15.0)
    b.arc(-11.73, 1171.60, rise=7.74)  # back straight OVER the bridge
    b.cp()
    b.arc(-11.73, 1171.60, rise=5.25)
    b.arc(-33.61, 60.00)  # T15 130R a
    b.arc(-5.87, 240.61)
    b.arc(-15.12, 160.10, rise=-0.88)  # T15 130R b
    b.arc(-1.39, 809.05, rise=-1.12)
    b.cp()
    b.arc(-4.18, 809.05, rise=-2.99)
    b.width(11.5)
    b.arc(92.51, 39.24, rise=-2.49)  # T16 Casio
    b.arc(-84.43, 26.28, rise=-1.52)  # T17 Casio
    b.width(14.0)
    b.arc(86.47, 104.95, rise=-4.01)  # T18
    b.width(14.0)
    b.straight(57.51, rise=-0.43)  # pit straight to the line
    b.cp()
    b.straight(121.35, rise=-1.57)

    b.finish_at_start()
