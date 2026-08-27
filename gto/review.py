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
import rollout
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

#: Big blinds an off-chart line has to be worth against this table before it is
#: called an exploit rather than a rounding error. It reads in both directions:
#: a call the chart folds, and a fold that passed one up.
EXPLOIT_FLOOR = 0.05

#: Equity a holding the board has already beaten needs before the bucket split
#: calls it live rather than dead. A gutshot on the flop is about 16% and an
#: overcard pair-out about 24%; below a tenth there is no draw worth counting,
#: and on the river the bucket is empty by construction because there is nothing
#: left to come.
LIVE_FLOOR = 0.12

#: Big blinds a better bet size has to be worth before the sizing curve is
#: allowed to say the size you chose was wrong, and before it calls it an error
#: rather than thin. The model behind the curve is one street deep - see
#: ``rollout.py`` - so it systematically understates a small bet that sets up
#: the next one, and these are set wide enough that it takes a real gap to
#: overcome that rather than a modelling artefact.
SIZING_FLOOR = 0.25
SIZING_ERROR = 1.00

#: Chart action names, by node, for each thing the hero can do.
_CHART_ACTION = {
    "rfi": {"raise": "raise", "bet": "raise", "check": "check", "fold": "fold"},
    "vs_rfi": {"raise": "3bet", "bet": "3bet", "call": "call", "fold": "fold"},
    "vs_3bet": {"raise": "4bet", "bet": "4bet", "call": "call", "fold": "fold"},
}


class Line:
    """One labelled number or statement in a review.

    ``chart`` is an optional structure the page draws rather than prints - a
    sizing curve, a bucket split. It is never the only place a number appears:
    the ``text`` always says the thing in words too, because a chart that fails
    to render must not take the finding with it.
    """

    def __init__(self, label, text, confidence, value=None, note=None,
                 chart=None):
        self.label = label
        self.text = text
        self.confidence = confidence
        self.value = value
        self.note = note
        self.chart = chart

    def to_dict(self):
        return {
            "label": self.label, "text": self.text, "value": self.value,
            "confidence": self.confidence,
            "confidence_text": CONFIDENCE_TEXT.get(self.confidence, ""),
            "note": self.note, "chart": self.chart,
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
    # The most frequent action that is *not* the one taken. Without it the
    # `mixed` headline read "it calls 70% and calls 70%" whenever the hand's
    # most common action was also the one the hero picked - which is most of
    # the time, since `mixed` is 20% to 75% and the top action is usually in it.
    other = next(((a, v) for a, v in ordered if a != mine), (best, best_freq))

    line = Line("Equilibrium", f"With {cls} here it plays: {parts}.",
                chart.confidence, value=took, note=note)
    return (mine, took, best, best_freq, chart, other), line


class _Model:
    """What the model layer worked out for one decision, in one place.

    It is one object rather than a pile of returns because three different
    readers want the same expensive computation - the equity line, the bucket
    split and the sizing curve - and computing it three times is the difference
    between a review that lands in a quarter of a second and one that does not.
    """

    def __init__(self):
        self.live = []
        #: Hero's equity against everybody still in, however many that is.
        self.equity = None
        self.error = 0.0
        #: Heads-up only: the one opponent, their combinations, and the hero's
        #: equity against each one. ``None`` the moment a second player is in,
        #: because nothing below this is honest multiway.
        self.name = None
        self.bot = None
        self.combos = None
        self.equities = None
        self.reads = None
        self.stack = None

    @property
    def solo(self):
        return self.equities is not None


def _model(d, rng, iters, bots):
    """Everything the ``model`` label covers, computed once."""
    m = _Model()
    m.live = [o for o in getattr(d, "opponents_in", []) if o["action"] != "fold"]
    if not m.live:
        return m

    dead = list(d.hole) + list(d.board)
    pools = []
    for o in m.live:
        c = ranges.weighted_combos(o["range"], dead=dead)
        if c:
            pools.append(c)
    if not pools:
        return m

    # Heads-up the per-combination pass is affordable and is strictly more
    # information than the pooled sample - the same weighted average, plus the
    # decomposition that produced it and the range left over after a call. Its
    # error is measured rather than assumed (``combined_error``) and lands on
    # top of what the pooled sampler manages in a fifth of the iterations.
    one = m.live[0]
    bot = (bots or {}).get(one["name"])
    if len(pools) == 1 and bot is not None:
        m.name = one["name"]
        m.bot = bot
        m.stack = one.get("stack")
        m.combos = pools[0]
        m.equities = eq.combo_equities(
            d.hole, m.combos, board=d.board, rng=rng,
            budget=eq.COMBO_BUDGET if d.board else eq.PREFLOP_COMBO_BUDGET)
        m.reads = [texture.read([a, b], d.board) for a, b, _w in m.combos]
        m.equity = eq.combined(m.equities, m.combos)
        m.error = m.equities.combined_error
        return m

    try:
        e = eq.range_equity(d.hole, pools, board=d.board, rng=rng, iters=iters,
                            dead=dead)
    except ValueError:
        return m
    m.equity = e[0]
    m.error = e.error
    return m


def _range_lines(d, m):
    """Who is in, what they have, and how you do against it."""
    if not m.live:
        return []

    lines = [Line(
        "Who is in",
        "; ".join(f"{o['name']} ({o['position']}) {o['action']}s "
                  f"{o['range'].pct():.0f}% of hands" for o in m.live),
        "model")]
    if m.equity is None:
        return lines

    against = "that range" if len(m.live) == 1 else "those ranges"
    # A zero after a plus-or-minus reads as a missing number rather than as the
    # strongest thing this line can say, which is that every runout was counted.
    how = ("every runout counted" if m.error <= 0
           else f"\u00b1{m.error * 100:.1f}")
    lines.append(Line(
        "Your equity",
        f"{m.equity * 100:.1f}% against {against} ({how})",
        "model", value=m.equity))
    if m.solo:
        lines.append(_bucket_line(d, m))
    return lines


#: How the bucket split is worded, per street. Preflop there is no board to be
#: ahead of, so the split is by how far ahead or behind the runout leaves you;
#: postflop it is the count anybody can do at the table.
_BUCKET_HELP = (
    "This is a count you can do yourself, and it is the whole method. Write "
    "down the hands they can actually have here. Split them into the ones you "
    "are already beating, the ones beating you that you can still outdraw, and "
    "the ones you are dead against. Give each group one rough number - a hand "
    "you beat on a dry board is worth about 90%, a live draw about a quarter, a "
    "dead one nothing - and average them weighted by how many combinations are "
    "in each group. A pair is 6 combinations, a suited hand 4, an offsuit hand "
    "12, and a card in your own hand or on the board removes some of them. That "
    "average is your equity, and it is the same arithmetic printed above."
)


def _bucket_line(d, m):
    """The weighted average, taken apart into the three groups it came from."""
    ahead = m.equities.ahead
    groups = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]  # weight, weight*equity
    for (a, b, w), e, is_ahead in zip(m.combos, m.equities, ahead):
        if is_ahead is None:
            slot = 0 if e >= 0.60 else (1 if e >= 0.40 else 2)
        elif is_ahead:
            slot = 0
        else:
            slot = 1 if e >= LIVE_FLOOR else 2
        groups[slot][0] += w
        groups[slot][1] += w * e

    total = sum(g[0] for g in groups) or 1.0
    if not d.board:
        names = ("you are a clear favourite over", "it is close against",
                 "you are behind")
    elif len(d.board) >= 5:
        # No cards to come, so nothing is drawing and nothing is dead: a
        # combination is beaten, beating, or chopping. The middle group is
        # **exactly the ties** - half a pot each, which is the only way to score
        # 0.5 with no runout left - and naming it "you can still outdraw" on a
        # river reads as a mistake in the tool. Leaving it out was worse: 1 and
        # 337 were printed against a total of 339, and the missing combination
        # was a chopped pot.
        names = ("you beat", "you split the pot with", "beat you")
    else:
        names = ("you are already ahead of", "you can still outdraw",
                 "you are drawing dead against")
    said, sums = [], []
    for (weight, weighted), name in zip(groups, names):
        if weight < 0.5 or not name:
            continue
        avg = weighted / weight
        said.append(f"{weight:.0f} {name} (worth {avg * 100:.0f}% each)")
        sums.append(f"{weight:.0f}\u00d7{avg * 100:.0f}%")
    if not said:
        return None

    # Approximately equal, and it has to be: every number in that sum is
    # rounded for reading while the equity above it is not, so a reader who does
    # this arithmetic lands half a point away. An equals sign there would make
    # the page look like it cannot add up.
    text = (f"{m.name} can have {total:.0f} combinations here. "
            + "; ".join(said) + ". "
            + f"({' + '.join(sums)}) \u00f7 {total:.0f} \u2248 "
              f"{m.equity * 100:.0f}%.")
    return Line("Where that equity comes from", text, "model",
                value=m.equity, note=_BUCKET_HELP,
                # The same groups the sentence names, dropped on the same rule.
                # Kept apart they disagreed: an empty middle bucket vanished
                # from the text and drew a box saying "0 combinations, 0%".
                chart={"kind": "buckets",
                       "labels": [n for g, n in zip(groups, names)
                                  if n and g[0] >= 0.5],
                       "rows": [{"combos": round(g[0]),
                                 "equity": round(g[1] / g[0] * 100, 1)}
                                for g, n in zip(groups, names)
                                if n and g[0] >= 0.5]})


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


#: What the sizing curve is and is not, printed under every one of them. The
#: page cannot be allowed to imply a solve happened here.
_SIZING_HELP = (
    "Every size is run against this opponent's actual strategy, hand by hand: "
    "their range here is known, their response to a bet of each size is a "
    "formula rather than a guess, so the fold, call and raise frequencies are "
    "exact and so is the range they have left after calling - which is why a "
    "bigger bet shows worse equity when it gets called. Three things it does "
    "not know. It stops at showdown on this street, so a small bet that sets up "
    "a bigger one on the next card is worth more than it says. It assumes you "
    "play the rest of the hand perfectly against a raise. And all of it is "
    "against these five people, not against equilibrium: a size that is best "
    "here can be wrong against somebody who folds properly."
)


def _sizing_lines(d, m, bb):
    """What each bet size was worth, when that can be answered at all.

    Only where the whole apparatus is honest: postflop, heads-up, and nobody has
    bet into the hero yet. Preflop is refused for a different reason from the
    others - ``Bot.preflop_action`` does not read a raise size at all, so the
    model cannot tell 2.5bb from 4bb and would print a flat line pretending it
    had an opinion.
    """
    if d.street == "preflop" or not m.solo or d.to_call > 0 or d.pot <= 0:
        return [], None
    if d.action not in ("bet", "raise", "check"):
        return [], None

    stack = m.stack if m.stack else d.stack
    sizes = rollout.price_bets(
        m.combos, m.equities, m.bot, pot=d.pot, hero_stack=d.stack,
        opp_stack=stack, board=d.board, street=d.street,
        hero_in_position=getattr(d, "in_position", True),
        yours=d.amount if d.action in ("bet", "raise") else None,
        reads=m.reads)
    # One bet against the check is still a comparison worth printing - short
    # stacked that is the entire decision. Nothing but the check is not.
    if len(sizes) < 2:
        return [], None

    best = max(sizes, key=lambda s: s.ev)
    yours = next((s for s in sizes if s.is_yours), None)
    if yours is None and d.action == "check":
        yours = sizes[0]
    if yours is None:
        return [], None

    gap = (best.ev - yours.ev) / bb
    mine = "checking" if yours.is_check else f"{yours.fraction:.0%} of the pot"
    won = "checking" if best.is_check else f"{best.fraction:.0%} of the pot"
    if best is yours or gap < SIZING_FLOOR:
        text = (f"{mine.capitalize()} was worth {yours.ev / bb:+.2f}bb, and "
                f"nothing on the curve beats it by enough to call it wrong.")
    else:
        text = (f"{won.capitalize()} was worth {best.ev / bb:+.2f}bb here; "
                f"{mine} was {yours.ev / bb:+.2f}bb, {gap:.2f}bb behind.")

    lines = [Line("What each size was worth", text, "model",
                  value=round(gap, 3), note=_SIZING_HELP,
                  chart={"kind": "sizes", "bb": bb,
                         "rows": [s.to_dict(bb) for s in sizes]})]

    # The reason, not just the number: a bet that is called more often by a
    # stronger range is the single thing a curve like this is for.
    bets = [s for s in sizes if not s.is_check and s.equity_called is not None]
    if len(bets) >= 2:
        small, big = bets[0], bets[-1]
        lines.append(Line(
            "Why the curve bends",
            f"{small.fraction:.0%} of the pot folds them out "
            f"{small.fold_pct * 100:.0f}% of the time and the hands that call it "
            f"are worth {small.equity_called * 100:.0f}% against you. "
            f"{big.fraction:.0%} folds them out {big.fold_pct * 100:.0f}% - but "
            f"what calls it is worth "
            f"only {big.equity_called * 100:.0f}%. Betting bigger buys folds and "
            f"sells you a worse showdown; which of those you want is what your "
            f"hand decides.",
            "model", value=small.equity_called - big.equity_called))
    return lines, (best, yours, gap)


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


def _sizing_verdict(d, sizing, bb):
    """A mark for a bet, a raise or a check, now that one can be made.

    This is the one thing ``review.py`` used to refuse outright: "a bet cannot
    be priced without solving what happens after it". It still cannot be priced
    against equilibrium, and this does not claim to - but against *these* five,
    whose strategies are known functions, every size has an exact fold, call and
    raise frequency, and that is enough to say which size was best and by how
    much. ``rollout.py`` states what the model does and does not see, and
    ``SIZING_FLOOR`` is set wide enough to absorb the part it does not.
    """
    best, yours, gap = sizing
    won = "checking" if best.is_check else f"betting {best.fraction:.0%} of the pot"
    if gap < SIZING_FLOOR:
        if yours.is_check:
            return ("correct", f"Fine. Checking was worth "
                               f"{yours.ev / bb:+.2f}bb against this range and "
                               f"nothing beats it by enough to matter.", None)
        return ("correct", f"Good size. {yours.fraction:.0%} of the pot was "
                           f"worth {yours.ev / bb:+.2f}bb, within "
                           f"{gap:.2f}bb of the best on the curve.", None)
    if yours.is_check:
        return ("thin" if gap < SIZING_ERROR else "error",
                f"Checking was worth {yours.ev / bb:+.2f}bb; {won} was worth "
                f"{best.ev / bb:+.2f}bb. Giving up {gap:.2f}bb.", gap)
    if best.is_check:
        return ("thin" if gap < SIZING_ERROR else "error",
                f"This one did not want a bet. Checking was worth "
                f"{best.ev / bb:+.2f}bb against {yours.ev / bb:+.2f}bb for "
                f"{yours.fraction:.0%} of the pot.", gap)
    bigger = best.fraction > yours.fraction
    return ("thin" if gap < SIZING_ERROR else "error",
            f"Right idea, wrong size - {'bigger' if bigger else 'smaller'}. "
            f"{best.fraction:.0%} of the pot was worth {best.ev / bb:+.2f}bb "
            f"against {yours.ev / bb:+.2f}bb for the {yours.fraction:.0%} you "
            f"chose.", gap)


def _verdict(d, chart_bits, ev_bb, my_equity=None, sizing=None, bb=25):
    """A word, a headline, and a number of big blinds where one is honest."""
    # An exploit is a line the chart does not take that this table pays for.
    # It comes in two directions and they are not the same event: you can take
    # one, or you can be handed one and fold it.
    took_one = ev_bb is not None and ev_bb > EXPLOIT_FLOOR and d.action in ("call", "check")
    missed_one = ev_bb is not None and ev_bb > EXPLOIT_FLOOR and d.action == "fold"

    if chart_bits:
        mine, took, best, best_freq, chart, other = chart_bits
        if mine is None:
            return ("unpriced",
                    f"Limping is not in the chart, so there is no equilibrium "
                    f"mark for it. See what it was worth against this table.",
                    None)
        if took >= CORRECT_FLOOR:
            # **An exploit needs the chart to actually disagree, and that is
            # why this sits inside the branch where the chart approved.** A
            # fold the chart folds 100% of the time, in a pot the model prices
            # as a call, is the equilibrium/table disagreement this file exists
            # to surface: the chart is answering "against an equilibrium
            # opener", and these five are not that. Checked any earlier it also
            # swallowed folds the chart *calls* - JTo in the big blind, which
            # equilibrium calls 100% of the time - and reported a plain error
            # as a read, with a "but" joining two clauses that agreed.
            if missed_one:
                return ("exploit",
                        f"Equilibrium {mine}s this {took * 100:.0f}% of the "
                        f"time too - but against these ranges calling was "
                        f"worth {ev_bb:+.2f}bb. The chart assumes the opener "
                        f"is at equilibrium and these five are not, so this is "
                        f"a read rather than a correction. It stops being true "
                        f"against a tighter table.",
                        ev_bb)
            return ("correct", f"Standard. Equilibrium {best}s this "
                               f"{best_freq * 100:.0f}% of the time.", None)
        if took >= MIXED_FLOOR:
            return ("mixed", f"Fine - this is a hand equilibrium plays more "
                             f"than one way. It {mine}s {took * 100:.0f}% and "
                             f"{other[0]}s {other[1] * 100:.0f}%.", None)
        # **Equilibrium and this table can disagree, and when they do that is
        # the most useful thing on the screen.** Equilibrium assumes the other
        # player is also playing equilibrium. Sanjay is not. A call that a chart
        # folds can still be a profit against a 45% opening range, and being
        # told it is simply "wrong" would teach the wrong lesson - the right one
        # is that it is an exploit, that it depends on the read, and that it
        # stops working against Ronit.
        if took >= RARE_FLOOR:
            if took_one:
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
        if took_one:
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
        # Nothing bet into us, so there is no call to price - but a bet or a
        # check into one opponent now has a curve behind it, and that is a real
        # mark rather than a shrug.
        if sizing is not None:
            return _sizing_verdict(d, sizing, bb)
        # Say what can be said rather than shrugging: a check with the best hand
        # is a leak even though its exact cost needs a solve.
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


def review_decision(d, bb=25, bounty_on=True, opponents=5, rng=None, iters=3000,
                    bots=None):
    """Mark one decision.

    ``bots`` is ``name -> Bot``. Without it the sizing curve and the bucket
    split are simply absent, because both are computed from the opponent's own
    strategy rather than from anything stored on the decision - so a review of a
    decision loaded back out of the database is the same review minus those two,
    rather than a worse version of them.
    """
    lines = [_what_you_had(d)]

    chart_bits, chart_line = _chart_line(d)
    if chart_line:
        lines.append(chart_line)

    # Order matters: the verdict needs the EV and the sizing curve before it can
    # tell an exploit from an error or a size from a mistake, so everything the
    # model can say is computed before anything is judged.
    m = _model(d, rng, iters, bots)
    lines.extend(_range_lines(d, m))

    ev_bb, odds_lines = _odds_lines(d, m.equity, bb, bounty_on, opponents)
    lines.extend(odds_lines)

    # The curve prices the check and every bet that was not made, so the older
    # "you are ahead, bet it" advice is the same finding said worse. It stays
    # for every spot the curve refuses - multiway, and facing a bet.
    sizing_lines, sizing = _sizing_lines(d, m, bb)
    if not sizing_lines:
        lines.extend(_aggression_lines(d, m.equity, bb))
    elif d.action in ("bet", "raise"):
        lines.extend(x for x in _aggression_lines(d, m.equity, bb)
                     if x.label == "Your sizing")
    lines.extend(sizing_lines)

    defence = _defence_line(d, bb)
    if defence:
        lines.append(defence)

    verdict, headline, loss = _verdict(d, chart_bits, ev_bb, m.equity, sizing, bb)
    return DecisionReview(d, verdict, headline, [x for x in lines if x], loss)


def review_hand(table, rng=None, iters=3000):
    """Mark every decision the hero made in the hand just finished."""
    opponents = len(table.seat_names) - 1
    return [
        review_decision(d, bb=table.bb, bounty_on=table.bounty_on,
                        opponents=opponents, rng=rng, iters=iters,
                        bots=getattr(table, "bots", None))
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
