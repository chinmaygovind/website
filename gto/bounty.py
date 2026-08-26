"""The bounty side game, and what it is actually worth.

The rule as played: **win three hands in a row and everybody pays you $1. Four
in a row, $2. Five or more, $3 - every hand, until you lose one.** It is
symmetric, so the hero pays it out as often as he collects it.

Sizes are quoted in dollars but stored in big blinds, because the whole point of
a trainer is that the advice does not change when the stakes do. At the game's
own 0.25/0.25 the ladder is 4bb, 8bb and 12bb **from each opponent** - so at a
six-handed table a fifth straight win is worth 60bb, which is more than a third
of a buy-in for winning one more pot. That is not a garnish on the game. It is
occasionally the biggest number on the table.

**Why the review cannot ignore it.** A player two wins into a streak is holding
an option, and the option has value whether or not he exercises it. Calling a
river bet closes it; folding does not, because a fold loses the hand and breaks
the streak just as surely as losing at showdown. Only *winning* keeps it. So the
correct adjustment is not "gamble more" - it is that the **gap between winning
and not winning this pot is larger than the pot**, by exactly the continuation
value computed here.

``streak_value`` is that gap. ``review.py`` adds it to the pot when it prices a
decision, and the review shows the bounty-adjusted number beside the plain one
so it is always visible how much of the answer came from the side game rather
than the poker.
"""

#: Consecutive wins -> dollars collected from **each** opponent. The ladder tops
#: out; a tenth straight win pays the same as a fifth.
LADDER = {3: 1.0, 4: 2.0, 5: 3.0}
LADDER_TOP = 3.0

#: What the ladder was written for. Everything scales off this so that changing
#: the blinds in the gear menu changes the bounty with them.
REFERENCE_BB_DOLLARS = 0.25


def payout_dollars(streak):
    """Dollars from each opponent for reaching this streak length."""
    if streak < 3:
        return 0.0
    return LADDER.get(streak, LADDER_TOP)


def payout_bb(streak, bb_dollars=REFERENCE_BB_DOLLARS):
    """The same, in big blinds, so advice survives a change of stakes."""
    if bb_dollars <= 0:
        return 0.0
    return payout_dollars(streak) / bb_dollars


def collect(streak, opponents, bb_dollars=REFERENCE_BB_DOLLARS):
    """Total big blinds collected this hand for reaching ``streak``."""
    return payout_bb(streak, bb_dollars) * opponents


def streak_value(current_streak, opponents, win_rate=None,
                 bb_dollars=REFERENCE_BB_DOLLARS, horizon=6):
    """How much more a win is worth than a non-win, in big blinds.

    ``current_streak`` is wins already banked *before* this hand. Winning takes
    it to ``current_streak + 1`` and keeps the option alive; anything else -
    losing at showdown, folding, chopping - sends it back to zero. So this is

        value(streak + 1) - value(0)

    where ``value(n)`` is the immediate payout at ``n`` plus the discounted worth
    of possibly continuing from there. ``win_rate`` is the chance of winning any
    given hand, which at a six-handed table is about 1/6 for an average player
    and which the caller should pass from the hero's own measured figure once
    there is one.

    ``horizon`` bounds the recursion. Six is far past the point where the
    discounted tail matters, since continuing requires winning every hand in
    between.
    """
    if opponents <= 0 or bb_dollars <= 0:
        return 0.0
    if win_rate is None:
        win_rate = 1.0 / (opponents + 1)

    def value(streak, depth):
        immediate = collect(streak, opponents, bb_dollars)
        if depth >= horizon:
            return immediate
        # Continuing is worth the chance of winning again times the value of
        # being one further up the ladder. Not winning is worth nothing extra -
        # the streak is gone either way, so it is not part of the difference.
        return immediate + win_rate * value(streak + 1, depth + 1)

    return value(current_streak + 1, 0) - value(0, 0)


def describe(current_streak, opponents, bb_dollars=REFERENCE_BB_DOLLARS,
             win_rate=None):
    """The sentence the review prints when the bounty changed the answer."""
    if current_streak <= 0:
        return None
    extra = streak_value(current_streak, opponents, win_rate, bb_dollars)
    if extra < 0.5:
        return None
    nxt = current_streak + 1
    due = payout_dollars(nxt) * opponents
    if due > 0:
        return (
            f"You are on {current_streak} in a row. Winning this pot pays "
            f"${due:.0f} in bounties on top of it, so the hand is worth about "
            f"{extra:.1f}bb more than the pot says."
        )
    return (
        f"You are on {current_streak} in a row. Winning does not pay yet, but it "
        f"is the step to a bounty, worth about {extra:.1f}bb."
    )


class Streaks:
    """Who is on what streak. One of these per session."""

    def __init__(self, names):
        self.streak = {n: 0 for n in names}
        self.paid = {n: 0.0 for n in names}

    def settle(self, winners, bb_dollars=REFERENCE_BB_DOLLARS):
        """Record a finished hand. Returns the transfers in dollars.

        A **chop breaks everybody's streak**, including a winner's. Sharing a pot
        is not winning it, and the alternative - letting two players both
        advance - makes a three-way chop a way of manufacturing bounties.
        """
        transfers = {}
        sole = winners[0] if len(winners) == 1 else None

        for name in self.streak:
            if name == sole:
                self.streak[name] += 1
            else:
                self.streak[name] = 0

        if sole is None:
            return transfers

        n = self.streak[sole]
        due = payout_dollars(n)
        if due <= 0:
            return transfers

        others = [x for x in self.streak if x != sole]
        for name in others:
            transfers[name] = -due
            self.paid[name] -= due
        transfers[sole] = due * len(others)
        self.paid[sole] += due * len(others)
        return transfers

    def to_dict(self):
        return {"streak": dict(self.streak), "paid": dict(self.paid)}

    @classmethod
    def from_dict(cls, d):
        s = cls(list(d["streak"]))
        s.streak.update(d["streak"])
        s.paid.update(d["paid"])
        return s
