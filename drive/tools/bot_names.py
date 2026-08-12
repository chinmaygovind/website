"""Generate the pool of names the bots race under.

A bot called "Bot 3" is furniture. A bot called `xX_kimi_Xx` or `LEWIS_44` is
somebody in the room, and the first time one of them beats you it matters more
than it should. That is the whole argument for this file.

So: a list of racing first names, put through the transformations a person
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

# The base pool: names off a grid, a banking or a bedroom wall. First names and
# surnames together and undifferentiated, because a username does not care which
# it started as - `senna_33` and `ayrton_33` are both somebody's handle.
BASE = """
ayrton senna alain prost michael schumacher lewis hamilton max verstappen
sebastian vettel fernando alonso kimi raikkonen mika hakkinen nigel mansell
damon hill graham nelson piquet niki lauda jackie stewart jim clark fangio
stirling moss james hunt jochen rindt gilles villeneuve jacques gerhard berger
rubens barrichello mark webber jenson button nico rosberg daniel ricciardo
lando norris charles leclerc george russell carlos sainz pierre gasly esteban
ocon yuki tsunoda oscar piastri sergio perez valtteri bottas felipe massa
juanpablo montoya david coulthard eddie irvine martin brundle johnny herbert
jean alesi olivier panis jarno trulli giancarlo fisichella heikki kovalainen
robert kubica nick heidfeld romain grosjean nico hulkenberg kevin magnussen
lance stroll alex albon guanyu zhou logan sargeant franco colapinto liam lawson
ollie bearman isack hadjar kimi antonelli jack doohan gabriel bortoleto
keke rosberg jody scheckter emerson fittipaldi ronnie peterson didier pironi
elio deangelis stefan bellof riccardo patrese rene arnoux patrick tambay
dale earnhardt jeff gordon richard petty jimmie johnson darrell waltrip
cale yarborough bobby allison davey bill elliott kyle busch kevin harvick
tony stewart joey logano denny hamlin martin truex brad keselowski ryan blaney
kyle larson alex bowman austin dillon bubba wallace terry labonte dale jarrett
mark martin ricky rudd matt kenseth carl edwards greg biffle ryan newman
lightning mcqueen mater doc hudson hornet sally ramone flo luigi guido sarge
fillmore chick hicks strip weathers dinoco cruz ramirez jackson storm smokey
francesco bernoulli holley shiftwell finn mcmissile miles axlerod sheriff
dan gurney mario andretti aj foyt al unser bobby rahal helio castroneves
dario franchitti scott dixon will power josef newgarden alex palou danica
jacky ickx derek bell tom kristensen allan mcnish michele alboreto
sebastien loeb ogier tommi makinen colin mcrae richard burns petter solberg
kalle rovanpera ott tanak ken block travis pastrana juha kankkunen ari vatanen
bjorn waldegard didier auriol marcus gronholm valentino rossi marc marquez
giacomo agostini mike hailwood barry sheene kenny roberts
""".split()

# The people who will actually be in these rooms. Deliberately a **tiny** slice
# of the pool - see FRIEND_SHARE - so that turning up on the grid against one is
# a thing that happens now and then rather than a room full of your mates.
FRIENDS = """
chinmay govind krish mittal reuben james sahil barapatre nihar bagkar
shreya satheesh sritanvi koneru ameya chaudhari maxwell zhang roberto tamez
danny gallagher celia tung peenengineering
""".split()

# How much of the pool comes from that list. 4% of 500 is about twenty names.
FRIEND_SHARE = 0.04

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


def _one(rng):
    """One username, by whichever recipe the dice pick.

    The name comes first and the decoration second, which is the order that
    keeps the two shares above meaning what they say: `FRIEND_SHARE` of these
    are somebody's actual mate, `PAIR_SHARE` of them get a racing word, and the
    rest are the ordinary case/number/leetspeak business.
    """
    name = rng.choice(FRIENDS if rng.random() < FRIEND_SHARE else BASE)

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
    """`count` distinct names, deterministically."""
    rng = random.Random(seed)
    out, seen = [], set()
    # Bounded rather than `while True`: the recipes above can only make so many
    # short names, and a generator that cannot reach the count should say so by
    # returning fewer rather than by spinning.
    for _ in range(count * 400):
        if len(out) >= count:
            break
        n = _one(rng)
        if len(n) > MAX_LEN or len(n) < 3:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--print", dest="show", action="store_true",
                    help="print them instead of writing the file")
    args = ap.parse_args(argv)

    names = generate(args.count, args.seed)
    if args.show:
        for n in names:
            print(n)
        return 0
    path = os.path.join(DRIVE, "bot_names.txt")
    with open(path, "w") as f:
        f.write("\n".join(names) + "\n")
    print("%d names -> %s" % (len(names), path))
    if len(names) < args.count:
        print("(the recipes ran out before %d; widen FIRST or MAX_LEN)" % args.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
