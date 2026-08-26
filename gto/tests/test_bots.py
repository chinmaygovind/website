"""The five brains, and whether they play like the people they describe.

The fast tests check **shape**: that ranges widen with position, that the tight
players are tighter than the loose ones everywhere, that nobody folds aces and
nobody opens 72o.

The slow one checks **calibration**: it deals thousands of hands and measures
each bot's VPIP and PFR against the numbers on its profile. That test is what
makes those numbers mean anything - ``vpip=58`` is a claim about behaviour, and
until something measures the behaviour it is decoration. It is marked
``calibration`` and left out of a normal run; see ``pytest.ini``.

Two bugs are pinned here because neither one failed anything - both just made
the bots quietly wrong:

* ``entrants`` used to be everybody dealt in rather than everybody who had put
  money in, so every preflop range was multiplied by ``MULTIWAY_TIGHTEN ** 4``
  before a card was played. A stated 58 VPIP measured 47.
* the raise frequency was rolled twice, once to reject calling and once to
  accept raising, which squares it. Every bot's PFR came out at about half.
"""

import collections
import random

import pytest

import bots
import profiles
import ranges
from cards import parse

BY_KEY = {p.key: p for p in profiles.FRIENDS}


def bot(key, seed=1):
    return bots.Bot(BY_KEY[key], random.Random(seed))


# ----------------------------------------------------------- range shape


@pytest.mark.parametrize("key", sorted(BY_KEY))
def test_opening_ranges_widen_from_early_to_late(key):
    b = bot(key)
    widths = [b.preflop_range(("rfi",), p).pct()
              for p in ("UTG", "HJ", "CO", "BTN")]
    assert widths == sorted(widths)


def test_vpip_is_a_session_average_not_a_position(key="ronit"):
    """A 19/16 nit opens about 12% first in and about 30% on the button.

    Both average to 19. Treating vpip as a per-position number gives a bot that
    opens as many hands under the gun as on the button, which is not a person.
    """
    b = bot(key)
    utg = b.preflop_range(("rfi",), "UTG").pct()
    btn = b.preflop_range(("rfi",), "BTN").pct()
    assert utg < BY_KEY[key].vpip < btn
    assert btn > utg * 2


def test_position_awareness_is_itself_a_skill():
    """The disciplined players have a wider spread between seats than the wild one."""
    def spread(key):
        b = bot(key)
        return (b.preflop_range(("rfi",), "BTN").pct()
                / b.preflop_range(("rfi",), "UTG").pct())
    assert spread("ronit") > spread("sanjay")


@pytest.mark.parametrize("pos", ["UTG", "CO", "BTN"])
def test_the_tight_players_are_tighter_than_the_loose_ones_everywhere(pos):
    order = ["ronit", "aarav", "apurva", "bell", "sanjay"]
    widths = [bot(k).preflop_range(("rfi",), pos).pct() for k in order]
    assert widths == sorted(widths)


@pytest.mark.parametrize("key", sorted(BY_KEY))
def test_everybody_plays_aces_and_nobody_opens_the_worst_hand(key):
    b = bot(key)
    for pos in ("UTG", "HJ", "CO", "BTN"):
        r = b.preflop_range(("rfi",), pos)
        assert r.weight("AA") == 1.0, (key, pos)
        assert r.weight("72o") == 0.0, (key, pos)


def test_discipline_decides_how_much_of_the_range_is_the_chart():
    """Ronit's extra hands are the chart's; Sanjay's are the ones he likes."""
    chart = ranges.lookup(("rfi",), "BTN").actions["raise"]
    ronit = bot("ronit").preflop_range(("rfi",), "BTN")
    sanjay = bot("sanjay").preflop_range(("rfi",), "BTN")

    def agreement(r):
        played = {c for c in r if r[c] > 0.5}
        return len(played & {c for c in chart if chart[c] > 0.5}) / max(1, len(played))

    assert agreement(ronit) > agreement(sanjay)


def test_a_loose_player_plays_hands_that_merely_look_good():
    """Offsuit kings on the button: nobody correct plays K4o, Sanjay does."""
    sanjay = bot("sanjay").preflop_range(("rfi",), "BTN")
    ronit = bot("ronit").preflop_range(("rfi",), "BTN")
    assert sanjay.weight("K4o") > 0.5
    assert ronit.weight("K4o") == 0.0


def test_a_multiway_pot_tightens_and_limpers_widen():
    b = bot("bell")
    alone = b.preflop_range(("rfi",), "BTN").pct()
    multi = b.preflop_range(("rfi",), "BTN", entrants=3).pct()
    limped = b.preflop_range(("rfi",), "BTN", limpers=2).pct()
    assert multi < alone < limped


# ------------------------------------------------------------- decisions


def test_a_bot_always_returns_something_legal_shaped():
    rng = random.Random(2)
    for key in BY_KEY:
        b = bot(key, 3)
        for _ in range(200):
            hole = rng.sample(range(52), 2)
            kind, _ = b.preflop_action(("rfi",), "BTN", hole, 25, 50, 5000)
            assert kind in ("fold", "check", "call", "raise")


def test_aces_are_never_folded_preflop():
    for key in BY_KEY:
        b = bot(key, 5)
        for _ in range(60):
            kind, _ = b.preflop_action(("rfi",), "UTG", parse("AsAh"), 25, 50, 5000)
            assert kind != "fold"


def test_the_worst_hand_is_never_raised_from_under_the_gun():
    for key in BY_KEY:
        b = bot(key, 5)
        for _ in range(60):
            kind, _ = b.preflop_action(("rfi",), "UTG", parse("7s2d"), 25, 50, 5000)
            assert kind == "fold"


def test_postflop_returns_a_sane_size():
    b = bot("apurva", 8)
    for _ in range(200):
        kind, size = b.postflop_action(
            parse("AsKs"), parse("Qs7h2d"), 0, 100, 5000, 1,
            in_position=True, is_aggressor=True, street="flop")
        assert kind in ("check", "bet")
        if kind == "bet":
            assert 0.25 <= size <= 1.5


def test_a_monster_is_not_folded_to_a_bet():
    b = bot("ronit", 4)
    folds = sum(
        b.postflop_action(parse("7s7c"), parse("7h2d9c"), 100, 300, 5000, 1,
                          in_position=True, is_aggressor=False, street="flop")[0] == "fold"
        for _ in range(200))
    assert folds == 0


def test_the_loose_player_calls_more_than_the_nit_with_ace_high():
    """Ace high on a king-high board, facing two thirds of the pot.

    It beats most *random* hands and almost none of the hands that bet, which is
    the distinction the bots have to make and the one Sanjay does not.
    """
    def calls(key):
        b = bot(key, 6)
        return sum(
            b.postflop_action(parse("Ah3d"), parse("7h2dKc"), 400, 600, 5000, 1,
                              in_position=False, is_aggressor=False,
                              street="flop")[0] in ("call", "raise")
            for _ in range(300))
    assert calls("sanjay") > calls("ronit")


# ----------------------------------------------------------------- tilt


def test_losing_a_big_pot_widens_a_bot_and_it_decays():
    b = bot("ronit")
    before = b.preflop_range(("rfi",), "CO").pct()
    b.lost_pot(bb_lost=150, bb_stack=200)
    assert b.tilt > 0
    assert b.preflop_range(("rfi",), "CO").pct() > before
    for _ in range(30):
        b.hand_over()
    assert b.tilt < 0.05


def test_the_fast_tilter_tilts_faster_than_the_one_who_never_does():
    fast, never = bot("ronit"), bot("sanjay")
    fast.lost_pot(100, 200)
    never.lost_pot(100, 200)
    assert fast.tilt > never.tilt


# -------------------------------------------------------------- memory


def test_a_bot_notices_a_player_who_folds_too_much_and_says_so():
    m = bots.Memory()
    for _ in range(20):
        m.saw_cbet(folded=True)
    assert m.hero_folds_too_much > 0.5
    assert any("fold" in n for n in m.notes())


def test_a_bot_will_not_act_on_two_observations():
    m = bots.Memory()
    m.saw_cbet(folded=True)
    m.saw_cbet(folded=True)
    assert m.hero_folds_too_much == 0.0
    assert m.notes() == []


def test_noticing_a_folder_makes_a_bot_bet_more():
    quiet, watching = bot("apurva", 11), bot("apurva", 11)
    for _ in range(30):
        watching.memory.saw_cbet(folded=True)

    def bets(b):
        b.rng = random.Random(11)
        return sum(
            b.postflop_action(parse("7s6c"), parse("AhKdQc"), 0, 200, 5000, 1,
                              in_position=True, is_aggressor=True,
                              street="flop")[0] == "bet"
            for _ in range(400))
    assert bets(watching) > bets(quiet)


def test_memory_survives_a_round_trip():
    m = bots.Memory()
    m.saw_cbet(folded=True)
    m.saw_hand(entered=True)
    assert bots.Memory.from_dict(m.to_dict()).to_dict() == m.to_dict()


# --------------------------------------------------------------- timing


def test_nobody_answers_instantly_and_the_slow_one_is_slower():
    fast, slow = bot("sanjay"), bot("bell")
    a = [fast.think_time(close=False) for _ in range(200)]
    b = [slow.think_time(close=False) for _ in range(200)]
    assert min(a) > 0.1
    assert sum(b) / len(b) > sum(a) / len(a)


def test_a_hard_spot_sometimes_gets_a_long_think():
    b = bot("bell", 12)
    times = [b.think_time(close=True) for _ in range(400)]
    assert max(times) > 4.0


# ---------------------------------------------------------- calibration


@pytest.mark.calibration
def test_measured_frequencies_match_the_profiles():
    """Deal a few thousand hands and check the bots do what their profiles say.

    Tolerance is generous on purpose. These are stochastic agents and the
    profile numbers are a description rather than a specification - what this
    catches is a bot playing 47% when it says 58, which is the kind of error
    that makes a whole session feel wrong without anything failing.
    """
    import table as T
    from engine import PREFLOP

    rng = random.Random(20260825)
    hero_profile = BY_KEY["apurva"].copy()
    hero_profile.key = hero_profile.name = "hero"
    hero = bots.Bot(hero_profile, rng)
    opponents = [bots.Bot(p, rng) for p in profiles.FRIENDS]
    t = T.Table("hero", opponents, rng=rng, seats=6)

    dealt = collections.Counter()
    vpip = collections.Counter()
    pfr = collections.Counter()

    for _ in range(2500):
        if t.needs_rebuy():
            t.rebuy()
        t.new_hand()
        for n in t.seat_names:
            dealt[n] += 1
        guard = 0
        while not t.hand.complete:
            guard += 1
            assert guard < 400, "a hand failed to finish"
            idx = t.hand.to_act
            if idx is None:
                break
            if t.seat_names[idx] != "hero":
                t.advance()
                continue
            seat = t.hand.seats[idx]
            legal = {a["action"]: a for a in t.hand.legal_actions()}
            if t.hand.street == PREFLOP:
                kind, size = hero.preflop_action(
                    T.preflop_node(t.hand, t.positions), t.positions[idx],
                    seat.hole, t.hand.call_amount(idx), t.hand.pot, seat.stack,
                    seats=len(t.seat_names), depth_bb=seat.stack / t.bb,
                    entrants=t._preflop_entrants()[1])
            else:
                kind, size = hero.postflop_action(
                    seat.hole, t.hand.board, t.hand.call_amount(idx), t.hand.pot,
                    seat.stack, max(1, len(t.hand.contenders) - 1),
                    in_position=t._in_position(idx), is_aggressor=False,
                    street=t.hand.street)
            t.hero_act(t._legalise(kind, size, legal, idx))

        # **Both counters are once per hand per player**, which is what VPIP
        # and PFR mean - somebody who calls and then calls a three-bet has
        # played one hand, not two.
        voluntary, raised = set(), set()
        for a in t.hand.actions:
            if a["street"] != PREFLOP:
                continue
            if a["action"] in ("call", "raise", "bet"):
                voluntary.add(a["name"])
            if a["action"] in ("raise", "bet"):
                raised.add(a["name"])
        for n in voluntary:
            vpip[n] += 1
        for n in raised:
            pfr[n] += 1

    for p in profiles.FRIENDS:
        n = p.name
        played = 100.0 * vpip[n] / dealt[n]
        raised = 100.0 * pfr[n] / dealt[n]
        assert abs(played - p.vpip) < 6.0, (
            f"{n} plays {played:.1f}% of hands, profile says {p.vpip}%")
        assert abs(raised - p.pfr) < 6.0, (
            f"{n} raises {raised:.1f}% of hands, profile says {p.pfr}%")
        # A profile is a pair, and the gap between them is as much of the
        # description as either number: somebody who plays 58 and raises 31 is
        # a different player from one who plays 58 and raises 55.
        assert raised <= played + 0.5, (
            f"{n} raises more hands ({raised:.1f}%) than it plays ({played:.1f}%)")
