"""The marking, which is the part this whole thing exists for.

These tests are less about the prose than about two properties the review has
to have if somebody is going to learn from it:

**Nothing may be labelled better than it is.** Every line carries a confidence,
every confidence has to be one of the five, and a chart line may never claim
``solver`` for a spot no solver covers.

**A verdict has to follow from its numbers.** Folding a hand that is a profit
against these ranges is an error; taking a line the chart mostly does is not;
and a call the chart folds but this table pays off is an *exploit*, not a
mistake - which is the distinction the file was written for.
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bounty
import ranges
import review
from cards import parse
from table import Decision


def decision(hole, **kw):
    """A decision with sane defaults, so each test states only what it means."""
    base = dict(
        street="preflop",
        position="CO",
        node=("rfi",),
        hole=parse(hole),
        board=[],
        pot=75,
        to_call=25,
        stack=5000,
        legal=["fold", "call", "raise"],
        opponents=1,
        seats=6,
        depth_bb=200.0,
        streak=0,
        in_position=True,
        opponents_in=[],
        action="call",
        amount=25,
    )
    base.update(kw)
    return Decision(**base)


def opponent(name="Ronit", position="UTG", action="raise", text="TT+,AQs+,AKo"):
    return {"name": name, "position": position, "action": action,
            "range": ranges.parse_range(text)}


def marks(r):
    return {line.label: line for line in r.lines}


# ------------------------------------------------------------ labelling


def test_every_confidence_is_one_of_the_five():
    """The scheme is worthless if a sixth label can leak in unnoticed."""
    rng = random.Random(1)
    for d in [
        decision("AsAd", action="raise", amount=250, to_call=25),
        decision("7h2c", action="fold"),
        decision("AsKs", node=("vs_rfi", "UTG"), position="BTN",
                 opponents_in=[opponent()]),
        decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 action="bet", amount=100, to_call=0,
                 opponents_in=[opponent(action="call")]),
        decision("9s8s", street="turn", node=None, board=parse("Ah7d2c5s"),
                 action="check", to_call=0, opponents_in=[opponent()]),
    ]:
        r = review.review_decision(d, rng=rng, iters=400)
        for line in r.lines:
            assert line.confidence in review.CONFIDENCE_TEXT, line
            assert line.to_dict()["confidence_text"]


def test_a_postflop_line_never_claims_a_solve():
    """No solver output covers six-handed postflop, so nothing may say so."""
    d = decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 opponents_in=[opponent(action="call")])
    r = review.review_decision(d, rng=random.Random(2), iters=400)
    assert all(line.confidence != "solver" for line in r.lines)


def test_the_equal_blind_small_blind_is_marked_heuristic():
    """The one node with no solve behind it has to say so every time."""
    d = decision("KsJd", position="SB", node=("rfi",), action="raise",
                 amount=75, to_call=12)
    r = review.review_decision(d)
    assert marks(r)["Equilibrium"].confidence == "heuristic"


def test_depth_does_not_launder_the_heuristic_into_a_derived_one():
    """200bb is deep enough to trip the depth adjustment. Adjusting a guess
    still leaves a guess, and the label has to keep saying so."""
    shallow = decision("KsJd", position="SB", node=("rfi",), depth_bb=100.0,
                       action="raise", amount=75, to_call=12)
    deep = decision("KsJd", position="SB", node=("rfi",), depth_bb=300.0,
                    action="raise", amount=75, to_call=12)
    for d in (shallow, deep):
        assert marks(review.review_decision(d))["Equilibrium"].confidence == "heuristic"


def test_an_uncharted_node_says_so_rather_than_guessing():
    d = decision("6s5s", node=("limped",), action="call")
    r = review.review_decision(d)
    line = marks(r)["Equilibrium"]
    assert line.confidence == "model"
    assert "not solved" in line.text or "No chart" in line.text
    assert r.verdict == "unpriced"


def test_a_review_serialises_whole():
    d = decision("AsAd", action="raise", amount=250)
    r = review.review_decision(d)
    out = r.to_dict()
    assert out["hole"] == "As Ad"
    assert out["verdict"] == r.verdict
    assert len(out["lines"]) == len(r.lines)
    assert all(set(x) >= {"label", "text", "confidence"} for x in out["lines"])


# -------------------------------------------------------------- verdicts


def test_raising_aces_is_correct():
    r = review.review_decision(decision("AsAd", action="raise", amount=250))
    assert r.verdict == "correct"
    assert r.loss_bb is None


def test_folding_aces_is_an_error():
    r = review.review_decision(decision("AsAd", action="fold", to_call=25))
    assert r.verdict == "error"


def test_folding_seven_deuce_under_the_gun_is_correct():
    r = review.review_decision(decision("7h2c", position="UTG", action="fold"))
    assert r.verdict == "correct"


def test_a_hand_the_chart_plays_two_ways_is_mixed_not_wrong():
    """A hand three-bet 30% of the time is not seven tenths of a mistake.

    Opening ranges here are pure raise-or-fold, so the mixing to test against
    is in the defending nodes - which is also where mixing actually matters.
    """
    node, pos = ("vs_rfi", "CO"), "BTN"
    chart = ranges.lookup(node, pos, seats=6, depth_bb=200.0)
    cls = next(c for c in ranges.CLASSES
               if review.MIXED_FLOOR <= chart.freqs(c).get("3bet", 0) < review.CORRECT_FLOOR)
    d = decision(_combo_of(cls), position=pos, node=node, action="raise",
                 amount=900, to_call=250)
    assert review.review_decision(d).verdict == "mixed"


def test_the_same_hand_played_the_other_way_is_also_not_a_mistake():
    """Both branches of a mix have to come back fine, or the mark is telling
    somebody to stop mixing."""
    node, pos = ("vs_rfi", "CO"), "BTN"
    chart = ranges.lookup(node, pos, seats=6, depth_bb=200.0)
    cls = next(c for c in ranges.CLASSES
               if review.MIXED_FLOOR <= chart.freqs(c).get("call", 0) < review.CORRECT_FLOOR
               and review.MIXED_FLOOR <= chart.freqs(c).get("3bet", 0))
    d = decision(_combo_of(cls), position=pos, node=node, action="call",
                 to_call=250)
    assert review.review_decision(d).verdict in ("mixed", "correct")


def _combo_of(cls):
    """A concrete two-card holding for a class like ``A5s`` or ``KQo``."""
    hi, lo = cls[0], cls[1]
    if len(cls) == 2:
        return f"{hi}s{lo}h"
    return f"{hi}s{lo}s" if cls[2] == "s" else f"{hi}s{lo}h"


# ------------------------------------------------- the exploit distinction


SANJAY = "22+,A2s+,K2s+,Q4s+,J6s+,T6s+,95s+,85s+,74s+,64s+,53s+,A2o+,K5o+,Q7o+,J8o+,T8o+,97o+,87o"


def _bb_facing(to_call, pot, hand, text=SANJAY, action="call"):
    """The big blind facing a raise from the cutoff, at whatever price."""
    opp = opponent(name="Sanjay", position="CO", action="raise", text=text)
    return decision(hand, position="BB", node=("vs_rfi", "CO"), action=action,
                    to_call=to_call, pot=pot, opponents_in=[opp])


def test_a_chart_fold_at_a_price_the_chart_never_sees_is_an_exploit():
    """The distinction the whole verdict scheme was written for.

    Somebody min-raises to 2bb. The blinds are equal, so there is 2bb dead and
    the hero owes 1bb into a pot of 4bb - four to one, a price no solved
    opening chart is built for, because nobody solves min-raises. The chart
    folds 96o. At four to one it is a clear profit, and marking it ``error``
    would teach the hero to fold correct calls.
    """
    r = review.review_decision(_bb_facing(25, 100, "9s6h"),
                               rng=random.Random(7), iters=4000)
    assert r.verdict == "exploit"
    assert r.loss_bb is None
    ev = marks(r)["Calling is worth"].value
    assert ev > 0


def test_the_same_hand_at_a_real_price_is_an_error():
    """Facing a normal 2.5x open the hero owes 9bb to win 12 - and now the
    chart's fold is simply right. The verdict has to move with the price."""
    r = review.review_decision(_bb_facing(225, 300, "9s6h"),
                               rng=random.Random(7), iters=4000)
    assert r.verdict == "error"
    assert r.loss_bb > 0


def test_the_exploit_headline_does_not_claim_an_uncomputed_comparison():
    """It may say what the call is worth against these ranges. It may not say
    what it would be worth against somebody else - nothing measured that, and
    at four to one it is a profit against everybody."""
    r = review.review_decision(_bb_facing(25, 100, "9s6h"),
                               rng=random.Random(7), iters=4000)
    assert "solid opener" not in r.headline
    assert "tighter opener" not in r.headline


def test_an_exploit_needs_the_ev_to_be_positive():
    """Without a live opponent to compute EV against, it is not an exploit."""
    d = decision("9s8h", position="UTG", node=("rfi",), action="raise",
                 amount=250, opponents_in=[])
    r = review.review_decision(d)
    assert r.verdict != "exploit"


# ------------------------------------------------------ pot odds and bounty


def test_pot_odds_are_arithmetic_and_right():
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=100, pot=300, action="call", opponents_in=[])
    line = marks(review.review_decision(d))["Pot odds"]
    assert line.confidence == "arithmetic"
    assert line.value == pytest.approx(0.25)


def test_the_bounty_goes_into_the_pot_and_lowers_what_you_need():
    """Folding breaks the streak as surely as losing, so it is not a bonus."""
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=100, pot=300, streak=2, action="call", opponents_in=[])
    lines = marks(review.review_decision(d, bounty_on=True, opponents=5))
    assert "Bounty" in lines
    assert lines["Bounty"].value < lines["Pot odds"].value
    assert lines["Bounty"].confidence == "arithmetic"


def test_no_streak_means_no_bounty_line():
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=100, pot=300, streak=0, action="call")
    assert "Bounty" not in marks(review.review_decision(d, bounty_on=True))


def test_the_bounty_toggle_is_honoured():
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=100, pot=300, streak=3, action="call")
    assert "Bounty" not in marks(review.review_decision(d, bounty_on=False))


def test_the_bounty_moves_the_verdict_when_it_is_big_enough():
    """A streak of four is worth tens of big blinds. It has to be able to turn
    a fold that would otherwise be fine into a fold that costs money."""
    board = parse("Ah7d2c")
    opp = [opponent(name="Sanjay", action="bet", text="22+,A2s+,K5s+,Q8s+,J8s+,"
                                                      "A2o+,K9o+,QTo+,JTo")]
    spot = dict(street="flop", node=None, board=board, to_call=200, pot=600,
                action="fold", opponents_in=opp)
    plain = review.review_decision(decision("9s9h", streak=0, **spot),
                                   bounty_on=True, rng=random.Random(3), iters=800)
    streaking = review.review_decision(decision("9s9h", streak=4, **spot),
                                       bounty_on=True, rng=random.Random(3), iters=800)
    plain_odds = marks(plain)["Pot odds"].value
    assert marks(streaking)["Bounty"].value < plain_odds


# -------------------------------------------------------- range modelling


def test_who_is_in_lists_only_the_live_opponents():
    live = opponent(name="Bell", action="call")
    folded = opponent(name="Sanjay", action="fold")
    d = decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=0, action="check", opponents_in=[live, folded])
    line = marks(review.review_decision(d, rng=random.Random(4), iters=400))["Who is in"]
    assert "Bell" in line.text and "Sanjay" not in line.text


def test_your_equity_is_modelled_not_claimed_as_equilibrium():
    d = decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=0, action="check", opponents_in=[opponent(action="call")])
    line = marks(review.review_decision(d, rng=random.Random(5), iters=800))["Your equity"]
    assert line.confidence == "model"
    assert 0.0 <= line.value <= 1.0


def test_top_pair_top_kicker_beats_that_range_more_often_than_not():
    """A sanity check on the direction of the model number, not its digits."""
    d = decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=0, action="check", opponents_in=[opponent(action="call")])
    line = marks(review.review_decision(d, rng=random.Random(6), iters=2000))["Your equity"]
    assert line.value > 0.5


def test_a_dead_card_cannot_be_in_an_opponent_range():
    """The hero holds two aces, so no opponent may be dealt one - if the
    combos were not filtered the equity would be quietly wrong."""
    d = decision("AsAd", street="flop", node=None, board=parse("Ac7d2h"),
                 to_call=0, action="check",
                 opponents_in=[opponent(action="call", text="AA")])
    r = review.review_decision(d, rng=random.Random(8), iters=400)
    # Only AhAs remains and the hero holds As, so nothing is left: the review
    # must drop the equity line rather than invent a number.
    assert "Your equity" not in marks(r)


# ---------------------------------------------------------- unpriced things


def test_a_bet_is_context_not_a_score():
    d = decision("AsKs", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=0, pot=400, action="bet", amount=200, opponents_in=[])
    r = review.review_decision(d)
    assert r.verdict == "unpriced"
    sizing = marks(r)["Your sizing"]
    assert sizing.confidence == "arithmetic"
    assert sizing.value == pytest.approx(1 / 3)


def test_folding_prints_the_frequency_that_makes_it_bad():
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=100, pot=300, action="fold", opponents_in=[])
    line = marks(review.review_decision(d))["If you fold everything like this"]
    assert line.confidence == "arithmetic"
    assert line.value == pytest.approx(2 / 3)


def test_no_defence_line_when_nobody_bet():
    d = decision("9s8h", street="flop", node=None, board=parse("Ah7d2c"),
                 to_call=0, pot=300, action="check")
    assert "If you fold everything like this" not in marks(review.review_decision(d))


def test_checking_the_best_hand_is_called_out():
    d = decision("AsAh", street="turn", node=None, board=parse("Ad7d2c5s"),
                 to_call=0, pot=800, action="check",
                 opponents_in=[opponent(action="check", text="KQs,QJs,JTs")])
    r = review.review_decision(d, rng=random.Random(9), iters=600)
    assert "Checking here" in marks(r)
    assert r.verdict == "thin"


# ------------------------------------------------------------- whole hands


def test_review_hand_skips_decisions_that_were_never_acted_on():
    """A spot the hero is sitting in right now has no action and no mark."""
    class FakeTable:
        bb = 25
        bounty_on = True
        seat_names = ["you", "Ronit", "Bell"]
        decisions = [decision("AsAd", action="raise", amount=250),
                     decision("KsKd", action=None, amount=None)]

    out = review.review_hand(FakeTable(), rng=random.Random(10), iters=200)
    assert len(out) == 1


def test_adaptation_notes_read_as_sentences():
    class FakeMemory:
        def notes(self):
            return ["has started three-betting you light"]

    class FakeBot:
        memory = FakeMemory()
        tilt = 0.9

    class FakeTable:
        bots = {"Sanjay": FakeBot()}

    out = review.adaptation_notes(FakeTable())
    assert out[0].startswith("Sanjay ") and out[0].endswith(".")
    assert any("steaming" in n for n in out)


def test_a_fold_the_chart_likes_but_this_table_pays_for_is_an_exploit():
    """The same disagreement as the test above, pointing the other way.

    96o at four to one is a call the chart never makes, and folding it is a
    fold the chart makes every time - so the chart calls the fold correct while
    the model, four lines below on the same panel, prices the call at most of a
    big blind. The review used to print both and mark the hand ``correct``,
    which is the review contradicting itself in one screen. The chart is still
    right about equilibrium; it is not right about Sanjay.
    """
    r = review.review_decision(_bb_facing(25, 100, "9s6h", action="fold"),
                               rng=random.Random(7), iters=4000)
    assert r.verdict == "exploit"
    assert r.loss_bb and r.loss_bb > review.EXPLOIT_FLOOR


def test_a_fold_the_chart_also_hates_is_an_error_and_not_a_read():
    """An exploit needs the chart to *disagree* with the table.

    Equilibrium calls JTo in the big blind 100% of the time and so does the
    model. Folding it is not a read about Sanjay, it is a mistake both sources
    agree on, and calling it an exploit would dress up an error as insight -
    with a "but" joining two clauses that say the same thing.
    """
    r = review.review_decision(_bb_facing(25, 100, "JsTh", action="fold"),
                               rng=random.Random(7), iters=4000)
    assert r.verdict == "error"
    assert "but" not in r.headline


def test_folding_correctly_is_still_correct():
    """The exploit branch must not swallow every fold it sees. 72o folded to a
    raise is the chart and the table agreeing, and it gets no tag at all."""
    r = review.review_decision(_bb_facing(75, 100, "7h2c", action="fold"),
                               rng=random.Random(7), iters=4000)
    assert r.verdict == "correct"
    assert r.loss_bb is None


def test_a_mixed_hand_is_described_against_a_different_action():
    """"It calls 70% and calls 70%" is not a sentence about a mixed strategy.

    `mixed` spans 20% to 75%, and the action the hero took is usually also the
    chart's most frequent one inside that band - so comparing against "the most
    frequent action" compared it against itself.
    """
    node, pos = ("vs_rfi", "CO"), "BTN"
    chart = ranges.lookup(node, pos, seats=6, depth_bb=200.0)
    seen = 0
    for cls in ranges.CLASSES:
        for action, name in (("call", "call"), ("raise", "3bet")):
            freq = chart.freqs(cls).get(name, 0.0)
            if not review.MIXED_FLOOR <= freq < review.CORRECT_FLOOR:
                continue
            d = decision(_combo_of(cls), position=pos, node=node,
                         action=action, to_call=250, amount=900)
            r = review.review_decision(d)
            if r.verdict != "mixed":
                continue
            seen += 1
            took, against = r.headline.split(" It ")[1].split(" and ")
            assert took.split()[0] != against.split()[0], r.headline
    assert seen, "no mixed verdict was produced to check"


def test_a_chopped_pot_is_a_bucket_on_the_river_and_not_a_missing_combination():
    """The counts printed have to add up to the total printed beside them.

    A tie is the only way to score exactly half a pot with no cards to come, so
    on a river every chop landed in a bucket that was named "" and dropped -
    printing "1 you beat; 337 beat you" against a total of 339.
    """
    import re

    import bots as bots_module
    import profiles

    bot = bots_module.Bot(profiles.FRIENDS[0], random.Random(2))
    for hole, board in (("9s9d", "9h9c2s3d4h"), ("AhKd", "AcKcQsJsTs"),
                        ("2c3d", "AsKsQsJsTs")):
        opp = opponent(name=bot.profile.name, position="CO", action="raise",
                       text=SANJAY)
        d = decision(hole, street="river", node=None, board=parse(board),
                     action="check", to_call=0, pot=400, amount=0,
                     opponents_in=[opp])
        r = review.review_decision(d, rng=random.Random(3), iters=200,
                                   bots={bot.profile.name: bot})
        line = next((x for x in r.lines
                     if x.label == "Where that equity comes from"), None)
        assert line is not None, f"no decomposition on {board}"
        total = int(re.search(r"have (\d+) combinations", line.text).group(1))
        counted = sum(int(n) for n in re.findall(r"(\d+)\u00d7", line.text))
        assert counted == total, f"{counted} of {total}: {line.text}"
