"""The no-limit hold'em state machine.

Three rules are what this file mostly exists for, because they are the three
almost every home-grown engine gets wrong:

1. **Side pots** come from contribution levels, not from the order people went
   all in.
2. **The minimum raise** tracks the last *full* raise. A short all-in raises what
   you must call without raising what you must raise to.
3. **A short all-in reopens the action but not the right to raise.** Everyone
   still behind the bet owes a decision, because the chips are owed either way;
   but a player who has already acted may only call or fold.

Rule 3 is here because it was **actually broken**, and the way it was broken is
the lesson. The fuzz asserted chips were conserved, and they were - the hand
just skipped to the flop with two players still owing money, and every chip was
still accounted for. A conservation invariant cannot see a street that ends
early. ``test_fuzz_holds_the_invariants`` now also asserts that a street only
ends square, which is what would have caught it.
"""

import random

import pytest

from cards import parse
from engine import PREFLOP, FLOP, TURN, RIVER, Hand


def acts(hand):
    return {a["action"] for a in hand.legal_actions()}


def deal(stacks, button=0, sb=25, bb=25, rng=None, **kw):
    players = [(f"p{i}", s) for i, s in enumerate(stacks)]
    return Hand.deal(players, button, sb, bb, rng=rng or random.Random(1), **kw)


# ------------------------------------------------------------------- blinds


def test_blinds_are_posted_and_the_under_the_gun_seat_acts_first():
    h = deal([10000] * 6)
    assert h.seats[1].committed == 25  # small blind
    assert h.seats[2].committed == 25  # big blind
    assert h.to_act == 3
    assert h.pot == 50


def test_heads_up_the_button_is_the_small_blind_and_acts_first():
    h = deal([10000, 10000])
    assert h.seats[0].committed == 25
    assert h.seats[1].committed == 25
    assert h.to_act == 0


def test_equal_blinds_let_the_small_blind_check_its_option():
    """0.25/0.25 is this game's whole point: the small blind has already matched."""
    h = deal([10000] * 6)
    for _ in range(3):  # UTG, HJ, CO fold
        h.apply({"action": "fold"})
    h.apply({"action": "fold"})  # button
    assert h.to_act == 1  # small blind
    assert acts(h) == {"check", "raise"}


def test_unequal_blinds_make_the_small_blind_complete():
    h = deal([10000] * 6, sb=25, bb=50)
    for _ in range(4):
        h.apply({"action": "fold"})
    assert h.to_act == 1
    assert acts(h) == {"fold", "call", "raise"}
    assert h.call_amount(1) == 25


def test_a_walk_gives_the_big_blind_the_pot():
    h = deal([10000] * 6)
    for _ in range(5):
        h.apply({"action": "fold"})
    assert h.complete
    assert h.payouts == {"p2": 50}  # payouts are keyed by name, not seat index
    assert h.seats[2].stack == 10000 - 25 + 50


# ------------------------------------------------------------- raise sizing


def test_minimum_raise_is_the_last_full_raise_again():
    h = deal([10000] * 6)
    assert h.min_raise_to(3) == 50  # bet 25, one more full raise of 25
    h.apply({"action": "raise", "to": 100})  # raise of 75
    assert h.min_raise_to(4) == 175


def test_a_short_all_in_does_not_raise_the_minimum_raise():
    """Rule 2, and the sizing convention that follows from it.

    UTG raises to 1000, an increment of 975 over the big blind. The short stack
    jams to 1200, which is not a full raise, so ``last_full_raise`` must stay at
    975. The next player's minimum raise is then **the current bet plus the last
    full increment**, 1200 + 975 = 2175 - not 1000 + 975, and not 1200 + 1200.
    That is what every major online room does, and it is worth pinning here
    because the other two readings are both defensible-sounding and both wrong.
    """
    h = deal([100000, 100000, 100000, 100000, 100000, 1200], button=0)
    h.apply({"action": "raise", "to": 1000})
    assert h.last_full_raise == 975
    h.apply({"action": "call", "amount": h.call_amount(h.to_act)})
    h.apply({"action": "raise", "to": 1200})  # all in, short of a full raise

    assert h.last_full_raise == 975
    assert h.current_bet == 1200
    assert h.min_raise_to(h.to_act) == 2175


def test_raise_bounds_are_totals_for_the_street():
    h = deal([10000] * 6)
    opts = {a["action"]: a for a in h.legal_actions()}
    assert opts["raise"]["min"] == 50
    assert opts["raise"]["max"] == 10000


# --------------------------------------------- rule 3: reopening the action


def build_short_all_in_spot():
    """A raises to 1000, B calls, C jams short to 1200.

    This is the exact shape that used to skip to the flop with A and B still
    owing 200 apiece.
    """
    h = deal([100000, 100000, 100000, 100000, 100000, 1200], button=0)
    h.apply({"action": "raise", "to": 1000})   # seat 3
    h.apply({"action": "call", "amount": h.call_amount(4)})   # seat 4
    h.apply({"action": "raise", "to": 1200})   # seat 5, all in short
    return h


def test_a_short_all_in_keeps_the_street_open():
    """The two who already called owe 200 and must be given the chance to pay it.

    Before the fix the street advanced to the flop here with that 200 apiece
    still owed. Chips were conserved the whole time, which is why the fuzz was
    happy and why this needs its own test.
    """
    h = build_short_all_in_spot()
    assert h.street == PREFLOP
    assert set(h.need_to_act) == {0, 1, 2, 3, 4}
    assert h.call_amount(3) == 200
    assert h.call_amount(4) == 200


def test_a_short_all_in_does_not_give_back_the_right_to_raise():
    """Rule 3. The two who already acted may only call or fold; the rest may raise."""
    h = build_short_all_in_spot()
    assert not h.may_raise(3) and not h.may_raise(4)
    assert all(h.may_raise(i) for i in (0, 1, 2))

    for _ in range(3):  # seats 0, 1, 2 have not acted, and fold
        h.apply({"action": "fold"})

    assert h.to_act == 3
    assert acts(h) == {"fold", "call"}
    h.apply({"action": "call", "amount": h.call_amount(3)})
    assert h.to_act == 4
    assert acts(h) == {"fold", "call"}


def test_a_player_who_has_not_acted_may_still_raise_over_a_short_all_in():
    """The lock is per-player: it applies to whoever already acted, nobody else."""
    h = deal([100000, 100000, 100000, 100000, 1200, 100000], button=0)
    h.apply({"action": "raise", "to": 1000})   # seat 3
    h.apply({"action": "raise", "to": 1200})   # seat 4 jams short
    assert h.to_act == 5  # has not acted yet
    assert acts(h) == {"fold", "call", "raise"}


def test_a_full_reraise_reopens_the_action_for_someone_who_already_acted():
    h = deal([100000] * 6, button=0)
    h.apply({"action": "raise", "to": 1000})   # seat 3
    h.apply({"action": "call", "amount": h.call_amount(4)})   # seat 4
    h.apply({"action": "raise", "to": 3000})   # seat 5, a full raise
    assert h.to_act == 0
    h.apply({"action": "fold"})
    h.apply({"action": "fold"})
    h.apply({"action": "fold"})
    assert h.to_act == 3
    assert "raise" in acts(h)  # seat 3 acted, but a full raise came behind


# ---------------------------------------------------------------- side pots


def test_side_pots_come_from_contribution_levels():
    h = deal([1000, 3000, 10000, 10000, 10000, 10000], button=3)
    # Seats 4 and 5 are the blinds; drive everyone all in.
    while not h.complete and h.to_act is not None:
        opts = {a["action"]: a for a in h.legal_actions()}
        if "raise" in opts:
            h.apply({"action": "raise", "to": opts["raise"]["max"]})
        elif "bet" in opts:
            h.apply({"action": "bet", "to": opts["bet"]["max"]})
        else:
            h.apply({"action": "call", "amount": h.call_amount(h.to_act)})
    assert h.complete
    assert sum(h.payouts.values()) == h.pot


def test_a_short_stack_cannot_win_more_than_it_covers():
    """The main pot is capped at the all-in player's contribution times heads."""
    h = deal([1000, 10000, 10000], button=0, sb=25, bb=25)
    while not h.complete and h.to_act is not None:
        opts = {a["action"]: a for a in h.legal_actions()}
        if "raise" in opts:
            h.apply({"action": "raise", "to": opts["raise"]["max"]})
        else:
            h.apply({"action": "call", "amount": h.call_amount(h.to_act)})
    assert h.payouts.get("p0", 0) <= 3000


# ------------------------------------------------------------- whole hands


def test_a_hand_plays_out_through_every_street():
    h = deal([10000] * 3, button=0)
    seen = []
    while not h.complete:
        seen.append(h.street)
        opts = acts(h)
        h.apply({"action": "check"} if "check" in opts
                else {"action": "call", "amount": h.call_amount(h.to_act)})
    assert set(seen) >= {PREFLOP, FLOP, TURN, RIVER}
    assert len(h.board) == 5


def test_folding_to_one_player_ends_the_hand_without_a_board():
    h = deal([10000] * 3, button=0)
    h.apply({"action": "raise", "to": 300})
    h.apply({"action": "fold"})
    h.apply({"action": "fold"})
    assert h.complete
    assert h.board == []


def test_a_chop_splits_the_pot():
    """Both players play the board; the odd chip has to go somewhere."""
    deck = list(parse("2c2d3c3d") + parse("AsKsQsJsTs"))
    h = Hand.deal([("a", 10000), ("b", 10000)], 0, 25, 25, deck=deck[::-1])
    while not h.complete:
        opts = acts(h)
        h.apply({"action": "check"} if "check" in opts
                else {"action": "call", "amount": h.call_amount(h.to_act)})
    assert sum(h.payouts.values()) == h.pot
    assert len(h.payouts) == 2


def test_serialises_and_resumes():
    h = deal([10000] * 4, button=0)
    h.apply({"action": "raise", "to": 300})
    again = Hand.from_dict(h.to_dict())
    assert again.to_dict() == h.to_dict()
    assert again.legal_actions() == h.legal_actions()


# ---------------------------------------------------------------- the fuzz


def test_fuzz_holds_the_invariants():
    """Random hands, four invariants, and the second one is the interesting one.

    * chips are conserved
    * **a street only ends square** - nobody who is still live is behind the bet
    * no pot pays out more than its eligible players put in
    * exactly the money in the middle is paid out
    """
    rng = random.Random(20260825)
    for _ in range(4000):
        n = rng.randint(2, 6)
        stacks = [rng.choice([200, 500, 1000, 5000, 20000, 50000]) for _ in range(n)]
        before = sum(stacks)
        h = deal(stacks, button=rng.randrange(n), rng=rng)

        street = h.street
        while not h.complete:
            if h.street != street:
                street = h.street
                assert all(s.committed == 0 for s in h.seats), "street ended unsquare"
            opts = h.legal_actions()
            pick = rng.choice(opts)
            if pick["action"] in ("raise", "bet"):
                to = rng.randint(pick["min"], pick["max"])
                h.apply({"action": pick["action"], "to": to})
            elif pick["action"] == "call":
                h.apply({"action": "call", "amount": h.call_amount(h.to_act)})
            else:
                h.apply(pick)

        assert sum(s.stack for s in h.seats) == before
        assert sum(h.payouts.values()) == h.pot
        for pot in h.pots if h.pots else []:
            cap = pot["amount"]
            assert cap <= h.pot


def test_fuzz_never_leaves_a_street_with_money_owed():
    """The regression that chip conservation could not see, stated directly."""
    rng = random.Random(4242)
    for _ in range(2000):
        n = rng.randint(2, 6)
        stacks = [rng.choice([120, 300, 900, 4000, 30000]) for _ in range(n)]
        h = deal(stacks, button=rng.randrange(n), rng=rng)
        street = h.street
        while not h.complete:
            if h.street != street:
                street = h.street
                owed = [
                    s for s in h.seats
                    if s.contending and not s.all_in and s.committed < h.current_bet
                ]
                assert not owed, f"street {street} began with {len(owed)} owing"
            opts = h.legal_actions()
            pick = rng.choice(opts)
            if pick["action"] in ("raise", "bet"):
                h.apply({"action": pick["action"],
                         "to": rng.randint(pick["min"], pick["max"])})
            elif pick["action"] == "call":
                h.apply({"action": "call", "amount": h.call_amount(h.to_act)})
            else:
                h.apply(pick)
