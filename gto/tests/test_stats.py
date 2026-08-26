"""The win rate, and the interval that says how little it means.

The headline number is the one thing here somebody will read and believe, so
these tests are mostly about the ways it could quietly lie: an interval that is
too narrow, a rate that silently counts bounty money as poker, an EV-adjusted
number that is not actually different from the observed one, and a confident
sentence printed off nine hands.

The statistics are checked against hand-computed values rather than against
another implementation, because "the same as the code" is not a test.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stats
from stats import HANDS_PER_HOUR, Z95, Running


def played(n, result=0, **kw):
    """A session of ``n`` identical hands."""
    s = Running()
    for _ in range(n):
        s.add_hand(result, **kw)
    return s


class FakeReview:
    def __init__(self, verdict, loss_bb=None):
        self.verdict = verdict
        self.loss_bb = loss_bb


# ------------------------------------------------------------ the interval


def test_a_rate_needs_at_least_two_hands():
    assert Running().rate() is None
    assert played(1, 500).rate() is None
    assert played(2, 500).rate() is not None


def test_the_rate_is_big_blinds_per_hundred():
    """One big blind won per hand is 100bb/100, whatever the blind is."""
    s = played(50, 25)
    assert s.rate()[0] == pytest.approx(100.0)


def test_a_bigger_blind_is_a_smaller_rate_for_the_same_chips():
    s = Running(bb_cents=100, bb_dollars=1.0)
    for _ in range(50):
        s.add_hand(25)
    assert s.rate()[0] == pytest.approx(25.0)


def test_the_interval_matches_the_textbook_formula():
    """Hand-computed, not compared against the code that produced it."""
    results = [500, -300, 0, 1200, -250, -100, 75, -400, 900, -50]
    s = Running()
    for r in results:
        s.add_hand(r)
    series = [r / 25 for r in results]
    n = len(series)
    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series) / (n - 1)
    expected_half = stats.t95(n - 1) * math.sqrt(var / n) * 100.0
    assert s.rate()[0] == pytest.approx(mean * 100.0)
    assert s.rate()[1] == pytest.approx(expected_half)


def test_the_interval_uses_t_not_the_normal_approximation():
    """The variance is estimated from the same ten hands the mean is, so 1.96
    is too narrow - by 14% here, which is the difference between an interval
    that covers zero and one that does not."""
    results = [500, -300, 0, 1200, -250, -100, 75, -400, 900, -50]
    s = Running()
    for r in results:
        s.add_hand(r)
    series = [r / 25 for r in results]
    mean = sum(series) / len(series)
    var = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
    normal_half = Z95 * math.sqrt(var / len(series)) * 100.0
    assert s.rate()[1] > normal_half


def test_the_critical_value_shrinks_towards_the_normal_one():
    assert stats.t95(1) > stats.t95(10) > stats.t95(100) > stats.t95(10000)
    assert stats.t95(10000) == pytest.approx(Z95, abs=0.001)
    assert stats.t95(24) == pytest.approx(2.064, abs=0.001)
    assert stats.t95(9) == pytest.approx(2.262, abs=0.001)


def test_the_critical_value_is_interpolated_between_table_entries():
    assert stats.t95(30) > stats.t95(35) > stats.t95(40)


def test_a_session_that_never_varies_has_no_interval():
    assert played(40, 25).rate()[1] == pytest.approx(0.0)


def test_more_hands_narrow_the_interval():
    short = Running()
    long = Running()
    pattern = [500, -500, 250, -250, 1000, -1000]
    for i in range(30):
        short.add_hand(pattern[i % len(pattern)])
    for i in range(300):
        long.add_hand(pattern[i % len(pattern)])
    assert long.rate()[1] < short.rate()[1]


def test_halving_the_interval_costs_four_times_the_hands():
    """Standard error falls with the square root, and ``hands_needed`` is the
    number that tells somebody why one evening cannot answer the question."""
    s = Running()
    pattern = [500, -500, 250, -250, 1000, -1000]
    for i in range(120):
        s.add_hand(pattern[i % len(pattern)])
    half = s.rate()[1]
    assert s.hands_needed(half) == pytest.approx(s.hands, rel=0.02)
    assert s.hands_needed(half / 2) == pytest.approx(4 * s.hands, rel=0.02)


def test_hands_needed_stays_quiet_on_a_sample_too_small_to_extrapolate_from():
    assert Running().hands_needed() is None
    assert played(10, 500).hands_needed() is None


# ----------------------------------------------------------- EV adjustment


def test_ev_adjusted_defaults_to_what_happened():
    s = Running()
    s.add_hand(500)
    s.add_hand(-500)
    assert s.rate(True) == s.rate(False)


def test_ev_adjustment_removes_the_variance_it_is_meant_to():
    """Get it in at 80% twice, win one and lose one. Observed swings the full
    pot each way; EV-adjusted says you won 80% of it both times."""
    s = Running()
    s.add_hand(2000, ev_cents=1200)
    s.add_hand(-2000, ev_cents=1200)
    for _ in range(20):
        s.add_hand(0, ev_cents=0)
    assert s.rate(True)[1] < s.rate(False)[1]
    assert s.rate(True)[0] > s.rate(False)[0]


def test_the_headline_uses_the_ev_adjusted_number():
    s = Running()
    for _ in range(60):
        s.add_hand(-100, ev_cents=100)
    assert "+" in s.headline()


# -------------------------------------------------------------- the money


def test_dollars_an_hour_is_the_rate_times_the_blind_times_the_pace():
    s = played(100, 25)          # exactly one big blind a hand
    money, half = s.hourly()
    assert money == pytest.approx(0.25 * HANDS_PER_HOUR)
    assert half == pytest.approx(0.0)


def test_per_hand_and_hourly_agree():
    s = Running()
    for i in range(50):
        s.add_hand(100 if i % 2 else -60)
    per_hand, _ = s.per_hand()
    money, _ = s.hourly()
    assert money == pytest.approx(per_hand * HANDS_PER_HOUR)


def test_a_losing_session_reads_as_a_loss():
    assert played(40, -50).hourly()[0] < 0


def test_the_pace_can_be_told_it_is_wrong():
    s = played(100, 25)
    assert s.hourly(hands_per_hour=54.0)[0] == pytest.approx(
        2 * s.hourly(hands_per_hour=27.0)[0])


# -------------------------------------------------------------- the bounty


def test_the_bounty_never_touches_the_poker_rate():
    """At 0.25/0.25 the bounty is large enough to swamp the cards, so a rate
    that quietly included it would say nothing about how somebody plays."""
    plain = played(40, 0)
    with_bounty = Running()
    for _ in range(40):
        with_bounty.add_hand(0, bounty_cents=300)
    assert with_bounty.rate() == plain.rate()
    assert with_bounty.hourly() == plain.hourly()
    assert with_bounty.bounty_hourly() > 0


def test_the_bounty_has_its_own_hourly():
    s = Running()
    for _ in range(10):
        s.add_hand(0, bounty_cents=100)
    assert s.bounty_hourly() == pytest.approx(1.0 * HANDS_PER_HOUR)


def test_no_hands_means_no_bounty_rate_rather_than_a_divide_by_zero():
    assert Running().bounty_hourly() == 0.0


def test_a_session_can_be_up_on_bounties_and_down_on_cards():
    s = Running()
    for _ in range(40):
        s.add_hand(-25, bounty_cents=200)
    assert s.hourly()[0] < 0
    assert s.bounty_hourly() > 0


# ------------------------------------------------------------- the hedging


def test_nine_hands_says_nothing():
    s = played(9, 2500)
    assert "too few" in s.headline()
    assert "hour" not in s.headline()


def test_an_interval_covering_zero_says_so():
    s = Running()
    pattern = [5000, -4800, 3000, -2900, 100, -50]
    for i in range(120):
        s.add_hand(pattern[i % len(pattern)])
    head = s.headline()
    assert "does not yet say whether you are winning" in head


def test_a_rate_clear_of_zero_is_stated_plainly():
    s = played(200, 30)          # steady, no variance at all
    head = s.headline()
    assert "does not yet say" not in head
    assert "over 200 hands" in head


def test_the_headline_always_gives_the_interval_with_the_number():
    """A dollar figure printed without one is the lie this module exists to
    avoid."""
    for s in (played(9, 100), played(200, 30)):
        head = s.headline()
        assert "give or take" in head or "too few" in head


# --------------------------------------------------------------- the HUD


def test_the_counters_are_percentages_of_the_right_denominator():
    s = Running()
    for _ in range(10):
        s.add_hand(0, vpip=True, pfr=True, saw_flop=True, showdown=True,
                   won_showdown=True)
    for _ in range(10):
        s.add_hand(0)
    out = s.summary()
    assert out["vpip"] == pytest.approx(50.0)
    assert out["pfr"] == pytest.approx(50.0)
    assert out["saw_flop"] == pytest.approx(50.0)
    # Went to showdown is out of flops seen, not hands dealt.
    assert out["wtsd"] == pytest.approx(100.0)
    # Won at showdown is out of showdowns reached.
    assert out["wsd"] == pytest.approx(100.0)


def test_three_bet_is_out_of_the_chances_to_three_bet():
    s = Running()
    for _ in range(3):
        s.add_hand(0, three_bet=True, three_bet_chance=True)
    for _ in range(7):
        s.add_hand(0, three_bet_chance=True)
    for _ in range(90):
        s.add_hand(0)
    assert s.summary()["three_bet"] == pytest.approx(30.0)


def test_a_stat_with_no_denominator_is_none_rather_than_zero():
    """Nought percent and "not yet known" are different claims."""
    out = Running().summary()
    assert out["vpip"] is None
    assert out["three_bet"] is None
    assert out["wtsd"] is None


def test_summary_is_json_safe():
    s = played(40, 25, vpip=True)
    s.add_review(FakeReview("error", 1.5), opponent="Sanjay")
    import json
    json.dumps(s.summary())


# -------------------------------------------------------------- the marks


def test_errors_are_counted_and_their_cost_added_up():
    s = Running()
    s.add_review(FakeReview("error", 1.5))
    s.add_review(FakeReview("error", 0.5))
    s.add_review(FakeReview("correct"))
    assert s.errors == 2
    assert s.error_bb == pytest.approx(2.0)
    assert s.summary()["error_rate"] == pytest.approx(200 / 3)


def test_an_exploit_is_not_an_error():
    s = Running()
    s.add_review(FakeReview("exploit"))
    assert s.errors == 0
    assert s.exploits == 1
    assert s.error_bb == 0.0


def test_an_unpriced_decision_counts_as_neither():
    s = Running()
    s.add_review(FakeReview("unpriced"))
    s.add_review(FakeReview("mixed"))
    s.add_review(FakeReview("thin", 0.3))
    assert s.errors == 0 and s.exploits == 0
    assert s.error_bb == 0.0
    assert s.decisions == 3


def test_an_error_with_no_priced_cost_still_counts_as_an_error():
    s = Running()
    s.add_review(FakeReview("error", None))
    assert s.errors == 1
    assert s.error_bb == 0.0


def test_mistakes_are_attributed_to_who_caused_them():
    s = Running()
    s.add_review(FakeReview("error", 2.0), opponent="Sanjay")
    s.add_review(FakeReview("correct"), opponent="Sanjay")
    s.add_review(FakeReview("error", 1.0), opponent="Ronit")
    by = s.summary()["by_opponent"]
    assert by["Sanjay"] == {"decisions": 2, "errors": 1, "lost_bb": 2.0}
    assert by["Ronit"]["lost_bb"] == pytest.approx(1.0)


# ----------------------------------------------------------- round tripping


def test_a_session_survives_the_database():
    s = played(30, 125, vpip=True, pfr=True)
    s.add_hand(-500, ev_cents=200, bounty_cents=300, showdown=True)
    s.add_review(FakeReview("error", 1.25), opponent="Bell")
    back = Running.from_dict(s.to_dict())
    assert back.summary() == s.summary()
    assert back.headline() == s.headline()


def test_a_restored_session_keeps_counting():
    s = played(30, 125)
    back = Running.from_dict(s.to_dict())
    back.add_hand(125)
    assert back.hands == 31
    assert back.rate()[0] == pytest.approx(s.rate()[0])
