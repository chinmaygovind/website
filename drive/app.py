import eventlet
eventlet.monkey_patch()

import os
import re
import sys
import hashlib
import json as json_mod
import time
import uuid
import random
import string
from functools import wraps
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, send_from_directory, abort)
from flask_socketio import SocketIO, join_room, leave_room, emit
from sqlalchemy import func

import models as models_mod
from models import (db, User, DriveStats, DriveTime, DriveStart, DriveRunCheck,
                    DriveGame, DrivePlayer, DriveRace, DriveGarage, DriveCheatFlag)
import tracks as tracks_mod
import tuning
import laptime
import runcheck
import racecheck
import visits
import bots as bots_mod
import botsim
import garage as garage_mod
# The palette and the hash moved into `garage.py`, with the rest of what a car
# is allowed to look like. Imported by name here because five routes call it.
from garage import color_for


def script_json(obj):
    """JSON that is safe to drop inside a ``<script>`` block.

    ``json.dumps`` does not escape ``<``, and every roster on this site is
    embedded straight into a script tag. So a display name of
    ``</script><svg onload=...>`` - thirty characters, which was exactly the
    limit - ended the script tag early and the rest of it was parsed as HTML:
    stored XSS that ran for every other player in the lobby, on a cookie shared
    across all four games. `naming.check_display_name` now rejects the angle
    brackets too, but the escaping is the half that has to be right, because it
    is the half that does not depend on remembering.

    Jinja's ``|tojson`` does exactly this and would be the obvious fix. It is not
    used because it cannot be told to use compact separators - only
    ``JSONProvider.response`` honours ``compact`` - and the track payload carries
    the whole ribbon, so ``", "`` instead of ``","`` is +17%: 12KB a page load on
    Sandy Cove.

    U+2028 and U+2029 are in here because they are valid in a JSON string and are
    *line terminators* in JavaScript, so an unescaped one is a syntax error at
    best.
    """
    return (json_mod.dumps(obj, separators=(",", ":"))
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))

# ---------------------------------------------------------------------------
# Config (mirrors ERS/KoT: shared accounts + cross-subdomain SSO)
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

_cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
if _cookie_domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain
if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

# One resolution of "which database", in models.py, because `verify.py` runs in
# a process of its own and has to arrive at the same file this does.
DATABASE_URL = models_mod.database_url()
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# The SQLite pragmas (WAL, and a busy timeout) live in `models.py` now, where
# `verify.py` gets them too - it writes to this same file from a process of its
# own, and a per-connection busy timeout it never set is a write that fails
# rather than waits.

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

with app.app_context():
    db.create_all()  # creates drive_* tables; never touches the shared users table
    # And the one thing `create_all` cannot do - see `models.ensure_columns`.
    # `drive_players` grew two columns for the room's bots, and a mapped column
    # the table does not have makes every query against it fail, so this runs
    # here rather than being a step somebody has to remember over SSH.
    models_mod.ensure_columns(db, log=app.logger)

# Every request logged, and this service's players marked as here. `visits.py`
# is one file copied into all five services and is byte-identical in each - the
# same convention `models.py` follows, and `tests/test_no_drift.py` on the main
# repo is what stops the copies drifting.
visits.init_app(app, db, "drive")

# What a car looks like lives in `garage.py`: the palette, every slot somebody
# can change, and the gates on the few that are earned. `color_for` above is
# still the answer for anybody who has not chosen - a guest, or an account that
# has never opened the garage.


def _garage_row(user, create=False):
    """The `drive_garage` row for a user, or None.

    `create=False` by default for the same reason `_stats` reads that way: a
    stranger loading somebody's page must not leave a row behind for them.
    """
    if not user:
        return None
    row = DriveGarage.query.filter_by(user_id=user.id).first()
    if row is None and create:
        row = DriveGarage(user_id=user.id, livery_json="{}", earned_json="[]")
        db.session.add(row)
        db.session.commit()
    return row


def _earned_for(user, row=None, holders=None, leaders=None):
    """What this account has earned, writing down the losable ones if they are new.

    Most gates are counters that only go up and are recomputed every time. The
    ones in `garage.KEPT` are things true *right now* - a track record or the top
    of the Time Trial board, both of which can be taken off you where the badge
    for them cannot - so the moment one is true it has to be persisted or it
    would be lost the next time somebody beats the lap. Doing it here rather than
    in a tool is also why no backfill is needed: every current holder earns
    theirs the first time anything asks.
    """
    if not user:
        return set()
    row = row if row is not None else _garage_row(user)
    already = row.earned if row else set()
    got = garage_mod.earned(user, already, holders, leaders)
    keep = got & garage_mod.KEPT
    if keep - already:
        row = row or _garage_row(user, create=True)
        row.earned_json = json_mod.dumps(sorted(already | keep))
        row.updated_at = datetime.utcnow()
        db.session.commit()
    return got


def _livery_for(user, holders=None, name=None, leaders=None):
    """The livery to draw for somebody, gates already applied.

    Every path that sends a car anywhere goes through here - the play page, a
    room's roster, a ghost, a stored replay - which is what makes a gate real
    rather than a suggestion the client is trusted to honour.

    `name` is **what a guest is hashed off**, and it is not optional decoration.
    Guests have no account to keep a livery against, so their colour is still
    `color_for` of the name they typed - which is what spreads a room's guests
    out and is precisely what let the first-free colour rule be deleted. Without
    it every guest resolves to `GUEST_COLOR` and a room of four of them is four
    identical red cars, which is the bug the deleted rule existed to prevent,
    reintroduced from the other end.
    """
    if not user:
        return garage_mod.resolve({}, name, set())
    row = _garage_row(user)
    got = _earned_for(user, row, holders, leaders)
    return garage_mod.resolve(garage_mod.loads(row.livery_json if row else None),
                              user.username, got)


def _car_livery(user):
    """The livery for the car *you* are about to drive, guests included."""
    return _livery_for(user, name=get_effective_name())


MAX_ROOM = 8

# In-memory per-room locks (single eventlet worker, like ERS/KoT).
_locks = {}


def _lock(code):
    return _locks.setdefault(code, eventlet.semaphore.Semaphore(1))


def _now_ms():
    return int(time.time() * 1000)

# The main site, which is where /accounts and the flag art are served from.
# Deliberately NOT `SITE_URL`: that name is already taken on the box, where it
# means *this* service's own public address (drive/.env has
# SITE_URL=https://drive.cgovind.com), and quietly borrowing it would point
# every flag at the wrong host.
MAIN_SITE_URL = os.environ.get("MAIN_SITE_URL", "https://cgovind.com").rstrip("/")

# Drive's own public origin. Only the share card needs it: `og:image` has to be
# an absolute URL and nothing that reads one ever sees a relative path resolved.
# It cannot come from `request` - there is no ProxyFix here, so behind nginx
# Flask believes every request arrived over http, and a card served as http on
# an https-only site is the sort of thing that quietly fails to render.
SELF_URL = os.environ.get("DRIVE_URL", "https://drive.cgovind.com").rstrip("/")

# One sentence, kept the same as `static/manifest.json`'s `description`. There is
# no way to share the string with a JSON file that the browser reads directly, so
# if you change one, change the other.
OG_DESCRIPTION = ("Low-poly time trials and multiplayer races. Pick a track, "
                  "chase the medal times, bump your friends off the road.")


# ---------------------------------------------------------------------------
# Auth helpers (shared with TTR/ERS/KoT via the users table + session cookie)
# ---------------------------------------------------------------------------

def get_session_key():
    if "session_key" not in session:
        session["session_key"] = str(uuid.uuid4())
    return session["session_key"]


def get_current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def get_effective_name():
    """The name to put on a seat: theirs if they chose one, else their username.

    Everything that writes a player's name into a game reads it from here, so
    the display name set on cgovind.com/accounts follows somebody into every
    lobby without any of the game code knowing that is what happened. A guest
    is whatever they typed.
    """
    u = get_current_user()
    return u.display if u else session.get("guest_name", "Guest")


def require_name(f):
    """Driving alone needs no identity at all; sharing a room needs a name."""
    @wraps(f)
    def wrapped(*a, **kw):
        if not get_current_user() and not session.get("guest_name"):
            return redirect(url_for("login_page", next=request.path))
        return f(*a, **kw)
    return wrapped


# Addresses under cgovind.com/accounts that are pages rather than people.
# Registering one of these would create an account whose own profile URL - and
# whose password-reset link - went somewhere else entirely, so it is refused
# here as well as there. Kept in step with `accounts/naming.py`'s RESERVED by
# `test_reserved_names_match_the_accounts_site`.
RESERVED_USERNAMES = {
    "settings", "forgot", "reset", "login", "logout", "register", "avatar",
    "confirm-email", "confirm", "me", "admin", "api", "static", "new", "edit",
}


def _valid_username(u):
    if u.lower() in RESERVED_USERNAMES:
        return False
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9_\-]{1,29}$', u))


def _make_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not DriveGame.query.filter_by(code=code).first():
            return code


def _stats(user, create=True):
    """The user's DriveStats row, created on first touch.

    ``create=False`` is for reading somebody *else's* page: a stranger opening a
    profile should not write a row, so it hands back an unattached
    ``DriveStats`` instead - every figure on it is zero, which is exactly what
    a driver with no races has, and nothing is committed.
    """
    if not user:
        return None
    if user.drive is None:
        if not create:
            return DriveStats()
        user.drive = DriveStats()
        db.session.commit()
    return user.drive


def _derive_asset_version():
    """A `?v=` token that moves when anything under `static/` moves.

    This used to be `ASSET_VERSION` from the box `.env`, bumped by hand, and a
    missed bump cost nothing because every static response also carried
    `Cache-Control: no-cache` - the browser revalidated whatever the token said.
    nginx now serves `static/` with a real cache lifetime, so a missed bump would
    mean stale JS for the length of that lifetime, and the token is derived rather
    than remembered.

    The newest mtime under the tree is enough. The deploy is `git reset --hard`,
    which only writes files whose contents actually changed, so the token moves
    exactly when the assets do and not on every deploy.

    **This does not make long-lived caching safe on its own.** Only four files are
    requested with the token on them (`style.css`, `game.js`, `garage.js`,
    `pending.js`); the rest of the module graph - `three.module.js`, `trackmesh.js`,
    `physics.js`, `render.js`, `course.js`, `sound.js` - is reached by bare
    `import` from inside `game.js` and carries no token at all. That is why the
    nginx cache lifetime on `/static/` is short. Version those imports before
    reaching for `immutable`.
    """
    newest = 0.0
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                m = os.stat(os.path.join(dirpath, name)).st_mtime
            except OSError:                  # vanished mid-walk; it cannot be the newest
                continue
            if m > newest:
                newest = m
    return str(int(newest)) if newest else "1"


# Walked once at import rather than per request: the tree cannot change under a
# running worker, and a deploy restarts it. An explicit `ASSET_VERSION` still
# wins, so the old knob is not silently ignored - but it is no longer needed, and
# leaving one set pins the token to whatever it says.
ASSET_VERSION = os.environ.get("ASSET_VERSION") or _derive_asset_version()


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(),
            "effective_name": get_effective_name(),
            "track_names": {t["slug"]: t["name"] for t in tracks_mod.TRACKS},
            # Where the flag art lives. It is one copy on the main site
            # rather than four, so a game refers to it by absolute URL - see
            # `UserProfile.flag_path`, which returns the path half.
            "site_url": MAIN_SITE_URL,
            # Drive's own origin and one-liner, for the share card in base.html.
            # `og_title` falling back to the page's own <title> and `og_image` to
            # the wheel are the defaults every page that is not about one track
            # wants; the track pages pass `_track_og()` over the top of them.
            "drive_url": SELF_URL,
            "og_description": OG_DESCRIPTION,
            "og_title": None,
            "og_image": "/static/img/og.png",
            # What the heartbeat in base.html says about this page. Derived
            # from the endpoint rather than passed by each route, so a new page
            # gets a sensible answer without anybody remembering to add one -
            # and the play page overrides it in JS, because there the track can
            # change under the page with no navigation at all.
            "presence_where": PRESENCE_BY_ENDPOINT.get(request.endpoint or "", "home"),
            # Facts about this server rather than about a page: whether it can
            # run bots at all (it needs a JS engine, and `DRIVE_BOTS=0` turns
            # them off on the box without a deploy) and how many cars fit. Here
            # rather than passed by each route because `play.html` is rendered
            # by three of them and a room is only one.
            "bots_on": botsim.available(),
            "max_bots": botsim.MAX_BOTS,
            "max_room": MAX_ROOM,
            "bot_levels": [(lv, bots_mod.LABEL[lv]) for lv in bots_mod.OFFERED],
            "bot_default": (bots_mod.DEFAULT_LEVEL
                            if bots_mod.DEFAULT_LEVEL in bots_mod.OFFERED
                            else bots_mod.OFFERED[0]),
            "asset_version": ASSET_VERSION}


PRESENCE_BY_ENDPOINT = {
    "lobbies": "lobby",
    "room": "room",
    "solo": "solo",
    "solo_last": "solo",
    "garage_page": "garage",
    "race_replay": "replay",
    "track_board": "board",
    "leaderboard": "board",
}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET"])
def login_page():
    if get_current_user() or session.get("guest_name"):
        return redirect(request.args.get("next") or url_for("lobbies"))
    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    ident = data.get("username", "").strip()
    password = data.get("password", "")
    user = User.query.filter((User.username == ident) | (User.email == ident.lower())).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401
    session.permanent = True
    session["user_id"] = user.id
    session.pop("guest_name", None)
    return jsonify({"ok": True})


@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not username or not email or not password:
        return jsonify({"ok": False, "error": "Please fill in all fields."}), 400
    if not _valid_username(username):
        return jsonify({"ok": False, "error": "Username must be 2-30 characters, start with a letter, and use only letters, numbers, hyphens or underscores."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"ok": False, "error": "Please enter a valid email address."}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "Username already taken. If it's yours, just log in - the same account works here."}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"ok": False, "error": "An account with that email already exists - log in instead."}), 409
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session.permanent = True
    session["user_id"] = user.id
    session.pop("guest_name", None)
    return jsonify({"ok": True})


# The character rule for a guest's name, which is the same rule an account's
# display name gets from `accounts/naming.py` on the website service. Drive is
# its own service with its own venv and cannot import that module, so this is a
# copy - the convention `visits.py` already follows here - and
# `tests/test_no_drift.py` reads the other file and fails when the two stop
# agreeing. Control characters, angle brackets (a roster is embedded in a
# `<script>` block; see `script_json`) and the bidi overrides that let a string
# render as text it does not contain.
GUEST_BAD_CHARS = re.compile("[\x00-\x1f\x7f<>\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


@app.route("/guest", methods=["POST"])
def guest_login():
    """A name is all a guest needs - but it is still a name on other people's screens.

    It used to be `.strip()[:20]` and nothing else, which meant the one piece of
    text on this site that took no validation at all went into the same roster
    every account's display name goes into. Twenty characters is too short for
    the payload that `naming` now rejects, but "too short to exploit today" is
    not a rule, and a guest could also simply type an existing player's name.
    """
    data = request.json or {}
    name = (data.get("name", "") or "").strip()[:20]
    if not name:
        return jsonify({"ok": False, "error": "Enter a name."}), 400
    if GUEST_BAD_CHARS.search(name):
        return jsonify({"ok": False, "error": "That name can't contain that "
                                              "character."}), 400
    if not any(ch.isalnum() for ch in name):
        return jsonify({"ok": False, "error": "A name needs at least one "
                                              "letter or number."}), 400
    session.permanent = True
    session["guest_name"] = name
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("guest_name", None)
    return redirect(url_for("index"))


@app.route("/favicon.ico")
def favicon():
    """The icon for everything that never reads the `<link>` tags.

    Feed readers, crawlers, chat unfurlers and older browsers all just ask the
    origin root for `/favicon.ico`, and until this existed they got Drive's 404
    page. The file itself is rendered from `icon.svg` like every other raster.
    """
    return send_from_directory(os.path.join(app.static_folder, "img"),
                               "favicon.ico", mimetype="image/vnd.microsoft.icon")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _my_pb_map():
    """{slug: DriveTime} for the logged-in user, for the track-select screen."""
    user = get_current_user()
    if not user:
        return {}
    return {t.track: t for t in DriveTime.query.filter_by(user_id=user.id).all()}


def _records():
    """{slug: (time_ms, holder, set_at)} - the standing record on every track.

    ``holder`` is the ``User``, not their name, so the templates can put the
    flag and the profile link on it the same way every other board does - the
    two tables on the Records page sat one above the other with only one of
    them linking anybody. It is ``None`` where the row's account is gone.

    ``set_at`` is the holder's ``updated_at``, which is when *this* lap was set:
    a better run replaces the row wholesale and stamps it, so the column cannot
    drift into meaning "when they first drove here".

    It is also where a re-driven lap is let onto the board. Nothing in Drive runs
    on a timer, and the process that checks a record writes its verdict and
    exits - so the settling happens in the one function every page that shows a
    record already calls. Normally it is a query that finds nothing.
    """
    _settle_checks()
    rows = (db.session.query(DriveTime.track, func.min(DriveTime.time_ms))
            .group_by(DriveTime.track).all())
    out = {}
    for slug, best in rows:
        holder = (DriveTime.query.filter_by(track=slug, time_ms=best)
                  .order_by(DriveTime.updated_at.asc()).first())
        out[slug] = (best, holder.user if holder else None,
                     holder.updated_at if holder else None)
    return out


def _my_rank_map(pbs=None):
    """{slug: rank} for the logged-in user's PB on each track.

    A time on its own says nothing until you know what else is on the board, so
    every place a PB is shown says where it places. One count per track the user
    has actually driven, which is at most the size of the pool.
    """
    pbs = _my_pb_map() if pbs is None else pbs
    return {slug: DriveTime.query.filter(DriveTime.track == slug,
                                         DriveTime.time_ms < row.time_ms).count() + 1
            for slug, row in pbs.items()}


def _ordinal(n):
    """1 -> "1st". A placing wants saying as one; "1" on its own reads as a count."""
    if n % 100 in (11, 12, 13):
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def _time_trial_board():
    """The Time Trial board as the page wants it: `garage.time_trial_board()`
    with each driver's best placing said as an ordinal.

    The scoring itself lives in `garage.py` rather than here, because the crown
    badge is now gated on topping this board and a second implementation of "who
    is first" is exactly the drift this repo keeps testing against. The split is
    where it usually is: garage owns the rule, this owns the words.
    """
    return [dict(r, best=_ordinal(r["best"]))
            for r in garage_mod.time_trial_board()]


# The track you were last on, so that "Solo" is a door back into the game rather
# than a menu. Kept in the session (not localStorage) because the /solo route has
# to know it server-side to render the right track on the first paint.
def _remember_track(slug):
    session["last_track"] = slug


def _last_track():
    slug = session.get("last_track")
    return slug if tracks_mod.get(slug) else tracks_mod.TRACKS[0]["slug"]


@app.route("/")
def index():
    """The home page: what this is, then the tracks.

    It is no longer the way in - "Solo" and "Drive now" both go straight to
    /solo, which puts you on the track you were last driving. This page is here
    to be read, so it leads with how the game works and keeps the track list
    below as a way of picking a specific one.
    """
    pbs = _my_pb_map()
    return render_template("index.html", tracks=tracks_mod.summaries(),
                           pbs=pbs, ranks=_my_rank_map(pbs), records=_records(),
                           name=get_effective_name(), user=get_current_user())


def _next_slug(slug):
    """The track after this one in the pool, for the "next track" button."""
    slugs = [t["slug"] for t in tracks_mod.TRACKS]
    if slug not in slugs:
        return slugs[0]
    return slugs[(slugs.index(slug) + 1) % len(slugs)]


def _track_cards():
    """Everything the track switcher shows: the track, and your time on it.

    Built here rather than in the switcher because a card wants the track pool,
    your PB row and where that PB places, and only the server can see all three.

    Deliberately *not* the record: the switcher is a menu for choosing where to
    drive, and a second time by somebody else on every card turns picking a
    track into a comparison. The record is on the board and the home page, which
    are for reading.
    """
    pbs = _my_pb_map()
    ranks = _my_rank_map(pbs)
    # The one module-level token, not a second read of the environment. The
    # switcher's card art is the only `?v=` built in Python rather than in a
    # template, and it was reading `ASSET_VERSION` directly - which pinned every
    # preview at `?v=1` the moment that variable stopped being set, and pinned it
    # for a month once nginx started honouring the token. Re-running
    # `tools/shoot_tracks.py` moves this now, because the pictures are under
    # `static/`.
    ver = ASSET_VERSION
    out = []
    for t in tracks_mod.summaries():
        slug = t["slug"]
        pb = pbs.get(slug)
        out.append(dict(t, image="/static/img/tracks/%s.png?v=%s" % (slug, ver),
                        pb_ms=(pb.time_ms if pb else None),
                        pb_medal=(pb.medal_shown if pb else None),
                        pb_rank=ranks.get(slug)))
    return out


@app.route("/solo")
def solo_last():
    """Solo, on whatever you were driving last.

    The point of the track switcher is that picking a track is something you do
    *while driving*, not a page you pass through on the way in - so this is the
    only URL solo needs, and it does not change when you switch track.
    """
    return _play_solo(_last_track())


@app.route("/solo/<slug>")
def solo(slug):
    """A specific track, which is still a real URL people link to and bookmark."""
    if not tracks_mod.get(slug):
        return redirect(url_for("solo_last"))
    return _play_solo(slug)


def fmt_ms(ms):
    """A lap time written the way the game writes it: `1:11.234`.

    The templates each had this as an inline format string, which was fine while
    a time was only ever *rendered*; a share card's title is built in Python and
    has to say the same thing, and two spellings of a lap time is the sort of
    difference nobody notices until one of them rounds the other way.
    """
    return "%d:%06.3f" % (ms // 60000, (ms % 60000) / 1000.0)


def _shared_lap(slug):
    """The lap named by `?watch=<id>`, when there is one and it can be played.

    Only for the unfurl: the *game* fetches the ghost itself through
    `/api/ghost`, and this is the server answering "what is this link a link
    to" for a crawler that will never run any of that. Scoped to the track for
    the same reason `/api/ghost` scopes it, and it insists on a stored replay -
    a card promising somebody's lap that then toasts "that lap is no longer
    there" is worse than the generic one.
    """
    who = request.args.get("watch", "")
    if not who.isdigit():
        return None
    return (DriveTime.query.filter_by(id=int(who), track=slug)
            .filter(DriveTime.ghost.isnot(None)).first())


def _track_og(track, lap=None):
    """The unfurl for a page about one track - or about one lap on it.

    A pasted link is most of how this travels, so what it shows is worth being
    specific about: the track's own card rather than the wheel, its blurb rather
    than the site's one-liner, and - when the link names a lap - the time and
    whose it is, because "1:11.234 on Big Red" is an argument and "Drive" is not.
    """
    og = {"og_image": "/static/img/og/%s.png" % track["slug"],
          "og_title": "%s | Drive" % track["name"],
          "og_description": track["blurb"]}
    if lap is not None:
        who = lap.user.display if lap.user else "Somebody"
        og["og_title"] = "%s on %s | Drive" % (fmt_ms(lap.time_ms), track["name"])
        og["og_description"] = (
            "%s drove %s here. Open it to watch the lap, then try to beat it."
            % (who, fmt_ms(lap.time_ms)))
    return og


def _play_solo(slug):
    track = tracks_mod.get(slug)
    _remember_track(slug)
    user = get_current_user()
    pb = DriveTime.query.filter_by(user_id=user.id, track=slug).first() if user else None
    return render_template(
        "play.html", mode="solo", track=track,
        **_track_og(track, _shared_lap(slug)),
        track_json=script_json(_track_payload(track["slug"])),
        track_scenery=tracks_mod.scenery_source(track["slug"]),
        tuning_json=tuning.as_json(), room=None, me_json="null",
        roster_json="[]", name=get_effective_name(), user=user,
        pb_ms=(pb.time_ms if pb else None), next_slug=_next_slug(slug),
        pb_splits=({slug: pb.splits} if pb else {}),
        # One answer, not two. `car_color` is the older field and is still read
        # by everything that wants a swatch rather than a car (the self dot on
        # the minimap, a standings row in solo), so it is taken *from* the
        # livery: computing it separately is how the two came to disagree for a
        # guest, whose livery is hashed off the name they typed while
        # `color_for(None)` is the one guest red.
        car_color=_car_livery(user)["body"],
        car_livery=script_json(_car_livery(user)),
        tracks=tracks_mod.summaries(), cards=_track_cards())


@app.route("/garage")
def garage_page():
    """Your car, on a turntable, with everything you can change about it.

    Accounts only, and that is not a paywall: a livery has to be stored against
    somebody, and a guest is a name in a session that will be gone tomorrow.
    Guests still drive - they just drive the colour their name hashes to.
    """
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page", next="/garage"))
    row = _garage_row(user)
    got = _earned_for(user, row)
    data = garage_mod.payload(user, garage_mod.loads(row.livery_json if row else None),
                              got, garage_mod.progress(user))
    return render_template("garage.html", user=user, name=get_effective_name(),
                           garage_json=script_json(data),
                           tracks=tracks_mod.summaries())


@app.route("/api/garage", methods=["GET", "POST"])
def api_garage():
    """Read or write the livery. The gates are applied on the way *out*.

    A POST is stored as asked for even where it is not allowed yet - see
    `garage.validate` against `garage.resolve`. Somebody who picks the pearl
    before their third gold has said what they want, and it goes on by itself
    the day they earn it rather than needing to be asked for twice.
    """
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Log in to use the garage."}), 401
    if request.method == "POST":
        row = _garage_row(user, create=True)
        row.livery_json = garage_mod.dumps(request.json or {})
        row.updated_at = datetime.utcnow()
        db.session.commit()
    else:
        row = _garage_row(user)
    got = _earned_for(user, row)
    return jsonify(dict(garage_mod.payload(
        user, garage_mod.loads(row.livery_json if row else None), got,
        garage_mod.progress(user)), ok=True))


@app.route("/lobbies")
@require_name
def lobbies():
    payload = _lobbies_payload()
    mine = None
    for p in _my_players(get_session_key()):
        mine = {"code": p.game.code}
        break
    return render_template("lobbies.html", games=payload["games"],
                           tracks=tracks_mod.summaries(), mine=mine,
                           online=_online_now(),
                           user=get_current_user(), name=get_effective_name())


def _online_now():
    """Who is about, anywhere on cgovind.com, for the lobbies page.

    Across all four games and not just this one, which is the point: the
    question a lobby raises is "is there anybody around to race", and somebody
    currently in King of Tokyo is somebody you can ask. Each row carries where
    they are so the answer is honest about what they are already doing.
    """
    rows = visits.online_now(db.session.connection(), limit=12)
    for r in rows:
        r["label"] = PRESENCE_LABEL.get(r["service"], "Online")
        if r["service"] == "drive" and r["detail"]:
            r["label"] = r["detail"]
    return rows


# The four games as a profile would name them, for the one-line "who is on"
# list. Deliberately short: this is a sidebar, not a profile.
PRESENCE_LABEL = {"drive": "Drive", "ttr": "Ticket to Ride",
                  "ers": "Egyptian Rat Screw", "kot": "King of Tokyo",
                  "site": "On the site"}


@app.route("/room/<code>")
@require_name
def room(code):
    game = DriveGame.query.filter_by(code=code.upper()).first()
    if not game:
        return redirect(url_for("lobbies"))
    me = DrivePlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
    if not me:
        return redirect(url_for("lobbies"))
    track = tracks_mod.get(game.track) or tracks_mod.TRACKS[0]
    _remember_track(track["slug"])
    user = get_current_user()
    pb = DriveTime.query.filter_by(user_id=user.id, track=track["slug"]).first() if user else None
    return render_template(
        "play.html", mode="room", track=track,
        track_json=script_json(_track_payload(track["slug"])),
        track_scenery=tracks_mod.scenery_source(track["slug"]),
        tuning_json=tuning.as_json(), room=game,
        me_json=script_json(me.to_dict(_livery_for(me.linked_user,
                                                   name=me.name))),
        roster_json=script_json(_roster(game)),
        name=get_effective_name(), user=user,
        pb_ms=(pb.time_ms if pb else None), next_slug=_next_slug(track["slug"]),
        pb_splits=({track["slug"]: pb.splits} if pb else {}),
        # One answer, not two. `car_color` is the older field and is still read
        # by everything that wants a swatch rather than a car (the self dot on
        # the minimap, a standings row in solo), so it is taken *from* the
        # livery: computing it separately is how the two came to disagree for a
        # guest, whose livery is hashed off the name they typed while
        # `color_for(None)` is the one guest red.
        car_color=_car_livery(user)["body"],
        car_livery=script_json(_car_livery(user)),
        tracks=tracks_mod.summaries(), cards=_track_cards())


@app.route("/j/<code>")
@require_name
def join_link(code):
    """The share link: open it and you are in the room.

    Everything else about joining is a form on the lobbies page, which is fine
    when you can see the room and wrong when somebody is trying to hand you
    theirs - "go to drive.cgovind.com, press Join, type A7QK2P" is three
    instructions where a link is none.

    Holding the link is the invitation, so it opens a private room without the
    passcode: the passcode exists to keep a room out of a stranger's hands, and
    a stranger does not have the link. `require_name` is still in the way, so
    somebody with no account is asked who they are first and lands back here.
    """
    code = (code or "").strip().upper()
    game = DriveGame.query.filter_by(code=code).first()
    if not game:
        return redirect(url_for("lobbies"))
    sk = get_session_key()
    if not DrivePlayer.query.filter_by(game_id=game.id, session_key=sk).first():
        if len(game.players) >= game.max_players:
            return redirect(url_for("lobbies"))
        _leave_other_rooms(sk)
        _add_player(game)
        _broadcast_lobbies()
    return redirect(url_for("room", code=game.code))


@app.route("/race/<int:race_id>")
def race_replay(race_id):
    """One finished race, watched again from any car in it.

    The same page the game is played on, in a third mode. A replay is a track,
    a set of cars and a clock, and the play page is already the only thing that
    knows how to draw those - reimplementing a lighter version of it would be a
    second renderer to keep in step with the first.

    The cars themselves are not in the page: eight replays of a two-minute race
    is most of a megabyte of numbers, so the shell loads and fetches them.
    """
    race = DriveRace.query.get(race_id)
    if not race:
        return redirect(url_for("index"))
    track = tracks_mod.get(race.track) or tracks_mod.TRACKS[0]
    user = get_current_user()
    return render_template(
        "play.html", mode="replay", track=track,
        track_json=script_json(_track_payload(track["slug"])),
        track_scenery=tracks_mod.scenery_source(track["slug"]),
        tuning_json=tuning.as_json(), room=None, me_json="null",
        roster_json="[]", name=get_effective_name(), user=user,
        pb_ms=None, next_slug=_next_slug(track["slug"]), pb_splits={},
        # One answer, not two. `car_color` is the older field and is still read
        # by everything that wants a swatch rather than a car (the self dot on
        # the minimap, a standings row in solo), so it is taken *from* the
        # livery: computing it separately is how the two came to disagree for a
        # guest, whose livery is hashed off the name they typed while
        # `color_for(None)` is the one guest red.
        car_color=_car_livery(user)["body"],
        car_livery=script_json(_car_livery(user)),
        # Where the way out of the replay goes. A race is watched from the room
        # that drove it, so the way out of it should be the way back in - and
        # the seat is still there to go back to, see `_seated_room`. `None` is
        # somebody who is in no room (a shared link, or the lobby list), and the
        # buttons fall back to what they always did.
        back_room=_seated_room(),
        race=race, tracks=tracks_mod.summaries(), cards=_track_cards())


@app.route("/api/race/<int:race_id>")
def api_race(race_id):
    """Every car in a finished race, unpacked - see `race_replay`."""
    race = DriveRace.query.get(race_id)
    if not race:
        return jsonify({"error": "no such race"}), 404
    cars = []
    for c in race.cars:
        frames = runcheck.unpack_ghost(c.get("ghost"))
        if not frames:
            continue
        cars.append({"pid": c.get("pid"), "name": c.get("name"),
                     "color": c.get("color"),
                     # Absent on any race recorded before the garage existed,
                     # which the renderer reads as "just the colour" - so an old
                     # replay plays back on the car it was driven in.
                     "livery": c.get("livery"), "ms": c.get("ms"),
                     "dnf": c.get("dnf"), "frames": frames})
    return jsonify({"ok": True, "id": race.id, "track": race.track,
                    "hz": race.hz or REPLAY_HZ, "ms": race.ms,
                    "why": race.why, "cars": cars})


@app.route("/track/<slug>")
def track_board(slug):
    track = tracks_mod.get(slug)
    if not track:
        return redirect(url_for("index"))
    _settle_checks()          # a lap that has just been cleared belongs on it
    rows = (DriveTime.query.filter_by(track=slug)
            .order_by(DriveTime.time_ms.asc()).limit(100).all())
    # One query for the whole board rather than one per row, clamped the same way
    # the account page clamps it (see `_starts_for`).
    started = {s.user_id: (s.starts or 0) for s in
               DriveStart.query.filter(DriveStart.track == slug,
                                       DriveStart.user_id.in_([r.user_id for r in rows])).all()}
    starts = {r.id: max(started.get(r.user_id, 0), r.runs or 0) for r in rows}
    # The same shape the in-game board uses, so a lap opens the same way in both
    # places rather than each growing its own idea of what a lap is.
    laps = [{"id": r.id, "name": r.user.display if r.user else "?",
             "time_ms": r.time_ms, "splits": r.splits,
             "medal": r.medal_shown, "has_ghost": bool(r.ghost)} for r in rows]
    return render_template("track.html", track=track, rows=rows, laps=laps,
                           starts=starts, tracks=tracks_mod.summaries(),
                           **_track_og(track),
                           user=get_current_user(), name=get_effective_name())


@app.route("/leaderboard")
def leaderboard():
    top = (DriveStats.query.join(User)
           .filter(DriveStats.races > 0, User.is_bot.isnot(True))
           .order_by(DriveStats.elo.desc()).limit(100).all())
    return render_template("leaderboard.html", stats=top,
                           tracks=tracks_mod.summaries(), records=_records(),
                           tt=_time_trial_board(),
                           user=get_current_user(), name=get_effective_name())


@app.route("/account")
def account():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page", next="/account"))
    return _account_page(user, is_me=True)


@app.route("/account/<username>")
def account_for(username):
    """Somebody else's Drive record, which is where the boards point.

    A name on a Drive leaderboard is a driver, and the next thing to know about
    a driver is their laps, their medals and how many goes each track has had
    out of them - which is this page, here, rather than four games away on the
    main site. The way on to the rest of them is a link *on* it, so the two
    profiles are a step apart in the order somebody actually reads them.
    """
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if user is None:
        abort(404)
    # One canonical spelling per profile, and one canonical address for your
    # own: `/account` is where the nav sends you and where the settings live,
    # so a link to yourself by name lands on the same page rather than a
    # second copy of it that quietly cannot be edited.
    me = get_current_user()
    if me and me.id == user.id:
        return redirect(url_for("account"))
    if user.username != username:
        return redirect(url_for("account_for", username=user.username), code=301)
    return _account_page(user, is_me=False)


def _account_page(user, is_me):
    _settle_checks(user.id)
    times = (DriveTime.query.filter_by(user_id=user.id)
             .order_by(DriveTime.updated_at.desc()).all())
    starts = _starts_for(user.id, times)
    by_track = {t.track: t for t in times}

    def _row(slug):
        # A track you have started and never finished has no `drive_times` row,
        # so it has no time and no medal - the row is there to say how many
        # goes it has had out of you, which is the one thing a table of times
        # alone cannot tell you.
        row = by_track.get(slug)
        return {"slug": slug, "time": row,
                "starts": starts.get(slug, 0) or (row.runs if row else 0),
                "runs": (row.runs if row else 0)}

    # One table, in the pool's own order - the same order the switcher, the
    # home page and the leaderboard all use. It used to be most-recent-PB
    # first with the never-finished tracks in a block underneath, which meant
    # the same track moved every time you drove and no two pages agreed on
    # where to look for it.
    pool = [t["slug"] for t in tracks_mod.TRACKS]
    rows = [_row(s) for s in pool if s in by_track or starts.get(s)]
    # A time or a start on a track that has since left the pool is still
    # yours, so it goes on the end rather than quietly disappearing.
    rows += [_row(s) for s in dict.fromkeys(list(by_track) + sorted(starts))
             if s not in set(pool)]
    # A lap being re-driven is not on the board and is not lost either, and the
    # person who drove it is the one person who should be told which. Only ever
    # your own: an unchecked lap of somebody else's is not news, it is a claim.
    waiting = []
    if is_me:
        waiting = (DriveRunCheck.query
                   .filter(DriveRunCheck.user_id == user.id,
                           DriveRunCheck.applied_at.is_(None),
                           DriveRunCheck.status.in_(("pending", "error")))
                   .order_by(DriveRunCheck.id.asc()).all())
    # Totalled per track rather than kept in a counter of its own: a track can have
    # starts and no time (never finished) or a time and no starts (driven before
    # the counter existed), and the per-track clamp already knows what to do with
    # both, so summing it cannot disagree with the column underneath.
    return render_template("account.html", user=user, is_me=is_me,
                           stats=_stats(user, create=is_me),
                           times=times, starts=starts, rows=rows, waiting=waiting,
                           total_starts=sum(starts.values()),
                           by_slug=tracks_mod.BY_SLUG,
                           tracks=tracks_mod.summaries(), name=get_effective_name())


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/tracks")
def api_tracks():
    return jsonify({"tracks": tracks_mod.summaries()})


def _track_payload(slug):
    """The track as the game receives it, with the record on it.

    The record belongs with the medal times rather than in a request of its
    own: it is the fourth time on the same list, and the only one of the four
    that is somebody's rather than the track's. Sent as a copy - the track
    dicts in `tracks_mod` are module-level and shared by every request.
    """
    track = tracks_mod.get(slug)
    if not track:
        return None
    # Same reason `_records` does it: this is the record the car on the road is
    # chasing, so a lap that has just been cleared belongs on it.
    _settle_checks()
    best = (DriveTime.query.filter_by(track=slug)
            .order_by(DriveTime.time_ms.asc()).first())
    out = dict(track)
    # The time and not the holder: whose lap it is belongs on the leaderboard,
    # not on a card read at 200km/h with three other times on it.
    out["record_ms"] = best.time_ms if best else None
    return out


@app.route("/api/track/<slug>")
def api_track(slug):
    track = _track_payload(slug)
    if not track:
        return jsonify({"error": "no such track"}), 404
    return jsonify(track)


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


@app.route("/api/last-track", methods=["POST"])
def api_last_track():
    """The switcher saying where you have moved to.

    Solo changes track without changing URL, so without this the session would
    still think you were on whatever /solo first handed you, and coming back
    would take you there instead of where you left off.
    """
    slug = (request.json or {}).get("track", "")
    if not tracks_mod.get(slug):
        return jsonify({"ok": False}), 404
    _remember_track(slug)
    return jsonify({"ok": True})


# What each `where` a page can send is called on a profile. **This table is the
# whole security model of the status line**: the browser sends a key, and a key
# that is not in here means no detail at all rather than something to display.
# A profile page is public, so anything that let a player put their own words
# on it would be a billboard with a text box attached.
PRESENCE_WHERE = {
    "room": "Multiplayer",
    "lobby": "In Lobby",
    "garage": "In the Garage",
    "replay": "Watching a replay",
    "board": "Reading the leaderboard",
}


@app.route("/api/presence", methods=["POST"])
def api_presence():
    """The heartbeat: "still here, and this is where".

    Sent on load and then once a minute while the tab is visible, which is what
    keeps a two-minute solo lap - a stretch with no other requests in it at all
    - from reading as somebody who has gone.

    Guests get a 200 and no row: presence hangs off an account, and there is
    nowhere to hang a guest's.
    """
    user = get_current_user()
    if not user:
        return jsonify({"ok": True})
    data = request.json or {}
    where = str(data.get("where", ""))[:20]
    detail = PRESENCE_WHERE.get(where)
    if where == "solo":
        # The one detail that is not a constant, and it still is not the
        # browser's text: the slug is looked up, and an unknown one is dropped.
        track = tracks_mod.get(str(data.get("track", ""))[:40])
        detail = track["name"] if track else None
    visits.seen(db, user.id, "drive", detail)
    return jsonify({"ok": True})


@app.route("/api/start", methods=["POST"])
def api_start():
    """A run has begun: count the attempt.

    The clock starting is what an attempt *is* - not opening the page and not
    rolling around behind the line - so this is posted from the same place the
    clock starts, which is also why a race counts: the green light is a start
    like any other. Guests have no row to count it in and get an honest ``false``
    rather than a 401; the clamp in ``_starts_for`` puts their history straight
    when they log in and the laps their browser kept are replayed.
    """
    slug = (request.json or {}).get("track", "")
    if not tracks_mod.get(slug):
        return jsonify({"ok": False, "error": "no such track"}), 404
    user = get_current_user()
    if not user:
        return jsonify({"ok": True, "stored": False})
    row = DriveStart.query.filter_by(user_id=user.id, track=slug).first()
    if row is None:
        row = DriveStart(user_id=user.id, track=slug, starts=0)
        db.session.add(row)
    row.starts = (row.starts or 0) + 1
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "stored": True, "starts": row.starts})


@app.route("/api/ping")
def api_ping():
    """The cheapest possible round trip, for the ping readout.

    Solo opens no socket at all - `game.js` only calls `connect()` in a room - so
    there is nothing in a time trial whose latency could be measured. This is the
    one thing both modes can measure the same way, and measuring it the same way in
    both is worth more than measuring the exact transport: what the number is for is
    "is my connection to this server healthy", and a figure that meant something
    different in solo than in a room would be worse than one meaning slightly less
    than a socket round trip in both.

    Deliberately does no work and touches nothing - no session lookup, no query, no
    presence write. It is polled every couple of seconds by every tab with the
    counter switched on, so anything it did would be that thing done forever. It is
    `visits.py`'s heartbeat that is excluded from the visit log for the same reason,
    and this path is skipped there too.
    """
    return jsonify({"ok": True})


@app.route("/api/activity", methods=["POST"])
def api_activity():
    """Driving that will never produce a board entry: an abandoned run, or a room lap.

    **This is where most of the driving was going.** `drive_time` and `distance` were
    only ever written by `/api/run`, which the client posts when a lap *finishes* -
    so measured on the live database, 8,134 of 9,758 attempts (83%) contributed zero
    minutes and zero kilometres, and every race, qualifying lap and room practice lap
    contributed nothing at all, because `/api/run` and `/api/start` both return early
    on `countsForTheBoard()`.

    It adds to those two counters and **touches nothing else** - not `runs`, which
    means laps finished, not `drive_times`, not a medal, not a rating. That is the
    whole reason this is a separate route rather than a flag on `/api/run`: the
    leaderboard rule is untouched, and no room lap time reaches the board through
    here. These are play stats, and "how long have you been driving" and "which laps
    count as records" are two different questions.

    Both numbers are clamped, because both are the client's word. Guests get an
    honest ``false`` rather than a 401, the rule `/api/start` already follows - there
    is no row to count it in and nothing has gone wrong.
    """
    # `navigator.sendBeacon` is the only thing that survives the tab going away, and
    # it sends `text/plain` unless you go out of your way - so `request.json` is None
    # and the beacon would be silently dropped, which is most of what this route is
    # for. `force=True` reads the body whatever the header says; `silent=True` makes
    # a malformed one an empty dict rather than a 400 nobody will ever see.
    data = request.get_json(force=True, silent=True) or {}
    track = tracks_mod.get(data.get("track", ""))
    if not track:
        return jsonify({"ok": False, "error": "no such track"}), 404
    user = get_current_user()
    if not user:
        return jsonify({"ok": True, "stored": False})
    ms = runcheck.clamp_run_ms(data.get("ms"))
    metres = runcheck.clamp_distance(track, data.get("distance"))
    st = _stats(user)
    st.drive_time = (st.drive_time or 0.0) + ms / 1000.0
    st.distance = (st.distance or 0.0) + metres
    db.session.commit()
    return jsonify({"ok": True, "stored": True})


def _floor_starts(user_id, slug, finishes):
    """Lift a track's start count to at least its finish count, and write it.

    A finish implies a start, but not that one was *recorded*: a guest posts no
    starts at all and their kept laps arrive at ``/api/run`` when they log in,
    and every lap driven before this counter existed has none behind it either.
    Clamping only on the way out to the screen would read correctly and still be
    wrong underneath - the next real start would land on a stored 0 and vanish
    under the backlog of finishes, and go on vanishing until it caught up. So
    the floor is put into the row, once, where the next start can count from it.

    Caller commits.
    """
    row = DriveStart.query.filter_by(user_id=user_id, track=slug).first()
    if row is None:
        row = DriveStart(user_id=user_id, track=slug, starts=0)
        db.session.add(row)
    if (row.starts or 0) < finishes:
        row.starts = finishes
        row.updated_at = datetime.utcnow()
    return row


def _starts_for(user_id, times):
    """Per-track start counts to put on a screen, keyed by slug.

    Never below the finish count beside it: you cannot finish a run you did not
    start, and "12 starts, 40 finishes" is not a smaller number than the truth
    but a wrong one. ``tools/backfill_starts.py`` and ``_floor_starts`` normally
    see to that in the data, so this is the same rule applied on the way out -
    for a database the backfill has not been run against, and for the window
    between a deploy and running it.

    ``times`` is the user's ``DriveTime`` rows, which the callers already hold.
    """
    rows = {r.track: (r.starts or 0)
            for r in DriveStart.query.filter_by(user_id=user_id).all()}
    for t in times:
        rows[t.track] = max(rows.get(t.track, 0), t.runs or 0)
    return rows


# ---------------------------------------------------------------------------
# Laps that are quick enough to be re-driven before they go up
# ---------------------------------------------------------------------------
#
# `runcheck.validate` asks whether a replay holds together. It cannot ask whether
# the car could have driven it, and a browser with a raised `ACCEL` produces a
# replay that passes every check in there - which is how a 12.288s Twin Loop took
# a track record. `verify.py` answers that by re-driving the lap through the real
# `Car.step`, and this is the machinery around it:
#
#   * a lap that would place in the top `VERIFY_TOP_N` is **held in
#     `drive_run_checks` instead of being stored**, so the board, the record, the
#     ghost and everybody's rank are untouched until it has been checked. Storing
#     it and reverting later is not available: `drive_times` keeps only the best
#     lap, so the row it overwrote is gone;
#   * the check runs in a **subprocess**, because one lap is one to four seconds
#     of solid CPU and Drive is a single eventlet worker - doing it here would
#     freeze every socket in every live race for that long;
#   * and the verdict is **settled by whoever reads the board next**, since the
#     child process only ever writes its own row.
#
# Two things this deliberately does not do. It does not hold laps at all when
# nothing can check them (`quickjs` missing, `DRIVE_VERIFY=0`): a lap that would
# wait for ever is worse than one that was never checked. And a *failed* check
# never touches the driver's stored time, because there is nothing of theirs to
# touch - the lap never got in.

_VERIFY_OK = None


def _can_verify():
    """Is there anything on this box that could re-drive a lap?

    `DRIVE_VERIFY` in the environment forces the answer either way, which is the
    switch to reach for if the verifier ever has to be turned off on the box
    without a deploy. Cached: it is a question about the installation.
    """
    global _VERIFY_OK
    forced = os.environ.get("DRIVE_VERIFY", "")
    if forced:
        return forced.lower() in ("1", "true", "yes")
    if _VERIFY_OK is None:
        try:
            import verify
            _VERIFY_OK = verify.available()
        except Exception:
            _VERIFY_OK = False
    return _VERIFY_OK


def _verify_payload(data):
    """The evidence off the wire: (inputs, anchors), or None if it is not usable.

    Shape-checked here and packed only if the lap is actually going to be held -
    `pack_verify` is a zlib compression of a few tens of kilobytes and this runs
    on the request path of every finished lap, the overwhelming majority of which
    are nowhere near the top of a board.
    """
    v = data.get("verify")
    if not isinstance(v, dict):
        return None
    inputs = runcheck.unpack_inputs(v.get("i"))
    anchors = v.get("a")
    if inputs is None or not isinstance(anchors, list) or not anchors:
        return None
    if len(anchors) > runcheck.MAX_ANCHORS:
        return None
    for a in anchors:
        if not isinstance(a, list) or len(a) != runcheck.ANCHOR_STRIDE:
            return None
        for x in a:
            if not isinstance(x, (int, float)) or isinstance(x, bool):
                return None
            if x != x or abs(x) > 1e9:            # NaN, infinities, nonsense
                return None
    return inputs, anchors


# Every check started and not yet reaped. Nothing waits on these - the point of
# a subprocess is that the request does not - but a child nobody collects stays
# in the process table as a zombie for as long as this worker lives, which is
# months. So they are polled on the way past, which is all `wait` would have
# done and none of the blocking.
_children = []

# How many checks may be in flight at once. Each child is up to ~110MB on the
# longest track and the box has about a gigabyte across five services, so an
# unbounded fan-out was the one way a busy evening could have the kernel pick
# something unrelated to kill - a live race in another room, or ERS. Two fits
# alongside everything else; three does not.
#
# **A refused spawn does not lose the lap.** The row is already committed to
# `drive_run_checks` and the client has already been told `pending`, so the lap
# is exactly where it would have been anyway - and `_settle_checks`'s sweep
# hands anything still pending past `_CHECK_GRACE` to a fresh child, which
# drains up to 50 rows in one runtime. The cost of being refused is that the lap
# goes up later, not that it is dropped.
MAX_VERIFIERS = int(os.environ.get("DRIVE_MAX_VERIFIERS", "2"))


def _spawn_verifier(*args):
    """Kick off a check in its own process, and do not wait for it.

    `start_new_session` so that a deploy restarting gunicorn does not take a
    half-finished check with it, and both pipes to devnull so nothing can block
    on a full buffer.

    Returns False without starting anything when `MAX_VERIFIERS` are already
    running. Every caller ignores the return, which is correct: see the note on
    `MAX_VERIFIERS` for why a refusal is safe.
    """
    # Reaped first, or a finished-but-uncollected child would count against the
    # cap for as long as this worker lives, which is months.
    _reap_verifiers()
    if len(_children) >= MAX_VERIFIERS:
        return False
    try:
        import subprocess
        p = subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "verify.py")] + list(args) + ["--quiet"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
        _children.append(p)
        return True
    except Exception:
        return False


def _reap_verifiers():
    """Collect whichever of them have finished. `poll` never blocks."""
    for p in list(_children):
        try:
            if p.poll() is not None:
                _children.remove(p)
        except Exception:
            _children.remove(p)


# How long a check may sit unanswered before it is assumed the process that was
# doing it is gone. Generous: a slow lap on a slow box is a few seconds, and
# re-running one that is merely still going costs a core for nothing.
_CHECK_GRACE = timedelta(minutes=10)

# And how often that is even asked. Two reasons, and the second is the important
# one: it keeps a query off nearly every page load, and it means a row that
# cannot be judged at all - a broken runtime, a blob nothing can read - costs one
# process every five minutes rather than one per page view. Module state in a
# single eventlet worker, so it is simply a variable.
_SWEEP_EVERY = timedelta(minutes=5)
_last_sweep = None


def _apply_check(c):
    """Act on a verdict, once. A pass becomes the driver's time; a fail is filed.

    The improvement is re-tested against the row *now* rather than against what
    it was when the lap was driven: two quick laps can be in the queue at once,
    and the slower of them arriving second must not overwrite the quicker.
    """
    c.applied_at = datetime.utcnow()
    if c.status != "pass":
        return
    track = tracks_mod.get(c.track)
    if not track:
        return
    st = DriveStats.query.filter_by(user_id=c.user_id).first()
    if st is None:
        st = DriveStats(user_id=c.user_id)
        db.session.add(st)
    row = DriveTime.query.filter_by(user_id=c.user_id, track=c.track).first()
    medal = runcheck.medal_for(track, c.time_ms)
    if row is None:
        row = DriveTime(user_id=c.user_id, track=c.track, time_ms=c.time_ms,
                        medal=medal, splits_json=c.splits_json, ghost=c.ghost,
                        runs=1)
        db.session.add(row)
        db.session.flush()
        _count_medal(st, medal)
    elif c.time_ms < row.time_ms:
        _uncount_medal(st, row.medal)
        row.time_ms = c.time_ms
        row.medal = medal
        row.splits_json = c.splits_json
        row.ghost = c.ghost
        row.updated_at = datetime.utcnow()
        _count_medal(st, medal)
    c.drive_time_id = row.id


def _settle_checks(user_id=None):
    """Apply any verdicts that have come back, and restart any that got lost.

    Called from the places that read the board rather than on a timer, because
    there is no timer: the process that judges a lap is a child that writes one
    row and exits. Normally both queries return nothing.
    """
    global _last_sweep
    try:
        _reap_verifiers()
        q = DriveRunCheck.query.filter(DriveRunCheck.applied_at.is_(None),
                                       DriveRunCheck.status.in_(("pass", "fail")))
        if user_id is not None:
            q = q.filter(DriveRunCheck.user_id == user_id)
        rows = q.order_by(DriveRunCheck.id.asc()).limit(20).all()
        for c in rows:
            _apply_check(c)
        if rows:
            db.session.commit()

        now = datetime.utcnow()
        if _last_sweep is not None and now - _last_sweep < _SWEEP_EVERY:
            return
        _last_sweep = now
        stale = (DriveRunCheck.query
                 .filter(DriveRunCheck.status.in_(("pending", "error")),
                         DriveRunCheck.queued_at < now - _CHECK_GRACE)
                 .first())
        if stale is not None and _can_verify():
            _spawn_verifier("--pending", "--again")
    except Exception:
        # Nothing here is worth failing a page load over: an unsettled verdict
        # is a lap that goes up a little later.
        db.session.rollback()


@app.route("/api/run", methods=["POST"])
def api_run():
    """A finished timed run: store it if it is a PB, and always count the try.

    Guests are welcome to drive but have no row to store a time in, so they get
    an honest answer back instead of a 401 - and their browser keeps the whole
    run (see static/js/pending.js), which is submitted here for real the moment
    they log in. A good lap should not be the price of not having an account.
    """
    data = request.json or {}
    track = tracks_mod.get(data.get("track", ""))
    if not track:
        return jsonify({"ok": False, "error": "no such track"}), 404
    time_ms = data.get("time_ms")
    splits = data.get("splits") or []
    ghost_frames = data.get("ghost")
    ok, why = runcheck.validate(track, time_ms, splits, ghost_frames)
    if not ok:
        return jsonify({"ok": False, "error": why}), 400

    medal = runcheck.medal_for(track, time_ms)
    user = get_current_user()
    best = (DriveTime.query.filter_by(track=track["slug"])
            .order_by(DriveTime.time_ms.asc()).first())

    def _run_rank(exclude_user_id=None):
        """Where this single run would sit on the board.

        Not the same as the rank of your PB row: a run slower than your own best
        still placed somewhere, and your existing entry must not be counted as
        somebody ahead of you.
        """
        q = DriveTime.query.filter(DriveTime.track == track["slug"],
                                   DriveTime.time_ms < time_ms)
        if exclude_user_id is not None:
            q = q.filter(DriveTime.user_id != exclude_user_id)
        return q.count() + 1

    def _rank_of(r):
        """Where a stored row sits on the board."""
        return DriveTime.query.filter(DriveTime.track == track["slug"],
                                      DriveTime.time_ms < r.time_ms).count() + 1

    if not user:
        return jsonify({"ok": True, "stored": False, "medal": medal,
                        "guest": True, "rank": None, "run_rank": _run_rank(),
                        "record_ms": best.time_ms if best else None,
                        "note": "Kept on this device - log in and it goes on the board."})

    # Anything of this player's that has been judged since they were last here,
    # so that "is this a PB" is asked of an up-to-date row.
    _settle_checks(user.id)

    st = _stats(user)
    st.runs = (st.runs or 0) + 1
    st.drive_time = (st.drive_time or 0.0) + time_ms / 1000.0
    st.distance = (st.distance or 0.0) + runcheck.clamp_distance(track, data.get("distance"))

    run_rank = _run_rank(exclude_user_id=user.id)
    row = DriveTime.query.filter_by(user_id=user.id, track=track["slug"]).first()

    # --- a lap near the top of the board is re-driven before it goes up ------
    if (run_rank <= runcheck.VERIFY_TOP_N and (row is None or time_ms < row.time_ms)
            and _can_verify()):
        ev = _verify_payload(data)
        if ev is None:
            # There is no way to check this lap and it is quick enough to need
            # checking. The honest cause is a page that was open across the
            # deploy that added the recording, and a reload fixes it; the other
            # cause is somebody who left the evidence out on purpose, and the
            # two get the same answer. `pending.js` drops a 4xx, which is right:
            # a lap kept from before this existed can never grow an input stream.
            db.session.commit()          # the attempt still counted
            return jsonify({"ok": False, "error": "This lap is quick enough to be "
                            "checked, and your game did not send what it is checked "
                            "from. Reload the page and it will."}), 400
        inputs, anchors = ev
        if row is not None:
            row.runs = (row.runs or 0) + 1
            _floor_starts(user.id, track["slug"], row.runs or 0)
        check = DriveRunCheck(
            user_id=user.id, track=track["slug"], time_ms=time_ms,
            splits_json=json_mod.dumps(splits),
            ghost=runcheck.pack_ghost(ghost_frames),
            evidence=runcheck.pack_verify(inputs, anchors))
        db.session.add(check)
        db.session.commit()
        _spawn_verifier("--check", str(check.id))
        return jsonify({"ok": True, "stored": True, "improved": False,
                        "pending": True,
                        "medal": row.medal_shown if row else None,
                        "pb_ms": row.time_ms if row else None,
                        "rank": _rank_of(row) if row else None,
                        "run_rank": run_rank,
                        # The lap that is *on the board* for them, which while a
                        # quicker one is being checked is still the older one -
                        # so a share link made here plays a real lap rather than
                        # one no read path can see yet. None on a first-ever lap
                        # of a track, which is held with no row behind it.
                        "time_id": row.id if row else None,
                        "record_ms": best.time_ms if best else None,
                        "is_record": False,
                        "note": "Being checked - a lap this quick is re-driven on "
                                "the server before it goes on the board."})

    improved = False
    if row is None:
        row = DriveTime(user_id=user.id, track=track["slug"], time_ms=time_ms,
                        medal=medal, splits_json=json_mod.dumps(splits),
                        ghost=runcheck.pack_ghost(ghost_frames), runs=1)
        db.session.add(row)
        improved = True
    else:
        row.runs = (row.runs or 0) + 1
        if time_ms < row.time_ms:
            # A better run replaces the row wholesale, ghost and all.
            _uncount_medal(st, row.medal)
            row.time_ms = time_ms
            row.medal = medal
            row.splits_json = json_mod.dumps(splits)
            row.ghost = runcheck.pack_ghost(ghost_frames)
            row.updated_at = datetime.utcnow()
            improved = True
    if improved:
        _count_medal(st, medal)
    _floor_starts(user.id, track["slug"], row.runs or 0)
    db.session.commit()

    # Re-read the record: this run may have just become it.
    best = DriveTime.query.filter_by(track=track["slug"]).order_by(DriveTime.time_ms.asc()).first()
    rank = DriveTime.query.filter(DriveTime.track == track["slug"],
                                  DriveTime.time_ms < row.time_ms).count() + 1
    return jsonify({"ok": True, "stored": True, "improved": improved,
                    "medal": row.medal_shown, "pb_ms": row.time_ms,
                    "rank": rank, "run_rank": run_rank,
                    "record_ms": best.time_ms if best else None,
                    # What the Share button on the finish sheet links to:
                    # `/solo/<slug>?watch=<id>`. It is the *row's* id and not
                    # this run's, because a run is not a thing that exists -
                    # `drive_times` keeps one row per player per track and a
                    # better lap overwrites it wholesale, so the only shareable
                    # solo lap anybody has on a track is their best one.
                    "time_id": row.id,
                    "is_record": bool(best and best.id == row.id)})


# "author" is retired and never awarded again (see tuning.MEDAL_MULT), but it is
# still in here so that improving on a row that earned one back when it existed
# decrements the right counter instead of leaving a phantom medal behind.
_MEDAL_FIELD = {"author": "authors", "gold": "golds",
                "silver": "silvers", "bronze": "bronzes"}


def _count_medal(st, medal):
    f = _MEDAL_FIELD.get(medal)
    if f:
        setattr(st, f, (getattr(st, f) or 0) + 1)


def _uncount_medal(st, medal):
    f = _MEDAL_FIELD.get(medal)
    if f:
        setattr(st, f, max(0, (getattr(st, f) or 0) - 1))


@app.route("/api/ghost/<slug>")
def api_ghost(slug):
    """Fetch a ghost to race.

    ``who=me`` is your PB, ``who=wr`` the record, and ``who=<id>`` any single row
    on the board - which is what makes "race this person's lap" possible from the
    leaderboard without leaving the track you are on.
    """
    track = tracks_mod.get(slug)
    if not track:
        return jsonify({"error": "no such track"}), 404
    who = request.args.get("who", "me")
    row = None
    if who == "wr":
        # The fastest lap **that can actually be shown**. Picking the fastest
        # row and then finding it has no replay is how "world record" came to
        # report that nobody had set a time here at all, on tracks with a full
        # board - a row keeps its time whether or not a ghost was stored with
        # it, and the oldest rows have none. Every other way in already only
        # offers laps with a replay: the board sends `has_ghost` and hands back
        # an id, which is why "view others" worked on the very tracks where
        # this did not.
        row = (DriveTime.query.filter_by(track=slug)
               .filter(DriveTime.ghost.isnot(None))
               .order_by(DriveTime.time_ms.asc()).first())
    elif who.isdigit():
        # Scoped to this track so an id from elsewhere cannot fetch a ghost that
        # would be replayed against geometry it was never driven on.
        row = DriveTime.query.filter_by(id=int(who), track=slug).first()
    else:
        user = get_current_user()
        if user:
            row = DriveTime.query.filter_by(user_id=user.id, track=slug).first()
    if not row or not row.ghost:
        return jsonify({"ok": True, "ghost": None})
    # A ghost is somebody's lap, so it is driven in their car - and in the car
    # they drive *now*, not the one they drove then: a livery is not recorded
    # with a lap, and a ghost of yours turning up in last month's paint would be
    # somebody else as far as anybody watching is concerned.
    livery = _livery_for(row.user) if row.user else None
    return jsonify({"ok": True, "hz": runcheck.ghost_hz(row.ghost),
                    "id": row.id, "time_ms": row.time_ms, "splits": row.splits,
                    "who": (row.user.display if row.user else "?"),
                    # The old field, answered off the livery so the two cannot
                    # disagree: it is what a client from before the garage reads,
                    # and what the watch bar's name is coloured with. A grey one
                    # is a lap nobody set.
                    "color": (livery or {}).get("body")
                             or color_for(row.user.username if row.user else None),
                    "livery": livery,
                    "ghost": runcheck.unpack_ghost(row.ghost)})


@app.route("/api/board/<slug>")
def api_board(slug):
    """The board for one track, with enough on each row to open it.

    Each row carries its own id and splits so the in-game leaderboard can show a
    lap's checkpoint times and then race or watch it, without a second request
    per row.
    """
    if not tracks_mod.get(slug):
        return jsonify({"error": "no such track"}), 404
    rows = (DriveTime.query.filter_by(track=slug)
            .order_by(DriveTime.time_ms.asc()).limit(50).all())
    user = get_current_user()
    return jsonify({"rows": [{"id": r.id, "name": r.user.display if r.user else "?",
                              "time_ms": r.time_ms, "medal": r.medal_shown,
                              "splits": r.splits, "has_ghost": bool(r.ghost),
                              "me": bool(user and r.user_id == user.id)}
                             for r in rows]})


# ---------------------------------------------------------------------------
# Lobby plumbing
# ---------------------------------------------------------------------------

def _my_players(sk):
    return (DrivePlayer.query.join(DriveGame, DrivePlayer.game_id == DriveGame.id)
            .filter(DrivePlayer.session_key == sk, DriveGame.status != "ended").all())


def _leave_other_rooms(sk, keep_code=None):
    for p in list(_my_players(sk)):
        g = p.game
        if g.code != keep_code:
            was_host = p.is_host
            db.session.delete(p)
            db.session.commit()
            remaining = sorted(g.players, key=lambda q: q.seat_order)
            # **The host leaving closes the room**, and creating or joining
            # another room is leaving this one. Same rule as `_drop`, which is
            # the same decision reached through the Leave button, and the
            # reasoning for it is written down there.
            if was_host:
                _close_room(g, "The host left, so the room closed.")
            # Bots do not keep a room alive; see `_drop`.
            elif not any(not q.is_bot for q in remaining):
                _close_room(g, "Everyone left.")
            else:
                _broadcast_roster(g)


def _seated_room(sk=None):
    """The room this browser still holds a seat in, if any.

    Opening a replay leaves the room's *page*, and the socket disconnect that
    goes with it is the soft kind - the car comes off the road, the seat stays
    in the database - so somebody away watching a replay is, as far as the room
    is concerned, still in it. Which is what lets the way out of a replay be
    "back to the room" rather than "out to the lobby list": there is a room to
    go back to, and going back to it is a page load. `on_join_room` clears the
    `gone` mark on the way in, so the car returns to the road with it.

    At most one seat, by construction rather than by luck: `_leave_other_rooms`
    runs on every join. `_my_players` skips ended games, so this can never point
    at a room that is only still there because nobody has swept it up yet.
    """
    seats = _my_players(sk or get_session_key())
    return seats[0].game.code if seats else None


def _roster(game):
    """Every seat with its livery and its session points, working the two
    whole-field queries out once.

    The one place a roster is built, so the gate check cannot be applied on
    three paths and forgotten on the fourth. Both `records_held` and
    `time_trial_leaders` are the same answer for everybody in the room, so they
    are asked once here rather than eight times inside `_livery_for`.

    **It takes the game rather than its players so it can find the points
    itself** (`_score_race` keeps them on the live room, which is keyed by
    code). Handed in as an argument they would be a thing four call sites have
    to remember, and the one that forgot would render a room where everybody's
    tally silently read zero - which is the failure the paragraph above is
    about. A room with no live state has no session to report, so the answer
    there is zero for everybody and the sidebar shows no column at all.
    """
    holders = garage_mod.records_held()
    leaders = garage_mod.time_trial_leaders()
    points = (_rooms.get(game.code) or {}).get("points", {})
    out = []
    for pl in game.players:
        seat = pl.to_dict(_livery_for(pl.linked_user, holders, pl.name, leaders))
        seat["points"] = points.get(pl.pid, 0)
        out.append(seat)
    return out


def _add_player(game, host=False):
    sk = get_session_key()
    existing = DrivePlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if existing:
        return existing
    user = get_current_user()
    name = get_effective_name()
    # **You always drive the car you chose.**
    #
    # A seat used to take your colour only if it was free and fall back to
    # first-free otherwise, on the grounds that two identical cars on a grid is
    # worse than being the wrong red for one race. That was the right trade while
    # nobody had picked anything - a hashed colour is not yours in any sense
    # worth protecting. It is the wrong trade now: being silently handed a
    # stranger's colour is far worse than sharing one, and the cars have names
    # over them precisely so that colour is not the only way to tell them apart.
    # So the rule is gone and nobody is overridden.
    #
    # Guests are hashed off the name they typed rather than all being handed
    # `GUEST_COLOR`, which is what the fallback used to spread out for them.
    # Two guests can still collide; so can two accounts, and the answer is the
    # same one.
    color = color_for(user.username if user else name)
    seat = max((p.seat_order for p in game.players), default=-1) + 1
    p = DrivePlayer(game_id=game.id, user_id=(user.id if user else None),
                    session_key=sk, name=name,
                    color=color, seat_order=seat, is_host=host)
    db.session.add(p)
    db.session.commit()
    return p


@app.route("/create", methods=["POST"])
@require_name
def create():
    data = request.json or {}
    slug = data.get("track") or tracks_mod.TRACKS[0]["slug"]
    if not tracks_mod.get(slug):
        slug = tracks_mod.TRACKS[0]["slug"]
    sk = get_session_key()
    _leave_other_rooms(sk)
    game = DriveGame(code=_make_code(), status="waiting", track=slug,
                     max_players=MAX_ROOM, is_private=bool(data.get("is_private")),
                     passcode=((data.get("passcode", "") or "").strip()[:20] or None),
                     last_activity_at=datetime.utcnow())
    db.session.add(game)
    db.session.commit()
    _add_player(game, host=True)
    _broadcast_lobbies()
    return jsonify({"ok": True, "code": game.code})


@app.route("/join", methods=["POST"])
@require_name
def join():
    data = request.json or {}
    code = (data.get("code", "") or "").strip().upper()
    passcode = (data.get("passcode", "") or "").strip()
    sk = get_session_key()
    game = DriveGame.query.filter_by(code=code).first()
    if not game:
        return jsonify({"ok": False, "error": "No room with that code."}), 404
    already = DrivePlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if not already:
        if len(game.players) >= game.max_players:
            # **A person takes a bot's seat.** A room that has filled its grid
            # with bots is not full in any sense that should keep somebody out -
            # the bots are there because there was nobody else - so the slowest
            # one stands down. Slowest rather than newest, because the field is
            # there to race and the easy one is the least of it.
            order = {lv: i for i, lv in enumerate(bots_mod.LEVELS)}
            spare = sorted((p for p in game.players if p.is_bot),
                           key=lambda p: order.get(p.bot_level, 0))
            if not spare:
                return jsonify({"ok": False, "error": "That room is full."}), 409
            db.session.delete(spare[0])
            db.session.commit()
            r = _rooms.get(code)
            if r:
                r["cars"].pop(spare[0].pid, None)
                _sync_bots(r, game)
        if game.is_private and game.passcode and passcode != game.passcode:
            return jsonify({"ok": False, "error": "Wrong passcode."}), 403
        _leave_other_rooms(sk)
        _add_player(game)
        _broadcast_lobbies()
    return jsonify({"ok": True, "code": game.code})


def _lobbies_payload():
    open_games = (DriveGame.query.filter_by(status="waiting", is_private=False)
                  .order_by(DriveGame.created_at.desc()).limit(30).all())
    out = []
    for g in open_games:
        if len(g.players) >= g.max_players:
            continue
        d = g.to_lobby_dict()
        t = tracks_mod.get(g.track)
        d["track_name"] = t["name"] if t else g.track
        r = _rooms.get(g.code)
        d["phase"] = r["phase"] if r else "free"
        out.append(d)
    return {"games": out}


def _broadcast_lobbies():
    socketio.emit("lobbies_update", _lobbies_payload(), room="lobbies")


def _broadcast_roster(game):
    socketio.emit("roster", {"players": _roster(game),
                             "track": game.track},
                  room="room:" + game.code)
    _broadcast_lobbies()


def _delete_game(game):
    for p in list(game.players):
        db.session.delete(p)
    _rooms.pop(game.code, None)
    _locks.pop(game.code, None)
    # The bot world outlives the room state unless it is told, and it is the
    # expensive thing here: a QuickJS world holding a built track is tens of
    # megabytes on a box with about a gigabyte across five services.
    botsim.drop(game.code)
    db.session.delete(game)
    db.session.commit()


def _close_room(game, reason):
    """End a room and tell whoever is in it why.

    One helper because a room ends for three different reasons now - the host
    leaving, the last person leaving, and the sweep - and everybody still on the
    page needs the same three things to happen in every case: told, deleted,
    and the lobby list brought up to date. The reason is carried through to the
    lobbies page rather than dropped, because a room vanishing under you looks
    exactly like a bug if nothing says what happened.

    The sweep does its own version of this, deliberately: it can close several
    rooms in one pass and batches the single `_broadcast_lobbies` at the end.
    """
    socketio.emit("room_closed", {"reason": reason}, room="room:" + game.code)
    _delete_game(game)
    _broadcast_lobbies()


# ---------------------------------------------------------------------------
# Live rooms
# ---------------------------------------------------------------------------
# A room is always "on": everyone in it is driving the current track whenever
# they like, and a race is a *phase* of the room rather than a separate place.
# Poses are kept in memory and fanned out as one merged snapshot per tick, so
# traffic is TICK_HZ messages/sec/viewer instead of that per car per viewer.
# None of this is ever written to the database.

TICK_HZ = 30
POSE_STALE_MS = 6000
# The most of a one-way trip anybody is credited with, in ms. A client measures
# its own round trip and reports it (`on_clock`); this is the ceiling on half of
# it, because the number arrives from the thing it flatters. 80ms one way covers
# a transatlantic connection with room to spare, and at MAX_SPEED it is worth
# about four units of road - so the worst a liar buys is being drawn a car
# length up on other people's screens, which is less than the error every honest
# car carried before any of this was compensated. It reaches nothing else: not
# racecheck, not `prog`, not the standings (see `_snapshot` on why it is its own
# field and not folded into the pose age), not the result.
UPSTREAM_CAP_MS = 80.0
QUAL_MS = 90000
COUNTDOWN_MS = 5000
FINISH_GRACE_MS = 45000
# How long the results sheet stays up before the room drops back to practice.
# Named rather than buried in `_close_race` for the usual reason - it is one of the
# numbers most likely to want moving - and because Rematch firing inside it is a
# real case that `_clear_results`'s `seq` guard exists for.
RESULTS_HOLD_S = 12
# The replay: every car, sampled on the same clock as a ghost and packed the
# same way, from the green light to the flag. Capped at six minutes, which is
# beyond any honest race on any track in the pool and stops a room left running
# from eating memory.
REPLAY_HZ = runcheck.GHOST_HZ
REPLAY_MAX_FRAMES = REPLAY_HZ * 60 * 6
# Replays are kept for their own sake - a link to one has to keep working - so
# they outlive the room. They cannot be kept for ever either, at a couple of
# hundred kilobytes each.
REPLAY_KEEP = 300
# A race must end. The grace clock below only starts when somebody *finishes*,
# so on its own it cannot save a race nobody finishes - which is the ordinary
# outcome of everyone crashing out or wandering off, and used to park the room
# in `racing` for ever with the host unable to restart it or change track.
HARD_RACE_MIN_MS = 150000
HARD_RACE_MAX_MS = 900000

# The phases a room moves through:
#
#   free -> qual_countdown -> qualifying -> countdown -> racing -> results
#
# with `qual_countdown` and `qualifying` skipped entirely when the host has
# turned qualifying off. Everything that can strand a room is a transition out
# of one of the middle four, so they all go through the same `_close_*` helpers
# and every one of them is guarded by a race sequence number - see `_race_seq`.
LIVE_PHASES = ("qual_countdown", "qualifying", "countdown", "racing")

# What the host can change about the next race, and what it is if they change
# nothing. Deliberately in the live room state rather than on `DriveGame`: a
# room's settings are about the next few minutes, `create_all` makes tables and
# not columns (so a new one would need a hand migration on the live database),
# and a room that has been empty long enough for its state to be dropped is not
# a room anybody is still setting up.
#
# Qualifying is **off** by default: it is ninety seconds plus five of lights
# before anybody races, which is most of a race spent not racing, and a room of
# people who have just found each other wants to be on the grid. The host turns
# it on from the room drawer when the grid is worth two minutes.
ROOM_DEFAULTS = {"qualifying": False}

_rooms = {}       # code -> live room state
_sid_room = {}    # socket id -> (code, pid)


def _room(code):
    r = _rooms.get(code)
    if not r:
        r = _rooms[code] = {"code": code, "phase": "free", "cars": {}, "t0": None,
                            "deadline": None, "finish": [], "chat": [],
                            "loop": None, "seq": 0,
                            # qualifying -> grid
                            "qual": {}, "qual_end": None, "grid": {}, "splits": {},
                            # The replay of whoever is provisionally on pole,
                            # which is a ghost anybody in the room can chase.
                            "pole": None,
                            # Last race's finishing order, which is the grid for
                            # the next one when there is no qualifying - see
                            # `_reverse_grid`. Survives a reset; it is history,
                            # not race state.
                            "last_order": [],
                            # The room's championship: pid -> points, added up
                            # over every race run here. Survives a reset and a
                            # track change for the same reason `last_order`
                            # does, and goes when the room does - see
                            # `_score_race`.
                            "points": {},
                            # Every car's poses through the race being driven,
                            # written out as a DriveRace when it ends.
                            "rec": None,
                            "races_run": 0,
                            # Bumped by every race so a timer armed for one race
                            # can never close the next one.
                            "race_seq": 0, "hard_end": None,
                            "settings": dict(ROOM_DEFAULTS)}
    return r


def _hot_track(r):
    """The room's track, for the 30Hz path. Memoised on the room.

    `_room_track` is a database query and says in as many words that it is for
    paths that run once per car per race. `on_pose` is thirty times a second per
    car and cannot have one - but it needs the track, because projecting a car
    back onto the ribbon is the whole of what makes `prog` the server's number
    rather than the client's.

    So the answer is kept on the room and dropped by the one handler that can
    change it. That is the second source of truth `_room_track` deliberately
    avoided, and the difference that makes it safe is that this one is *derived*
    and has a single writer: a miss re-queries, so the worst a stale entry can
    do is be thrown away and fetched again. The miss is cached too (as `False`),
    or a room whose game row has been swept would run a query per pose.
    """
    trk = r.get("trk")
    if trk is None:
        trk = r["trk"] = _room_track(r["code"]) or False
    return trk or None


def _watch(r, pid):
    """This car's rolling anti-cheat state. See `racecheck.Watcher`."""
    return r.setdefault("watch", {}).setdefault(pid, racecheck.Watcher())


def _car(r, pid):
    return r["cars"].setdefault(pid, {
        "p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0], "v": [0.0, 0.0, 0.0],
        "prog": 0.0, "cp": 0, "flags": 0, "sl": 0.0, "ts": 0, "name": "", "color": "#fff",
        "ms": None, "dnf": False, "gone": False, "up": 0.0,
    })


def _note_upstream(c, rtt):
    """Keep the shortest round trip this car has reported, halved and capped.

    Split out of `on_clock` so the rule can be read and tested without a socket
    under it, since the rule is the whole of the interesting part.

    A round trip is unusable if it can only ever grow: the pings arrive while
    the page is still loading, so the first of them is the worst measurement of
    the session and would set the number for the rest of it. The minimum is the
    sample with the least queueing in it, which is also the only direction a
    client cannot walk this in - and the cap is what bounds it even then. `None`
    on the first ping, when nothing has been measured yet.
    """
    try:
        rtt = float(rtt)
    except (TypeError, ValueError):
        return
    if rtt != rtt or rtt < 0:                   # NaN, or a trip that went back
        return
    one_way = min(rtt / 2.0, UPSTREAM_CAP_MS)
    c["up"] = one_way if c["up"] <= 0 else min(c["up"], one_way)


def _snapshot(r):
    """Everyone's latest pose, merged, with each one's own age.

    `t` is when the snapshot went out; a car's pose in it is whatever arrived
    last, which can be a whole pose-interval older. Field 13 is that gap,
    because the client extrapolates each car forward from when it reported and
    reading them all as fresh leaves every car short by a different amount every
    tick - jitter that looks like the network and is actually arithmetic.

    Field 14 is how full that car's tow is, 0..1, with `FLAG.SLIP` in the flags
    saying whether it is the charge or what is left of the boost. It is here so
    a rival's slipstream can be *drawn* and *heard* rather than only known
    about. Every trailing field is appended rather than inserted and the client
    guards on the array's length, so a page left open across a deploy degrades
    to no tow rather than to a car in the wrong place.

    **Field 15 is the other half of the trip, and it is deliberately not added
    into field 13.** A pose is stamped on arrival, so 13 is the wait since it
    landed and says nothing about the journey it made to get here - while the
    pose describes where the car was when it was *sent*. Leaving that out drew
    every car short by its own upstream leg on every screen but its own: about
    1.5 units at 60ms of ping, always backwards, and mirrored, so two drivers
    level with each other each had the other one trailing. `c["up"]` is that
    leg (`on_clock`), and it goes in a field of its own because the two numbers
    have **different owners and different consumers**. 13 is the server's own
    measurement; 15 is the client's, capped. Rendering wants both, and adds
    them. The running order (`orderFromSnapshot`) wants only the one the server
    owns - fold them together and overstating your ping quietly buys projected
    distance on the board, which is precisely the number the order exists to
    make trustworthy.
    """
    now = _now_ms()
    cars = {}
    for pid, c in r["cars"].items():
        if c["gone"] or now - c["ts"] > POSE_STALE_MS:
            continue
        cars[pid] = [round(c["p"][0], 2), round(c["p"][1], 2), round(c["p"][2], 2),
                     round(c["q"][0], 3), round(c["q"][1], 3), round(c["q"][2], 3), round(c["q"][3], 3),
                     round(c["v"][0], 2), round(c["v"][1], 2), round(c["v"][2], 2),
                     round(c["prog"], 1), c["cp"], c["flags"], max(0, now - c["ts"]),
                     round(c.get("sl", 0.0), 2), round(c["up"])]
    return {"t": now, "cars": cars}


def _race_state(r):
    return {"phase": r["phase"], "t0": r["t0"], "deadline": r["deadline"],
            "finish": r["finish"], "qual": _qual_state(r),
            "settings": dict(r["settings"]), "pole": _pole_meta(r),
            "order": [pid for pid, _ in sorted(r["cars"].items(),
                                               key=lambda kv: -kv[1]["prog"])]}


def _live(r):
    """Everyone actually here: a fresh pose, and not already out of the door.

    A car that has gone is kept in `cars` while a race is on (it is a DNF, not
    a disappearance) so it must be excluded from every "who is still driving"
    question by name rather than by going stale on its own.
    """
    now = _now_ms()
    return [pid for pid, c in r["cars"].items()
            if not c["gone"] and now - c["ts"] < POSE_STALE_MS]


def _pending(r):
    """Cars still out on the circuit - neither home nor retired.

    Scoped to the grid, because the grid is exactly who started. Somebody who
    walks into the room while a race is on is driving, but they are not in it,
    and counting them here would mean a race could never reach "all in".
    """
    live = set(_live(r))
    return [pid for pid in r["grid"]
            if pid in live and r["cars"][pid]["ms"] is None
            and not r["cars"][pid]["dnf"]]


# ---------------------------------------------------------------------------
# Bots in a room
# ---------------------------------------------------------------------------
# A bot is an ordinary seat (`DrivePlayer.is_bot`) whose car is stepped by the
# server instead of by a browser - see `botsim` for why the server and not the
# host's tab. Everything downstream of a pose treats it as any other car: the
# snapshot carries it, the standings order it, the replay records it, the
# slipstream tows off it, and it can be hit. Two things are deliberately *not*
# true of it: it never reaches ELO (no `user_id`, the same door a guest comes
# through) and it is never judged by the anti-cheat, which would flag the quick
# ones for taking exactly the shortcuts they were taught.

def _bot_pids(r):
    return r.get("bots") or {}


def _humans(r):
    """Everyone here who is a person: a fresh pose, not gone, not a bot.

    The room's own liveness is measured on this and never on `_live`, because a
    room with bots in it produces poses for ever - so an empty one would keep
    its pump, its bot world and any race it was in the middle of alive until
    somebody happened to come back.
    """
    bots = _bot_pids(r)
    return [pid for pid in _live(r) if pid not in bots]


def _bot_world(r, create=False):
    slug = r.get("bot_slug")
    if not slug or not botsim.available():
        return None
    return botsim.world(r["code"], slug, create=create)


def _bot_humans(r):
    """The people, in the shape `botsim` hands to the driver.

    A bot is given the same picture of the room everybody else has: where the
    real cars are, how fast they are going and how far round they have got. The
    poses are up to a tick old, which is exactly as stale as every car in this
    game is to every browser other than its own.
    """
    out = []
    bots = _bot_pids(r)
    now = _now_ms()
    for pid, c in r["cars"].items():
        if pid in bots or c["gone"] or now - c["ts"] > POSE_STALE_MS:
            continue
        out.append({"pid": pid, "x": c["p"][0], "y": c["p"][1], "z": c["p"][2],
                    "qx": c["q"][0], "qy": c["q"][1], "qz": c["q"][2],
                    "qw": c["q"][3],
                    "vx": c["v"][0], "vy": c["v"][1], "vz": c["v"][2],
                    "prog": c["prog"],
                    "done": c["ms"] is not None or c["dnf"]})
    return out


# How often a room holding bot seats with no bot world may try to rebuild one,
# and how many times a world may throw before the room gives up on it.
BOT_REVIVE_MS = 2000
BOT_FAIL_LIMIT = 3


def _revive_bots(r):
    """Rebuild a bot world that has gone missing under seats that still exist.

    **Seats and world can only be made to agree by a host action**, and that is
    the bug this exists for. `_tick_bots` used to return here, so a room that
    lost its world mid-session showed bots in the roster with no cars on the
    track, for the rest of the session, with nothing in the UI to say why.
    Reported from a real room after a track change, and not reproducible here
    against sixteen tracks, humans posing and every phase - so this does not
    claim to know the trigger. It makes the state recoverable instead of
    terminal, which is true whatever the trigger turns out to be.

    Throttled and outside the room lock's owner: the pump does not hold the
    lock, so this takes it, and a rebuild that is going to fail should cost one
    query every couple of seconds rather than one per tick.
    """
    now = _now_ms()
    if now - (r.get("bot_revive") or 0) < BOT_REVIVE_MS:
        return
    r["bot_revive"] = now
    with app.app_context():
        with _lock(r["code"]):
            game = DriveGame.query.filter_by(code=r["code"]).first()
            if game:
                _sync_bots(r, game)


def _tick_bots(r):
    """Step this room's bots and write their poses in as though they had sent them.

    Called from `_pump`, so it runs at `TICK_HZ` on the same greenlet that fans
    out the snapshot. The `dt` is measured rather than assumed: `eventlet.sleep`
    is a floor and not a promise, and a bot stepped by a nominal 33ms while 40
    really elapsed drifts behind the people it is racing.
    """
    if not r.get("bots"):
        return
    w = _bot_world(r)
    if w is None:
        _revive_bots(r)
        return
    now = _now_ms()
    last = r.get("bot_t")
    r["bot_t"] = now
    if last is None:
        return                       # first tick has no interval to step over
    dt = (now - last) / 1000.0
    # Clamped for the same reason `Stepper` has `MAX_STEPS`: a worker that was
    # busy for a second must not fast-forward the field a second up the road.
    if dt <= 0:
        return
    dt = min(dt, 0.25)
    # Seconds since the green light, which is the only thing a bot needs the
    # clock for: its reaction time off the line. `None` outside a race, so a bot
    # in practice simply drives.
    since = None
    if r["phase"] == "racing" and r.get("t0"):
        since = (now - r["t0"]) / 1000.0
    try:
        poses, events = w.tick(dt, _bot_humans(r), now, r["phase"], since)
    except Exception:
        # A bot world that has thrown is not worth taking the room down for.
        # Drop it: the seats stay, the cars stop appearing, and the race carries
        # on for the people in it.
        #
        # **The track is in the message because the symptom is track-shaped.**
        # Reported from a real room: bots worked on two tracks, the host moved to
        # a third and the cars never appeared, and removing and re-adding did not
        # help - which is what this branch looks like from the outside when the
        # tick throws every time on one particular slug. Without the slug and the
        # bot count here, the log said only that *a* room had failed.
        fails = r["bot_fail"] = (r.get("bot_fail") or 0) + 1
        app.logger.exception(
            "bot world failed in room %s on %s (%d bots, phase %s, failure %d);"
            " dropping it", r["code"], r.get("bot_slug"),
            len(r.get("bots") or {}), r["phase"], fails)
        botsim.drop(r["code"])
        # **The seats stay listed, so leaving `r["bots"]` set is what lets
        # `_revive_bots` build a new world on the next tick.** One bad tick -
        # a pose that arrived half-written, a world caught mid-rebuild - should
        # cost a blink, not the session. Only after it has failed
        # `BOT_FAIL_LIMIT` times in a row is it treated as this track simply not
        # working, and only then is the room told, once.
        if fails >= BOT_FAIL_LIMIT:
            r["bots"] = {}
            socketio.emit("room_error",
                          {"error": "The bots stopped working on this track. "
                                    "Re-add them, or try another track."},
                          room="room:" + r["code"])
        return
    r["bot_fail"] = 0
    for row in poses:
        c = _car(r, row[0])
        c["p"] = [row[1], row[2], row[3]]
        c["q"] = [row[4], row[5], row[6], row[7]]
        c["v"] = [row[8], row[9], row[10]]
        c["prog"] = row[11]
        c["cp"] = int(row[12])
        c["flags"] = int(row[13])
        c["sl"] = row[14]
        c["ts"] = now
    if events:
        _bot_events(r, events, now)


def _bot_events(r, events, now):
    """A bot reached a checkpoint or crossed the line. Do what the room does.

    The same three things `on_split`, `on_qual_time` and `on_finish` do for a
    person, minus every check in them: those exist to bound what a *client*
    claims, and there is no client here - the number came from the server's own
    simulation of the server's own car.
    """
    w = _bot_world(r)
    for pid, evs in events:
        for ev in evs:
            kind, a = ev[0], ev[1]
            ms = ev[2] if len(ev) > 2 else 0
            if kind == "cp":
                if r["phase"] == "racing" and pid in r["grid"]:
                    mine = r["splits"].setdefault(pid, {})
                    if a not in mine:
                        mine[a] = ms
                        socketio.emit("race_split", {"pid": pid, "cp": a, "ms": ms},
                                      room="room:" + r["code"])
            elif kind == "finish":
                _bot_finished(r, pid, a, w, now)


def _bot_finished(r, pid, ms, w, now):
    """A bot got to the end of its lap, in whichever session it was driving."""
    code = r["code"]
    if r["phase"] == "racing":
        if pid not in r["grid"]:
            return
        c = _car(r, pid)
        if c["ms"] is not None or c["dnf"]:
            return
        seq = r["race_seq"]
        c["ms"] = ms
        r["finish"].append({"pid": pid, "name": c["name"], "ms": ms,
                            "color": c["color"]})
        r["finish"].sort(key=lambda e: e["ms"])
        if r["deadline"] is None:
            r["deadline"] = _now_ms() + FINISH_GRACE_MS
            eventlet.spawn_after(FINISH_GRACE_MS / 1000.0,
                                 _close_race, code, "timeout", seq)
        socketio.emit("race_progress", _race_state(r), room="room:" + code)
        _maybe_close(code, seq)
        return

    if r["phase"] == "qualifying":
        best = r["qual"].get(pid)
        if best is None or ms < best:
            r["qual"][pid] = ms
            socketio.emit("qual_progress", {"qual": _qual_state(r)},
                          room="room:" + code)
            _bot_pole(r, pid, ms, w)
    # Practice and qualifying both send it straight back out for another lap -
    # a bot that finishes once and then parks is not practising, and a
    # qualifying session with one lap in it is not a session.
    if w is not None and r["phase"] in ("free", "qualifying"):
        w.restart(pid, r.get("bot_slot", {}).get(pid, 0), now)


def _bot_pole(r, pid, ms, w):
    """A bot has gone quickest in qualifying, so its lap becomes the room's ghost.

    Worth having rather than skipping: the one ghost a session is about is
    whoever is on pole, and a max bot's lap is the most useful target in the
    room - it is the record's own line, driven.

    `runcheck.leaves_course` is deliberately **not** applied, unlike the check on
    a person's pole lap. That check asks whether a replay stayed near the road,
    and the quick levels are driving a line that jumps clean across a loop on
    four tracks in this pool. It exists to stop a *client* fabricating a ghost
    for the room to chase; this one came from the room's own simulation.
    """
    if w is None:
        return
    if r["pole"] and r["pole"]["ms"] <= ms:
        return
    frames = w.ghost_of(pid)
    if not _sane_frames(frames):
        return
    c = _car(r, pid)
    r["pole"] = {"pid": pid, "name": c["name"], "color": c["color"], "ms": ms,
                 "hz": runcheck.GHOST_HZ, "frames": frames}
    socketio.emit("qual_pole", _pole_meta(r), room="room:" + r["code"])


def _sync_bots(r, game):
    """Make the live bot world match the seats in the database.

    One place, called from every path that can change either side - a bot added
    or kicked, a track changed, a room joined. The seats are the truth and the
    world is derived, which is the `_hot_track` rule again: a derived thing with
    a single writer can be stale and rebuilt, but it can never contradict.
    """
    if not botsim.available():
        return
    seats = [p for p in game.players if p.is_bot]
    if not seats:
        if r.get("bots"):
            botsim.drop(r["code"])
        r["bots"] = {}
        return
    r["bot_slug"] = game.track
    w = botsim.world(r["code"], game.track, create=True)
    if w is None:
        return
    want = {p.pid: (p.bot_level or bots_mod.DEFAULT_LEVEL) for p in seats}
    have = dict(w.bots)
    for pid in have:
        if pid not in want:
            w.remove(pid)
    holders = garage_mod.records_held()
    leaders = garage_mod.time_trial_leaders()
    for i, p in enumerate(seats):
        if p.pid in w.bots:
            continue
        # Seeded off the seat, so a bot makes the same mistakes for as long as
        # it is in the room and two bots never make them together.
        w.add(p.pid, want[p.pid], seed=p.id * 7919 + i)
        c = _car(r, p.pid)
        seat = p.to_dict(_livery_for(None, holders, p.name, leaders))
        c["name"], c["color"] = p.name, seat["color"]
    r["bots"] = dict(w.bots)
    r["bot_slot"] = {p.pid: i for i, p in enumerate(seats)}


def _hard_race_ms(slug):
    """The longest a race on this track may possibly last.

    Eight times a gold lap is far beyond any honest attempt while still being
    short enough that a stranded room recovers on its own rather than needing
    the host to notice.
    """
    t = tracks_mod.get(slug) or {}
    gold = (t.get("medals") or {}).get("gold") or 60.0
    return int(max(HARD_RACE_MIN_MS, min(HARD_RACE_MAX_MS, gold * 8000)))


def _qual_state(r):
    """The provisional grid, live, while qualifying is running.

    Ordered exactly the way the grid will be, so the list people watch during
    the session is the list they line up in - no lap sorts to the back, and
    everyone can see what a lap would buy them.
    """
    if r["phase"] not in ("qualifying", "countdown") and not r["qual"]:
        return None
    rows = []
    for pid in _live(r):
        c = r["cars"][pid]
        rows.append({"pid": pid, "name": c["name"], "color": c["color"],
                     "ms": r["qual"].get(pid)})
    rows.sort(key=lambda e: (e["ms"] is None, e["ms"] or 0, e["name"]))
    return {"ends": r["qual_end"], "rows": rows}


def _start_grid(r):
    """Qualifying order, with anyone who never set a lap shuffled in at the back.

    A lap is the price of a good slot. Nobody is sorted by name, ever: it is
    the one ordering that is both arbitrary and *stable*, so the same person
    started on pole every single race.
    """
    live = _live(r)
    timed = sorted((p for p in live if r["qual"].get(p)),
                   key=lambda p: r["qual"][p])
    untimed = [p for p in live if not r["qual"].get(p)]
    random.shuffle(untimed)
    return {pid: i for i, pid in enumerate(timed + untimed)}


def _reverse_grid(r):
    """The grid when there is no qualifying: last race's order, reversed.

    Somebody has to start on pole, and with no session to earn it in the only
    orderings available are arbitrary ones. Reversing the last result is the
    arbitrary one that is at least *about* the racing: the person who has just
    been beaten starts ahead of the person who beat them, and a room of mixed
    ability keeps having close races instead of one procession after another.

    Anyone who was not in the last race - or was not in a last race, because
    there has not been one - lines up behind the field, shuffled. A grid slot
    is something the room has seen you earn or lose; turning up is neither.
    """
    live = set(_live(r))
    order = [pid for pid in reversed(r["last_order"]) if pid in live]
    rest = [pid for pid in live if pid not in set(order)]
    random.shuffle(rest)
    return {pid: i for i, pid in enumerate(order + rest)}


def _pump(code):
    """Per-room broadcast loop: one merged snapshot per tick while anyone is here.

    The bots are stepped from here too, immediately before the snapshot that
    carries them, so a bot's pose is the freshest thing in the packet rather
    than a tick old.
    """
    idle = 0
    while True:
        eventlet.sleep(1.0 / TICK_HZ)
        r = _rooms.get(code)
        if not r:
            return
        _tick_bots(r)
        snap = _snapshot(r)
        _record_race(r)
        # **Idle is measured on the people, not on the cars.** A room with bots
        # in it never stops producing poses, so a pump that asked "did anybody
        # report" would keep a deserted room and its whole bot world alive for
        # ever - and the race in it could never end either.
        if _humans(r):
            idle = 0
        else:
            idle += 1
            # An empty room in the middle of a race is a race that can never
            # end by itself, and the room it strands is still there when
            # somebody comes back to it. Let it go before the pump does.
            if idle == TICK_HZ * 8 and r["phase"] in LIVE_PHASES:
                _abort_race(code, "Everyone left.")
            if idle > TICK_HZ * 20:      # nobody has sent a pose in 20s
                r["loop"] = None
                return
        if snap["cars"]:
            socketio.emit("poses", snap, room="room:" + code)


def _record_race(r):
    """One replay frame per car, on the ghost's clock, while a race is running.

    Sampled off the poses the server already has rather than asked for
    separately - a replay is the race as everybody else saw it, which is
    exactly what those poses are.

    Frame `n` is the pose at `n / REPLAY_HZ` seconds after the green light for
    *every* car, so the rows stay the same length and the whole thing plays
    back as one moment in time. A car that has stopped reporting (finished,
    gone, lagging) repeats its last pose rather than leaving a hole, since a
    hole would shift every frame after it and slew that car's replay against
    everybody else's.
    """
    rec = r.get("rec")
    if not rec or r["phase"] != "racing":
        return
    elapsed = (_now_ms() - rec["t0"]) / 1000.0
    while rec["n"] / REPLAY_HZ <= elapsed:
        if rec["n"] >= REPLAY_MAX_FRAMES:
            return
        for pid, frames in rec["cars"].items():
            c = r["cars"].get(pid)
            if c is None:
                frames.append(list(frames[-1]) if frames
                              else [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0])
                continue
            frames.append([c["p"][0], c["p"][1], c["p"][2],
                           c["q"][0], c["q"][1], c["q"][2], c["q"][3],
                           c["flags"]])
        rec["n"] += 1


def _store_replay(r, game, standings, why):
    """Write the race that has just finished out as a DriveRace. Lock held.

    Returns its id, or None - a race with nothing recorded (everybody
    disconnected before the first frame) is not a replay, and offering an
    empty one from the results sheet would be worse than offering none.
    """
    rec = r.get("rec")
    r["rec"] = None
    if not rec or not rec["n"]:
        return None
    order = {e["pid"]: i for i, e in enumerate(standings)}
    # **The livery is stored with the race rather than looked up when it is
    # watched**, which is the opposite of what a ghost does one screen over - and
    # deliberately so. A ghost is a lap of *yours* that you are chasing now, so
    # it should be the car you drive now. A replay is a record of an afternoon:
    # repainting everybody in it because somebody changed their mind last week
    # would make it a record of nothing.
    holders = garage_mod.records_held()
    leaders = garage_mod.time_trial_leaders()
    livery_by_pid = {pl.pid: _livery_for(pl.linked_user, holders, pl.name, leaders)
                     for pl in game.players}
    cars = []
    for pid, frames in rec["cars"].items():
        if len(frames) < 2:
            continue
        c = r["cars"].get(pid) or {}
        cars.append({"pid": pid, "name": c.get("name") or "Driver",
                     "color": c.get("color") or "#8899aa",
                     "livery": livery_by_pid.get(pid),
                     "ms": c.get("ms"), "dnf": bool(c.get("dnf")),
                     "ghost": runcheck.pack_ghost(frames)})
    if not cars:
        return None
    # In finishing order, so the replay opens on the winner rather than on
    # whoever happens to be first in a dict.
    cars.sort(key=lambda e: order.get(e["pid"], 99))
    race = DriveRace(code=r["code"], track=rec["track"] or game.track,
                     hz=REPLAY_HZ, ms=int(rec["n"] * 1000 / REPLAY_HZ),
                     why=why, cars_json=json_mod.dumps(cars))
    db.session.add(race)
    db.session.commit()
    return race.id


def _ensure_pump(code):
    r = _room(code)
    if r["loop"] is None:
        r["loop"] = eventlet.spawn(_pump, code)


@socketio.on("join_lobbies")
def on_join_lobbies():
    join_room("lobbies")
    emit("lobbies_update", _lobbies_payload())


@socketio.on("join_room_")
def on_join_room(data=None):
    code = (data or {}).get("code", "").upper()
    game = DriveGame.query.filter_by(code=code).first()
    if not game:
        return
    me = DrivePlayer.query.filter_by(game_id=game.id,
                                     session_key=get_session_key()).first()
    if not me:
        return
    join_room("room:" + code)
    _sid_room[request.sid] = (code, me.pid)
    r = _room(code)
    c = _car(r, me.pid)
    # The livery decides the colour, not the column - the same rule `to_dict`
    # follows and for the same reason. This dict is what the standings, the chat
    # line, the pole message and the stored replay all read, so a stale column
    # here would put somebody's hashed colour on every one of those while their
    # car on the road wore the one they chose. Taken on every connect rather
    # than at join, so changing a livery and reloading is enough.
    seat = me.to_dict(_livery_for(me.linked_user, name=me.name))
    c["name"], c["color"], c["ts"] = me.name, seat["color"], _now_ms()
    # Coming back clears the "left the room" mark but *not* a DNF: reconnecting
    # mid-race puts you back on the road, it does not put you back in the race
    # you dropped out of.
    c["gone"] = False
    # Rebuild the bot world if the room state was swept while nobody was here.
    # Derived from the seats and single-writer, so a miss costs a rebuild and
    # can never contradict the roster - the `_hot_track` rule again.
    _sync_bots(r, game)
    _ensure_pump(code)
    game.last_activity_at = datetime.utcnow()
    db.session.commit()
    emit("room_hello", {"track": game.track,
                        "me": seat,
                        "players": _roster(game),
                        "race": _race_state(r), "chat": r["chat"][-30:],
                        "settings": dict(r["settings"]),
                        "server_ms": _now_ms()})
    _broadcast_roster(game)


@socketio.on("clock")
def on_clock(data=None):
    """Round-trip clock sync so a countdown lands at the same instant for all.

    The reply is the whole of that. What the *request* also carries is the round
    trip this client has measured, which is the one thing about its connection
    the server cannot find out for itself: a pose is stamped when it **lands**,
    so the server times the leg out to everybody else exactly and knows nothing
    whatever about the leg in. Halved and kept here, it is what lets `_snapshot`
    report an age covering the whole path instead of half of it - without it
    every car is drawn short by its own upstream leg, on every screen but its
    own, which is about 1.5 units at 60ms of ping and always in the same
    direction.

    **Clamped, because it is a client number that buys distance.** The only
    thing it feeds is how far other browsers extrapolate this car, so inflating
    it draws you a little further up the road on screens that are not yours. It
    reaches neither `racecheck`, nor `prog`, nor the **standings** - which is
    why it travels in a field of its own rather than added into the pose age,
    see `_snapshot` - nor the result. `UPSTREAM_CAP_MS` is worth four units at
    MAX_SPEED, less than the error every honest car on the track was carrying
    while none of this was compensated at all. Kept as the **minimum** seen, the
    same sample the client's own offset is taken from: the shortest trip is the
    one with the least queueing in it, and a min cannot be walked upwards.
    """
    emit("clock", {"c": (data or {}).get("c"), "s": _now_ms()})
    ent = _sid_room.get(request.sid)
    if not ent:
        return                                  # not seated yet; four more come
    r = _rooms.get(ent[0])
    if r:
        _note_upstream(_car(r, ent[1]), (data or {}).get("rtt"))


@socketio.on("pose")
def on_pose(data=None):
    """A car's own report of where it is. Client-authoritative, but not unquestioned.

    Client-authoritative is right for a car in a race ticking at 30Hz - there is
    no other way to have it steer like a car - but "authoritative" was doing more
    work than it should have. Every field here arrived unchecked, including the
    two the *server* then made decisions from: `prog` orders the standings and is
    the only real tooth in `_finish_is_possible`, so `emit('pose', {prog: 99999})`
    followed by a finish claim won a race, its ELO, its win, its podium and its
    badge without the car being driven at all.

    So a pose is now plausible or it is dropped. `racecheck` says what that
    means and, more importantly, why each rule is shaped the way it is; what
    matters here is the failure mode. **A refused pose is not a penalty**: the
    car keeps the last position the server believed, which looks like a moment
    of rubber-banding, and it goes on racing. Only a car that fails steadily -
    `STRIKE_LIMIT` of them - loses its rating at the flag, silently. A dropped
    frame on a bad connection costs nothing, which it must, because this runs
    while somebody is mid-corner.
    """
    ent = _sid_room.get(request.sid)
    if not ent or not data:
        return
    code, pid = ent
    r = _rooms.get(code)
    if not r:
        return
    c = _car(r, pid)
    w = _watch(r, pid)
    track = _hot_track(r)
    now = _now_ms()

    p, q, v = data.get("p"), data.get("q"), data.get("v")
    # Numbers first, and `finite` rather than a bare `float()`: JSON has `NaN`
    # and `Infinity` and Python parses both, so this pose is fanned straight
    # back out to five other browsers as a car at coordinates that are not
    # coordinates. The pole ghost has been checked for exactly this since it
    # existed (`_sane_frames`); the live stream never was.
    if not (isinstance(p, list) and len(p) == 3 and racecheck.finite(p)):
        return
    if not (isinstance(q, list) and len(q) == 4 and racecheck.finite(q)):
        return
    p = [float(x) for x in p]

    # Measured against the last pose the server *believed*, not the last one it
    # was sent - otherwise a refused jump becomes the baseline for the next one
    # and a cheat only ever has to be refused once.
    prev = c["p"] if c["ts"] else None
    try:
        flags = int(data.get("flags") or 0)
    except (TypeError, ValueError):
        return
    if racecheck.check_pose(w, track, prev, p, now - (c["ts"] or now), flags):
        return
    racecheck.sample_progress(w, track, p, now)

    c["p"] = p
    c["q"] = [float(x) for x in q]
    if isinstance(v, list) and len(v) == 3 and racecheck.finite(v):
        c["v"] = [float(x) for x in v]
    c["cp"] = racecheck.clamp_cp(data.get("cp") or 0)
    c["flags"] = flags
    # The client's own progress, but never further round than the server has
    # seen it get. It is kept rather than replaced because it updates every pose
    # where the server's projection is sampled at 5Hz, and the standings read it
    # - so this is smooth where `w.prog` would step. What it can no longer be is
    # a number somebody typed.
    try:
        claimed = float(data.get("prog") or 0.0)
    except (TypeError, ValueError):
        claimed = 0.0
    if claimed != claimed:                              # NaN
        claimed = 0.0
    c["prog"] = max(0.0, min(claimed, w.prog + racecheck.PROG_LEAD))
    # How full the tow is. Clamped rather than trusted: it is fanned straight
    # back out to everybody else, and it is the loudness of an effect on their
    # screens, so a client sending 400 would be a car in a permanent boost.
    try:
        c["sl"] = min(1.0, max(0.0, float(data.get("sl") or 0.0)))
    except (TypeError, ValueError):
        c["sl"] = 0.0
    c["ts"] = now


@socketio.on("set_track")
def on_set_track(data=None):
    code = (data or {}).get("code", "").upper()
    slug = (data or {}).get("track", "")
    if not tracks_mod.get(slug):
        return
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        r = _room(code)
        if r["phase"] in LIVE_PHASES:
            emit("room_error", {"error": "Can't change track mid-race."})
            return
        game.track = slug
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        r["trk"] = None                  # `_hot_track`'s memo; this is its writer
        _reset_race(r)
        # A new track is a new world: a different ribbon, a different collider
        # and a different fast line. `_sync_bots` notices the slug moved and
        # rebuilds, which is the same rule `_hot_track` follows one line up.
        _sync_bots(r, game)
    socketio.emit("track_change", {"track": slug}, room="room:" + code)
    _broadcast_lobbies()


@socketio.on("set_setting")
def on_set_setting(data=None):
    """The host changing what the next race will be.

    Between races only, for the same reason the track is: it decides what
    everybody is about to spend the next few minutes doing, and moving it out
    from under a session already running would be changing the rules mid-game.
    The whole set is sent back to the whole room, so nobody is looking at a
    switch that says something different from the one the host is holding.
    """
    code = (data or {}).get("code", "").upper()
    key = (data or {}).get("key")
    if key not in ROOM_DEFAULTS:
        return
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        r = _room(code)
        if r["phase"] in LIVE_PHASES:
            emit("room_error", {"error": "Can't change the settings mid-race."})
            return
        r["settings"][key] = bool((data or {}).get("value"))
        out = dict(r["settings"])
    socketio.emit("room_settings", out, room="room:" + code)


def _seat_bot(game, level, commit=True):
    """Add one bot seat to a room. Returns the row, or None if it is full.

    `commit=False` is for filling the grid, which seats up to seven in a row:
    a commit each was seven write transactions before the roster went out, and
    the press felt like it had not registered. The caller commits once.
    """
    if len(game.players) >= game.max_players:
        return None
    # Checked against what is *offered* rather than what exists, so a level that
    # is not ready cannot be reached by editing one field in a socket payload.
    if level not in bots_mod.OFFERED:
        level = bots_mod.DEFAULT_LEVEL
    used = {p.name for p in game.players}
    name = bots_mod.pick_name(used)
    seat = max((p.seat_order for p in game.players), default=-1) + 1
    p = DrivePlayer(game_id=game.id, user_id=None,
                    session_key="bot_%s" % uuid.uuid4().hex[:12],
                    name=name, color=color_for(name), seat_order=seat,
                    is_host=False, is_bot=True, bot_level=level)
    db.session.add(p)
    # `flush` gets the row an id without a write transaction, but **it does not
    # expire anything**, and `game.players` is a loaded collection that stays
    # cached until something does. A commit used to be what expired it. Without
    # the explicit expire the fill loop re-reads a `game.players` that never
    # grows, so `len(...) >= max_players` is never true and it seats bots until
    # the process is killed - and every seat computes the same `seat_order`.
    # One SELECT per bot, against seven write transactions before.
    db.session.flush()
    if commit:
        db.session.commit()
    else:
        db.session.expire(game, ["players"])
    return p


def _host_room(code):
    """`(game, room)` if this socket is the host of a room that can take bots.

    The one gate for both bot commands: it is the host's field to set, and it
    is set **between races** for the same reason the track and the qualifying
    switch are - adding a car to a grid that is already lit changes what
    everybody is in the middle of.
    """
    game = DriveGame.query.filter_by(code=code).first()
    if not game:
        return None, None
    me = DrivePlayer.query.filter_by(game_id=game.id,
                                     session_key=get_session_key()).first()
    if not me or not me.is_host:
        return None, None
    r = _room(code)
    if r["phase"] in LIVE_PHASES:
        emit("room_error", {"error": "Can't change the bots mid-race."})
        return None, None
    return game, r


@socketio.on("add_bot")
def on_add_bot(data=None):
    """Host-only: seat one bot at the chosen level."""
    code = (data or {}).get("code", "").upper()
    if not botsim.available():
        emit("room_error", {"error": "Bots are switched off on this server."})
        return
    with _lock(code):
        game, r = _host_room(code)
        if not game:
            return
        if len([p for p in game.players if p.is_bot]) >= botsim.MAX_BOTS:
            emit("room_error", {"error": "That is as many bots as a room takes."})
            return
        if not _seat_bot(game, (data or {}).get("level")):
            emit("room_error", {"error": "The room is full."})
            return
        _sync_bots(r, game)
    _broadcast_roster(game)


@socketio.on("fill_bots")
def on_fill_bots(data=None):
    """Host-only: fill every empty seat with bots at the chosen level."""
    code = (data or {}).get("code", "").upper()
    if not botsim.available():
        emit("room_error", {"error": "Bots are switched off on this server."})
        return
    with _lock(code):
        game, r = _host_room(code)
        if not game:
            return
        level = (data or {}).get("level")
        added = 0
        while len(game.players) < game.max_players:
            if len([p for p in game.players if p.is_bot]) >= botsim.MAX_BOTS:
                break
            if not _seat_bot(game, level, commit=False):
                break
            added += 1
        if not added:
            db.session.rollback()
            emit("room_error", {"error": "There is no room for another car."})
            return
        db.session.commit()
        _sync_bots(r, game)
    _broadcast_roster(game)


def _reset_race(r):
    """Put the room back to free practice with nothing left over.

    `last_order`, `points` and `settings` deliberately survive: the first is the
    result of the race that just happened and is the next grid, the second is
    the room's championship and is the whole point of there being more than one
    race, and the third is what the host has said about the room.
    """
    r["phase"] = "free"
    r["t0"] = r["deadline"] = r["hard_end"] = r["qual_end"] = None
    r["finish"] = []
    r["qual"] = {}
    r["pole"] = None
    r["rec"] = None
    r["grid"] = {}
    r["splits"] = {}
    for pid in list(r["cars"]):
        c = r["cars"][pid]
        if c["gone"]:
            # Only kept around to be a DNF in the race that has just ended.
            r["cars"].pop(pid, None)
            r.get("watch", {}).pop(pid, None)
            continue
        c["ms"], c["dnf"], c["cp"], c["prog"] = None, False, 0, 0.0
    # The anti-cheat's rolling state goes back to nothing with everything else.
    # `on_set_track` comes through here, and a new track is a different ribbon,
    # so a carried-over station hint and progress would be measurements of a
    # line the car is no longer on.
    for w in r.get("watch", {}).values():
        w.reset()
    # And the bots go back out on the road. Same reasoning as the watchers: they
    # are mid-lap in a session that no longer exists.
    world = _bot_world(r)
    if world is not None:
        world.release()


def _abort_race(code, why):
    """Scrap a race in progress and hand the room back, rating nothing.

    Used for the ways a race stops being a race rather than ending as one: the
    host calling it off before the lights, and the room emptying out.
    """
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] not in LIVE_PHASES:
                return
            r["race_seq"] += 1        # orphan every timer this race armed
            _reset_race(r)
            game = DriveGame.query.filter_by(code=code).first()
            if game:
                game.status = "waiting"
                game.last_activity_at = datetime.utcnow()
                db.session.commit()
        socketio.emit("race_abort", {"why": why}, room="room:" + code)
        _broadcast_lobbies()


def _open_race(r):
    """Wind a free room up for a new race, and say whether qualifying will run.

    Both answers end in five seconds of lights; what they are counting down to
    is the difference. With qualifying on that is the session, and the grid is
    the order it produces. With it off it is the race itself, and the grid is
    the last result reversed - see `_reverse_grid`.
    """
    quali = bool(r["settings"].get("qualifying", ROOM_DEFAULTS["qualifying"]))
    r["race_seq"] += 1
    r["qual"] = {}
    r["pole"] = None
    r["qual_end"] = None
    r["t0"] = r["deadline"] = r["hard_end"] = None
    r["finish"] = []
    r["grid"] = {}
    r["splits"] = {}
    r["rec"] = None
    # Rematch can land inside the twelve seconds the results sheet is up,
    # before the tail of `_close_race` has tidied up, so the cars kept behind
    # to be DNFs in the last race are dropped here too.
    for pid in [p for p, c in r["cars"].items() if c["gone"]]:
        r["cars"].pop(pid, None)
    for c in r["cars"].values():
        c["ms"], c["dnf"] = None, False
    r["phase"] = "qual_countdown" if quali else "countdown"
    r["t0"] = _now_ms() + COUNTDOWN_MS
    return quali


@socketio.on("start_race")
def on_start_race(data=None):
    """The host's one button, and it means different things by phase.

    In free practice it starts the five seconds before qualifying - or, with
    qualifying switched off in the room settings, the five seconds before the
    race itself. During qualifying it is "go now", because ninety seconds is
    the right length for a session nobody wants to cut short and the wrong
    length for four people who are ready.
    """
    code = (data or {}).get("code", "").upper()
    skip = go = None
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        r = _room(code)
        if r["phase"] == "qualifying":
            skip = r["race_seq"]      # skip the rest of the session
        elif r["phase"] in ("qual_countdown", "countdown", "racing"):
            return
        else:
            if not _live(r):
                emit("room_error", {"error": "Nobody is here to race."})
                return
            quali = _open_race(r)
            game.status = "playing"
            game.last_activity_at = datetime.utcnow()
            db.session.commit()
            go = (r["race_seq"], quali, r["t0"], game.track)
    if skip is not None:
        _close_qual(code, skip)
        return
    if go is None:
        return
    seq, quali, t0, track = go
    if quali:
        # Nobody is placed anywhere for this one. Qualifying is not a start
        # line - everyone leaves the pits when they like, on their own lap -
        # so the lights are simply "the session opens now", counted down from
        # wherever you happen to be sitting.
        socketio.emit("qual_countdown", {"t0": t0, "server_ms": _now_ms()},
                      room="room:" + code)
        eventlet.spawn_after(COUNTDOWN_MS / 1000.0, _open_qual, code, seq)
    else:
        _light_grid(code, seq, track)
    _broadcast_lobbies()


def _open_qual(code, seq):
    """The lights before qualifying have run down: the session is open."""
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "qual_countdown" or r["race_seq"] != seq:
                return
            r["phase"] = "qualifying"
            r["qual"] = {}
            r["pole"] = None
            r["qual_end"] = _now_ms() + QUAL_MS
            r["t0"] = None
            ends = r["qual_end"]
            qual = _qual_state(r)
        socketio.emit("qual_start", {"ends": ends, "qual": qual,
                                     "server_ms": _now_ms()}, room="room:" + code)
        eventlet.spawn_after(QUAL_MS / 1000.0, _close_qual, code, seq)


@socketio.on("qual_time")
def on_qual_time(data=None):
    """A practice lap set during qualifying. Best one counts, as it should.

    The replay comes up with it, because the lap on provisional pole is a ghost
    everybody else in the room can chase - which is the one ghost worth having
    during a session whose entire purpose is that lap. Only the leader's is
    kept; the rest are read once to find out they are not quick enough.
    """
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    r = _rooms.get(code)
    if not r or r["phase"] != "qualifying":
        return
    ms = int((data or {}).get("ms") or 0)
    if ms <= 0:
        return
    # Pole was claimable with `emit('qual_time', {ms: 1})`, the same way a race
    # was winnable with `emit('finish', {ms: 1})`. A qualifying lap has no green
    # light of its own to measure against - everybody leaves when they like - so
    # only the physical floor applies here, not the clock. That is the half that
    # matters anyway: it is what stops a one-line grid.
    track = _room_track(code)
    if track and ms < laptime.line_length(track) / (tuning.MAX_SPEED * 1.7) * 1000.0:
        return
    if r["qual"].get(pid) is not None and ms >= r["qual"][pid]:
        return
    r["qual"][pid] = ms
    socketio.emit("qual_progress", {"qual": _qual_state(r)}, room="room:" + code)
    frames = (data or {}).get("ghost")
    if not _sane_frames(frames):
        return
    if r["pole"] and r["pole"]["ms"] <= ms:
        return                   # quick, but not quick enough to be the ghost
    # The pole lap is the one ghost a whole qualifying session chases, so it is
    # worth more than a shape check before it becomes everybody's target: a
    # fabricated one is a car nobody can follow, cutting a corner that is not
    # there, and every driver in the room aiming at it. The corridor is the one
    # question worth asking of frames alone - `runcheck.validate`'s gate and
    # clock checks want the splits, which a qualifying lap does not send, and
    # the re-simulation wants an input stream, which no room lap carries.
    if track and runcheck.leaves_course(track, frames):
        return
    c = _car(r, pid)
    r["pole"] = {"pid": pid, "name": c["name"], "color": c["color"], "ms": ms,
                 "hz": int((data or {}).get("hz") or runcheck.GHOST_HZ),
                 "frames": frames}
    # Only who is on pole goes out to everybody. The lap itself is tens of
    # kilobytes and most of the room is not chasing it, so it is fetched by the
    # people who are - see `qual_pole_req`.
    socketio.emit("qual_pole", _pole_meta(r), room="room:" + code)


def _sane_frames(frames):
    """Is this a replay at all?

    The pole lap is the one thing a client sends that the server hands **to
    other clients** rather than storing, so it is worth a look before it is
    passed on: a frame of nonsense is a rival's ghost car at coordinates that
    are not numbers, in somebody else's browser. Only the shape is checked -
    whether the lap is honest is a question for a leaderboard, and this one
    never reaches one.
    """
    if not isinstance(frames, list) or not 2 <= len(frames) <= runcheck.MAX_GHOST_FRAMES:
        return False
    for f in frames:
        if not isinstance(f, list) or len(f) < 7:
            return False
        for v in f[:7]:
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v != v:
                return False
    return True


def _pole_meta(r):
    p = r.get("pole")
    if not p:
        return None
    return {"pid": p["pid"], "name": p["name"], "color": p["color"], "ms": p["ms"]}


def _seat_livery(code, pid):
    """The car whoever holds this seat drives **now**.

    Looked up when it is asked for rather than kept on the live car dict, which
    is the ghost rule and not the replay one: a ghost is a lap somebody is
    chasing at this moment, so it should be the car its owner drives at this
    moment. `_store_replay` resolves the same thing at the opposite end of the
    same argument, and says why there.
    """
    game = DriveGame.query.filter_by(code=code).first()
    if not game:
        return None
    for pl in game.players:
        if pl.pid == pid:
            return _livery_for(pl.linked_user, name=pl.name)
    return None


@socketio.on("qual_pole_req")
def on_qual_pole_req(data=None):
    """Somebody has asked to chase the provisional pole lap. Send it to them."""
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, _pid = ent
    r = _rooms.get(code)
    p = (r or {}).get("pole")
    if not p:
        emit("qual_pole_ghost", {"ghost": None})
        return
    # Their whole car, not only its colour: this ghost is the one thing everybody
    # in a qualifying session is looking at, and a lap that arrived with a body
    # colour alone was drawn on stock wheels with no stripe - the pole driver's
    # paint on somebody else's car.
    #
    # `color` is answered off the livery for the reason `api_ghost` gives: it is
    # the same fact twice, and the copy on the live car dict is only as fresh as
    # that driver's last connect, so computing them separately is how the swatch
    # and the car come to disagree.
    livery = _seat_livery(code, p["pid"])
    emit("qual_pole_ghost", {"ghost": p["frames"], "hz": p["hz"],
                             "who": p["name"],
                             "color": (livery or {}).get("body") or p["color"],
                             "livery": livery,
                             "ms": p["ms"], "pid": p["pid"]})


def _close_qual(code, seq):
    """The session is over: the grid is the order it finished in."""
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "qualifying" or r["race_seq"] != seq:
                return
            game = DriveGame.query.filter_by(code=code).first()
            if not game:
                return
            grid = _start_grid(r)
            track = game.track
        if not grid:
            _abort_race(code, "Nobody set off.")
            return
        _light_grid(code, seq, track, grid)


def _light_grid(code, seq, track, grid=None):
    """Put the field on the grid and light the countdown.

    Both ways into a race come through here - the end of qualifying, and a room
    with qualifying switched off - so the grid, the lights and the green are one
    piece of machinery with two ways of deciding the order.
    """
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["race_seq"] != seq:
                return
            if r["phase"] not in ("qualifying", "countdown"):
                return
            game = DriveGame.query.filter_by(code=code).first()
            if not game:
                return
            if grid is None:
                grid = _reverse_grid(r)
            # A grid worked out a moment ago, under a different hold of this
            # lock (see `_close_qual`), can name somebody who has since left -
            # and during qualifying a leaver's car is dropped rather than kept
            # as a DNF, because there is no race to be a DNF in yet. Drop them
            # and close the gap, or the field starts with a hole in it and the
            # placement below reads a car that is not there.
            grid = {pid: i for pid, i in grid.items() if pid in r["cars"]}
            grid = {pid: n for n, (pid, _) in
                    enumerate(sorted(grid.items(), key=lambda kv: kv[1]))}
            if not grid:
                r["race_seq"] += 1
                _reset_race(r)
                socketio.emit("race_abort", {"why": "Nobody is here."},
                              room="room:" + code)
                return
            r["grid"] = grid
            # The bots line up with everybody else, on the slots the same grid
            # handed them, and are held there for the lights.
            world = _bot_world(r)
            if world is not None:
                world.place_grid({pid: n for pid, n in grid.items()
                                  if pid in _bot_pids(r)})
            r["races_run"] += 1
            r["phase"] = "countdown"
            r["t0"] = _now_ms() + COUNTDOWN_MS
            r["deadline"] = None
            for pid in grid:
                c = r["cars"][pid]
                c["ms"], c["dnf"], c["cp"], c["prog"] = None, False, 0, 0.0
            t0 = r["t0"]
            qual = dict(r["qual"])
        # No `flip`: which side pole starts on is the inside of the first
        # corner, which is a property of the track (`pole_side`) and the same
        # every race. It used to alternate, which meant half the time the car
        # that earned pole started on the outside of turn one.
        socketio.emit("race_start", {"t0": t0, "grid": grid, "track": track,
                                     "qual": qual, "server_ms": _now_ms()},
                      room="room:" + code)
        eventlet.spawn_after(COUNTDOWN_MS / 1000.0, _go_green, code, seq)
        _broadcast_lobbies()


def _go_green(code, seq):
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "countdown" or r["race_seq"] != seq:
                return
            r["phase"] = "racing"
            game = DriveGame.query.filter_by(code=code).first()
            hard = _hard_race_ms(game.track if game else "")
            r["hard_end"] = _now_ms() + hard
            t0 = r["t0"]
            # Start recording from the green light, so frame 0 of every car is
            # the same instant and the replay's clock is the race's clock.
            r["rec"] = {"t0": t0, "track": game.track if game else "", "n": 0,
                        "cars": {pid: [] for pid in r["grid"]}}
            # **Every watcher starts this race from nothing**, and the green
            # light is exactly the right moment for it - not `countdown`, where
            # the grid is assigned.
            #
            # `Watcher.prog` is monotone: it has to be, or a car that rolled
            # backwards over its own line would be refused the finish it just
            # took. So a qualifying lap's progress would otherwise still be
            # sitting there when the lights went out, and `_finish_is_possible`
            # would wave the first claim of the race through on the strength of
            # a lap driven before it.
            #
            # The strikes go with it, and that is what pays for the grid. Being
            # placed in a slot is a teleport by every measure in `racecheck`,
            # and the client does it partway through the countdown - after the
            # phase changes, so a reset there would happen *before* the jump it
            # was meant to excuse and catch nothing. Clearing here, five seconds
            # later, means whatever the move cost is discarded before it can
            # count against anybody, and the first pose of the race is measured
            # against the grid slot the car is genuinely sitting on.
            for w in r.get("watch", {}).values():
                w.reset()
            # The bots' clock is the room's clock: they start the lap they are
            # timed on at the same instant everybody else does.
            world = _bot_world(r)
            if world is not None:
                world.green(t0)
        socketio.emit("race_green", {"t0": t0}, room="room:" + code)
        # The backstop. Every other way a race ends depends on somebody doing
        # something; this one does not.
        eventlet.spawn_after(hard / 1000.0, _close_race, code, "time limit", seq)


@socketio.on("split")
def on_split(data=None):
    """A checkpoint time, so everyone can be shown their gap to the leader.

    Fanned straight back out rather than accumulated into a leaderboard: each
    client keeps what it has heard and works out its own reference, because
    "the quickest anybody *else* got here" is a different number for each of
    them and the server would have to send a different message per car.
    """
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    r = _rooms.get(code)
    if not r or r["phase"] != "racing" or pid not in r["grid"]:
        return
    try:
        cp = int((data or {}).get("cp") or 0)
        ms = int((data or {}).get("ms") or 0)
    except (TypeError, ValueError):
        return
    if cp <= 0 or ms <= 0:
        return
    # Bounded the same way a finish is, and for a smaller version of the same
    # reason. A split only feeds the gap on everybody's HUD - it reaches no
    # standing and no rating - but it is fanned straight back out, so an
    # unbounded one shows five other people a leader who is forty seconds up the
    # road and not there. `cp` past the last checkpoint is not a checkpoint, and
    # `ms` cannot be longer than the race has been running.
    track = _hot_track(r)
    if track and cp > len(track.get("gates") or []):
        return
    if ms > _now_ms() - (r.get("t0") or 0) + FINISH_CLOCK_SLACK_MS:
        return
    mine = r["splits"].setdefault(pid, {})
    if cp in mine:
        return              # a checkpoint is passed once; a second is a replay
    mine[cp] = ms
    socketio.emit("race_split", {"pid": pid, "cp": cp, "ms": ms},
                  room="room:" + code)


# How far the clock may disagree. It is for the network and not for the driving:
# the client stops its own timer at the line and the message then crosses the
# wire, so an honest `ms` is a little *under* the server's own elapsed time.
FINISH_CLOCK_SLACK_MS = 1500

# How much of the ribbon a car must have covered to claim it went round.
FINISH_MIN_PROG = 0.9


def _room_track(code):
    """The track a room is on, as a track dict, or None.

    One small query, on paths that run once per car per race and a few times a
    qualifying session. The alternative - keeping a copy on the in-memory room -
    is a second source of truth that `set_track` and every join would have to
    remember to update, for a saving nothing here can measure.
    """
    game = DriveGame.query.filter_by(code=code).first()
    return tracks_mod.get(game.track) if game else None


def _finish_is_possible(r, c, ms, w=None):
    """Could this car have finished in `ms`? Not "did it" - see the caveat.

    `on_finish` used to take any positive number, so `socket.emit('finish',
    {ms: 1})` won any race outright - and a race feeds ELO, `wins`, `podiums`
    and the `checkers` badge. Clients are authoritative over their own car by
    design, and that is right for a race ticking at 30Hz, but *finishing* is one
    discrete claim and the server has always known when the lights went green.

    Three bounds, and the middle one is the load-bearing one:

    * **Not longer than the race has been running.** Trivially true of an honest
      lap and it costs nothing to say.
    * **Not faster than the car physically goes.** The ribbon's own length over
      `MAX_SPEED * 1.7` - the hard velocity clamp, the same number
      `runcheck.SPEED_CEIL` is set from. This is a statement about the
      simulation rather than about anybody's driving, so unlike a floor under
      `ideal` it cannot punish somebody for being quick: on Sunrise it is 9.8s
      against a real lap of about 16.
    * **The car has to have gone round**, and this is now the server's own
      opinion of that rather than the client's. It used to read `c["prog"]`,
      which is a number the same client had just sent - so the one load-bearing
      check was satisfied by `emit('pose', {prog: 99999})` and the whole thing
      reduced to "wait out the physics floor, then claim". What it reads now is
      `Watcher.prog`: the car's position projected back onto the ribbon by
      `racecheck.sample_progress`, five times a second, from poses that each had
      to be reachable from the one before. To get that number up you have to
      actually move a car around the course.

    **What this does not do**, and it should be said plainly: `ms` still comes
    from the client, so somebody willing to drive round slowly can claim the lap
    took less time than it did. Closing *that* needs the replay and the input
    stream behind it, which a race deliberately does not carry - see
    `racecheck`'s preamble for why a room is not the place for the
    re-simulation. The bound that is left is a real one: a lap no faster than
    the car goes, no longer than the race has run, over a course the server
    watched the car cover.
    """
    elapsed = _now_ms() - (r.get("t0") or 0)
    if ms > elapsed + FINISH_CLOCK_SLACK_MS:
        return False
    # Asked of the room's own row rather than read off `r["rec"]`, which
    # `_go_green` sets up and which is therefore either absent or a *previous*
    # race's track during qualifying. A miss skips the two track-shaped checks
    # rather than failing them: refusing a finish nobody can prove is wrong
    # costs somebody a race they actually drove, which is the worse mistake.
    track = _room_track(r["code"])
    if track:
        length = laptime.line_length(track)
        if ms < length / (tuning.MAX_SPEED * 1.7) * 1000.0:
            return False
        # The server's projection, falling back to the car's own number only
        # when there is no watcher at all - which is a car that has never sent a
        # pose, and therefore one that is about to fail this anyway.
        prog = w.prog if w is not None else c.get("prog", 0.0)
        if prog < FINISH_MIN_PROG * length:
            return False
    return True


@socketio.on("finish")
def on_finish(data=None):
    """A car crossed the line. First one home starts the clock on everyone else."""
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    seq = None
    with _lock(code):
        r = _rooms.get(code)
        if not r or r["phase"] != "racing":
            return
        c = _car(r, pid)
        if c["ms"] is not None or c["dnf"]:
            return
        ms = int((data or {}).get("ms") or 0)
        if ms <= 0:
            return
        if not _finish_is_possible(r, c, ms, _watch(r, pid)):
            return
        seq = r["race_seq"]
        c["ms"] = ms
        r["finish"].append({"pid": pid, "name": c["name"], "ms": ms,
                            "color": c["color"]})
        r["finish"].sort(key=lambda e: e["ms"])
        if r["deadline"] is None:
            r["deadline"] = _now_ms() + FINISH_GRACE_MS
            eventlet.spawn_after(FINISH_GRACE_MS / 1000.0,
                                 _close_race, code, "timeout", seq)
        socketio.emit("race_progress", _race_state(r), room="room:" + code)
    _maybe_close(code, seq)


def _maybe_close(code, seq=None):
    """Close the race the moment nobody is left out on the circuit.

    Called from every path that can empty the road - a finish, a resignation, a
    disconnection, a kick - because "the last car is in" is not something only
    finishing can cause, and when a leaver was the last one still driving there
    is nothing else left to notice it.

    Never called with the room lock held: `_close_race` takes it, and an
    eventlet semaphore is not reentrant.
    """
    r = _rooms.get(code)
    if not r or r["phase"] != "racing":
        return
    if seq is not None and r["race_seq"] != seq:
        return
    if _pending(r):
        return
    eventlet.spawn_after(0.4, _close_race, code, "all in", r["race_seq"])


def _close_race(code, why, seq=None):
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "racing":
                return
            if seq is not None and r["race_seq"] != seq:
                return          # a timer armed for a race that is already over
            r["phase"] = "results"
            game = DriveGame.query.filter_by(code=code).first()
            standings = list(r["finish"])
            # Everyone on the grid who is not in the results is a DNF: retired,
            # still circulating when the flag came out, or gone. A car that
            # left mid-race is kept in `cars` precisely so that it lands here
            # rather than quietly escaping the result. The grid is the field,
            # so somebody who turned up after the lights is not in the standings
            # and somebody who was there at the lights always is.
            now = _now_ms()
            for pid in r["grid"]:
                c = r["cars"].get(pid)
                if c is None or c["ms"] is not None:
                    continue
                c["dnf"] = True
                standings.append({"pid": pid, "name": c["name"], "ms": None,
                                  "color": c["color"]})
            # The championship the room is running, updated the moment the
            # standings are settled. Unlike the rating it does not care whether
            # there is a `game` row to write to - the table is the room's own
            # and lives in memory - and unlike the rating it pays out to
            # everybody, so it is not gated on the anti-cheat either: a flagged
            # car keeps its place in the standings on the screen, and points are
            # what that place is worth in this room for the next ten minutes.
            points = _score_race(r, standings)
            elo_delta = {}
            race_id = None
            # Judged before either of the next two lines: the rating needs the
            # answer, and `_store_replay` is what clears `r["rec"]`, which is
            # the recording the post-race pass reads.
            flagged = _judge_race(r)
            if game:
                elo_delta = _rate_race(game, standings, set(flagged))
                race_id = _store_replay(r, game, standings, why)
                _record_flags(r, game, flagged, race_id)
                game.add_result({"t": now, "track": game.track, "race": race_id,
                                 "standings": standings, "why": why})
                game.status = "waiting"
                game.last_activity_at = datetime.utcnow()
                db.session.commit()
            # The order this race finished in is the grid for the next one when
            # the room is not qualifying - so it is kept here rather than
            # derived later, while the standings are in front of us.
            r["last_order"] = [e["pid"] for e in standings]
            closed_seq = r["race_seq"]
            socketio.emit("race_result", {"standings": standings, "why": why,
                                          "elo": elo_delta, "points": points,
                                          "race": race_id},
                          room="room:" + code)
            # The sidebar tally has moved, and the roster is the one thing that
            # carries it - so it is re-sent rather than left to the client to
            # add up out of the result sheet. Two reasons and they are the same
            # reason twice: a browser that walked in after the lights never saw
            # the result, and a reload has to land on the numbers everybody else
            # is looking at.
            if game:
                _broadcast_roster(game)
        # Scheduled rather than slept through inline. Two reasons, one of them
        # production and one of them the tests.
        #
        # `_close_race` is called *directly* for the host's End race (`on_end_race`),
        # so an inline `eventlet.sleep(RESULTS_HOLD_S)` held that handler's greenlet
        # for twelve seconds after the flag - cooperative, so nothing else stalled,
        # but the handler had no business still being on the stack.
        #
        # And it made `_close_race` untestable without paying for it: two tests
        # called it synchronously and slept twelve real seconds each, which was
        # **24s of a 56s suite** and therefore most of why a deploy felt slow. It
        # hid well - the tests passed, so the only symptom was the clock.
        eventlet.spawn_after(RESULTS_HOLD_S, _clear_results, code, closed_seq)


def _clear_results(code, seq):
    """The room going back to practice once the results sheet has had its time.

    The `seq` guard is the same one every deferred close carries: Rematch can fire
    inside `RESULTS_HOLD_S`, so a timer armed for one race must not tidy up the next
    one. Kept here rather than left in `_close_race` because this is the half that
    runs late, which is exactly the half that can be stale.
    """
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "results" or r["race_seq"] != seq:
                return
            _reset_race(r)
        socketio.emit("race_reset", {}, room="room:" + code)
        _broadcast_lobbies()


@socketio.on("resign")
def on_resign(data=None):
    """Retire from the race and go back to practice, without leaving the room.

    A DNF, and it is rated as one. Quitting the race has to cost the same as
    quitting the tab, or the honest way out is the expensive one.
    """
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    seq = None
    with _lock(code):
        r = _rooms.get(code)
        if not r or r["phase"] not in ("countdown", "racing"):
            return
        c = _car(r, pid)
        if c["ms"] is not None or c["dnf"]:
            return
        seq = r["race_seq"]
        c["dnf"] = True
        emit("resigned", {"pid": pid})
        socketio.emit("race_progress", _race_state(r), room="room:" + code)
    _maybe_close(code, seq)


@socketio.on("end_race")
def on_end_race(data=None):
    """The host stopping a race that is not going to end on its own.

    Before the lights it is a cancellation and rates nothing. Once the race is
    running it is the chequered flag: whoever is home keeps their finishing
    order, everyone still out is a DNF, and it is rated like any other race.
    """
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        r = _room(code)
        phase, seq = r["phase"], r["race_seq"]
    if phase == "racing":
        _close_race(code, "ended by the host", seq)
    elif phase in ("qualifying", "countdown"):
        _abort_race(code, "The host called it off.")


def _judge_race(r):
    """Who, if anybody, drove something the car cannot do. `{pid: reasons}`.

    Two sources of evidence, and they answer different halves:

      * the **live** strikes each car collected through the race
        (`racecheck.Watcher`), which is the per-pose bucket and the corridor
        sampled at 5Hz;
      * a **post-race** pass over the trace the server recorded itself
        (`racecheck.scan_race`), which is the questions no per-step rule can
        ask - a whole race's median speed, and the corridor over every frame
        instead of every fifth one.

    Run before `_rate_race` and before `_store_replay`, because the first needs
    the answer and the second is what throws the frames away.

    Only the graded field is looked at: `r["grid"]` is who lined up, and
    somebody who joined after the lights is not in the standings and cannot be
    in this either.
    """
    rec = r.get("rec") or {}
    track = tracks_mod.get(rec.get("track") or "")
    out = {}
    bots = _bot_pids(r)
    for pid in r.get("grid", {}):
        # **A bot is never judged.** Every rule in `racecheck` is about whether
        # a *client* could have driven what it claims, and a bot has no client:
        # its poses are the server's own simulation of the server's own car. It
        # would also fail - the quick levels drive a line that jumps clean
        # across a loop, which is exactly what the corridor check is looking
        # for - and the finding would go in a table about people cheating.
        if pid in bots:
            continue
        reasons = {}
        w = r.get("watch", {}).get(pid)
        flagged = False
        if w is not None and w.flagged:
            flagged = True
            reasons.update(w.reasons)
        for why in racecheck.scan_race(track, (rec.get("cars") or {}).get(pid), REPLAY_HZ):
            flagged = True
            reasons[why] = reasons.get(why, 0) + 1
        if flagged:
            out[pid] = reasons
    return out


def _record_flags(r, game, flagged, race_id):
    """Write the findings down. Nothing in Drive reads them yet - that is the point.

    The verdict a flagged car gets is silent and rating-shaped: it is skipped by
    `_rate_race` exactly the way a guest is, and nobody in the room is told.
    That leaves the finding itself with nowhere to go, which is what this table
    is for - somewhere a person can look later, when there is an admin page to
    look with. See `DriveCheatFlag`.

    Guests are flagged too, even though a guest has no rating to lose. They can
    still take a win off somebody, and a row saying who and on what track is
    worth more than the reasoning that a guest does not matter.
    """
    if not flagged or not game:
        return
    by_pid = {p.pid: p for p in game.players}
    for pid, reasons in flagged.items():
        pl = by_pid.get(pid)
        c = r["cars"].get(pid) or {}
        db.session.add(DriveCheatFlag(
            user_id=pl.user_id if pl else None,
            name=(pl.name if pl else None) or c.get("name") or "Driver",
            code=r["code"], race_id=race_id, track=game.track,
            phase="racing", strikes=sum(reasons.values()),
            reasons_json=json_mod.dumps(reasons)))
    db.session.commit()


def _score_race(r, standings):
    """The room's championship points for one race, and the running tally with
    them added in. `{pid: {"got": n, "total": t}}`.

    **N for the winner down to 1 for last, where N is the size of the field.**
    So what a win is worth is how many cars you beat: a race in a full room
    moves the table more than a duel does, which is the right way round for a
    thing meant to hold a whole evening together.

    **A DNF scores nothing**, and the places behind the finishers simply go
    unawarded. Scoring the DNF rows off their positions would be paying out on
    the one part of a result that is noise - they are ordered by whichever they
    happened to give up in, which is exactly why `_rate_race` draws two of them
    rather than ranking them. A tally that survives a whole session has to be
    built out of the parts of a result that mean something, and the winner is
    still worth the full field either way: retiring costs you your own points,
    not everybody else's.

    Everyone in the standings scores, including guests and bots. This is not
    ELO - there is nothing here anybody can farm, because it does not leave the
    room - so the field is the field, and a bot taking third has to *take* third
    or the table is not about the racing.

    **It is a session, not a record.** It lives on the live room, so it survives
    a race (`_reset_race` leaves it alone), a track change and the results
    sheet, and it goes when the room does. No column, no migration, nothing to
    sweep - the same trade `settings` makes. A seat that leaves and comes back
    is a new seat with a new pid and starts from nothing, which is the honest
    reading of "leaving the room".
    """
    n = len(standings)
    out = {}
    for i, e in enumerate(standings):
        got = 0 if e["ms"] is None else n - i
        total = r["points"][e["pid"]] = r["points"].get(e["pid"], 0) + got
        out[e["pid"]] = {"got": got, "total": total}
    return out


def _rate_race(game, standings, skip=()):
    """Pairwise ELO over the finishing order, counting only logged-in accounts.

    **Guests are invisible to the rating.** They are in the room, on the grid
    and in the standings on the screen, but for ELO the field is the accounts
    and their order is their order *among themselves*: beating a guest gains
    nothing and losing to one costs nothing. Anything else is a rating anybody
    can move by opening a second tab, and the number stops meaning anything.
    The same goes for the win and podium tallies, which used to be read off the
    overall standings - so a guest winning meant nobody was recorded as having
    won, and a guest in the top three pushed an account off its own podium.

    A finisher beats a DNF. **Two DNFs draw with each other**, because their
    order in the standings is the arbitrary order they happened to drop out in
    (or the dict order they were swept up in), and staking a full win on it
    would be rating noise.

    Still needs two accounts: a race with one is a race with nobody to rate
    them against.

    **`skip` is the anti-cheat's whole verdict**, and it is deliberately the
    same door a guest comes through: a car that failed `_judge_race` is in the
    room, on the grid and in the standings on everybody's screen, and simply is
    not part of the rating. Nothing else happens to it. That means beating one
    gains nothing, which is the right answer twice over - the result is not
    evidence about either driver, and a room cannot be farmed by bringing a
    cheat along to lose to.
    """
    by_pid = {p.pid: p for p in game.players}
    rated = [e for e in standings
             if e["pid"] in by_pid and by_pid[e["pid"]].user_id
             and e["pid"] not in skip]
    if len(rated) < 2:
        return {}
    K = 32.0
    # Rank among the rated field only, so guest placings do not leave gaps or
    # steal a win. `standings` is already in finishing order with DNFs last.
    place = {e["pid"]: i for i, e in enumerate(rated)}
    finished = {e["pid"]: e["ms"] is not None for e in rated}
    ratings = {}
    for e in rated:
        ratings[e["pid"]] = _stats(by_pid[e["pid"]].linked_user).elo or 1000
    out = {}
    for e in rated:
        pid = e["pid"]
        st = _stats(by_pid[pid].linked_user)
        mine = ratings[pid]
        delta = 0.0
        n = 0
        for o in rated:
            if o["pid"] == pid:
                continue
            n += 1
            exp = 1 / (1 + 10 ** ((ratings[o["pid"]] - mine) / 400))
            if not finished[pid] and not finished[o["pid"]]:
                actual = 0.5           # neither of us got there; nobody won
            else:
                actual = 1.0 if place[pid] < place[o["pid"]] else 0.0
            delta += K * (actual - exp)
        if n:
            delta /= n
        st.races = (st.races or 0) + 1
        # A win is a win of the race you were rated in. Retiring is never one,
        # even when everybody retired.
        if finished[pid]:
            if place[pid] == 0:
                st.wins = (st.wins or 0) + 1
            if place[pid] < 3:
                st.podiums = (st.podiums or 0) + 1
        st.elo = max(100, int(round(mine + delta)))
        out[pid] = {"before": mine, "after": st.elo, "delta": round(delta)}
    db.session.commit()
    return out


@socketio.on("chat")
def on_chat(data=None):
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    text = ((data or {}).get("text") or "").strip()[:200]
    if not text:
        return
    r = _rooms.get(code)
    if not r:
        return
    c = _car(r, pid)
    msg = {"pid": pid, "name": c["name"], "color": c["color"], "text": text,
           "t": _now_ms()}
    r["chat"].append(msg)
    del r["chat"][:-60]
    socketio.emit("chat", msg, room="room:" + code)


@socketio.on("leave")
def on_leave(data=None):
    """Leaving on purpose: the row goes, not just the car.

    `data=None` is load-bearing. Every button that leaves a room emits this
    with no payload at all, so Socket.IO called the handler with no arguments
    and it raised a TypeError before doing anything - which meant pressing
    Leave took you to the lobbies page and left your name in the room you had
    just left, sitting there until the sweep noticed. Every handler here takes
    the same default now, since they all already cope with `(data or {})` and
    a client that emits without a payload should be a non-event rather than a
    line in the log.
    """
    _drop(request.sid, hard=True)


@socketio.on("disconnect")
def on_disconnect():
    _drop(request.sid, hard=False)


def _drop(sid, hard):
    ent = _sid_room.pop(sid, None)
    if not ent:
        return
    code, pid = ent
    r = _rooms.get(code)
    if r:
        c = r["cars"].get(pid)
        # Leaving mid-race is a DNF, not a disappearance. The car is marked
        # gone (so it stops being drawn and stops holding the race open) but
        # kept, so it is still in the standings and still rated. Otherwise the
        # cheapest way to avoid losing rating is to close the tab.
        if c is not None and r["phase"] in ("countdown", "racing") \
                and pid in r["grid"] and c["ms"] is None:
            c["dnf"] = True
            c["gone"] = True
        else:
            r["cars"].pop(pid, None)
    # Whoever just left may have been the last car still out there.
    _maybe_close(code)
    if not hard:
        return
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me:
            return
        was_host = me.is_host
        db.session.delete(me)
        db.session.commit()
        remaining = sorted(game.players, key=lambda p: p.seat_order)
        # **The host leaving closes the room.** The seat used to be handed to
        # whoever was next in seat order, which sounds generous and is not: the
        # room is the host's - the track, the settings, the grid, when a race
        # starts, which bots are in it - and everything about it that anybody
        # else was waiting for was theirs to press. Passing it to whoever
        # happened to join first hands the room to somebody who did not ask for
        # it, in the middle of a session somebody else set up, and the usual
        # outcome is a room that nobody starts anything in until it is swept.
        # The session's points go with it, which is the other half: a
        # championship is a thing the room was running, and a room with a new
        # owner is a new room.
        #
        # It only fires on a **hard** leave - the Leave button, or joining
        # somewhere else - because a disconnect is the soft kind: closing a tab
        # or losing wifi keeps the seat, so the host's train going into a tunnel
        # does not take everybody's race with it.
        if was_host:
            _close_room(game, "The host left, so the room closed.")
            return
        # **A room of nothing but bots is an empty room.** They cannot leave,
        # cannot host, and would otherwise hold the seat count above zero for
        # ever - the room would sit in the lobby list with four cars going round
        # it and nobody in it.
        #
        # Unreachable while every room has a host, now that the branch above
        # takes the host's own departure: anybody else leaving leaves the host
        # behind, and a host is a person. Kept because it is two lines, and
        # because what it prevents would otherwise wait on the 45-minute sweep.
        if not any(not p.is_bot for p in remaining):
            _close_room(game, "Everyone left.")
            return
        _broadcast_roster(game)


@socketio.on("kick")
def on_kick(data=None):
    code = (data or {}).get("code", "").upper()
    pid = (data or {}).get("pid")
    with _lock(code):
        game = DriveGame.query.filter_by(code=code).first()
        if not game:
            return
        me = DrivePlayer.query.filter_by(game_id=game.id,
                                         session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        target = next((p for p in game.players if p.pid == pid), None)
        if not target or target.is_host:
            return
        socketio.emit("kicked", {"pid": pid}, room="room:" + code)
        was_bot = target.is_bot
        db.session.delete(target)
        db.session.commit()
        r = _rooms.get(code)
        if r:
            c = r["cars"].get(pid)
            if c is not None and r["phase"] in ("countdown", "racing") \
                    and pid in r["grid"] and c["ms"] is None:
                c["dnf"], c["gone"] = True, True
            else:
                r["cars"].pop(pid, None)
            # The x on a bot's row is how a bot is removed - there is no second
            # control for it, because "take that car off the grid" is the same
            # thing whoever is driving it.
            if was_bot:
                _sync_bots(r, game)
        _broadcast_roster(game)
    _maybe_close(code)


# ---------------------------------------------------------------------------
# Background sweep: reap dead rooms (mirrors ERS/KoT)
# ---------------------------------------------------------------------------

def _stale_cleanup():
    IDLE_LIMIT = timedelta(minutes=45)

    def _run():
        with app.app_context():
            changed = False
            cutoff = datetime.utcnow() - IDLE_LIMIT
            for game in DriveGame.query.filter(DriveGame.status != "ended").all():
                seen = game.last_activity_at or game.created_at
                live = _rooms.get(game.code)
                # Busy means *people*. Bots report a pose thirty times a second
                # for as long as the pump runs, so asking `_live` here would
                # make a deserted room with a bot in it immortal.
                busy = bool(live and _humans(live))
                humans = [p for p in game.players if not p.is_bot]
                if not humans or (not busy and seen and seen < cutoff):
                    socketio.emit("room_closed", {"reason": "Room expired."},
                                  room="room:" + game.code)
                    _delete_game(game)
                    changed = True
            for code in list(_rooms):
                if not DriveGame.query.filter_by(code=code).first():
                    _rooms.pop(code, None)
            # Replays outlive the rooms they were driven in, on purpose - a link
            # to one has to keep working - but not for ever, at a couple of
            # hundred kilobytes each. The newest REPLAY_KEEP stay.
            old = (DriveRace.query.order_by(DriveRace.id.desc())
                   .offset(REPLAY_KEEP).all())
            if old:
                for race in old:
                    db.session.delete(race)
                db.session.commit()
            if changed:
                _broadcast_lobbies()

    _run()
    while True:
        eventlet.sleep(5 * 60)
        _run()


eventlet.spawn(_stale_cleanup)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5005)),
                 debug=True)
