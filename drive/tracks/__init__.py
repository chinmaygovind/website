"""The track pool: one folder per track, discovered rather than listed.

A track is a **directory**::

    tracks/costco/
        track.py      what it is, and the geometry
        palette.py    what it looks like            (optional)
        scenery.js    mesh code only this track has (optional)

Drop one in and it is in the game - on the home page, in the switcher, on the
leaderboard, in a room. Nothing else has to be edited, which is the entire point:
adding Costco used to mean editing seven files in three languages, two of which
were a Python constant and a JavaScript constant that had to agree with each other
and were held together by a test that scraped one with a regex.

What `track.py` must define
---------------------------
``slug``, ``name``, ``difficulty`` (1-5), and ``build(b)`` - which
takes a `Builder` and lays the road. Everything else is optional:

    ground      world Y of the solid ground plane. ``None`` means the track
                floats in the void and leaving the road is a fall. Default None.
    order       where it sits in the pool. Default 500, ties broken by slug.
    closed      True for a lap: the finish line *is* the start line, and
                `solver` closes the ribbon on itself. Default False.
    exposed     True to declare that running wide is *meant* to be unrecoverable,
                so `test_barriers_are_opt_in` stops asking for barriers.
    scenery     True if the folder ships a `scenery.js`. Checked, so a typo in
                the filename is an error rather than a track with no building.
    medals      ``(gold, silver, bronze)`` in seconds, cut from the board by
                `tools/set_medals.py`. **Generated, not authored** - the same
                deal `hotlap.json` has. Omit it and the three times are derived
                from the ribbon instead, so a brand new track is playable and
                medalled on its first run; run the tool once it has been driven.

Everything derived stays derived
--------------------------------
``pole_side``, ``gate_ceil`` and the ideal lap are all computed here from the
ribbon. A new track gets them for free and cannot get them wrong - and retuning
the car in `tuning.py` retunes the ideal lap on every track, which is why there
is no second copy of `ACCEL` anywhere.

The medal times are the **one exception**, and it was earned rather than chosen.
They were derived too, as `ideal` times a global multiplier, and `ideal` turns
out to be a fine estimate of a lap and a poor estimate of a standard: against the
records people actually set it is out by 0.744 to 0.888 of itself *depending on
the track*. No single multiplier spans that. The one that shipped gave gold to
92.7% of every time ever set here, and tightening it enough to fix that left
three tracks with no attainable gold at all. So a track that has been played
declares its own, cut from the board by `tools/set_medals.py`; a track that has
not falls back to the derivation, which is what keeps "a track is one folder"
true.

Order matters more than it looks
--------------------------------
``TRACKS[0]`` is the fallback track in five places in `app.py`, and the home page
is asserted to list the pool in order. So discovery is sorted by ``order`` and
then ``slug``, never by whatever the filesystem happened to return, and a
duplicate slug is an error rather than a coin flip.
"""

import hashlib
import importlib
import logging
import os
import pickle
import tempfile

from tracks import look, solver

# This package is a façade: most of what follows is re-exported rather than used
# here, so that `tracks.GATE_CEIL_MAX` works and callers do not have to know
# which submodule a constant lives in. `validate_track.py` and `test_tracks.py`
# read them off this name. A linter told to strip unused imports would empty
# both lines and break those callers, hence the `noqa` - the names are the
# interface, and being unused *inside* this file is the normal case for one.
from tracks.builder import (CELL, LEVEL, ROAD_W, STATION, Builder,     # noqa: F401
                            PROF_BLEND, PROF_SAMPLES, rise_at, surface_at)
from tracks.checks import (CROSS_CLEAR, FIRST_TURN_DEG, GATE_CEIL_MARGIN,  # noqa: F401
                           GATE_CEIL_MAX, GATE_CEIL_MIN, crossings,
                           gate_ceiling, pole_side, self_proximity)

HERE = os.path.dirname(os.path.abspath(__file__))
_log = logging.getLogger(__name__)

# Folders that failed to load, as `{slug: exception}`. Populated by `_assemble`
# and asserted empty by `test_every_track_folder_loads`, which is what stops a
# track like this reaching main. See the note there for why a bad track is
# excluded rather than fatal.
BROKEN = {}

# Where a track ends up when it does not say. Middle of the range, so a track can
# be pushed either way without renumbering the pool.
DEFAULT_ORDER = 500

# ---------------------------------------------------------------------------
# The built pool, cached on disk
# ---------------------------------------------------------------------------
#
# **Building the pool is 4 seconds and it is the same 4 seconds every time.** A
# track is a pure function of its own two source files and of the shared code
# that interprets them - `builder`, `solver`, `checks`, `look`, `laptime`,
# `tuning` - so the answer only changes when one of those does. Most of the cost
# is not the ribbon (0.9s for all 22) but what is derived from it: `laptime`'s
# racing line relaxes 320 iterations over every station, and `gate_ceiling`
# tracks every gate across the whole map.
#
# That was 4 seconds on `import tracks`, which is paid by every pytest process,
# every `verify.py` in production, and every one of the sixteen xdist workers -
# and twelve more times over in `test_track_folders.py`, which calls `_assemble`
# once per broken-folder case.
#
# So each finished track is pickled under `__pycache__`, keyed on a hash of
# everything that can change it. It sits beside the `.pyc` files for the same
# reason they do: derived from the source, worthless if the source moves, and
# already ignored by git. A stale entry is not possible rather than unlikely -
# the key *is* the content - and a corrupt or unreadable one is a miss, so the
# worst case is the 4 seconds this replaces.
_CACHE_DIR = os.path.join(HERE, "__pycache__", "pool")

# Bump when the *shape* of a cached dict changes in a way the source hash cannot
# see - a new derived key, a different type. The file hashes below cover
# everything else.
_CACHE_VERSION = 1

_code_stamp_cached = None


def _code_stamp():
    """A hash of every file that can change how any track comes out.

    The shared interpreters, not the track folders - those are hashed per track.
    `laptime` and `tuning` are in here because the ideal lap and the medals
    derived from it are cached too, so retuning the car has to invalidate every
    entry; that is the same rule the module docstring states for `tuning.py`.
    """
    global _code_stamp_cached
    if _code_stamp_cached is None:
        h = hashlib.sha1()
        h.update(b"v%d" % _CACHE_VERSION)
        up = os.path.dirname(HERE)
        for path in ([os.path.join(HERE, n) for n in sorted(os.listdir(HERE))
                      if n.endswith(".py")]
                     + [os.path.join(up, "laptime.py"), os.path.join(up, "tuning.py")]):
            try:
                with open(path, "rb") as f:
                    h.update(f.read())
            except OSError:
                # A file that cannot be read is a key that cannot be trusted, so
                # make it one nothing will match rather than one that ignores it.
                h.update(os.urandom(16))
        _code_stamp_cached = h.hexdigest()
    return _code_stamp_cached


def _cache_key(folder):
    """The cache key for one track folder, or None if it cannot be read.

    `track.py` and `palette.py` are the whole of what a folder contributes to
    the built dict. `scenery.js` is deliberately *not* in here: it is read on
    demand by `scenery_source` and never enters the track document - `stamp()`
    hashes it separately, for the different question of whether a save state is
    still valid.
    """
    h = hashlib.sha1()
    h.update(_code_stamp().encode())
    h.update(folder.encode())
    for name in ("track.py", "palette.py"):
        path = os.path.join(HERE, folder, name)
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except FileNotFoundError:
            h.update(b"-")
        except OSError:
            return None
    return h.hexdigest()


def _cache_load(key):
    """The finished track dict for `key`, or None.

    A fresh object every time, because the caller owns what it gets back -
    `_time_it` writes into it, and `from_document` and the maker both hand
    track dicts around expecting to be able to. Unpickling *is* the copy, and it
    is 13ms for the whole pool against the 4 seconds of building it.
    """
    if key is None:
        return None
    try:
        with open(os.path.join(_CACHE_DIR, key), "rb") as f:
            return pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError,
            ValueError):
        return None


def _cache_store(key, t):
    """Write one finished track under its key. Never raises.

    Written to a uniquely named temporary and renamed, because sixteen xdist
    workers cold-start on the same cache directory at once and `os.replace` is
    atomic: a reader either sees the previous file or the whole new one, never
    half of one. A failure here costs the 4 seconds and nothing else, so it is
    swallowed rather than allowed to take the pool down - a read-only checkout
    must still be able to build its tracks.
    """
    if key is None:
        return
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(t, f, pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, os.path.join(_CACHE_DIR, key))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except (OSError, pickle.PicklingError):
        pass


# Keys for the tracks this process actually built, so the loop at the foot of
# the module can write them once they are complete. A track is only cacheable
# when it has its `ideal` and `medals` on it, and those need `laptime`, which
# cannot be imported until the ribbons exist - see the import further down.
_to_cache = {}


def _discover():
    """Every folder in `tracks/` that has a `track.py`, by name.

    Names rather than imported modules, so that importing one is inside
    `_assemble`'s per-track guard: a `track.py` with a syntax error in it is the
    single likeliest thing a first-time contributor will push, and it must not be
    able to stop the other fifteen tracks loading.

    A folder without a `track.py` is not a track - most likely somebody's scratch
    directory - so it is skipped silently rather than reported as broken.
    """
    out = []
    for entry in sorted(os.listdir(HERE)):
        d = os.path.join(HERE, entry)
        if not os.path.isdir(d) or entry.startswith((".", "_")):
            continue
        if not os.path.exists(os.path.join(d, "track.py")):
            continue
        out.append(entry)
    return out


def _meta(mod, folder):
    """Read a track module's declarations, with a clear error for each mistake.

    Named errors rather than an AttributeError, because the reader of this message
    is often somebody adding their first track and the difference between
    "``name`` is missing from tracks/quarry/track.py" and
    "``module 'tracks.quarry.track' has no attribute 'name'``" is most of whether
    they can fix it without reading this file.
    """
    def need(attr):
        if not hasattr(mod, attr):
            raise ValueError(
                "tracks/%s/track.py is missing `%s`. A track needs slug, name, "
                "difficulty and build(b)." % (folder, attr))
        return getattr(mod, attr)

    slug = need("slug")
    if slug != folder:
        raise ValueError(
            "tracks/%s/track.py says slug = %r. The folder name is the slug - it "
            "is in the URL (/solo/%s), the leaderboard and every saved time, so "
            "the two cannot differ." % (folder, slug, folder))
    if not callable(getattr(mod, "build", None)):
        raise ValueError("tracks/%s/track.py needs `build(b)`" % folder)

    diff = need("difficulty")
    if not (isinstance(diff, int) and 1 <= diff <= 5):
        raise ValueError("tracks/%s/track.py: difficulty must be 1-5, not %r"
                         % (folder, diff))

    return {
        "slug": slug,
        "name": need("name"),
        "difficulty": diff,
        "ground": getattr(mod, "ground", None),
        "order": getattr(mod, "order", DEFAULT_ORDER),
        # Where the turtle starts and what it starts with. `rails` is the
        # *default* for sections that do not say otherwise: a track floating in
        # the void wants it on, because without ground under it running wide is a
        # fall rather than a penalty. `origin` only matters when a track is
        # authored against something in world space - Sandy Cove starts at
        # z = -20 because its road is placed relative to a fixed waterline.
        "width": getattr(mod, "width", ROAD_W),
        "rails": bool(getattr(mod, "rails", False)),
        "origin": tuple(getattr(mod, "origin", (0.0, 0.0, 0.0, 0.0))),
        "closed": bool(getattr(mod, "closed", False)),
        "exposed": bool(getattr(mod, "exposed", False)),
        "wants_scenery": bool(getattr(mod, "scenery", False)),
        # A placement list, if the folder declares one. Drawn by `placeAll` in
        # `buildTrack`, which is the same interpreter a player's track goes
        # through - so a pool track can use the library too, and a community
        # track adopted into the pool by `tools/adopt_track.py` keeps its
        # scenery without anything being rewritten as code.
        "placed": getattr(mod, "placed", None),
        # Three medal times in seconds, fastest first, or None to derive them
        # from the ribbon. Cut from the board by `tools/set_medals.py` - see
        # `_medal_times` below for why a track that has been played gets to
        # overrule the simulation about how quick it is.
        "medal_times": _medals_decl(folder, getattr(mod, "medals", None)),
        "build": mod.build,
        "module": mod,
    }


def _medals_decl(folder, raw):
    """Validate an optional `medals = (gold, silver, bronze)` declaration."""
    if raw is None:
        return None
    try:
        v = tuple(float(x) for x in raw)
    except (TypeError, ValueError):
        raise ValueError("tracks/%s/track.py: medals must be three numbers "
                         "(gold, silver, bronze) in seconds, not %r"
                         % (folder, raw))
    if len(v) != 3:
        raise ValueError("tracks/%s/track.py: medals needs exactly three times, "
                         "got %d" % (folder, len(v)))
    if not (v[0] < v[1] < v[2]):
        raise ValueError("tracks/%s/track.py: medals must be strictly "
                         "increasing (gold, silver, bronze), got %r"
                         % (folder, v))
    return v


def _assemble():
    """Every track folder, built. Ones that fail are recorded, not raised.

    **A bad track is left out of the pool rather than taking the app down with
    it**, and the whole of that decision is about blast radius. Raising is the
    tidier-looking choice and it means one contributor's typo stops the other
    fifteen tracks loading, stops the server booting, and stops *pytest collecting
    any test in the suite* - so the person who has to fix it cannot run anything,
    including the test that would tell them what is wrong.

    It is not silent. Each failure warns with the folder name and the reason, and
    `test_tracks.py::test_every_track_folder_loads` fails on `BROKEN`, so a pull
    request carrying one cannot go green. The failure just stays inside the track
    it belongs to.

    Three things can go wrong and all three are guarded per track, because the
    likeliest of them is the first: **importing** `track.py` (a syntax error, or
    anything that raises at module level), **reading** its declarations (a missing
    `name`, a slug that disagrees with the folder), and **building** the ribbon (a
    loop that will not close).
    """
    broken, entries = {}, []
    for folder in _discover():
        try:
            mod = importlib.import_module("tracks.%s.track" % folder)
            entries.append(_meta(mod, folder))
        except Exception as exc:
            broken[folder] = exc

    seen = {}
    for e in list(entries):
        if e["slug"] in seen:
            # Unreachable while `_meta` insists slug == folder and folder names
            # are unique on a filesystem, which is belt and braces rather than
            # dead weight: the day a track is allowed to name itself, this is
            # what stops two of them owning one URL.
            broken[e["slug"]] = ValueError(
                "two folders claim the slug %r. A slug is in the URL and in every "
                "saved time, so it has to be unique." % e["slug"])
            entries.remove(e)
            continue
        seen[e["slug"]] = e
    entries.sort(key=lambda e: (e["order"], e["slug"]))

    out = []
    for e in entries:
        try:
            out.append(_one(e))
        except Exception as exc:
            broken[e["slug"]] = exc

    for slug, exc in sorted(broken.items()):
        _log.warning("tracks/%s did not load and is not in the pool: %s", slug, exc)

    BROKEN.clear()
    BROKEN.update(broken)
    if not out:
        raise ValueError(
            "no tracks loaded from %s. A track is a folder with a track.py in it; "
            "%d folder(s) were found and every one of them failed: %s"
            % (HERE, len(broken),
               "; ".join("%s (%s)" % (s, e) for s, e in sorted(broken.items()))
               or "none found"))
    return out


def _one(e):
    """Build one track, all the way to its medals-ready dict.

    Answered from the disk cache when this folder and the code that interprets
    it are both unchanged - see `_cache_key`. A hit comes back with `ideal` and
    `medals` already on it and the loop at the foot of this module leaves it
    alone; a miss is remembered in `_to_cache` so that same loop can write it
    once `laptime` has finished it off.
    """
    # **Only a folder is cacheable.** `from_document` comes through here too,
    # for a track that has no folder to hash and whose geometry changes under a
    # slug the editor reuses - `draft` is one slug shared by every draft in
    # flight - so a key built from the slug would hand one player's track to
    # another. `module` is the discriminator: `_meta` puts the imported
    # `track.py` on it, and a document has None.
    key = _cache_key(e["slug"]) if e.get("module") is not None else None
    if key is not None:
        hit = _cache_load(key)
        if hit is not None:
            return hit
        _to_cache[e["slug"]] = key

    def fresh():
        x, y, z, yaw = e["origin"]
        return Builder(x, y, z, yaw=yaw, width=e["width"], rails=e["rails"])

    b = fresh()
    built = e["build"](b)
    # A folder's `build` may either return the Builder or just drive the one it
    # was given. Both read naturally, and insisting on one of them is a rule a
    # contributor would have to be told rather than one they could guess.
    if built is None:
        built = b

    closure = []
    if e["closed"]:
        # Make the ribbon meet itself. The author lays out a loop that feels
        # right; this is what turns it into one that actually closes. See
        # `tracks/solver.py` - and note it is only reached for a closed track, so
        # nothing point-to-point pays for it.
        built, closure = solver.close(e["build"], fresh)

    t = {"slug": e["slug"], "name": e["name"],
         "ground": e["ground"], "difficulty": e["difficulty"],
         "exposed": e["exposed"], "closed": e["closed"],
         # Whether this track ships a `scenery.js`. On the track rather than
         # left in `_meta` because the *browser* needs the answer: the switcher
         # swaps the world in place, so it has to know to go and fetch the
         # scenery before it builds. See `/scenery/<slug>.js` in app.py.
         "scenery": e["wants_scenery"],
         "placed": e.get("placed"),
         # The three times cut from the board, or None to derive them below.
         "medal_times": e["medal_times"],
         "cell": CELL, "level": LEVEL, "station": STATION}
    t.update(built.build())
    # Both derived from the ribbon rather than authored, so a new track gets them
    # for free and cannot get them wrong.
    t["pole_side"] = pole_side(t)
    t["gate_ceil"] = gate_ceiling(t)
    # What it looks like, on the track itself. This is the whole reason the
    # palettes came out of trackmesh.js: `_track_payload` sends this dict to the
    # page as `window.DRIVE_TRACK` and `jsrt` sends the pool to QuickJS as JSON, so
    # a palette here reaches the browser *and* the anti-cheat with no new plumbing
    # - and Sandy Cove's waterline and the Costco shell stop being two copies of
    # one number in two languages.
    t["pal"] = look.check(e["slug"], _palette_for(e))
    if closure:
        # Kept on the track so `tools/validate_track.py` can print it and a test
        # can assert on it. Also said out loud once, because a solver that silently
        # rewrote what you authored would be worse than the tool it replaced.
        t["closure"] = closure
        _log.info("%s: closed the loop by %s", t["slug"],
                  ", ".join("%s %s -> %s" % (c["leg"], c["was"], c["now"])
                            for c in closure))
    return t


def _palette_for(entry):
    """A track's palette: one carried on the entry, its own `palette.py`, or the default.

    The carried case is a track that has no folder to look in - a stored
    document, whose palette travels with it. Checked first because a document
    with a palette must not silently get the neutral default just because
    `tracks/<slug>/palette.py` does not exist.

    The default is not a fallback for a mistake - `look.check` catches those. It
    is so that a folder with a `track.py` and nothing else renders correctly the
    first time it is driven, which is most of the difference between adding a
    track and learning what a palette is first.
    """
    if entry.get("pal"):
        return dict(entry["pal"])
    try:
        return importlib.import_module("tracks.%s.palette" % entry["slug"]).PALETTE
    except ModuleNotFoundError:
        return dict(look.DEFAULT)
    except AttributeError:
        raise ValueError("tracks/%s/palette.py must define `PALETTE`"
                         % entry["slug"])


TRACKS = _assemble()
BY_SLUG = {t["slug"]: t for t in TRACKS}

# Kept as derived sets rather than as the authored ones they used to be. Nothing
# outside here should need them - a track carries `closed` and `exposed` on
# itself - but they were part of this module's surface and a test still reaches
# for one.
CLOSED = {t["slug"] for t in TRACKS if t["closed"]}
EXPOSED = {t["slug"] for t in TRACKS if t["exposed"]}

# Medal times need the lap simulation, which needs the assembled ribbons - hence
# the import down here rather than at the top.
import laptime  # noqa: E402

# **A track that has been played overrules the simulation about how quick it is,
# and a track that has not been played still gets medals.**
#
# `laptime.ideal_lap` is a good estimate of a lap and a poor estimate of a
# *standard*: measured against the records people actually set, it is out by
# 0.744 to 0.888 of itself depending on the track. One global multiplier over
# that spread cannot be both hard on Chicane Park and possible on Spiral Ascent -
# tighten it until Chicane means something and Spiral Ascent has no gold at all,
# which is the state `docs/runs-and-scoring.md` already predicted and blamed on
# the estimate rather than on the multiplier.
#
# So the numbers are cut from the board by `tools/set_medals.py` and written into
# each `track.py`, and this is only the fallback. Frozen values and not a live
# query on purpose: medals read off the current board would move under the player
# every time somebody set a record, and the card in the corner is a target rather
# than a running commentary.
def _time_it(t):
    """The ideal lap and the three medals, onto a built track.

    Factored out of the loop below because a **stored document** needs exactly
    this too, and a second copy of the "declared times win, otherwise derive"
    rule is a second place for a user track to get medals a pool track would
    not. See `from_document`.
    """
    t["ideal"] = laptime.ideal_lap(t)
    t["medals"] = (laptime.named_medals(t["medal_times"])
                   if t["medal_times"] else laptime.medals(t["ideal"]))
    return t


for _t in TRACKS:
    # A cache hit already carries both, and recomputing `ideal` is the 3 seconds
    # the cache exists to skip. `_time_it` stays the one place the "declared
    # times win, otherwise derive" rule lives, for the misses and for
    # `from_document`.
    if "ideal" not in _t:
        _time_it(_t)
    if _t["slug"] in _to_cache:
        _cache_store(_to_cache.pop(_t["slug"]), _t)


def scenery_path(slug):
    """Where a track's own mesh code lives, if it has any."""
    p = os.path.join(HERE, slug, "scenery.js")
    return p if os.path.exists(p) else None


def scenery_source(slug):
    """A track's `scenery.js`, as text, or None.

    Read on demand rather than at import: it is tens of KB per track, only the
    track being driven needs it, and a file edited while the server is running
    should take effect on reload like every other static asset here.
    """
    p = scenery_path(slug)
    if p is None:
        return None
    with open(p) as f:
        return f.read()


_STAMPS = {}


def stamp(t, scenery=None):
    """A fingerprint of everything about a track that a saved car position
    depends on: the ribbon, the gates, the spawn, and the track's own collider.

    Practice save states store one and refuse to restore when it has moved, so
    that a corner re-authored under you cannot put you back inside a rock. It is
    `tracks.moves.fingerprint` - which already exists to wipe a user track's
    board when its geometry changes, the same question asked for the same reason
    - **plus the bytes of the track's `scenery.js`**, which the pool needs and a
    user track does not. That file is where the collider lives for a third of
    the pool: Rickety Rails' portal frames, the Costco's racking, Silverstone's
    anti-cut barriers. Fingerprinting the ribbon alone would leave a save state
    valid across an edit that moved a wall into it.

    Cached, because it hashes tens of KB of source and the answer only changes
    when the process restarts - which is also when an edited `scenery.js` is
    picked up, since `scenery_source` reads on demand.
    """
    from tracks import moves

    slug = t.get("slug")
    # Only the pool is cached. A user track has no folder to read and its
    # geometry changes under the same slug every time the editor saves - and a
    # draft shares the one reserved `draft` with every other draft, so a cache
    # keyed on the slug would hand one person's stamp to another's track.
    pool = slug in BY_SLUG and not t.get("user")
    if pool and slug in _STAMPS:
        return _STAMPS[slug]
    h = hashlib.sha1()
    h.update(moves.fingerprint(t, scenery).encode())
    src = scenery_source(slug) if pool else None
    if src:
        h.update(src.encode())
    got = h.hexdigest()[:16]
    if pool:
        _STAMPS[slug] = got
    return got


def all_scenery():
    """Every track's scenery, in pool order: `[(slug, source), ...]`.

    This is what `jsrt.bundle` concatenates into the QuickJS script, and it is the
    reason it is a function rather than a per-track lookup. The anti-cheat builds
    whichever track a submitted lap claims, so *all* of them have to be in the
    bundle - a bundle missing one verifies laps against a track with no building
    in it, and nothing about that failure is loud. See `test_scenery.py`.
    """
    out = []
    for t in TRACKS:
        src = scenery_source(t["slug"])
        if src is not None:
            out.append((t["slug"], src))
    return out


def summaries():
    """Everything the track-select screen needs, without the station lists.

    `scenery` is in here so the switcher knows *before* you click a card whether
    that track needs its `scenery.js` fetching - which lets it ask for the
    scenery and the track payload at the same time rather than one after the
    other. See `ensureScenery` in game.js.
    """
    return [{k: t[k] for k in ("slug", "name", "difficulty", "ideal",
                               "medals", "checkpoints", "scenery")}
            for t in TRACKS]


# ---------------------------------------------------------------------------
# Tracks that are not folders
# ---------------------------------------------------------------------------

# How a slug that is not in the pool gets resolved, or `None`.
#
# **Nothing in `tracks/` may import the database**, and this hook is why. This
# package is imported by `verify.py` in a process of its own, by `jsrt` inside
# QuickJS's host, and by every test in the suite - none of which has an app
# context, and one of which (a checkout with no `DATABASE_URL`) has no database
# driver installed at all. So the app layer installs a resolver at start-up and
# `tracks/` stays what it is: geometry, and no I/O.
#
# **The resolver must cache within a request.** `get` is called from twenty-odd
# places in `app.py` for a single page - the payload, the record, the ghost, the
# share card, the canonical link - and a database round trip and a ribbon
# rebuild for each would be absurd. Building a document is a few milliseconds;
# doing it thirty times is not.
_resolver = None

# Slugs a player may not take. The pool's own nineteen are added below, because
# one flat namespace is what lets a user track live at `/solo/<slug>` and get
# every share link, canonical tag and sitemap entry for free - and that only
# works if a player cannot claim `spa`.
RESERVED = {
    "new", "edit", "make", "draft", "admin", "api", "static", "scenery",
    "solo", "room", "race", "replay", "leaderboard", "account", "login",
    "logout", "register", "privacy", "tracks", "track", "garage", "portal",
}


def set_resolver(fn):
    """Install the thing that turns a slug into a live user track, or `None`.

    Called once, from `app.py`, and only when there is a database to read.
    """
    global _resolver
    _resolver = fn


def slugify(name):
    """A name a player typed, as a slug. `"Foggy Ridge!"` -> `"foggy-ridge"`.

    The editor derives the slug from the name so nobody has to be told what a
    slug is. Kept next to `slug_is_available` because the two have to agree
    about what a legal slug looks like, and a candidate this produces has to be
    one that passes.
    """
    out, prev_dash = [], True          # leading dash suppressed
    for ch in (name or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")[:40].rstrip("-")


def slug_is_available(slug):
    """Whether a player may claim `slug`. Says why not, when they may not.

    Returns `(True, None)` or `(False, reason)`. The reason is shown to the
    person typing the name, so it says what to do rather than what went wrong.

    Takes the slug **as it will be stored** and refuses anything it would have
    had to change - no quiet normalising. A checker that lowercases its input
    and answers about the lowercased version invites a caller to validate one
    string and store another, which is how two tracks end up fighting over a
    URL. Run the name through `slugify` first.
    """
    s = slug or ""
    if s != s.strip().lower():
        return False, "Use lower case, without spaces at either end."
    if not s:
        return False, "A track needs a name."
    if len(s) < 3:
        return False, "That is too short - three characters or more."
    if len(s) > 40:
        return False, "That is too long - forty characters or fewer."
    if not all(c.isalnum() or c == "-" for c in s):
        return False, "Letters, numbers and hyphens only."
    if s.startswith("-") or s.endswith("-") or "--" in s:
        return False, "Hyphens go between words, not at the ends."
    if s in BY_SLUG:
        return False, "%s is already a track here." % BY_SLUG[s]["name"]
    if s in RESERVED:
        return False, "That name is reserved."
    return True, None


def from_document(slug, doc, order=DEFAULT_ORDER, timed=True, spans=None):
    """A stored document, assembled into the same dict a folder produces.

    Deliberately routed through the very same `_one` and `_time_it` the pool
    uses, rather than through a parallel assembler. Everything a track gets for
    free - `pole_side`, `gate_ceil`, the ideal lap, the three medals, the
    closure solve on a lap that has to meet itself - is got here by *calling the
    same code*, so a user track cannot drift into being a slightly different
    kind of object. The only thing that differs is where `build` comes from: a
    folder has a function, and this has a document to replay.

    Raises whatever the build raises. The caller decides whether a bad row is
    fatal or merely absent, exactly as `_assemble` does for a bad folder.

    **`timed=False` skips the lap-time model, and the editor needs it to.**
    Replaying a document and building its ribbon costs about 4ms even for the
    longest track in the pool; `laptime.ideal_lap` - a racing-line relaxation
    and a speed profile over every station - costs about 550ms. Live editing
    wants the road on every change and the lap time hardly ever, so it asks for
    the road. Without the flag the editor would be a hundred times slower than
    it needs to be, and it would be slow on the one eventlet worker that also
    relays every live race pose at 30Hz.
    """
    from tracks import moves

    entry = {
        "slug": slug,
        "name": doc.get("name") or slug,
        "difficulty": int(doc.get("difficulty") or 3),
        "ground": doc.get("ground"),
        "order": order,
        "width": float(doc.get("width", ROAD_W)),
        "rails": bool(doc.get("rails")),
        "origin": tuple(doc.get("origin") or (0.0, 0.0, 0.0, 0.0)),
        "closed": bool(doc.get("closed")),
        "exposed": bool(doc.get("exposed")),
        # A user track never ships a `scenery.js`; what it has instead is baked
        # geometry on the document, which needs no fetch and no bundle.
        "wants_scenery": False,
        # **`placed`, and not `scenery`.** `t["scenery"]` is already a boolean -
        # does this track have a `scenery.js` next to it - so putting the
        # placement list there would be read by `buildTrack` as `true.length`,
        # which is `undefined`, which is falsy: the scenery would never be drawn
        # and nothing would say so.
        "placed": doc.get("scenery") or None,
        # Always derived. `tools/set_medals.py` cuts from a board, and a user
        # track's board is too small and too self-selected to cut from.
        "medal_times": None,
        "pal": doc.get("pal"),
        "build": lambda b: moves.replay(doc, b, spans=spans),
        "module": None,
    }
    t = _one(entry)
    if timed:
        _time_it(t)
    else:
        # Named rather than absent, so a caller that forgot cannot read a stale
        # number: `None` fails loudly where a missing key might be shrugged off.
        t["ideal"] = None
        t["medals"] = None
    # Marks it as somebody's rather than the pool's. Read by the play page (the
    # by-line), the switcher (the Community shelf) and `/admin` - and by nothing
    # that touches geometry, which is the point.
    t["user"] = True
    return t


def get(slug):
    """The one place a slug becomes a track.

    Called from twenty-odd places in `app.py` - `/solo`, `/api/track`,
    `/api/run`, `/api/start`, `/api/ghost`, the room machinery, replays, share
    cards, `robots.txt`, `sitemap.xml`, the switcher. Teaching *this* about
    stored tracks is what makes a player's track work everywhere without any of
    those learning a second way to be a track.
    """
    t = BY_SLUG.get(slug)
    if t is not None:
        return t
    if _resolver is None:
        return None
    return _resolver(slug)
