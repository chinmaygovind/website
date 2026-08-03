import eventlet
eventlet.monkey_patch()

import os
import re
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
                    DriveGame, DrivePlayer)
import tracks as tracks_mod
import tuning
import runcheck

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

# Car colours, handed out by seat. Chosen to stay apart at a distance and on the
# minimap, since telling cars apart mid-pack is the whole job.
CAR_COLORS = [
    "#e8453c",  # red
    "#3d8bfd",  # blue
    "#f2c94c",  # yellow
    "#27ae60",  # green
    "#bb6bd9",  # purple
    "#f2994a",  # orange
    "#56ccf2",  # cyan
    "#f178b6",  # pink
]

MAX_ROOM = 8

# In-memory per-room locks (single eventlet worker, like ERS/KoT).
_locks = {}


def _lock(code):
    return _locks.setdefault(code, eventlet.semaphore.Semaphore(1))


def _now_ms():
    return int(time.time() * 1000)


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
    u = get_current_user()
    return u.username if u else session.get("guest_name", "Guest")


def require_name(f):
    """Driving alone needs no identity at all; sharing a room needs a name."""
    @wraps(f)
    def wrapped(*a, **kw):
        if not get_current_user() and not session.get("guest_name"):
            return redirect(url_for("login_page", next=request.path))
        return f(*a, **kw)
    return wrapped


def _valid_username(u):
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9_\-]{1,29}$', u))


def _make_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not DriveGame.query.filter_by(code=code).first():
            return code


def _stats(user):
    """The user's DriveStats row, created on first touch."""
    if not user:
        return None
    if user.drive is None:
        user.drive = DriveStats()
        db.session.commit()
    return user.drive


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(),
            "effective_name": get_effective_name(),
            "track_names": {t["slug"]: t["name"] for t in tracks_mod.TRACKS},
            "asset_version": os.environ.get("ASSET_VERSION", "1")}


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
    """{slug: (time_ms, username, set_at)} - the standing record on every track.

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
        out[slug] = (best, holder.user.username if holder and holder.user else "?",
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
        track_json=json_mod.dumps(track, separators=(",", ":")),
        tuning_json=tuning.as_json(), room=None, me_json="null",
        roster_json="[]", name=get_effective_name(), user=user,
        pb_ms=(pb.time_ms if pb else None), next_slug=_next_slug(slug),
        pb_splits=({slug: pb.splits} if pb else {}),
        tracks=tracks_mod.summaries(), cards=_track_cards())


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
                           user=get_current_user(), name=get_effective_name())


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
        track_json=json_mod.dumps(track, separators=(",", ":")),
        tuning_json=tuning.as_json(), room=game,
        me_json=json_mod.dumps(me.to_dict(), separators=(",", ":")),
        roster_json=json_mod.dumps([p.to_dict() for p in game.players], separators=(",", ":")),
        name=get_effective_name(), user=user,
        pb_ms=(pb.time_ms if pb else None), next_slug=_next_slug(track["slug"]),
        pb_splits=({track["slug"]: pb.splits} if pb else {}),
        tracks=tracks_mod.summaries(), cards=_track_cards())


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
    laps = [{"id": r.id, "name": r.user.username if r.user else "?",
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
                           user=get_current_user(), name=get_effective_name())


@app.route("/account")
def account():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page", next="/account"))
    times = (DriveTime.query.filter_by(user_id=user.id)
             .order_by(DriveTime.updated_at.desc()).all())
    starts = _starts_for(user.id, times)
    # A track you have started and never finished has no `drive_times` row, so it
    # would be missing from a table listing those - and it is the one the start
    # count has most to say about. Listed after the times, without one.
    done = {t.track for t in times}
    unfinished = sorted(((slug, n) for slug, n in starts.items() if slug not in done),
                        key=lambda kv: -kv[1])
    # Totalled per track rather than kept in a counter of its own: a track can have
    # starts and no time (never finished) or a time and no starts (driven before
    # the counter existed), and the per-track clamp already knows what to do with
    # both, so summing it cannot disagree with the column underneath.
    return render_template("account.html", user=user, stats=_stats(user),
                           times=times, starts=starts, unfinished=unfinished,
                           total_starts=sum(starts.values()),
                           by_slug=tracks_mod.BY_SLUG,
                           tracks=tracks_mod.summaries(), name=get_effective_name())


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/tracks")
def api_tracks():
    return jsonify({"tracks": tracks_mod.summaries()})


@app.route("/api/track/<slug>")
def api_track(slug):
    track = tracks_mod.get(slug)
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
        row = DriveTime.query.filter_by(track=slug).order_by(DriveTime.time_ms.asc()).first()
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
    return jsonify({"ok": True, "hz": runcheck.ghost_hz(row.ghost),
                    "id": row.id, "time_ms": row.time_ms, "splits": row.splits,
                    "who": (row.user.username if row.user else "?"),
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
    return jsonify({"rows": [{"id": r.id, "name": r.user.username if r.user else "?",
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


def _add_player(game, host=False):
    sk = get_session_key()
    existing = DrivePlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if existing:
        return existing
    user = get_current_user()
    taken = {p.color for p in game.players}
    color = next((c for c in CAR_COLORS if c not in taken),
                 CAR_COLORS[len(game.players) % len(CAR_COLORS)])
    seat = max((p.seat_order for p in game.players), default=-1) + 1
    p = DrivePlayer(game_id=game.id, user_id=(user.id if user else None),
                    session_key=sk, name=(user.username if user else get_effective_name()),
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
    socketio.emit("roster", {"players": [p.to_dict() for p in game.players],
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
# traffic is 20 messages/sec/viewer instead of 20 per car per viewer. None of
# this is ever written to the database.

TICK_HZ = 20
POSE_STALE_MS = 6000
COUNTDOWN_MS = 5000
FINISH_GRACE_MS = 45000

_rooms = {}       # code -> live room state
_sid_room = {}    # socket id -> (code, pid)


def _room(code):
    r = _rooms.get(code)
    if not r:
        r = _rooms[code] = {"code": code, "phase": "free", "cars": {}, "t0": None,
                            "deadline": None, "finish": [], "chat": [],
                            "loop": None, "seq": 0}
    return r


def _car(r, pid):
    return r["cars"].setdefault(pid, {
        "p": [0.0, 0.0, 0.0], "q": [0.0, 0.0, 0.0, 1.0], "v": [0.0, 0.0, 0.0],
        "prog": 0.0, "cp": 0, "flags": 0, "ts": 0, "name": "", "color": "#fff",
        "ms": None, "dnf": False,
    })


def _snapshot(r):
    now = _now_ms()
    cars = {}
    for pid, c in r["cars"].items():
        if now - c["ts"] > POSE_STALE_MS:
            continue
        cars[pid] = [round(c["p"][0], 2), round(c["p"][1], 2), round(c["p"][2], 2),
                     round(c["q"][0], 3), round(c["q"][1], 3), round(c["q"][2], 3), round(c["q"][3], 3),
                     round(c["v"][0], 2), round(c["v"][1], 2), round(c["v"][2], 2),
                     round(c["prog"], 1), c["cp"], c["flags"]]
    return {"t": now, "cars": cars}


def _race_state(r):
    return {"phase": r["phase"], "t0": r["t0"], "deadline": r["deadline"],
            "finish": r["finish"],
            "order": [pid for pid, _ in sorted(r["cars"].items(),
                                               key=lambda kv: -kv[1]["prog"])]}


def _pump(code):
    """Per-room broadcast loop: one merged snapshot per tick while anyone is here."""
    idle = 0
    while True:
        eventlet.sleep(1.0 / TICK_HZ)
        r = _rooms.get(code)
        if not r:
            return
        snap = _snapshot(r)
        if snap["cars"]:
            idle = 0
            socketio.emit("poses", snap, room="room:" + code)
        else:
            idle += 1
            if idle > TICK_HZ * 20:      # nobody has sent a pose in 20s
                r["loop"] = None
                return


def _ensure_pump(code):
    r = _room(code)
    if r["loop"] is None:
        r["loop"] = eventlet.spawn(_pump, code)


@socketio.on("join_lobbies")
def on_join_lobbies():
    join_room("lobbies")
    emit("lobbies_update", _lobbies_payload())


@socketio.on("join_room_")
def on_join_room(data):
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
    c["name"], c["color"], c["ts"] = me.name, me.color, _now_ms()
    _ensure_pump(code)
    game.last_activity_at = datetime.utcnow()
    db.session.commit()
    emit("room_hello", {"track": game.track, "me": me.to_dict(),
                        "players": [p.to_dict() for p in game.players],
                        "race": _race_state(r), "chat": r["chat"][-30:],
                        "server_ms": _now_ms()})
    _broadcast_roster(game)


@socketio.on("clock")
def on_clock(data):
    """Round-trip clock sync so a countdown lands at the same instant for all."""
    emit("clock", {"c": (data or {}).get("c"), "s": _now_ms()})


@socketio.on("pose")
def on_pose(data):
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
    c["ts"] = _now_ms()


@socketio.on("set_track")
def on_set_track(data):
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
        if r["phase"] in ("countdown", "racing"):
            emit("room_error", {"error": "Can't change track mid-race."})
            return
        game.track = slug
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        r["phase"] = "free"
        r["t0"] = r["deadline"] = None
        r["finish"] = []
        for c in r["cars"].values():
            c["ms"], c["dnf"], c["cp"], c["prog"] = None, False, 0, 0.0
    socketio.emit("track_change", {"track": slug}, room="room:" + code)
    _broadcast_lobbies()


@socketio.on("start_race")
def on_start_race(data):
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
        if r["phase"] in ("countdown", "racing"):
            return
        fresh = [pid for pid, c in r["cars"].items()
                 if _now_ms() - c["ts"] < POSE_STALE_MS]
        if len(fresh) < 1:
            emit("room_error", {"error": "Nobody is here to race."})
            return
        r["phase"] = "countdown"
        r["t0"] = _now_ms() + COUNTDOWN_MS
        r["deadline"] = None
        r["finish"] = []
        grid = {}
        for i, pid in enumerate(sorted(fresh, key=lambda x: r["cars"][x]["name"])):
            grid[pid] = i
            c = r["cars"][pid]
            c["ms"], c["dnf"], c["cp"], c["prog"] = None, False, 0, 0.0
        r["grid"] = grid
        game.status = "playing"
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
    socketio.emit("race_start", {"t0": r["t0"], "grid": grid, "track": game.track,
                                 "server_ms": _now_ms()}, room="room:" + code)
    eventlet.spawn_after(COUNTDOWN_MS / 1000.0, _go_green, code)
    _broadcast_lobbies()


def _go_green(code):
    with app.app_context():
        r = _rooms.get(code)
        if not r or r["phase"] != "countdown":
            return
        r["phase"] = "racing"
        socketio.emit("race_green", {"t0": r["t0"]}, room="room:" + code)


@socketio.on("finish")
def on_finish(data):
    """A car crossed the line. First one home starts the clock on everyone else."""
    ent = _sid_room.get(request.sid)
    if not ent:
        return
    code, pid = ent
    with _lock(code):
        r = _rooms.get(code)
        if not r or r["phase"] != "racing":
            return
        c = _car(r, pid)
        if c["ms"] is not None:
            return
        ms = int((data or {}).get("ms") or 0)
        if ms <= 0:
            return
        c["ms"] = ms
        r["finish"].append({"pid": pid, "name": c["name"], "ms": ms,
                            "color": c["color"]})
        r["finish"].sort(key=lambda e: e["ms"])
        if r["deadline"] is None:
            r["deadline"] = _now_ms() + FINISH_GRACE_MS
            eventlet.spawn_after(FINISH_GRACE_MS / 1000.0, _close_race, code, "timeout")
        socketio.emit("race_progress", _race_state(r), room="room:" + code)
        racers = [p for p, cc in r["cars"].items()
                  if _now_ms() - cc["ts"] < POSE_STALE_MS]
        if all(r["cars"][p]["ms"] is not None for p in racers):
            eventlet.spawn_after(0.4, _close_race, code, "all in")


def _close_race(code, why):
    with app.app_context():
        with _lock(code):
            r = _rooms.get(code)
            if not r or r["phase"] != "racing":
                return
            r["phase"] = "results"
            game = DriveGame.query.filter_by(code=code).first()
            standings = list(r["finish"])
            for pid, c in r["cars"].items():
                if c["ms"] is None and _now_ms() - c["ts"] < POSE_STALE_MS:
                    c["dnf"] = True
                    standings.append({"pid": pid, "name": c["name"], "ms": None,
                                      "color": c["color"]})
            elo_delta = {}
            if game:
                elo_delta = _rate_race(game, standings)
                game.add_result({"t": _now_ms(), "track": game.track,
                                 "standings": standings, "why": why})
                game.status = "waiting"
                game.last_activity_at = datetime.utcnow()
                db.session.commit()
            socketio.emit("race_result", {"standings": standings, "why": why,
                                          "elo": elo_delta}, room="room:" + code)
        eventlet.sleep(12)
        r = _rooms.get(code)
        if r and r["phase"] == "results":
            r["phase"] = "free"
            r["t0"] = r["deadline"] = None
            socketio.emit("race_reset", {}, room="room:" + code)
        _broadcast_lobbies()


def _rate_race(game, standings):
    """Pairwise ELO over the finishing order; DNFs sit below every finisher.

    Only rated when at least two logged-in accounts took part - a race against
    guests moves nobody's number.
    """
    by_pid = {p.pid: p for p in game.players}
    rated = [(e, by_pid[e["pid"]]) for e in standings
             if e["pid"] in by_pid and by_pid[e["pid"]].user_id]
    if len(rated) < 2:
        return {}
    K = 32.0
    place = {}
    for i, e in enumerate(standings):
        place[e["pid"]] = i
    ratings = {}
    for e, p in rated:
        st = _stats(p.linked_user)
        ratings[e["pid"]] = st.elo or 1000
    out = {}
    for e, p in rated:
        st = _stats(p.linked_user)
        mine = ratings[e["pid"]]
        delta = 0.0
        n = 0
        for o, _op in rated:
            if o["pid"] == e["pid"]:
                continue
            n += 1
            exp = 1 / (1 + 10 ** ((ratings[o["pid"]] - mine) / 400))
            actual = 1.0 if place[e["pid"]] < place[o["pid"]] else 0.0
            delta += K * (actual - exp)
        if n:
            delta /= n
        st.races = (st.races or 0) + 1
        if place[e["pid"]] == 0:
            st.wins = (st.wins or 0) + 1
        if place[e["pid"]] < 3:
            st.podiums = (st.podiums or 0) + 1
        st.elo = max(100, int(round(mine + delta)))
        out[e["pid"]] = {"before": mine, "after": st.elo, "delta": round(delta)}
    db.session.commit()
    return out


@socketio.on("chat")
def on_chat(data):
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
def on_leave(data):
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
        r["cars"].pop(pid, None)
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
def on_kick(data):
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
            r["cars"].pop(pid, None)
        _broadcast_roster(game)


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
                busy = bool(live and live["cars"])
                if not game.players or (not busy and seen and seen < cutoff):
                    socketio.emit("room_closed", {"reason": "Room expired."},
                                  room="room:" + game.code)
                    _delete_game(game)
                    changed = True
            for code in list(_rooms):
                if not DriveGame.query.filter_by(code=code).first():
                    _rooms.pop(code, None)
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
