"""Cards, as integers.

A card is ``rank * 4 + suit``: rank 0-12 for deuce through ace, suit 0-3 for
clubs, diamonds, hearts, spades. So ``rank = card >> 2`` and ``suit = card & 3``,
and the natural integer order sorts by rank then suit - which is what makes the
evaluator's bit work in ``evaluator.py`` cheap.

Nothing here knows about poker beyond what a card *is*. Hand strength lives in
``evaluator.py``, ranges in ``ranges.py``, and the rules in ``engine.py``.

The text form is the universal one - ``As``, ``Td``, ``2c`` - because it is what
every solver output, every hand history and every test fixture in this directory
is written in, and a format nobody has to translate is a format nobody gets
wrong.
"""

RANKS = "23456789TJQKA"
SUITS = "cdhs"

RANK_INDEX = {ch: i for i, ch in enumerate(RANKS)}
SUIT_INDEX = {ch: i for i, ch in enumerate(SUITS)}

DECK = tuple(range(52))

#: Human names, indexed by the category ``evaluator.evaluate`` returns.
CATEGORY_NAMES = (
    "high card",
    "a pair",
    "two pair",
    "three of a kind",
    "a straight",
    "a flush",
    "a full house",
    "four of a kind",
    "a straight flush",
)


def rank_of(card):
    """0-12, deuce through ace."""
    return card >> 2


def suit_of(card):
    """0-3, clubs through spades."""
    return card & 3


def make(rank, suit):
    """Build a card from a rank index and a suit index."""
    return rank * 4 + suit


def parse_card(text):
    """``"As"`` -> the integer for the ace of spades.

    Rank is case-insensitive because ``AS`` and ``as`` both turn up in pasted
    hand histories; suit is *not*, since an uppercase ``S`` is unambiguous but
    the rank ``T`` and a lowercase ``t`` are the same character to a reader and
    a different one to a dict.
    """
    text = text.strip()
    if len(text) != 2:
        raise ValueError(f"not a card: {text!r}")
    rank, suit = text[0].upper(), text[1].lower()
    if rank not in RANK_INDEX or suit not in SUIT_INDEX:
        raise ValueError(f"not a card: {text!r}")
    return make(RANK_INDEX[rank], SUIT_INDEX[suit])


def parse(text):
    """``"AsKd"`` or ``"As Kd"`` -> a list of card integers.

    Accepts whitespace and commas between cards so a board can be written the
    way it reads out loud.
    """
    cleaned = text.replace(",", " ").split()
    if len(cleaned) == 1 and len(cleaned[0]) > 2:
        blob = cleaned[0]
        cleaned = [blob[i:i + 2] for i in range(0, len(blob), 2)]
    return [parse_card(c) for c in cleaned]


def card_str(card):
    """The integer for the ace of spades -> ``"As"``."""
    return RANKS[rank_of(card)] + SUITS[suit_of(card)]


def cards_str(cards):
    """A list of cards -> ``"As Kd 7h"``."""
    return " ".join(card_str(c) for c in cards)


def hole_class(cards):
    """The 169-class name for two hole cards: ``AKs``, ``AKo``, ``77``.

    This is the unit preflop ranges are written in, so it is the key every
    chart in ``ranges.py`` is looked up by.
    """
    if len(cards) != 2:
        raise ValueError("a hole class needs exactly two cards")
    a, b = cards
    ra, rb = rank_of(a), rank_of(b)
    if ra < rb:
        ra, rb = rb, ra
    hi, lo = RANKS[ra], RANKS[rb]
    if ra == rb:
        return hi + lo
    return hi + lo + ("s" if suit_of(a) == suit_of(b) else "o")
