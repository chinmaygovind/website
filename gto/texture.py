"""Reading a board: what you have, what you might get, and what it looks like.

Two customers with different needs, and one vocabulary between them.

``bots.py`` needs a *decision* input - some numbers that say how good this is
and how good it might become - and it needs them in milliseconds, because five
bots make a decision every street.

``review.py`` needs *words*. "You bet 60% of the pot into three players on a
monotone board holding second pair and no diamond" is a sentence somebody can
learn from; "EV -1.8bb" on its own is not. So the same reading produces both,
and they can never disagree about what you had.

**Nothing here is used to score you.** Bot decisions come from this file; your
score comes from ``ranges.py``, ``equity.py`` and the solver. If the two were
wired together the trainer would be grading you against its own opinion, and a
tool that marks your homework with the same pen it wrote it with is worth
nothing. The only thing this file contributes to a review is the description.
"""

import bisect
import itertools

from cards import DECK, RANKS, rank_of, suit_of
from evaluator import category_of, evaluate

#: Nine cards make a flush from four; eight and four are the two straight draws.
FLUSH_OUTS = 9
OESD_OUTS = 8
GUTSHOT_OUTS = 4


def _rank_mask(cards):
    mask = 0
    for c in cards:
        mask |= 1 << rank_of(c)
    return mask


def _suit_counts(cards):
    counts = [0, 0, 0, 0]
    for c in cards:
        counts[suit_of(c)] += 1
    return counts


# ------------------------------------------------------------ how strong now


#: Every opponent holding scored against one board, twice over: sorted, for the
#: rank lookup, and keyed by the pair, for the removal. Five bots reading the
#: same flop share both, which is the whole reason a hand is milliseconds rather
#: than tens of them.
#:
#: **The keyed copy is what makes a per-combination caller affordable.** Removing
#: the holdings the reader blocks used to walk all 1,176 pairs to find the 89 of
#: them that matter, and re-evaluate those - 354us a call, which is nothing for
#: five bots a street and is thirty seconds when ``rollout.py`` asks it of every
#: combination in a range. Looked up instead of rescanned it is about 9us.
#:
#: The limit is 64 rather than 512 because each entry is now two structures
#: rather than one. Nothing here reads more than a handful of boards at a time -
#: five bots and a review all look at the same one - so the smaller cache costs
#: nothing and the dictionary is what would otherwise grow to tens of megabytes
#: in a worker that never restarts.
_BOARD_SCORES = {}
_BOARD_CACHE_LIMIT = 64


def _pair_key(a, b):
    """One integer for an unordered pair of cards, which are 0-51."""
    return a * 52 + b if a < b else b * 52 + a


def _board_scores(board):
    """``(sorted scores, {pair key: score})`` for every holding on this board."""
    key = tuple(sorted(board))
    hit = _BOARD_SCORES.get(key)
    if hit is None:
        if len(_BOARD_SCORES) >= _BOARD_CACHE_LIMIT:
            _BOARD_SCORES.clear()
        rest = [c for c in DECK if c not in set(board)]
        by_pair = {}
        for a, b in itertools.combinations(rest, 2):
            by_pair[_pair_key(a, b)] = evaluate([a, b] + list(board))
        hit = (sorted(by_pair.values()), by_pair)
        _BOARD_SCORES[key] = hit
    return hit


def showdown_strength(hole, board):
    """Fraction of all other two-card holdings this hand currently beats.

    Ties count a half, so a hand that plays the board scores near 0.5 rather
    than near 1 - which is the number a bot should act on, and the number the
    naive "count wins" version gets badly wrong on a board that plays.

    **Exact, and shared.** Every holding is scored against the board once and
    cached, because five bots reading the same flop were otherwise doing the
    same eleven hundred evaluations five times over. The cached list includes
    the combinations that use the reader's own cards, so those are found and
    removed - about ninety evaluations rather than eleven hundred, and the same
    answer as counting from scratch, which ``test_texture.py`` checks directly.
    """
    board = list(board)
    scores, by_pair = _board_scores(board)
    mine = evaluate(list(hole) + board)

    below = bisect.bisect_left(scores, mine)
    equal = bisect.bisect_right(scores, mine) - below
    total = len(scores)

    # Drop the combinations that are not available to an opponent, because this
    # hand is holding one of the cards. Those are enumerated directly - each hole
    # card paired with every other live card - rather than found by filtering all
    # 1,176 pairs, and their scores are read out of the cache rather than
    # recomputed. Same answer, and `test_texture.py` counts it from scratch.
    known = set(board)
    h0, h1 = hole
    blocked = [_pair_key(h0, c) for c in DECK if c not in known and c != h0]
    blocked += [_pair_key(h1, c) for c in DECK
                if c not in known and c != h1 and c != h0]
    for pair in blocked:
        theirs = by_pair[pair]
        total -= 1
        if theirs < mine:
            below -= 1
        elif theirs == mine:
            equal -= 1

    return (below + equal / 2.0) / total if total else 0.5


# --------------------------------------------------------------- what draws


def flush_draw(hole, board):
    """0 nothing, 1 backdoor, 2 a real draw, 3 already made.

    Counted in the suit the *hole cards* contribute to. Four to a flush entirely
    on the board is not a draw, it is a card everybody has, and calling it a draw
    is how a bot ends up semi-bluffing with the sixth-best hand.
    """
    board_counts = _suit_counts(board)
    best = 0
    for suit in range(4):
        mine = sum(1 for c in hole if suit_of(c) == suit)
        if not mine:
            continue
        total = mine + board_counts[suit]
        if total >= 5:
            best = max(best, 3)
        elif total == 4:
            best = max(best, 2)
        elif total == 3 and len(board) == 3:
            # Backdoor only on the flop. Three to a flush on the turn cannot get
            # there with one card, and calling it a draw is how a review ends up
            # telling somebody they had "a backdoor flush draw" on the river.
            best = max(best, 1)
    return best


def straight_outs(hole, board):
    """How many distinct ranks would complete a straight, using at least one hole card.

    Counted by asking, for every rank not yet present, whether adding it makes a
    straight that the hole cards are part of. That is slower than pattern
    matching and it is right about the cases pattern matching gets wrong - a
    board that already has a straight on it, a hand that only appears to be open
    ended because the board supplies both ends.
    """
    cards = list(hole) + list(board)
    if len(cards) < 4:
        return 0
    have = _straight_in(cards)

    outs = 0
    present = _rank_mask(cards)
    for r in range(13):
        if present & (1 << r):
            continue
        probe = cards + [r * 4]  # suit is irrelevant to a straight
        made = _straight_in(probe)
        if made is None or made == have:
            continue
        # If the board plus that card makes the same straight, our hole cards
        # contributed nothing and it is not our out - everybody has it. An
        # earlier version also required the board to *already* hold a straight,
        # which is a condition that almost never fires, so a five-card board
        # with a straight on it still counted outs to a bigger one nobody could
        # miss.
        if _straight_in(list(board) + [r * 4]) == made:
            continue
        outs += 4
    return outs


def _straight_in(cards):
    mask = _rank_mask(cards)
    run = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if run:
        return (run.bit_length() - 1) + 4
    wheel = (1 << 12) | (1 << 3) | (1 << 2) | (1 << 1) | (1 << 0)
    return 3 if mask & wheel == wheel else None


def outs(hole, board):
    """Total clean outs to a materially better hand.

    Flush and straight outs overlap - a card can do both - so the straight count
    is reduced by the ones that are also flush cards rather than added to it.
    Double counting here is the difference between a semi-bluff that is correct
    and one that is not.
    """
    if len(board) >= 5:
        return 0
    total = 0
    fd = flush_draw(hole, board)
    if fd == 2:
        total += FLUSH_OUTS
    sd = straight_outs(hole, board)
    if sd and fd == 2:
        sd = int(sd * 0.75)  # roughly one in four straight cards is also a flush card
    total += sd
    return total


# ------------------------------------------------------------ what you made


def pair_read(hole, board):
    """Which pair this is, in the words a player would use.

    Returns ``(label, kicker_rank_or_None)``. ``label`` is one of ``overpair``,
    ``top pair``, ``second pair``, ``third pair``, ``weak pair``, ``pocket pair``
    (below top board card but not matching anything), or ``None``.
    """
    if not board:
        return (None, None)
    hole_ranks = sorted((rank_of(c) for c in hole), reverse=True)
    board_ranks = sorted({rank_of(c) for c in board}, reverse=True)

    if hole_ranks[0] == hole_ranks[1]:
        if hole_ranks[0] > board_ranks[0]:
            return ("overpair", None)
        if hole_ranks[0] in board_ranks:
            return ("set", None)
        return ("pocket pair", None)

    for r in hole_ranks:
        if r in board_ranks:
            place = board_ranks.index(r)
            kicker = next(k for k in hole_ranks if k != r)
            label = {0: "top pair", 1: "second pair", 2: "third pair"}.get(
                place, "weak pair")
            return (label, kicker)
    return (None, None)


def kicker_quality(kicker):
    """``good``/``decent``/``weak`` for a kicker rank index."""
    if kicker is None:
        return None
    if kicker >= 11:
        return "good"
    if kicker >= 8:
        return "decent"
    return "weak"


# ----------------------------------------------------------- what the board is


def board_texture(board):
    """How dangerous the board is, in the terms that change how it plays."""
    if not board:
        return {"paired": False, "monotone": False, "two_tone": False,
                "connected": 0, "high": None, "wetness": 0.0}
    ranks = [rank_of(c) for c in board]
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    suits = _suit_counts(board)
    distinct = sorted(set(ranks), reverse=True)

    connected = 0
    for a, b in itertools.combinations(distinct, 2):
        if a - b <= 4:
            connected += 1

    # One number decides both flush facts, so they cannot contradict each other.
    # An earlier version computed `monotone` two different ways in the same
    # function and let `two_tone` read the wrong one.
    flush_cards = max(suits)
    paired = max(counts.values()) >= 2

    wetness = min(1.0, (
        0.35 * (flush_cards >= 3)
        + 0.20 * (flush_cards == 2)
        + 0.12 * connected
        + 0.15 * (distinct[0] >= 10)
    ))
    return {
        "paired": paired,
        "flush_cards": flush_cards,
        "monotone": flush_cards >= 3,
        "two_tone": flush_cards == 2,
        "connected": connected,
        "high": RANKS[distinct[0]],
        "wetness": round(wetness, 3),
    }


# ----------------------------------------------------------------- the whole


def read(hole, board):
    """Everything at once: the numbers for the bot, the words for the review."""
    made = evaluate(list(hole) + list(board)) if len(board) >= 3 else None
    label, kicker = pair_read(hole, board)
    fd = flush_draw(hole, board)
    o = outs(hole, board) if len(board) in (3, 4) else 0
    return {
        "category": category_of(made) if made is not None else None,
        "pair": label,
        "kicker": kicker_quality(kicker),
        "flush_draw": fd,
        "straight_outs": straight_outs(hole, board) if 0 < len(board) < 5 else 0,
        "outs": o,
        "strength": showdown_strength(hole, board) if len(board) >= 3 else None,
        "texture": board_texture(board),
    }


#: Made hands that outrank a pairing, by ``evaluator`` category index. Below a
#: straight, a hand is some arrangement of pairs and ``pair_read`` says which;
#: at a straight and above, the category *is* the description and the pair
#: underneath it is not worth a word - "a set" is the wrong thing to call kings
#: full.
_MADE_ABOVE_PAIRS = {
    4: "a straight",
    5: "a flush",
    6: "a full house",
    7: "four of a kind",
    8: "a straight flush",
}


def describe_hand(hole, board):
    """The phrase a review line uses: ``"top pair, weak kicker, flush draw"``.

    **A made hand is named before any draw it also happens to have.** This used
    to be built from the pair, the suits and the outs alone, and a straight is
    none of those: a wheel on A-2-4 came out as "a gutshot", and Broadway on
    Q-J-T as "a backdoor flush draw". Both are true and both are the wrong
    sentence - the hand was made, and a trainer that tells you you are drawing
    when you are already there is worse than one that says nothing.
    """
    r = read(hole, board)
    bits = []
    made = _MADE_ABOVE_PAIRS.get(r["category"])
    if made:
        bits.append(made)
    elif r["pair"] == "set":
        bits.append("a set")
    elif r["pair"]:
        bits.append(r["pair"] + (f", {r['kicker']} kicker" if r["kicker"] else ""))

    if not made and r["flush_draw"] == 3:
        bits.append("a flush")
    elif len(board) < 5 and r["flush_draw"] == 2 and r["category"] != 5:
        # A real redraw is worth saying over a made straight; a backdoor one is
        # not, and printing it next to "a straight" reads as a tool that has not
        # noticed what you have.
        bits.append("a flush draw")
    elif not made and len(board) < 5 and r["flush_draw"] == 1:
        bits.append("a backdoor flush draw")
    # A draw to the hand you already have is not a draw. Straight outs are
    # counted from the board and do not know the hand is already made.
    if not made:
        if r["straight_outs"] >= OESD_OUTS:
            bits.append("an open-ended straight draw")
        elif r["straight_outs"] >= GUTSHOT_OUTS:
            bits.append("a gutshot")

    # Two overcards is worth saying when it is all you have: it is the
    # difference between a bluff with backdoors and a bluff with nothing, and it
    # is the hand people misplay most on a flop they missed.
    if not bits and board:
        top = max(rank_of(c) for c in board)
        over = sum(1 for c in hole if rank_of(c) > top)
        if over == 2:
            return "no pair, two overcards"
        if over == 1:
            return "no pair, one overcard"
    return ", ".join(bits) if bits else "no pair and no draw"
