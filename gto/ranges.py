"""The preflop reference: what equilibrium does with each of the 169 hands.

Postflop, this trainer computes. Preflop, it looks up - because a preflop
decision at a six-handed table is a node in a game tree whose leaves are entire
postflop games, and nobody solves that on a web request. So preflop scoring
reads a chart, and the whole honesty of the preflop review rests on being exact
about **where each chart came from**. Every strategy here carries a
``confidence``:

``solver``
    Encoded from published equilibrium solutions for 100bb 6-max, 2.5bb open,
    no rake. Hand-transcribed, so read them as accurate to roughly a percent of
    range width - not to the combo.
``derived``
    A ``solver`` chart moved by a stated, quantified argument: the equal blinds
    (below), or stack depth. The argument is in the ``notes`` the lookup returns
    and the review prints it, so a derived line never reads like a solved one.
``heuristic``
    No solved analogue exists. Today that is exactly one node, and it is the
    node this game plays most: see **The small blind problem**.

A node with no chart at all returns ``None`` rather than the nearest chart.
``review.py`` then falls back to the EV-against-this-table number, which is
exact by construction, and says so. Guessing would be worse than declining:
this is a tool somebody is learning from.

**The equal blinds change every chart.** A home game running 0.25/0.25 is not
0.5/1 scaled - the small blind is a whole big blind, so there is **2bb dead in
the middle instead of 1.5bb**, and that moves real money. A 2.5bb steal risks
2.5 to win 2.0 rather than 2.5 to win 1.5, so it needs to fold out 55.6% rather
than 62.5%. Every opening range is therefore wider than its published
counterpart, and every defence is wider too, because the caller is also getting
the extra half blind. The widenings are named sets, not a fudge factor, so you
can see exactly which hands moved and disagree with the specific ones.

**The small blind problem.** With equal blinds the small blind has *already
matched the big blind*. Folded to, it is not facing a decision to enter the pot
- it is facing check or raise, and **folding is strictly dominated**: checking
costs nothing and wins some pots. Every published SB chart in existence is for
a half-blind SB with a fold option, and applying one here would tell you to
throw away hands you are entitled to see a free flop with. That is the single
biggest structural difference between this game and the games the charts come
from, it comes up once an orbit, and there is no solve to transcribe. So the SB
node is marked ``heuristic``, is built raise-or-check with **no fold branch at
all**, and is the first thing the CFR work in ``solver.py`` should replace.

**Depth.** The default seat is 200bb ($50 at 0.25/0.25) and stacks run to 600bb,
where the charts are 100bb. Depth is applied as named tweaks above stated
thresholds - more polar three-betting, wider cold-calling - each with the reason
attached. Below 150bb nothing is applied, because the published ranges are flat
enough over that span that moving them would be inventing precision.
"""

import re

from cards import RANKS

PAIR_COMBOS = 6
SUITED_COMBOS = 4
OFFSUIT_COMBOS = 12
TOTAL_COMBOS = 1326

_RANK_INDEX = {r: i for i, r in enumerate(RANKS)}


def all_classes():
    """The 169 hand classes, strongest-first within each high card."""
    out = []
    for i in range(12, -1, -1):
        out.append(RANKS[i] * 2)
        for j in range(i - 1, -1, -1):
            out.append(RANKS[i] + RANKS[j] + "s")
            out.append(RANKS[i] + RANKS[j] + "o")
    return out


CLASSES = all_classes()
_CLASS_SET = set(CLASSES)


def combos_of(cls):
    """How many of the 1326 starting hands are in this class: 6, 4 or 12."""
    if len(cls) == 2:
        return PAIR_COMBOS
    return SUITED_COMBOS if cls.endswith("s") else OFFSUIT_COMBOS


def _cls(hi, lo, suited):
    if hi == lo:
        return RANKS[hi] * 2
    a, b = (hi, lo) if hi > lo else (lo, hi)
    return RANKS[a] + RANKS[b] + ("s" if suited else "o")


def _parse_hand(tok):
    """``"AKs"`` -> ``(12, 11, True)``; ``"77"`` -> ``(5, 5, None)``."""
    if len(tok) == 2:
        a, b = tok
        if a != b or a not in _RANK_INDEX:
            raise ValueError(f"not a pair: {tok!r}")
        r = _RANK_INDEX[a]
        return r, r, None
    if len(tok) != 3:
        raise ValueError(f"cannot read hand {tok!r}")
    a, b, sfx = tok[0], tok[1], tok[2].lower()
    if a not in _RANK_INDEX or b not in _RANK_INDEX or sfx not in ("s", "o"):
        raise ValueError(f"cannot read hand {tok!r}")
    hi, lo = _RANK_INDEX[a], _RANK_INDEX[b]
    if hi == lo:
        raise ValueError(f"a pair cannot be suited or offsuit: {tok!r}")
    if hi < lo:
        hi, lo = lo, hi
    return hi, lo, sfx == "s"


def _expand_span(left, right):
    """``"AJs-A7s"``, ``"99-66"``, ``"76s-43s"`` - the three spans that mean something."""
    lh, ll, ls = _parse_hand(left)
    rh, rl, rs = _parse_hand(right)
    if ls != rs:
        raise ValueError(f"span mixes suited and offsuit: {left}-{right}")
    if lh == ll and rh == rl:
        lo, hi = sorted((ll, rl))
        return [_cls(r, r, None) for r in range(lo, hi + 1)]
    if lh == rh:
        lo, hi = sorted((ll, rl))
        return [_cls(lh, k, ls) for k in range(lo, hi + 1)]
    if lh - ll == rh - rl:
        gap = lh - ll
        lo, hi = sorted((ll, rl))
        return [_cls(k + gap, k, ls) for k in range(lo, hi + 1)]
    raise ValueError(f"cannot read span {left}-{right}")


def _expand(tok):
    """One token of range notation -> the classes it names."""
    if "-" in tok:
        left, right = tok.split("-", 1)
        return _expand_span(left.strip(), right.strip())
    plus = tok.endswith("+")
    if plus:
        tok = tok[:-1].strip()
    hi, lo, suited = _parse_hand(tok)
    if not plus:
        return [_cls(hi, lo, suited)]
    if hi == lo:
        return [_cls(r, r, None) for r in range(lo, 13)]
    return [_cls(hi, k, suited) for k in range(lo, hi)]


def parse_range(text):
    """Range notation -> a :class:`Range`.

    ``"22+, ATs+, A5s:0.5, KQo"``. A ``:w`` suffix weights that token, and a
    later token **overrides** an earlier one for the classes they share - which
    is what lets a chart say ``"A2s+, A5s:0.55"`` and mean it. Order matters, so
    write the broad stroke first and the exceptions after.
    """
    out = {}
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        weight = 1.0
        if ":" in tok:
            tok, w = tok.split(":", 1)
            tok = tok.strip()
            weight = float(w)
            if not 0.0 <= weight <= 1.0:
                raise ValueError(f"weight out of range in {text!r}: {weight}")
        for cls in _expand(tok):
            out[cls] = weight
    return Range(out)


class Range(dict):
    """Class -> weight in [0, 1]. Absent means 0."""

    def combos(self):
        return sum(w * combos_of(c) for c, w in self.items())

    def pct(self):
        return 100.0 * self.combos() / TOTAL_COMBOS

    def weight(self, cls):
        return self.get(cls, 0.0)

    def merged(self, other):
        """This range with ``other``'s weights laid over the top."""
        out = dict(self)
        out.update(other)
        return Range(out)

    def __repr__(self):
        return f"<Range {self.pct():.1f}% {len(self)} classes>"


class Strategy:
    """What to do with each class, as frequencies that sum to one.

    Actions are given as ranges; whatever weight is left over goes to
    ``residual``, which is ``"fold"`` everywhere except the equal-blind small
    blind, where it is ``"check"`` because there is nothing to fold to.
    """

    def __init__(self, name, confidence, residual="fold", notes=(), **actions):
        if confidence not in ("solver", "derived", "heuristic"):
            raise ValueError(f"unknown confidence {confidence!r}")
        self.name = name
        self.confidence = confidence
        self.residual = residual
        self.notes = list(notes)
        self.actions = {
            k: (v if isinstance(v, Range) else parse_range(v))
            for k, v in actions.items()
        }
        self._validate()

    def _validate(self):
        """No class may be assigned more than 100% of itself.

        Run at import, on every chart. These charts are hand-transcribed and the
        overwhelmingly likely typo is a hand left in two lists at full weight -
        which would silently make a strategy that cannot be played, and would
        show up in the review as a confident wrong number rather than a crash.
        """
        for cls in CLASSES:
            total = sum(r.weight(cls) for r in self.actions.values())
            if total > 1.0 + 1e-9:
                raise ValueError(
                    f"{self.name}: {cls} is assigned {total:.3f} across "
                    f"{sorted(self.actions)}"
                )

    def freqs(self, cls):
        """Every action's frequency for one class, residual included."""
        out = {a: r.weight(cls) for a, r in self.actions.items()}
        out[self.residual] = max(0.0, 1.0 - sum(out.values()))
        return out

    def best(self, cls):
        """The most frequent action, and its frequency."""
        f = self.freqs(cls)
        action = max(f, key=lambda a: (f[a], a != self.residual))
        return action, f[action]

    def is_mixed(self, cls, floor=0.05):
        """True when at least two actions clear ``floor`` - so the review can say so."""
        return sum(1 for v in self.freqs(cls).values() if v >= floor) > 1

    def with_notes(self, extra):
        out = Strategy.__new__(Strategy)
        out.__dict__.update(self.__dict__)
        out.notes = self.notes + list(extra)
        return out

    def __repr__(self):
        parts = ", ".join(f"{a} {r.pct():.1f}%" for a, r in self.actions.items())
        return f"<Strategy {self.name} [{self.confidence}] {parts}>"


# ------------------------------------------------------------------- positions

#: Preflop order. Five-handed is six-handed with UTG removed, and that is not an
#: approximation: an opening range depends on **how many players act behind
#: you**, not on how many are at the table. Five-handed HJ is first to act with
#: four behind; six-handed HJ has UTG already folded and also has four behind.
#: Same node, same chart.
POSITIONS = {
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    5: ["HJ", "CO", "BTN", "SB", "BB"],
}

_OPENER_BUCKET = {"UTG": "EARLY", "HJ": "EARLY", "CO": "CO", "BTN": "BTN", "SB": "SB"}


def positions(seats):
    if seats not in POSITIONS:
        raise ValueError(f"no chart set for {seats}-handed")
    return list(POSITIONS[seats])


def opener_bucket(pos):
    """Which opening-range width a position stands for. ``BB`` never opens."""
    return _OPENER_BUCKET.get(pos)


def hero_bucket(pos):
    """How a defender's node is keyed: the blinds are their own cases."""
    if pos in ("SB", "BB"):
        return pos
    return "IP"


# ----------------------------------------------------------------- RFI charts

#: 100bb, 2.5bb open, no rake, half-size small blind - the world the published
#: solutions live in. ``EQUAL_BLIND_RFI_EXTRA`` moves them into this game's.
BASE_RFI = {
    "UTG": "22+, A2s+, K9s+, Q9s+, J9s+, T8s+, 97s+, 87s, 76s, 65s, AJo+, KQo",
    "HJ": (
        "22+, A2s+, K8s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, "
        "ATo+, KJo+"
    ),
    "CO": (
        "22+, A2s+, K5s+, Q7s+, J7s+, T7s+, 96s+, 85s+, 75s+, 64s+, 54s, "
        "ATo+, KTo+, QJo"
    ),
    "BTN": (
        "22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 95s+, 85s+, 74s+, 63s+, 53s+, 43s, "
        "A2o+, K8o+, Q9o+, J9o+, T9o"
    ),
}

#: What the extra half blind buys. A 2.5bb steal into 2bb of blinds needs to work
#: 2.5/4.5 = 55.6% of the time; into 1.5bb it needed 62.5%. That is a large
#: change in the break-even, and it is worth about a seat's worth of position -
#: which is why these additions look like the next seat over's boundary hands.
EQUAL_BLIND_RFI_EXTRA = {
    "UTG": "K8s, Q8s, J8s, 54s",
    "HJ": "K7s, Q7s, J7s, 96s, 64s",
    "CO": "K4s, Q6s, J6s, T6s, 95s, 74s, 63s, A9o, K9o",
    "BTN": "Q3s, J5s, T5s, 94s, 84s, 73s, 62s, 52s, K7o, Q8o, J8o, T8o, 98o",
}

#: Folded to the small blind, equal blinds. **There is no fold branch.** The
#: small blind has already matched the big blind, so its options are check and
#: raise, and a chart that folds here is throwing away a free flop. Nothing
#: published covers this node, so: raise the hands that want the initiative and
#: the fold equity, check the rest and see a flop for nothing. Marked
#: ``heuristic`` on purpose. ``solver.py`` should own this node.
EQUAL_BLIND_SB = {
    "raise": (
        "55+, 44-22:0.35, A2s+, K7s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, "
        "K6s:0.4, Q7s:0.4, J7s:0.4, T7s:0.4, 96s:0.4, 85s:0.4, 64s:0.35, 54s:0.5, "
        "A7o+, KTo+, QJo, A5o:0.4, A4o:0.35, K9o:0.4, QTo:0.4, JTo:0.45, T9o:0.3"
    ),
}


# -------------------------------------------------------- defending an open

#: Keyed ``(opener bucket, hero bucket)``. Missing keys are missing on purpose -
#: a hand that reaches a node with no chart gets no chart, not the nearest one.
VS_RFI = {
    ("EARLY", "IP"): {
        "3bet": (
            "QQ+, JJ:0.75, TT:0.35, AKs, AQs:0.55, AJs:0.15, AKo:0.9, AQo:0.25, "
            "A5s:0.55, A4s:0.4, A3s:0.25, KQs:0.25, KJs:0.2, KTs:0.1"
        ),
        "call": (
            "JJ:0.25, TT:0.65, 99-55, 44-22:0.55, AQs:0.45, AJs:0.85, ATs, "
            "A9s:0.3, A5s:0.45, A4s:0.4, KQs:0.75, KJs:0.8, KTs:0.55, QJs, "
            "QTs:0.7, JTs, T9s, 98s, 87s, 76s:0.55, AKo:0.1, AQo:0.6, AJo:0.3, "
            "KQo:0.35"
        ),
    },
    ("EARLY", "SB"): {
        "3bet": (
            "QQ+, JJ:0.8, TT:0.5, AKs, AQs:0.7, AJs:0.2, AKo, AQo:0.35, "
            "A5s:0.6, A4s:0.45, KQs:0.3, KJs:0.25"
        ),
        "call": (
            "JJ:0.2, TT:0.5, 99-66, 55-22:0.4, AQs:0.3, AJs:0.8, ATs:0.85, "
            "A5s:0.4, KQs:0.7, KJs:0.5, KTs:0.4, QJs:0.65, QTs:0.4, JTs:0.7, "
            "T9s:0.45, 98s:0.3, AQo:0.4, AJo:0.15"
        ),
    },
    ("EARLY", "BB"): {
        "3bet": (
            "QQ+, JJ:0.7, TT:0.2, AKs, AQs:0.5, AKo:0.9, A5s:0.55, A4s:0.45, "
            "A3s:0.3, KJs:0.2, KTs:0.15, 76s:0.15, 65s:0.15"
        ),
        "call": (
            "JJ:0.3, TT:0.8, 99-22, AQs:0.5, AJs-A6s, A5s:0.45, A4s:0.55, "
            "A3s:0.7, A2s, KQs, KJs:0.8, KTs:0.85, K9s-K7s, QJs-Q8s, JTs-J8s, "
            "T9s-T8s, 98s, 97s, 87s, 86s, 76s:0.85, 75s:0.6, 65s:0.85, 54s, "
            "AKo:0.1, AQo, AJo, ATo, A9o:0.5, A8o:0.35, KQo, KJo, KTo:0.6, "
            "QJo, QTo:0.5, JTo:0.6, T9o:0.3"
        ),
    },
    ("CO", "IP"): {
        "3bet": (
            "JJ+, TT:0.6, 99:0.2, AKs, AQs, AJs:0.4, ATs:0.2, AKo, AQo:0.5, "
            "AJo:0.15, A5s:0.5, A4s:0.45, A3s:0.35, A2s:0.3, KQs:0.4, KJs:0.3, "
            "KTs:0.2, QJs:0.2, 87s:0.15, 76s:0.15"
        ),
        "call": (
            "TT:0.4, 99:0.8, 88-22, AJs:0.6, ATs:0.8, A9s-A6s, A5s:0.5, "
            "A4s:0.4, KQs:0.6, KJs:0.7, KTs:0.8, K9s, QJs:0.8, QTs, Q9s:0.6, "
            "JTs, J9s:0.55, T9s, 98s, 87s:0.8, 76s:0.8, 65s:0.6, AQo:0.5, "
            "AJo:0.7, ATo:0.4, KQo:0.6, KJo:0.25"
        ),
    },
    ("CO", "SB"): {
        "3bet": (
            "JJ+, TT:0.7, AKs, AQs, AJs:0.35, AKo, AQo:0.5, A5s:0.6, A4s:0.5, "
            "A3s:0.35, KQs:0.4, KJs:0.3, KTs:0.2, QJs:0.2"
        ),
        "call": (
            "TT:0.3, 99-55, 44-22:0.45, AJs:0.65, ATs, A9s:0.6, A5s:0.4, "
            "KQs:0.6, KJs:0.6, KTs:0.55, QJs:0.7, QTs:0.55, JTs:0.75, T9s:0.6, "
            "98s:0.5, 87s:0.4, 76s:0.3, AQo:0.4, AJo:0.35, KQo:0.4"
        ),
    },
    ("CO", "BB"): {
        "3bet": (
            "JJ+, TT:0.45, AKs, AQs:0.6, AJs:0.25, AKo:0.95, AQo:0.35, "
            "A5s:0.55, A4s:0.5, A3s:0.4, A2s:0.3, KJs:0.25, KTs:0.2, K9s:0.15, "
            "87s:0.15, 76s:0.2, 65s:0.2, 54s:0.2"
        ),
        "call": (
            "TT:0.55, 99-22, AQs:0.4, AJs:0.75, ATs-A6s, A5s:0.45, A4s:0.5, "
            "A3s:0.6, A2s:0.7, KQs, KJs:0.75, KTs:0.8, K9s:0.85, K8s-K5s, "
            "QJs-Q6s, JTs-J7s, T9s-T7s, 98s-96s, 87s:0.85, 86s, 76s:0.8, 75s, "
            "65s:0.8, 64s:0.6, 54s:0.8, 53s:0.5, AKo:0.05, AQo:0.65, AJo, ATo, "
            "A9o, A8o:0.7, A7o:0.5, A5o:0.4, A4o:0.35, KQo, KJo, KTo, K9o:0.5, "
            "QJo, QTo, Q9o:0.5, JTo, J9o:0.5, T9o:0.6, 98o:0.35"
        ),
    },
    ("BTN", "SB"): {
        "3bet": (
            "TT+, 99:0.5, AKs, AQs, AJs, ATs:0.5, AKo, AQo, AJo:0.4, A5s:0.65, "
            "A4s:0.55, A3s:0.45, A2s:0.35, KQs, KJs:0.5, KTs:0.35, K9s:0.2, "
            "QJs:0.4, QTs:0.25, JTs:0.3"
        ),
        "call": (
            "99:0.5, 88-22, ATs:0.5, A9s-A6s, A5s:0.35, KJs:0.5, KTs:0.6, "
            "QJs:0.55, QTs:0.6, JTs:0.65, T9s:0.6, 98s:0.5, 87s:0.5, 76s:0.4, "
            "AJo:0.5, ATo:0.5, KQo:0.6, KJo:0.35, QJo:0.3"
        ),
    },
    ("BTN", "BB"): {
        "3bet": (
            "TT+, 99:0.35, AKs, AQs, AJs:0.5, AKo, AQo:0.6, AJo:0.3, A5s:0.6, "
            "A4s:0.55, A3s:0.45, A2s:0.4, KQs:0.55, KJs:0.35, KTs:0.25, "
            "QJs:0.3, JTs:0.2, T9s:0.15, 65s:0.2, 54s:0.25"
        ),
        "call": (
            "99:0.65, 88-22, AJs:0.5, ATs-A6s, A5s:0.4, A4s:0.45, A3s:0.55, "
            "A2s:0.6, KQs:0.45, KJs:0.65, KTs:0.75, K9s-K2s, QJs:0.7, QTs-Q4s, "
            "JTs:0.8, J9s-J6s, T9s:0.85, T8s-T6s, 98s-95s, 87s-85s, 76s-74s, "
            "65s:0.8, 64s, 54s:0.75, 53s, 43s, AQo:0.4, AJo:0.7, ATo, A9o, "
            "A8o, A7o, A6o:0.6, A5o, A4o, A3o:0.5, A2o:0.4, KQo, KJo, KTo, "
            "K9o, K8o:0.5, K7o:0.35, QJo, QTo, Q9o, Q8o:0.4, JTo, J9o, J8o:0.4, "
            "T9o, T8o:0.4, 98o, 97o:0.35, 87o, 76o:0.4"
        ),
    },
    # Equal blinds again: the small blind that raised did so from a range that
    # never folded, and the big blind is closing with an extra half blind of
    # dead money already its own. Heuristic, and paired with EQUAL_BLIND_SB.
    ("SB", "BB"): {
        "3bet": (
            "TT+, 99:0.4, AKs, AQs, AJs:0.4, AKo, AQo:0.5, A5s:0.6, A4s:0.5, "
            "A3s:0.4, KQs:0.5, KJs:0.3, KTs:0.2, QJs:0.25, JTs:0.2, 76s:0.2, "
            "65s:0.2"
        ),
        "call": (
            "99:0.6, 88-22, AJs:0.6, ATs-A6s, A5s:0.4, A4s:0.5, A3s:0.6, A2s, "
            "KQs:0.5, KJs:0.7, KTs:0.8, K9s-K5s, QJs:0.75, QTs-Q7s, JTs:0.8, "
            "J9s-J7s, T9s-T7s, 98s-96s, 87s-86s, 76s:0.8, 75s, 65s:0.8, 64s, "
            "54s, AQo:0.5, AJo, ATo, A9o, A8o, A7o:0.6, A6o:0.4, A5o:0.5, KQo, "
            "KJo, KTo, K9o:0.6, QJo, QTo, Q9o:0.5, JTo, J9o:0.5, T9o:0.6, "
            "98o:0.4"
        ),
    },
}

#: Facing a three-bet, keyed by **the opener's own** bucket - a button that
#: opened 50% defends a three-bet very differently from an early seat that
#: opened 19%, and it is the width it opened that decides it.
VS_3BET = {
    "EARLY": {
        "4bet": (
            "KK+, QQ:0.55, JJ:0.15, AKs:0.6, AKo:0.5, AQs:0.15, A5s:0.35, "
            "A4s:0.25, KQs:0.1"
        ),
        "call": (
            "QQ:0.45, JJ:0.85, TT, 99, 88:0.7, 77:0.5, 66-22:0.3, AKs:0.4, "
            "AQs:0.85, AJs, ATs:0.7, A5s:0.3, KQs:0.75, KJs:0.6, QJs:0.5, "
            "JTs:0.5, T9s:0.4, 98s:0.35, AKo:0.5, AQo:0.3"
        ),
    },
    "CO": {
        "4bet": (
            "KK+, QQ:0.6, JJ:0.25, AKs:0.65, AKo:0.6, AQs:0.2, A5s:0.4, "
            "A4s:0.35, A3s:0.25, KQs:0.15, K9s:0.15"
        ),
        "call": (
            "QQ:0.4, JJ:0.75, TT, 99, 88, 77:0.7, 66-22:0.4, AKs:0.35, "
            "AQs:0.8, AJs, ATs, A9s:0.4, A5s:0.35, KQs:0.8, KJs:0.7, KTs:0.5, "
            "QJs:0.65, QTs:0.45, JTs:0.6, T9s:0.5, 98s:0.45, 87s:0.4, 76s:0.3, "
            "AKo:0.4, AQo:0.5, AJo:0.25, KQo:0.3"
        ),
    },
    "BTN": {
        "4bet": (
            "KK+, QQ:0.65, JJ:0.3, TT:0.1, AKs:0.7, AKo:0.65, AQs:0.25, "
            "AQo:0.15, A5s:0.45, A4s:0.4, A3s:0.3, A2s:0.2, K9s:0.2, K8s:0.15, "
            "Q9s:0.15"
        ),
        "call": (
            "QQ:0.35, JJ:0.7, TT:0.9, 99, 88, 77, 66:0.7, 55-22:0.45, "
            "AKs:0.3, AQs:0.75, AJs, ATs, A9s:0.6, A8s:0.4, A5s:0.3, KQs:0.85, "
            "KJs:0.75, KTs:0.65, K9s:0.4, QJs:0.7, QTs:0.6, Q9s:0.4, JTs:0.65, "
            "J9s:0.45, T9s:0.6, 98s:0.5, 87s:0.5, 76s:0.45, 65s:0.35, "
            "AKo:0.35, AQo:0.7, AJo:0.45, ATo:0.25, KQo:0.5, KJo:0.3, QJo:0.2"
        ),
    },
    "SB": {
        "4bet": (
            "KK+, QQ:0.6, JJ:0.25, AKs:0.65, AKo:0.6, AQs:0.2, A5s:0.4, A4s:0.3"
        ),
        "call": (
            "QQ:0.4, JJ:0.75, TT, 99, 88, 77:0.6, 66-22:0.35, AKs:0.35, "
            "AQs:0.8, AJs, ATs, A9s:0.4, KQs:0.8, KJs:0.65, KTs:0.5, QJs:0.6, "
            "QTs:0.4, JTs:0.55, T9s:0.45, 98s:0.4, 87s:0.35, AKo:0.4, AQo:0.5, "
            "AJo:0.3, KQo:0.35"
        ),
    },
}


# --------------------------------------------------------------------- depth

#: The seat here is 200bb ($50 at 0.25/0.25) and stacks reach 600bb, where every
#: chart above is 100bb. Depth is applied as **named** moves above stated
#: thresholds, each with the reason the review prints, rather than as a factor -
#: so you can see which hands moved and argue with those specific hands.
#:
#: Nothing is applied below 150bb. Published ranges are flat enough across
#: 100-150bb that moving them would be inventing precision this file has no
#: right to.
#:
#: Each op is ``(kind, action, hands, factor)``. ``scale`` multiplies the
#: weights already there; ``boost`` adds the weights written in the text. After
#: every op the class totals are renormalised down if they exceed one, so a
#: boost can never make an unplayable strategy.
DEPTH_TIERS = [
    (
        150.0,
        "deep (150bb+)",
        [
            ("scale", "3bet", "AQo, AJo, ATo, KQo, KJo", 0.6),
            ("boost", "call", "AQo:0.2, AJo:0.2, ATo:0.15, KQo:0.2, KJo:0.1", None),
            ("boost", "3bet", "A5s:0.1, A4s:0.1, A3s:0.1, A2s:0.1, KTs:0.1, QTs:0.1", None),
            ("boost", "call", "22+:0.1, 76s:0.1, 65s:0.1, 54s:0.1, 87s:0.1, 98s:0.1", None),
        ],
        [
            "Offsuit broadways three-bet less at depth: they make one pair in a "
            "pot that is now threatening several hundred blinds, and one pair "
            "is exactly what does not want that pot. The weight moves to call.",
            "Suited wheel aces and suited broadways three-bet more: at depth the "
            "value of a hand that can make the nuts and stack somebody rises "
            "faster than the value of a hand that is merely ahead now.",
            "Pairs and suited connectors call more. Set-mining wants about 12:1 "
            "on the implied odds and gets it at 200bb; at 100bb it does not.",
        ],
    ),
    (
        300.0,
        "very deep (300bb+)",
        [
            ("scale", "3bet", "AQo, AJo, ATo, KQo, KJo, AJs, KQs", 0.7),
            ("scale", "4bet", "AQo, AQs, JJ, TT", 0.6),
            ("boost", "call", "22+:0.15, 65s:0.15, 54s:0.15, 43s:0.15, J9s:0.15, T8s:0.15", None),
        ],
        [
            "Beyond 300bb the four-bet range tightens towards hands that want "
            "all the money in: the middling value four-bets stop being value at "
            "all once the stack behind is four times the pot.",
            "Small pairs and suited gappers keep gaining. These are the hands "
            "whose whole value is the rare enormous pot, and at this depth the "
            "enormous pot is available.",
        ],
    ),
]


def _apply_ops(actions, ops):
    for kind, action, text, factor in ops:
        if action not in actions:
            continue
        target = actions[action]
        for cls, w in parse_range(text).items():
            if kind == "scale":
                if cls in target:
                    target[cls] = target[cls] * factor
            elif kind == "boost":
                target[cls] = min(1.0, target.get(cls, 0.0) + w)
            else:
                raise ValueError(f"unknown depth op {kind!r}")


def _renormalise(actions):
    """Shrink any class that now sums past one, keeping the action mix."""
    for cls in CLASSES:
        total = sum(a.weight(cls) for a in actions.values())
        if total > 1.0:
            for a in actions.values():
                if cls in a:
                    a[cls] = a[cls] / total


def apply_depth(strategy, depth_bb):
    """A strategy moved to this stack depth, with the reasons attached.

    Returns the strategy unchanged below the first threshold. Above one, a
    solved strategy becomes ``derived`` - it is no longer the published
    solution, and the review must not present it as one.

    **Adjusting never improves a label.** A ``heuristic`` strategy that has been
    moved for depth is still a heuristic, and stamping the result ``derived``
    would have it claim, in the one place somebody reads the confidence, to have
    been "adjusted from a solved equilibrium" when there was no equilibrium to
    adjust. That is exactly the lie this scheme exists to prevent, and it would
    have been told about the equal-blind small blind - the single node with no
    solve behind it - every time the hero sat deeper than 150bb.
    """
    tiers = [t for t in DEPTH_TIERS if depth_bb >= t[0]]
    if not tiers:
        return strategy

    actions = {k: Range(dict(v)) for k, v in strategy.actions.items()}
    notes = list(strategy.notes)
    for _, label, ops, reasons in tiers:
        _apply_ops(actions, ops)
        notes.append(f"Adjusted for {label}.")
        notes.extend(reasons)
    _renormalise(actions)

    return Strategy(
        strategy.name + f" @{depth_bb:.0f}bb",
        "derived" if strategy.confidence in ("solver", "derived") else strategy.confidence,
        residual=strategy.residual,
        notes=notes,
        **actions,
    )


# ------------------------------------------------------------------- assembly

_EQUAL_BLIND_NOTE = (
    "Widened for the equal blinds. With 0.25/0.25 there is 2bb dead in the "
    "middle rather than 1.5bb, so a 2.5bb open needs to work 55.6% of the time "
    "rather than 62.5% - about a seat's worth of position."
)

_SB_NOTE = (
    "Heuristic, not a solve. The small blind has already matched the big blind, "
    "so folding is dominated by checking and this strategy has no fold branch. "
    "No published solution covers an equal-blind small blind; treat the split "
    "as a considered starting point rather than an equilibrium."
)

_STRATEGIES = {}


def _build():
    for pos, text in BASE_RFI.items():
        _STRATEGIES[("rfi", pos, False)] = Strategy(
            f"RFI {pos}", "solver", **{"raise": text}
        )
        widened = parse_range(text).merged(parse_range(EQUAL_BLIND_RFI_EXTRA[pos]))
        _STRATEGIES[("rfi", pos, True)] = Strategy(
            f"RFI {pos} (equal blinds)",
            "derived",
            notes=[_EQUAL_BLIND_NOTE],
            **{"raise": widened},
        )

    _STRATEGIES[("rfi", "SB", True)] = Strategy(
        "SB option (equal blinds)",
        "heuristic",
        residual="check",
        notes=[_SB_NOTE],
        **EQUAL_BLIND_SB,
    )

    for (opener, hero), spec in VS_RFI.items():
        confidence = "heuristic" if opener == "SB" else "solver"
        notes = [_SB_NOTE] if opener == "SB" else []
        _STRATEGIES[("vs_rfi", opener, hero)] = Strategy(
            f"vs {opener} open, {hero}", confidence, notes=notes, **spec
        )

    for opener, spec in VS_3BET.items():
        confidence = "heuristic" if opener == "SB" else "solver"
        notes = [_SB_NOTE] if opener == "SB" else []
        _STRATEGIES[("vs_3bet", opener)] = Strategy(
            f"{opener} facing a 3-bet", confidence, notes=notes, **spec
        )


_build()


def lookup(node, hero_pos, seats=6, depth_bb=100.0, equal_blinds=True):
    """The reference strategy for a preflop spot, or ``None`` if there is none.

    ``node`` is one of:

    ``("rfi",)``
        Folded to hero.
    ``("vs_rfi", opener_pos)``
        One raise in front, hero has not acted.
    ``("vs_3bet", threebettor_pos)``
        Hero opened, one player three-bet, nobody else came along.

    **``None`` is a real answer and the common one.** Limped pots, squeezes,
    four-bet pots, three-way pots, any spot with a cold-caller already in - none
    of those are charted, because charting them by hand would be making numbers
    up. ``review.py`` handles ``None`` by scoring the decision on the
    EV-against-this-table figure alone and saying that is what it did.
    """
    if hero_pos not in POSITIONS.get(seats, ()):
        raise ValueError(f"{hero_pos} is not a seat at a {seats}-handed table")

    kind = node[0]
    if kind == "rfi":
        if hero_pos == "BB":
            return None
        found = _STRATEGIES.get(("rfi", hero_pos, equal_blinds))
        if found is None and hero_pos == "SB":
            return None
    elif kind == "vs_rfi":
        opener = opener_bucket(node[1])
        bucket = hero_bucket(hero_pos)
        found = _STRATEGIES.get(("vs_rfi", opener, bucket))
        if found is not None and equal_blinds:
            found = _widen_defence(found, opener, bucket)
    elif kind == "vs_3bet":
        found = _STRATEGIES.get(("vs_3bet", opener_bucket(hero_pos)))
    else:
        raise ValueError(f"unknown preflop node {node!r}")

    if found is None:
        return None
    return apply_depth(found, depth_bb)


#: The other half of the equal blinds, and the half that matters more.
#:
#: Facing a 2.5bb open, a **half**-blind small blind pays 2.0 into 4.0 and needs
#: 33.3%. An **equal** small blind has already put a whole blind in, pays 1.5
#: into 4.5, and needs 25.0% - which is big-blind pot odds while still being out
#: of position with a live big blind behind. Nothing else about this game moves
#: a range as far. The big blind improves too, 27.3% to 25.0%, and a cold-caller
#: in position from 38.5% to 35.7%; both are real but small next to the small
#: blind's.
#:
#: Applied to the calling range only. Three-betting is a fold-equity decision
#: and the extra half blind barely touches it - if anything it argues for
#: calling *instead of* three-betting, which is exactly what boosting only the
#: call does.
EQUAL_BLIND_DEFENCE_EXTRA = {
    "SB": (
        "88-22:0.4, A9s-A6s:0.5, KTs:0.35, K9s-K7s:0.5, QTs:0.3, Q9s-Q8s:0.5, "
        "J9s-J8s:0.5, T9s:0.35, T8s:0.5, 98s:0.4, 97s:0.4, 87s:0.4, 86s:0.4, "
        "76s:0.4, 65s:0.4, 54s:0.4, ATo:0.35, A9o:0.3, KQo:0.25, KJo:0.35, "
        "KTo:0.3, QJo:0.35, QTo:0.25, JTo:0.3"
    ),
    "BB": (
        "K4s-K2s:0.3, Q3s-Q2s:0.3, J5s-J4s:0.3, T5s:0.3, 94s:0.3, 84s:0.3, "
        "74s:0.3, 63s:0.3, 52s:0.3, 42s:0.3, 32s:0.3, A5o-A2o:0.3, K6o-K4o:0.3, "
        "Q7o:0.3, J8o:0.3, T8o:0.3, 97o:0.3, 86o:0.3, 76o:0.3, 65o:0.3"
    ),
    "IP": (
        "88-22:0.2, A9s-A6s:0.3, K9s:0.3, Q9s:0.3, J9s:0.3, T8s:0.3, 97s:0.3, "
        "86s:0.3, 65s:0.3, 54s:0.3, ATo:0.25, KJo:0.25, QJo:0.3"
    ),
}

_DEFENCE_NOTES = {
    "SB": (
        "Widened hard for the equal blinds. The small blind is already in for a "
        "full blind, so it calls 1.5 into 4.5 and needs 25% where a half-blind "
        "small blind needed 33.3%. It is getting big-blind odds out of position - "
        "call more, and three-bet no more than before.",
    ),
    "BB": (
        "Widened for the equal blinds: 25% needed rather than 27.3%, because the "
        "small blind's extra half blind is dead money in front of you.",
    ),
    "IP": (
        "Widened slightly for the equal blinds: 35.7% needed rather than 38.5%.",
    ),
}


def _widen_defence(strategy, opener, hero_bucket_name):
    """Move a published defence into this game's blind structure.

    Skipped when the opener is the small blind, because that node was written
    for the equal blinds already and would otherwise be widened twice.
    """
    extra = EQUAL_BLIND_DEFENCE_EXTRA.get(hero_bucket_name)
    if extra is None or opener == "SB":
        return strategy
    actions = {k: Range(dict(v)) for k, v in strategy.actions.items()}
    _apply_ops(actions, [("boost", "call", extra, None)])
    _renormalise(actions)
    return Strategy(
        strategy.name + " (equal blinds)",
        "derived",
        residual=strategy.residual,
        notes=list(strategy.notes) + list(_DEFENCE_NOTES[hero_bucket_name]),
        **actions,
    )


# ------------------------------------------------------- classes to cards

_CLASS_COMBOS = {}


def class_combos(cls):
    """The concrete two-card holdings in a class: 6, 4 or 12 of them."""
    hit = _CLASS_COMBOS.get(cls)
    if hit is None:
        from cards import make
        if len(cls) == 2:
            r = _RANK_INDEX[cls[0]]
            hit = [(make(r, a), make(r, b))
                   for a in range(4) for b in range(a + 1, 4)]
        else:
            hi, lo = _RANK_INDEX[cls[0]], _RANK_INDEX[cls[1]]
            if cls.endswith("s"):
                hit = [(make(hi, s), make(lo, s)) for s in range(4)]
            else:
                hit = [(make(hi, a), make(lo, b))
                       for a in range(4) for b in range(4) if a != b]
        _CLASS_COMBOS[cls] = hit
    return hit


def weighted_combos(rng_range, dead=()):
    """``[(card, card, weight), ...]`` for a range, skipping blocked holdings.

    **Card removal is not a rounding error.** Holding the ace of spades takes
    every ace-of-spades combination out of everybody else's range, and on a spot
    that turns on whether the opponent has the nut flush that is the whole
    question. So this is done by enumeration rather than by scaling the class
    weight, and the caller passes every known card as ``dead``.
    """
    dead = set(dead)
    out = []
    for cls, w in rng_range.items():
        if w <= 0:
            continue
        for a, b in class_combos(cls):
            if a in dead or b in dead:
                continue
            out.append((a, b, w))
    return out
