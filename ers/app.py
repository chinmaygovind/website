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
                   redirect, url_for, session, send_from_directory)
from flask_socketio import SocketIO, join_room, emit
from sqlalchemy import event
from sqlalchemy.engine import Engine

from models import db, User, ErsStats, ErsGame, ErsPlayer, ErsSlap
import game_logic as gl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Cross-subdomain SSO with Ticket to Ride: same SECRET_KEY + a cookie scoped to
# .cgovind.com means a login on either site is valid on both. Left unset locally
# (host-only cookie on localhost, which is shared across ports anyway).
_cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
if _cookie_domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain
if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

# Share Ticket to Ride's database so accounts are the same. Locally this defaults
# to TTR's dev SQLite file; in prod DATABASE_URL points at the shared file.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    _shared = os.path.join(os.path.dirname(__file__), "..", "ttr", "instance", "tickettoride.db")
    DATABASE_URL = "sqlite:///" + os.path.abspath(_shared)
# Make sure the sqlite directory exists so a first local run doesn't fail.
if DATABASE_URL.startswith("sqlite:///"):
    _path = DATABASE_URL[len("sqlite:///"):]
    if _path and _path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(_path)) or ".", exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    # WAL + a busy timeout let ERS and TTR share one SQLite file safely.
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
    db.create_all()  # creates ers_* tables; never touches the shared users table
    # Idempotent column adds for existing ers_games rows (new tables get them via create_all).
    for _stmt in ["ALTER TABLE ers_games ADD COLUMN events_json TEXT DEFAULT '[]'"]:
        try:
            with db.engine.connect() as _c:
                _c.execute(db.text(_stmt)); _c.commit()
        except Exception:
            pass

# Seat colors (name is shown in the player's color in the slap log).
ERS_COLORS = ["#f2c94c", "#eb5757", "#56ccf2", "#6fcf78", "#bb6bd9",
              "#f2994a", "#2fd4b6", "#f178b6"]

# Bot slap reaction is drawn from Exponential(mean = this many seconds).
BOT_SLAP_MEAN_SEC = 5.0

# In-memory per-game locks + bot scheduling guards (single eventlet worker).
_locks = {}
_sched = {}


def _lock(code):
    return _locks.setdefault(code, eventlet.semaphore.Semaphore(1))


# ---------------------------------------------------------------------------
# Auth helpers (shared with TTR via the users table + session cookie)
# ---------------------------------------------------------------------------

def get_session_key():
    if "session_key" not in session:
        session["session_key"] = str(uuid.uuid4())
    return session["session_key"]


def get_current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def get_effective_name():
    u = get_current_user()
    return u.username if u else session.get("guest_name", "Guest")


def require_login(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not get_current_user() and not session.get("guest_name"):
            return redirect(url_for("login_page"))
        return f(*a, **kw)
    return wrapped


def _valid_username(u):
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9_\-]{1,29}$', u))


def _make_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not ErsGame.query.filter_by(code=code).first():
            return code


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(),
            "effective_name": get_effective_name(),
            "asset_version": os.environ.get("ASSET_VERSION", "1")}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET"])
def login_page():
    if get_current_user() or session.get("guest_name"):
        return redirect(url_for("lobbies"))
    return render_template("login.html")


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
    return redirect(url_for("login_page"))


@app.route("/sw.js")
def service_worker():
    # Served from root so the service worker can control the whole origin.
    resp = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ---------------------------------------------------------------------------
# Lobby routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if get_current_user() or session.get("guest_name"):
        return redirect(url_for("lobbies"))
    return redirect(url_for("login_page"))


@app.route("/lobbies")
@require_login
def lobbies():
    open_games = ErsGame.query.filter_by(status="waiting", is_private=False)\
        .order_by(ErsGame.created_at.desc()).limit(30).all()
    games = [g.to_lobby_dict() for g in open_games if len(g.players) < g.max_players]
    return render_template("lobbies.html", games=games, user=get_current_user(),
                           name=get_effective_name())


def _add_player(game, host=False):
    """Seat the current session in a game (idempotent)."""
    sk = get_session_key()
    existing = ErsPlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if existing:
        return existing
    user = get_current_user()
    seat = len(game.players)
    p = ErsPlayer(
        game_id=game.id, user_id=(user.id if user else None), session_key=sk,
        name=(user.username if user else get_effective_name()),
        color=ERS_COLORS[seat % len(ERS_COLORS)], seat_order=seat, is_host=host,
    )
    db.session.add(p)
    db.session.commit()
    return p


@app.route("/create", methods=["POST"])
@require_login
def create():
    data = request.json or {}
    try:
        max_players = max(2, min(8, int(data.get("max_players", 4))))
    except (TypeError, ValueError):
        max_players = 4
    is_private = bool(data.get("is_private"))
    passcode = (data.get("passcode", "") or "").strip()[:20] or None
    game = ErsGame(code=_make_code(), status="waiting", max_players=max_players,
                   is_private=is_private, passcode=passcode,
                   last_activity_at=datetime.utcnow())
    db.session.add(game)
    db.session.commit()
    _add_player(game, host=True)
    return jsonify({"ok": True, "code": game.code})


@app.route("/join", methods=["POST"])
@require_login
def join():
    data = request.json or {}
    code = (data.get("code", "") or "").strip().upper()
    passcode = (data.get("passcode", "") or "").strip()
    game = ErsGame.query.filter_by(code=code).first()
    if not game:
        return jsonify({"ok": False, "error": "No game with that code."}), 404
    already = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
    if not already:
        if game.status != "waiting":
            return jsonify({"ok": False, "error": "That game has already started."}), 409
        if len(game.players) >= game.max_players:
            return jsonify({"ok": False, "error": "That game is full."}), 409
        if game.is_private and game.passcode and passcode != game.passcode:
            return jsonify({"ok": False, "error": "Wrong passcode."}), 403
        _add_player(game)
    return jsonify({"ok": True, "code": game.code})


@app.route("/lobby/<code>")
@require_login
def lobby(code):
    game = ErsGame.query.filter_by(code=code.upper()).first()
    if not game:
        return redirect(url_for("lobbies"))
    me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
    if not me:
        return redirect(url_for("lobbies"))
    if game.status != "waiting":
        return redirect(url_for("game_page", code=game.code))
    return render_template("lobby.html", game=game, me=me,
                           players=[p.to_dict() for p in game.players],
                           name=get_effective_name())


@app.route("/leaderboard")
@require_login
def leaderboard():
    top = ErsStats.query.join(User).filter(ErsStats.games_played > 0,
                                           User.is_bot.isnot(True))\
        .order_by(ErsStats.elo.desc()).limit(100).all()
    return render_template("leaderboard.html", stats=top, user=get_current_user())


@app.route("/account")
@require_login
def account():
    user = get_current_user()
    stats = user.ers if user else None
    return render_template("account.html", user=user, stats=stats,
                           name=get_effective_name())


@app.route("/game/<code>")
@require_login
def game_page(code):
    game = ErsGame.query.filter_by(code=code.upper()).first()
    if not game:
        return redirect(url_for("lobbies"))
    me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
    if not me:
        return redirect(url_for("lobbies"))
    roster = {p.pid: p.to_dict() for p in game.players}
    return render_template("game.html", game=game, my_pid=me.pid,
                           roster_json=json_mod.dumps(roster),
                           name=get_effective_name())


# ---------------------------------------------------------------------------
# Broadcasting + game helpers
# ---------------------------------------------------------------------------

def _roster(game):
    return {p.pid: p.to_dict() for p in game.players}


def _broadcast(game):
    state = game.state
    socketio.emit("game_state", {"state": gl.public_view(state),
                                 "roster": _roster(game)}, room="game:" + game.code)


def _push_log(state, entry):
    entry["t"] = int(time.time() * 1000)
    state.setdefault("log", []).append(entry)
    state["log"] = state["log"][-60:]


def _pg(state, pid):
    return state.setdefault("pg", {}).setdefault(pid, {
        "turns": 0, "cards_flipped": 0, "cards_won": 0, "piles_won": 0,
        "slaps_won": 0, "false_slaps": 0, "slap_opportunities": 0,
        "reaction_ms_total": 0, "reaction_samples": 0, "fastest_slap_ms": None,
    })


def _name(game, pid):
    p = _roster(game).get(pid, {})
    return p.get("name", pid), p.get("color", "#f2c94c")


def _uid(game, pid):
    for p in game.players:
        if p.pid == pid:
            return p.user_id
    return None


def _log_event(game, ev):
    """Append one entry to the game's full move-by-move replay (events_json)."""
    ev.setdefault("t", int(time.time() * 1000))
    try:
        evs = json_mod.loads(game.events_json or "[]")
    except Exception:
        evs = []
    evs.append(ev)
    game.events_json = json_mod.dumps(evs)


# ---------------------------------------------------------------------------
# Socket handlers
# ---------------------------------------------------------------------------

@socketio.on("join_lobby")
def on_join_lobby(data):
    code = (data or {}).get("code", "").upper()
    join_room("lobby:" + code)
    game = ErsGame.query.filter_by(code=code).first()
    if game:
        emit("lobby_update", {"players": [p.to_dict() for p in game.players],
                              "max_players": game.max_players,
                              "status": game.status})


@socketio.on("join_game")
def on_join_game(data):
    code = (data or {}).get("code", "").upper()
    join_room("game:" + code)
    game = ErsGame.query.filter_by(code=code).first()
    if game and game.status != "waiting":
        emit("game_state", {"state": gl.public_view(game.state), "roster": _roster(game)})


@socketio.on("add_bot")
def on_add_bot(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = ErsGame.query.filter_by(code=code).first()
        if not game or game.status != "waiting":
            return
        me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
        if not me or not me.is_host or len(game.players) >= game.max_players:
            return
        seat = len(game.players)
        bot_names = ["Slappy", "Reflex", "Quickdraw", "Whiskers", "Ace", "Bandit", "Turbo"]
        used = {p.name for p in game.players}
        name = next((n for n in bot_names if n not in used), f"Bot{seat}")
        bot = ErsPlayer(game_id=game.id, user_id=None,
                        session_key=f"bot_{uuid.uuid4().hex[:8]}", name=name,
                        color=ERS_COLORS[seat % len(ERS_COLORS)], seat_order=seat,
                        is_host=False, is_bot=True)
        db.session.add(bot)
        db.session.commit()
        socketio.emit("lobby_update", {"players": [p.to_dict() for p in game.players],
                                       "max_players": game.max_players,
                                       "status": game.status}, room="lobby:" + code)


@socketio.on("start_game")
def on_start_game(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = ErsGame.query.filter_by(code=code).first()
        if not game or game.status != "waiting":
            return
        me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
        if not me or not me.is_host:
            return
        players = sorted(game.players, key=lambda p: p.seat_order)
        if len(players) < 2:
            emit("start_error", {"error": "Need at least 2 players."})
            return
        pids = [p.pid for p in players]
        state = gl.new_deal(pids)
        state["slappable_at"] = None
        state["pg_last_flipper"] = None
        for pid in pids:
            _pg(state, pid)
        game.state = state
        game.status = "playing"
        game.events_json = "[]"
        _log_event(game, {"type": "start", "players": pids,
                          "names": {p.pid: p.name for p in players}})
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        socketio.emit("go_to_game", {"code": code}, room="lobby:" + code)
        _broadcast(game)  # anyone already in the game room sees the dealt table
    # Give players a moment to load the table before bots start acting.
    eventlet.spawn_after(2.5, _kick, code, "start")


@socketio.on("flip")
def on_flip(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = ErsGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
        if not me:
            return
        state = game.state
        if state["current"] != me.pid or state.get("pending_win"):
            return
        _do_flip(game, state, me.pid)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        _broadcast(game)
    _kick(code)


@socketio.on("slap")
def on_slap(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = ErsGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        me = ErsPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
        if not me:
            return
        state = game.state
        changed = _do_slap(game, state, me.pid)
        if changed:
            game.state = state
            game.last_activity_at = datetime.utcnow()
            db.session.commit()
            _broadcast(game)
    _kick(code)


# ---------------------------------------------------------------------------
# Applying engine actions + recording per-game stats / the slap feed
# ---------------------------------------------------------------------------

def _do_flip(game, state, pid):
    events = gl.flip(state, pid)
    for ev in events:
        if ev["type"] == "flip":
            pg = _pg(state, ev["pid"])
            pg["cards_flipped"] += 1
            if state.get("pg_last_flipper") != ev["pid"]:
                pg["turns"] += 1
                state["pg_last_flipper"] = ev["pid"]
            _log_event(game, {"type": "flip", "pid": ev["pid"], "card": ev["card"]})
    # Reaction clock + slap-opportunity credit key off the resulting pile.
    reasons = gl.slap_reasons(state["pile"], state["rules"])
    if reasons:
        state["slappable_at"] = time.time()
        for other in state["players"]:
            if other not in state["eliminated"]:
                _pg(state, other)["slap_opportunities"] += 1
    else:
        state["slappable_at"] = None
    _record_wins(game, state, events)
    return events


def _do_slap(game, state, pid):
    reasons = gl.slap_reasons(state["pile"], state["rules"])
    now = time.time()
    events = gl.slap(state, pid, state["rules"])
    if not events:
        return False
    won_count = next((e["count"] for e in events if e["type"] == "win_pile"), 0)
    name, color = _name(game, pid)
    for ev in events:
        if ev["type"] == "slap_win":
            reaction = None
            if state.get("slappable_at"):
                reaction = max(0, int((now - state["slappable_at"]) * 1000))
            pg = _pg(state, pid)
            pg["slaps_won"] += 1
            if reaction is not None:
                pg["reaction_ms_total"] += reaction
                pg["reaction_samples"] += 1
                if pg["fastest_slap_ms"] is None or reaction < pg["fastest_slap_ms"]:
                    pg["fastest_slap_ms"] = reaction
            _push_log(state, {"kind": "slap", "name": name, "color": color,
                              "reaction_ms": reaction, "reasons": ev["reasons"]})
            _log_event(game, {"type": "slap", "pid": pid, "valid": True,
                              "reasons": ev["reasons"], "reaction_ms": reaction,
                              "cards": won_count})
            db.session.add(ErsSlap(game_code=game.code, user_id=_uid(game, pid), pid=pid,
                                   name=name, valid=True, reasons=",".join(ev["reasons"]),
                                   reaction_ms=reaction, cards=won_count))
            state["slappable_at"] = None
        elif ev["type"] == "false_slap":
            _pg(state, pid)["false_slaps"] += 1
            _push_log(state, {"kind": "false", "name": name, "color": color,
                              "burned": ev.get("burned", 0)})
            _log_event(game, {"type": "slap", "pid": pid, "valid": False,
                              "burned": ev.get("burned", 0)})
            db.session.add(ErsSlap(game_code=game.code, user_id=_uid(game, pid), pid=pid,
                                   name=name, valid=False, reasons="", reaction_ms=None,
                                   cards=0))
    _record_wins(game, state, events)
    return True


def _record_wins(game, state, events):
    """Attach card gains + the '+N cards' log line + elimination notes."""
    for ev in events:
        if ev["type"] == "win_pile":
            pg = _pg(state, ev["pid"])
            pg["cards_won"] += ev["count"]
            pg["piles_won"] += 1
            name, color = _name(game, ev["pid"])
            # Update the most recent slap line with the pile size, else log a pile win.
            if state.get("log") and state["log"][-1].get("kind") == "slap":
                state["log"][-1]["cards"] = ev["count"]
            else:
                _push_log(state, {"kind": "pile", "name": name, "color": color,
                                  "cards": ev["count"]})
            _log_event(game, {"type": "win", "pid": ev["pid"], "count": ev["count"]})
        elif ev["type"] == "eliminated":
            name, color = _name(game, ev["pid"])
            _push_log(state, {"kind": "out", "name": name, "color": color,
                              "place": ev["place"], "turns_lasted": ev["turns_lasted"]})
            _log_event(game, {"type": "out", "pid": ev["pid"], "place": ev["place"],
                              "turns_lasted": ev["turns_lasted"]})
    if state["phase"] == "ended":
        _log_event(game, {"type": "end", "winner": state.get("winner")})
        _finalize(game, state)


# ---------------------------------------------------------------------------
# Bot orchestration (server-authoritative; bots never false-slap)
# ---------------------------------------------------------------------------

def _bot_pids(game):
    return {p.pid for p in game.players if p.is_bot}


def _kick(code, why=None):
    """Schedule the next bot action(s) for the game's current state.

    Establishes its own app context so it is safe to call from a bare greenlet
    (bot callbacks) as well as from a socket handler.
    """
    with app.app_context():
        with _lock(code):
            game = ErsGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if state["phase"] == "ended":
                return
            bots = _bot_pids(game)
            seq = state["seq"]
            sched = _sched.setdefault(code, {})

            if state.get("pending_win") and sched.get("grace") != seq:
                sched["grace"] = seq
                eventlet.spawn_after(gl.TRIBUTE_GRACE_SECONDS, _bot_grace, code, seq)

            cur = state["current"]
            if cur in bots and not state.get("pending_win") and sched.get("flip") != seq:
                sched["flip"] = seq
                delay = 0.9 if why == "start" else random.uniform(0.55, 1.1)
                eventlet.spawn_after(delay, _bot_flip, code, seq, cur)

            if gl.slap_reasons(state["pile"], state["rules"]) and sched.get("slap") != seq:
                sched["slap"] = seq
                for bp in bots:
                    if bp in state["eliminated"] or bp in state["slap_locked"]:
                        continue
                    # Reaction ~ Exponential(mean 5s). Slow on purpose: by the time most
                    # of these fire the pile has usually moved on, so _bot_slap re-checks
                    # and skips - bots only catch a slappable pile that lingers. Beatable.
                    eventlet.spawn_after(random.expovariate(1 / BOT_SLAP_MEAN_SEC), _bot_slap, code, seq, bp)


def _bot_flip(code, seq, pid):
    with app.app_context():
        with _lock(code):
            game = ErsGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if state["phase"] != "playing" or state.get("pending_win"):
                return
            if state["current"] != pid:
                return
            _do_flip(game, state, pid)
            game.state = state
            game.last_activity_at = datetime.utcnow()
            db.session.commit()
            _broadcast(game)
    _kick(code)


def _bot_slap(code, seq, pid):
    with app.app_context():
        with _lock(code):
            game = ErsGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if state["phase"] != "playing":
                return
            if pid in state["eliminated"] or pid in state["slap_locked"]:
                return
            if not gl.slap_reasons(state["pile"], state["rules"]):
                return          # no longer slappable; bot never false-slaps
            _do_slap(game, state, pid)
            game.state = state
            game.last_activity_at = datetime.utcnow()
            db.session.commit()
            _broadcast(game)
    _kick(code)


def _bot_grace(code, seq):
    with app.app_context():
        with _lock(code):
            game = ErsGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if not state.get("pending_win"):
                return
            events = gl.resolve_pending(state)
            _record_wins(game, state, events)
            game.state = state
            game.last_activity_at = datetime.utcnow()
            db.session.commit()
            _broadcast(game)
    _kick(code)


# ---------------------------------------------------------------------------
# Game finalize: flush per-game stats + ELO into ers_stats
# ---------------------------------------------------------------------------

def _finalize(game, state):
    if game.status == "ended":
        return
    game.status = "ended"

    places = {s["pid"]: s["place"] for s in state.get("standings", [])}
    # Map real (linked, non-bot) players to their user + place.
    real = {}
    for p in game.players:
        if p.user_id and not p.is_bot:
            real[p.pid] = p.user_id
    ratings = {pid: (User.query.get(uid).ers.elo if User.query.get(uid).ers else 1000)
               for pid, uid in real.items()}

    for pid, uid in real.items():
        user = User.query.get(uid)
        st = user._ensure_stats()
        pg = state.get("pg", {}).get(pid, {})
        place = places.get(pid)

        # Pairwise ELO vs the other real players by finishing place (1 = best).
        my_elo = st.elo or 1000
        K = 32 if (st.games_played or 0) < 10 else 16
        opps = [o for o in real if o != pid]
        delta = 0.0
        for o in opps:
            exp = 1 / (1 + 10 ** ((ratings[o] - my_elo) / 400))
            if place is not None and places.get(o) is not None:
                actual = 1.0 if place < places[o] else (0.5 if place == places[o] else 0.0)
            else:
                actual = 0.5
            delta += K * (actual - exp)
        if opps:
            delta /= len(opps)

        st.elo = max(100, my_elo + round(delta))
        st.games_played = (st.games_played or 0) + 1
        if place == 1:
            st.games_won = (st.games_won or 0) + 1
        st.turns_played = (st.turns_played or 0) + pg.get("turns", 0)
        st.cards_flipped = (st.cards_flipped or 0) + pg.get("cards_flipped", 0)
        st.cards_won = (st.cards_won or 0) + pg.get("cards_won", 0)
        st.piles_won = (st.piles_won or 0) + pg.get("piles_won", 0)
        st.slaps_won = (st.slaps_won or 0) + pg.get("slaps_won", 0)
        st.false_slaps = (st.false_slaps or 0) + pg.get("false_slaps", 0)
        st.slap_opportunities = (st.slap_opportunities or 0) + pg.get("slap_opportunities", 0)
        st.reaction_ms_total = (st.reaction_ms_total or 0) + pg.get("reaction_ms_total", 0)
        st.reaction_samples = (st.reaction_samples or 0) + pg.get("reaction_samples", 0)
        fs = pg.get("fastest_slap_ms")
        if fs is not None and (st.fastest_slap_ms is None or fs < st.fastest_slap_ms):
            st.fastest_slap_ms = fs
        if place is not None and (st.best_place is None or place < st.best_place):
            st.best_place = place

    db.session.add(game)
    db.session.commit()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5003)), debug=True)
