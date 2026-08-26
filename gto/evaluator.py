"""Hand strength, as one comparable integer.

``evaluate(cards)`` takes five, six or seven cards and returns a score. A bigger
score is a better hand, and two hands are equal exactly when their scores are
equal - so a showdown is ``max()`` and a chop is a tie, with no special cases
anywhere else in the codebase.

The score packs into 24 bits::

    category << 20 | t1 << 16 | t2 << 12 | t3 << 8 | t4 << 4 | t5

``category`` is 0-8 (high card through straight flush) and ``t1..t5`` are the
tiebreak ranks in descending significance, each a rank index 0-12. Because the
category is the most significant field, comparing the packed integers compares
category first and only then the tiebreakers, which is precisely how poker hands
compare. ``describe()`` unpacks it back into English for the review screen.

**Why this shape rather than a lookup table.** The usual fast 7-card evaluator is
a 32-million-entry table, which is minutes to generate and far too large to ship
in a repo whose ``.git`` is already 640MB. This is pure arithmetic on two small
bitmasks, needs no table at all, and ``tests/test_evaluator.py`` checks it
against an exhaustive independent implementation over every 5-card hand - all
2,598,960 of them - so its correctness is a proof rather than a spot check.

Speed is not this module's problem. Monte Carlo equity needs millions of
evaluations, and that path is the vectorised one in ``equity.py``, which is
checked against *this* function on random inputs.
"""

from cards import CATEGORY_NAMES, RANKS

HIGH_CARD = 0
PAIR = 1
TWO_PAIR = 2
TRIPS = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
QUADS = 7
STRAIGHT_FLUSH = 8

#: Ace, five, four, three, deuce - the one straight the shift trick cannot see,
#: because the ace is at the top of the rank order and this is the hand where it
#: plays at the bottom.
_WHEEL = (1 << 12) | (1 << 3) | (1 << 2) | (1 << 1) | (1 << 0)


def _score(category, ranks):
    """Pack a category and its tiebreak ranks into the comparable integer."""
    value = category
    for i in range(5):
        value = (value << 4) | (ranks[i] if i < len(ranks) else 0)
    return value


def _top_ranks(mask, n):
    """The ``n`` highest rank indices set in ``mask``, descending."""
    out = []
    for r in range(12, -1, -1):
        if mask & (1 << r):
            out.append(r)
            if len(out) == n:
                break
    return out


def _straight_high(mask):
    """Rank index of the top card of the best straight in ``mask``, or None.

    ``mask & mask>>1 & mask>>2 & mask>>3 & mask>>4`` leaves bit *i* set exactly
    when ranks *i* through *i+4* are all present, so the highest surviving bit
    is the bottom of the best straight and four above it is the top.
    """
    run = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if run:
        return (run.bit_length() - 1) + 4
    if mask & _WHEEL == _WHEEL:
        return 3
    return None


def evaluate(cards):
    """Score five to seven cards. Higher is better.

    Every category the cards support is scored and the best is returned, rather
    than testing categories in order and stopping. It costs a few comparisons
    and it removes the family of bugs where a hand is read as the first thing it
    matches - a seven-card hand that is at once a flush and a full house being
    the one that catches people out.
    """
    if not 5 <= len(cards) <= 7:
        raise ValueError(f"need 5-7 cards, got {len(cards)}")

    rank_count = [0] * 13
    suit_count = [0] * 4
    suit_mask = [0] * 4
    mask = 0
    for c in cards:
        r = c >> 2
        s = c & 3
        rank_count[r] += 1
        suit_count[s] += 1
        suit_mask[s] |= 1 << r
        mask |= 1 << r

    best = -1

    for s in range(4):
        if suit_count[s] >= 5:
            flush_mask = suit_mask[s]
            high = _straight_high(flush_mask)
            if high is not None:
                best = max(best, _score(STRAIGHT_FLUSH, [high]))
            best = max(best, _score(FLUSH, _top_ranks(flush_mask, 5)))
            break

    high = _straight_high(mask)
    if high is not None:
        best = max(best, _score(STRAIGHT, [high]))

    quads, trips, pairs = [], [], []
    for r in range(12, -1, -1):
        n = rank_count[r]
        if n == 4:
            quads.append(r)
        elif n == 3:
            trips.append(r)
        elif n == 2:
            pairs.append(r)

    if quads:
        kicker = _top_ranks(mask & ~(1 << quads[0]), 1)
        best = max(best, _score(QUADS, [quads[0]] + kicker))

    if trips and (len(trips) > 1 or pairs):
        under = trips[1] if len(trips) > 1 else -1
        if pairs and pairs[0] > under:
            under = pairs[0]
        best = max(best, _score(FULL_HOUSE, [trips[0], under]))

    if trips:
        kickers = _top_ranks(mask & ~(1 << trips[0]), 2)
        best = max(best, _score(TRIPS, [trips[0]] + kickers))

    if len(pairs) >= 2:
        rest = mask & ~(1 << pairs[0]) & ~(1 << pairs[1])
        best = max(best, _score(TWO_PAIR, [pairs[0], pairs[1]] + _top_ranks(rest, 1)))

    if pairs:
        kickers = _top_ranks(mask & ~(1 << pairs[0]), 3)
        best = max(best, _score(PAIR, [pairs[0]] + kickers))

    best = max(best, _score(HIGH_CARD, _top_ranks(mask, 5)))
    return best


def category_of(score):
    """The category index a score belongs to."""
    return score >> 20


def tiebreaks(score):
    """The five tiebreak rank indices packed into a score, most significant first."""
    return [(score >> shift) & 0xF for shift in (16, 12, 8, 4, 0)]


def describe(score):
    """A score -> the English a review line reads, e.g. ``"two pair, aces and nines"``."""
    cat = category_of(score)
    t = tiebreaks(score)
    name = lambda r: RANKS[r]
    plural = {
        "2": "deuces", "3": "threes", "4": "fours", "5": "fives", "6": "sixes",
        "7": "sevens", "8": "eights", "9": "nines", "T": "tens", "J": "jacks",
        "Q": "queens", "K": "kings", "A": "aces",
    }

    if cat == STRAIGHT_FLUSH:
        if t[0] == 12:
            return "a royal flush"
        return f"a straight flush, {name(t[0])} high"
    if cat == QUADS:
        return f"four {plural[name(t[0])]}"
    if cat == FULL_HOUSE:
        return f"a full house, {plural[name(t[0])]} full of {plural[name(t[1])]}"
    if cat == FLUSH:
        return f"a flush, {name(t[0])} high"
    if cat == STRAIGHT:
        return f"a straight, {name(t[0])} high"
    if cat == TRIPS:
        return f"three {plural[name(t[0])]}"
    if cat == TWO_PAIR:
        return f"two pair, {plural[name(t[0])]} and {plural[name(t[1])]}"
    if cat == PAIR:
        return f"a pair of {plural[name(t[0])]}"
    return f"{name(t[0])} high"


def category_name(score):
    """Just the category, without tiebreakers: ``"a flush"``."""
    return CATEGORY_NAMES[category_of(score)]
