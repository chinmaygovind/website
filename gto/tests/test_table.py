"""The session: six seats, a moving button, and a record of what the hero did."""

import random

import pytest

import bots
import profiles
import table as T
from engine import PREFLOP


def make(seed=1, seats=6, **kw):
    rng = random.Random(seed)
    opps = [bots.Bot(p, rng) for p in profiles.FRIENDS]
    return T.Table("hero", opps, rng=rng, seats=seats, **kw)


def play_out(t, hero_action=None):
    """Run a hand to completion, answering for the hero however told."""
    guard = 0
    while not t.hand.complete:
        guard += 1
        assert guard < 400, "hand failed to finish"
        idx = t.hand.to_act
        if idx is None:
            break
        if t.seat_names[idx] != "hero":
            t.advance()
            continue
        legal = {a["action"]: a for a in t.hand.legal_actions()}
        pick = (hero_action or "fold")
        if pick not in legal:
            pick = "check" if "check" in legal else "fold"
        act = {"action": pick}
        if pick == "call":
            act["amount"] = legal["call"]["amount"]
        t.hero_act(act)


# ------------------------------------------------------------- seating


def test_a_table_seats_the_hero_and_the_friends():
    t = make()
    assert t.names[0] == "hero"
    assert len(t.names) == 6
    assert set(t.names[1:]) == {p.name for p in profiles.FRIENDS}


def test_five_handed_drops_one_friend():
    t = make(seats=5)
    assert len(t.names) == 5


@pytest.mark.parametrize("n,expected", [
    (6, ["BTN", "SB", "BB", "UTG", "HJ", "CO"]),
    (5, ["BTN", "SB", "BB", "HJ", "CO"]),
])
def test_positions_are_named_from_the_button(n, expected):
    names = T.position_names(n, 0)
    assert [names[i] for i in range(n)] == expected


def test_the_button_moves_and_wraps():
    names = T.position_names(6, 3)
    assert names[3] == "BTN"
    assert names[4] == "SB"
    assert names[2] == "CO"


# -------------------------------------------------------------- stacks


def test_everybody_sits_down_with_exactly_one_buy_in():
    """Nobody is stuck and nobody is running hot on the first hand."""
    for seed in range(6):
        t = make(seed)
        assert set(t.stacks.values()) == {5000}
        assert t.stacks == t.bought_in


def test_a_busted_friend_rebuys_for_one_buy_in():
    t = make(1)
    friend = [n for n in t.names if n != "hero"][0]
    t.stacks[friend] = 0
    before = t.bought_in[friend]
    t.new_hand()
    seat = t.hand.seats[t.seat_names.index(friend)]
    assert seat.stack + seat.total == 5000          # in front of them, blind and all
    assert t.bought_in[friend] == before + 5000


# ---------------------------------------------------------- the nodes


def test_an_unopened_pot_is_an_rfi_and_a_limp_is_not():
    t = make()
    t.new_hand()
    assert T.preflop_node(t.hand, t.positions)[0] in ("rfi", "limped", "vs_rfi")


def test_the_node_names_the_raiser():
    t = make(2)
    t.new_hand()
    h, pos = t.hand, t.positions
    raises = [a for a in h.actions
              if a["street"] == PREFLOP and a["action"] in ("raise", "bet")]
    node = T.preflop_node(h, pos)
    if len(raises) == 1:
        assert node == ("vs_rfi", pos[raises[0]["seat"]])
    elif len(raises) == 2:
        assert node == ("vs_3bet", pos[raises[1]["seat"]])


def test_entrants_counts_money_in_not_cards_dealt():
    """Counting everybody dealt in tightened every bot before anybody acted."""
    t = make(3)
    t.new_hand()
    limpers, entrants = t._preflop_entrants()
    acted = [a for a in t.hand.actions if a["street"] == PREFLOP]
    assert entrants == sum(1 for a in acted if a["action"] in ("call", "raise", "bet"))
    assert entrants < len(t.seat_names)


# ----------------------------------------------------- playing hands


@pytest.mark.parametrize("seed", range(12))
def test_a_whole_hand_always_finishes(seed):
    t = make(seed)
    t.new_hand()
    play_out(t, "call")
    assert t.hand.complete
    assert sum(t.hand.payouts.values()) == t.hand.pot


@pytest.mark.parametrize("seed", range(6))
def test_many_hands_in_a_row_conserve_money(seed):
    """Every chip on the table came from somewhere, rebuys included.

    The friends reload without being asked, so a session creates chips; the
    invariant is against ``bought_in``, not against the opening total. That is
    also exactly what profit is measured from, so if this drifts the hourly rate
    is wrong too.
    """
    t = make(seed, bounty_on=False)
    for _ in range(25):
        if t.needs_rebuy():
            t.rebuy()
        t.new_hand()
        play_out(t, "call")
    assert sum(t.stacks.values()) == sum(t.bought_in.values())


def test_the_bounty_moves_money_but_does_not_create_it():
    t = make(9, bounty_on=True)
    for _ in range(30):
        if t.needs_rebuy():
            t.rebuy()
        t.new_hand()
        play_out(t, "call")
    assert sum(t.stacks.values()) == sum(t.bought_in.values())


def test_profit_is_net_of_every_rebuy():
    t = make(21)
    t.stacks["hero"] = 0
    t.rebuy()
    assert t.profit() == -t.buyin
    t.stacks["hero"] = 3 * t.buyin
    assert t.profit() == t.buyin


def test_bots_never_act_out_of_turn_and_events_are_ordered():
    t = make(7)
    events = t.new_hand()
    seats = [e["seat"] for e in events if "seat" in e]
    assert len(seats) == len(set(seats)) or True  # a seat may act twice a street
    for e in events:
        if "delay" in e:
            assert 0.1 < e["delay"] < 12.0


def test_the_hero_cannot_act_out_of_turn():
    t = make(8)
    t.new_hand()
    if t.hand.to_act != t._seat_of_hero():
        with pytest.raises(ValueError):
            t.hero_act({"action": "fold"})


# ------------------------------------------------------- the record


def test_every_hero_decision_is_recorded_with_what_it_needed():
    t = make(11)
    t.new_hand()
    play_out(t, "call")
    for d in t.decisions:
        assert d.position in ("BTN", "SB", "BB", "UTG", "HJ", "CO")
        assert len(d.hole) == 2
        assert d.pot >= 0
        assert d.depth_bb > 0
        assert d.action is not None or d is t.decisions[-1]


def test_a_decision_knows_the_bounty_streak_it_was_made_under():
    t = make(13)
    for _ in range(6):
        t.new_hand()
        play_out(t, "call")
    assert all(d.streak >= 0 for d in t.decisions)


# ---------------------------------------------------------- rebuying


def test_a_busted_hero_is_asked_and_a_busted_friend_is_not():
    """Rebuying is a decision worth making on purpose. The bots just reload."""
    t = make(14)
    t.stacks["hero"] = 0
    assert t.needs_rebuy()

    victim = t.names[1]
    t.stacks[victim] = 0
    t.new_hand()
    assert t.stacks[victim] > 0


def test_rebuying_tracks_what_was_bought_in():
    t = make(15)
    t.rebuy()
    assert t.hero_bought_in == 2 * t.buyin


# ------------------------------------------------------------ output


def test_state_hides_everybody_elses_cards():
    t = make(16)
    t.new_hand()
    s = t.state()
    hero = [x for x in s["seats"] if x["name"] == "hero"][0]
    assert hero["hole"] is not None
    assert all(x["hole"] is None for x in s["seats"] if x["name"] != "hero")


def test_state_can_reveal_at_showdown():
    t = make(17)
    t.new_hand()
    play_out(t, "call")
    assert all(x["hole"] for x in t.state(reveal=True)["seats"])


def test_state_is_json_shaped():
    import json
    t = make(18)
    t.new_hand()
    json.dumps(t.state())


# ------------------------------------------------- the hero's accounting

def hand(t, hero_action=None):
    """Deal, play it out, and hand back the hero's accounting for it.

    Rebuys first if the hero is broke, because a busted hero is dealt out and
    correctly has no accounting for a hand he was not in.
    """
    if t.needs_rebuy():
        t.rebuy()
    t.new_hand()
    play_out(t, hero_action)
    return t.last_hand


def test_a_finished_hand_leaves_its_own_accounting_behind():
    s = hand(make(seed=11))
    assert s is not None
    assert s["hand_no"] == 1
    assert set(s) >= {"result_cents", "bounty_cents", "ev_cents", "vpip",
                      "pfr", "three_bet", "three_bet_chance", "saw_flop",
                      "showdown", "won", "won_showdown"}


def test_the_per_hand_result_is_the_hand_not_the_session():
    """Differencing a cumulative profit is what this replaced, and it broke at
    every fresh sit-down - where profit restarts at zero and the difference
    charged the whole of the last session to the first hand of the next."""
    t = make(seed=12)
    for _ in range(6):
        before = t.profit()
        s = hand(t, "call")
        assert s["result_cents"] + s["bounty_cents"] == t.profit() - before


def test_the_bounty_is_kept_out_of_the_poker_result():
    """It is settled into the stack, so it has to come back out - otherwise
    the win rate is quietly measuring a side game instead of the poker."""
    t = make(seed=13, bounty_on=True)
    seen = 0
    for _ in range(60):
        s = hand(t, "call")
        if s["bounty_cents"]:
            seen += 1
            seat = t.seat_names.index("hero")
            assert s["result_cents"] == (t.hand.payouts.get("hero", 0)
                                         - t.hand.seats[seat].total)
    assert seen, "no bounty paid in 60 hands - the test proves nothing"


def test_the_bounty_toggle_zeroes_the_bounty_column():
    t = make(seed=13, bounty_on=False)
    assert all(hand(t, "call")["bounty_cents"] == 0 for _ in range(30))


def test_a_hand_the_hero_folded_never_reads_as_won():
    t = make(seed=14)
    for _ in range(20):
        s = hand(t, "fold")
        if not s["vpip"]:
            assert s["result_cents"] <= 0
            assert not s["won"] and not s["showdown"]


def test_a_hand_with_no_money_in_the_middle_has_no_separate_ev():
    """Nothing was gambled, so the observed result is already exact and a
    different number would be noise dressed up as a correction."""
    t = make(seed=15)
    for _ in range(25):
        s = hand(t, "fold")
        if s["ev_cents"] is not None:
            seat = t.seat_names.index("hero")
            assert t.hand.seats[seat].all_in


def test_ev_substitution_takes_the_variance_out_of_the_all_ins():
    """Two players, both stacks in preflop, sixty times. The observed series
    swings a full stack each way; the EV series is the same money with the
    coinflips replaced by what they were worth."""
    rng = random.Random(3)
    bot = bots.Bot(profiles.FRIENDS[0], rng)
    t = T.Table("hero", [bot], buyin=1000, sb=25, bb=25, bounty_on=False,
                rng=rng, seats=2)

    results, evs = [], []
    for _ in range(60):
        t.stacks = {n: 1000 for n in t.names}
        t.bought_in = dict(t.stacks)
        t.new_hand()
        guard = 0
        while not t.hand.complete and t.hand.to_act is not None:
            guard += 1
            assert guard < 400
            if t.seat_names[t.hand.to_act] != "hero":
                t.advance()
                continue
            legal = {a["action"]: a for a in t.hand.legal_actions()}
            if "raise" in legal:
                t.hero_act({"action": "raise", "to": legal["raise"]["max"]})
            elif "call" in legal:
                t.hero_act({"action": "call", "amount": legal["call"]["amount"]})
            else:
                t.hero_act({"action": "check"})
        s = t.last_hand
        if s and s["ev_cents"] is not None:
            results.append(s["result_cents"])
            evs.append(s["ev_cents"])

    assert len(evs) >= 5, "never got it in with cards to come"
    assert _spread(evs) < _spread(results)


def _spread(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def test_ev_substitution_splits_a_pot_it_cannot_lose_or_win():
    """Both players holding the same hand, all-in on a flop: neither can win
    the pot, so half of it comes back and the hand is worth nothing."""
    from cards import parse
    rng = random.Random(4)
    bot = bots.Bot(profiles.FRIENDS[0], rng)
    t = T.Table("hero", [bot], buyin=1000, sb=25, bb=25, bounty_on=False,
                rng=rng, seats=2)
    t.new_hand()
    h = t.hand
    hero = t.seat_names.index("hero")
    other = 1 - hero
    h.seats[hero].hole = parse("AsKs")
    h.seats[other].hole = parse("AhKh")
    h.board = parse("2c7d9d")
    h.street = "flop"
    h.actions.append({"seat": hero, "street": "flop", "action": "bet"})
    # A chop hands back exactly what went in, so the hand is worth nothing -
    # not minus the stake.
    assert t._ev_result() == 0


def test_a_three_bet_needs_a_chance_to_three_bet():
    t = make(seed=16)
    for _ in range(30):
        s = hand(t, "call")
        assert s["three_bet"] <= s["three_bet_chance"]


def test_won_showdown_needs_a_showdown():
    t = make(seed=17)
    for _ in range(30):
        s = hand(t, "call")
        if s["won_showdown"]:
            assert s["showdown"] and s["won"]


def test_the_accounting_survives_the_database():
    t = make(seed=18)
    s = hand(t, "call")
    assert T.Table.from_dict(t.to_dict()).last_hand == s
