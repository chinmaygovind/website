"""Equity: how often a holding wins, given what is already known.

Everything in the instant review comes from here - pot odds, break-even
frequencies, the EV of a call. It answers one question, ``showdown_equity``, and
answers it **exactly** whenever exact is affordable, falling back to sampling
only when it is not:

===========  ====================  ==========================================
street       runouts to enumerate  what this module does
===========  ====================  ==========================================
river        1                     exact, one evaluation each
turn         44                    exact
flop         990                   exact, ~20ms heads-up
preflop      1,712,304             sampled, because exact is 38 seconds
===========  ====================  ==========================================

That table is the whole design. A trainer that reports a river call as "you
needed 31.2% and had 30.8%" must not have arrived at those numbers by sampling -
the difference between them is smaller than the sampling error would be. Postflop
is where the close decisions are, postflop is exactly where exact enumeration is
cheap, so postflop is never sampled.

**Ties are split, not counted as wins.** A player who chops a three-way pot gets
1/3 of that runout, so the returned equities always sum to 1. Counting a chop as
a win overstates the value of hands that play for chops - low flushes, counterfeit
two pairs, boards that play - which are precisely the hands a home game
overvalues, and precisely the mistake this tool exists to catch.
"""

import itertools
import random
from math import comb

from cards import DECK
from evaluator import evaluate

#: Enumerate rather than sample when the number of runouts is at or under this.
#: 1,000 runouts is about 20ms heads-up, which is imperceptible in a review and
#: covers every postflop street. Preflop is 1.7 million and falls through to
#: sampling.
EXACT_LIMIT = 2000

DEFAULT_ITERS = 20000


def _remaining_deck(dead):
    dead = set(dead)
    return [c for c in DECK if c not in dead]


def _score_runout(holes, board):
    """Fractional wins for one completed board. Ties split."""
    scores = [evaluate(list(h) + board) for h in holes]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    share = 1.0 / len(winners)
    out = [0.0] * len(holes)
    for i in winners:
        out[i] = share
    return out


def runout_count(board_size, players):
    """How many distinct runouts remain, given a board size and player count."""
    known = board_size + 2 * players
    return comb(52 - known, 5 - board_size)


def showdown_equity(holes, board=(), rng=None, iters=None, exact_limit=EXACT_LIMIT):
    """Each player's share of the pot, averaged over every possible runout.

    ``holes`` is a list of two-card lists, one per player still contending.
    Returns a list of floats summing to 1.

    Exact whenever the number of runouts is small enough, sampled otherwise -
    and ``was_exact`` on the returned object says which, because a review line
    that quotes a number to a tenth of a percent has to know whether it earned
    that tenth.
    """
    board = list(board)
    if len(holes) < 2:
        raise ValueError("equity needs at least two players")

    dead = list(board)
    for h in holes:
        dead.extend(h)
    if len(set(dead)) != len(dead):
        raise ValueError("a card appears twice")

    need = 5 - len(board)
    deck = _remaining_deck(dead)
    total = comb(len(deck), need) if need else 1

    if need == 0 or total <= exact_limit:
        acc = [0.0] * len(holes)
        n = 0
        for extra in itertools.combinations(deck, need):
            for i, v in enumerate(_score_runout(holes, board + list(extra))):
                acc[i] += v
            n += 1
        return Equity([a / n for a in acc], exact=True, samples=n)

    rng = rng or random.Random()
    iters = iters or DEFAULT_ITERS
    acc = [0.0] * len(holes)
    for _ in range(iters):
        extra = rng.sample(deck, need)
        for i, v in enumerate(_score_runout(holes, board + extra)):
            acc[i] += v
    return Equity([a / iters for a in acc], exact=False, samples=iters)


class Equity(list):
    """A list of per-player equities that remembers how it was computed."""

    def __new__(cls, values, exact, samples):
        self = super().__new__(cls, values)
        return self

    def __init__(self, values, exact, samples):
        super().__init__(values)
        self.exact = exact
        self.samples = samples

    @property
    def error(self):
        """One standard error on a sampled equity, or 0.0 when exact.

        Worst case p=0.5, so this is an upper bound rather than the exact
        binomial error for the observed p - which is the right way round for a
        number used to decide whether a difference is real.
        """
        if self.exact:
            return 0.0
        return 0.5 / (self.samples ** 0.5)


# ------------------------------------------------------------------ pot maths


def required_equity(to_call, pot_before_call):
    """The equity a call needs to break even.

    ``pot_before_call`` is what is in the middle *before* you put the call in,
    so a pot-sized bet faced is ``required_equity(100, 200) == 1/3``.
    """
    if to_call <= 0:
        return 0.0
    return to_call / (pot_before_call + to_call)


def pot_odds(to_call, pot_before_call):
    """The same thing said the other way: ``3.0`` means 3-to-1."""
    if to_call <= 0:
        return float("inf")
    return pot_before_call / to_call


def call_ev(equity, to_call, pot_before_call):
    """EV in chips of calling, relative to folding.

    Folding is worth 0 by definition - money already in the pot is not yours and
    is not part of this comparison. That convention is used everywhere in
    ``review.py``, so a "you lost 1.8bb by calling" line always means against the
    fold, never against some other action.

    **What you win is the pot, not the pot plus your own call.** Your call comes
    back to you when you win; it was never a gain. Counting it made every call
    look better than it is by exactly ``equity * to_call``, which is not a small
    error and not a random one - it points the same way every time, at calling
    more. It also disagreed with ``required_equity``: the two must cross zero
    together, and ``test_call_ev_is_zero_exactly_at_the_required_equity`` is
    what now holds them to it.
    """
    return equity * pot_before_call - (1 - equity) * to_call


def breakeven_bluff_frequency(bet, pot):
    """How often a bluff of this size must work to break even: ``bet/(pot+bet)``."""
    return bet / (pot + bet)


def minimum_defence_frequency(bet, pot):
    """How often the caller must continue to stop a bluff of this size printing.

    ``pot / (pot + bet)``. This is the number a home game gets wrong most often
    and in the same direction - overfolding to big bets - which is why it gets
    its own line in the review whenever the hero folds facing a bet.
    """
    return pot / (pot + bet)


# ------------------------------------------------------------ against a range


def range_equity(hero, opponents, board=(), rng=None, iters=4000, dead=()):
    """Hero's share of the pot against one or more **weighted ranges**.

    ``opponents`` is a list of ``[(card, card, weight), ...]`` - what
    ``ranges.weighted_combos`` produces. Each iteration draws one holding per
    opponent in proportion to weight, discards the draw if two opponents were
    dealt the same card, and runs the board out.

    Returns an :class:`Equity`-shaped result whose ``error`` is the honest
    sampling error, because unlike ``showdown_equity`` this one is never exact:
    the range itself is a model of somebody, and enumerating every combination
    of five opponents' ranges is not affordable at any speed.

    **Rejection rather than repair.** When two opponents draw the same card the
    whole sample is thrown away instead of being patched up, because patching it
    quietly reweights the ranges towards whatever the patch prefers.
    """
    if not opponents:
        raise ValueError("range equity needs at least one opponent")
    rng = rng or random.Random()
    board = list(board)
    known = set(hero) | set(board) | set(dead)

    tables = []
    for combos in opponents:
        usable = [(a, b, w) for a, b, w in combos
                  if a not in known and b not in known and w > 0]
        if not usable:
            raise ValueError("an opponent range is empty once cards are removed")
        total = 0.0
        cumulative = []
        for a, b, w in usable:
            total += w
            cumulative.append(total)
        tables.append((usable, cumulative, total))

    need_deck = [c for c in DECK if c not in known]
    wins = 0.0
    done = 0
    attempts = 0
    limit = iters * 12

    while done < iters and attempts < limit:
        attempts += 1
        holes = [list(hero)]
        used = set(known)
        ok = True
        for usable, cumulative, total in tables:
            pick = rng.uniform(0, total)
            lo, hi = 0, len(cumulative) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if cumulative[mid] < pick:
                    lo = mid + 1
                else:
                    hi = mid
            a, b, _ = usable[lo]
            if a in used or b in used:
                ok = False
                break
            used.add(a)
            used.add(b)
            holes.append([a, b])
        if not ok:
            continue

        deck = [c for c in need_deck if c not in used]
        extra = rng.sample(deck, 5 - len(board)) if len(board) < 5 else []
        wins += _score_runout(holes, board + extra)[0]
        done += 1

    if not done:
        raise ValueError("could not draw a legal matchup from these ranges")
    return Equity([wins / done, 1 - wins / done], exact=False, samples=done)
