"""The people at the table.

A bot is described by **two independent numbers**, and keeping them independent
is the whole idea:

*how wide* they play
    ``vpip`` and the frequencies around it. This is the easy axis and the one
    every poker bot has.

*how well chosen* the wide part is
    ``discipline``. At 1.0 a player who plays 30% of hands plays the *best* 30%
    - the chart's 30%. At 0.0 they play the 30% they find attractive.

Those are different failings and the people they describe are different people.
Ronit playing 19% disciplined and Sanjay playing 58% undisciplined are not the
same player scaled; they are wrong in unrelated directions, and a review that
says "Sanjay called your river bet with third pair" has to come from a bot that
would actually do that.

**Humans do not widen along the EV gradient.** Asked to play more hands, nobody
adds the next-best hand by expected value - they add another ace, another suited
thing, another two-picture-card hand, because those are the hands that *look*
like hands. That is what ``taste`` encodes, and it is why the loose bots here
lose money in a recognisable way rather than a random one.

**The photographs are not in this repo.** The five friends are real people and
the repo is public, so ``gto/avatars/`` is gitignored and prod serves the files
from ``/home/ubuntu/gto-avatars`` to a logged-in owner only - the same reasoning,
and the same shape, as ``accounts/``'s ``AVATAR_DIR``. Anyone not signed in as
Chinmay gets ``STRANGERS`` below: the same six poker personalities with invented
names and drawn initials. The tendencies are public; the people are not.
"""

import copy

from cards import RANKS

_RI = {r: i for i, r in enumerate(RANKS)}


# ------------------------------------------------------------------- taste


def features(cls):
    """What a human notices about a starting hand, as numbers in 0..1.

    Not what makes it good - what makes it *look* good. That gap is the model.
    """
    if len(cls) == 2:
        r = _RI[cls[0]]
        return {
            "pair": 1.0, "pair_rank": r / 12.0, "ace": 0.0, "suited": 0.0,
            "connected": 0.0, "broadway": 0.0, "high": r / 12.0, "gap": 0.0,
        }
    hi, lo, suited = _RI[cls[0]], _RI[cls[1]], cls.endswith("s")
    gap = hi - lo - 1
    broadway = sum(1 for r in (hi, lo) if r >= 8) / 2.0  # ten or better
    return {
        "pair": 0.0,
        "pair_rank": 0.0,
        "ace": 1.0 if hi == 12 else 0.0,
        "suited": 1.0 if suited else 0.0,
        "connected": max(0.0, 1.0 - gap / 4.0),
        "broadway": broadway,
        "high": hi / 12.0,
        "gap": min(gap, 8) / 8.0,
    }


#: What an average recreational player finds attractive. A profile's ``taste``
#: is this with its own overrides laid on top.
#: ``pair`` is large because a pair earns nothing from any of the other
#: features - no suit, no connectedness, no broadway - so a weight in line with
#: them silently ranks **aces below a suited ace**. At the widths the loose bots
#: play that is invisible; at a nit's 13% opening range it put AA in the soft
#: edge of the range and folded it one time in ten.
BASE_TASTE = {
    "pair": 1.80,
    "pair_rank": 1.00,
    "ace": 0.85,
    "suited": 0.70,
    "connected": 0.45,
    "broadway": 0.75,
    "high": 0.60,
    "gap": -0.35,
}


def taste_score(cls, taste):
    f = features(cls)
    return sum(f[k] * taste.get(k, 0.0) for k in f)


# ----------------------------------------------------------------- profiles


class Profile:
    """One player's tendencies. Every number is live-tunable from the gear menu.

    Frequencies are percentages, because that is how they are read in a HUD and
    how they are shown in the settings panel. ``bots.py`` converts.
    """

    FIELDS = (
        "vpip", "pfr", "three_bet", "fold_to_three_bet", "cbet", "fold_to_cbet",
        "wtsd", "aggression", "bluff", "limp", "squeeze", "call_down",
        "discipline", "tilt_speed", "tilt_effect",
    )

    def __init__(self, key, name, blurb, taste=None, **kw):
        self.key = key
        self.name = name
        self.blurb = blurb
        self.taste = dict(BASE_TASTE, **(taste or {}))
        for f in self.FIELDS:
            setattr(self, f, kw.pop(f))
        self.timing = kw.pop("timing")
        self.avatar = kw.pop("avatar", f"{key}.jpg")
        if kw:
            raise ValueError(f"{key}: unknown profile fields {sorted(kw)}")
        self._check()

    def _check(self):
        if not 0 <= self.pfr <= self.vpip:
            raise ValueError(
                f"{self.key}: pfr {self.pfr} must be between 0 and vpip {self.vpip} - "
                "a player cannot raise more hands than they play"
            )
        for f in ("vpip", "pfr", "three_bet", "fold_to_three_bet", "cbet",
                  "fold_to_cbet", "wtsd", "limp", "squeeze"):
            if not 0 <= getattr(self, f) <= 100:
                raise ValueError(f"{self.key}: {f} is a percentage")
        for f in ("aggression", "bluff", "call_down", "discipline", "tilt_effect"):
            if not 0.0 <= getattr(self, f) <= 2.0:
                raise ValueError(f"{self.key}: {f} out of range")

    def copy(self):
        return copy.deepcopy(self)

    def to_dict(self):
        d = {f: getattr(self, f) for f in self.FIELDS}
        d.update(key=self.key, name=self.name, blurb=self.blurb,
                 avatar=self.avatar, timing=dict(self.timing), taste=dict(self.taste))
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        return cls(d.pop("key"), d.pop("name"), d.pop("blurb"), **d)

    def __repr__(self):
        return f"<Profile {self.name} {self.vpip:.0f}/{self.pfr:.0f}>"


#: How long a decision takes, in seconds. ``tank`` is the chance of a long think
#: on a close spot, which is most of what makes a bot feel like a person: a table
#: where everybody answers in 1.2s reads as a table of robots however well they
#: play.
def timing(fast, slow, tank):
    return {"fast": fast, "slow": slow, "tank": tank}


FRIENDS = [
    Profile(
        "ronit", "Ronit Kapoor",
        "Nit. Plays a tight, aggressive, close-to-solver game and does not "
        "bluff-catch. Beat him by folding when he finally bets big.",
        vpip=16, pfr=16, three_bet=7, fold_to_three_bet=62, cbet=58,
        fold_to_cbet=52, wtsd=26, aggression=1.15, bluff=0.75, limp=2,
        squeeze=7, call_down=0.70, discipline=0.88,
        tilt_speed="fast", tilt_effect=0.55,
        taste={"gap": -0.55, "connected": 0.35, "broadway": 0.60},
        timing=timing(1.1, 4.5, 0.18),
    ),
    Profile(
        "aarav", "Aarav Mullinti",
        "The other nit, and the better of the two. Slightly wider than Ronit "
        "and much more willing to three-bet you light in position.",
        vpip=19, pfr=18, three_bet=9, fold_to_three_bet=57, cbet=64,
        fold_to_cbet=48, wtsd=25, aggression=1.30, bluff=0.95, limp=1,
        squeeze=9, call_down=0.72, discipline=0.90,
        tilt_speed="fast", tilt_effect=0.45,
        taste={"gap": -0.50, "connected": 0.50, "suited": 0.80},
        timing=timing(1.0, 4.0, 0.16),
    ),
    Profile(
        "bell", "Bell",
        "Solid casual. Plays a few too many hands and calls a street too far, "
        "but rarely does anything stupid. Takes his time.",
        vpip=26, pfr=19, three_bet=5, fold_to_three_bet=52, cbet=55,
        fold_to_cbet=58, wtsd=31, aggression=0.85, bluff=0.65, limp=12,
        squeeze=4, call_down=1.05, discipline=0.62,
        tilt_speed="slow", tilt_effect=0.30,
        taste={"suited": 0.85, "broadway": 0.90, "ace": 0.95},
        timing=timing(2.4, 9.0, 0.30),
    ),
    Profile(
        "apurva", "Apurva",
        "Casual but sharp. Similar width to Bell with more aggression and a "
        "better feel for when a board has missed everybody.",
        vpip=25, pfr=20, three_bet=6, fold_to_three_bet=54, cbet=61,
        fold_to_cbet=51, wtsd=29, aggression=1.05, bluff=0.85, limp=8,
        squeeze=6, call_down=0.92, discipline=0.68,
        tilt_speed="med", tilt_effect=0.35,
        taste={"suited": 0.80, "connected": 0.60, "broadway": 0.80},
        timing=timing(1.8, 7.0, 0.26),
    ),
    Profile(
        "sanjay", "Sanjay",
        "Loose and fast. Any ace, any suited card, any two pictures, and he is "
        "never folding a pair. Wins big pots and gives them all back.",
        vpip=50, pfr=31, three_bet=12, fold_to_three_bet=38, cbet=72,
        fold_to_cbet=33, wtsd=39, aggression=1.45, bluff=1.35, limp=22,
        squeeze=11, call_down=1.55, discipline=0.22,
        tilt_speed="none", tilt_effect=0.10,
        taste={"ace": 1.30, "suited": 1.10, "broadway": 0.95, "gap": -0.12,
               "connected": 0.65, "pair": 2.05},
        timing=timing(0.7, 2.6, 0.08),
    ),
]

#: Everyone who is not signed in as the owner plays against these instead. Same
#: six tendencies, invented people - because the tendencies are the interesting
#: part and the friends are not public.
STRANGERS = []
_STRANGER_NAMES = {
    "ronit": ("The Rock", "rock"),
    "aarav": ("Needle", "needle"),
    "bell": ("Coach", "coach"),
    "apurva": ("Marlowe", "marlowe"),
    "sanjay": ("Fireworks", "fireworks"),
}
for _p in FRIENDS:
    _name, _key = _STRANGER_NAMES[_p.key]
    _s = _p.copy()
    _s.key, _s.name, _s.avatar = _key, _name, None
    STRANGERS.append(_s)

BY_KEY = {p.key: p for p in FRIENDS + STRANGERS}


def table(private=True):
    """The five opponents. ``private`` is whether the viewer is the owner."""
    return [p.copy() for p in (FRIENDS if private else STRANGERS)]
