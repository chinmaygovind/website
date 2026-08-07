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
# So the hash keeps its own eight for ever. The ten below it are choosable and
# nothing else. `test_the_hashed_colours_never_move` pins the list and a couple
# of known name -> colour answers.
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

# Every body colour you may choose. The eight above, then ten more.
#
# **This list is checked rather than eyeballed** (`test_garage.py`): every pair is
# at least DELTA_E_MIN apart in CIELAB so no two cars are confusable mid-pack,
# every entry is at least BACKDROP_MIN from tarmac, kerb, grass, a bright sky, a
# dark sky and snow so no car can hide against the world, and every L* sits
# inside a band so nothing is near-black or near-white. That check does real work:
# it threw out a handsome forest green at 14.3 from grass, a sand at 10.8 from a
# bright sky, and a gold 13.8 from the yellow already here.
#
# The tightest pair that survives is orange/rust at 23.3, against 29.8 for the
# original eight alone - a widened palette is necessarily a closer-packed one, and
# 23 is still several times the distance at which two colours read as different.
PALETTE = HASH_COLORS + [
    "#17bfa8",   # teal
    "#9fd63c",   # lime
    "#7b6cf6",   # violet
    "#b3a4f7",   # lavender
    "#ff8f7a",   # salmon
    "#8195b0",   # slate
    "#c65f2e",   # rust
    "#8f9e3d",   # olive
    "#967440",   # bronze
    "#b24d5c",   # rose
]

GUEST_COLOR = HASH_COLORS[0]

# The bars the palette is held to, here rather than in the test so the intent
# lives with the data it constrains.
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
RECORD_GREEN = "#55e08a"


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
FINISHES = ("matte", "gloss", "metallic", "pearl")
LIVERIES = ("none", "centre", "twin", "band", "hoop", "halves", "fade",
            "pinstripe")
RIM_STYLES = ("stock", "spoke5", "spoke6", "mesh", "dish", "forged")
BADGES = ("none", "laurel")

DEFAULTS = {
    "body": None,          # None -> color_for(username)
    "trim": None,          # None -> body darkened, which is what render.js does
    "rim": None,           # None -> the tyre colour, i.e. no rim at all
    "glass": None,         # None -> render.js's own #2b3240
    "stripe": None,        # None -> trim; only read when `livery` is not "none"
    "finish": "matte",
    "livery": "none",
    "rim_style": "stock",
    "two_tone": False,
    "badge": "none",
}

FREE_HEX = ("trim", "rim", "glass", "stripe")
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
    if body in PALETTE:
        out["body"] = body
    if raw.get("finish") in FINISHES:
        out["finish"] = raw["finish"]
    if raw.get("livery") in LIVERIES:
        out["livery"] = raw["livery"]
    if raw.get("rim_style") in RIM_STYLES:
        out["rim_style"] = raw["rim_style"]
    if raw.get("badge") in BADGES:
        out["badge"] = raw["badge"]
    out["two_tone"] = bool(raw.get("two_tone"))
    return out


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
# Each entry is the slot it lives in, the value that is locked, and the sentence
# shown on the locked row. The sentence sits beside the predicate on purpose:
# they are one fact, and a UI that renders its own wording is a UI that will one
# day promise something the server refuses.
#
# Three are counters that only ever go up. The fourth is the only one anybody can
# take off you, and it is **earned once and kept**: `holds_record_now` or an
# already-recorded earn. That is also why it needs no backfill - every current
# record holder qualifies the first time the garage looks at them, and the earn
# is written down then.
GATES = {
    "pearl":     {"slot": "finish",    "value": "pearl",
                  "text": "A gold on any 3 tracks"},
    "pinstripe": {"slot": "livery",    "value": "pinstripe",
                  "text": "A gold on every track"},
    "forged":    {"slot": "rim_style", "value": "forged",
                  "text": "Finish every track"},
    "laurel":    {"slot": "badge",     "value": "laurel",
                  "text": "Set a track record"},
}


def _golds(user):
    st = getattr(user, "drive", None)
    return (getattr(st, "golds", 0) or 0) + (getattr(st, "authors", 0) or 0)


def _tracks_finished(user):
    """How many tracks in the current pool this account has a time on.

    Scoped to the pool rather than to every row, so a time on a retired track
    cannot quietly count toward finishing the twelve that exist.
    """
    from models import DriveTime
    pool = {t["slug"] for t in tracks_mod.TRACKS}
    rows = DriveTime.query.filter_by(user_id=user.id).all()
    return len({r.track for r in rows if r.track in pool})


def record_holders():
    """Every account holding the fastest lap on any track in the pool.

    Computed **once for everybody** rather than once per person, because the
    obvious shape - "does this user hold a record" - is thirteen queries, and a
    room broadcasting its roster would ask it eight times for a hundred queries
    to draw eight cars. The answer is the same set whoever is asking.

    Same rule the Records page draws (`_records` in app.py): the lowest
    `time_ms` on a track, earliest on a tie, since whoever got there first holds
    it.
    """
    from models import DriveTime
    from sqlalchemy import func
    rows = (DriveTime.query.with_entities(DriveTime.track,
                                          func.min(DriveTime.time_ms))
            .group_by(DriveTime.track).all())
    out = set()
    for slug, best in rows:
        if slug not in tracks_mod.BY_SLUG:
            continue
        holder = (DriveTime.query.filter_by(track=slug, time_ms=best)
                  .order_by(DriveTime.updated_at.asc()).first())
        if holder and holder.user_id:
            out.add(holder.user_id)
    return out


def earned(user, already=(), holders=None):
    """Which gated ids this account has, as a set.

    `already` is whatever has been written down before, which only matters for
    `laurel`: the other three are recomputed from counters that cannot go down,
    so storing those would be a second copy of a fact the database already holds.

    `holders` is `record_holders()` when the caller is asking about more than one
    person and has worked it out once - see why up there.
    """
    if user is None:
        return set()
    got = set()
    if _golds(user) >= 3:
        got.add("pearl")
    if _golds(user) >= len(tracks_mod.TRACKS):
        got.add("pinstripe")
    if _tracks_finished(user) >= len(tracks_mod.TRACKS):
        got.add("forged")
    if holders is None:
        holders = record_holders()
    if "laurel" in (already or ()) or user.id in holders:
        got.add("laurel")
    return got


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


def payload(user, livery, got):
    """Everything the garage screen needs, in one object.

    Sent with the page as well as from `/api/garage`, so the car on screen is
    right on the first paint rather than after a request - the same reason
    `_track_payload` is embedded in the play page.
    """
    return {
        "livery": resolve(livery, user.username if user else None, got),
        "palette": list(PALETTE),
        "finishes": list(FINISHES),
        "liveries": list(LIVERIES),
        "rim_styles": list(RIM_STYLES),
        "badges": list(BADGES),
        "defaults": dict(DEFAULTS),
        "record_green": RECORD_GREEN,
        # Every gate, whether it is open, and the words for it. Shown greyed with
        # this text when it is shut, so the thing to chase is visible - and the
        # words come from here rather than from the template, so they cannot say
        # something the server will not honour.
        "gates": [dict(GATES[g], id=g, got=(g in got)) for g in GATES],
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
