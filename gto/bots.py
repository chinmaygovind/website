"""How the five of them actually decide.

A bot's range is built from two things: **the chart** for the spot, and **its own
taste**, blended by ``discipline``. At discipline 1.0 you get the chart. At 0.0
you get whatever that person finds attractive. Everyone here is somewhere in
between, and where they are is what makes them them.

The width is set separately by ``vpip``. Two axes, and they do not interact:
Ronit is narrow and well chosen, Sanjay is wide and badly chosen, Bell is a bit
wide and moderately chosen. Scaling one player's range would never produce
another player, which is the point.

**These brains never score you.** The review's numbers come from ``ranges.py``,
``equity.py`` and the solver; this file only supplies opponents to play against
and a description of what they did. If a bot's opinion fed the grade, the
trainer would be marking its own homework.

**Where a chart does not exist, the nearest chart is stretched rather than a
number invented.** Limped pots and multiway spots are not solved anywhere, so a
bot facing three limpers plays its opening chart widened by a stated factor.
That is openly a fudge - but it is a fudge over a real equilibrium range rather
than a made-up ordering, and it only ever decides what a bot does, never what
you are told.
"""

import random

import profiles
import ranges
import texture
from cards import hole_class

#: Nobody plays the same range twice. Hands near the edge of a bot's range are
#: taken some of the time rather than always, over a band this wide in combos -
#: which is both more human and, by accident, closer to a mixed strategy than a
#: hard cutoff would be.
EDGE_BAND = 0.16

#: Uncharted preflop nodes, and what is stretched to cover them. The number is a
#: multiplier on the bot's target width, not on the chart.
LIMPED_POT_WIDEN = 1.45
MULTIWAY_TIGHTEN = 0.80

#: **VPIP is a whole-session average, not a per-position number**, and forgetting
#: that produces bots that open as many hands under the gun as on the button.
#: A 19/16 nit opens about 12% first in and about 31% on the button; both of
#: those average out to 19.
#:
#: The shape comes from the charts themselves rather than from a table typed in
#: here, so it cannot drift away from them: each position's factor is that
#: position's chart width over the mean chart width.
POSITION_FACTOR = {}


def _build_position_factors():
    widths = {
        pos: ranges.lookup(("rfi",), pos).actions["raise"].pct()
        for pos in ("UTG", "HJ", "CO", "BTN")
    }
    mean = sum(widths.values()) / len(widths)
    POSITION_FACTOR.update({p: w / mean for p, w in widths.items()})
    POSITION_FACTOR["SB"] = 1.0
    POSITION_FACTOR["BB"] = 1.0


_build_position_factors()

#: How much of that positional spread a player actually has. **Position
#: awareness is a skill**, and the people who lack it are the same people who
#: play too many hands - a maniac plays nearly as many under the gun as on the
#: button, which is most of why it costs him. So the spread is scaled by
#: discipline rather than applied flat.
def _position_width(profile, pos):
    factor = POSITION_FACTOR.get(pos, 1.0)
    spread = 0.35 + 0.65 * profile.discipline
    return profile.vpip * (1.0 + (factor - 1.0) * spread)


#: The chart player's own VPIP - what "playing correctly" scores on the same
#: measure the profiles use. A profile's ``vpip`` over this is how much looser
#: than correct that person defends. Calibrated by measurement, not arithmetic:
#: ``test_bots.py`` deals thousands of hands and checks each bot's observed VPIP
#: lands near the number on its profile, which is the only way this constant
#: means anything.
BASELINE_VPIP = 26.0


#: Played by everybody, at every width, whatever their taste. This is a floor on
#: the model rather than a trait: a blend that demotes aces because a pair scores
#: no "suited" and no "connected" points has gone wrong, and no amount of tuning
#: the weights makes that safe at every range width. Twenty-four combinations,
#: 1.8% of hands, so it never meaningfully distorts even the tightest bot.
PREMIUM = frozenset({"AA", "KK", "QQ", "AKs"})


def _preference(chart, taste, discipline):
    """Score every class by how much this player wants to play it."""
    raw = {c: profiles.taste_score(c, taste) for c in ranges.CLASSES}
    lo, hi = min(raw.values()), max(raw.values())
    span = (hi - lo) or 1.0
    out = {}
    for c in ranges.CLASSES:
        liking = (raw[c] - lo) / span
        correct = chart.weight(c) if chart is not None else 0.0
        score = discipline * correct + (1.0 - discipline) * liking
        if c in PREMIUM:
            score += 1.0
        out[c] = score
    return out


def _take_top(preference, target_pct, band=EDGE_BAND):
    """The top ``target_pct`` of hands by preference, with a soft edge."""
    target = ranges.TOTAL_COMBOS * target_pct / 100.0
    width = ranges.TOTAL_COMBOS * band
    order = sorted(ranges.CLASSES, key=lambda c: (-preference[c], c))

    out, seen = {}, 0.0
    for c in order:
        n = ranges.combos_of(c)
        middle = seen + n / 2.0
        if middle <= target - width / 2:
            w = 1.0
        elif middle >= target + width / 2:
            w = 0.0
        else:
            w = (target + width / 2 - middle) / width
        if w > 0.001:
            out[c] = round(min(1.0, w), 4)
        seen += n
    return ranges.Range(out)


class Memory:
    """What a bot has noticed about the hero, and what it does about it.

    Counts only. The adjustment is derived on read, so the settings panel can
    show both the observation and the adaptation it caused - which is what makes
    "Ronit has started three-betting you because you folded the last six" a line
    the review can print rather than a thing that silently happens.
    """

    #: Below this many observations a bot has not seen enough to change anything.
    MIN_SAMPLE = 8

    def __init__(self):
        self.hero_cbet_faced = 0
        self.hero_cbet_folded = 0
        self.hero_opens = 0
        self.hero_hands = 0
        self.hero_showdowns = 0
        self.hero_showdown_strong = 0

    def saw_cbet(self, folded):
        self.hero_cbet_faced += 1
        self.hero_cbet_folded += bool(folded)

    def saw_hand(self, entered):
        self.hero_hands += 1
        self.hero_opens += bool(entered)

    def saw_showdown(self, strong):
        self.hero_showdowns += 1
        self.hero_showdown_strong += bool(strong)

    @property
    def hero_folds_too_much(self):
        """A number in -1..1: positive means bluff into them more."""
        if self.hero_cbet_faced < self.MIN_SAMPLE:
            return 0.0
        rate = self.hero_cbet_folded / self.hero_cbet_faced
        return max(-1.0, min(1.0, (rate - 0.50) / 0.25))

    @property
    def hero_plays_too_many(self):
        if self.hero_hands < self.MIN_SAMPLE * 2:
            return 0.0
        rate = self.hero_opens / self.hero_hands
        return max(-1.0, min(1.0, (rate - 0.28) / 0.20))

    def notes(self):
        """Human-readable adaptations, for the review to surface."""
        out = []
        if self.hero_folds_too_much > 0.3:
            out.append("has noticed you fold to continuation bets and is betting more")
        elif self.hero_folds_too_much < -0.3:
            out.append("has noticed you do not fold and has stopped bluffing you")
        if self.hero_plays_too_many > 0.3:
            out.append("has noticed you play a lot of hands and is widening back at you")
        elif self.hero_plays_too_many < -0.3:
            out.append("has noticed you are tight and is giving your bets more credit")
        return out

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        m = cls()
        m.__dict__.update(d)
        return m


class Bot:
    """One seat's decision maker. Stateless between hands except for ``memory``."""

    def __init__(self, profile, rng=None, memory=None):
        self.profile = profile
        self.rng = rng or random.Random()
        self.memory = memory or Memory()
        #: Rises when they lose a big pot, decays every hand. Widens their range
        #: and their aggression, by ``tilt_effect``.
        self.tilt = 0.0

    # ------------------------------------------------------------- tilting

    TILT_RATE = {"fast": 0.55, "med": 0.32, "slow": 0.18, "none": 0.04}

    def lost_pot(self, bb_lost, bb_stack):
        """Told after a hand. A big loss tilts; the size of "big" is relative."""
        if bb_lost <= 0 or bb_stack <= 0:
            return
        hurt = min(1.0, bb_lost / max(20.0, bb_stack * 0.4))
        self.tilt = min(1.0, self.tilt + hurt * self.TILT_RATE[self.profile.tilt_speed])

    def hand_over(self):
        self.tilt *= 0.82

    @property
    def _tilt_widen(self):
        return 1.0 + self.tilt * self.profile.tilt_effect

    # ------------------------------------------------------------ preflop

    def preflop_range(self, node, pos, seats=6, depth_bb=200.0, limpers=0,
                      entrants=0):
        """This player's actual range for a spot, chart blended with taste."""
        p = self.profile
        chart = None
        try:
            chart = ranges.lookup(node, pos, seats=seats, depth_bb=depth_bb)
        except ValueError:
            chart = None

        if chart is not None:
            backbone = ranges.Range({
                c: sum(r.weight(c) for r in chart.actions.values())
                for c in ranges.CLASSES
            })
        else:
            backbone = None

        if node[0] == "rfi":
            width = _position_width(p, pos)
        elif backbone is not None:
            # Defending is charted, so the chart sets the width and the profile
            # only says how much looser than correct this person is.
            #
            # The exponent is above one because **looseness is not linear in
            # defence**. A nit is not a solid player scaled down by a quarter;
            # he folds his big blind far more than that, which is most of why
            # his PFR-to-VPIP ratio is so high - almost everything he plays, he
            # raised. At an exponent of 1.0 the tight bots flatted so much that
            # their measured PFR came out at two thirds of their profile.
            #
            # It is not symmetric. Applying the same exponent upwards sent a
            # stated 58 VPIP to a measured 67, because a player who is already
            # defending most hands has nowhere left to widen to.
            ratio = p.vpip / BASELINE_VPIP
            width = backbone.pct() * (ratio ** 1.35 if ratio < 1 else ratio ** 0.85)
        else:
            width = _position_width(p, pos)

        width *= self._tilt_widen
        if limpers:
            width *= LIMPED_POT_WIDEN
        if entrants > 1:
            width *= MULTIWAY_TIGHTEN ** (entrants - 1)
        width *= 1.0 + 0.12 * self.memory.hero_plays_too_many
        width = max(3.0, min(94.0, width))

        return _take_top(_preference(backbone, p.taste, p.discipline), width)

    def preflop_action(self, node, pos, hole, to_call, pot, stack, seats=6,
                       depth_bb=200.0, limpers=0, entrants=0, streak=0):
        """``("fold"|"check"|"call"|"raise", None)``.

        ``entrants`` is how many opponents have **voluntarily put money in**, not
        how many were dealt cards. Passing the latter tightened every preflop
        range by ``MULTIWAY_TIGHTEN ** 4`` before anybody had done anything,
        which took a stated 58% VPIP down to a measured 47%.

        The entry roll happens **once**, and so does the raise roll. An earlier
        version rolled the raise twice - once to reject calling and once to
        accept raising - which quietly squared the raise frequency and put every
        bot's PFR at about half its profile.
        """
        p = self.profile
        cls = hole_class(hole)
        unopened = node[0] in ("rfi", "limped")
        lookup_node = node if node[0] in ("rfi", "vs_rfi", "vs_3bet") else ("rfi",)
        played = self.preflop_range(lookup_node, pos, seats, depth_bb, limpers,
                                    entrants)
        want = played.weight(cls)

        # The bounty makes a streak worth defending. A player two hands into one
        # plays a bit more, exactly as they do in the real game.
        if streak >= 2:
            want = min(1.0, want * (1.0 + 0.10 * min(streak, 4)))

        if self.rng.random() >= want:
            return ("fold", None) if to_call > 0 else ("check", None)

        p_raise = self._raise_share(node, played, cls, unopened)
        if self.rng.random() < p_raise:
            return ("raise", None)
        return ("call", None) if to_call > 0 else ("check", None)

    def _raise_share(self, node, played, cls, unopened):
        """How often this hand comes in raising rather than calling."""
        p = self.profile
        if unopened:
            # Everything you play, you raise - except the part you limp. Limping
            # is a home-game fact and the loose profiles do a lot of it.
            base = 1.0 - p.limp / 100.0
        elif node[0] == "vs_rfi":
            # Three-bet frequency is measured against hands *faced*, and the
            # continuing range is what it is drawn from.
            width = max(played.pct(), 1.0)
            base = min(1.0, p.three_bet / width)
        elif node[0] == "vs_3bet":
            base = 0.24
        else:
            base = 0.30

        # Strong hands raise more than the middle of the range does - but how
        # much more depends on whether there is a raise in front.
        #
        # Facing one, the choice between three-betting and flatting really is
        # strength driven, so the spread is wide. **Unopened it is not.** A nit
        # with a 2% limp rate does not limp the bottom of his opening range; he
        # raises it or he folds it. A spread that wide on an unopened pot turned
        # four in ten of Ronit's opens into limps and put his measured PFR three
        # points under his profile. So the unopened modulation is centred on one
        # and narrow: it tilts which hands raise, never how many.
        strength = 1.0 - self._rank_within(played, cls)
        spread = (0.85, 0.30) if unopened else (0.60, 0.80)
        share = base * (spread[0] + spread[1] * strength)
        return max(0.0, min(1.0, share * (1.0 + 0.25 * self.tilt)))

    def range_after(self, node, pos, action, seats=6, depth_bb=200.0,
                    limpers=0, entrants=0, streak=0):
        """The range this bot is on, having taken ``action`` at this node.

        **Exact, not estimated.** A bot's preflop strategy is a known function -
        a probability of entering per hand class and a probability of raising
        given entry - so Bayes gives the posterior directly. There is no
        sampling and no guessing involved, which is why the review is allowed to
        say "Ronit has 7.2% of hands here" and mean it.

        What it does *not* say is that Ronit is right to have that range. This
        is what the model of Ronit does, labelled as such.
        """
        unopened = node[0] in ("rfi", "limped")
        lookup_node = node if node[0] in ("rfi", "vs_rfi", "vs_3bet") else ("rfi",)
        played = self.preflop_range(lookup_node, pos, seats, depth_bb, limpers,
                                    entrants)

        out = {}
        for cls in ranges.CLASSES:
            enter = played.weight(cls)
            if streak >= 2:
                enter = min(1.0, enter * (1.0 + 0.10 * min(streak, 4)))
            if action == "fold":
                out[cls] = 1.0 - enter
                continue
            if enter <= 0.0:
                continue
            raise_p = self._raise_share(node, played, cls, unopened)
            out[cls] = enter * (raise_p if action == "raise" else 1.0 - raise_p)

        total = sum(w * ranges.combos_of(c) for c, w in out.items())
        if total <= 0:
            return ranges.Range({})
        return ranges.Range({c: w for c, w in out.items() if w > 1e-9})

    def _rank_within(self, played, cls):
        """0 for the best hand in the range, 1 for the worst. Cheap and stable."""
        if cls not in played:
            return 1.0
        order = sorted(played, key=lambda c: (-played[c], c))
        return order.index(cls) / max(1, len(order) - 1)

    # ----------------------------------------------------------- postflop

    def postflop_action(self, hole, board, to_call, pot, stack, opponents,
                        in_position, is_aggressor, street):
        """``("fold"|"check"|"call"|"bet"|"raise", fraction_of_pot_or_None)``."""
        p = self.profile
        read = texture.read(hole, board)
        strength = read["strength"] or 0.0

        # ``strength`` is measured against a *random* holding, and the player who
        # just bet does not have a random holding. Raising it to a power is the
        # right shape for that correction: it barely touches a hand that beats
        # nearly everything and it guts a hand that beats slightly more than
        # half, which is exactly the difference between a set and ace high.
        #
        # Two things push the exponent up. Every extra opponent is another hand
        # to be better than. And the **size of the bet faced** says how much
        # stronger than random the bettor's range is - without this term the
        # bots called two-thirds pot with ace-high on a king-high board more
        # than half the time, because ace-high does beat most random hands.
        pressure = 0.0
        if to_call > 0:
            pressure = min(1.8, 0.60 + 0.90 * (to_call / max(pot, 1)))
        confidence = strength ** (max(1, opponents) + pressure)
        outs = read["outs"]
        # Two per out per street to come is the standard shorthand and is close
        # enough for a bot; the review never uses it.
        draw_equity = min(0.45, outs * (0.04 if street == "flop" else 0.02))

        aggression = p.aggression * (1.0 + 0.3 * self.tilt)
        bluffiness = p.bluff * (1.0 + 0.35 * self.memory.hero_folds_too_much)
        wet = read["texture"]["wetness"]

        if to_call > 0:
            required = to_call / (pot + to_call)
            sticky = p.call_down * (1.0 + 0.25 * self.tilt)

            # ``call_down`` is a willingness to **bluff-catch**, and it belongs
            # only on the made-hand half. A nit is not bad at pot odds - he is
            # reluctant to pay somebody off with one pair. Applying his 0.70 to
            # a fifteen-out draw as well had him folding a combo draw getting
            # three to one, which is not tight, it is broken.
            equity = max(confidence * sticky, draw_equity + confidence * 0.30)

            if confidence > 0.90 and self.rng.random() < 0.45 * aggression:
                return ("raise", self._size(0.75, wet))
            if equity > required:
                return ("call", None)
            # Bluff-raising: rare, and rarer out of position.
            if (outs >= texture.OESD_OUTS and in_position
                    and self.rng.random() < 0.18 * bluffiness):
                return ("raise", self._size(0.7, wet))
            fold_pull = p.fold_to_cbet / 100.0
            if self.rng.random() < fold_pull * (1.0 - equity):
                return ("fold", None)
            return ("call", None) if equity > required * 0.75 else ("fold", None)

        # Nobody has bet.
        if confidence > 0.82:
            size = self._size(0.66 if wet < 0.5 else 0.8, wet)
            return ("bet", size) if self.rng.random() < 0.85 * aggression else ("check", None)

        cbet_rate = p.cbet / 100.0 if is_aggressor else p.cbet / 160.0
        cbet_rate *= 1.0 + 0.30 * self.memory.hero_folds_too_much
        cbet_rate *= 1.0 - 0.25 * (opponents - 1)
        cbet_rate *= 0.85 + 0.4 * in_position

        semi = outs >= texture.GUTSHOT_OUTS
        chance = cbet_rate * (1.15 if semi else bluffiness * 0.9)
        if self.rng.random() < max(0.0, chance):
            return ("bet", self._size(0.5 if wet > 0.6 else 0.6, wet))
        return ("check", None)

    def _size(self, base, wetness):
        """Bet size as a fraction of the pot, jittered so it is not a tell."""
        size = base * (0.9 + 0.25 * wetness)
        return round(max(0.25, min(1.5, size * self.rng.uniform(0.88, 1.14))), 3)

    # ------------------------------------------------------------- timing

    def think_time(self, close):
        """Seconds before this bot acts. ``close`` marks a genuinely hard spot."""
        t = self.profile.timing
        if close and self.rng.random() < t["tank"]:
            return self.rng.uniform(t["slow"] * 0.6, t["slow"])
        return self.rng.uniform(t["fast"] * 0.45, t["fast"] * 1.35)
