"""Equity, and in particular whether it earned the decimal places it prints.

The review quotes lines like "you needed 31.2% and had 30.8%". A difference of
four tenths of a percent is smaller than the sampling error of any Monte Carlo
this could afford on a web request, so the rule is that **postflop is never
sampled** - and that rule is what most of this file checks.

The preflop sampler is checked against exact enumeration rather than against
published tables, because published tables are averaged over suit combinations
and this function is not. ``AsAh`` against ``KsKh`` is genuinely 82.64%, not the
82.36% a table prints, because those two hands share both suits. Chasing that
0.3% as if it were a bug is a full afternoon; the test below is here so nobody
spends it twice.
"""

import random

import pytest

from cards import parse
from equity import (
    breakeven_bluff_frequency, call_ev, minimum_defence_frequency, pot_odds,
    required_equity, runout_count, showdown_equity,
)


def eq(text, board="", **kw):
    holes = [parse(h) for h in text.split()]
    return showdown_equity(holes, parse(board), **kw)


# ------------------------------------------------- exact where it must be


@pytest.mark.parametrize("board,exact", [
    ("", False),        # 1,712,304 runouts
    ("AsKd7c", True),   # 990
    ("AsKd7c2h", True), # 44
    ("AsKd7c2h9s", True),
])
def test_postflop_is_exact_and_preflop_is_not(board, exact):
    e = eq("QcQd JhJc", board)
    assert e.exact is exact
    assert (e.error == 0.0) is exact


def test_runout_counts_are_what_the_docstring_claims():
    assert runout_count(0, 2) == 1_712_304
    assert runout_count(3, 2) == 990
    assert runout_count(4, 2) == 44
    assert runout_count(5, 2) == 1


def test_equities_always_sum_to_one():
    for board in ("", "AsKd7c", "AsKd7c2h", "AsKd7c2h9s"):
        e = eq("QcQd JhJc 5s5d", board, iters=2000)
        assert abs(sum(e) - 1.0) < 1e-9


# ------------------------------------------------------------------- ties


def test_a_chop_is_half_a_win_not_a_win():
    """Both play the board. Counting a chop as a win would say 100/100.

    The board is rainbow-ish on purpose: an earlier version used four spades,
    and the hand holding the fifth spade quietly had a flush rather than a chop.
    """
    e = eq("2c3d 4h5s", "AsKdQhJcTd")
    assert e.exact
    assert e == [0.5, 0.5]


def test_a_three_way_chop_splits_three_ways():
    e = eq("2c3d 4h5s 6c7d", "AsKdQhJcTd")
    assert e == [pytest.approx(1 / 3)] * 3


def test_the_better_kicker_wins_outright():
    e = eq("AsKd AcQd", "Ah7c2s9h4d")
    assert e == [1.0, 0.0]


# --------------------------------------------------- known exact answers


def test_a_missed_draw_on_the_river_is_worth_nothing():
    """The flush never came, so the pair of aces has all of it."""
    e = eq("AsAd 7h8h", "2h5h9cKdQs")
    assert e.exact
    assert e == [1.0, 0.0]


def test_the_nuts_has_all_of_it():
    e = eq("AsKs 2c2d", "QsJsTs4h9d")
    assert e == [1.0, 0.0]


def test_a_dominated_hand_still_has_its_outs():
    """AK against AQ on a dry ace flop: the Q outs and the runner-runners."""
    e = eq("AsKd AcQd", "Ah7c2s")
    assert e.exact
    assert 0.0 < e[1] < 0.15


# ------------------------------------------- the sampler is not biased


@pytest.mark.parametrize("hero,villain,expected", [
    ("AsAh", "KsKh", 0.826366),
])
def test_the_preflop_sampler_agrees_with_exact_enumeration(hero, villain, expected):
    """The 0.3% gap to published tables is suit specificity, not a bug.

    ``expected`` is this pair enumerated over all 1,712,304 runouts, which takes
    about 45 seconds - too slow to run here, so the answer is written down. A
    published table says 82.36% for "AA vs KK" because it averages over suit
    combinations; these two hands share both suits, which is worth a third of a
    percent. Both numbers are right about different questions.
    """
    e = eq(f"{hero} {villain}", iters=60_000, rng=random.Random(11))
    assert not e.exact
    assert abs(e[0] - expected) < 4 * e.error


def test_sampling_more_shrinks_the_stated_error():
    small = eq("AsAh KsKh", iters=2_500, rng=random.Random(1))
    big = eq("AsAh KsKh", iters=40_000, rng=random.Random(1))
    assert big.error < small.error / 3


# ------------------------------------------------------------- pot maths


def test_required_equity_of_a_pot_sized_bet_is_a_third():
    assert required_equity(100, 200) == pytest.approx(1 / 3)


def test_required_equity_of_a_half_pot_bet_is_a_quarter():
    """``pot_before_call`` includes the bet you are facing. Pot 100, bet 50, so 150."""
    assert required_equity(50, 150) == pytest.approx(0.25)


def test_pot_odds_says_the_same_thing_the_other_way():
    assert pot_odds(100, 300) == 3.0
    assert pot_odds(0, 300) == float("inf")


def test_a_free_call_needs_no_equity():
    assert required_equity(0, 500) == 0.0


def test_call_ev_is_measured_against_folding():
    """Folding is 0 by convention, so a break-even call is 0 too."""
    assert call_ev(1 / 3, 100, 200) == pytest.approx(0.0)
    assert call_ev(0.5, 100, 200) == pytest.approx(50.0)
    assert call_ev(0.0, 100, 200) == pytest.approx(-100.0)
    assert call_ev(1.0, 100, 200) == pytest.approx(200.0)


@pytest.mark.parametrize("to_call,pot", [(100, 200), (50, 150), (33, 100), (700, 250)])
def test_call_ev_is_zero_exactly_at_the_required_equity(to_call, pot):
    """The two functions must cross zero together, or one of them is wrong.

    They did not. ``call_ev`` counted the caller's own chips as winnings, which
    made every call look better than it is by ``equity * to_call`` - an error
    that always points at calling more, in a tool whose whole job is to say when
    you are calling too much.
    """
    p = required_equity(to_call, pot)
    assert call_ev(p, to_call, pot) == pytest.approx(0.0, abs=1e-9)
    assert call_ev(p + 0.05, to_call, pot) > 0
    assert call_ev(p - 0.05, to_call, pot) < 0


def test_breakeven_bluff_and_minimum_defence_are_complements():
    for bet, pot in [(50, 100), (100, 100), (200, 100), (33, 100)]:
        assert (breakeven_bluff_frequency(bet, pot)
                + minimum_defence_frequency(bet, pot)) == pytest.approx(1.0)


def test_minimum_defence_against_a_pot_sized_bet_is_half():
    assert minimum_defence_frequency(100, 100) == pytest.approx(0.5)


# ------------------------------------------------------------ complaints


def test_a_duplicated_card_is_an_error():
    with pytest.raises(ValueError):
        eq("AsAh AsKd")
    with pytest.raises(ValueError):
        eq("AsAh KsKd", "AsKh2c")


def test_one_player_is_not_a_showdown():
    with pytest.raises(ValueError):
        showdown_equity([parse("AsAh")])
