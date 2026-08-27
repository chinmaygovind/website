"""The closed form has to be the same function the bots actually are.

``rollout.response`` is a hand transcription of the ``to_call > 0`` branch of
``Bot.postflop_action``, and a transcription is a thing that drifts. Everything
``rollout.py`` says about a bet size is downstream of it, so these tests deal
the real method a few thousand times and check the frequencies land on the
closed form's numbers. **If these fail, the bet-sizing page is lying**, and the
fix is to re-read `bots.py` rather than to widen the tolerance.
"""

import random

import pytest

import bots
import equity as eq
import profiles
import ranges
import rollout
import texture
from cards import parse_card as pc


def cards(text):
    return [pc(x) for x in text.split()]


def a_bot(key="bell", seed=4):
    profile = next(p for p in profiles.FRIENDS if p.key == key)
    return bots.Bot(profile, random.Random(seed))


SPOTS = [
    ("As Kd", "Qs 7h 2c", 60, 160, "flop", True),
    ("7h 7s", "Ac Kd 4s", 200, 400, "flop", False),
    ("9d 8d", "Td 7c 2h", 100, 300, "flop", True),
    ("Ah Qc", "Ad 9s 3h", 150, 450, "turn", False),
    ("2c 3d", "Kh Qd Js 4c", 400, 800, "turn", True),
    ("Kc Ks", "Kd 8h 3c 2s 9d", 250, 700, "river", False),
]


@pytest.mark.parametrize("hole,board,to_call,pot,street,ip", SPOTS)
def test_the_closed_form_is_the_frequency_the_bot_actually_plays(
        hole, board, to_call, pot, street, ip):
    hole, board = cards(hole), cards(board)
    for key in ("ronit", "bell", "sanjay"):
        bot = a_bot(key)
        pf, pc_, pr, _size = rollout.response(
            bot, hole, board, to_call=to_call, pot=pot, opponents=1,
            in_position=ip, street=street)

        n = 4000
        seen = {"fold": 0, "call": 0, "raise": 0}
        bot.rng = random.Random(99)
        for _ in range(n):
            kind, _ = bot.postflop_action(
                hole, board, to_call, pot, 5000, 1, in_position=ip,
                is_aggressor=False, street=street)
            seen[kind] += 1

        # Three standard errors on 4,000 draws is about 2.4 points at the worst
        # frequency, and this is a frequency against a frequency rather than a
        # point estimate against a truth, so 3.5 is the honest line.
        for name, want in (("fold", pf), ("call", pc_), ("raise", pr)):
            got = seen[name] / n
            assert abs(got - want) < 0.035, (
                f"{key} {name}: closed form {want:.3f}, played {got:.3f}")


def test_the_raise_size_is_the_average_of_the_one_the_bot_jitters():
    hole, board = cards("Kc Ks"), cards("Kd 8h 3c")
    bot = a_bot("sanjay")
    _f, _c, pr, size = rollout.response(
        bot, hole, board, to_call=100, pot=300, opponents=1, in_position=True,
        street="flop")
    assert pr > 0

    bot.rng = random.Random(7)
    drawn = [s for kind, s in (
        bot.postflop_action(hole, board, 100, 300, 5000, 1, in_position=True,
                            is_aggressor=False, street="flop")
        for _ in range(4000)) if kind == "raise"]
    assert drawn
    assert abs(sum(drawn) / len(drawn) - size) < 0.02


def test_probabilities_are_a_distribution():
    for hole, board, to_call, pot, street, ip in SPOTS:
        for key in ("ronit", "aarav", "bell", "sanjay"):
            pf, pc_, pr, _ = rollout.response(
                a_bot(key), cards(hole), cards(board), to_call=to_call,
                pot=pot, opponents=1, in_position=ip, street=street)
            assert min(pf, pc_, pr) >= 0.0
            assert abs(pf + pc_ + pr - 1.0) < 1e-9


# ------------------------------------------------------------------- pricing


def a_spot(hero="As Kd", board="Qs 7h 2c", key="bell"):
    bot = a_bot(key)
    hero, board = cards(hero), cards(board)
    rng_ = bot.range_after(("rfi",), "CO", "call", seats=6, depth_bb=200.0)
    combos = ranges.weighted_combos(rng_, dead=hero + board)
    equities = eq.combo_equities(hero, combos, board=board,
                                 rng=random.Random(1))
    return hero, board, bot, combos, equities


def test_a_bigger_bet_folds_out_more_and_is_called_by_better():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=5000,
                               opp_stack=5000, board=board, street="flop")
    bets = [s for s in sizes if not s.is_check]
    for small, big in zip(bets, bets[1:]):
        assert big.fold_pct >= small.fold_pct - 1e-9, (
            f"{big.fraction:.0%} folds out less than {small.fraction:.0%}")
        assert big.equity_called <= small.equity_called + 1e-9, (
            "a bigger bet should be called by a stronger range")


def test_checking_is_priced_as_the_share_of_the_pot_it_checks_down():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=5000,
                               opp_stack=5000, board=board, street="flop")
    check = sizes[0]
    assert check.is_check
    assert abs(check.ev - eq.combined(equities, combos) * 400) < 1e-6


def test_the_size_you_chose_is_in_the_curve_and_marked():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=5000,
                               opp_stack=5000, board=board, street="flop",
                               yours=173)
    mine = [s for s in sizes if s.is_yours]
    assert len(mine) == 1
    assert abs(mine[0].chips - 173) <= 8


def test_a_short_stack_cannot_bet_more_than_it_has():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=150,
                               opp_stack=5000, board=board, street="flop")
    assert all(s.chips <= 150 for s in sizes)


def test_the_nuts_prefers_a_bet_to_a_check():
    hero, board, bot, combos, equities = a_spot(hero="Qc Qd", board="Qs 7h 2c")
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=5000,
                               opp_stack=5000, board=board, street="flop")
    check = sizes[0]
    assert max(s.ev for s in sizes if not s.is_check) > check.ev


def test_a_size_that_ran_out_of_chips_appears_once_and_says_what_it_is():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=120,
                               opp_stack=5000, board=board, street="flop")
    bets = [s for s in sizes if not s.is_check]
    assert len(bets) == len({s.chips for s in bets}), (
        "clamped sizes were listed more than once")
    shove = [s for s in bets if s.all_in]
    assert shove and shove[0].chips == 120
    # 120 into 400 is 30% of the pot however big the fraction asked for was.
    assert abs(shove[0].fraction - 0.30) < 0.01


def test_a_curve_with_nothing_to_bet_is_just_the_check():
    hero, board, bot, combos, equities = a_spot()
    sizes = rollout.price_bets(combos, equities, bot, pot=400, hero_stack=0,
                               opp_stack=5000, board=board, street="flop")
    assert [s.is_check for s in sizes] == [True]
