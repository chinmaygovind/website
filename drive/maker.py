"""The track maker, and what happens to a track somebody keeps.

Split out of `app.py` in August 2026, when that file was 5,700 lines. This is
the part that came out first because it was the part that came out *cleanly*:
it needs nine names from `app.py` and `app.py` needs none back, so the
dependency runs one way and there is no import cycle to work around.

**What is in here.** Everything from `/make` to a track being live: the move
schema handed to the editor and to somebody else's model, building a document
into a road, the draft store, saving under a slug nobody else can take, the
checks and the drove-it gate, submitting, forking, the gallery, the admin
queue, and `/scenery/<slug>.js`.

**What is deliberately not.** `/api/last-track`, `/api/presence`, `/api/start`,
`/api/ping` and `/api/activity` sat inside the same banner in `app.py` and are
not about making a track at all - they stayed. So did `_floor_starts` and
`_starts_for`, which are about counting attempts and only looked like they
belonged here because they were the last thing under the heading.

**How the routes get registered.** `app.py` imports this module at the very
foot of the file, after everything below is defined, purely for the side effect
of running the `@app.route` decorators. That is why the import is at the bottom
there and why it looks unused. Nothing here may import `app.py` at module scope
*before* the names it wants exist, which in practice means: only import from
`app`, only the nine names below, and never call back into it at import time.

If you add a module-level mutable to this file, add `"maker"` to `RELOADED` in
`tests/conftest.py` - it is already there, and the note beside it says why a
module left out of that list contaminates the next test.
"""

import os
import math
import uuid
import json as json_mod
import time

from datetime import datetime

from flask import (render_template, request, jsonify, redirect, url_for,
                   session, send_from_directory, abort)

from models import db, DriveUserTrack
import tracks as tracks_mod
from tracks import checks
from tracks import look
from tracks import moves as moves_mod
from tracks import plan as plan_mod
from tracks import solver as solver_mod
from tracks import starters
import tuning

# The nine names this module needs from `app.py`. `app` itself is the Flask
# object every route below decorates; the rest are shared helpers, except
# `DATABASE_URL`, which is read at import time to decide whether to register the
# user-track resolver at all. See the docstring on why this import is safe
# despite `app.py` importing this file.
from app import (app, DATABASE_URL, get_current_user, get_effective_name,
                 portal_mode, script_json, _car_livery, _my_pb_map, _prefs_for)


# What a document may contain. Bounds rather than taste: a track over these is
# refused, a track under them is somebody's business.
#
# The move cap is generous - Big Red, the longest in the pool, is 64 moves - and
# the length cap is about twice it. They exist because **`/api/make/build`
# replays a document on the one eventlet worker that also relays every live race
# pose at 30Hz**, so the cost of one call has to be bounded by something other
# than good faith.
MAKE_MAX_MOVES = 400
MAKE_MAX_UNITS = 6000.0


def _make_forbidden():
    """The editor does not exist in the portal build.

    CrazyGames forbids a game offering any login of its own, and authorship
    without identity is not a thing - a gallery of tracks by nobody is worse
    than no gallery. So `/make` 404s there exactly as `/login` does, rather than
    half-working.
    """
    return portal_mode()


@app.route("/make")
@app.route("/make/<shape>")
def make(shape=None):
    """The editor. No login needed to open it, build in it, or drive what you built.

    Signing in is for *keeping* a track, which is the point at which an account
    means something. Until then the draft lives in the browser.
    """
    if _make_forbidden():
        abort(404)
    if shape is not None and shape not in starters.SHAPES:
        return redirect(url_for("make"))
    return _render_editor(starters.document(shape) if shape else None, shape)


def _render_editor(doc, shape):
    """The editor page, for a starting shape or for a draft being reopened.

    One function because there are two ways in and they must agree about every
    one of eight template arguments - and the failure mode of them not agreeing
    is the one already paid for once here: the page route and the API built the
    track differently, so the first paint had no spans and read `0 UNITS`.
    """
    track = None
    if doc is not None:
        # Untimed: the ribbon is 4ms and the lap-time model is 550ms, and the
        # page wants the road now. The lap estimate arrives from its own call.
        track, _err = _draft_track(doc)
    return render_template(
        "make.html", user=get_current_user(), name=get_effective_name(),
        shape=shape, shapes_json=script_json(starters.summaries()),
        doc_json=script_json(doc), track_json=script_json(track),
        tuning_json=tuning.as_json(), looks_json=script_json(_pool_looks()),
        # What a key the palette does not carry falls back to. Sent rather than
        # written into make.js so there is one table, and it is the same one a
        # brand new track gets.
        default_pal_json=script_json(look.DEFAULT),
        # The move vocabulary, for the AI panel. Generated from `moves.SPEC`
        # and `moves.HELP` rather than written out, so a move gaining a field is
        # a move whose description gains it too.
        vocab_json=script_json(_moves_spec()),
        caps_json=script_json(
            {"moves": MAKE_MAX_MOVES, "units": MAKE_MAX_UNITS}))


def _moves_spec():
    """The whole authored-move vocabulary, as data a model can be handed.

    This is the half of the track maker no model has any chance of guessing.
    Scenery at least looks like graphics code; a document of `{"t": "arc",
    "deg": -150, "rad": 17}` looks like nothing, and a model asked to help with
    a track layout without this will write three.js, or a Bezier curve, or an
    SVG path.

    Assembled from the schema itself - `SPEC` for the fields and their defaults,
    `HELP` for what each one does, `LAYS_ROAD` for which carry a width - so it
    cannot describe a vocabulary the replayer does not have.
    """
    return {
        "version": moves_mod.SCHEMA_VERSION,
        "moves": [
            {
                "t": t,
                "what": moves_mod.HELP[t],
                "fields": {
                    k: ("required" if v is moves_mod.REQ else v)
                    for k, v in fields.items()
                },
                "lays_road": t in moves_mod.LAYS_ROAD,
            }
            for t, fields in moves_mod.SPEC.items()
        ],
        # Carried on every road-laying move rather than inherited from the one
        # before, which is the one deliberate difference from the turtle: in a
        # list you can reorder, and sticky state means deleting one move
        # silently rewidens nine others.
        "per_move": {
            "w": "road width in units, default %s" % moves_mod.ROAD_W,
            "rail": "barriers: '' none, 'l' left, 'r' right, 'lr' both",
        },
        "freeable": list(moves_mod.FREEABLE),
        "limits": {
            "moves": MAKE_MAX_MOVES,
            "units": MAKE_MAX_UNITS,
            # From `tracks/checks.py`, which is where they are enforced. A
            # second copy here would be a spec that tells a model a number the
            # editor then refuses it for.
            "min_arc_radius": checks.MIN_RADIUS,
            "min_loop_radius": checks.MIN_LOOP_RADIUS,
            "distinct_radii": checks.RADII_DISTINCT,
            "closure_stretch": 0.15,
            "first_turn_deg": checks.FIRST_TURN_DEG,
            "gate_ceiling": [checks.GATE_CEIL_MIN, checks.GATE_CEIL_MAX],
        },
    }


def _pool_looks():
    """Every palette in the pool, whole, for the borrow-a-look list.

    Whole and not filtered to the keys the editor draws: 18KB for all nineteen
    against a page that already carries a track, and the alternative is a
    borrow that silently drops Spa's grandstands because the palette editor has
    no control for them. What the editor cannot edit it carries.
    """
    return [{"slug": t["slug"], "name": t["name"], "pal": t.get("pal") or {}}
            for t in tracks_mod.TRACKS]


def _ribbon_length(track):
    """How much road a document actually laid, for the cap and for the HUD."""
    line, total = track.get("line") or (), 0.0
    for i in range(1, len(line)):
        a, b = line[i - 1]["p"], line[i]["p"]
        total += math.dist(a, b)
    return total


def _draft_track(doc, timed=False):
    """A document, built the way the editor needs it: fast, measured, mapped.

    `timed=True` prices a lap and cuts the three medals, which costs about 550ms
    against the ribbon's 4ms. The editor never wants that on a keystroke; the
    play page always does - the medal card in the corner reads `medals.gold`,
    and handing it `None` is a null dereference on the first frame.

    One helper for both entry points - the page's first paint and every rebuild
    after it - because the first version had the route build the track without
    `spans` or `units`, and the editor then had no way to frame a selected move
    and showed a length of zero. Two paths producing subtly different track
    dicts is exactly the drift this is here to prevent.

    Returns `(track, error)`; the error is written for the person editing.
    """
    n = len(doc.get("moves") or ())
    if not n:
        return None, "A track needs at least a start and a finish."
    if n > MAKE_MAX_MOVES:
        return None, "That is %d moves; the limit is %d." % (n, MAKE_MAX_MOVES)
    spans = []
    try:
        track = tracks_mod.from_document(
            str(doc.get("slug") or "draft"), doc, timed=timed, spans=spans)
    except moves_mod.MoveError as e:
        return None, str(e)
    except solver_mod.CannotClose as e:
        return None, str(e)
    units = _ribbon_length(track)
    if units > MAKE_MAX_UNITS:
        return None, ("That is %.0f units of road; the limit is %.0f."
                      % (units, MAKE_MAX_UNITS))
    track["units"] = round(units, 1)
    # Which stations each move laid, so selecting a move can highlight its
    # stretch and put the camera on it. A closed lap is solved by re-running the
    # build, so `spans` holds several runs' worth and the *last* one is the run
    # that produced the ribbon being sent. See `solver.close`.
    track["spans"] = spans[-n:]
    return track, None


@app.route("/api/make/build", methods=["POST"])
def api_make_build():
    """A document in, the road out. The editor's whole loop.

    Deliberately **not** a second Builder in JavaScript. `tuning.py` is the
    single source of truth for the simulation and there is no second copy of
    `ACCEL` in a .js file; a second copy of the *turtle* would be the same
    mistake with more surface, and it would drift the first time somebody
    changed how a hill eases. So the editor asks the real one, debounced.

    Returns `400` with a message written for the person editing, never a
    traceback: every error in here is something they typed.
    """
    if _make_forbidden():
        abort(404)
    doc = request.get_json(silent=True)
    if not isinstance(doc, dict):
        return jsonify({"error": "That is not a track document."}), 400
    try:
        track, err = _draft_track(doc)
    except Exception as e:                                  # pragma: no cover
        app.logger.warning("make: build failed: %s", e)
        return jsonify({"error": "That did not build: %s" % e}), 400
    if err:
        # A closed lap that will not close is the one failure worth naming
        # separately: it is not a broken document, it is a shape that needs a
        # change, and the editor says so differently.
        kind = "closure" if "clos" in err else None
        return jsonify({"error": err, "kind": kind}), 400
    # Everything that built and is still wrong. A corner of radius 4 is valid
    # geometry and the builder is right to lay it; the reason it must not ship
    # is that the car cannot get round it, which is a fact about the physics.
    # So it rides alongside the road rather than as a 400 - the editor shows the
    # road you asked for and says what is wrong with it.
    return jsonify({"track": track, "notes": [
        {"level": lvl, "at": at, "text": text}
        for lvl, at, text in moves_mod.advise(doc)]})


# Drafts handed from the editor to the play page, as `{token: (doc, expiry)}`.
#
# In memory, and a plain dict, for the same reason live race state is: there is
# one eventlet worker, and a draft is about the next few minutes. Nothing here
# is worth a table - a lost draft costs somebody one click of the Drive button,
# and the editor still holds the document.
_DRAFTS = {}
_DRAFT_TTL = 2 * 60 * 60
_DRAFT_MAX = 400

# **The slug a draft is driven under, and it is a reserved word on purpose.**
#
# `/api/run` and `/api/start` both begin with `tracks_mod.get(...)` and reject a
# slug that resolves to nothing. `draft` is in `tracks.RESERVED`, so no player
# can ever claim it and it can therefore never resolve - which makes "a lap on
# an unpublished draft cannot reach the leaderboard" true *by construction*
# rather than by a guard somebody has to remember to write. See
# `test_a_draft_lap_cannot_reach_the_board`.
DRAFT_SLUG = "draft"


def _sweep_drafts():
    now = time.time()
    for k in [k for k, (_, exp) in _DRAFTS.items() if exp < now]:
        _DRAFTS.pop(k, None)
    # A cap as well as a clock, because the clock only helps once time passes.
    while len(_DRAFTS) > _DRAFT_MAX:
        _DRAFTS.pop(next(iter(_DRAFTS)), None)


@app.route("/api/make/draft", methods=["POST"])
def api_make_draft():
    """Park a document so the play page can pick it up, and hand back a token.

    The editor could not simply put the document in the URL - it is kilobytes -
    and the session cookie is the wrong size of place for one. So it goes here
    for a couple of hours under a token that is only useful to whoever has it.
    """
    if _make_forbidden():
        abort(404)
    doc = request.get_json(silent=True)
    if not isinstance(doc, dict):
        return jsonify({"error": "That is not a track document."}), 400
    track, err = _draft_track(doc)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"token": _stash_draft(doc)})


def _stash_draft(doc):
    """Park a document under a token. One helper, because forking wants it too."""
    _sweep_drafts()
    token = uuid.uuid4().hex[:22]
    _DRAFTS[token] = (doc, time.time() + _DRAFT_TTL)
    return token


@app.route("/make/edit/<token>")
def make_edit(token):
    """Reopen the editor on a draft, which is how you get *back* from driving.

    Driving a draft is a full page navigation to the real play page, so the
    editor's state is gone by the time you arrive. Going back therefore cannot
    be `history.back()` - that reloads the starting shape and throws away every
    change. The token already holds the document, so it is what the way back is
    built on, and the round trip edit - drive - edit keeps your track.
    """
    if _make_forbidden():
        abort(404)
    _sweep_drafts()
    got = _DRAFTS.get(token)
    if not got:
        return redirect(url_for("make"))
    doc, _exp = got
    return _render_editor(doc, doc.get("from_shape") or "blank")


@app.route("/make/drive/<token>")
def make_drive(token):
    """Drive a draft. The real game, on a road nobody has published.

    The same `play.html` and the same `game.js` the pool gets - a draft is a
    track, and the play page already knows how to drive one. What it is *not* is
    a track anything can store a time against: see `DRAFT_SLUG`.
    """
    if _make_forbidden():
        abort(404)
    _sweep_drafts()
    got = _DRAFTS.get(token)
    if not got:
        # Expired or never existed. Back to the editor rather than a 404: the
        # person clicked Drive and the answer to "your draft timed out" is the
        # editor, not an error page.
        return redirect(url_for("make"))
    doc, _exp = got
    # Timed, unlike every editor build: the play page shows the three medals and
    # a lap has to be worth measuring against something.
    track, err = _draft_track(doc, timed=True)
    if err:
        return redirect(url_for("make"))
    track["slug"] = DRAFT_SLUG
    track["name"] = doc.get("name") or "Your track"
    # A draft never reaches `_track_payload`, so its practice-save stamp is set
    # here. The scenery has to be passed in: a draft's collider lives in its
    # document rather than in a `scenery.js` next to it, and a stamp blind to it
    # would keep a save state valid across a wall being dragged into the road.
    track["stamp"] = tracks_mod.stamp(track, doc.get("scenery"))
    user = get_current_user()
    return render_template(
        "play.html", mode="solo", track=track, draft_token=token,
        og_image=None, og_title="%s | Drive" % track["name"],
        track_json=script_json(track), track_scenery=None,
        tuning_json=tuning.as_json(), room=None, me_json="null",
        roster_json="[]", name=get_effective_name(), user=user,
        pb_ms=None, next_slug=None, pb_splits={},
        car_color=_car_livery(user)["body"],
        car_livery=script_json(_car_livery(user)),
        prefs_json=script_json(_prefs_for(user)),
        tracks=[], cards=[])


# ---------------------------------------------------------------------------
# Keeping a track
# ---------------------------------------------------------------------------
#
# **A user track is not a second kind of track**, and this section is where that
# stops being a claim. A row holds the authored document; `tracks.from_document`
# replays it through the same `Builder` that builds Spa; and `tracks.get` - the
# one function `/solo`, `/api/track`, `/api/run`, `/api/start`, `/api/ghost`,
# rooms, replays, share cards, `robots.txt` and the switcher all call - is taught
# to resolve a live slug. Every one of those routes then works with no further
# change, which is the whole trick and the reason this is a small feature rather
# than a second game.


def _user_track_row(slug):
    return DriveUserTrack.query.filter_by(slug=slug).first()


# Built tracks, by slug. `tracks.get` is called several times per request on some
# pages and a *timed* build is about 550ms - a racing-line relaxation over every
# station - so resolving from the row every time would put half a second into the
# critical path of the play page. Keyed on `updated_at` so an edit invalidates it
# without anything having to remember to.
_LIVE_CACHE = {}
_LIVE_CACHE_MAX = 64


def _track_from_row(row, timed=True):
    """A row as a track dict, or None if the document no longer builds.

    None rather than an exception, for the reason `tracks.BROKEN` exists: one
    unbuildable track must not take down the page that was listing it. A row
    that stops building is a bug worth finding, and the way to find it is a
    gallery with a gap in it rather than a 500.
    """
    key = (row.slug, row.updated_at, timed)
    got = _LIVE_CACHE.get(row.slug)
    if got and got[0] == key:
        return got[1]
    try:
        t = tracks_mod.from_document(row.slug, row.doc, timed=timed)
    except Exception as e:
        app.logger.warning("user track %s no longer builds: %s", row.slug, e)
        return None
    t["name"] = row.name
    t["difficulty"] = row.difficulty
    t["level"] = row.difficulty
    # Who made it. Read by the play page's by-line, the gallery card and the
    # switcher shelf, and by nothing that touches geometry.
    t["author"] = row.author.username if row.author else None
    t["author_name"] = row.author.display if row.author else None
    t["forked_from"] = row.forked_from
    t["status"] = row.status
    if len(_LIVE_CACHE) >= _LIVE_CACHE_MAX:
        _LIVE_CACHE.clear()
    _LIVE_CACHE[row.slug] = (key, t)
    return t


def _resolve_user_track(slug):
    """The hook `tracks.get` falls through to. Live tracks only.

    A draft resolving here would be a draft with a leaderboard, reachable at
    `/solo/<slug>` by anybody who guessed the name - so the status check is not
    a nicety, it is the difference between unlisted and published.
    """
    # Never raises. This is a fallback hook on the pool's own lookup, called
    # from twenty-odd routes, and a database that is briefly unreachable must
    # come out as "no such track" rather than as a 500 on the home page. It is
    # also called with no application context at all by `tools/` scripts, which
    # only ever want the pool.
    try:
        row = _user_track_row(slug)
        if row is None or row.status != "live":
            return None
        return _track_from_row(row)
    except Exception:
        # The whole lookup, not just the query: reading `row.author` needs a
        # live session too, and a half-loaded row is the same "no such track"
        # from every caller's point of view.
        return None


def _forget_track(slug):
    _LIVE_CACHE.pop(slug, None)


# **This one line is the feature.** `tracks.get` is the single chokepoint every
# route already goes through, so installing a fallback here is what makes
# `/solo/<slug>`, `/api/track`, `/api/run`, `/api/start`, `/api/ghost`, rooms,
# replays, share cards, `robots.txt`, `sitemap.xml` and the switcher all work on
# a player's track without one of them being edited.
#
# Installed only when there is a database, because `tracks/` must stay DB-free:
# it is imported by `verify.py` in a separate process, by `jsrt` inside QuickJS's
# host, and by tests with no database at all.
if DATABASE_URL:
    tracks_mod.set_resolver(_resolve_user_track)


def _is_admin(user):
    """Case-insensitively, on both sides, and that is not fussiness.

    `accounts/admin.py:admin_names` lowercases the configured names *and* the
    username, and reads the same `ADMIN_USERNAMES`. Matching exactly is the
    whole requirement: the two gates disagreeing means the track queue is
    visible to somebody `/admin` refuses, or - worse and likelier - `/admin`
    works and the queue 404s at the one person who is supposed to review
    tracks, with no error anywhere to say why. `ADMIN_USERNAMES=Chinmay` did
    exactly that.
    """
    if not user or getattr(user, "is_bot", False):
        return False
    return (user.username or "").lower() in ADMIN_NAMES


ADMIN_NAMES = frozenset(
    n.strip().lower() for n in
    os.environ.get("ADMIN_USERNAMES", "chinmay").split(",") if n.strip())


def _may_edit(row, user):
    """The author, or Chinmay. Nobody else, at any status."""
    return bool(user) and (row.author_id == user.id or _is_admin(user))


# ---- saving ---------------------------------------------------------------


@app.route("/api/make/save", methods=["POST"])
def api_make_save():
    """Keep a track. This is the first point at which an account means anything.

    Building and driving need no login at all - see `/make` - because an editor
    that asks who you are before it shows you a road is an editor most people
    close. Saving is different: a saved track has an author, an address and a
    board, and none of those exist without an identity.
    """
    if _make_forbidden():
        abort(404)
    user = get_current_user()
    if not user:
        return jsonify({"error": "Sign in to keep a track.",
                        "need_login": True}), 401
    body = request.get_json(silent=True) or {}
    doc = body.get("doc")
    if not isinstance(doc, dict) or not (doc.get("moves") or ()):
        return jsonify({"error": "That is not a track document."}), 400

    track, err = _draft_track(doc)
    if err:
        return jsonify({"error": err}), 400

    name = (str(doc.get("name") or "").strip() or "Untitled")[:60]
    slug = body.get("slug")
    row = _user_track_row(slug) if slug else None
    if slug and row is None:
        return jsonify({"error": "There is no track with that address."}), 404
    if row is not None and not _may_edit(row, user):
        return jsonify({"error": "That is not yours to change."}), 403

    if row is None:
        slug = _free_slug(name)
        if slug is None:
            return jsonify({"error":
                "Every version of that name is taken. Try another."}), 409
        row = DriveUserTrack(slug=slug, author_id=user.id, status="draft",
                               name=name, forked_from=doc.get("forked_from"))
        db.session.add(row)

    was_hash, was_look = row.geom_hash, row.look_hash
    row.name = name
    row.difficulty = int(doc.get("difficulty") or 3)
    row.doc_json = json_mod.dumps(doc, separators=(",", ":"))
    row.source = doc.get("source") or None
    row.geom_hash = moves_mod.fingerprint(track, doc.get("scenery"))
    # The cover, such as it is, written where the ribbon is already built. Every
    # track has one from the moment it is saved, which a rendered picture cannot
    # manage - `tools/shoot_user_tracks.py` has to be run for those.
    row.plan_path = plan_mod.path_for(track.get("line") or ())
    row.look_hash = moves_mod.look_fingerprint(doc)
    row.updated_at = datetime.utcnow()

    # **What was approved is what is live.** A cosmetic edit - a colour, a name,
    # a difficulty - saves straight onto a live track and the board is untouched,
    # because none of it changes the road. Anything that moves the road, or its
    # collider, drops it back to the queue: every time on that board was driven
    # against the old one, and a record silently becoming a time on a different
    # road is the one thing a leaderboard cannot survive.
    # Two signals, because the board rule and the review rule are not the same
    # rule. A moved corner invalidates every time on the board, so it wipes it.
    # A swapped-out city does not - lap times do not care - but it still has to
    # come back, because what was approved was a *particular* city. A colour,
    # a name or a difficulty is neither, and saves straight onto a live track.
    moved = bool(was_hash and was_hash != row.geom_hash)
    reskinned = bool(was_look and was_look != row.look_hash)
    requeued = False
    if row.status == "live" and (moved or reskinned):
        row.status = "queued"
        row.queued_at = datetime.utcnow()
        requeued = True
    db.session.commit()
    _forget_track(row.slug)
    return jsonify({"slug": row.slug, "status": row.status,
                    "requeued": requeued, "geom_changed": moved,
                    "look_changed": reskinned,
                    # The one the author cares about: whether their board went.
                    "board_kept": not moved})


def _free_slug(name):
    """A slug for a name, with a number on the end if it has to be.

    `tracks.slug_is_available` returns `(ok, why)` and **not** a bool - reading
    it as one is a truthy tuple, which let `draft`, `admin`, `api` and every
    pool slug straight through. `draft` in particular: it is the slug every
    draft is driven under, so a row holding it would put draft laps on a real
    board.
    """
    base = tracks_mod.slugify(name) or "track"
    for n in range(0, 200):
        cand = base if n == 0 else "%s-%d" % (base, n + 1)
        if len(cand) > 40:
            cand = cand[:40].rstrip("-")
        ok, _why = tracks_mod.slug_is_available(cand)
        if ok and not _user_track_row(cand):
            return cand
    return None


# ---- the checks, and the gate -------------------------------------------


def _run_checks(doc, track):
    """Every structural check, run per document, written for a person.

    **None of this is new logic.** It is the same battery `tracks/checks.py` and
    `drive/tests/` already apply to the nineteen, run on demand instead of at
    import, with its output written for the author rather than for a test
    runner. A check that lives here and nowhere else would be a second standard
    for what a track is.

    Returns [(ok, label, detail)] - ordered, and all of them, because a list
    that stops at the first failure tells somebody one thing per attempt.
    """
    out = []

    def add(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    issues = checks.self_proximity(track)
    add(not issues, "No road laid over itself",
        "" if not issues else "%d place%s where the lap runs too close to "
        "itself: %s" % (len(issues), "" if len(issues) == 1 else "s",
                        ", ".join(str(i) for i in issues[:4])))

    radii = sorted({round(abs(1.0 / e["curv"]), 1)
                    for e in track["line"] if abs(e.get("curv") or 0) > 1e-6})
    tight = radii[0] if radii else None
    add(radii and tight >= checks.MIN_RADIUS,
        "Every corner is drivable",
        "" if not radii else ("the tightest is %.4g, and under %.4g nothing can "
                             "get round it" % (tight, checks.MIN_RADIUS)
                             if tight < checks.MIN_RADIUS else
                             "tightest %.4g, widest %.4g" % (tight, radii[-1])))
    add(len(radii) >= checks.RADII_DISTINCT, "Corner radii are varied",
        "%d different radi%s; a circuit worth learning uses %d or more"
        % (len(radii), "us" if len(radii) == 1 else "i",
           checks.RADII_DISTINCT))

    # `checks.pole_side` and `gate_ceiling` are *measurements*, not verdicts -
    # they answer "which side" and "how high", and it is the pool's tests that
    # decide whether the answer is acceptable. So the judging is here, and it is
    # the same judging: pole is checked against where the track actually turns
    # first, and the ceiling against the track's own crossing clearance.
    side = track.get("pole_side")
    add(side in (-1, 1), "Pole is on the inside of turn one",
        "" if side in (-1, 1) else "the first corner is not clear enough to "
        "put a grid behind")

    ceil = track.get("gate_ceil")
    line = track["line"]
    over = [(i, j) for i, j in checks.crossings(track)
            if ceil is not None
            and ceil >= abs(line[i]["p"][1] - line[j]["p"][1])]
    add(ceil is not None
        and checks.GATE_CEIL_MIN <= ceil <= checks.GATE_CEIL_MAX and not over,
        "No checkpoint creditable from above",
        "" if not over else "the road crosses over a checkpoint closer than "
        "the %.4g the gate counts from, so a lap could be credited from the "
        "wrong level" % ceil)

    cps = sum(1 for m in doc.get("moves") or () if m.get("t") == "cp")
    add(cps >= checks.MIN_CHECKPOINTS, "Enough checkpoints",
        "%d; three or four round a lap is usual" % cps)

    grounded = doc.get("ground") is not None
    rails = any((m.get("rail") or "") for m in doc.get("moves") or ())
    add(grounded or rails or doc.get("exposed"),
        "Barriers where there is no ground",
        "" if grounded or rails else "this track floats in a void and has no "
        "barriers, so the road has nothing to stop you leaving it")

    med = track.get("medals")
    ordered = bool(med) and med["gold"] < med["silver"] < med["bronze"]
    add(ordered, "Medals in order",
        "" if ordered else "the three medal times are not increasing")

    for lvl, at, text in moves_mod.advise(doc):
        if lvl == "refuse":
            add(False, "Playable layout", text)
    return out


# Laps driven on a draft, as `{(who, geom_hash): (ms, when)}`.
#
# **The submit gate is that you have driven it, start line to flag, cleanly** -
# and that is the best of the four options for a reason worth naming: it proves
# finishability by *demonstration* rather than by inference, and it pays for
# itself three times over. That lap becomes the track's first record, its first
# ghost, and the line `tools/hotlap.py` needs - so a brand new user track has
# bots that drive it properly instead of following the relaxed line.
#
# Keyed on the geometry hash and not on the slug, so driving it and then moving a
# corner does not count: what was proved was that *that road* can be finished.
_DROVE = {}
_DROVE_TTL = 24 * 60 * 60
_DROVE_MAX = 2000


def _drove_key():
    u = get_current_user()
    return "u%d" % u.id if u else "s:" + str(session.get("visit_sid") or "?")


def _sweep_drove():
    now = time.time()
    for k in [k for k, v in _DROVE.items() if v[1] + _DROVE_TTL < now]:
        _DROVE.pop(k, None)
    if len(_DROVE) > _DROVE_MAX:
        for k in sorted(_DROVE, key=lambda k: _DROVE[k][1])[:len(_DROVE) // 2]:
            _DROVE.pop(k, None)


@app.route("/api/make/drove", methods=["POST"])
def api_make_drove():
    """The game says a draft lap finished. Recorded against the geometry.

    Called from `game.js` when a lap completes on a draft, which is the only
    thing a draft lap is good for - it cannot reach a board (see `DRAFT_SLUG`)
    and it does not want to.
    """
    if _make_forbidden():
        abort(404)
    body = request.get_json(silent=True) or {}
    token, ms = body.get("token"), body.get("ms")
    if not token or not isinstance(ms, (int, float)) or ms <= 0:
        return jsonify({"error": "no"}), 400
    got = _DRAFTS.get(token)
    if not got:
        return jsonify({"ok": False, "why": "that draft has expired"})
    doc, _exp = got
    track, err = _draft_track(doc)
    if err:
        return jsonify({"ok": False, "why": err})
    _sweep_drove()
    h = moves_mod.fingerprint(track, doc.get("scenery"))
    key = (_drove_key(), h)
    best = _DROVE.get(key)
    if not best or ms < best[0]:
        _DROVE[key] = (float(ms), time.time())
    return jsonify({"ok": True})


@app.route("/api/make/checks", methods=["POST"])
def api_make_checks():
    """Run the gate, and say whether the door would open."""
    if _make_forbidden():
        abort(404)
    doc = request.get_json(silent=True)
    if not isinstance(doc, dict):
        return jsonify({"error": "That is not a track document."}), 400
    track, err = _draft_track(doc, timed=True)
    if err:
        return jsonify({"error": err}), 400
    rows = _run_checks(doc, track)
    h = moves_mod.fingerprint(track, doc.get("scenery"))
    drove = _DROVE.get((_drove_key(), h))
    rows.append({"ok": bool(drove), "label": "You have driven it",
                 "detail": ("%s" % _fmt_ms(drove[0])) if drove
                           else "drive it from the start line to the flag, "
                                "cleanly, and this ticks itself"})
    return jsonify({
        "checks": rows,
        "ready": all(r["ok"] for r in rows),
        "notes": [{"level": lvl, "at": at, "text": text}
                  for lvl, at, text in moves_mod.advise(doc)
                  if lvl == "note"],
        "signed_in": bool(get_current_user()),
    })


def _fmt_ms(ms):
    ms = int(ms)
    return "%d:%02d.%03d" % (ms // 60000, (ms // 1000) % 60, ms % 1000)


@app.route("/api/make/submit", methods=["POST"])
def api_make_submit():
    """Put a saved track in the queue. Structural checks block; taste does not."""
    if _make_forbidden():
        abort(404)
    user = get_current_user()
    if not user:
        return jsonify({"error": "Sign in first.", "need_login": True}), 401
    slug = (request.get_json(silent=True) or {}).get("slug")
    row = _user_track_row(slug or "")
    if row is None:
        return jsonify({"error": "Save it first."}), 404
    if not _may_edit(row, user):
        return jsonify({"error": "That is not yours."}), 403
    doc = row.doc
    track, err = _draft_track(doc, timed=True)
    if err:
        return jsonify({"error": err}), 400
    rows = _run_checks(doc, track)
    h = moves_mod.fingerprint(track, doc.get("scenery"))
    if not _DROVE.get((_drove_key(), h)):
        rows.append({"ok": False, "label": "You have driven it",
                     "detail": "drive this exact road from the start line to "
                               "the flag first"})
    bad = [r for r in rows if not r["ok"]]
    if bad:
        return jsonify({"error": "Not ready yet.", "checks": rows}), 400
    row.status = "queued"
    row.queued_at = datetime.utcnow()
    db.session.commit()
    _forget_track(row.slug)
    return jsonify({"ok": True, "status": "queued"})


# ---- forking --------------------------------------------------------------


@app.route("/api/make/fork/<slug>", methods=["POST"])
def api_make_fork(slug):
    """A document derived from anything live - pool track or somebody else's.

    **Always credited, forever.** `forked_from` is a column and not a note in
    the description, so the card says "based on Spa-Francorchamps" for as long
    as the track exists and there is no way to save a fork that has forgotten
    where it came from.

    Not everything survives the trip. Three of the nineteen sculpt their own
    geometry in code - the Costco's shell, Mount Joy's and Shroom Street's
    height fields - and a fork says so rather than quietly producing a track
    that is missing the thing it was famous for.
    """
    if _make_forbidden():
        abort(404)
    row = _user_track_row(slug)
    if row is not None:
        if row.status != "live" and not _may_edit(row, get_current_user()):
            abort(404)
        doc = dict(row.doc)
        dropped = []
        origin = row.name
    else:
        from tools import to_moves
        if slug not in set(to_moves.slugs()):
            abort(404)
        try:
            doc, dropped = to_moves.document(slug)
        except Exception as e:                                  # pragma: no cover
            return jsonify({"error": "That one cannot be forked: %s" % e}), 400
        origin = tracks_mod.get(slug)["name"]
    doc["forked_from"] = slug
    doc["name"] = "%s (fork)" % (doc.get("name") or origin)
    # Never inherit the parent's address or its board.
    doc.pop("slug", None)
    token = _stash_draft(doc)
    return jsonify({"token": token, "dropped": dropped, "origin": origin,
                    "url": url_for("make_edit", token=token)})


# ---- the gallery ----------------------------------------------------------


@app.route("/tracks")
def community_tracks():
    """Everything anybody has published, newest first.

    A page of its own as well as a shelf in the switcher, because a gallery is
    something you browse and the switcher is something you use mid-race.
    """
    if _make_forbidden():
        abort(404)
    rows = (DriveUserTrack.query.filter_by(status="live")
            .order_by(DriveUserTrack.published_at.desc().nullslast()).all())
    mine = []
    user = get_current_user()
    if user:
        mine = (DriveUserTrack.query.filter_by(author_id=user.id)
                .filter(DriveUserTrack.status != "live")
                .order_by(DriveUserTrack.updated_at.desc()).all())
    return render_template("community.html", user=user,
                           name=get_effective_name(), rows=rows, mine=mine,
                           cards=_user_cards(rows))


def _user_cards(rows):
    """The bits of a live row a card wants, without building nineteen tracks."""
    pbs = _my_pb_map()
    out = []
    for r in rows:
        t = _track_from_row(r, timed=True)
        if t is None:
            continue
        pb = pbs.get(r.slug)
        out.append({
            "slug": r.slug, "name": r.name, "difficulty": r.difficulty,
            "author": r.author.display if r.author else "somebody",
            "forked_from": r.forked_from,
            "units": int(_ribbon_length(t)),
            "ideal": t.get("ideal"),
            "checkpoints": t.get("checkpoints"),
            "pb_ms": pb.time_ms if pb else None,
        })
    return out


# ---- the queue ------------------------------------------------------------
#
# **Just drive it.** The review is not a form, it is a lap: the reason to open
# somebody's track is to find out whether it is any good, and nothing on a page
# answers that. So the queue is a list with a Drive button, and approving is one
# POST from wherever you happen to be.


@app.route("/admin/tracks")
def admin_tracks():
    """The queue. 404s for anybody who is not Chinmay, logged in or not.

    A 403 would confirm the console exists, which is the same reasoning the
    rest of `/admin` uses.
    """
    user = get_current_user()
    if not _is_admin(user) or _make_forbidden():
        abort(404)
    q = (DriveUserTrack.query
         .order_by(DriveUserTrack.queued_at.desc().nullslast(),
                   DriveUserTrack.updated_at.desc()).all())
    return render_template("admin_tracks.html", user=user,
                           name=get_effective_name(),
                           queued=[r for r in q if r.status == "queued"],
                           live=[r for r in q if r.status == "live"],
                           other=[r for r in q if r.status
                                  not in ("queued", "live")])


@app.route("/admin/tracks/<slug>/<action>", methods=["POST"])
def admin_track_action(slug, action):
    """approve, hide, unhide, reject. Four verbs and one rule.

    **What was approved is what is live.** Approving stamps `published_at` and
    the geometry hash it was approved *at*; a later edit that moves the road
    compares against that and comes back here. Rejecting keeps the row - the
    author's draft is theirs and losing it to a review would be worse than the
    track being bad.
    """
    user = get_current_user()
    if not _is_admin(user) or _make_forbidden():
        abort(404)
    row = _user_track_row(slug)
    if row is None:
        abort(404)
    note = (request.form.get("note") or "").strip()[:500]
    if action == "approve":
        row.status = "live"
        row.published_at = row.published_at or datetime.utcnow()
    elif action == "hide":
        row.status = "hidden"
    elif action == "unhide":
        row.status = "live"
    elif action == "reject":
        row.status = "draft"
        row.queued_at = None
    else:
        abort(404)
    if note:
        row.review_note = note
    db.session.commit()
    _forget_track(slug)
    return redirect(url_for("admin_tracks"))


@app.route("/admin/tracks/<slug>/drive")
def admin_track_drive(slug):
    """Drive a track that is not live, which is the whole of the review.

    The queue's Drive button used to point at `/solo/<slug>`, and that silently
    did not work: `_resolve_user_track` is live-only *on purpose* - a queued
    track resolving there would be an unlisted track with a real leaderboard,
    reachable by anybody who guessed the slug - so `/solo` bounced the reviewer
    to whatever they last drove, which reads as a mis-click rather than an
    error. The rule is right; it just had nothing carved out for the one person
    who has to drive the thing before approving it.

    So this borrows the draft path rather than widening the resolver: stash the
    row's document and hand it to `make_drive`, which drives it under
    `DRAFT_SLUG` on the same `play.html`. Nothing about `tracks.get` moves, so
    `/api/run`, `/api/start`, rooms, the switcher and the sitemap still cannot
    see it, and the lap cannot land on a board - which is what you want from a
    review lap anyway.

    The document's address is dropped for the reason `api_make_fork` drops it:
    the way back out of a draft is the editor, and an editor holding somebody
    else's slug is one Save from overwriting their track.
    """
    user = get_current_user()
    if not _is_admin(user) or _make_forbidden():
        abort(404)
    row = _user_track_row(slug)
    if row is None:
        abort(404)
    doc = dict(row.doc)
    doc.pop("slug", None)
    doc["name"] = row.name
    return redirect(url_for("make_drive", token=_stash_draft(doc)))

@app.route("/api/make/look", methods=["POST"])
def api_make_look():
    """Judge a palette. Structural failures block; taste is only ever said.

    The visual half of a palette edit never comes here - the palette is read
    entirely by `buildTrack` and the renderer, so the editor re-runs those
    locally and the road recolours with no round trip. What this call is for is
    the *words*: `look.check` and `look.advise` are the single source of truth
    for what a palette may be and what it probably should not be, and a second
    copy of eight thresholds in JavaScript is exactly the drift the palette
    contract was moved into Python to end.
    """
    if _make_forbidden():
        abort(404)
    pal = request.get_json(silent=True)
    if not isinstance(pal, dict):
        return jsonify({"error": "That is not a palette."}), 400
    try:
        look.check("draft", pal, where="This palette")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e), "advice": []})
    return jsonify({"ok": True, "advice": [
        {"level": lvl, "key": key, "text": text}
        for lvl, key, text in look.advise(pal)]})


@app.route("/api/make/lap", methods=["POST"])
def api_make_lap():
    """What a lap of this would take, and the three medals.

    Its own call because it is a hundred times the cost of the road: a
    racing-line relaxation and a speed profile over every station, about 550ms
    against the ribbon's 4ms. The editor asks for it long after you stop typing,
    and never while you are still moving a slider.
    """
    if _make_forbidden():
        abort(404)
    doc = request.get_json(silent=True)
    if not isinstance(doc, dict) or not (doc.get("moves") or ()):
        return jsonify({"error": "That is not a track document."}), 400
    if len(doc.get("moves") or ()) > MAKE_MAX_MOVES:
        return jsonify({"error": "Too many moves."}), 400
    try:
        track = tracks_mod.from_document(
            str(doc.get("slug") or "draft"), doc, timed=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ideal": track["ideal"], "medals": track["medals"]})


@app.route("/scenery/<slug>.js")
def track_scenery(slug):
    """A track's own mesh code, for the switcher.

    The play page *inlines* this for the track you arrive on (see the comment at
    the foot of play.html), which is right for arrival and useless for a switch:
    `switchTrack` swaps the world without navigating, so the second track's
    scenery has to come from somewhere. Here.

    Not decoration. Costco's building and Mount Joy's mountain are in the
    collider - most of each track's solid geometry - so a switch that builds
    without them is not a plainer version of the track, it is a different one,
    and a lap driven on it would go to `/api/run` as a time on this one.

    An hour of `max-age`, matching what nginx gives an un-tokened asset under
    `static/`: nothing can bust this URL, and `send_from_directory` adds an ETag
    so an edited file is still picked up on revalidate. Restricted to slugs in
    the pool because `slug` comes off the wire.

    **Served by Python and not by nginx**, which is against the rule the rest of
    `static/` follows, deliberately. These files live in `tracks/<slug>/` rather
    than under `static/`, so handing them to nginx means a second `alias` block
    in the vhost - hand-managed, undone by a `certbot --nginx` renewal, and
    silent when it goes. The bytes do not justify it: two tracks, ~60kB between
    them, only on a switch onto one of them, and a 304 after the first. Move it
    if a third and fourth track ship one.
    """
    if not tracks_mod.get(slug) or tracks_mod.scenery_path(slug) is None:
        abort(404)
    return send_from_directory(os.path.join(tracks_mod.HERE, slug), "scenery.js",
                               mimetype="text/javascript", max_age=3600)
