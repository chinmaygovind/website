"""What each bet size is actually worth against the five of them.

``review.py`` could always say what a bet *needed* - the break-even bluff
frequency is arithmetic - but never what one was *worth*, because that needs the
subgame after it and nobody solves a six-handed postflop tree. So a bet got its
sizing arithmetic and the verdict ``unpriced``, which is honest and is not
feedback.

This module prices it, and the reason it can is the same reason ``model``
exists at all: **every bot's strategy is a closed-form function, so its response
to a bet is a probability rather than a sample.** ``Bot.postflop_action`` rolls
``self.rng.random()`` against known expressions; ``response`` evaluates those
expressions instead of rolling them. Run over every combination in the range the
bot is on, that gives the exact fold, call and raise frequency against any size -
and, because calling is selective, the exact range the bot has *left* after
calling, which is the thing that makes a big bet worse than its fold equity
suggests.

What is being computed, stated plainly, because it is a model and not a solve:

**One street.** The hand ends at showdown after this street's action. No turn
bet, no river bluff, no implied odds. Betting the flop to set up the turn is a
real thing this cannot see, and it is the main reason the numbers here understate
small bets.
**The hero best-responds to a raise** - calls it or folds it, whichever is worth
more, knowing the raising range. That is the industry-standard reference: the
bots are not at an equilibrium, so there is no joint equilibrium for the hero to
be part of, and the well-defined quantity is the best response to what they
actually do.
**Heads-up only.** With two opponents left there is no product of independent
responses that is honest - their ranges are not independent once one of them has
called - so the multiway case is refused rather than approximated.
**Their raise size is its own average.** ``Bot._size`` jitters by a uniform 0.88
to 1.14, and this uses the mean of that, 1.01, rather than the draw.

The output is a curve, and **the curve is the point rather than its maximum**.
A model this coarse cannot tell 0.62bb from 0.58bb; it can tell that half pot
beats pot by a third of a big blind and say which of fold equity and value is
paying for it.
"""

import texture

#: The sizes offered, as fractions of the pot. The bottom is a block bet and the
#: top is an overbet, because the answer "you are betting too small" has to have
#: somewhere to point.
DEFAULT_FRACTIONS = (0.25, 0.33, 0.5, 0.66, 1.0, 1.5)

#: The mean of ``Bot._size``'s ``rng.uniform(0.88, 1.14)``.
SIZE_JITTER_MEAN = 1.01


def _clamp01(x):
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def response(bot, hole, board, to_call, pot, opponents=1, in_position=False,
             street="flop", read=None):
    """``(p_fold, p_call, p_raise, raise_to_fraction)`` facing a bet. Exact.

    A line-for-line reading of the ``to_call > 0`` branch of
    ``Bot.postflop_action``, with each ``rng.random() < x`` replaced by ``x``
    and the branch order preserved - which is the whole content of it, since an
    earlier branch takes probability away from every later one.

    ``pot`` is the pot **including** the bet being faced, as the engine reports
    it and as ``Bot.postflop_action`` expects it.

    ``test_rollout.py`` deals this against the real ``postflop_action`` a few
    thousand times per spot and fails if the frequencies drift apart. That test
    is the only thing keeping the two in step, so it is not optional.
    """
    p = bot.profile
    read = read or texture.read(hole, board)
    strength = read["strength"] or 0.0
    pressure = min(1.8, 0.60 + 0.90 * (to_call / max(pot, 1))) if to_call > 0 else 0.0
    confidence = strength ** (max(1, opponents) + pressure)
    outs = read["outs"]
    draw_equity = min(0.45, outs * (0.04 if street == "flop" else 0.02))

    aggression = p.aggression * (1.0 + 0.3 * bot.tilt)
    bluffiness = p.bluff * (1.0 + 0.35 * bot.memory.hero_folds_too_much)
    wet = read["texture"]["wetness"]

    required = to_call / (pot + to_call) if to_call > 0 else 0.0
    sticky = p.call_down * (1.0 + 0.25 * bot.tilt)
    equity = max(confidence * sticky, draw_equity + confidence * 0.30)

    r1 = _clamp01(0.45 * aggression) if confidence > 0.90 else 0.0
    p_fold = p_call = 0.0
    p_raise = r1
    raise_size = 0.75 * r1

    left = 1.0 - r1
    if equity > required:
        p_call += left
    else:
        r2 = (_clamp01(0.18 * bluffiness)
              if outs >= texture.OESD_OUTS and in_position else 0.0)
        p_raise += left * r2
        raise_size += 0.70 * left * r2
        left *= 1.0 - r2

        f = _clamp01((p.fold_to_cbet / 100.0) * (1.0 - equity))
        p_fold += left * f
        left *= 1.0 - f
        if equity > required * 0.75:
            p_call += left
        else:
            p_fold += left

    if p_raise > 0:
        base = raise_size / p_raise
        frac = base * (0.9 + 0.25 * wet) * SIZE_JITTER_MEAN
        raise_to = max(0.25, min(1.5, frac))
    else:
        raise_to = 0.0
    return p_fold, p_call, p_raise, raise_to


class Size:
    """One candidate bet, priced."""

    def __init__(self, fraction, chips, ev, fold_pct, call_pct, raise_pct,
                 equity_called, is_check=False, is_yours=False, all_in=False):
        self.fraction = fraction
        self.chips = chips
        self.ev = ev
        self.fold_pct = fold_pct
        self.call_pct = call_pct
        self.raise_pct = raise_pct
        #: Hero's equity against the part of the range that **called** - always
        #: worse than against the whole range, and by how much is the whole
        #: argument against overbetting a thin hand.
        self.equity_called = equity_called
        self.is_check = is_check
        self.is_yours = is_yours
        #: The size ran out of somebody's stack before it reached the fraction
        #: that was asked for, so ``fraction`` is what it came to rather than
        #: what was wanted.
        self.all_in = all_in

    def to_dict(self, bb):
        return {
            "fraction": None if self.is_check else round(self.fraction, 3),
            "chips": self.chips,
            "bb": round(self.chips / bb, 2),
            "ev_bb": round(self.ev / bb, 3),
            "fold_pct": round(self.fold_pct * 100, 1),
            "call_pct": round(self.call_pct * 100, 1),
            "raise_pct": round(self.raise_pct * 100, 1),
            "equity_called": (None if self.equity_called is None
                              else round(self.equity_called * 100, 1)),
            "check": self.is_check,
            "yours": self.is_yours,
            "all_in": self.all_in,
        }

    def __repr__(self):
        tag = "check" if self.is_check else f"{self.fraction:.0%}"
        return f"<{tag} {self.chips} ev={self.ev:.1f}>"


def price_bets(combos, equities, bot, pot, hero_stack, opp_stack, board,
               street="flop", hero_in_position=True, fractions=DEFAULT_FRACTIONS,
               yours=None, reads=None):
    """Every candidate size, priced in chips, plus checking it down.

    ``pot`` is what is in the middle **before** the hero bets. ``equities`` is
    ``equity.combo_equities`` over the same ``combos``, in the same order.

    Everything is measured against the same zero as ``equity.call_ev``: money
    already in the middle is not the hero's, so every number here is what the
    line is worth against giving the pot up for nothing. **Checking is one of
    the priced options rather than the baseline** - it is worth the hero's share
    of the pot it checks down, which is a real number and is usually a good one,
    and a bet has to beat it rather than beat zero.
    """
    if not combos:
        return []
    reads = reads or [texture.read([a, b], board) for a, b, _w in combos]
    weights = [w for _a, _b, w in combos]
    total_w = sum(weights) or 1.0
    equity_all = sum(e * w for e, w in zip(equities, weights)) / total_w

    out = [Size(0.0, 0, equity_all * pot, 0.0, 0.0, 0.0, equity_all,
                is_check=True)]

    wanted = list(fractions)
    if yours is not None and yours > 0 and pot > 0:
        mine = yours / pot
        if all(abs(mine - f) > 0.02 for f in wanted):
            wanted.append(mine)
        wanted.sort()

    # A size that ran out of chips is not a distinct size. Short-stacked, every
    # fraction from a third up clamps to the same all-in, and printing them as
    # six rows with six labels and one identical EV is a curve that says nothing
    # six times. The label becomes what the bet actually came to, because
    # "150% of the pot" on a bet of 30% of it is simply false.
    seen = set()
    for frac in wanted:
        bet = min(int(round(frac * pot)), hero_stack, opp_stack)
        if bet <= 0 or bet in seen:
            continue
        seen.add(bet)
        all_in = bet >= min(hero_stack, opp_stack)
        if all_in:
            frac = bet / pot
        ev = 0.0
        w_fold = w_call = w_raise = 0.0
        called_eq = called_w = 0.0
        for (a, b, w), e, read in zip(combos, equities, reads):
            pf, pc, pr, rto = response(
                bot, [a, b], board, to_call=bet, pot=pot + bet, opponents=1,
                in_position=not hero_in_position, street=street, read=read)
            if opp_stack <= bet:
                pc, pr = pc + pr, 0.0
            w_fold += w * pf
            w_call += w * pc
            w_raise += w * pr
            called_eq += w * pc * e
            called_w += w * pc

            ev_c = pf * pot
            ev_c += pc * (e * (pot + bet) - (1 - e) * bet)
            if pr > 0:
                # What they raise to, capped by their stack; what the hero can
                # actually call, capped by the hero's. Calling all-in for less
                # than they raised leaves the excess uncontested, so the pot the
                # hero is playing for is twice the hero's own total and no more.
                to = max(bet + 1, min(bet + int(round(rto * (pot + bet))), opp_stack))
                total = bet + min(to - bet, max(0, hero_stack - bet))
                calling = e * (pot + total) - (1 - e) * total
                ev_c += pr * max(-bet, calling)
            ev += w * ev_c
        out.append(Size(
            frac, bet, ev / total_w, w_fold / total_w, w_call / total_w,
            w_raise / total_w,
            called_eq / called_w if called_w > 0 else None, all_in=all_in))

    # The size actually chosen is marked by being the nearest one on the curve
    # rather than by matching a tolerance. A tolerance has to agree with the one
    # that decided whether to insert the exact fraction in the first place, and
    # when the two disagreed - a 30% bet is within 0.04 of the offered 33%, and
    # 3% of the pot is outside pot/50 - the curve came out with nothing marked
    # on it and the whole line was dropped. Two thirds of them, silently.
    if yours is not None and yours > 0:
        bets = [s for s in out if not s.is_check]
        if bets:
            min(bets, key=lambda s: abs(s.chips - yours)).is_yours = True
    return out
