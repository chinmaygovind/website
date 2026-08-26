"""The side game, which at these stakes is not a side game.

$1/$2/$3 from each of five opponents at 0.25/0.25 is 20/40/60 big blinds, so a
third straight win pays about a tenth of a buy-in per opponent. The tests that
matter here are the ones about **magnitude** - it would be easy to build this
correctly and still quietly treat it as a garnish.
"""

import pytest

import bounty as B


def test_the_ladder_only_starts_at_three():
    assert B.payout_dollars(1) == B.payout_dollars(2) == 0.0
    assert B.payout_dollars(3) == 1.0
    assert B.payout_dollars(4) == 2.0
    assert B.payout_dollars(5) == 3.0


def test_the_ladder_tops_out():
    for n in range(5, 20):
        assert B.payout_dollars(n) == 3.0


def test_the_ladder_is_worth_a_lot_of_big_blinds_at_these_stakes():
    """A third straight win at 0.25/0.25 pays 20bb. That is the headline."""
    assert B.collect(3, 5, 0.25) == pytest.approx(20.0)
    assert B.collect(4, 5, 0.25) == pytest.approx(40.0)
    assert B.collect(5, 5, 0.25) == pytest.approx(60.0)


def test_the_same_ladder_is_small_at_bigger_stakes():
    """Quoting in big blinds is what makes the advice survive a change of stakes."""
    assert B.collect(3, 5, 2.00) == pytest.approx(2.5)


# --------------------------------------------------------- what a win is worth


def test_a_streak_of_two_makes_the_next_pot_worth_far_more_than_the_pot():
    """This is the number that changes how a hand should be played."""
    assert B.streak_value(2, 5, bb_dollars=0.25) > 20.0


def test_the_option_is_worth_something_even_before_it_pays():
    """One win from nothing is still a step towards the ladder."""
    assert B.streak_value(1, 5, bb_dollars=0.25) > 0.0
    assert B.streak_value(0, 5, bb_dollars=0.25) > 0.0


def test_a_win_is_worth_more_the_further_up_the_ladder_you_are():
    values = [B.streak_value(s, 5, bb_dollars=0.25) for s in range(5)]
    assert values == sorted(values)


def test_the_default_win_rate_is_one_over_the_table_size():
    assert B.streak_value(2, 5) == B.streak_value(2, 5, win_rate=1 / 6)


def test_a_bigger_win_rate_makes_the_option_worth_more():
    """A winning player continues streaks more often, so the option is worth more."""
    assert (B.streak_value(2, 5, win_rate=0.30)
            > B.streak_value(2, 5, win_rate=0.10))


def test_no_bounty_means_no_adjustment():
    assert B.streak_value(4, 0) == 0.0
    assert B.streak_value(4, 5, bb_dollars=0) == 0.0


# --------------------------------------------------------------- the streaks


def test_winning_advances_and_anything_else_resets():
    s = B.Streaks(["hero", "a", "b"])
    for _ in range(3):
        s.settle(["hero"])
    assert s.streak["hero"] == 3
    s.settle(["a"])
    assert s.streak["hero"] == 0
    assert s.streak["a"] == 1


def test_a_chop_breaks_everybodys_streak_including_the_winners():
    """Sharing a pot is not winning it. The alternative makes chopping a way of
    manufacturing bounties."""
    s = B.Streaks(["hero", "a", "b"])
    for _ in range(2):
        s.settle(["hero"])
    assert s.streak["hero"] == 2
    s.settle(["hero", "a"])
    assert s.streak == {"hero": 0, "a": 0, "b": 0}


def test_the_transfers_balance():
    s = B.Streaks(["hero", "a", "b", "c"])
    for _ in range(3):
        t = s.settle(["hero"])
    assert sum(t.values()) == pytest.approx(0.0)
    assert t["hero"] == pytest.approx(3.0)
    assert all(t[n] == -1.0 for n in ("a", "b", "c"))


def test_nothing_is_transferred_below_three():
    s = B.Streaks(["hero", "a"])
    assert s.settle(["hero"]) == {}
    assert s.settle(["hero"]) == {}
    assert s.settle(["hero"]) != {}


def test_the_running_total_tracks_what_was_paid():
    s = B.Streaks(["hero", "a", "b"])
    for _ in range(4):
        s.settle(["hero"])
    assert s.paid["hero"] == pytest.approx(2.0 * 2 + 1.0 * 2)
    assert s.paid["a"] == pytest.approx(-3.0)


def test_streaks_survive_a_round_trip():
    s = B.Streaks(["hero", "a"])
    s.settle(["hero"])
    again = B.Streaks.from_dict(s.to_dict())
    assert again.to_dict() == s.to_dict()


def test_describe_says_nothing_when_there_is_nothing_to_say():
    assert B.describe(0, 5) is None


def test_describe_names_the_money_when_there_is_some():
    text = B.describe(2, 5, bb_dollars=0.25)
    assert "$5" in text and "2 in a row" in text
