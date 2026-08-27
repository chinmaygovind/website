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
import statistics
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


# --------------------------------------------------- one combination at a time

#: Hand evaluations one ``combo_equities`` call may spend. Unlike everything
#: above it, this one runs the board out **per combination in a range**, so the
#: cost is runouts times combinations rather than runouts - and the flop's 1,081
#: runouts against a loose bot's 343 combinations is 371,000 evaluations and a
#: full second, inside a review a browser is waiting on.
#:
#: So the runouts are what gets cut, not the range: a range read to two thirds
#: of its combinations is a different range, while a sampled runout is the same
#: range measured less precisely, and ``ComboEquities.error`` says by how much.
#: 45,000 is about an eighth of a second, which leaves the turn (46 runouts) and
#: the river (1) exact and comfortable, and samples only the flop and preflop -
#: the same split, for the same reason, as the table at the top of this file.
COMBO_BUDGET = 45_000

#: Preflop the same call is worth a third as much and costs the same, so it gets
#: a third of the budget. There is no board to be ahead of, so the split it feeds
#: is the coarse one - favourite, close, behind - and its boundaries sit at 60%
#: and 40%, nowhere near tight enough to care about the extra precision. The
#: expensive streets are the ones with a board on them, which is where the
#: decisions are.
PREFLOP_COMBO_BUDGET = 15_000

#: Never fewer than this many runouts however wide the range is - and never
#: more, because this floor overrides the budget and is therefore what sets the
#: worst case. A 58% VPIP bot has 679 combinations preflop, and at 120 runouts
#: that is 81,000 evaluations against a 15,000 budget: five times over, on the
#: one opponent who turns up most often. Eighty keeps the widest range inside a
#: tenth of a second and still tells a live draw from a dead hand, which is what
#: the buckets in ``review.py`` need it for.
MIN_COMBO_RUNOUTS = 80


class ComboEquities(list):
    """Hero's equity against each opponent holding, plus how it was arrived at."""

    def __init__(self, values, exact, runouts, ahead, spread=0.0):
        super().__init__(values)
        self.exact = exact
        self.runouts = runouts
        #: ``True`` where the hero's hand is the better one **on the board as it
        #: stands**, before any more cards. ``None`` per entry preflop.
        self.ahead = ahead
        #: Standard deviation across runouts of the hero's share against the
        #: whole range. Zero when exact. See ``combined_error``.
        self.spread = spread

    @property
    def error(self):
        """One standard error on **one combination's** number, or 0.0 if exact.

        Worst case p=0.5, as in :class:`Equity`. This is the right error for
        "how well do I know my equity against exactly ace-king", and the wrong
        one for the range as a whole - see ``combined_error``.
        """
        if self.exact:
            return 0.0
        return 0.5 / (self.runouts ** 0.5)

    @property
    def combined_error(self):
        """One standard error on the **weighted average** over the whole range.

        Not the per-combination error, and not that error divided by the number
        of combinations either. Every combination is run against the same
        runouts, so their errors are correlated and do not average away - but a
        single runout scored against three hundred holdings is already an average
        rather than a coin flip, so they do not simply add either. Both of the
        arithmetic answers are wrong, in opposite directions and by a factor of
        two: on a flop against a 23% range the per-combination error is 3.1% and
        the truth, measured over twelve seeds, is 1.3%.

        So it is measured rather than derived: ``spread`` is the standard
        deviation across runouts of the hero's share against the whole range,
        which is exactly the quantity whose mean is being reported.
        """
        if self.exact or self.runouts < 2:
            return 0.0
        return self.spread / (self.runouts ** 0.5)


def combo_equities(hero, combos, board=(), rng=None, budget=COMBO_BUDGET):
    """Hero's equity against **each** holding in ``combos``, one number each.

    ``combos`` is ``[(card, card, weight), ...]`` as ``ranges.weighted_combos``
    produces. The weights are carried through untouched; this answers only the
    per-holding question, and what to do with the weights is the caller's.

    **Every combination is run against the same runouts.** That is not a saving,
    it is the point: the sizing rollout compares one bet size against another,
    and the two comparisons share their sampling error almost exactly, so the
    *difference* between them is far better determined than either number is.
    Drawing fresh runouts per size would put noise on exactly the quantity being
    read off the page. Where the street is short enough the runouts are simply
    all of them and there is no error to share.

    A runout that uses one of the opponent's own cards is skipped for that
    opponent rather than replaced, for ``range_equity``'s reason: replacing it
    reweights the board towards whatever the replacement prefers.
    """
    hero = list(hero)
    board = list(board)
    rng = rng or random.Random()
    known = set(hero) | set(board)
    deck = [c for c in DECK if c not in known]
    need = 5 - len(board)

    total = comb(len(deck), need) if need else 1
    afford = max(MIN_COMBO_RUNOUTS, budget // max(1, len(combos)))
    exact = need == 0 or total <= afford
    if exact:
        draws = list(itertools.combinations(deck, need))
    else:
        seen = set()
        draws = []
        while len(draws) < afford:
            pick = tuple(sorted(rng.sample(deck, need)))
            if pick in seen:
                continue
            seen.add(pick)
            draws.append(pick)

    hero_scores = [evaluate(hero + board + list(d)) for d in draws]
    made = evaluate(hero + board) if len(board) >= 3 else None

    # Per runout as well as per combination, because the standard error of the
    # weighted average cannot be derived from the per-combination one - see
    # ``ComboEquities.combined_error``.
    per_runout = [0.0] * len(draws)
    weight_seen = [0.0] * len(draws)

    out, ahead = [], []
    for a, b, w in combos:
        won = 0.0
        n = 0
        for i, (d, mine) in enumerate(zip(draws, hero_scores)):
            if a in d or b in d:
                continue
            theirs = evaluate([a, b] + board + list(d))
            if theirs < mine:
                share = 1.0
            elif theirs == mine:
                share = 0.5
            else:
                share = 0.0
            won += share
            per_runout[i] += w * share
            weight_seen[i] += w
            n += 1
        out.append(won / n if n else 0.5)
        ahead.append(None if made is None
                     else made > evaluate([a, b] + board))

    spread = 0.0
    if not exact and len(draws) > 1:
        shares = [p / s for p, s in zip(per_runout, weight_seen) if s > 0]
        if len(shares) > 1:
            spread = statistics.pstdev(shares)
    return ComboEquities(out, exact, len(draws), ahead, spread)


def combined(equities, combos):
    """The weighted average - the single equity number those combos add up to."""
    total = sum(w for _a, _b, w in combos)
    if total <= 0:
        return 0.0
    return sum(e * w for e, (_a, _b, w) in zip(equities, combos)) / total
