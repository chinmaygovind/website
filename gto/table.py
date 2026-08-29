"""One seat, five friends, and a game that keeps going.

This is the layer between the rules (``engine.py``) and the web app. It owns the
things a hand does not: who is sitting there, how much they have, whose turn the
button is, the bounty streaks, and the record of every decision the hero made -
which is the raw material the review works from.

**The server never sleeps.** Bots decide instantly and their think-time comes
back as a ``delay`` on each event for the browser to pace. A server that slept
for Bell's nine-second tank would hold a worker for nine seconds, and there are
three of them.

**Everybody sits down with one buy-in.** The stacks used to start scattered -
somebody stuck, somebody running hot - on the argument that a home game two
hours old does not look like a lobby, and that a table of identical stacks is a
solved-looking game. It also meant the first hand of a session was played at
whatever depths the dice handed you, which is a confusing thing to open with.
They diverge fast enough on their own from the second orbit, so the shape is
now something the session produces rather than something it starts with.
"""

import random

import bounty
import ranges
from cards import card_str, cards_str
import equity as eq
from engine import BOARD_SIZE, PREFLOP, Hand

#: Seat names by distance from the button. Five-handed drops UTG, which is the
#: same reduction ``ranges.POSITIONS`` makes and for the same reason.
ORDER_FROM_BUTTON = {
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    5: ["BTN", "SB", "BB", "HJ", "CO"],
    4: ["BTN", "SB", "BB", "CO"],
    3: ["BTN", "SB", "BB"],
    2: ["BTN", "BB"],
}


def position_names(n, button):
    """``seat index -> position name``."""
    order = ORDER_FROM_BUTTON[n]
    return {(button + i) % n: name for i, name in enumerate(order)}


def preflop_node(hand, positions):
    """Which charted node the action is at, for the bots and for the review.

    Returns a ``ranges.lookup`` node, or ``("limped",)`` / ``("multi",)`` for the
    shapes nothing is charted for.
    """
    raises = [a for a in hand.actions
              if a["street"] == PREFLOP and a["action"] in ("raise", "bet")]
    calls = [a for a in hand.actions
             if a["street"] == PREFLOP and a["action"] == "call"]

    if not raises:
        return ("limped",) if calls else ("rfi",)
    if len(raises) == 1:
        return ("vs_rfi", positions[raises[0]["seat"]])
    if len(raises) == 2:
        return ("vs_3bet", positions[raises[1]["seat"]])
    return ("multi",)


def preflop_node_before(hand, positions, action):
    """The node an already-taken preflop action was faced with.

    Rebuilt from the actions that came before it, because a bot's range depends
    on what it was looking at when it decided - not on what the pot looks like
    once everybody behind has piled in.
    """
    earlier = []
    for a in hand.actions:
        if a is action:
            break
        if a["street"] == PREFLOP:
            earlier.append(a)
    raises = [a for a in earlier if a["action"] in ("raise", "bet")]
    calls = [a for a in earlier if a["action"] == "call"]
    if not raises:
        return ("limped",) if calls else ("rfi",)
    if len(raises) == 1:
        return ("vs_rfi", positions[raises[0]["seat"]])
    if len(raises) == 2:
        return ("vs_3bet", positions[raises[1]["seat"]])
    return ("multi",)


class Decision:
    """One spot the hero was put in, with everything needed to score it later."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def to_dict(self):
        out = dict(self.__dict__)
        out["opponents_in"] = [
            {**o, "range": dict(o["range"])} for o in out.get("opponents_in", [])
        ]
        return out


class Table:
    """A continuous session: the seat, the five of them, and the running score."""

    def __init__(self, hero, opponents, buyin=5000, sb=25, bb=25,
                 bounty_on=True, rng=None, seats=None):
        self.rng = rng or random.Random()
        self.hero = hero
        self.buyin = buyin
        self.sb, self.bb = sb, bb
        self.bounty_on = bounty_on

        want = seats or self.rng.choice([5, 6])
        chosen = list(opponents)[: want - 1]
        self.bots = {b.profile.name: b for b in chosen}
        self.names = [hero] + [b.profile.name for b in chosen]

        self.stacks = {n: buyin for n in self.names}

        #: Every chip that has entered the game, per player. Profit is stack
        #: minus this, which is the only honest way to state it once people
        #: start rebuying - and it is what the hourly rate is computed from.
        #: The bounty only ever moves money between seats, so it never appears
        #: here, and ``sum(stacks) == sum(bought_in)`` is an invariant of the
        #: whole session.
        self.bought_in = dict(self.stacks)

        self.button = self.rng.randrange(len(self.names))
        self.streaks = bounty.Streaks(self.names)
        self.hand = None
        self.positions = {}
        #: Who is in which engine seat. Set properly by ``new_hand``, but seeded
        #: here so that a table nobody has dealt to yet can still describe
        #: itself - the page renders an empty table before the first hand.
        self.seat_names = list(self.names)
        self.decisions = []
        self.hands_played = 0
        self.hero_bought_in = buyin
        self.events = []
        #: The hero's accounting for the hand just finished, written by
        #: ``_settle``. ``None`` until one has been played.
        self.last_hand = None

    # ------------------------------------------------------------ the hand

    @property
    def hero_seat(self):
        return 0

    def seated(self):
        """Who has chips to play. Anyone at zero is sitting out until they rebuy."""
        return [n for n in self.names if self.stacks[n] > 0]

    def needs_rebuy(self):
        return self.stacks[self.hero] <= 0

    def rebuy(self, amount=None):
        amount = amount or self.buyin
        self.stacks[self.hero] += amount
        self.bought_in[self.hero] += amount
        self.hero_bought_in += amount

    def profit(self, name=None):
        """Chips won or lost, net of every rebuy. Cents."""
        name = name or self.hero
        return self.stacks[name] - self.bought_in[name]

    def new_hand(self):
        """Deal, top the bots up the way a home game does, and run to the hero."""
        for name, b in self.bots.items():
            b.hand_over()
            if self.stacks[name] <= 0:
                # A friend who busts rebuys without being asked, for the one
                # buy-in everybody sat down with. The hero is asked, because
                # that is a decision worth making on purpose.
                self.stacks[name] = self.buyin
                self.bought_in[name] += self.buyin

        players = [(n, self.stacks[n]) for n in self.names if self.stacks[n] > 0]
        if len(players) < 2:
            raise ValueError("not enough players with chips")

        while self.names[self.button] not in dict(players):
            self.button = (self.button + 1) % len(self.names)
        seat_of = {n: i for i, (n, _) in enumerate(players)}
        button_seat = seat_of[self.names[self.button]]

        self.hand = Hand.deal(players, button_seat, self.sb, self.bb, rng=self.rng)
        self.positions = position_names(len(players), button_seat)
        self.seat_names = [n for n, _ in players]
        self.decisions = []
        self.events = []
        return self.advance()

    def _seat_of_hero(self):
        return self.seat_names.index(self.hero) if self.hero in self.seat_names else None

    # ----------------------------------------------------------- the loop

    def advance(self):
        """Run bots until it is the hero's turn or the hand is over."""
        h = self.hand
        hero_seat = self._seat_of_hero()
        while not h.complete and h.to_act is not None and h.to_act != hero_seat:
            self._bot_acts(h.to_act)
        if h.complete:
            self._settle()
        elif h.to_act == hero_seat:
            self._record_decision(hero_seat)
        return self.events

    def _bot_acts(self, idx):
        h = self.hand
        name = self.seat_names[idx]
        bot = self.bots[name]
        seat = h.seats[idx]
        to_call = h.call_amount(idx)
        opponents = max(1, len(h.contenders) - 1)
        legal = {a["action"]: a for a in h.legal_actions()}

        if h.street == PREFLOP:
            node = preflop_node(h, self.positions)
            limpers, entrants = self._preflop_entrants()
            kind, size = bot.preflop_action(
                node, self.positions[idx], seat.hole, to_call, h.pot,
                seat.stack, seats=len(self.seat_names),
                depth_bb=seat.stack / self.bb, limpers=limpers,
                entrants=entrants, streak=self.streaks.streak[name],
            )
        else:
            aggressor = self._last_aggressor()
            kind, size = bot.postflop_action(
                seat.hole, h.board, to_call, h.pot, seat.stack, opponents,
                in_position=self._in_position(idx), is_aggressor=(aggressor == idx),
                street=h.street,
            )

        action = self._legalise(kind, size, legal, idx)
        close = to_call > 0 and to_call > h.pot * 0.25
        self.events.append({
            "seat": idx, "name": name, "action": action["action"],
            "amount": action.get("amount") or action.get("to") or 0,
            "delay": round(bot.think_time(close), 2), "street": h.street,
        })
        h.apply(action)

    def _legalise(self, kind, size, legal, idx):
        """Turn a bot's intent into something the engine will accept.

        A bot may want to raise when raising is not on offer - it has already
        acted and only a short all-in came behind it - and the honest answer
        then is to call, not to crash.
        """
        h = self.hand
        if kind in ("bet", "raise"):
            key = "raise" if "raise" in legal else ("bet" if "bet" in legal else None)
            if key:
                pot = h.pot
                want = h.current_bet + int(pot * (size or 0.6))
                lo, hi = legal[key]["min"], legal[key]["max"]
                return {"action": key, "to": max(lo, min(hi, want))}
            kind = "call" if "call" in legal else "check"
        if kind == "call" and "call" in legal:
            return {"action": "call", "amount": legal["call"]["amount"]}
        if kind == "check" and "check" in legal:
            return {"action": "check"}
        if kind == "fold" and "fold" in legal:
            return {"action": "fold"}
        return {"action": "check"} if "check" in legal else {"action": "fold"}

    def _preflop_entrants(self):
        """``(limpers, entrants)`` - who has *voluntarily* put money in so far.

        Not the same as who was dealt cards, and using the latter tightens every
        bot before a single decision has been made.
        """
        acts = [a for a in self.hand.actions if a["street"] == PREFLOP]
        limpers = sum(1 for a in acts if a["action"] == "call")
        entrants = sum(1 for a in acts if a["action"] in ("call", "raise", "bet"))
        return limpers, entrants

    def _last_aggressor(self):
        h = self.hand
        same = [a for a in h.actions
                if a["street"] == h.street and a["action"] in ("bet", "raise")]
        if same:
            return same[-1]["seat"]
        earlier = [a for a in h.actions if a["action"] in ("bet", "raise")]
        return earlier[-1]["seat"] if earlier else None

    def _in_position(self, idx):
        """Whether this seat acts last among those still in, postflop."""
        h = self.hand
        live = [s.seat for s in h.contenders]
        order = [(self.hand.button + 1 + i) % len(h.seats) for i in range(len(h.seats))]
        live_order = [s for s in order if s in live]
        return bool(live_order) and live_order[-1] == idx

    # ------------------------------------------------------- hero's turn

    def opponent_ranges(self):
        """What every live opponent's range is, right now.

        Taken at the moment the hero is asked to act, because it depends on what
        everybody has done so far and there is no reconstructing it afterwards
        from a settled hand. Exact given the model of each bot - see
        ``Bot.range_after``.

        Postflop it is still the **preflop** range, narrowed by the preflop
        action only. That is a real limitation and ``review.py`` labels it: a bot
        that check-raised the turn is on a much stronger range than its preflop
        one, and nothing here knows that yet.
        """
        h = self.hand
        limpers, entrants = self._preflop_entrants()
        out = []
        for i, name in enumerate(self.seat_names):
            if name == self.hero or not h.seats[i].contending:
                continue
            bot = self.bots.get(name)
            if bot is None:
                continue
            acts = [a for a in h.actions
                    if a["seat"] == i and a["street"] == PREFLOP]
            if not acts:
                continue
            last = acts[-1]["action"]
            action = "raise" if last in ("raise", "bet") else (
                "call" if last == "call" else "fold")
            node = preflop_node_before(h, self.positions, acts[-1])
            out.append({
                "name": name,
                "position": self.positions[i],
                "action": action,
                # What they have left behind the line. ``rollout.py`` needs it to
                # know when a raise it is pricing is actually all-in, and it is
                # cheaper to record it now than to reconstruct it from a settled
                # hand later. Absent on decisions recorded before this existed,
                # so every reader must default it.
                "stack": h.seats[i].stack,
                "range": bot.range_after(
                    node, self.positions[i], action,
                    seats=len(self.seat_names),
                    depth_bb=max(1.0, h.seats[i].stack / self.bb),
                    limpers=limpers, entrants=entrants,
                    streak=self.streaks.streak[name]),
            })
        return out

    def _record_decision(self, idx):
        h = self.hand
        seat = h.seats[idx]
        node = preflop_node(h, self.positions) if h.street == PREFLOP else None
        self.decisions.append(Decision(
            street=h.street,
            position=self.positions[idx],
            node=node,
            hole=list(seat.hole),
            board=list(h.board),
            pot=h.pot,
            to_call=h.call_amount(idx),
            stack=seat.stack,
            legal=h.legal_actions(),
            opponents=max(1, len(h.contenders) - 1),
            seats=len(self.seat_names),
            depth_bb=seat.stack / self.bb,
            streak=self.streaks.streak[self.hero],
            in_position=self._in_position(idx),
            opponents_in=self.opponent_ranges(),
            # The engine's own record of the spot, taken now because it cannot
            # be reconstructed later: by the time a hand is written down its
            # action log covers the whole hand and every stack is the settled
            # one. Raw facts only - who is where, what they have, what has
            # happened - and deliberately nothing this repo concluded about it,
            # because `coach.py` is the one reader and its whole value is that
            # it works the hand out without seeing `review.py`'s answer.
            actions_before=[dict(a) for a in h.actions],
            seats_at=[{"name": s.name, "position": self.positions.get(i),
                       "stack": s.stack, "committed": s.committed,
                       "in_hand": bool(s.contending)}
                      for i, s in enumerate(h.seats)],
            action=None,
            amount=None,
        ))

    def hero_act(self, action):
        """Apply the hero's action, record it, and run on."""
        h = self.hand
        idx = self._seat_of_hero()
        if h.complete or h.to_act != idx:
            raise ValueError("not your turn")

        if self.decisions and self.decisions[-1].action is None:
            d = self.decisions[-1]
            d.action = action["action"]
            d.amount = action.get("to") or action.get("amount") or 0

        self.events = []
        h.apply(action)
        return self.advance()

    # --------------------------------------------------------- settling

    def _settle(self):
        h = self.hand
        for i, name in enumerate(self.seat_names):
            self.stacks[name] = h.seats[i].stack

        winners = sorted(h.payouts, key=lambda n: -h.payouts[n])
        top = h.payouts.get(winners[0], 0) if winners else 0
        sole = [n for n in h.payouts if h.payouts[n] == top]

        transfers = {}
        if self.bounty_on:
            transfers = self.streaks.settle(sole, self.bb / 100.0)
            for name, amount in transfers.items():
                if name in self.stacks:
                    self.stacks[name] += int(round(amount * 100))

        for i, name in enumerate(self.seat_names):
            if name in self.bots:
                lost = h.seats[i].total - h.payouts.get(name, 0)
                self.bots[name].lost_pot(lost / self.bb, self.stacks[name] / self.bb)

        self.last_hand = self._hand_summary(transfers)
        self.hands_played += 1
        self.button = (self.button + 1) % len(self.names)
        self.events.append({"kind": "hand_over", "payouts": dict(h.payouts),
                            "streaks": dict(self.streaks.streak)})

    def _hand_summary(self, transfers):
        """What this one hand did to the hero, and what he did in it.

        **Per hand, and with the bounty kept out of the poker.** The running
        stats used to be reconstructed by differencing the hero's cumulative
        profit, which broke twice over: profit restarts at zero at every fresh
        sit-down, so the first hand of a session posted the whole of the last
        one as a loss; and the bounty is settled into ``stacks``, so bounty
        money was being counted as a poker win rate. It is not poker and at
        0.25/0.25 it is bigger than the poker, which is exactly why
        ``stats.py`` keeps the two apart - and it can only do that if what
        reaches it is already separated.
        """
        h = self.hand
        hero = self.hero
        seat = self._seat_of_hero()
        if seat is None:
            return None

        won = hero in (h.payouts or {})
        contested = len(h.contenders) > 1
        pre = [a for a in h.actions
               if a["seat"] == seat and a["street"] == PREFLOP]
        faced_raise = [d for d in self.decisions
                       if d.street == PREFLOP and d.node and d.node[0] == "vs_rfi"]

        return {
            "hand_no": self.hands_played + 1,
            "position": self.positions.get(seat),
            "hole": list(h.seats[seat].hole),
            "board": list(h.board),
            #: Chips won minus chips put in, this hand only. The bounty is not
            #: in here even though it has already moved the stack.
            "result_cents": h.payouts.get(hero, 0) - h.seats[seat].total,
            "ev_cents": self._ev_result(),
            "bounty_cents": int(round(transfers.get(hero, 0) * 100)),
            "vpip": any(a["action"] in ("call", "raise", "bet") for a in pre),
            "pfr": any(a["action"] in ("raise", "bet") for a in pre),
            #: A chance to three-bet is a spot where exactly one raise was in
            #: front of you - which is what the ``vs_rfi`` node means, so it is
            #: read off the decisions rather than counted a second way.
            "three_bet_chance": bool(faced_raise),
            "three_bet": any(d.action in ("raise", "bet") for d in faced_raise),
            "saw_flop": bool(h.board) and not h.seats[seat].folded,
            "showdown": bool(h.board) and contested and not h.seats[seat].folded,
            "won": won,
            "won_showdown": won and contested and bool(h.board),
            "streak_after": self.streaks.streak.get(hero, 0),
        }

    def _ev_result(self):
        """The hand's result with an all-in runout replaced by its equity.

        Getting it in with 80% and losing is a 0% hand in the ledger and an 80%
        hand in reality, and over a few hundred hands the difference between
        those two is most of the variance that has nothing to do with how
        somebody played. This is the number the win rate converges on roughly
        three times faster, and the one the headline uses.

        It only ever fires when money went in with cards still to come: the
        street of the last action says how much of the board was out when the
        betting stopped, and if that is five then nothing was gambled and the
        observed result is already exact.

        **Side pots are paid by equity within each pot's own eligible set**,
        renormalised, the same way ``Hand._showdown`` pays them by who actually
        won - a player who is not in for a pot cannot take a share of it.
        """
        h = self.hand
        seat = self._seat_of_hero()
        if seat is None or not h.actions:
            return None
        hero_seat = h.seats[seat]
        if hero_seat.folded or len(h.contenders) < 2:
            return None

        known = BOARD_SIZE[h.actions[-1]["street"]]
        if known >= 5:
            return None

        board = list(h.board[:known])
        contenders = list(h.contenders)
        shares = eq.showdown_equity([list(s.hole) for s in contenders], board,
                                    rng=self.rng, iters=4000)
        by_name = {s.name: shares[i] for i, s in enumerate(contenders)}

        expected = 0.0
        for pot in h.build_pots():
            eligible = pot["eligible"]
            total = sum(by_name.get(s.name, 0.0) for s in eligible)
            if total <= 0:
                continue
            mine = by_name.get(self.hero, 0.0) if hero_seat in eligible else 0.0
            expected += pot["amount"] * mine / total
        return int(round(expected)) - hero_seat.total

    # ------------------------------------------------------------ output

    def state(self, reveal=False):
        h = self.hand
        hero_seat = self._seat_of_hero()
        return {
            "hands_played": self.hands_played,
            "button": h.button if h else None,
            "street": h.street if h else None,
            "board": [card_str(c) for c in h.board] if h else [],
            "pot": h.pot if h else 0,
            "to_act": h.to_act if h else None,
            "complete": h.complete if h else True,
            "streaks": dict(self.streaks.streak),
            "seats": [
                {
                    "name": n,
                    "position": self.positions.get(i),
                    "stack": h.seats[i].stack if h else self.stacks[n],
                    "committed": h.seats[i].committed if h else 0,
                    "folded": h.seats[i].folded if h else False,
                    "all_in": h.seats[i].all_in if h else False,
                    "hole": (cards_str(h.seats[i].hole)
                             if h and (reveal or i == hero_seat) else None),
                }
                for i, n in enumerate(self.seat_names if h else self.names)
            ],
            "legal": h.legal_actions() if h and h.to_act == hero_seat else [],
        }

    # ------------------------------------------------------- persistence

    def to_dict(self):
        """The whole session, as JSON-safe data.

        **The table lives in the database, not in a worker's memory.** Two
        reasons, and the second is the one that decides it: gunicorn runs three
        sync workers and the next request is not guaranteed to reach the one
        holding your table; and a deploy restarts the service, which with
        in-memory state would end everybody's session mid-hand every time
        anything ships.

        The bots' random state is deliberately **not** kept. Continuity of
        randomness across a page load is worth nothing, and storing a Mersenne
        Twister's 624 words per bot to get it would be silly.
        """
        return {
            "hero": self.hero,
            "buyin": self.buyin,
            "sb": self.sb,
            "bb": self.bb,
            "bounty_on": self.bounty_on,
            "names": list(self.names),
            "stacks": dict(self.stacks),
            "bought_in": dict(self.bought_in),
            "button": self.button,
            "hands_played": self.hands_played,
            "hero_bought_in": self.hero_bought_in,
            "streaks": self.streaks.to_dict(),
            "bots": {
                name: {
                    "profile": b.profile.to_dict(),
                    "memory": b.memory.to_dict(),
                    "tilt": b.tilt,
                }
                for name, b in self.bots.items()
            },
            "hand": self.hand.to_dict() if self.hand else None,
            "seat_names": list(getattr(self, "seat_names", [])),
            "positions": {str(k): v for k, v in self.positions.items()},
            "decisions": [d.to_dict() for d in self.decisions],
            "last_hand": self.last_hand,
        }

    @classmethod
    def from_dict(cls, d, rng=None):
        import bots as bots_module
        import profiles as profiles_module

        rng = rng or random.Random()
        restored = []
        for name in d["names"][1:]:
            spec = d["bots"][name]
            bot = bots_module.Bot(
                profiles_module.Profile.from_dict(spec["profile"]), rng,
                memory=bots_module.Memory.from_dict(spec["memory"]))
            bot.tilt = spec["tilt"]
            restored.append(bot)

        t = cls(d["hero"], restored, buyin=d["buyin"], sb=d["sb"], bb=d["bb"],
                bounty_on=d["bounty_on"], rng=rng, seats=len(d["names"]))
        t.names = list(d["names"])
        t.stacks = dict(d["stacks"])
        t.bought_in = dict(d["bought_in"])
        t.button = d["button"]
        t.hands_played = d["hands_played"]
        t.hero_bought_in = d["hero_bought_in"]
        t.streaks = bounty.Streaks.from_dict(d["streaks"])
        t.seat_names = list(d["seat_names"])
        t.positions = {int(k): v for k, v in d["positions"].items()}
        t.hand = Hand.from_dict(d["hand"]) if d["hand"] else None
        t.last_hand = d.get("last_hand")
        t.decisions = [Decision(**x) for x in d["decisions"]]
        for dec in t.decisions:
            dec.opponents_in = [
                {**o, "range": ranges.Range(o["range"])}
                for o in getattr(dec, "opponents_in", [])
            ]
        return t
