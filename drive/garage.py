"""What a car can look like, and who has earned which parts of that.

One module owns the whole vocabulary - the palette, every slot, and every gate
together with the sentence shown for it - because the text on a locked item and
the check that enforces it must not be able to drift apart. A locked row saying
"a gold on every track" over a rule that actually wants three is worse than no
text at all.

Three rules run through everything here:

**A car with no garage row must render exactly as it does today.** Every default
below is today's value, and `trim`, `rim` and `glass` default to ``None`` meaning
"whatever the renderer already did" rather than to a colour that happens to
match. That is what stops this being a silent restyle of everybody's car, and
`test_garage.py` pins it.

**Nothing here may touch the simulation.** Not ride height, not the collision
radius, not the wheel radius, not a gram of mass. A cosmetic that changed how the
car drives would make every time on the leaderboard mean something different
depending on what its driver was wearing, and the boards would quietly stop being
comparable. Everything in this file is paint, geometry that is bolted on, and
nothing else.

**A gate is checked where the livery is read, not where it is written.**
`resolve` is called on every path that sends a livery anywhere, so an item you
have not earned cannot be worn by POSTing it - see `validate` vs `resolve`.
"""

import hashlib
import json
import re

import tracks as tracks_mod

# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
# **HASH_COLORS is frozen at eight, and that is load-bearing.**
#
# `color_for` is `HASH_COLORS[sha1(name) % len(HASH_COLORS)]`, so the *length* of
# the list it indexes is part of the answer. Hashing over the full palette below
# would have changed the modulus from 8 to 18 and with it the default colour of
# every account that already exists - and, because a ghost is drawn in its
# owner's colour, the colour of every lap ever recorded. Nobody chose those
# colours but they have been theirs for months, and a deploy is not allowed to
# repaint them.
#
# So the hash keeps its own eight for ever. Whatever is offered beside them is
# choosable and nothing else. `test_the_hashed_colours_never_move` pins the list
# and a couple of known name -> colour answers.
HASH_COLORS = [
    "#e8453c",   # red
    "#3d8bfd",   # blue
    "#f2c94c",   # yellow
    "#27ae60",   # green
    "#bb6bd9",   # purple
    "#f2994a",   # orange
    "#56ccf2",   # cyan
    "#f178b6",   # pink
]

# Every body colour you are *offered*: the eight above, plus two. It was eighteen
# for a while and eighteen swatches is two rows, which reads as a paint chart
# rather than as a choice - see `RETIRED` for what happened to the other eight.
#
# **This list is checked rather than eyeballed** (`test_garage.py`, over `BODY_OK`):
# every pair is at least DELTA_E_MIN apart in CIELAB so no two cars are confusable
# mid-pack, every entry is at least BACKDROP_MIN from tarmac, kerb, grass, a bright
# sky, a dark sky and snow so no car can hide against the world, and every L* sits
# inside a band so nothing is near-black or near-white. That check does real work:
# it threw out a handsome forest green at 14.3 from grass, a sand at 10.8 from a
# bright sky, and a gold 13.8 from the yellow already here.
PALETTE = HASH_COLORS + [
    "#17bfa8",   # teal
    "#8195b0",   # slate
]

# **Offered yesterday and still worn today.** The palette was eighteen and is ten,
# because eighteen swatches is two rows and reads as a paint chart rather than as a
# choice. These eight are the ones that came out - and `validate` still *accepts*
# them, which is the whole point of their being here: dropping a colour from the
# offered list is a change to the garage, and dropping it from the accepted list
# would repaint the car of anybody wearing one, which is the single thing this file
# is least allowed to do. They are simply no longer suggested.
#
# The visibility rules apply to these exactly as they do to the ten, because a car
# in one is still a car on the road - `test_garage.py` checks `BODY_OK` and not
# `PALETTE`.
RETIRED = [
    "#9fd63c",   # lime
    "#7b6cf6",   # violet
    "#b3a4f7",   # lavender
    "#ff8f7a",   # salmon
    "#c65f2e",   # rust
    "#8f9e3d",   # olive
    "#967440",   # bronze
    "#b24d5c",   # rose
]

# Every body colour that may be *worn*, as against offered.
BODY_OK = frozenset(PALETTE) | frozenset(RETIRED)

GUEST_COLOR = HASH_COLORS[0]

# The colour the record is drawn in on the medals card, and so the colour the
# record's own badges are. Needed up here by the badge swatch list; `RECORD_GREEN`
# below is the name the rest of the project uses and is checked against
# `render.js`'s copy by `test_garage.py`.
RECORD_GREEN_HEX = "#55e08a"

# What the *detail* slots offer, which is not what the body offers.
#
# **The body's list is held to rules that these are not, and must not be.** Every
# bar below this comment exists so that no two cars are confusable and no car can
# hide against the world - which is a rule about the thing you see from thirty
# metres, and the trim, the rim, the glass and a stripe are not that thing. White
# is the case that makes it obvious: a white *car* vanishes against a kerb and
# against snow, and a white *stripe* is the most ordinary stripe there is. There
# was no white, black or grey anywhere in the garage, so a white stripe could not
# be had at all, and the glass tint could be pink.
#
# **A shortcut and not a rule.** `validate` still takes any hex in these slots
# (`FREE_HEX`), so these lists say what is worth offering rather than what is
# allowed - and the picker is right there for everything else.
#
# **Ten at most each, so every slot is one row.** They started at twenty-four - six
# neutrals in front of the whole body palette - which is two rows and reads as a
# paint chart. Ten is about as many as can be scanned without counting.
NEUTRALS = ["#ffffff", "#9aa3af", "#101216"]
BRIGHTS = ["#e8453c", "#3d8bfd", "#f2c94c", "#27ae60", "#bb6bd9", "#f2994a",
           "#56ccf2"]

SWATCHES = {
    # Trim and a stripe are contrast against the body: three neutrals - white,
    # grey, near-black - and seven colours across the wheel.
    "trim":   NEUTRALS + BRIGHTS,
    "stripe": NEUTRALS + BRIGHTS,
    # Metals, because that is what a wheel is, then four paint colours because a
    # painted rim is a thing people do. `#c9ced6` is the default and is second only
    # because white sorts before silver.
    "rim":    ["#ffffff", "#c9ced6", "#8d939c", "#101216", "#d9b45a", "#b5793f",
               "#e8453c", "#3d8bfd", "#f2c94c", "#27ae60"],
    # **Replaced rather than extended**, and it is the only one. Glass is dark and
    # neutral or it is not glass, so offering the body colours here was offering
    # eighteen wrong answers - the tint could be pink. Six darks from limo black up
    # to a light smoke, plus the two the real world actually uses: a green-blue and
    # a blue-grey. `#2b3240` is render.js's own default.
    "glass":  ["#101216", "#20242c", "#2b3240", "#1e2c33", "#26333f",
               "#3c4656", "#586475", "#7d8898"],
    # The roof is a second body colour, so it is offered the paints the car comes
    # in - a two-tone is two of those - plus white and black, which are the two
    # roofs real cars come with and which the body may not be. The eight hashed
    # ones rather than all ten, to keep it to a single row.
    "roof":   ["#ffffff", "#101216"] + list(HASH_COLORS),
    # A badge is a mark rather than a panel, so it wants the things a mark is: the
    # three it already uses by default, then metal, then contrast.
    "badge_color": [RECORD_GREEN_HEX, "#e8c34a", "#c98b4b", "#ffffff", "#101216",
                    "#c9ced6", "#e8453c", "#3d8bfd", "#f2c94c", "#56ccf2"],
}

# The bars the palette is held to, here rather than in the test so the intent
# lives with the data it constrains. **The body's only** - see `SWATCHES`.
DELTA_E_MIN = 22.0        # between any two body colours
BACKDROP_MIN = 24.0       # between a body colour and anything it is seen against
L_MIN, L_MAX = 45.0, 86.0

# What a car is seen against, sampled from the road colours in trackmesh.js and
# the extremes of the sky pool. Not exhaustive and not meant to be - it is the
# handful that a car actually disappears into.
BACKDROPS = {
    "tarmac": "#3f4450", "kerb": "#e6e6e6", "grass": "#4a7c3f",
    "bright sky": "#f0c9a0", "dark sky": "#241a3a", "snow": "#e8eef5",
}

# The colour the record is already drawn in on the medals card, and therefore the
# only colour the record's own badge can be. Green there because a record "is not
# a medal and cannot be won"; green here for the same reason.
RECORD_GREEN = RECORD_GREEN_HEX


def color_for(username):
    """The car colour that belongs to a person before they have chosen one.

    Hashed rather than handed out by seat, so somebody is one colour in a lobby,
    alone on a time trial, and as the ghost of a lap they set months ago - which
    is the whole reason it exists: a ghost has to be somebody's, and nothing
    stores whose colour it was.

    sha1 rather than `hash()`, which is salted per process and would give the
    same person a different colour after every restart. Over `HASH_COLORS` and
    never over `PALETTE` - see the note up there.
    """
    if not username:
        return GUEST_COLOR
    h = hashlib.sha1(username.lower().encode("utf-8")).hexdigest()
    return HASH_COLORS[int(h[:8], 16) % len(HASH_COLORS)]


# ---------------------------------------------------------------------------
# The slots
# ---------------------------------------------------------------------------
# `None` means "whatever the renderer does when nobody has said" and is not the
# same as a colour that happens to look the same: it is what makes an account
# with no row indistinguishable from one from before the garage existed.
# Two, and they are the two that mean something on a car made of flat-shaded
# boxes: paint that scatters and paint that reflects. Metallic and pearl were here
# and are gone - they were distinguishable from each other only after being tuned
# against each other, and three ways of saying "shiny" is two too many. A stored
# `metallic` or `pearl` therefore fails `validate` and falls back to matte, which is
# what every unknown value here has always done.
FINISHES = ("matte", "gloss")
LIVERIES = ("none", "centre", "twin", "band", "hoop", "halves", "fade",
            "pinstripe")
RIM_STYLES = ("stock", "spoke5", "spoke6", "mesh", "dish", "forged")
# A case of them rather than one. Each is a shape drawn on the bonnet in its own
# colour (`render.js`), and each is gated on something the database already
# records - which is the constraint that picked this set: `DriveStats` has wins,
# podiums, races, elo and distance, all written today, and `create_all` makes
# tables and not columns, so a badge wanting a new counter would need a migration
# by hand on the live box.
BADGES = ("none", "laurel", "checkers", "chevrons", "crown", "podium",
          "sunburst", "ribbon", "shield")

DEFAULTS = {
    "body": None,          # None -> color_for(username)
    # The spoiler, its stays and the darkened detail. Was called the trim and did
    # double duty: it painted these *and* the roof, whenever the `two_tone` toggle
    # was on. The roof is its own slot now, so this is only ever the wing.
    "trim": None,          # None -> body darkened, which is what render.js does
    # The cabin. `two_tone` was a boolean that put the roof in the trim colour, and
    # a colour picker says that and more, so the toggle is gone - picking a roof
    # colour *is* two-tone. A car wearing the old toggle goes back to a
    # body-coloured roof, which is the one repaint in this change and was asked for.
    "roof": None,          # None -> the body colour, i.e. no two-tone
    "rim": None,           # None -> the tyre colour, i.e. no rim at all
    "glass": None,         # None -> render.js's own #2b3240
    "stripe": None,        # None -> trim; only read when `livery` is not "none"
    # None -> the badge's own colour (`BADGE_COLOR` in render.js): green for the
    # three about records, gold for the sunburst, bronze for the podium. So the
    # meaning survives for anybody who does not go looking, and a gold laurel is
    # available to anybody who does.
    "badge_color": None,
    "finish": "matte",
    "livery": "none",
    "rim_style": "stock",
    "badge": "none",
}

FREE_HEX = ("trim", "roof", "rim", "glass", "stripe", "badge_color")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex_or_none(v):
    if not isinstance(v, str):
        return None
    v = v.strip().lower()
    return v if _HEX.match(v) else None


def validate(raw):
    """A livery with everything unrecognised thrown away.

    **Never raises.** A key this version has not heard of is a client from after
    the next deploy, or somebody poking the endpoint; either way the answer is to
    ignore it rather than to 500. A slot with a bad value falls back to its
    default, so a malformed body colour is today's car and not a black one.

    This does *not* check gates - that is `resolve`, and the split is deliberate:
    what somebody asked for is worth storing even if they cannot wear it yet, so
    that earning the item later puts it on without them having to ask twice.
    """
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    for k in FREE_HEX:
        h = _hex_or_none(raw.get(k))
        if h:
            out[k] = h
    body = _hex_or_none(raw.get("body"))
    # `BODY_OK` and not `PALETTE`: a colour that is no longer offered is still worn
    # by whoever chose it while it was. See `RETIRED`.
    if body in BODY_OK:
        out["body"] = body
    if raw.get("finish") in FINISHES:
        out["finish"] = raw["finish"]
    if raw.get("livery") in LIVERIES:
        out["livery"] = raw["livery"]
    if raw.get("rim_style") in RIM_STYLES:
        out["rim_style"] = raw["rim_style"]
    if raw.get("badge") in BADGES:
        out["badge"] = raw["badge"]
    return out


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
# Each entry is the slot it lives in, the value that is locked, and the sentence
# shown on the locked row. The sentence sits beside the predicate on purpose:
# they are one fact, and a UI that renders its own wording is a UI that will one
# day promise something the server refuses.
#
# Most are counters that only ever go up. Two are **records held right now**,
# which can be taken off you - so those are earned once and kept (`KEPT`), from
# either a live check or an already-recorded earn. That is also why they need no
# backfill: every current record holder qualifies the first time the garage looks
# at them, and the earn is written down then.
#
# `sunburst` deliberately shares `pinstripe`'s condition. Two items may want the
# same achievement, and a gold on every track is the thing the sunburst was asked
# for; giving it a different bar to keep the list tidy would be tidiness deciding
# what the game rewards.
GATES = {
    # `text` is what the *locked* chip says: the thing still to do. `done` is what
    # the *worn* chip says, and it is a separate string rather than the same one
    # bent into shape, because half of these are instructions ("Finish every
    # track") and half are noun phrases ("A gold on any 3 tracks") - anything that
    # reads them into one sentence gets half of them wrong. "Unlocked for finish
    # every track" is that failure.
    "pinstripe": {"slot": "livery",    "value": "pinstripe",
                  "text": "A gold on every track",
                  "done": "a gold on every track"},
    "forged":    {"slot": "rim_style", "value": "forged",
                  "text": "Finish every track",
                  "done": "finishing every track"},
    "laurel":    {"slot": "badge",     "value": "laurel",
                  "text": "Set a track record",
                  "done": "setting a track record"},
    "checkers":  {"slot": "badge",     "value": "checkers",
                  "text": "Win a multiplayer race",
                  "done": "winning a multiplayer race"},
    "podium":    {"slot": "badge",     "value": "podium",
                  "text": "Finish 10 races in the top three",
                  "done": "ten top-three finishes"},
    "chevrons":  {"slot": "badge",     "value": "chevrons",
                  "text": "Reach Ace rating",
                  "done": "reaching Ace rating"},
    "sunburst":  {"slot": "badge",     "value": "sunburst",
                  "text": "A gold on every track",
                  "done": "a gold on every track"},
    "ribbon":    {"slot": "badge",     "value": "ribbon",
                  "text": "Drive 100 km",
                  "done": "driving 100 km"},
    # **The one gate about the whole pool rather than about one lap.** It asked
    # for three track records at once, which is the same achievement the laurel
    # already names, three times over - so the top two badges on the list were
    # about the same thing and a driver quick on three tracks and nowhere else
    # outranked one who was second on every other one. Topping the Time Trial board
    # is the thing a crown should mean: best over the whole pool, by the board's
    # own scoring, which already counts a track you have never driven against
    # you. It is `KEPT` for the same reason the laurel is - it can be taken off
    # you tomorrow and the badge cannot.
    "crown":     {"slot": "badge",     "value": "crown",
                  "text": "Top the Time Trials leaderboard",
                  "done": "topping the Time Trials leaderboard"},
    # **This gate used to be the pearl finish.** Metallic and pearl went, and its
    # condition - three golds - is a real rung on the ladder that would otherwise
    # have earned nothing at all, so it moved to a badge rather than being deleted
    # with the finish it happened to be attached to.
    "shield":    {"slot": "badge",     "value": "shield",
                  "text": "A gold on any 3 tracks",
                  "done": "a gold on any 3 tracks"},
}

# The gates whose condition can stop being true, and which are therefore written
# down the first moment it is. Named here rather than in `app.py`, which used to
# carry the literal `{"laurel"}` - the vocabulary belongs with the vocabulary, and
# adding a second losable gate should not mean remembering a set in another file.
KEPT = frozenset({"laurel", "crown"})

# The bars for the counter gates. Out here because they are the numbers most
# likely to want moving after somebody has actually played, and hunting them
# through the predicates is how a threshold ends up disagreeing with its own text.
ACE_ELO = 1250            # `DriveStats.elo_tier`'s own boundary for "Ace"
PODIUMS_NEEDED = 10
RIBBON_METRES = 100_000   # a lap is roughly 0.9-2.8 km, so this is ~50-100 runs


def _golds(user):
    st = getattr(user, "drive", None)
    return (getattr(st, "golds", 0) or 0) + (getattr(st, "authors", 0) or 0)


def _stat(user, name, missing=0):
    """One counter off the stats row, or `missing` when there is no row.

    `getattr` twice rather than a join, so this works against the stub user
    `test_garage.py` hands `payload` - and so an account that has never finished
    anything reads as zero rather than as an exception.
    """
    st = getattr(user, "drive", None)
    v = getattr(st, name, None)
    return missing if v is None else v


# `DriveStats.elo`'s own default, repeated rather than imported because this
# module is deliberately free of `models` at import time. A fresh account is 1000
# and not 0, so defaulting to 0 would put "(0/1250)" on the chip for somebody who
# has simply never raced - a number that is wrong rather than just unflattering.
START_ELO = 1000


def _elo(user):
    return _stat(user, "elo", START_ELO)


def _tracks_finished(user):
    """How many tracks in the current pool this account has a time on.

    Scoped to the pool rather than to every row, so a time on a retired track
    cannot quietly count toward finishing the ones that exist.
    """
    from models import DriveTime
    pool = {t["slug"] for t in tracks_mod.TRACKS}
    rows = DriveTime.query.filter_by(user_id=user.id).all()
    return len({r.track for r in rows if r.track in pool})


def records_held():
    """**How many** records each account holds, as ``{user_id: count}``.

    A dict rather than a set, which reads the same for the one question anybody
    asks of it: `user.id in records_held()` is "do they hold one", exactly as it
    was. The counts are what the Records page shows beside a name.

    Computed **once for everybody** rather than once per person, because the
    obvious shape - "does this user hold a record" - is thirteen queries, and a
    room broadcasting its roster would ask it eight times for a hundred queries
    to draw eight cars. The answer is the same table whoever is asking.

    Same rule the Records page draws (`_records` in app.py): the lowest
    `time_ms` on a track, earliest on a tie, since whoever got there first holds
    it.
    """
    from models import DriveTime
    from sqlalchemy import func
    rows = (DriveTime.query.with_entities(DriveTime.track,
                                          func.min(DriveTime.time_ms))
            .group_by(DriveTime.track).all())
    out = {}
    for slug, best in rows:
        if slug not in tracks_mod.BY_SLUG:
            continue
        holder = (DriveTime.query.filter_by(track=slug, time_ms=best)
                  .order_by(DriveTime.updated_at.asc()).first())
        if holder and holder.user_id:
            out[holder.user_id] = out.get(holder.user_id, 0) + 1
    return out


def time_trial_board():
    """Every driver's Time Trial Score: their placing on each track, added up.

    Golf scoring, so **low is good** and a clean sweep of the pool scores one
    per track. Firsts everywhere but two tracks, and thirds on those, scores
    four over the sweep.

    Three rules make that sum well defined:

    - **A tie shares a place**, which is the answer `_my_rank_map` in app.py
      already gives for one track: a placing is the number of strictly faster
      laps plus one.
    - **A track you have never driven scores one worse than last on it** - the
      place you would take by turning up and being slowest. Adding up only the
      tracks somebody *has* driven would make driving fewer of them the way to a
      better score, which is the opposite of what a board is for: one lonely
      first place would beat a full sweep. A track *nobody* has driven is worth
      1 to everybody by the same rule, which cannot reorder anyone. The
      `driven` count is what keeps a big score from being a mystery.
    - **It is worked out on the way to the screen and stored nowhere.** A
      personal best does not only change *your* score, it demotes everybody you
      overtook, so a number kept per driver would have to rewrite most of the
      board on every lap and would be wrong for as long as one write path was
      missed. Derived from `drive_times` on each render it cannot go stale, and
      the whole pool is one query.

    Only laps driven alone against the clock are in `drive_times` at all (see
    `countsForTheBoard` in game.js), so nothing set in a room reaches this
    board either.

    **It lives here rather than in app.py because the crown is gated on it.** A
    gate has to ask the same question the board answers or the badge is about
    something nobody can see; `_time_trial_board` is now this plus the ordinals
    the page prints. `best` is an int here for the same reason - a placing is a
    number until something decides to say it out loud.
    """
    from models import db, DriveTime, User

    slugs = [t["slug"] for t in tracks_mod.TRACKS]
    pool = set(slugs)

    # One query for the lot. The join is what drops bots and any row whose
    # account is gone - the same two things the ratings board filters out.
    rows = (db.session.query(DriveTime.track, DriveTime.time_ms, User)
            .join(User, User.id == DriveTime.user_id)
            .filter(User.is_bot.isnot(True)).all())

    by_track = {}
    for track, ms, user in rows:
        if track in pool:      # a retired track's times are not places in the pool
            by_track.setdefault(track, []).append((ms, user))

    field = {}                 # slug -> how many drivers have a time there
    places = {}                # user id -> {slug: placing}
    who = {}                   # user id -> User
    for slug, entries in by_track.items():
        field[slug] = len(entries)
        place = {}
        for i, ms in enumerate(sorted(e[0] for e in entries)):
            place.setdefault(ms, i + 1)   # first index wins, so equal times tie
        for ms, user in entries:
            who[user.id] = user
            places.setdefault(user.id, {})[slug] = place[ms]

    board = [{"user": who[uid],
              "score": sum(mine.get(s, field.get(s, 0) + 1) for s in slugs),
              "driven": len(mine),
              "of": len(slugs),
              "best": min(mine.values())}
             for uid, mine in places.items()]

    # The score is the order. Everything after it in the key only decides who
    # comes first *inside* a tie, which the shared position below then hides.
    board.sort(key=lambda r: (r["score"], -r["driven"], r["user"].display.lower()))
    for i, r in enumerate(board):
        r["pos"] = (board[i - 1]["pos"] if i and r["score"] == board[i - 1]["score"]
                    else i + 1)
    return board


def time_trial_leaders():
    """The user ids sitting at the top of the Time Trial board.

    A **set**, because the board shares a position on an equal score and two
    people tied for first are both first - anything that broke that tie here
    would be handing the badge out on `display.lower()`, which is not an
    achievement.

    Empty when nobody has driven anything, so a fresh database gates the crown
    rather than granting it to a board of nobody.
    """
    return {r["user"].id for r in time_trial_board() if r["pos"] == 1}


def _counts(user, holders, leaders):
    """Every gate's (have, need), which is the one place either is worked out.

    `earned` and `progress` are both this, read two ways - "is have >= need" and
    "what are the two numbers". They used to be separate lists of predicates, and
    that is a shape where a threshold and the count shown beside it can disagree
    while both look right.
    """
    n = len(tracks_mod.TRACKS)
    golds = _golds(user)
    return {
        "shield":    (min(golds, 3), 3),
        "pinstripe": (min(golds, n), n),
        "forged":    (_tracks_finished(user), n),
        # A thing you have or have not done, so 0 or 1 out of 1 - "0/1 records"
        # would be a worse sentence than the text already on the chip, and the
        # garage only shows a count when `need` is more than one.
        "laurel":    (1 if user.id in holders else 0, 1),
        "checkers":  (min(_stat(user, "wins"), 1), 1),
        "podium":    (min(_stat(user, "podiums"), PODIUMS_NEEDED), PODIUMS_NEEDED),
        # Shown as a rating rather than as a distance from one, because Ace is a
        # number people know: "(1180/1250)" says where you are.
        "chevrons":  (min(_elo(user), ACE_ELO), ACE_ELO),
        "sunburst":  (min(golds, n), n),
        # In kilometres. Metres would put "(43102/100000)" on the chip, which is a
        # number nobody reads.
        "ribbon":    (min(int(_stat(user, "distance", 0.0) // 1000),
                          RIBBON_METRES // 1000), RIBBON_METRES // 1000),
        # First on the Time Trial board, which is 0 or 1 out of 1 for the same
        # reason the laurel is: it is a thing you are or are not, and "0/1
        # leaderboards" is a worse sentence than the text already on the chip.
        # Deliberately not "how far off the top you are" - the board's scores are
        # placings added up, so a bar from 47 to 12 would be measuring a distance
        # that has nothing to do with how much driving is left in it.
        "crown":     (1 if user.id in leaders else 0, 1),
    }


def earned(user, already=(), holders=None, leaders=None):
    """Which gated ids this account has, as a set.

    `already` is whatever has been written down before, and it matters for the
    `KEPT` gates and only those: the rest are recomputed from counters that cannot
    go down, so storing them would be a second copy of a fact the database holds.

    `holders` and `leaders` are `records_held()` and `time_trial_leaders()` when
    the caller is asking about more than one person and has worked them out once -
    a room's roster is eight people and one board.
    """
    if user is None:
        return set()
    if holders is None:
        holders = records_held()
    if leaders is None:
        leaders = time_trial_leaders()
    counts = _counts(user, holders, leaders)
    got = {gid for gid, (have, need) in counts.items() if have >= need}
    # A record can be taken off you and the badge for it cannot, so an earn that
    # was written down outranks a condition that has since stopped being true.
    return got | (set(already or ()) & KEPT)


def progress(user, holders=None, leaders=None):
    """How far along each gate this account is, as ``{gid: (have, need)}``.

    Only for the line the garage shows: "Pinstripe needs a gold on every track
    (9/12)". The gate's *text* is still the authority on what it wants - this is
    the count behind it, and both come out of `_counts`, so they cannot describe
    different rules.
    """
    if user is None:
        return {}
    return _counts(user,
                   records_held() if holders is None else holders,
                   time_trial_leaders() if leaders is None else leaders)


def resolve(livery, username, got):
    """The livery to actually draw: their choices, minus anything unearned.

    Called on **every** path that sends a livery to anybody - the play page, the
    roster, a ghost, a stored replay - which is what makes the gates real. A
    client can POST `finish: pearl` all day; it is stored, and it is replaced
    here until the golds arrive.
    """
    out = dict(validate(livery))
    for gid, g in GATES.items():
        if gid not in got and out.get(g["slot"]) == g["value"]:
            out[g["slot"]] = DEFAULTS[g["slot"]]
    if out["body"] is None:
        out["body"] = color_for(username)
    return out


def payload(user, livery, got, prog=None):
    """Everything the garage screen needs, in one object.

    Sent with the page as well as from `/api/garage`, so the car on screen is
    right on the first paint rather than after a request - the same reason
    `_track_payload` is embedded in the play page.

    `prog` is optional, and that is not laziness: this function is also called
    against a user object with no database behind it, and `progress` runs two
    queries. Made unconditional it would turn every caller into one that needs a
    session. A gate with no progress simply has no numbers on it.
    """
    prog = prog or {}
    return {
        "livery": resolve(livery, user.username if user else None, got),
        "palette": list(PALETTE),
        # What each detail slot offers, which is a different question from what
        # the body offers - see `SWATCHES`. Sent as its own key rather than
        # folded into `palette` because `palette` *is* the body's list, and the
        # rules it is checked against are the body's rules.
        "swatches": {k: list(v) for k, v in SWATCHES.items()},
        "finishes": list(FINISHES),
        "liveries": list(LIVERIES),
        "rim_styles": list(RIM_STYLES),
        "badges": list(BADGES),
        "defaults": dict(DEFAULTS),
        "record_green": RECORD_GREEN,
        # Every gate, whether it is open, the words for it, and how far along it
        # you are. Shown greyed with this text when it is shut, so the thing to
        # chase is visible - and the words come from here rather than from the
        # template, so they cannot say something the server will not honour.
        "gates": [dict(GATES[g], id=g, got=(g in got),
                       have=prog.get(g, (0, 0))[0], need=prog.get(g, (0, 0))[1])
                  for g in GATES],
    }


def dumps(livery):
    """Storage form. Only the keys that differ from the defaults.

    So a row is small, and so that a default which changes later moves the cars
    of everybody who never touched that slot - which is what a default is for.
    """
    v = validate(livery)
    return json.dumps({k: x for k, x in v.items() if DEFAULTS.get(k) != x},
                      separators=(",", ":"))


def loads(blob):
    try:
        return validate(json.loads(blob) if blob else {})
    except (ValueError, TypeError):
        return dict(DEFAULTS)
