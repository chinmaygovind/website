"""Egyptian Rat Screw - pure game engine.

No Flask, no I/O: every function takes a plain ``state`` dict and mutates it in
place, returning a list of event dicts describing what happened (used by the app
layer for broadcasts / animations). Keeping the rules here and side-effect-free
is what lets ``tests/test_engine.py`` prove the game makes no mistakes.

Card representation: ``{"rank": int, "suit": str}`` where rank is 2..10 for the
number cards, 11=J, 12=Q, 13=K, 14=A. A hand is a list of face-down cards where
index 0 is the TOP (flipped next) and the end of the list is the BOTTOM (where a
won pile is placed). The center ``pile`` is a list where index 0 is the bottom
card and the last element is the most-recently-flipped top card.

Rules implemented (see the linked ruleset):
  * Royalty tribute: playing J/Q/K/A obliges the next player to flip up to
    1/2/3/4 cards; flip a royalty and the tribute passes on with the new count,
    otherwise the player who laid the last royalty wins the pile.
  * Slaps (first valid slap wins the whole pile): double (XX), sandwich (X_X),
    top-matches-bottom, plus the optional add-to-ten and King+Queen.
  * False slap burns cards to the bottom of the pile and locks the slapper out
    of the current pile until the next card is flipped.
  * Running out of cards does not eliminate you immediately - you may still slap
    back in; you are out when the next pile is won by someone else. Last player
    holding cards wins.
"""

import random

SUITS = ["♠", "♥", "♦", "♣"]  # ♠ ♥ ♦ ♣
RANKS = list(range(2, 15))  # 2..10, J=11, Q=12, K=13, A=14

# Royalty tribute counts: how many cards the next player owes.
ROYALTY = {11: 1, 12: 2, 13: 3, 14: 4}  # J, Q, K, A

# Optional slap rules that are enabled (core double/sandwich/top-bottom always on).
DEFAULT_RULES = ("ten", "kingqueen")

# Cards burned to the bottom of the pile on a false slap.
FALSE_SLAP_BURN = 1

# Seconds a failed tribute waits before the beneficiary collects, so a valid slap
# on the final card can still beat the collection. Used by the app's grace timer.
TRIBUTE_GRACE_SECONDS = 1.2

RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}


def rank_label(rank):
    return RANK_LABELS.get(rank, str(rank))


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def make_deck():
    return [{"rank": r, "suit": s} for s in SUITS for r in RANKS]


def _extra_receivers(player_ids, extra_priority, remainder):
    """The ``remainder`` players who each get one leftover card. Follows
    ``extra_priority`` (filtered to valid ids, de-duped) then deal order as a
    fallback, so passing lowest-ELO-first steers the extras to the underdogs."""
    order = []
    for pid in (extra_priority or []):
        if pid in player_ids and pid not in order:
            order.append(pid)
    for pid in player_ids:
        if pid not in order:
            order.append(pid)
    return order[:remainder]


def new_deal(player_ids, seed=None, rules=DEFAULT_RULES, extra_priority=None):
    """Deal a shuffled 52-card deck as evenly as possible into face-down stacks.

    The even part is dealt round-robin; the few leftover cards (52 rarely divides
    evenly) go out one each. By default that follows deal order, but a caller can
    pass ``extra_priority`` to hand the extras to specific players first - the app
    passes lowest-ELO-first so the weaker players start a touch bigger."""
    player_ids = list(player_ids)
    rng = random.Random(seed)
    deck = make_deck()
    rng.shuffle(deck)
    n = len(player_ids)
    hands = {pid: [] for pid in player_ids}
    base = len(deck) // n
    for i in range(base * n):
        hands[player_ids[i % n]].append(deck[i])
    remainder = len(deck) - base * n
    for pid, card in zip(_extra_receivers(player_ids, extra_priority, remainder),
                         deck[base * n:]):
        hands[pid].append(card)
    return {
        "players": player_ids,
        "hands": hands,
        "pile": [],
        "current": player_ids[0],
        "challenge": None,        # {"chances_left", "beneficiary", "rank"} or None
        "eliminated": [],
        "pending_win": None,      # {"pid", "reason"} awaiting the grace window
        "last_flip": None,        # {"pid", "card", "seq"} of the most recent flip
        "last_burn": None,        # {"pid", "card", "seq"} of the most recent false-slap burn
        "last_win": None,         # {"pid", "count", "seq"} of the most recent pile win
        "slap_locked": [],        # players who false-slapped the current pile
        "phase": "playing",       # "playing" | "ended"
        "winner": None,
        "rules": list(rules),
        "turns": 0,               # total cards flipped so far ("lasted X turns")
        "standings": [],          # finish order: [{pid, place, turns_lasted}]
        "log": [],                # app-owned slap/event feed (engine never reads it)
        "seq": 0,                 # bumps on every mutation (client de-dupe/animation)
    }


# ---------------------------------------------------------------------------
# Turn helpers
# ---------------------------------------------------------------------------

def _active(state, pid):
    """A player who can take a turn: not eliminated and holding cards."""
    return pid not in state["eliminated"] and bool(state["hands"][pid])


def _next_active_after(state, pid):
    order = state["players"]
    n = len(order)
    start = order.index(pid) if pid in order else -1
    for i in range(1, n + 1):
        cand = order[(start + i) % n]
        if _active(state, cand):
            return cand
    return None


def _advance_turn(state):
    nxt = _next_active_after(state, state["current"])
    if nxt is not None:
        state["current"] = nxt
    # if None, the sole card-holder stays current; the pile in play resolves it.


def _check_win(state):
    if state["phase"] != "playing":
        return
    alive = [p for p in state["players"] if p not in state["eliminated"]]
    if len(alive) <= 1:
        state["phase"] = "ended"
        winner = alive[0] if alive else None
        state["winner"] = winner
        if winner is not None and not any(s["pid"] == winner for s in state["standings"]):
            place = len(state["players"]) - len(state["standings"])
            state["standings"].append({"pid": winner, "place": place,
                                        "turns_lasted": state["turns"]})
        state["seq"] += 1


# ---------------------------------------------------------------------------
# Core actions
# ---------------------------------------------------------------------------

def flip(state, pid):
    """The current player flips their top card onto the pile."""
    events = []
    if state["phase"] != "playing":
        return events
    if pid != state["current"]:
        return events          # not your turn
    if state["pending_win"]:
        return events          # waiting on the grace window; no new cards
    hand = state["hands"][pid]
    if not hand:
        _advance_turn(state)   # defensive; current should always have cards
        return events

    card = hand.pop(0)
    state["pile"].append(card)
    state["slap_locked"] = []  # a new card clears false-slap lockouts
    state["turns"] += 1
    state["seq"] += 1
    state["last_flip"] = {"pid": pid, "card": card, "seq": state["seq"]}
    events.append({"type": "flip", "pid": pid, "card": card})

    v = ROYALTY.get(card["rank"], 0)
    ch = state["challenge"]

    if ch is not None:
        if v > 0:
            # A royalty during tribute: the challenge passes to the next player.
            state["challenge"] = {"chances_left": v, "beneficiary": pid, "rank": card["rank"]}
            _advance_turn(state)
        else:
            ch["chances_left"] -= 1
            if ch["chances_left"] <= 0 or not hand:
                # Tribute failed (ran out of chances, or out of cards mid-tribute):
                # the beneficiary wins, pending a grace window for a last slap.
                state["pending_win"] = {"pid": ch["beneficiary"], "reason": "tribute",
                                        "rank": ch.get("rank")}
                events.append({"type": "tribute_fail", "pid": ch["beneficiary"]})
            # else: the same player keeps paying - current stays put.
    else:
        if v > 0:
            state["challenge"] = {"chances_left": v, "beneficiary": pid, "rank": card["rank"]}
        _advance_turn(state)

    return events


def slap_reasons(pile, rules):
    """Return the list of slap rules currently satisfied by ``pile`` (top = last)."""
    reasons = []
    n = len(pile)
    if n < 2:
        return reasons
    top = pile[-1]["rank"]
    second = pile[-2]["rank"]
    bottom = pile[0]["rank"]

    if top == second:
        reasons.append("double")
    if n >= 3 and top == pile[-3]["rank"]:
        reasons.append("sandwich")
    if top == bottom:
        reasons.append("top_bottom")
    if "ten" in rules:
        a, b = _num_value(top), _num_value(second)
        if a is not None and b is not None and a + b == 10:
            reasons.append("ten")
    if "kingqueen" in rules:
        if {top, second} == {12, 13}:
            reasons.append("kingqueen")
    return reasons


def _num_value(rank):
    """Value for the add-to-ten rule: A=1, number cards face value, J/Q/K don't count."""
    if rank == 14:
        return 1
    if 2 <= rank <= 10:
        return rank
    return None


def slap(state, pid, rules=None):
    """A player slaps the pile. First valid slap under the caller's lock wins."""
    events = []
    if state["phase"] != "playing":
        return events
    if pid in state["eliminated"]:
        return events
    if not state["pile"]:
        return events                       # nothing to slap; no penalty
    if pid in state["slap_locked"]:
        return events                       # already false-slapped this pile
    rules = state["rules"] if rules is None else rules

    reasons = slap_reasons(state["pile"], rules)
    if reasons:
        events.append({"type": "slap_win", "pid": pid, "reasons": reasons})
        events += award_pile(state, pid, via="slap")
    else:
        # False slap: burn cards from the top of the slapper's stack to the
        # bottom of the pile, and lock them out until the next card is flipped.
        was_empty = not state["hands"][pid]      # already out of cards = on their last life
        burn = min(FALSE_SLAP_BURN, len(state["hands"][pid]))
        burned = [state["hands"][pid].pop(0) for _ in range(burn)]
        if burned:
            state["pile"] = burned + state["pile"]
        state["slap_locked"].append(pid)
        state["seq"] += 1
        burned_card = burned[0] if burned else None
        state["last_burn"] = {"pid": pid, "card": burned_card, "seq": state["seq"]}
        events.append({"type": "false_slap", "pid": pid, "burned": burn, "card": burned_card})
        if was_empty:                            # wrong slap on your last life knocks you out
            ev = _eliminate(state, pid)
            if ev:
                events.append(ev)
            _check_win(state)
    return events


def _eliminate(state, pid):
    """Knock ``pid`` out, recording their finishing place. Returns the event or None."""
    if pid in state["eliminated"]:
        return None
    state["eliminated"].append(pid)
    place = len(state["players"]) - len(state["standings"])
    state["standings"].append({"pid": pid, "place": place, "turns_lasted": state["turns"]})
    return {"type": "eliminated", "pid": pid, "place": place, "turns_lasted": state["turns"]}


def award_pile(state, pid, via=None, rank=None):
    """Give the whole pile to ``pid`` (placed at the bottom of their stack).

    ``via`` is "slap" or "tribute"; ``rank`` is the royalty rank when a tribute
    was failed (so the UI can say "takes the pile on a King")."""
    events = []
    pile = state["pile"]
    count = len(pile)
    if count:
        state["hands"][pid].extend(pile)    # to the bottom of the stack
    state["pile"] = []
    state["challenge"] = None
    state["pending_win"] = None
    state["slap_locked"] = []
    state["seq"] += 1
    state["last_win"] = {"pid": pid, "count": count, "seq": state["seq"]}
    events.append({"type": "win_pile", "pid": pid, "count": count, "via": via, "rank": rank})

    # Anyone else who is now out of cards used up their one life to slap back in.
    for other in state["players"]:
        if other != pid and other not in state["eliminated"] and not state["hands"][other]:
            ev = _eliminate(state, other)
            if ev:
                events.append(ev)

    # The winner leads the next round.
    if state["hands"][pid]:
        state["current"] = pid
    else:
        nxt = _next_active_after(state, pid)
        if nxt is not None:
            state["current"] = nxt

    _check_win(state)
    return events


def resign(state, pid):
    """A player leaves an in-progress game: their cards leave play and they are out."""
    events = []
    if state["phase"] != "playing" or pid not in state["players"] or pid in state["eliminated"]:
        return events
    state["hands"][pid] = []
    if state.get("challenge") and state["challenge"].get("beneficiary") == pid:
        state["challenge"] = None
    if state.get("pending_win") and state["pending_win"].get("pid") == pid:
        state["pending_win"] = None
    ev = _eliminate(state, pid)
    if ev:
        ev["left"] = True
        events.append(ev)
    if state["current"] == pid:
        _advance_turn(state)
    _check_win(state)
    return events


def resolve_pending(state):
    """Resolve a failed-tribute collection once the grace window elapses."""
    pw = state.get("pending_win")
    if not pw:
        return []
    state["pending_win"] = None
    return award_pile(state, pw["pid"], via="tribute", rank=pw.get("rank"))


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def _royalty_counts(hand):
    """How many J/Q/K/A a stack holds, for the per-seat royalty tally."""
    c = {"J": 0, "Q": 0, "K": 0, "A": 0}
    for card in hand:
        lbl = RANK_LABELS.get(card["rank"])
        if lbl in c:
            c[lbl] += 1
    return c


def public_view(state):
    """The state broadcast to clients - hand contents stay secret (face-down),
    except the J/Q/K/A tally per seat, which is surfaced on purpose."""
    ch = state["challenge"]
    return {
        "players": state["players"],
        "counts": {pid: len(state["hands"][pid]) for pid in state["players"]},
        "royalty": {pid: _royalty_counts(state["hands"][pid]) for pid in state["players"]},
        "slap_locked": state.get("slap_locked", []),
        "pile": state["pile"],
        "pile_count": len(state["pile"]),
        "current": state["current"],
        "challenge": None if not ch else {
            "chances_left": ch["chances_left"],
            "beneficiary": ch["beneficiary"],
            "rank": ch.get("rank"),
            "label": rank_label(ch.get("rank")) if ch.get("rank") else None,
        },
        "eliminated": state["eliminated"],
        "pending_win": state.get("pending_win"),
        "last_flip": state.get("last_flip"),
        "last_burn": state.get("last_burn"),
        "last_win": state.get("last_win"),
        "phase": state["phase"],
        "winner": state["winner"],
        "rules": state["rules"],
        "turns": state["turns"],
        "standings": state["standings"],
        "log": state.get("log", [])[-40:],
        "seq": state["seq"],
    }
