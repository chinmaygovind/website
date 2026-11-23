"""High Roller

A toy car loose in a giant casino: through the slots, up a playing card onto
the craps table, over the dice, across to the roulette wheel and round it back
down to the carpet, then back under the table you were just on.
"""

from tracks.builder import FREE

slug = "casino"
name = "High Roller"
difficulty = 5
# Set by hand, as Playground's were: no board to cut from yet. Gold is 0.85 of
# the 39.0s ideal; re-cut with tools/set_medals.py once laps exist.
medals = (33.3, 34.5, 36.1)
ground = -1.2
order = 360
width = 15.0
closed = True
scenery = True

# Height of the craps table's felt. The roulette table is TABLE - 3, because the
# jump between them lands lower than it leaves.
TABLE = 14.0
# Height of the blackjack table, the second climb.
BJ = 9.0
# The craps gate's width: the table is centred on the road's long run, 20
# units each side of it (the card's top edge is that far: 4 of straight and a
# radius-16 turn), and the gate spans it to just inside the rails. It cannot
# be much wider than this: `self_proximity` reads a straight whose half-width
# jumps from 11 to over 19 as the road running into itself.
GATE_CRAPS = 37.0


def build(b):
    """A figure-eight, so its turning sums to zero rather than 360.

    The crossing is the point of it: the run back north passes under the gap
    between the two tables, so the jump you made a lap ago is overhead. The
    clearance is the whole of TABLE, which is far past CROSS_CLEAR and well
    over the 4.3 units the chase camera rides.
    """
    # --- the slot floor: a weave between the rows ---------------------------
    b.start(run=40)
    b.arc(-45, 30).arc(90, 30).arc(-45, 30)
    b.straight(40)
    b.arc(90, 34)

    # --- chip stacks: a slalom round five towers ---------------------------
    b.arc(-40, 24).arc(80, 24).arc(-80, 24).arc(80, 24).arc(-40, 24)
    b.cp()

    # --- up a playing card onto the craps table ------------------------------
    # The ramp *is* the card: `skin` draws no tarmac, and scenery.js lays a
    # giant ace of spades through these stations, bent the way the eased climb
    # bends. Far longer than sqrt(330 * 14) = 68, because the pad has the car
    # at 60 at the lip.
    b.boost(16)
    b.skin(True)
    b.straight(161, rise=TABLE)

    # --- the craps table: the felt is the road, dice tumbling across it -------
    # Turned onto at once so the road runs the table's whole length, which is
    # what makes it a craps table (about 2.5 to 1) and not a square of felt.
    b.width(22.0)
    b.straight(4)
    b.arc(90, 16)
    b.straight(46)
    # A gate on every table, because dropping off one onto the carpet would
    # otherwise be a shortcut - and each spans its whole table, so it asks
    # "did you drive the table" rather than "did you hit this strip of it". A
    # gate is as wide as the road under it, and this road is felt with no
    # surface of its own, so widening it here costs nothing you can see.
    # Only 10 units either side of it wide, and the rest of the run normal:
    # wide stations more than 30 apart along a straight read as the road
    # running into itself.
    b.width(GATE_CRAPS)
    b.cp(pre=10, post=10)
    b.width(22.0)
    b.straight(21)
    b.skin(False)

    # --- the big one: off the end of the table onto the roulette table ------
    # The landing is the roulette layout, so it is felt too.
    b.width(15.0)
    b.crest(1.5, 8)
    b.gap(36, drop=4.5)
    b.skin(True)
    b.width(24.0)                        # the whole betting layout
    b.straight(14)
    b.cp()
    b.skin(False)

    # --- round the wheel and down to the carpet -----------------------------
    b.width(15.0)
    b.arc(-270, 46, rise=-(TABLE - 3))

    # --- back under the gap, through the slot machine -----------------------
    b.width(15.0)
    b.straight(40)                          # under the gap: the jump is overhead
    b.cp()
    b.boost(14)
    b.straight(60)

    # --- switchback, then up onto the blackjack table ------------------------
    b.arc(-90, 16)
    b.straight(FREE(22))
    b.arc(90, 16)
    b.arc(-90, 20)
    b.boost(14)
    b.skin(True)                         # the queen of hearts
    b.straight(100, rise=BJ)             # pad-fed, so well past sqrt(330 * 9)

    # --- round the blackjack table's curved edge ----------------------------
    b.width(20.0)
    b.arc(90, 32)
    b.straight(7)
    b.width(32.0)                        # rail to dealer's tray
    b.cp(pre=10, post=10)
    b.width(20.0)
    b.straight(7)
    b.arc(90, 32)
    b.skin(False)

    # --- off the table and home ---------------------------------------------
    b.arc(-90, 25)                       # still the table's width: funnels, not a step
    b.width(15.0)
    b.straight(FREE(84), rise=-BJ)
    b.arc(90, 25)
    b.straight(74)                       # pays back the craps table's length
    b.finish_at_start()
