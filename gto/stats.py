"""What you are actually winning, and how sure anybody can be about it.

The headline number is dollars an hour. It is also, over any session you will
ever play, **mostly noise**, and a trainer that prints it without saying so is
lying by omission. So every rate here comes with a 95% interval, and the
interval is usually embarrassing - which is the point. A 20bb/100 win rate over
600 hands has a confidence interval about 60bb/100 wide. You cannot tell a
winning player from a losing one in an evening, and knowing that is worth more
than the number.

The interval is a **t** interval, not a normal one, because the variance is
estimated from the same few hands the mean is. And it is still optimistic: hand
results are not normally distributed - they are a spike at minus one big blind
with a long right tail - so the true interval over a short session is wider
than this says, never narrower. It is the floor on how little you know.

**Two numbers, and the second one is better.**

*Observed* is what happened: chips won over hands played. It is what you would
see in a real session and it is what the interval is computed on.

*EV-adjusted* replaces the outcome of every all-in with its equity. If you get
it in with 80% and lose, observed says you lost the pot and EV-adjusted says you
won 80% of it. Over a few hundred hands that removes most of the variance that
has nothing to do with how you played, so it converges perhaps three times
faster. It is the number to look at, and it is the one the headline uses.

**The bounty is counted separately**, because it is not poker and because at
0.25/0.25 it is large enough to swamp the poker if it is not. A session can be
up on bounties and down on cards, and that is worth being able to see.
"""

import math

#: Hands an hour in a live home game. Six-handed with people talking, it is
#: nearer 25 than the 60-80 an online table runs.
HANDS_PER_HOUR = 27.0

#: 1.96 standard errors is the 95% interval - **for a known variance**, which
#: over a few dozen hands is exactly what nobody has.
Z95 = 1.959964

#: Two-sided 95% critical values of Student's t, by degrees of freedom. The
#: variance here is estimated from the same handful of hands the mean is, and
#: using 1.96 anyway makes the interval too narrow by 42% at ten hands and 5%
#: at twenty-five - which is the difference between "this does not yet say
#: whether you are winning" and a confident number. That is the one error this
#: module exists to avoid, so it is worth a lookup table.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 50: 2.009,
    60: 2.000, 80: 1.990, 100: 1.984, 120: 1.980,
}


def t95(df):
    """The two-sided 95% critical value at ``df`` degrees of freedom.

    Exact from the table where it has an entry, and the Cornish-Fisher
    expansion of the t quantile in between and beyond - which is within a
    thousandth of the true value everywhere past df 30, and converges on 1.96
    as the sample grows, which is the right thing for it to do.
    """
    if df <= 0:
        return float("inf")
    if df in _T95:
        return _T95[df]
    if df > 120:
        z = Z95
        return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)
    lo = max(k for k in _T95 if k < df)
    hi = min(k for k in _T95 if k > df)
    span = (df - lo) / (hi - lo)
    return _T95[lo] + span * (_T95[hi] - _T95[lo])


class Running:
    """One session's totals, updated a hand at a time."""

    def __init__(self, bb_cents=25, bb_dollars=0.25):
        self.bb_cents = bb_cents
        self.bb_dollars = bb_dollars
        self.hands = 0
        self.results = []       # chips won or lost per hand, cents
        self.ev_results = []    # the same, with all-ins replaced by their equity
        self.bounty_cents = 0

        self.vpip = 0
        self.pfr = 0
        self.three_bet = 0
        self.three_bet_chances = 0
        self.saw_flop = 0
        self.went_to_showdown = 0
        self.won_at_showdown = 0
        self.pots_won = 0

        self.decisions = 0
        self.errors = 0
        self.error_bb = 0.0
        self.exploits = 0
        self.by_opponent = {}

    # ------------------------------------------------------------- recording

    def add_hand(self, result_cents, ev_cents=None, bounty_cents=0,
                 vpip=False, pfr=False, three_bet=False, three_bet_chance=False,
                 saw_flop=False, showdown=False, won_showdown=False, won=False):
        self.hands += 1
        self.results.append(result_cents)
        self.ev_results.append(result_cents if ev_cents is None else ev_cents)
        self.bounty_cents += bounty_cents
        self.vpip += bool(vpip)
        self.pfr += bool(pfr)
        self.three_bet += bool(three_bet)
        self.three_bet_chances += bool(three_bet_chance)
        self.saw_flop += bool(saw_flop)
        self.went_to_showdown += bool(showdown)
        self.won_at_showdown += bool(won_showdown)
        self.pots_won += bool(won)

    def add_review(self, decision_review, opponent=None):
        self.decisions += 1
        if decision_review.verdict == "error":
            self.errors += 1
            self.error_bb += decision_review.loss_bb or 0.0
        elif decision_review.verdict == "exploit":
            self.exploits += 1
        if opponent:
            slot = self.by_opponent.setdefault(
                opponent, {"decisions": 0, "errors": 0, "lost_bb": 0.0})
            slot["decisions"] += 1
            if decision_review.verdict == "error":
                slot["errors"] += 1
                slot["lost_bb"] += decision_review.loss_bb or 0.0

    # -------------------------------------------------------------- rates

    def _bb(self, results):
        return [r / self.bb_cents for r in results]

    def rate(self, ev_adjusted=True):
        """``(bb/100, half-width of the 95% interval)``. ``None`` before it means anything."""
        series = self._bb(self.ev_results if ev_adjusted else self.results)
        n = len(series)
        if n < 2:
            return None
        mean = sum(series) / n
        var = sum((x - mean) ** 2 for x in series) / (n - 1)
        se = math.sqrt(var / n)
        return (mean * 100.0, t95(n - 1) * se * 100.0)

    def hourly(self, ev_adjusted=True, hands_per_hour=HANDS_PER_HOUR):
        """``(dollars/hour, half-width)``, poker only - the bounty is separate."""
        r = self.rate(ev_adjusted)
        if r is None:
            return None
        per_hand_bb, half = r[0] / 100.0, r[1] / 100.0
        money = per_hand_bb * self.bb_dollars * hands_per_hour
        return (money, half * self.bb_dollars * hands_per_hour)

    def per_hand(self, ev_adjusted=True):
        r = self.rate(ev_adjusted)
        if r is None:
            return None
        return (r[0] / 100.0 * self.bb_dollars, r[1] / 100.0 * self.bb_dollars)

    def bounty_hourly(self, hands_per_hour=HANDS_PER_HOUR):
        if not self.hands:
            return 0.0
        return (self.bounty_cents / 100.0) / self.hands * hands_per_hour

    def hands_needed(self, target_half_bb100=10.0):
        """How many hands before the interval is this narrow. Usually a shock.

        Standard error falls with the square root of hands, so halving the width
        costs four times the hands. This is the number that tells somebody why
        they cannot know whether tonight went well.
        """
        r = self.rate(True)
        if r is None or self.hands < 30 or r[1] <= 0:
            return None
        return int(self.hands * (r[1] / target_half_bb100) ** 2)

    # ---------------------------------------------------------------- HUD

    def _pct(self, top, bottom):
        return None if not bottom else 100.0 * top / bottom

    def summary(self):
        rate = self.rate(True)
        raw = self.rate(False)
        hourly = self.hourly(True)
        return {
            "hands": self.hands,
            "vpip": self._pct(self.vpip, self.hands),
            "pfr": self._pct(self.pfr, self.hands),
            "three_bet": self._pct(self.three_bet, self.three_bet_chances),
            "saw_flop": self._pct(self.saw_flop, self.hands),
            "wtsd": self._pct(self.went_to_showdown, self.saw_flop),
            "wsd": self._pct(self.won_at_showdown, self.went_to_showdown),
            "won": self._pct(self.pots_won, self.hands),
            "bb100": None if rate is None else round(rate[0], 1),
            "bb100_ci": None if rate is None else round(rate[1], 1),
            "bb100_observed": None if raw is None else round(raw[0], 1),
            "hourly": None if hourly is None else round(hourly[0], 2),
            "hourly_ci": None if hourly is None else round(hourly[1], 2),
            "bounty_total": round(self.bounty_cents / 100.0, 2),
            "bounty_hourly": round(self.bounty_hourly(), 2),
            "decisions": self.decisions,
            "errors": self.errors,
            "error_rate": self._pct(self.errors, self.decisions),
            "error_bb": round(self.error_bb, 1),
            "exploits": self.exploits,
            "hands_for_10bb100": self.hands_needed(10.0),
            "by_opponent": self.by_opponent,
        }

    def headline(self):
        """The sentence at the top of the stats page, hedged exactly as much as
        the sample deserves."""
        h = self.hourly(True)
        if h is None or self.hands < 25:
            return (f"{self.hands} hands so far - far too few to say anything "
                    f"about a win rate.")
        money, half = h
        if half > abs(money):
            return (f"${money:+.2f}/hour, give or take ${half:.2f}. That "
                    f"interval covers zero, so after {self.hands} hands this "
                    f"does not yet say whether you are winning.")
        return (f"${money:+.2f}/hour, give or take ${half:.2f}, over "
                f"{self.hands} hands.")

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d):
        s = cls(d.get("bb_cents", 25), d.get("bb_dollars", 0.25))
        s.__dict__.update(d)
        return s
