"""Hand strength. This is the primitive every other number in the trainer sits
on, so it is proven rather than spot-checked.

``test_matches_independent_reference`` scores all 2,598,960 five-card hands
against a second implementation written a completely different way - sort the
ranks, group them, read the shape - and also counts how many hands land in each
category and checks those against the textbook figures. Two implementations
agreeing is good; two implementations agreeing *and* producing the known
frequencies is a proof, because a shared misunderstanding would move the counts.

It is marked ``exhaustive`` and left out of a normal run. See ``pytest.ini``.

**One combination is deliberately not tested, because it cannot happen.** In
seven cards you can never hold both a flush and a full house. A flush is five
cards of five distinct ranks; a full house is five cards over two ranks; in
seven cards those two sets must overlap in at least three cards, and three cards
cannot be both all-distinct and drawn from two ranks. The same argument rules
out quads-with-a-flush. An earlier version of this file asserted the opposite
and was wrong.
"""

import collections
import itertools
import random

import pytest

from cards import DECK, parse
from evaluator import (
    FLUSH, FULL_HOUSE, HIGH_CARD, PAIR, QUADS, STRAIGHT, STRAIGHT_FLUSH,
    TRIPS, TWO_PAIR, category_of, describe, evaluate, tiebreaks,
)

#: How many of the 2,598,960 five-card hands fall in each category. These are
#: the published figures, not something this code produced.
TEXTBOOK_COUNTS = {
    STRAIGHT_FLUSH: 40,
    QUADS: 624,
    FULL_HOUSE: 3_744,
    FLUSH: 5_108,
    STRAIGHT: 10_200,
    TRIPS: 54_912,
    TWO_PAIR: 123_552,
    PAIR: 1_098_240,
    HIGH_CARD: 1_302_540,
}


def ref5(cards):
    """An independent five-card evaluator: sort, group, read the shape.

    Deliberately written without a single idea in common with ``evaluate`` -
    no bitmasks, no packed integer, no scoring-every-category. Returns
    ``(category, tiebreak ranks)``.
    """
    ranks = [c >> 2 for c in cards]
    suits = [c & 3 for c in cards]
    flush = len(set(suits)) == 1
    counts = collections.Counter(ranks)
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [n for _, n in groups]
    ordered = [r for r, _ in groups]
    distinct = sorted(counts, reverse=True)

    straight = None
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            straight = distinct[0]
        elif distinct == [12, 3, 2, 1, 0]:
            straight = 3

    if straight is not None and flush:
        return STRAIGHT_FLUSH, [straight]
    if shape == [4, 1]:
        return QUADS, ordered
    if shape == [3, 2]:
        return FULL_HOUSE, ordered
    if flush:
        return FLUSH, distinct
    if straight is not None:
        return STRAIGHT, [straight]
    if shape == [3, 1, 1]:
        return TRIPS, ordered
    if shape == [2, 2, 1]:
        return TWO_PAIR, ordered
    if shape == [2, 1, 1, 1]:
        return PAIR, ordered
    return HIGH_CARD, distinct


def agrees(cards):
    """True when ``evaluate`` reads these five cards the way ``ref5`` does."""
    cat, ranks = ref5(cards)
    score = evaluate(list(cards))
    return category_of(score) == cat and tiebreaks(score)[:len(ranks)] == ranks


# --------------------------------------------------------------- the proof


@pytest.mark.exhaustive
def test_matches_independent_reference_on_every_five_card_hand():
    counts = collections.Counter()
    for hand in itertools.combinations(DECK, 5):
        cat, ranks = ref5(hand)
        score = evaluate(list(hand))
        assert category_of(score) == cat, hand
        assert tiebreaks(score)[:len(ranks)] == ranks, hand
        counts[cat] += 1

    assert sum(counts.values()) == 2_598_960
    assert dict(counts) == TEXTBOOK_COUNTS


def test_matches_reference_on_a_random_sample():
    """The same check, small enough to run every time. Not a substitute."""
    rng = random.Random(20260825)
    for _ in range(20_000):
        assert agrees(rng.sample(DECK, 5))


# ------------------------------------------------------ the seven-card traps


def test_straight_flush_beats_the_ace_high_flush_it_hides_inside():
    """Six spades: A-K-Q-9-2 of spades is an ace-high flush, but 5432A is there too."""
    wheel_sf = evaluate(parse("As5s4s3s2sKsQd"))
    assert category_of(wheel_sf) == STRAIGHT_FLUSH
    assert tiebreaks(wheel_sf)[0] == 3  # five high
    assert wheel_sf > evaluate(parse("AsKsQs9s2s7d3c"))


def test_flush_beats_a_straight_made_of_other_cards():
    """The straight and the flush are both there and are not the same five cards."""
    score = evaluate(parse("AsKsQs9s2sJdTd"))
    assert category_of(score) == FLUSH


def test_three_pair_plays_the_top_two():
    score = evaluate(parse("AsAcKsKcQsQcJd"))
    assert category_of(score) == TWO_PAIR
    assert tiebreaks(score)[:3] == [12, 11, 10]  # aces and kings, queen kicker
    assert describe(score) == "two pair, aces and kings"


def test_two_trips_make_a_full_house_not_six_of_a_kind():
    score = evaluate(parse("AsAcAdKsKcKdQh"))
    assert category_of(score) == FULL_HOUSE
    assert tiebreaks(score)[:2] == [12, 11]


def test_full_house_takes_the_best_pair_available():
    """Both routes to the second rank have to pick the fives.

    Seven cards reach a full house two ways and only two: **two trips** plus a
    spare, where the lower trip plays as the pair; or **one trip and two pairs**,
    where the better pair plays. They cannot both happen - two trips is already
    six cards and the seventh cannot pair anything - so both branches need their
    own case.

    The third hand is the trap in the first branch: a lone five is not a pair,
    so the deuces play and the five is irrelevant.
    """
    two_trips = evaluate(parse("7s7c7d5s5c5d2h"))
    trip_and_pairs = evaluate(parse("7s7c7d5s5c2d2h"))
    assert category_of(two_trips) == category_of(trip_and_pairs) == FULL_HOUSE
    assert tiebreaks(two_trips)[:2] == tiebreaks(trip_and_pairs)[:2] == [5, 3]

    lone_kicker = evaluate(parse("7s7c7d2s2c2d5h"))
    assert tiebreaks(lone_kicker)[:2] == [5, 0]  # sevens full of deuces


def test_quads_take_the_best_kicker_not_a_paired_one():
    score = evaluate(parse("AsAcAdAhKsKc2d"))
    assert category_of(score) == QUADS
    assert tiebreaks(score)[:2] == [12, 11]


def test_wheel_is_a_five_high_straight_and_loses_to_a_six_high_one():
    wheel = evaluate(parse("As2c3d4h5s9d8c"))
    six = evaluate(parse("2c3d4h5s6dKcQh"))
    assert category_of(wheel) == category_of(six) == STRAIGHT
    assert six > wheel


def test_ace_high_straight_is_the_best_straight():
    broadway = evaluate(parse("AsKcQdJhTs3d2c"))
    assert category_of(broadway) == STRAIGHT
    assert tiebreaks(broadway)[0] == 12


def test_a_pair_on_the_board_does_not_break_a_straight():
    score = evaluate(parse("9s8c7d6h5s5c2d"))
    assert category_of(score) == STRAIGHT
    assert tiebreaks(score)[0] == 7  # nine high


def test_equal_hands_score_equal():
    """Two players playing the same board must tie, not be separated by suit."""
    board = parse("AsKsQsJsTd")
    assert evaluate(parse("2c3c") + board) == evaluate(parse("4d5d") + board)


def test_seven_cards_never_hold_both_a_flush_and_a_full_house():
    """The counting argument in this module's docstring, checked by sampling."""
    rng = random.Random(7)
    for _ in range(50_000):
        cards = rng.sample(DECK, 7)
        counts = collections.Counter(c >> 2 for c in cards)
        suits = collections.Counter(c & 3 for c in cards)
        has_flush = max(suits.values()) >= 5
        trips = [r for r, n in counts.items() if n >= 3]
        boat = bool(trips) and (
            len(trips) > 1 or any(n >= 2 for r, n in counts.items() if r != trips[0])
        )
        assert not (has_flush and boat)


def test_rejects_the_wrong_number_of_cards():
    with pytest.raises(ValueError):
        evaluate(parse("AsKsQs2d"))
    with pytest.raises(ValueError):
        evaluate(parse("AsKsQsJsTs9s8s7s"))


def test_describe_reads_like_english():
    assert describe(evaluate(parse("AsKsQsJsTs"))) == "a royal flush"
    assert describe(evaluate(parse("9s8s7s6s5s"))) == "a straight flush, 9 high"
    assert describe(evaluate(parse("7s7c7d7h2s"))) == "four sevens"
    assert describe(evaluate(parse("7s7c7d2h2s"))) == "a full house, sevens full of deuces"
    assert describe(evaluate(parse("As9s7s4s2s"))) == "a flush, A high"
    assert describe(evaluate(parse("9c8s7s6s5s"))) == "a straight, 9 high"
    assert describe(evaluate(parse("7s7c7d9h2s"))) == "three sevens"
    assert describe(evaluate(parse("7s7c2d2h9s"))) == "two pair, sevens and deuces"
    assert describe(evaluate(parse("7s7cKd4h9s"))) == "a pair of sevens"
    assert describe(evaluate(parse("Ks9c7d4h2s"))) == "K high"
