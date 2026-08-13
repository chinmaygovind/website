"""Generate the pool of names the bots race under.

A bot called "Bot 3" is furniture. A bot called `xX_kimi_Xx` or `LEWIS_44` is
somebody in the room, and the first time one of them beats you it matters more
than it should. That is the whole argument for this file.

So: a small list of racing names, put through the transformations a person
actually uses when a username is taken - case, separators, leetspeak, a number
that means something, a suffix off a streaming platform - and a second list of
racing words to pair them with. Seeded, so the committed `bot_names.txt` is
reproducible: re-running this on the same seed produces the same file, and a
diff means somebody changed the generator rather than the dice.

    python tools/bot_names.py            # rewrite drive/bot_names.txt
    python tools/bot_names.py --count 50 --print
"""

import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)

# Short enough to read on a nameplate over a car at racing distance, which is
# the tightest place one of these has to fit.
MAX_LEN = 16
DEFAULT_COUNT = 500
SEED = 20260811

# How many decorations to try on one drawn name before giving up on it.
TRIES = 60

# The pool is four small lists and every name in it is equally likely - see
# POOL. First names and surnames go in together and undifferentiated, because a
# username does not care which it started as: `senna_33` and `ayrton_33` are
# both somebody's handle.

# The 2026 grid, by team. Eleven teams under the new regulations, Cadillac
# being the eleventh.
F1 = """
lando norris oscar piastri
charles leclerc lewis hamilton
max verstappen isack hadjar
george russell kimi antonelli
fernando alonso lance stroll
pierre gasly franco colapinto
alex albon carlos sainz
liam lawson arvid lindblad
esteban ocon oliver bearman
nico hulkenberg gabriel bortoleto
sergio perez valtteri bottas
""".split()

# Five off the wall behind the grid. Kept to five on purpose: the whole point of
# a short pool is that you see the same handful of names all evening and start
# to know which of them is quick.
LEGENDS = """
ayrton senna michael schumacher fangio niki lauda alain prost
""".split()

# The people who will actually be in these rooms.
FRIENDS = """
chinmay govind krish mittal shreya satheesh sritanvi koneru reuben james
sahil barapatre nihar bagkar arjun suryawanshi celia tung peengineering
maxwell zhang roberto
""".split()

CARS = """
lightning mcqueen mater doc hudson sally chick hicks
""".split()

# Uniform means uniform over *this*, so a name that appears in two of the lists
# above must not get two tickets. Order-preserving so the file stays a readable
# diff rather than reshuffling on a set's whim.
POOL = list(dict.fromkeys(F1 + LEGENDS + FRIENDS + CARS))

# How often a name is paired with a racing word at all. Most usernames are a
# name and a number; the word is the occasional one, not the house style.
PAIR_SHARE = 0.08

RACING = """
apex drift turbo nitro boost slip tow kerb brake trail vmax redline downforce
podium pole stint undercut chicane hairpin camber
""".split()

TAG = """
gg xd ttv yt hd tv real official pro noob god king ace legend rookie sim
""".split()

# The numbers people put on the end of a username. Car numbers and years,
# because that is what they are: 44, 33 and 7 are somebody's, and 04 is when
# somebody was born.
NUMBERS = ["7", "44", "33", "1", "3", "16", "81", "4", "11", "55", "63", "14",
           "27", "22", "10", "77", "99", "01", "02", "03", "04", "05", "06",
           "07", "08", "09", "2004", "2005", "2006", "2007", "2008", "123",
           "360", "911", "918", "917", "488", "296"]

LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}


def _leet(word, rng, hard=False):
    out = []
    for ch in word:
        sub = LEET.get(ch)
        if sub and (hard or rng.random() < 0.5):
            out.append(sub)
        else:
            out.append(ch)
    return "".join(out)


def _case(word, rng):
    r = rng.random()
    if r < 0.45:
        return word
    if r < 0.7:
        return word.capitalize()
    if r < 0.85:
        return word.upper()
    # tHe OnE eVeRyBoDy HaS sEeN
    return "".join(c.upper() if i % 2 else c for i, c in enumerate(word))


def _one(rng, name=None):
    """One username, by whichever recipe the dice pick.

    The name comes first and the decoration second. Every name in `POOL` is
    equally likely; `PAIR_SHARE` of them then get a racing word and the rest are
    the ordinary case/number/leetspeak business.
    """
    if name is None:
        name = rng.choice(POOL)

    if rng.random() < PAIR_SHARE:
        word = rng.choice(RACING)
        if rng.random() < 0.5:
            return "%s_%s" % (_case(name, rng), _case(word, rng))
        return "%s%s" % (_case(word, rng), _case(name, rng))

    style = rng.random()
    if style < 0.16:
        return "xX_%s_Xx" % _case(name, rng)
    if style < 0.25:
        return "xX%sXx" % _case(name, rng)
    if style < 0.42:
        return "%s%s%s" % (_case(name, rng), rng.choice("._-"), rng.choice(NUMBERS))
    if style < 0.58:
        return "%s%s" % (_case(name, rng), rng.choice(NUMBERS))
    if style < 0.68:
        return "%s_%s" % (_case(name, rng), rng.choice(TAG))
    if style < 0.76:
        return "%s_%s" % (rng.choice(TAG), _case(name, rng))
    if style < 0.86:
        return _leet(name, rng, hard=True) + rng.choice(NUMBERS)
    if style < 0.93:
        return "%s_%s" % (_leet(_case(name, rng), rng), rng.choice(NUMBERS))
    if style < 0.97:
        return "the%s%s" % (name.capitalize(), rng.choice(NUMBERS))
    return "%s%s%s" % (name, "_" * rng.randint(1, 3), rng.choice(NUMBERS))


def generate(count=DEFAULT_COUNT, seed=SEED):
    """`count` distinct names, deterministically.

    Returns `(names, unused)`, where `unused` is every entry of `POOL` that
    reached the file zero times - see the retry below for why that can happen
    and why it is worth saying out loud.
    """
    rng = random.Random(seed)
    out, seen, used = [], set(), set()
    # Bounded rather than `while True`: the recipes above can only make so many
    # short names, and a generator that cannot reach the count should say so by
    # returning fewer rather than by spinning.
    for _ in range(count * 400):
        if len(out) >= count:
            break
        # The name is drawn once and then decorated up to TRIES times, rather
        # than redrawn on every miss. A long name fits only two or three of the
        # recipes under MAX_LEN, so redrawing would quietly turn "uniform over
        # POOL" into "uniform over the short half of POOL" - `peengineering`
        # would have been in the pool and never once in the file.
        name = rng.choice(POOL)
        for _ in range(TRIES):
            n = _one(rng, name)
            if len(n) > MAX_LEN or len(n) < 3:
                continue
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(n)
            used.add(name)
            break
    return out, [n for n in POOL if n not in used]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--print", dest="show", action="store_true",
                    help="print them instead of writing the file")
    args = ap.parse_args(argv)

    names, unused = generate(args.count, args.seed)
    if args.show:
        for n in names:
            print(n)
        return 0
    path = os.path.join(DRIVE, "bot_names.txt")
    with open(path, "w") as f:
        f.write("\n".join(names) + "\n")
    print("%d names -> %s" % (len(names), path))
    if len(names) < args.count:
        print("(the recipes ran out before %d; widen POOL or MAX_LEN)" % args.count)
    # A pool entry too long to survive MAX_LEN is in the list and not in the
    # game, which looks like nothing at all. Say it.
    if unused:
        print("(never fit MAX_LEN=%d, so nobody races as them: %s)"
              % (MAX_LEN, ", ".join(unused)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
