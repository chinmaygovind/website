import eventlet
eventlet.monkey_patch()

import os
import re
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
from sqlalchemy import event, func
from sqlalchemy.engine import Engine

from models import (db, User, DriveStats, DriveTime, DriveStart,
                    DriveGame, DrivePlayer, DriveRace, DriveGarage)
import tracks as tracks_mod
import tuning
import runcheck
import visits
import garage as garage_mod
# The palette and the hash moved into `garage.py`, with the rest of what a car
# is allowed to look like. Imported by name here because five routes call it.
from garage import color_for

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

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    _shared = os.path.join(os.path.dirname(__file__), "..", "ttr", "instance", "tickettoride.db")
    DATABASE_URL = "sqlite:///" + os.path.abspath(_shared)
if DATABASE_URL.startswith("sqlite:///"):
    _path = DATABASE_URL[len("sqlite:///"):]
    if _path and _path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(_path)) or ".", exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
    except Exception:
        pass


db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

with app.app_context():
    db.create_all()  # creates drive_* tables; never touches the shared users table

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


def _earned_for(user, row=None, holders=None):
    """What this account has earned, writing down the losable ones if they are new.

    Most gates are counters that only go up and are recomputed every time. The
    ones in `garage.KEPT` are records *held right now* - a record can be taken off
    you and the badge for it cannot - so the moment one is true it has to be
    persisted or it would be lost the next time somebody beats the lap. Doing it
    here rather than in a tool is also why no backfill is needed: every current
    record holder earns theirs the first time anything asks.
    """
    if not user:
        return set()
    row = row if row is not None else _garage_row(user)
    already = row.earned if row else set()
    got = garage_mod.earned(user, already, holders)
    keep = got & garage_mod.KEPT
    if keep - already:
        row = row or _garage_row(user, create=True)
        row.earned_json = json_mod.dumps(sorted(already | keep))
        row.updated_at = datetime.utcnow()
        db.session.commit()
    return got


def _livery_for(user, holders=None, name=None):
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
    got = _earned_for(user, row, holders)
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


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(),
            "effective_name": get_effective_name(),
            "track_names": {t["slug"]: t["name"] for t in tracks_mod.TRACKS},
            # Where the flag art lives. It is one copy on the main site
            # rather than four, so a game refers to it by absolute URL - see
            # `UserProfile.flag_path`, which returns the path half.
            "site_url": MAIN_SITE_URL,
            # What the heartbeat in base.html says about this page. Derived
            # from the endpoint rather than passed by each route, so a new page
            # gets a sensible answer without anybody remembering to add one -
            # and the play page overrides it in JS, because there the track can
            # change under the page with no navigation at all.
            "presence_where": PRESENCE_BY_ENDPOINT.get(request.endpoint or "", "home"),
            "asset_version": os.environ.get("ASSET_VERSION", "1")}


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


@app.route("/guest", methods=["POST"])
def guest_login():
    data = request.json or {}
    name = (data.get("name", "") or "").strip()[:20]
    if not name:
        return jsonify({"ok": False, "error": "Enter a name."}), 400
    session.permanent = True
    session["guest_name"] = name
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("guest_name", None)
    return redirect(url_for("index"))


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
    """
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
    """Every driver's Time Trial Score: their placing on each track, added up.

    Golf scoring, so **low is good** and a clean sweep of the pool is 12. Ten
    firsts and two thirds is 16.

    Three rules make that sum well defined:

    - **A tie shares a place**, which is the answer `_my_rank_map` already gives
      for one track: a placing is the number of strictly faster laps plus one.
    - **A track you have never driven scores one worse than last on it** - the
      place you would take by turning up and being slowest. Adding up only the
      tracks somebody *has* driven would make driving fewer of them the way to a
      better score, which is the opposite of what a board is for: one lonely
      first place would beat a full sweep. A track *nobody* has driven is worth
      1 to everybody by the same rule, which cannot reorder anyone. The
      `driven` column is what keeps a big score from being a mystery.
    - **It is worked out here, on the way to the screen, and stored nowhere.** A
      personal best does not only change *your* score, it demotes everybody you
      overtook, so a number kept per driver would have to rewrite most of the
      board on every lap and would be wrong for as long as one write path was
      missed. Derived from `drive_times` on each render it cannot go stale, and
      the pool is twelve tracks.

    Only laps driven alone against the clock are in `drive_times` at all (see
    `countsForTheBoard` in game.js), so nothing set in a room reaches this
    board either.
    """
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
              "best": _ordinal(min(mine.values()))}
             for uid, mine in places.items()]

    # The score is the order. Everything after it in the key only decides who
    # comes first *inside* a tie, which the shared position below then hides.
    board.sort(key=lambda r: (r["score"], -r["driven"], r["user"].display.lower()))
    for i, r in enumerate(board):
        r["pos"] = (board[i - 1]["pos"] if i and r["score"] == board[i - 1]["score"]
                    else i + 1)
    return board


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
    ver = os.environ.get("ASSET_VERSION", "1")
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


def _play_solo(slug):
    track = tracks_mod.get(slug)
    _remember_track(slug)
    user = get_current_user()
    pb = DriveTime.query.filter_by(user_id=user.id, track=slug).first() if user else None
    return render_template(
        "play.html", mode="solo", track=track,
        track_json=json_mod.dumps(_track_payload(track["slug"]),
                                  separators=(",", ":")),
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
        car_livery=json_mod.dumps(_car_livery(user), separators=(",", ":")),
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
                           garage_json=json_mod.dumps(data, separators=(",", ":")),
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
        track_json=json_mod.dumps(_track_payload(track["slug"]),
                                  separators=(",", ":")),
        tuning_json=tuning.as_json(), room=game,
        me_json=json_mod.dumps(me.to_dict(_livery_for(me.linked_user,
                                                     name=me.name)),
                               separators=(",", ":")),
        roster_json=json_mod.dumps(_roster(game.players), separators=(",", ":")),
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
        car_livery=json_mod.dumps(_car_livery(user), separators=(",", ":")),
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
        track_json=json_mod.dumps(_track_payload(track["slug"]),
                                  separators=(",", ":")),
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
        car_livery=json_mod.dumps(_car_livery(user), separators=(",", ":")),
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
    # Totalled per track rather than kept in a counter of its own: a track can have
    # starts and no time (never finished) or a time and no starts (driven before
    # the counter existed), and the per-track clamp already knows what to do with
    # both, so summing it cannot disagree with the column underneath.
    return render_template("account.html", user=user, is_me=is_me,
                           stats=_stats(user, create=is_me),
                           times=times, starts=starts, rows=rows,
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

    if not user:
        return jsonify({"ok": True, "stored": False, "medal": medal,
                        "guest": True, "rank": None, "run_rank": _run_rank(),
                        "record_ms": best.time_ms if best else None,
                        "note": "Kept on this device - log in and it goes on the board."})

    st = _stats(user)
    st.runs = (st.runs or 0) + 1
    st.drive_time = (st.drive_time or 0.0) + time_ms / 1000.0
    st.distance = (st.distance or 0.0) + runcheck.clamp_distance(track, data.get("distance"))

    run_rank = _run_rank(exclude_user_id=user.id)
    row = DriveTime.query.filter_by(user_id=user.id, track=track["slug"]).first()
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
            db.session.delete(p)
            db.session.commit()
            remaining = sorted(g.players, key=lambda q: q.seat_order)
            if not remaining:
                _delete_game(g)
            else:
                if p.is_host and not any(q.is_host for q in remaining):
                    remaining[0].is_host = True
                    db.session.commit()
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


def _roster(players):
    """Every seat with its livery, working the record holders out once.

    The one place a roster is built, so the gate check cannot be applied on
    three paths and forgotten on the fourth.
    """
    holders = garage_mod.records_held()
    return [pl.to_dict(_livery_for(pl.linked_user, holders, pl.name))
            for pl in players]


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
            return jsonify({"ok": False, "error": "That room is full."}), 409
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
    socketio.emit("roster", {"players": _roster(game.players),
                             "track": game.track},
                  room="room:" + game.code)
    _broadcast_lobbies()


def _delete_game(game):
    for p in list(game.players):
        db.session.delete(p)
    _rooms.pop(game.code, None)
    _locks.pop(game.code, None)
    db.session.delete(game)
    db.session.commit()


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
QUAL_MS = 90000
COUNTDOWN_MS = 5000
FINISH_GRACE_MS = 45000
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
ROOM_DEFAULTS = {"qualifying": True}

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
                            # Every car's poses through the race being driven,
                            # written out as a DriveRace when it ends.
                            "rec": None,
                            "races_run": 0,
                            # Bumped by every race so a timer armed for one race
                            # can never close the next one.
                            "race_seq": 0, "hard_end": None,
                            "settings": dict(ROOM_DEFAULTS)}
    return r


def _car(r, pid):
    return r["cars"].setdefault(pid, {
        "p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0], "v": [0.0, 0.0, 0.0],
        "prog": 0.0, "cp": 0, "flags": 0, "sl": 0.0, "ts": 0, "name": "", "color": "#fff",
        "ms": None, "dnf": False, "gone": False,
    })


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
    about. Both of the trailing fields are appended rather than inserted and the
    client guards on the array's length, so a page left open across a deploy
    degrades to no tow rather than to a car in the wrong place.
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
                     round(c.get("sl", 0.0), 2)]
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
    """Per-room broadcast loop: one merged snapshot per tick while anyone is here."""
    idle = 0
    while True:
        eventlet.sleep(1.0 / TICK_HZ)
        r = _rooms.get(code)
        if not r:
            return
        snap = _snapshot(r)
        _record_race(r)
        if snap["cars"]:
            idle = 0
            socketio.emit("poses", snap, room="room:" + code)
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
    livery_by_pid = {pl.pid: _livery_for(pl.linked_user, holders, pl.name)
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
    _ensure_pump(code)
    game.last_activity_at = datetime.utcnow()
    db.session.commit()
    emit("room_hello", {"track": game.track,
                        "me": seat,
                        "players": _roster(game.players),
                        "race": _race_state(r), "chat": r["chat"][-30:],
                        "settings": dict(r["settings"]),
                        "server_ms": _now_ms()})
    _broadcast_roster(game)


@socketio.on("clock")
def on_clock(data=None):
    """Round-trip clock sync so a countdown lands at the same instant for all."""
    emit("clock", {"c": (data or {}).get("c"), "s": _now_ms()})


@socketio.on("pose")
def on_pose(data=None):
    """A car's own report of where it is. Client-authoritative by design."""
    ent = _sid_room.get(request.sid)
    if not ent or not data:
        return
    code, pid = ent
    r = _rooms.get(code)
    if not r:
        return
    c = _car(r, pid)
    p, q, v = data.get("p"), data.get("q"), data.get("v")
    if isinstance(p, list) and len(p) == 3:
        c["p"] = [float(x) for x in p]
    if isinstance(q, list) and len(q) == 4:
        c["q"] = [float(x) for x in q]
    if isinstance(v, list) and len(v) == 3:
        c["v"] = [float(x) for x in v]
    c["prog"] = float(data.get("prog") or 0.0)
    c["cp"] = int(data.get("cp") or 0)
    c["flags"] = int(data.get("flags") or 0)
    # How full the tow is. Clamped rather than trusted: it is fanned straight
    # back out to everybody else, and it is the loudness of an effect on their
    # screens, so a client sending 400 would be a car in a permanent boost.
    c["sl"] = min(1.0, max(0.0, float(data.get("sl") or 0.0)))
    c["ts"] = _now_ms()


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
        _reset_race(r)
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


def _reset_race(r):
    """Put the room back to free practice with nothing left over.

    `last_order` and `settings` deliberately survive: one is the result of the
    race that just happened and is the next grid, the other is what the host
    has said about the room.
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
            continue
        c["ms"], c["dnf"], c["cp"], c["prog"] = None, False, 0, 0.0


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
    quali = bool(r["settings"].get("qualifying", True))
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
    if r["qual"].get(pid) is not None and ms >= r["qual"][pid]:
        return
    r["qual"][pid] = ms
    socketio.emit("qual_progress", {"qual": _qual_state(r)}, room="room:" + code)
    frames = (data or {}).get("ghost")
    if not _sane_frames(frames):
        return
    if r["pole"] and r["pole"]["ms"] <= ms:
        return                   # quick, but not quick enough to be the ghost
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
    cp = int((data or {}).get("cp") or 0)
    ms = int((data or {}).get("ms") or 0)
    if cp <= 0 or ms <= 0:
        return
    mine = r["splits"].setdefault(pid, {})
    if cp in mine:
        return              # a checkpoint is passed once; a second is a replay
    mine[cp] = ms
    socketio.emit("race_split", {"pid": pid, "cp": cp, "ms": ms},
                  room="room:" + code)


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
            elo_delta = {}
            race_id = None
            if game:
                elo_delta = _rate_race(game, standings)
                race_id = _store_replay(r, game, standings, why)
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
                                          "elo": elo_delta, "race": race_id},
                          room="room:" + code)
        eventlet.sleep(12)
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "results" or r["race_seq"] != closed_seq:
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


def _rate_race(game, standings):
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
    """
    by_pid = {p.pid: p for p in game.players}
    rated = [e for e in standings
             if e["pid"] in by_pid and by_pid[e["pid"]].user_id]
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
        if not remaining:
            socketio.emit("room_closed", {"reason": "Everyone left."},
                          room="room:" + code)
            _delete_game(game)
            _broadcast_lobbies()
            return
        if was_host and not any(p.is_host for p in remaining):
            remaining[0].is_host = True
            db.session.commit()
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
                busy = bool(live and _live(live))
                if not game.players or (not busy and seen and seen < cutoff):
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
