"""Reading a board, for a bot to act on and for a review to describe."""

import itertools
import random

import pytest

from cards import DECK, parse
from evaluator import evaluate
import texture as T


def read(hole, board):
    return T.read(parse(hole), parse(board))


# ------------------------------------------------------------- strength


def reference_strength(hole, board):
    """Counted from scratch, the slow obvious way, with no cache anywhere."""
    known = set(hole) | set(board)
    rest = [c for c in DECK if c not in known]
    mine = evaluate(list(hole) + list(board))
    below = equal = total = 0
    for a, b in itertools.combinations(rest, 2):
        theirs = evaluate([a, b] + list(board))
        total += 1
        if theirs < mine:
            below += 1
        elif theirs == mine:
            equal += 1
    return (below + equal / 2.0) / total


def test_the_cached_strength_is_the_same_number_as_counting_from_scratch():
    """The cache is an optimisation and must not be an approximation.

    It stores every holding scored against the board, including the ones using
    the reader's own cards, and then removes those. Getting that removal wrong
    would shift every bot's read by a percent or two - too small to notice and
    too big to be fine.
    """
    rng = random.Random(31337)
    for _ in range(40):
        deck = list(DECK)
        rng.shuffle(deck)
        n = rng.choice([3, 4, 5])
        hole, board = deck[:2], deck[2:2 + n]
        assert T.showdown_strength(hole, board) == pytest.approx(
            reference_strength(hole, board), abs=1e-12)


def test_the_nuts_is_near_one_and_the_worst_hand_is_near_zero():
    assert T.showdown_strength(*[parse(x) for x in ("AsKs", "QsJsTs4h9d")]) > 0.999
    assert T.showdown_strength(*[parse(x) for x in ("3c2d", "AsKsQs4h9d")]) < 0.06


def test_a_hand_that_plays_the_board_lands_near_a_half():
    """Counting chops as wins is what puts this near one, and it is the mistake
    that makes a bot overvalue every board that plays."""
    s = T.showdown_strength(parse("2c3d"), parse("AsKdQhJcTd"))
    assert 0.15 < s < 0.55


# ----------------------------------------------------------------- draws


@pytest.mark.parametrize("hole,board,expected", [
    ("AsKs", "Qs7s2d", 2),   # four to a flush, two of them ours
    ("AsKs", "Qs7h2d", 1),   # backdoor
    ("AsKs", "QsJsTs", 3),   # made
    ("AhKd", "Qs7s2s", 0),   # the board is four to a flush; we have none of it
    ("AsKd", "Qs7s2s", 2),   # ...but one spade of ours makes it a draw
])
def test_flush_draws_are_counted_in_our_own_suit(hole, board, expected):
    assert T.flush_draw(parse(hole), parse(board)) == expected


def test_four_of_our_suit_on_a_four_card_board_is_a_made_flush():
    assert T.flush_draw(parse("AsKd"), parse("Qs7s2s9s")) == 3


def test_a_flush_on_the_board_is_not_our_draw():
    """Four to a flush that we contribute nothing to is not a draw, it is a
    card everybody has - and calling it one is how a bot semi-bluffs with the
    sixth best hand."""
    assert T.flush_draw(parse("AhKd"), parse("Qs7s2s")) == 0


@pytest.mark.parametrize("hole,board,expected", [
    ("9s8s", "7h6d2c", 8),    # open ended
    ("9s8s", "7h5d2c", 4),    # gutshot
    ("AsKd", "Qh7c2s", 0),    # nothing
    ("JhTh", "QcKd3s", 8),    # open ended at the top
])
def test_straight_outs(hole, board, expected):
    assert T.straight_outs(parse(hole), parse(board)) == expected


def test_a_straight_already_on_the_board_is_not_a_draw():
    assert T.straight_outs(parse("2c3d"), parse("9s8h7c6d5s")) == 0


def test_flush_and_straight_outs_are_not_double_counted():
    """A card can complete both, and adding the two counts inflates the semi-bluff."""
    hole, board = parse("9s8s"), parse("7s6s2c")
    assert T.flush_draw(hole, board) == 2
    assert T.straight_outs(hole, board) == 8
    assert T.outs(hole, board) < T.FLUSH_OUTS + T.OESD_OUTS


def test_the_river_has_no_outs():
    assert T.outs(parse("9s8s"), parse("7h6d2cKsQh")) == 0


# ------------------------------------------------------------ what we made


@pytest.mark.parametrize("hole,board,label", [
    ("AhKd", "Ac7c2d", "top pair"),
    ("Kh9d", "Ac7cKd", "second pair"),
    ("7h5d", "AcKc7d", "third pair"),
    ("AsAd", "Kh7c2d", "overpair"),
    ("7s7d", "Ah7c2d", "set"),
    ("5s5d", "AhKc2d", "pocket pair"),
    ("9s8d", "AhKc2d", None),
])
def test_pair_read(hole, board, label):
    assert T.pair_read(parse(hole), parse(board))[0] == label


def test_the_kicker_is_the_other_card_not_the_paired_one():
    label, kicker = T.pair_read(parse("Ah2d"), parse("Ac7c3d"))
    assert label == "top pair"
    assert T.kicker_quality(kicker) == "weak"


# ---------------------------------------------------------------- texture


def test_board_texture_reads_the_dangerous_boards_as_dangerous():
    dry = T.board_texture(parse("7h2d9c"))
    wet = T.board_texture(parse("QsJsTs"))
    assert wet["wetness"] > dry["wetness"]
    assert wet["monotone"] and not wet["two_tone"]
    assert not dry["monotone"] and not dry["two_tone"]


def test_monotone_and_two_tone_never_disagree():
    """They are read off one number, because an earlier version read off two."""
    rng = random.Random(9)
    for _ in range(300):
        board = rng.sample(DECK, rng.choice([3, 4, 5]))
        t = T.board_texture(board)
        assert not (t["monotone"] and t["two_tone"])
        assert t["monotone"] == (t["flush_cards"] >= 3)
        assert t["two_tone"] == (t["flush_cards"] == 2)


def test_a_paired_board_is_seen_as_paired():
    assert T.board_texture(parse("7h7d2c"))["paired"]
    assert not T.board_texture(parse("7h8d2c"))["paired"]


# ------------------------------------------------------------- the words


@pytest.mark.parametrize("hole,board,phrase", [
    ("AhKd", "Ac7c2d", "top pair, good kicker"),
    ("7s7d", "Ah7c2d", "a set"),
    ("AsKs", "Qs7s2c", "a flush draw"),
    ("9s8s", "7h6d2c", "an open-ended straight draw"),
    ("AsKs", "Qh7d2c", "no pair, two overcards"),
    ("Ah2d", "Kh7c3d", "no pair, one overcard"),
    ("7c2d", "AhKdQc", "no pair and no draw"),
])
def test_describe_hand(hole, board, phrase):
    assert T.describe_hand(parse(hole), parse(board)) == phrase


def test_read_never_raises_on_any_real_spot():
    rng = random.Random(4)
    for _ in range(200):
        deck = list(DECK)
        rng.shuffle(deck)
        n = rng.choice([3, 4, 5])
        r = T.read(deck[:2], deck[2:2 + n])
        assert 0.0 <= r["strength"] <= 1.0
        assert isinstance(T.describe_hand(deck[:2], deck[2:2 + n]), str)
