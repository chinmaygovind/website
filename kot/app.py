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

from models import db, User, KotStats, KotGame, KotPlayer
import game_logic as gl

# ---------------------------------------------------------------------------
# Config (mirrors ERS: shared accounts + cross-subdomain SSO)
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
    db.create_all()  # creates kot_* tables; never touches the shared users table
    for _stmt in ["ALTER TABLE kot_games ADD COLUMN events_json TEXT DEFAULT '[]'"]:
        try:
            with db.engine.connect() as _c:
                _c.execute(db.text(_stmt)); _c.commit()
        except Exception:
            pass

# Each seat is a King of Tokyo monster (name + signature colour).
MONSTERS = [
    ("Gigazaur", "#6fcf78"),
    ("The King", "#f2994a"),
    ("Cyber Bunny", "#f178b6"),
    ("Kraken", "#56ccf2"),
    ("Meka Dragon", "#eb5757"),
    ("Alienoid", "#bb6bd9"),
]

# In-memory per-game locks (single eventlet worker, like ERS).
_locks = {}


def _lock(code):
    return _locks.setdefault(code, eventlet.semaphore.Semaphore(1))


# ---------------------------------------------------------------------------
# Auth helpers (shared with TTR/ERS via the users table + session cookie)
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
        if not KotGame.query.filter_by(code=code).first():
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
    resp = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ---------------------------------------------------------------------------
# One-game-at-once helpers
# ---------------------------------------------------------------------------

def _my_players(sk):
    """Every seat this session holds in a non-ended game."""
    return (KotPlayer.query.join(KotGame, KotPlayer.game_id == KotGame.id)
            .filter(KotPlayer.session_key == sk, KotGame.status != "ended").all())


def _active_playing_game(sk, exclude_code=None):
    for p in _my_players(sk):
        if p.game.status == "playing" and p.game.code != exclude_code:
            return p.game
    return None


def _leave_waiting_lobbies(sk, keep_code=None):
    """Pull this session out of any *waiting* lobby except keep_code, reaping empties."""
    for p in list(_my_players(sk)):
        g = p.game
        if g.status == "waiting" and g.code != keep_code:
            was_host = p.is_host
            db.session.delete(p)
            db.session.commit()
            remaining = sorted(g.players, key=lambda q: q.seat_order)
            if not remaining:
                socketio.emit("lobby_closed", {"reason": "Host left."}, room="lobby:" + g.code)
                _delete_game(g)
            else:
                if was_host and not any(q.is_host for q in remaining):
                    remaining[0].is_host = True
                    db.session.commit()
                _broadcast_lobby(g)


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
    payload = _lobbies_payload()
    # Surface the game this session is already in so they can hop back.
    mine = None
    for p in _my_players(get_session_key()):
        mine = {"code": p.game.code, "status": p.game.status}
        break
    return render_template("lobbies.html", games=payload["games"], live=payload["live"],
                           user=get_current_user(), name=get_effective_name(), mine=mine)


def _add_player(game, host=False):
    """Seat the current session in a game (idempotent)."""
    sk = get_session_key()
    existing = KotPlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if existing:
        return existing
    user = get_current_user()
    seat = len(game.players)
    monster, color = MONSTERS[seat % len(MONSTERS)]
    p = KotPlayer(
        game_id=game.id, user_id=(user.id if user else None), session_key=sk,
        name=(user.username if user else get_effective_name()),
        color=color, monster=monster, seat_order=seat, is_host=host,
    )
    db.session.add(p)
    db.session.commit()
    return p


@app.route("/create", methods=["POST"])
@require_login
def create():
    data = request.json or {}
    sk = get_session_key()
    live = _active_playing_game(sk)
    if live:
        return jsonify({"ok": False, "error": "You're still in a live game. Leave it first.",
                        "code": live.code}), 409
    max_players = 6   # always the max; there's no lobby-size setting to choose
    is_private = bool(data.get("is_private"))
    passcode = (data.get("passcode", "") or "").strip()[:20] or None
    _leave_waiting_lobbies(sk)
    game = KotGame(code=_make_code(), status="waiting", max_players=max_players,
                   is_private=is_private, passcode=passcode,
                   last_activity_at=datetime.utcnow())
    db.session.add(game)
    db.session.commit()
    _add_player(game, host=True)
    _broadcast_lobbies()
    return jsonify({"ok": True, "code": game.code})


@app.route("/join", methods=["POST"])
@require_login
def join():
    data = request.json or {}
    code = (data.get("code", "") or "").strip().upper()
    passcode = (data.get("passcode", "") or "").strip()
    sk = get_session_key()
    game = KotGame.query.filter_by(code=code).first()
    if not game:
        return jsonify({"ok": False, "error": "No game with that code."}), 404
    already = KotPlayer.query.filter_by(game_id=game.id, session_key=sk).first()
    if not already:
        live = _active_playing_game(sk, exclude_code=code)
        if live:
            return jsonify({"ok": False, "error": "You're still in a live game. Leave it first.",
                            "code": live.code}), 409
        if game.status != "waiting":
            return jsonify({"ok": False, "error": "That game has already started - you can watch it."}), 409
        if len(game.players) >= game.max_players:
            return jsonify({"ok": False, "error": "That game is full."}), 409
        if game.is_private and game.passcode and passcode != game.passcode:
            return jsonify({"ok": False, "error": "Wrong passcode."}), 403
        _leave_waiting_lobbies(sk)
        _add_player(game)
        _broadcast_lobbies()
    return jsonify({"ok": True, "code": game.code})


@app.route("/lobby/<code>")
@require_login
def lobby(code):
    game = KotGame.query.filter_by(code=code.upper()).first()
    if not game:
        return redirect(url_for("lobbies"))
    me = KotPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
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
    top = KotStats.query.join(User).filter(KotStats.games_played > 0,
                                           User.is_bot.isnot(True))\
        .order_by(KotStats.elo.desc()).limit(100).all()
    return render_template("leaderboard.html", stats=top, user=get_current_user())


@app.route("/account")
@require_login
def account():
    user = get_current_user()
    stats = user.kot if user else None
    return render_template("account.html", user=user, stats=stats,
                           name=get_effective_name())


@app.route("/game/<code>")
@require_login
def game_page(code):
    game = KotGame.query.filter_by(code=code.upper()).first()
    if not game:
        return redirect(url_for("lobbies"))
    me = KotPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()
    if not me and game.status == "waiting":
        return redirect(url_for("lobbies"))   # nothing to spectate before the start
    roster = {p.pid: p.to_dict() for p in game.players}
    return render_template("game.html", game=game, my_pid=(me.pid if me else ""),
                           roster_json=json_mod.dumps(roster),
                           name=get_effective_name())


# ---------------------------------------------------------------------------
# Broadcasting + reaping
# ---------------------------------------------------------------------------

def _roster(game):
    return {p.pid: p.to_dict() for p in game.players}


def _names(game):
    return {p.pid: p.name for p in game.players}


def _broadcast(game):
    state = game.state
    socketio.emit("game_state", {"state": gl.public_view(state),
                                 "roster": _roster(game)}, room="game:" + game.code)


def _broadcast_lobby(game):
    socketio.emit("lobby_update", {"players": [p.to_dict() for p in game.players],
                                   "max_players": game.max_players,
                                   "status": game.status}, room="lobby:" + game.code)


def _lobbies_payload():
    open_games = KotGame.query.filter_by(status="waiting", is_private=False)\
        .order_by(KotGame.created_at.desc()).limit(30).all()
    games = [g.to_lobby_dict() for g in open_games if len(g.players) < g.max_players]
    live_games = KotGame.query.filter_by(status="playing", is_private=False)\
        .order_by(KotGame.last_activity_at.desc()).limit(20).all()
    live = [g.to_lobby_dict() for g in live_games]
    return {"games": games, "live": live}


def _broadcast_lobbies():
    """Push the open/live game lists to anyone sitting on /lobbies, so a new
    game (or one filling up, starting, or ending) shows up without a reload."""
    socketio.emit("lobbies_update", _lobbies_payload(), room="lobbies")


def _delete_game(game):
    for p in list(game.players):
        db.session.delete(p)
    db.session.delete(game)
    db.session.commit()


def _player_elo(p):
    if p.linked_user and p.linked_user.kot:
        return p.linked_user.kot.elo or 1000
    return 1000


def _me(game):
    return KotPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()


def _log_event(game, ev):
    ev.setdefault("t", int(time.time() * 1000))
    try:
        evs = json_mod.loads(game.events_json or "[]")
    except Exception:
        evs = []
    evs.append(ev)
    game.events_json = json_mod.dumps(evs)


# ---------------------------------------------------------------------------
# Socket handlers - lobby
# ---------------------------------------------------------------------------

@socketio.on("join_lobby")
def on_join_lobby(data):
    code = (data or {}).get("code", "").upper()
    join_room("lobby:" + code)
    game = KotGame.query.filter_by(code=code).first()
    if game:
        _broadcast_lobby(game)


@socketio.on("join_lobbies")
def on_join_lobbies():
    """The /lobbies page joins this room so it gets a fresh open/live game
    list pushed to it whenever anything changes, instead of needing a reload."""
    join_room("lobbies")


@socketio.on("join_game")
def on_join_game(data):
    code = (data or {}).get("code", "").upper()
    join_room("game:" + code)
    game = KotGame.query.filter_by(code=code).first()
    if game and game.status != "waiting":
        emit("game_state", {"state": gl.public_view(game.state), "roster": _roster(game)})


@socketio.on("kick_player")
def on_kick_player(data):
    code = (data or {}).get("code", "").upper()
    pid = (data or {}).get("pid")
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "waiting":
            return
        me = _me(game)
        if not me or not me.is_host:
            return
        target = next((p for p in game.players if p.pid == pid), None)
        if not target or target.is_host:
            return
        socketio.emit("player_kicked", {"pid": pid}, room="lobby:" + code)
        db.session.delete(target)
        db.session.commit()
        _broadcast_lobby(game)
        _broadcast_lobbies()


@socketio.on("leave_lobby")
def on_leave_lobby(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game:
            return
        me = _me(game)
        if not me:
            return
        was_host = me.is_host
        db.session.delete(me)
        db.session.commit()
        remaining = sorted(game.players, key=lambda p: p.seat_order)
        if not remaining:
            socketio.emit("lobby_closed", {"reason": "Everyone left the lobby."},
                          room="lobby:" + code)
            _delete_game(game)
            _broadcast_lobbies()
            return
        if was_host and not any(p.is_host for p in remaining):
            remaining[0].is_host = True
            db.session.commit()
        _broadcast_lobby(game)
        _broadcast_lobbies()


@socketio.on("start_game")
def on_start_game(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "waiting":
            return
        me = _me(game)
        if not me or not me.is_host:
            return
        players = sorted(game.players, key=lambda p: p.seat_order)
        if len(players) < 2:
            emit("start_error", {"error": "Need at least 2 monsters to start."})
            return
        pids = [p.pid for p in players]
        state = gl.new_game(pids)
        gl.set_names(state, {p.pid: p.name for p in players})
        game.state = state
        game.status = "playing"
        game.events_json = "[]"
        _log_event(game, {"type": "start", "players": pids,
                          "names": {p.pid: p.name for p in players}})
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        socketio.emit("go_to_game", {"code": code}, room="lobby:" + code)
        _broadcast(game)
        _broadcast_lobbies()


# ---------------------------------------------------------------------------
# Socket handlers - gameplay
# ---------------------------------------------------------------------------

def _act(code, fn, must_be_current=True):
    """Load the game, verify the caller controls a seat, run fn(game, state, pid),
    then persist + broadcast + finalize. Returns the acting pid or None."""
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        me = _me(game)
        if not me:
            return
        state = game.state
        gl.set_names(state, _names(game))
        if state["phase"] == "ended":
            return
        if must_be_current and state["current"] != me.pid:
            return
        fn(game, state, me.pid)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)


@socketio.on("roll")
def on_roll(data):
    keep = (data or {}).get("keep", [])
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.do_roll(s, pid, keep))


@socketio.on("set_keep")
def on_set_keep(data):
    keep = (data or {}).get("keep", [])
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.set_keep(s, pid, keep))


@socketio.on("resolve")
def on_resolve(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.resolve(s, pid))


@socketio.on("yield_tokyo")
def on_yield(data):
    leave = bool((data or {}).get("leave"))
    # The yielding player is whoever is at the head of the queue, not the current
    # player, so validate against the queue rather than must_be_current.
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        me = _me(game)
        if not me:
            return
        state = game.state
        gl.set_names(state, _names(game))
        py = state.get("pending_yield")
        if state["phase"] != "yield" or not py or not py["queue"] or py["queue"][0] != me.pid:
            return
        gl.yield_decision(state, me.pid, leave)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)


@socketio.on("buy_card")
def on_buy(data):
    index = (data or {}).get("index")
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.buy_card(s, pid, index))


@socketio.on("sweep_shop")
def on_sweep(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.sweep_shop(s, pid))


@socketio.on("card_action")
def on_card_action(data):
    d = data or {}
    # must_be_current=False: a couple of cards (Psychic Probe, Opportunist) are
    # reactions fired on someone else's turn; gl.card_action enforces which ones.
    _act(d.get("code", "").upper(),
         lambda g, s, pid: gl.card_action(s, pid, d.get("card"), d.get("choice")),
         must_be_current=False)


@socketio.on("end_turn")
def on_end_turn(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.end_turn(s, pid))


@socketio.on("leave_game")
def on_leave_game(data):
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        me = _me(game)
        if not me:
            return
        state = game.state
        gl.set_names(state, _names(game))
        if state["phase"] == "ended":
            return
        gl.resign(state, me.pid)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)


# ---------------------------------------------------------------------------
# Finalize: ELO + stats into kot_stats
# ---------------------------------------------------------------------------

def _finalize(game, state):
    if game.status == "ended":
        return
    game.status = "ended"
    _log_event(game, {"type": "end", "winner": state.get("winner")})

    places = {s["pid"]: s["place"] for s in state.get("standings", [])}
    real = {p.pid: p.user_id for p in game.players if p.user_id and not p.is_bot}
    ratings = {pid: (User.query.get(uid).kot.elo if User.query.get(uid).kot else 1000)
               for pid, uid in real.items()}

    for pid, uid in real.items():
        user = User.query.get(uid)
        st = user._ensure_stats()
        place = places.get(pid)
        m = state["mon"].get(pid, {})
        stat = m.get("stat", {})

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
        st.vp_scored = (st.vp_scored or 0) + m.get("vp", 0)
        st.damage_dealt = (st.damage_dealt or 0) + stat.get("damage", 0)
        st.monsters_koed = (st.monsters_koed or 0) + stat.get("kos", 0)
        st.tokyo_turns = (st.tokyo_turns or 0) + stat.get("tokyo_turns", 0)
        st.cards_bought = (st.cards_bought or 0) + stat.get("cards", 0)
        if place is not None and (st.best_place is None or place < st.best_place):
            st.best_place = place
        if m.get("vp", 0) > (st.highest_vp or 0):
            st.highest_vp = m.get("vp", 0)

    db.session.add(game)
    db.session.commit()
    _broadcast_lobbies()


# ---------------------------------------------------------------------------
# Background sweep: reap dead lobbies + idle games (mirrors ERS)
# ---------------------------------------------------------------------------

def _stale_game_cleanup():
    PLAYING_LIMIT = timedelta(minutes=30)
    WAITING_LIMIT = timedelta(minutes=30)

    def _run():
        with app.app_context():
            changed = False
            now = datetime.utcnow()
            playing_cutoff = now - PLAYING_LIMIT
            stale_playing = KotGame.query.filter(
                KotGame.status == "playing",
                db.or_(KotGame.last_activity_at == None,        # noqa: E711
                       KotGame.last_activity_at < playing_cutoff),
            ).all()
            for game in stale_playing:
                game.status = "ended"
                db.session.commit()
                changed = True

            waiting_cutoff = now - WAITING_LIMIT
            for game in KotGame.query.filter_by(status="waiting").all():
                too_old = (game.created_at or now) < waiting_cutoff
                if not game.players or too_old:
                    socketio.emit("lobby_closed", {"reason": "Lobby expired."},
                                  room="lobby:" + game.code)
                    _delete_game(game)
                    changed = True

            if changed:
                _broadcast_lobbies()

    _run()
    while True:
        eventlet.sleep(5 * 60)
        _run()


eventlet.spawn(_stale_game_cleanup)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=True)
