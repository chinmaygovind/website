"""The preflop reference charts, and the claims made about them.

Two kinds of test here. The first kind checks the notation parser, because every
chart in the file is written in it and a silently mis-expanded token would put a
wrong hand in a range with no other symptom.

The second kind checks the **claims** - that the small blind chart really has no
fold branch, that opening ranges really do widen from early to late, that the
equal-blind adjustment really widens rather than merely relabelling, that a
depth-adjusted strategy is never still labelled ``solver``. Those are the things
``review.py`` will tell somebody who is trying to learn, so they need to be true.
"""

import pytest

import ranges as R
from ranges import CLASSES, Range, Strategy, lookup, parse_range


# ------------------------------------------------------------------ notation


def test_there_are_exactly_169_classes_and_1326_combos():
    assert len(CLASSES) == len(set(CLASSES)) == 169
    assert sum(R.combos_of(c) for c in CLASSES) == 1326


@pytest.mark.parametrize("text,expected", [
    ("AA", ["AA"]),
    ("AKs", ["AKs"]),
    ("TT+", ["TT", "JJ", "QQ", "KK", "AA"]),
    ("ATs+", ["ATs", "AJs", "AQs", "AKs"]),
    ("KTo+", ["KTo", "KJo", "KQo"]),
    ("99-77", ["77", "88", "99"]),
    ("AJs-A9s", ["A9s", "ATs", "AJs"]),
    ("76s-43s", ["43s", "54s", "65s", "76s"]),
    ("T9o-87o", ["87o", "98o", "T9o"]),
])
def test_tokens_expand_to_the_right_classes(text, expected):
    assert sorted(parse_range(text)) == sorted(expected)


def test_a_plus_on_a_non_pair_walks_the_kicker_not_the_high_card():
    """``A9s+`` is A9s through AKs. It is not A9s, K9s, Q9s."""
    assert all(c.startswith("A") for c in parse_range("A9s+"))
    assert "AAs" not in parse_range("A9s+")
    assert sorted(parse_range("A9s+")) == sorted(["A9s", "ATs", "AJs", "AQs", "AKs"])


def test_suit_order_does_not_matter():
    assert parse_range("KAs") == parse_range("AKs")


def test_weights_attach_to_their_token():
    r = parse_range("TT+, AKs:0.5")
    assert r.weight("AA") == 1.0
    assert r.weight("AKs") == 0.5
    assert r.weight("72o") == 0.0


def test_a_later_token_overrides_an_earlier_one():
    """This is what lets a chart write the broad stroke then the exceptions."""
    r = parse_range("A2s+, A5s:0.55")
    assert r.weight("AKs") == 1.0
    assert r.weight("A5s") == 0.55


def test_combos_and_percent():
    assert Range({"AA": 1.0}).combos() == 6
    assert Range({"AKs": 1.0}).combos() == 4
    assert Range({"AKo": 1.0}).combos() == 12
    assert parse_range("22+").combos() == 78
    assert Range({c: 1.0 for c in CLASSES}).pct() == pytest.approx(100.0)


@pytest.mark.parametrize("bad", ["AKx", "A", "AAs", "ZZ", "AKs-99", "AKs-QJo", "A9"])
def test_nonsense_notation_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_range(bad)


def test_a_span_of_equal_gap_hands_walks_down_the_ladder():
    """``AKs-KQs`` is the zero-gap run, not a typo. Same rule as ``76s-43s``."""
    assert sorted(parse_range("AKs-KQs")) == ["AKs", "KQs"]
    assert sorted(parse_range("KJs-QTs")) == ["KJs", "QTs"]


def test_a_strategy_that_overcommits_a_hand_is_rejected():
    """The likely transcription error: one hand left in two lists at full weight."""
    with pytest.raises(ValueError, match="AA"):
        Strategy("bad", "solver", raise_="AA", call="AA")


# ------------------------------------------------------- frequencies add up


@pytest.mark.parametrize("key", sorted(R._STRATEGIES, key=str))
def test_every_chart_is_a_probability_distribution(key):
    s = R._STRATEGIES[key]
    for cls in CLASSES:
        f = s.freqs(cls)
        assert all(v >= -1e-12 for v in f.values()), (key, cls)
        assert sum(f.values()) == pytest.approx(1.0), (key, cls)


# --------------------------------------------------- the small blind claim


def test_the_equal_blind_small_blind_never_folds():
    """It has already matched the big blind, so checking dominates folding."""
    s = lookup(("rfi",), "SB", equal_blinds=True)
    assert s.residual == "check"
    for cls in CLASSES:
        assert "fold" not in s.freqs(cls)
    assert s.best("72o")[0] == "check"
    assert s.best("AA")[0] == "raise"


def test_the_small_blind_chart_is_labelled_heuristic():
    """It is not a solve and must never be presented as one."""
    s = lookup(("rfi",), "SB")
    assert s.confidence == "heuristic"
    assert any("not a solve" in n for n in s.notes)


def test_the_small_blind_still_raises_a_real_range():
    """Checking everything would be as wrong as folding too much."""
    s = lookup(("rfi",), "SB")
    pct = s.actions["raise"].pct()
    assert 20.0 < pct < 45.0


# ----------------------------------------------------------- opening ranges


def test_opening_ranges_widen_from_early_to_late():
    widths = [
        lookup(("rfi",), p).actions["raise"].pct()
        for p in ("UTG", "HJ", "CO", "BTN")
    ]
    assert widths == sorted(widths)
    assert widths[0] < 25.0 < widths[-1]


def test_every_opening_range_contains_the_premiums_and_none_contain_the_trash():
    for p in ("UTG", "HJ", "CO", "BTN"):
        r = lookup(("rfi",), p).actions["raise"]
        for cls in ("AA", "KK", "QQ", "AKs", "AKo"):
            assert r.weight(cls) == 1.0, (p, cls)
        for cls in ("72o", "83o", "94o", "32o"):
            assert r.weight(cls) == 0.0, (p, cls)


def test_the_big_blind_is_never_asked_to_open():
    """Folded to the big blind is a walk, not a decision."""
    assert lookup(("rfi",), "BB") is None


# ------------------------------------------------------------ equal blinds


@pytest.mark.parametrize("pos", ["UTG", "HJ", "CO", "BTN"])
def test_equal_blinds_widen_every_opening_range(pos):
    narrow = lookup(("rfi",), pos, equal_blinds=False)
    wide = lookup(("rfi",), pos, equal_blinds=True)
    assert wide.actions["raise"].pct() > narrow.actions["raise"].pct()
    assert narrow.confidence == "solver"
    assert wide.confidence == "derived"


@pytest.mark.parametrize("opener,hero", [
    ("UTG", "CO"), ("UTG", "SB"), ("UTG", "BB"),
    ("CO", "BTN"), ("CO", "SB"), ("CO", "BB"),
    ("BTN", "SB"), ("BTN", "BB"),
])
def test_equal_blinds_widen_every_defence(opener, hero):
    narrow = lookup(("vs_rfi", opener), hero, equal_blinds=False)
    wide = lookup(("vs_rfi", opener), hero, equal_blinds=True)
    assert sum(r.pct() for r in wide.actions.values()) > \
           sum(r.pct() for r in narrow.actions.values())


def test_the_small_blind_widens_most_of_all():
    """It goes from needing 33.3% to needing 25%. Nobody else moves that far."""
    def gain(hero):
        a = lookup(("vs_rfi", "BTN"), hero, equal_blinds=False)
        b = lookup(("vs_rfi", "BTN"), hero, equal_blinds=True)
        return (sum(r.pct() for r in b.actions.values())
                - sum(r.pct() for r in a.actions.values()))
    assert gain("SB") > gain("BB")


def test_the_small_blind_open_node_is_not_widened_twice():
    """That chart was written for the equal blinds already."""
    a = lookup(("vs_rfi", "SB"), "BB", equal_blinds=False)
    b = lookup(("vs_rfi", "SB"), "BB", equal_blinds=True)
    assert a.actions["call"] == b.actions["call"]


# ------------------------------------------------------------------- depth


def test_below_the_first_threshold_nothing_is_adjusted():
    s = lookup(("vs_rfi", "BTN"), "BB", depth_bb=100)
    assert not any("Adjusted for" in n for n in s.notes)


def test_a_depth_adjusted_chart_is_never_still_labelled_solver():
    for depth in (150, 200, 400):
        s = lookup(("vs_rfi", "BTN"), "BB", depth_bb=depth, equal_blinds=False)
        assert s.confidence == "derived"
        assert any("Adjusted for" in n for n in s.notes)


def test_depth_polarises_the_three_bet_and_widens_the_call():
    shallow = lookup(("vs_rfi", "CO"), "BTN", depth_bb=100, equal_blinds=False)
    deep = lookup(("vs_rfi", "CO"), "BTN", depth_bb=200, equal_blinds=False)
    assert deep.actions["3bet"].weight("AQo") < shallow.actions["3bet"].weight("AQo")
    assert deep.actions["3bet"].weight("A5s") >= shallow.actions["3bet"].weight("A5s")
    assert deep.actions["call"].pct() > shallow.actions["call"].pct()


def test_depth_never_breaks_the_distribution():
    for depth in (100, 150, 200, 300, 600):
        s = lookup(("vs_rfi", "BTN"), "BB", depth_bb=depth)
        for cls in CLASSES:
            assert sum(s.freqs(cls).values()) == pytest.approx(1.0), (depth, cls)


# ---------------------------------------------------------- table size


def test_five_handed_uses_the_same_charts_as_six_handed():
    """A chart depends on how many act behind you, not on the table size.

    Five-handed HJ is first to act with four behind. Six-handed HJ has UTG
    already folded and also has four behind. Same node.
    """
    for pos in ("HJ", "CO", "BTN"):
        five = lookup(("rfi",), pos, seats=5)
        six = lookup(("rfi",), pos, seats=6)
        assert five.actions["raise"] == six.actions["raise"]


def test_asking_for_a_seat_that_does_not_exist_is_an_error():
    with pytest.raises(ValueError):
        lookup(("rfi",), "UTG", seats=5)


# ----------------------------------------------------- declining to answer


def test_an_uncharted_node_returns_none_rather_than_the_nearest_chart():
    """Guessing would be worse than declining. review.py handles None."""
    assert lookup(("vs_rfi", "BB"), "SB") is None


def test_an_unknown_node_kind_is_an_error_not_a_none():
    with pytest.raises(ValueError):
        lookup(("squeeze", "CO"), "BB")


# --------------------------------------------------------- sanity of play


@pytest.mark.parametrize("key", sorted(R._STRATEGIES, key=str))
def test_no_chart_ever_folds_aces(key):
    s = R._STRATEGIES[key]
    assert s.freqs("AA").get("fold", 0.0) == 0.0, key


def test_facing_a_three_bet_the_widest_opener_defends_widest():
    widths = [
        sum(r.pct() for r in R._STRATEGIES[("vs_3bet", b)].actions.values())
        for b in ("EARLY", "CO", "BTN")
    ]
    assert widths == sorted(widths)


def test_kings_and_aces_are_the_backbone_of_every_four_bet_range():
    for b in ("EARLY", "CO", "BTN", "SB"):
        four = R._STRATEGIES[("vs_3bet", b)].actions["4bet"]
        assert four.weight("AA") == 1.0
        assert four.weight("KK") == 1.0


def test_depth_adjustment_never_improves_a_confidence_label():
    """A guess moved for stack depth is still a guess.

    ``apply_depth`` used to stamp everything it touched ``derived``, which for
    the equal-blind small blind - the only node here with no solve behind it -
    turned "a considered starting point" into "adjusted from a solved
    equilibrium" the moment the hero sat deeper than 150bb. The label is the
    one place a learner is told how much to trust a line, so it may only ever
    get weaker.
    """
    for depth in (200.0, 400.0):
        sb = R.lookup(("rfi",), "SB", seats=6, depth_bb=depth)
        assert sb.confidence == "heuristic"
        solved = R.lookup(("rfi",), "CO", seats=6, depth_bb=depth)
        assert solved.confidence == "derived"


def test_the_reason_for_every_depth_adjustment_is_printed_with_it():
    shallow = R.lookup(("vs_rfi", "CO"), "BTN", seats=6, depth_bb=100.0)
    deep = R.lookup(("vs_rfi", "CO"), "BTN", seats=6, depth_bb=200.0)
    assert len(deep.notes) > len(shallow.notes)
    assert any("150bb" in n or "deep" in n for n in deep.notes)
