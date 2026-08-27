"""Checking this trainer's numbers against somebody else's.

Everything here answers one question: **is the arithmetic in this directory
actually right, or is it only self-consistent?** Every test in ``tests/`` checks
this code against this code. That catches a regression and cannot catch a
mistake that was there from the first commit - a misread chart, an equity
function that has always been half a percent out, an evaluator that ranks two
hands the wrong way round on a board nobody thought to write a test for.

So these compare against things written by other people:

``eval7``
    A separate hand evaluator and exact hand-versus-range solver, written in C,
    used by a lot of poker research. It knows nothing about this repository. It
    is the reference for ``evaluator.py``, ``equity.py`` and the new per-holding
    machinery in it.
published preflop solutions
    The opening charts in ``ranges.py`` are labelled ``solver``, which is a
    claim that they were read off a solved 6-max 100bb equilibrium. That claim
    is testable: a chart transcribed by hand can be typed wrong, and the widths
    it produces can be compared with the frequencies those solutions are
    published at.
TexasSolver
    An open-source postflop solver. This is the one comparison that is **not
    run here**, because it needs a binary this repository does not ship and will
    not download at test time. The check is written, it says exactly what to
    install, and until somebody installs it the report says ``not run`` rather
    than passing quietly.

**A check that cannot run is not a check that passed**, and the report page is
built around saying so: every row carries its status, its sample size and the
worst disagreement found, and a row that never ran says that in the same place
a failure would appear.
"""

import os
import random
import shutil

import equity as eq
import ranges
from cards import DECK, RANKS, SUITS, card_str, parse_card
from evaluator import evaluate

#: Percentage points a hand-transcribed opening chart may sit away from the
#: frequency the published solution is quoted at. Solutions differ by more than
#: nothing between themselves - rake, open size and bet-size abstraction all
#: move an opening range by a point or so - and this is the honest width of that
#: band rather than a tolerance chosen to make the charts pass.
CHART_TOLERANCE = 3.0

#: Standard 6-max 100bb opening frequencies, as published solved strategies quote
#: them. This is a **second, independent transcription of the same claim**
#: ``BASE_RFI`` makes; the point of comparing two transcriptions is that a typo
#: shows up in exactly one of them.
PUBLISHED_RFI = {
    "UTG": 15.5,
    "HJ": 19.5,
    "CO": 26.5,
    "BTN": 44.0,
}

#: Where a TexasSolver console binary would be. Set ``TEXASSOLVER_BIN``, or put
#: ``console_solver`` on the path.
TEXASSOLVER_ENV = "TEXASSOLVER_BIN"


class Check:
    """One comparison, and what it found."""

    def __init__(self, name, against, question, status, samples=0, worst=None,
                 tolerance=None, detail="", rows=()):
        self.name = name
        self.against = against
        self.question = question
        #: ``"pass"``, ``"fail"`` or ``"not run"``. Never anything else, and
        #: never absent - a check with no status reads as one that passed.
        self.status = status
        self.samples = samples
        self.worst = worst
        self.tolerance = tolerance
        self.detail = detail
        self.rows = list(rows)

    def to_dict(self):
        return {
            "name": self.name, "against": self.against,
            "question": self.question, "status": self.status,
            "samples": self.samples,
            "worst": None if self.worst is None else round(self.worst, 6),
            "tolerance": self.tolerance, "detail": self.detail,
            "rows": self.rows,
        }

    def __repr__(self):
        return f"<{self.name}: {self.status}>"


def _e7():
    import eval7
    return eval7


def available():
    """Whether the external reference is installed at all."""
    try:
        _e7()
        return True
    except ImportError:
        return False


def _to_e7(cards):
    e7 = _e7()
    return [e7.Card(card_str(c)) for c in cards]


def _reference_equity(hero, villain, board):
    """Exact equity, enumerated here, scored by eval7's evaluator.

    **The reference is built rather than borrowed, and that is deliberate.**
    ``eval7.py_hand_vs_range_exact`` returns 1.0 for every input in 0.1.11 - AA
    against KK included - so it is not usable, and its Monte Carlo sibling is a
    sampler, which is the wrong kind of thing to check an exact answer with.
    What is needed is an exact enumeration that shares no code with
    ``equity.py``: this loop is written here, and every hand in it is ranked by
    eval7's C evaluator rather than by ``evaluator.py``. So a disagreement is a
    real disagreement about poker and not two copies of one mistake.

    ``_reference_agrees_with_eval7_monte_carlo`` then checks *this* against
    eval7's own sampler, because a hand-written reference is a thing that can be
    wrong too.
    """
    import itertools
    e7 = _e7()
    hero, villain, board = list(hero), list(villain), list(board)
    known = set(hero) | set(villain) | set(board)
    deck = [c for c in DECK if c not in known]
    need = 5 - len(board)
    won = 0.0
    n = 0
    for extra in itertools.combinations(deck, need):
        full = board + list(extra)
        mine = e7.evaluate(_to_e7(hero + full))
        theirs = e7.evaluate(_to_e7(villain + full))
        won += 1.0 if mine > theirs else (0.5 if mine == theirs else 0.0)
        n += 1
    return won / n if n else 0.0


def _reference_range_equity(hero, combos, board):
    """The same, against a weighted list of holdings. Exact."""
    total = 0.0
    weighted = 0.0
    for a, b, w in combos:
        weighted += w * _reference_equity(hero, [a, b], board)
        total += w
    return weighted / total if total else 0.0


# ------------------------------------------------------------- the evaluator


def evaluator_against_eval7(n=20000, seed=11):
    """Does this evaluator rank two hands the same way round as eval7 does?

    Not "is the score the same number" - the two use different scales and there
    is no reason they should. What has to agree is the **order**, on every pair,
    including the ties: a tie called a win is how a chopped pot turns into a
    made-up edge, and it is the error ``equity.py``'s docstring says this whole
    directory is built to avoid.
    """
    if not available():
        return Check("Hand ranking", "eval7",
                     "does evaluate() order two hands the way eval7 does?",
                     "not run", detail="eval7 is not installed")
    e7 = _e7()
    rng = random.Random(seed)
    bad = []
    for _ in range(n):
        cards = rng.sample(DECK, 9)
        board, a, b = cards[:5], cards[5:7], cards[7:9]
        mine = (evaluate(a + board) > evaluate(b + board),
                evaluate(a + board) == evaluate(b + board))
        # eval7 scores higher for better hands, same as this one.
        ta, tb = e7.evaluate(_to_e7(a + board)), e7.evaluate(_to_e7(b + board))
        theirs = (ta > tb, ta == tb)
        if mine != theirs:
            bad.append({
                "board": " ".join(card_str(c) for c in board),
                "a": " ".join(card_str(c) for c in a),
                "b": " ".join(card_str(c) for c in b),
            })
    return Check(
        "Hand ranking", "eval7",
        "does evaluate() order two hands the way eval7 does?",
        "pass" if not bad else "fail", samples=n, worst=len(bad), tolerance=0,
        detail=(f"{n:,} random pairs on a full board, every one ordered "
                f"identically." if not bad
                else f"{len(bad)} of {n:,} pairs disagreed."),
        rows=bad[:5])


# ---------------------------------------------------------------- the equity


_EQUITY_SPOTS = [
    ("As Ks", "Qh Jd", "7c 2d 9s"),
    ("Ac Ad", "Kc Kd", "2h 7s Ts"),
    ("Jh Th", "Ad Kc", "9h 8c 2h"),
    ("7c 7d", "As Kh", "Kd 4s 2c 9h"),
    ("Qs Jc", "Ah Ts", "Kd Qd 3h 8s"),
    ("5h 5c", "Ac Qd", "Kh 9s 4d 2c 7h"),
]


def _cards(text):
    return [parse_card(x) for x in text.split()]


def equity_against_eval7(tolerance=1e-9):
    """Is ``showdown_equity`` exactly what an independent enumeration says?

    These are the spots ``equity.py`` claims to answer *exactly* - a board of
    three cards or more - so the tolerance is floating-point noise rather than a
    sampling allowance. A disagreement here is a bug, not a variance.
    """
    if not available():
        return Check("Hand versus hand", "eval7",
                     "is exact enumeration exact?", "not run",
                     detail="eval7 is not installed")
    rows, worst = [], 0.0
    for hero, villain, board in _EQUITY_SPOTS:
        h, v, b = _cards(hero), _cards(villain), _cards(board)
        mine = eq.showdown_equity([h, v], board=b)[0]
        theirs = _reference_equity(h, v, b)
        worst = max(worst, abs(mine - theirs))
        rows.append({"spot": f"{hero} vs {villain} on {board}",
                     "ours": round(mine * 100, 4),
                     "theirs": round(theirs * 100, 4),
                     "diff": round((mine - theirs) * 100, 6)})
    return Check(
        "Hand versus hand", "eval7's evaluator, enumerated here",
        "is exact enumeration exact?",
        "pass" if worst <= tolerance else "fail",
        samples=len(_EQUITY_SPOTS), worst=worst * 100, tolerance=tolerance * 100,
        detail=("Every spot agrees to the last place a float has."
                if worst <= tolerance else
                f"Worst disagreement {worst * 100:.6f} points."),
        rows=rows)


_RANGE_SPOTS = [
    ("As Ks", "QQ+,AKs,AQs", "7c 2d 9s"),
    ("Jh Th", "TT+,AJs+,KQs", "9h 8c 2h"),
    ("7c 7d", "22+,A2s+,KTs+", "Kd 4s 2c 9h"),
    ("Qs Jc", "88+,ATo+,KJo+", "Kd Qd 3h 8s"),
]


def range_equity_against_eval7(iters=8000, seed=5):
    """Does the sampler land where the exact answer is, within its own error?

    ``range_equity`` is honest that it samples, and it reports a standard error.
    The test of that claim is not "is it close" but "is it inside the interval it
    printed": a sampler whose answers are good and whose error bar is wrong is
    a sampler nobody can use to decide anything.
    """
    if not available():
        return Check("Hand versus range", "eval7",
                     "does the sampler agree with an exact solve?", "not run",
                     detail="eval7 is not installed")
    rng = random.Random(seed)
    rows, worst_sigma = [], 0.0
    for hero, rng_text, board in _RANGE_SPOTS:
        h, b = _cards(hero), _cards(board)
        combos = _combos_from_e7(rng_text, dead=h + b)
        got = eq.range_equity(h, [combos], board=b, rng=rng, iters=iters,
                              dead=h + b)
        theirs = _reference_range_equity(h, combos, b)
        sigma = abs(got[0] - theirs) / (got.error or 1e-9)
        worst_sigma = max(worst_sigma, sigma)
        rows.append({"spot": f"{hero} vs {rng_text} on {board}",
                     "ours": round(got[0] * 100, 3),
                     "theirs": round(theirs * 100, 3),
                     "diff": round((got[0] - theirs) * 100, 3),
                     "sigma": round(sigma, 2)})
    # Three standard errors is the usual line and the error is an upper bound
    # (worst-case p=0.5), so anything outside it is a real disagreement.
    return Check(
        "Hand versus range", "eval7's evaluator, enumerated here",
        "does the sampler agree with an exact solve, inside its own error bar?",
        "pass" if worst_sigma <= 3.0 else "fail",
        samples=len(_RANGE_SPOTS), worst=worst_sigma, tolerance=3.0,
        detail=(f"Worst gap {worst_sigma:.2f} standard errors, over "
                f"{iters:,} samples a spot."),
        rows=rows)


def _combos_from_e7(text, dead):
    """The combinations of an eval7 range string, weighted, in this repo's cards."""
    e7 = _e7()
    dead = set(dead)
    out = []
    for hand, weight in e7.HandRange(text).hands:
        cards = [parse_card(str(c)) for c in hand]
        if cards[0] in dead or cards[1] in dead:
            continue
        out.append((cards[0], cards[1], float(weight)))
    return out


def combo_equities_against_eval7(seed=3):
    """The per-holding pass, checked one holding at a time and in aggregate.

    This is the machinery the bucket split and every sizing number are built on,
    so it is checked twice: each combination against an exact hand-versus-hand
    solve, and the weighted average against an exact hand-versus-range solve.
    """
    if not available():
        return Check("Equity per holding", "eval7",
                     "is the per-holding pass right, one holding at a time?",
                     "not run", detail="eval7 is not installed")
    rows, worst = [], 0.0
    for hero, rng_text, board in _RANGE_SPOTS:
        h, b = _cards(hero), _cards(board)
        combos = _combos_from_e7(rng_text, dead=h + b)
        got = eq.combo_equities(h, combos, board=b, rng=random.Random(seed))
        if not got.exact:
            continue
        for (a, c, _w), mine in zip(combos, got):
            worst = max(worst, abs(mine - _reference_equity(h, [a, c], b)))
        pooled = eq.combined(got, combos)
        exact = _reference_range_equity(h, combos, b)
        rows.append({"spot": f"{hero} vs {rng_text} on {board}",
                     "combos": len(combos),
                     "ours": round(pooled * 100, 4),
                     "theirs": round(exact * 100, 4),
                     "diff": round((pooled - exact) * 100, 4)})
        worst = max(worst, abs(pooled - exact))
    return Check(
        "Equity per holding", "eval7's evaluator, enumerated here",
        "is the per-holding pass right, one holding at a time and pooled?",
        "pass" if worst <= 1e-9 else "fail",
        samples=len(rows), worst=worst * 100, tolerance=1e-7,
        detail=("Exact on every street that enumerates, both per combination "
                "and pooled." if worst <= 1e-9
                else f"Worst disagreement {worst * 100:.6f} points."),
        rows=rows)


def reference_against_eval7_sampler(samples=200000, seed=1):
    """Is the reference enumeration itself right?

    Everything above is measured against ``_reference_equity``, which is code
    written for this file and therefore code that can be wrong. eval7 ships its
    own sampler, ``py_all_hands_vs_range``, which shares nothing with that loop
    but the evaluator - so this runs it on the same spots and checks the two
    land on the same number. It is a sampler, so the band is its own error
    rather than zero.
    """
    if not available():
        return Check("The reference itself", "eval7's own sampler",
                     "is the enumeration this file checks against right?",
                     "not run", detail="eval7 is not installed")
    e7 = _e7()
    rows, worst = [], 0.0
    for hero, villain, board in _EQUITY_SPOTS:
        h, v, b = _cards(hero), _cards(villain), _cards(board)
        mine = _reference_equity(h, v, b)
        got = e7.py_all_hands_vs_range(
            e7.HandRange("".join(hero.split())),
            e7.HandRange("".join(villain.split())), _to_e7(b), samples)
        theirs = list(got.values())[0]
        worst = max(worst, abs(mine - theirs))
        rows.append({"spot": f"{hero} vs {villain} on {board}",
                     "ours": round(mine * 100, 3),
                     "theirs": round(theirs * 100, 3),
                     "diff": round((mine - theirs) * 100, 3)})
    # Three standard errors on `samples` draws, in percentage points.
    band = 3 * 0.5 / (samples ** 0.5)
    return Check(
        "The reference itself", "eval7's own sampler",
        "is the enumeration every row above is checked against right?",
        "pass" if worst <= band else "fail",
        samples=len(_EQUITY_SPOTS), worst=worst * 100, tolerance=band * 100,
        detail=(f"Worst gap {worst * 100:.3f} points against a "
                f"{band * 100:.3f}-point sampling band at {samples:,} draws."),
        rows=rows)


# ------------------------------------------------------------- the charts


def charts_against_published():
    """Do the opening charts open as often as the solutions they claim to be?

    ``BASE_RFI`` is labelled ``solver``, which is a claim about where it came
    from, and a hand-typed range is the easiest thing in this repository to get
    quietly wrong - one boundary hand costs a point of width and nothing else
    notices. The equal-blind ranges are *deliberately* wider and are checked
    against the base rather than against the publication, because widening them
    is the thing ``ranges.py`` says it did.
    """
    rows, worst = [], 0.0
    for pos, published in PUBLISHED_RFI.items():
        base = ranges.lookup(("rfi",), pos, equal_blinds=False)
        ours = base.actions["raise"].pct()
        gap = ours - published
        worst = max(worst, abs(gap))
        wide = ranges.lookup(("rfi",), pos).actions["raise"].pct()
        rows.append({"spot": pos, "ours": round(ours, 1),
                     "theirs": round(published, 1), "diff": round(gap, 1),
                     "equal_blind": round(wide, 1),
                     "widened_by": round(wide - ours, 1)})
    return Check(
        "Opening ranges", "published 6-max 100bb solutions",
        "does a chart labelled `solver` open as often as the solve it names?",
        "pass" if worst <= CHART_TOLERANCE else "fail",
        samples=len(PUBLISHED_RFI), worst=worst, tolerance=CHART_TOLERANCE,
        detail=(f"Worst gap {worst:.1f} points of opening frequency, against a "
                f"{CHART_TOLERANCE:.0f}-point band."),
        rows=rows)


# ---------------------------------------------------------------- postflop


def texassolver_binary():
    return os.environ.get(TEXASSOLVER_ENV) or shutil.which("console_solver")


def postflop_against_texassolver():
    """The one that does not run, and says so.

    A postflop comparison needs a solver binary. This repository will not
    download one at test time and does not vendor one, so the honest report is
    ``not run`` with the command that would make it run - not a green row, and
    not a silent absence.
    """
    binary = texassolver_binary()
    if not binary:
        return Check(
            "Postflop strategy", "TexasSolver",
            "do the postflop numbers match a real solve?",
            "not run",
            detail=(
                "No solver binary. Build TexasSolver and point "
                f"{TEXASSOLVER_ENV} at its console_solver, or put that on the "
                "path. Until then nothing here is checked against a postflop "
                "solve, and `rollout.py`'s numbers are `model` - exact against "
                "these five bots, and not a claim about equilibrium."))
    return Check(
        "Postflop strategy", "TexasSolver",
        "do the postflop numbers match a real solve?",
        "not run",
        detail=(f"Found {binary}, but the comparison itself is not written "
                f"yet: `rollout.py` prices a size against a known opponent, "
                f"and a solver prices it against an equilibrium one, so the "
                f"two answer different questions and the harness has to say "
                f"which before it can compare anything."))


# -------------------------------------------------------------------- all


CHECKS = (
    evaluator_against_eval7,
    reference_against_eval7_sampler,
    equity_against_eval7,
    range_equity_against_eval7,
    combo_equities_against_eval7,
    charts_against_published,
    postflop_against_texassolver,
)


def run_all(quick=False):
    """Every check, as dictionaries. ``quick`` shrinks the slow samples."""
    out = []
    for fn in CHECKS:
        if quick and fn is evaluator_against_eval7:
            out.append(fn(n=2000).to_dict())
        elif quick and fn is reference_against_eval7_sampler:
            out.append(fn(samples=40000).to_dict())
        else:
            out.append(fn().to_dict())
    return out


def summary(checks):
    """One line for the top of the report."""
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    skipped = sum(1 for c in checks if c["status"] == "not run")
    return {"passed": passed, "failed": failed, "not_run": skipped,
            "total": len(checks),
            "eval7": available()}
