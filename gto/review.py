"""Marking the hero's decisions, and being honest about how each mark was made.

Every line the review prints carries **where its number came from**, because
they do not all come from the same place and they are not all equally good:

``solver``
    Read off a published equilibrium solution. Preflop only.
``derived``
    A solved range moved by a stated argument - the equal blinds, or the stack
    depth. The argument is printed with it.
``heuristic``
    No solve exists for the spot. Today that is the equal-blind small blind, and
    it is marked every time it is used.
``model``
    **Exact against this table, not against equilibrium.** Every bot's strategy
    is a known function, so the range each one is on can be computed by Bayes
    rather than guessed, and your equity against those ranges is then a real
    number. It is exactly right about the question "what is this worth against
    Ronit, Bell and Sanjay" and says nothing at all about equilibrium.
``arithmetic``
    Pot odds, break-even frequencies, minimum defence. True by definition.

**What this file will not do is invent the missing number.** A raise size cannot
be priced without solving the subgame it leads to, so a raise is reported with
its context and no score, rather than with a score that came from nowhere. A
multiway postflop spot has no equilibrium anybody can compute, so it gets the
model number and the arithmetic and no ``GTO`` verdict. Somebody learning from
this needs to be able to tell the difference between "this is wrong" and "nobody
knows", and the difference is in the label.

**Nor will it invent the missing comparison.** An exploit is reported as worth
what it is worth *against these ranges*, because that is the only thing that was
computed. Saying "and it would lose against a solid opener" would be a second
claim, about a range nobody evaluated, and it is not always even true - at four
to one, calling is a profit against everybody.

**The bounty is priced into the odds, not bolted on afterwards.** Folding breaks
a streak exactly as surely as losing does, so the streak's value is not a bonus
for continuing - it is added to the pot, because it is part of what winning is
worth and no part of what folding is worth.
"""

import bounty
import equity as eq
import ranges
import texture
from cards import cards_str, hole_class

CONFIDENCE_TEXT = {
    "solver": "from a solved equilibrium",
    "derived": "adjusted from a solved equilibrium",
    "heuristic": "a considered starting point - no solve covers this spot",
    "model": "exact against this table, not against equilibrium",
    "arithmetic": "true by definition",
}

#: How often equilibrium has to take an action before doing it is not a mistake.
#: A strategy that plays a hand three ways is not three quarters wrong.
MIXED_FLOOR = 0.20
CORRECT_FLOOR = 0.75
RARE_FLOOR = 0.02

#: Chart action names, by node, for each thing the hero can do.
_CHART_ACTION = {
    "rfi": {"raise": "raise", "bet": "raise", "check": "check", "fold": "fold"},
    "vs_rfi": {"raise": "3bet", "bet": "3bet", "call": "call", "fold": "fold"},
    "vs_3bet": {"raise": "4bet", "bet": "4bet", "call": "call", "fold": "fold"},
}


class Line:
    """One labelled number or statement in a review."""

    def __init__(self, label, text, confidence, value=None, note=None):
        self.label = label
        self.text = text
        self.confidence = confidence
        self.value = value
        self.note = note

    def to_dict(self):
        return {
            "label": self.label, "text": self.text, "value": self.value,
            "confidence": self.confidence,
            "confidence_text": CONFIDENCE_TEXT.get(self.confidence, ""),
            "note": self.note,
        }

    def __repr__(self):
        return f"<{self.label}: {self.text} [{self.confidence}]>"


class DecisionReview:
    """One decision, marked."""

    def __init__(self, decision, verdict, headline, lines, loss_bb=None):
        self.decision = decision
        self.verdict = verdict
        self.headline = headline
        self.lines = lines
        self.loss_bb = loss_bb

    def to_dict(self):
        d = self.decision
        return {
            "street": d.street,
            "position": d.position,
            "hole": cards_str(d.hole),
            "board": cards_str(d.board) if d.board else "",
            "action": d.action,
            "amount": d.amount,
            "verdict": self.verdict,
            "headline": self.headline,
            "loss_bb": None if self.loss_bb is None else round(self.loss_bb, 2),
            "lines": [x.to_dict() for x in self.lines],
        }


# ------------------------------------------------------------------ pieces


def _what_you_had(d):
    if d.board:
        return Line("Your hand",
                    f"{cards_str(d.hole)} on {cards_str(d.board)} - "
                    f"{texture.describe_hand(d.hole, d.board)}",
                    "arithmetic")
    return Line("Your hand", f"{cards_str(d.hole)} ({hole_class(d.hole)})",
                "arithmetic")


def _chart_line(d):
    """What equilibrium does with this hand here, or why there is no answer."""
    if d.street != "preflop" or d.node is None:
        return None, None
    if d.node[0] not in _CHART_ACTION:
        return None, Line(
            "Equilibrium",
            "No chart covers this node. Limped and multiway preflop pots are "
            "not solved anywhere, so there is no equilibrium answer to give you "
            "- the numbers below are against this table instead.",
            "model")

    chart = ranges.lookup(d.node, d.position, seats=d.seats, depth_bb=d.depth_bb)
    if chart is None:
        return None, Line(
            "Equilibrium",
            "No chart covers this spot, so nothing here is claiming to be "
            "equilibrium.", "model")

    cls = hole_class(d.hole)
    freqs = chart.freqs(cls)
    ordered = sorted(freqs.items(), key=lambda kv: -kv[1])
    best, best_freq = ordered[0]

    mine = _CHART_ACTION[d.node[0]].get(d.action)
    took = freqs.get(mine, 0.0) if mine else None

    parts = ", ".join(f"{a} {v * 100:.0f}%" for a, v in ordered if v >= 0.01)
    note = " ".join(chart.notes) if chart.notes else None
    line = Line("Equilibrium", f"With {cls} here it plays: {parts}.",
                chart.confidence, value=took, note=note)
    return (mine, took, best, best_freq, chart), line


def _range_lines(d, rng, iters):
    """Who is in, what they have, and how you do against it."""
    live = [o for o in getattr(d, "opponents_in", []) if o["action"] != "fold"]
    if not live:
        return None, []

    lines = [Line(
        "Who is in",
        "; ".join(f"{o['name']} ({o['position']}) {o['action']}s "
                  f"{o['range'].pct():.0f}% of hands" for o in live),
        "model")]

    dead = list(d.hole) + list(d.board)
    combos = []
    for o in live:
        c = ranges.weighted_combos(o["range"], dead=dead)
        if c:
            combos.append(c)
    if not combos:
        return None, lines

    try:
        e = eq.range_equity(d.hole, combos, board=d.board, rng=rng, iters=iters,
                            dead=dead)
    except ValueError:
        return None, lines

    mine = e[0]
    lines.append(Line(
        "Your equity",
        f"{mine * 100:.1f}% against {'that range' if len(combos) == 1 else 'those ranges'}"
        f" (±{e.error * 100:.1f})",
        "model", value=mine))
    return mine, lines


def _odds_lines(d, my_equity, bb, bounty_on, opponents):
    """Pot odds, the bounty, and what a call is worth. Facing a bet only."""
    if d.to_call <= 0:
        return None, []

    lines = []
    required = eq.required_equity(d.to_call, d.pot)
    lines.append(Line(
        "Pot odds",
        f"{d.to_call / bb:.1f}bb to win {d.pot / bb:.1f}bb - you need "
        f"{required * 100:.1f}% to break even",
        "arithmetic", value=required))

    extra_chips = 0.0
    if bounty_on and d.streak > 0:
        extra_bb = bounty.streak_value(d.streak, opponents, bb_dollars=bb / 100.0)
        extra_chips = extra_bb * bb
        if extra_bb >= 0.5:
            adjusted = eq.required_equity(d.to_call, d.pot + extra_chips)
            lines.append(Line(
                "Bounty",
                bounty.describe(d.streak, opponents, bb_dollars=bb / 100.0)
                + f" That drops what you need from {required * 100:.1f}% to "
                  f"{adjusted * 100:.1f}%.",
                "arithmetic", value=adjusted,
                note="Folding breaks the streak just as surely as losing does, "
                     "so the streak's value belongs in the pot rather than as a "
                     "reason to gamble."))
            required = adjusted

    if my_equity is None:
        return None, lines

    ev_chips = eq.call_ev(my_equity, d.to_call, d.pot + extra_chips)
    ev_bb = ev_chips / bb
    lines.append(Line(
        "Calling is worth",
        f"{ev_bb:+.2f}bb against folding",
        "model", value=ev_bb))
    return ev_bb, lines


def _aggression_lines(d, my_equity, bb):
    """What a bet or a check was, when nobody had bet into you.

    Neither can be *priced* without solving the subgame - what a bet is worth
    depends on what everybody does with the rest of their range afterwards, and
    that is the thing nobody can compute six-handed. But two useful things can
    still be said exactly: what a bet of that size needs to work, and whether a
    check gave up a hand that was probably best.
    """
    lines = []
    if d.to_call > 0:
        return lines

    if d.action in ("bet", "raise") and d.amount:
        pot_before = d.pot
        size = d.amount
        if pot_before > 0 and size > 0:
            need = eq.breakeven_bluff_frequency(size, pot_before)
            lines.append(Line(
                "Your sizing",
                f"{size / bb:.1f}bb into {pot_before / bb:.1f}bb - about "
                f"{100 * size / pot_before:.0f}% of the pot, which as a pure "
                f"bluff needs to work {need * 100:.0f}% of the time.",
                "arithmetic", value=need))

    if d.action == "check" and my_equity is not None and d.board:
        if my_equity > 0.65:
            lines.append(Line(
                "Checking here",
                f"You are ahead of these ranges {my_equity * 100:.0f}% of the "
                f"time. Value you do not bet on this street is value you cannot "
                f"get back on the next one.",
                "model", value=my_equity))
        elif my_equity < 0.35:
            lines.append(Line(
                "Checking here",
                f"You are behind these ranges - {my_equity * 100:.0f}% - so "
                f"checking is the cheap option and the right default.",
                "model", value=my_equity))
    return lines


def _defence_line(d, bb):
    """What has to keep coming back, when the hero folds facing a bet."""
    if d.to_call <= 0 or d.action != "fold":
        return None
    pot_before = d.pot - d.to_call
    if pot_before <= 0:
        return None
    mdf = eq.minimum_defence_frequency(d.to_call, pot_before)
    bluff = eq.breakeven_bluff_frequency(d.to_call, pot_before)
    return Line(
        "If you fold everything like this",
        f"A bet this size needs to work {bluff * 100:.0f}% of the time, so you "
        f"have to continue with {mdf * 100:.0f}% of your range to stop it "
        f"printing.",
        "arithmetic", value=mdf)


# ------------------------------------------------------------- the verdict


def _verdict(d, chart_bits, ev_bb, my_equity=None):
    """A word, a headline, and a number of big blinds where one is honest."""
    if chart_bits:
        mine, took, best, best_freq, chart = chart_bits
        if mine is None:
            return ("unpriced",
                    f"Limping is not in the chart, so there is no equilibrium "
                    f"mark for it. See what it was worth against this table.",
                    None)
        if took >= CORRECT_FLOOR:
            return ("correct", f"Standard. Equilibrium {best}s this "
                               f"{best_freq * 100:.0f}% of the time.", None)
        if took >= MIXED_FLOOR:
            return ("mixed", f"Fine - this is a hand equilibrium plays more "
                             f"than one way. It {mine}s {took * 100:.0f}% and "
                             f"{best}s {best_freq * 100:.0f}%.", None)
        # **Equilibrium and this table can disagree, and when they do that is
        # the most useful thing on the screen.** Equilibrium assumes the other
        # player is also playing equilibrium. Sanjay is not. A call that a chart
        # folds can still be a profit against a 45% opening range, and being
        # told it is simply "wrong" would teach the wrong lesson - the right one
        # is that it is an exploit, that it depends on the read, and that it
        # stops working against Ronit.
        exploit = ev_bb is not None and ev_bb > 0.05 and d.action in ("call", "check")
        if took >= RARE_FLOOR:
            if exploit:
                return ("exploit",
                        f"Equilibrium {mine}s this only {took * 100:.0f}% of the "
                        f"time - but against these ranges it is worth "
                        f"{ev_bb:+.2f}bb, so it is an exploit rather than a "
                        f"mistake. The profit is in the read, not in the hand: "
                        f"it lasts exactly as long as they keep playing that "
                        f"range.",
                        None)
            return ("thin", f"Thin. Equilibrium {mine}s only "
                            f"{took * 100:.0f}% here and mostly {best}s.",
                    _loss(ev_bb, d))
        if exploit:
            return ("exploit",
                    f"Equilibrium never {mine}s this - it {best}s "
                    f"{best_freq * 100:.0f}% of the time. Against these ranges "
                    f"it is still worth {ev_bb:+.2f}bb, so it is a read rather "
                    f"than an error - but it is only worth that against these "
                    f"ranges, and nothing here has checked what it is worth "
                    f"against anybody else.",
                    None)
        return ("error", f"Equilibrium does not {mine} here at all - it {best}s "
                         f"{best_freq * 100:.0f}% of the time.", _loss(ev_bb, d))

    if ev_bb is None:
        # Nothing bet into us, so there is no call to price. Say what can be
        # said rather than shrugging: a check with the best hand is a leak even
        # though its exact cost needs a solve.
        if d.action == "check" and my_equity is not None and my_equity > 0.65:
            return ("thin",
                    f"You checked with the best hand about "
                    f"{my_equity * 100:.0f}% of the time. That is the most "
                    f"common way a winning session turns into an even one.",
                    None)
        if d.action in ("bet", "raise"):
            return ("unpriced",
                    "A bet cannot be priced without solving what happens after "
                    "it, so this is context rather than a mark. The sizing "
                    "arithmetic below is exact.", None)
        return ("unpriced",
                "Nothing to price - nobody had bet, so there was no call to "
                "compare against folding.", None)
    if d.action == "fold" and ev_bb > 0.15:
        return ("error", f"Folding cost you about {ev_bb:.2f}bb - calling was "
                         f"profitable against these ranges.", ev_bb)
    if d.action in ("call", "check") and ev_bb < -0.15:
        return ("error", f"Calling cost about {-ev_bb:.2f}bb against these "
                         f"ranges; folding was better.", -ev_bb)
    return ("correct", "Reasonable against these ranges.", None)


def _loss(ev_bb, d):
    if ev_bb is None:
        return None
    if d.action == "fold" and ev_bb > 0:
        return ev_bb
    if d.action in ("call", "check") and ev_bb < 0:
        return -ev_bb
    return None


# -------------------------------------------------------------- the whole


def review_decision(d, bb=25, bounty_on=True, opponents=5, rng=None, iters=3000):
    """Mark one decision."""
    lines = [_what_you_had(d)]

    chart_bits, chart_line = _chart_line(d)
    if chart_line:
        lines.append(chart_line)

    # Order matters: the verdict needs the EV before it can tell an exploit from
    # an error, so the model numbers are computed before anything is judged.
    my_equity, range_lines = _range_lines(d, rng, iters)
    lines.extend(range_lines)

    ev_bb, odds_lines = _odds_lines(d, my_equity, bb, bounty_on, opponents)
    lines.extend(odds_lines)

    lines.extend(_aggression_lines(d, my_equity, bb))

    defence = _defence_line(d, bb)
    if defence:
        lines.append(defence)

    verdict, headline, loss = _verdict(d, chart_bits, ev_bb, my_equity)
    return DecisionReview(d, verdict, headline, lines, loss)


def review_hand(table, rng=None, iters=3000):
    """Mark every decision the hero made in the hand just finished."""
    opponents = len(table.seat_names) - 1
    return [
        review_decision(d, bb=table.bb, bounty_on=table.bounty_on,
                        opponents=opponents, rng=rng, iters=iters)
        for d in table.decisions if d.action is not None
    ]


def adaptation_notes(table):
    """What the bots have started doing differently, for the review to surface."""
    out = []
    for name, bot in table.bots.items():
        for note in bot.memory.notes():
            out.append(f"{name} {note}.")
        if bot.tilt > 0.35:
            out.append(f"{name} is steaming and is playing more hands than usual.")
    return out
