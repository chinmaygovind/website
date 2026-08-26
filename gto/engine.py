"""No-limit hold'em, as a pure state machine.

One ``Hand`` is one hand of poker. It knows the rules and nothing else - no
Flask, no database, no clock, no opinion about who should do what. Bots live in
``bots.py``, scoring in ``review.py``, and both drive this the same way the
browser does, which is what makes a bot's decision and yours comparable at all.

**Money is integer cents everywhere.** $0.25 is ``25``. A pot split three ways
is where floating point stops being an abstraction and starts being a bug you
find six weeks later in a hand history, and this game's whole purpose is to
report small edges accurately.

**Blinds are not assumed to be unequal.** Chinmay's game is $0.25/$0.25, where
the small blind has already matched the big blind before the cards are out - so
the small blind may *check* its option preflop, which is illegal in almost every
other game and is a legal, common line here. Nothing in this file compares
``sb`` against ``bb``; the betting round asks only whether a player has matched
``current_bet``, which gets that case right without a special case.

The three rules that are usually wrong in a hand engine, and are tested here:

* **A short all-in reopens the action but not the raising.** These are two
  different questions and conflating them is the classic hand-engine bug. If
  somebody jams for less than a full raise, everyone still behind the bet must
  call or fold - the money is owed either way - but only players who have not
  acted since the last *full* raise may re-raise. ``need_to_act`` answers the
  first question, ``may_raise`` answers the second off ``raise_seq``.
* **The minimum raise tracks the last *full* raise**, not the last bet. A short
  all-in bumps ``current_bet`` without bumping ``min_raise_to``.
* **Side pots are built from contribution levels, and folded money is live.**
  Chips a folder put in still belong in the pots at or below the level they
  reached, which is why the loop below sums over *all* players and filters only
  the eligibility list.
"""

import random

from cards import DECK
from evaluator import evaluate

PREFLOP, FLOP, TURN, RIVER, SHOWDOWN = "preflop", "flop", "turn", "river", "showdown"
STREETS = (PREFLOP, FLOP, TURN, RIVER)

#: How many board cards are out on each street.
BOARD_SIZE = {PREFLOP: 0, FLOP: 3, TURN: 4, RIVER: 5, SHOWDOWN: 5}


class Seat:
    """One player's state within a single hand."""

    __slots__ = ("name", "stack", "hole", "folded", "all_in",
                 "committed", "total", "acted_seq", "seat")

    def __init__(self, name, stack, seat):
        self.name = name
        self.seat = seat
        self.stack = stack
        self.hole = []
        self.folded = False
        self.all_in = False
        #: chips put in on the current street
        self.committed = 0
        #: chips put in across the whole hand, which is what side pots key on
        self.total = 0
        #: the value ``Hand.raise_seq`` held when this player last acted on this
        #: street, or -1 if they have not acted yet. A player may raise only if a
        #: *full* raise has landed since - which is what stops a short all-in
        #: from handing the table a fresh raising right it should not get.
        self.acted_seq = -1

    @property
    def live(self):
        """Still able to act: in the hand and with chips behind."""
        return not self.folded and not self.all_in

    @property
    def contending(self):
        """Still eligible to win a pot, whether or not able to act."""
        return not self.folded

    def to_dict(self):
        return {
            "name": self.name, "seat": self.seat, "stack": self.stack,
            "hole": list(self.hole), "folded": self.folded, "all_in": self.all_in,
            "committed": self.committed, "total": self.total,
            "acted_seq": self.acted_seq,
        }

    @classmethod
    def from_dict(cls, d):
        s = cls(d["name"], d["stack"], d["seat"])
        s.hole = list(d["hole"])
        s.folded = d["folded"]
        s.all_in = d["all_in"]
        s.committed = d["committed"]
        s.total = d["total"]
        s.acted_seq = d["acted_seq"]
        return s


class Hand:
    """One hand, from posting blinds to a settled pot.

    Construct with ``Hand.deal(...)`` for a fresh hand, or ``Hand.from_dict`` to
    resume one out of the database.
    """

    def __init__(self):
        self.seats = []
        self.button = 0
        self.sb = 0
        self.bb = 0
        self.ante = 0
        self.board = []
        self.deck = []
        self.street = PREFLOP
        self.to_act = None
        self.current_bet = 0
        self.last_full_raise = 0
        #: bumped by every full raise. Compared against a seat's ``acted_seq``
        #: to decide whether that seat still holds the right to raise.
        self.raise_seq = 0
        self.need_to_act = []
        self.log = []
        self.actions = []
        self.complete = False
        self.payouts = {}
        self.pots = []

    # ---------------------------------------------------------------- setup

    @classmethod
    def deal(cls, players, button, sb, bb, ante=0, rng=None, deck=None):
        """Start a hand.

        ``players`` is a list of ``(name, stack_in_cents)`` in seat order.
        ``button`` is an index into it. ``deck`` lets a test pin the cards; when
        it is None the deck is shuffled with ``rng``.
        """
        if len(players) < 2:
            raise ValueError("a hand needs at least two players")
        rng = rng or random.Random()

        h = cls()
        h.seats = [Seat(name, stack, i) for i, (name, stack) in enumerate(players)]
        h.button = button % len(players)
        h.sb, h.bb, h.ante = sb, bb, ante

        if deck is None:
            h.deck = list(DECK)
            rng.shuffle(h.deck)
        else:
            h.deck = list(deck)

        n = len(h.seats)
        for s in h.seats:
            s.hole = [h.deck.pop(), h.deck.pop()]

        if ante:
            for s in h.seats:
                h._put(s, min(ante, s.stack))
            for s in h.seats:
                s.committed = 0

        if n == 2:
            sb_seat, bb_seat = h.button, (h.button + 1) % 2
        else:
            sb_seat, bb_seat = (h.button + 1) % n, (h.button + 2) % n

        h._put(h.seats[sb_seat], min(sb, h.seats[sb_seat].stack))
        h._put(h.seats[bb_seat], min(bb, h.seats[bb_seat].stack))

        h.current_bet = max(s.committed for s in h.seats)
        h.last_full_raise = bb
        h._blind_seats = (sb_seat, bb_seat)

        first = h.button if n == 2 else (h.button + 3) % n
        h.need_to_act = h._order_from(first)
        h.to_act = h._next_actor()
        h.log.append({"kind": "deal", "button": h.button,
                      "sb": sb_seat, "bb": bb_seat})
        h._settle_if_done()
        return h

    def _put(self, seat, amount):
        """Move ``amount`` from a stack into the pot, marking all-in if it empties."""
        amount = min(amount, seat.stack)
        seat.stack -= amount
        seat.committed += amount
        seat.total += amount
        if seat.stack == 0:
            seat.all_in = True
        return amount

    def _order_from(self, start):
        """Seat indices in action order beginning at ``start``, live players only."""
        n = len(self.seats)
        return [(start + i) % n for i in range(n) if self.seats[(start + i) % n].live]

    def _next_actor(self):
        """Whoever is next in ``need_to_act`` and still able to act."""
        while self.need_to_act:
            idx = self.need_to_act[0]
            if self.seats[idx].live:
                return idx
            self.need_to_act.pop(0)
        return None

    # -------------------------------------------------------------- queries

    @property
    def pot(self):
        """Everything committed so far, this street and every street before it."""
        return sum(s.total for s in self.seats)

    @property
    def contenders(self):
        return [s for s in self.seats if s.contending]

    def call_amount(self, idx):
        """What this player must add to match the current bet (capped by stack)."""
        s = self.seats[idx]
        return min(self.current_bet - s.committed, s.stack)

    def min_raise_to(self, idx):
        """Smallest legal total-this-street a raise may go to.

        Tracks the last *full* raise, so a short all-in raises what you must call
        without raising what you must raise to.
        """
        s = self.seats[idx]
        want = self.current_bet + self.last_full_raise
        return min(want, s.committed + s.stack)

    def max_raise_to(self, idx):
        s = self.seats[idx]
        return s.committed + s.stack

    def legal_actions(self, idx=None):
        """Every action the player on the clock may take, as dicts.

        A raise carries ``min`` and ``max`` as *totals for the street*, not
        increments - the same number the ``to`` field of a raise action takes,
        so a caller never has to convert between the two and get it backwards.
        """
        if self.complete:
            return []
        idx = self.to_act if idx is None else idx
        if idx is None:
            return []
        s = self.seats[idx]
        out = []
        to_call = self.call_amount(idx)

        if to_call > 0:
            out.append({"action": "fold"})
            out.append({"action": "call", "amount": to_call})
        else:
            out.append({"action": "check"})

        if s.stack > to_call and self.may_raise(idx):
            lo, hi = self.min_raise_to(idx), self.max_raise_to(idx)
            if hi > self.current_bet:
                kind = "raise" if self.current_bet > 0 else "bet"
                out.append({"action": kind, "min": min(lo, hi), "max": hi})

        return out

    def may_raise(self, idx):
        """Whether this seat still holds the right to raise.

        True until they act, and true again once a *full* raise lands behind
        them. A short all-in leaves ``raise_seq`` alone, so a player who has
        already acted stays locked to call-or-fold - which is the rule.
        """
        return self.seats[idx].acted_seq < self.raise_seq

    # --------------------------------------------------------------- acting

    def apply(self, action):
        """Apply one action for the player on the clock. Returns self."""
        if self.complete:
            raise ValueError("hand is over")
        idx = self.to_act
        if idx is None:
            raise ValueError("nobody is on the clock")
        seat = self.seats[idx]
        kind = action["action"]
        to_call = self.call_amount(idx)

        if kind == "fold":
            seat.folded = True
            self._record(idx, "fold", 0)

        elif kind == "check":
            if to_call > 0:
                raise ValueError(f"cannot check facing {to_call}")
            self._record(idx, "check", 0)

        elif kind == "call":
            paid = self._put(seat, to_call)
            self._record(idx, "call", paid)

        elif kind in ("bet", "raise"):
            target = int(action["to"])
            hi = self.max_raise_to(idx)
            lo = self.min_raise_to(idx)
            if target > hi:
                raise ValueError(f"cannot go to {target}, only {hi} behind")
            if target <= self.current_bet:
                raise ValueError(f"{target} does not raise {self.current_bet}")
            if target < lo and target < hi:
                raise ValueError(f"raise to {target} is below the minimum {lo}")

            increment = target - self.current_bet
            full = increment >= self.last_full_raise
            paid = self._put(seat, target - seat.committed)
            self.current_bet = target

            if full:
                self.last_full_raise = increment
                self.raise_seq += 1

            # Everyone still live and now behind the bet owes a decision, short
            # all-in or not - the chips are owed either way. Whether any of them
            # may *raise* is a different question, answered by may_raise().
            self.need_to_act = [
                i for i in self._order_from((idx + 1) % len(self.seats))
                if i != idx and self.seats[i].committed < self.current_bet
            ]
            self._record(idx, kind, paid)

        else:
            raise ValueError(f"unknown action {kind!r}")

        seat.acted_seq = self.raise_seq
        if self.need_to_act and self.need_to_act[0] == idx:
            self.need_to_act.pop(0)
        else:
            self.need_to_act = [i for i in self.need_to_act if i != idx]

        self.to_act = self._next_actor()
        self._settle_if_done()
        return self

    def _record(self, idx, kind, amount):
        self.actions.append({
            "seat": idx, "name": self.seats[idx].name, "street": self.street,
            "action": kind, "amount": amount,
            "to": self.seats[idx].committed, "pot_before": self.pot - amount,
        })

    # ------------------------------------------------------- street changes

    def _settle_if_done(self):
        """Advance the street, or finish the hand, if the round is over."""
        while True:
            if self.complete:
                return
            if len(self.contenders) == 1:
                self._award_uncontested()
                return
            if self.to_act is not None:
                return
            if self.street == RIVER:
                self._showdown()
                return
            self._advance_street()
            if self.to_act is not None:
                return

    def _advance_street(self):
        """Deal the next street and open a new betting round."""
        for s in self.seats:
            s.committed = 0
            s.acted_seq = -1
        self.current_bet = 0
        self.last_full_raise = self.bb
        self.raise_seq = 0

        nxt = STREETS[STREETS.index(self.street) + 1]
        self.street = nxt
        while len(self.board) < BOARD_SIZE[nxt]:
            self.board.append(self.deck.pop())
        self.log.append({"kind": "street", "street": nxt, "board": list(self.board)})

        if sum(1 for s in self.seats if s.live) <= 1:
            self.need_to_act = []
        else:
            n = len(self.seats)
            first = (self.button + 1) % n if n > 2 else (self.button + 1) % 2
            self.need_to_act = self._order_from(first)
        self.to_act = self._next_actor()

    # ------------------------------------------------------------ finishing

    def _award_uncontested(self):
        """Everyone folded. One player takes the lot, and never shows."""
        winner = self.contenders[0]
        total = self.pot
        winner.stack += total
        self.payouts = {winner.name: total}
        self.pots = [{"amount": total, "eligible": [winner.name],
                      "winners": [winner.name]}]
        self.complete = True
        self.street = SHOWDOWN
        self.log.append({"kind": "win", "name": winner.name, "amount": total,
                         "shown": False})

    def build_pots(self):
        """Split the money into a main pot and any side pots.

        Levels are the distinct amounts players put in across the hand. Each pot
        collects, from *every* player including folders, the slice of their
        contribution that falls in that level's band - which is how a folded
        player's chips end up in the pots they were still in for and none of the
        ones above.
        """
        levels = sorted({s.total for s in self.seats if s.total > 0})
        pots, prev = [], 0
        for level in levels:
            amount = sum(min(s.total, level) - min(s.total, prev) for s in self.seats)
            eligible = [s for s in self.seats if s.contending and s.total >= level]
            if amount > 0 and eligible:
                pots.append({"amount": amount, "eligible": eligible})
            elif amount > 0 and pots:
                pots[-1]["amount"] += amount
            prev = level
        return pots

    def _showdown(self):
        """Rank every contender and pay out each pot to its best eligible hands."""
        self.street = SHOWDOWN
        scores = {}
        for s in self.contenders:
            scores[s.name] = evaluate(list(s.hole) + list(self.board))

        payouts = {}
        detail = []
        for pot in self.build_pots():
            eligible = pot["eligible"]
            best = max(scores[s.name] for s in eligible)
            winners = [s for s in eligible if scores[s.name] == best]
            share, remainder = divmod(pot["amount"], len(winners))
            for s in winners:
                s.stack += share
                payouts[s.name] = payouts.get(s.name, 0) + share
            if remainder:
                odd = self._odd_chip_seat(winners)
                odd.stack += remainder
                payouts[odd.name] = payouts.get(odd.name, 0) + remainder
            detail.append({
                "amount": pot["amount"],
                "eligible": [s.name for s in eligible],
                "winners": [s.name for s in winners],
            })

        self.pots = detail
        self.payouts = payouts
        self.scores = scores
        self.complete = True
        self.log.append({"kind": "showdown", "board": list(self.board),
                         "scores": {k: v for k, v in scores.items()}})

    def _odd_chip_seat(self, winners):
        """An indivisible cent goes to the first winner left of the button."""
        n = len(self.seats)
        for i in range(1, n + 1):
            idx = (self.button + i) % n
            for s in winners:
                if s.seat == idx:
                    return s
        return winners[0]

    # ----------------------------------------------------- (de)serialisation

    def to_dict(self):
        return {
            "seats": [s.to_dict() for s in self.seats],
            "button": self.button, "sb": self.sb, "bb": self.bb, "ante": self.ante,
            "board": list(self.board), "deck": list(self.deck), "street": self.street,
            "to_act": self.to_act, "current_bet": self.current_bet,
            "last_full_raise": self.last_full_raise,
            "raise_seq": self.raise_seq,
            "need_to_act": list(self.need_to_act),
            "log": list(self.log), "actions": list(self.actions),
            "complete": self.complete, "payouts": dict(self.payouts),
            "pots": list(self.pots),
        }

    @classmethod
    def from_dict(cls, d):
        h = cls()
        h.seats = [Seat.from_dict(s) for s in d["seats"]]
        h.button, h.sb, h.bb = d["button"], d["sb"], d["bb"]
        h.ante = d.get("ante", 0)
        h.board, h.deck = list(d["board"]), list(d["deck"])
        h.street, h.to_act = d["street"], d["to_act"]
        h.current_bet = d["current_bet"]
        h.last_full_raise = d["last_full_raise"]
        h.raise_seq = d["raise_seq"]
        h.need_to_act = list(d["need_to_act"])
        h.log, h.actions = list(d["log"]), list(d["actions"])
        h.complete = d["complete"]
        h.payouts = dict(d["payouts"])
        h.pots = list(d["pots"])
        return h
