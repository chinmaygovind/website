"""Card encoding: the one primitive everything else indexes into."""

import pytest

from cards import (
    DECK, RANKS, SUITS, card_str, cards_str, hole_class, make, parse,
    parse_card, rank_of, suit_of,
)


def test_deck_is_52_distinct_cards():
    assert len(DECK) == 52
    assert len(set(DECK)) == 52
    assert sorted(DECK) == list(range(52))


def test_rank_and_suit_round_trip():
    for c in DECK:
        assert make(rank_of(c), suit_of(c)) == c


def test_every_rank_suit_pair_appears_exactly_once():
    seen = {(rank_of(c), suit_of(c)) for c in DECK}
    assert len(seen) == 52
    assert seen == {(r, s) for r in range(13) for s in range(4)}


def test_string_round_trip():
    for c in DECK:
        assert parse_card(card_str(c)) == c


def test_parse_reads_a_run_of_cards():
    assert parse("AsKdQh") == [parse_card("As"), parse_card("Kd"), parse_card("Qh")]
    assert cards_str(parse("2c7d")) == "2c 7d"


@pytest.mark.parametrize("text,expected", [
    ("AsKs", "AKs"),
    ("AsKd", "AKo"),
    ("KsAs", "AKs"),
    ("7c7d", "77"),
    ("2s3s", "32s"),
])
def test_hole_class(text, expected):
    assert hole_class(parse(text)) == expected


def test_hole_class_covers_exactly_169_classes():
    """Every two-card combination falls into one of the 169, and all 169 occur."""
    seen = {}
    for i, a in enumerate(DECK):
        for b in DECK[i + 1:]:
            seen.setdefault(hole_class([a, b]), 0)
            seen[hole_class([a, b])] += 1
    assert len(seen) == 169
    assert sum(seen.values()) == 1326
    assert sorted(set(seen.values())) == [4, 6, 12]


def test_rank_and_suit_alphabets():
    assert RANKS == "23456789TJQKA"
    assert SUITS == "cdhs"
