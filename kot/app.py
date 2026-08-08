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
import bot
import visits


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


# Every request logged, and this service's players marked as here.
# `visits.py` is one file copied into all five services and is byte-identical
# in each - the same convention `models.py` follows, and the main repo's
# `tests/test_no_drift.py` is what stops the copies drifting.
visits.init_app(app, db, "kot")

# Each seat is a King of Tokyo monster (name + signature colour).
MONSTERS = [
    ("Gigazaur", "#6fcf78"),
    ("The King", "#f2994a"),
    ("Cyber Bunny", "#f178b6"),
    ("Kraken", "#56ccf2"),
    ("Meka Dragon", "#eb5757"),
    ("Alienoid", "#bb6bd9"),
]

# Bot display names. Which one shows up is random, but Bot-zilla is the
# headliner: it gets half the weight on the first bot added to a table, with
# the other four splitting the rest. Later bots just take a random free name.
BOT_NAMES = ["Bot-zilla", "Claw-de", "Mechatron", "The Terminator", "Gloopy"]
BOT_HEADLINER = "Bot-zilla"
BOT_HEADLINER_WEIGHT = 0.5


def _pick_bot_name(used):
    free = [n for n in BOT_NAMES if n not in used]
    if not free:
        return None
    if BOT_HEADLINER in free:
        others = [n for n in free if n != BOT_HEADLINER]
        if not others or random.random() < BOT_HEADLINER_WEIGHT:
            return BOT_HEADLINER
        return random.choice(others)
    return random.choice(free)

# In-memory per-game locks (single eventlet worker, like ERS).
_locks = {}


def _lock(code):
    return _locks.setdefault(code, eventlet.semaphore.Semaphore(1))

# The main site, which is where /accounts and the flag art are served from.
# Deliberately NOT `SITE_URL`: that name is already taken on the box, where it
# means *this* service's own public address (drive/.env has
# SITE_URL=https://drive.cgovind.com), and quietly borrowing it would point
# every flag at the wrong host.
MAIN_SITE_URL = os.environ.get("MAIN_SITE_URL", "https://cgovind.com").rstrip("/")


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
    """The name to put on a seat: theirs if they chose one, else their username.

    Everything that writes a player's name into a game reads it from here, so
    the display name set on cgovind.com/accounts follows somebody into every
    lobby without any of the game code knowing that is what happened. A guest
    is whatever they typed.
    """
    u = get_current_user()
    return u.display if u else session.get("guest_name", "Guest")


def require_login(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not get_current_user() and not session.get("guest_name"):
            return redirect(url_for("login_page"))
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
        if not KotGame.query.filter_by(code=code).first():
            return code


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(),
            "effective_name": get_effective_name(),
            # Where the flag art lives. It is one copy on the main site
            # rather than four, so a game refers to it by absolute URL - see
            # `UserProfile.flag_path`, which returns the path half.
            "site_url": MAIN_SITE_URL,
            # What the heartbeat in base.html says about this page. Derived
            # from the endpoint rather than passed by each route, so a new
            # page gets a sensible answer without anybody remembering one.
            "presence_where": PRESENCE_BY_ENDPOINT.get(request.endpoint or "", "home"),
            "asset_version": os.environ.get("ASSET_VERSION", "1")}


PRESENCE_BY_ENDPOINT = {
    "lobbies": "lobby",
    "lobby": "lobby",
    "game_page": "game",
    "leaderboard": "board",
}


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
            if not any(not q.is_bot for q in remaining):
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
                           user=get_current_user(), name=get_effective_name(),
                           mine=mine, online=_online_now())

# What each `where` a page can send is called on a profile. **This table is the
# whole security model of the status line**: the browser sends a key, and a key
# that is not in here means no detail at all rather than something to display.
# A profile page is public, so anything that let a player put their own words
# on it would be a billboard with a text box attached.
PRESENCE_WHERE = {
    "lobby": "In Lobby",
    "game": "In Game",
    "board": "Reading the leaderboard",
}


@app.route("/api/presence", methods=["POST"])
def api_presence():
    """The heartbeat behind the green dot on cgovind.com/accounts.

    Sent on load and then once a minute while the tab is visible. Guests get a
    200 and no row: presence hangs off an account, and there is nowhere to hang
    a guest's.
    """
    user = get_current_user()
    if not user:
        return jsonify({"ok": True})
    where = str((request.json or {}).get("where", ""))[:20]
    visits.seen(db, user.id, "kot", PRESENCE_WHERE.get(where))
    return jsonify({"ok": True})


def _online_now():
    """Who is about, anywhere on cgovind.com, for the lobbies page.

    Across all four games and not just this one, which is the point: the
    question a lobby raises is "is there anybody around to play", and somebody
    currently driving is somebody you can ask.
    """
    rows = visits.online_now(db.session.connection(), limit=12)
    for r in rows:
        r["label"] = PRESENCE_LABEL.get(r["service"], "Online")
    return rows


# The four games as a profile would name them, for the one-line "who is on"
# list. Deliberately short: this is a sidebar, not a profile.
PRESENCE_LABEL = {"drive": "Drive", "ttr": "Ticket to Ride",
                  "ers": "Egyptian Rat Screw", "kot": "King of Tokyo",
                  "site": "On the site"}



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
        name=get_effective_name(),
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
                           roster_json=script_json(roster),
                           name=get_effective_name())


# ---------------------------------------------------------------------------
# Broadcasting + reaping
# ---------------------------------------------------------------------------

def _roster(game):
    return {p.pid: p.to_dict() for p in game.players}


def _names(game):
    return {p.pid: p.name for p in game.players}


def _broadcast(game):
    """Emit personalized per-player views (never room-wide) so an owner-only
    field like Made in a Lab's peek reaches only its owner - every player has
    their own private room from on_join_game, and spectators share one
    generic, owner-blind room."""
    state = game.state
    roster = _roster(game)
    for p in game.players:
        socketio.emit("game_state", {"state": gl.public_view(state, viewer_pid=p.pid), "roster": roster},
                      room=f"game:{game.code}:{p.pid}")
    socketio.emit("game_state", {"state": gl.public_view(state), "roster": roster},
                  room=f"game:{game.code}:spectate")


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
    _bot_sched.pop(game.code, None)
    _locks.pop(game.code, None)
    db.session.delete(game)
    db.session.commit()


def _player_elo(p):
    if p.linked_user and p.linked_user.kot:
        return p.linked_user.kot.elo or 1000
    return 1000


def _me(game):
    return KotPlayer.query.filter_by(game_id=game.id, session_key=get_session_key()).first()


def _log_event(game, ev, state=None, log_after=None):
    """Append one entry to the game's move-by-move replay.

    ``ev`` is the action itself (what the player chose); passing ``state`` also
    snapshots the resulting position, and ``log_after`` attaches every engine
    log line the action produced - which is where the consequences (damage,
    Tokyo moves, knockouts, card triggers) come from, without game_logic
    needing to know a replay exists."""
    ev.setdefault("t", int(time.time() * 1000))
    if state is not None:
        ev["seq"] = state.get("seq")
        ev["turn"] = state.get("turn")
        ev["phase"] = state.get("phase")
        ev["current"] = state.get("current")
        ev["tokyo"] = dict(state.get("tokyo") or {})
        ev["mon"] = {pid: {"hp": m["hp"], "vp": m["vp"], "energy": m["energy"],
                           "alive": m["alive"], "cards": list(m.get("cards", []))}
                     for pid, m in (state.get("mon") or {}).items()}
        if log_after is not None:
            ev["log"] = [l["text"] for l in state.get("log", []) if l["id"] > log_after]
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
    game = KotGame.query.filter_by(code=code).first()
    if not game:
        return
    me = _me(game)
    # Each player gets their own private room so _broadcast can personalize
    # game_state per viewer; spectators share one generic, owner-blind room.
    join_room(f"game:{code}:{me.pid}" if me else f"game:{code}:spectate")
    if game.status != "waiting":
        emit("game_state", {"state": gl.public_view(game.state, viewer_pid=(me.pid if me else None)),
                            "roster": _roster(game)})


@socketio.on("add_bot")
def on_add_bot(data):
    """Host-only: seat a bot. It is a normal player row from here on - it takes
    a monster and colour like anyone else and is driven by _bot_kick once the
    game starts."""
    code = (data or {}).get("code", "").upper()
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "waiting":
            return
        me = _me(game)
        if not me or not me.is_host:
            return
        if len(game.players) >= game.max_players:
            emit("start_error", {"error": "The table is full."})
            return
        # Pick a monster and seat nobody holds: after a kick, len(players) can
        # collide with an existing seat and hand out a duplicate monster.
        taken = {p.monster for p in game.players}
        monster, color = next(((m, c) for m, c in MONSTERS if m not in taken),
                              MONSTERS[len(game.players) % len(MONSTERS)])
        seat = max((p.seat_order for p in game.players), default=-1) + 1
        name = _pick_bot_name({p.name for p in game.players}) or f"Bot-{seat}"
        db.session.add(KotPlayer(
            game_id=game.id, user_id=None,
            session_key=f"bot_{uuid.uuid4().hex[:8]}", name=name,
            color=color, monster=monster, seat_order=seat,
            is_host=False, is_bot=True))
        db.session.commit()
        _broadcast_lobby(game)
        _broadcast_lobbies()


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
        # Bots are not a reason to keep a lobby alive - once the last human
        # walks out, reap it and the bots with it.
        if not any(not p.is_bot for p in remaining):
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
                          "names": {p.pid: p.name for p in players},
                          "bots": [p.pid for p in players if p.is_bot]},
                   state=state, log_after=0)
        game.last_activity_at = datetime.utcnow()
        db.session.commit()
        socketio.emit("go_to_game", {"code": code}, room="lobby:" + code)
        _broadcast(game)
        _broadcast_lobbies()
    _bot_kick(code, why="start")


# ---------------------------------------------------------------------------
# Socket handlers - gameplay
# ---------------------------------------------------------------------------

def _act(code, fn, must_be_current=True, event=None, actor_pid=None):
    """Load the game, verify the caller controls a seat, run fn(game, state, pid),
    then record the move, persist, broadcast and finalize.

    ``event`` is either a dict or a callable ``(state, pid) -> dict`` describing
    the action, evaluated BEFORE fn runs so it captures what the player chose
    rather than what it turned into. ``actor_pid`` lets a bot act without a
    session; everything else goes through the caller's own seat."""
    with _lock(code):
        game = KotGame.query.filter_by(code=code).first()
        if not game or game.status != "playing":
            return
        state = game.state
        if actor_pid is not None:
            pid = actor_pid
            if pid not in state.get("mon", {}):
                return
        else:
            me = _me(game)
            if not me:
                return
            pid = me.pid
        gl.set_names(state, _names(game))
        if state["phase"] == "ended":
            return
        if must_be_current and state["current"] != pid:
            return
        ev = event(state, pid) if callable(event) else (dict(event) if event else None)
        log_after = state.get("log_seq", 0)
        before_seq = state.get("seq")
        fn(game, state, pid)
        # A rejected action (wrong phase, unaffordable card) leaves the state
        # untouched; don't write a replay entry for something that never happened.
        if ev is not None and state.get("seq") != before_seq:
            ev.setdefault("pid", pid)
            _log_event(game, ev, state=state, log_after=log_after)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)
    _bot_kick(code)


@socketio.on("roll")
def on_roll(data):
    keep = (data or {}).get("keep", [])
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.do_roll(s, pid, keep),
         event=lambda s, pid: {"type": "roll", "roll_num": s["roll_num"],
                               "keep": list(keep), "before": list(s["dice"])})


@socketio.on("set_keep")
def on_set_keep(data):
    # Purely cosmetic die-locking; the keep set that matters is the one sent
    # with the reroll, so this stays out of the replay.
    keep = (data or {}).get("keep", [])
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.set_keep(s, pid, keep))


@socketio.on("resolve")
def on_resolve(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.resolve(s, pid),
         event=lambda s, pid: {"type": "resolve", "dice": list(s["dice"]),
                               "rolls_used": s["roll_num"]})


@socketio.on("token_choice")
def on_token_choice(data):
    d = data or {}
    _act(d.get("code", "").upper(),
         lambda g, s, pid: gl.token_choice_decision(s, pid, d.get("poison"), d.get("shrink")),
         event=lambda s, pid: {"type": "token_choice", "poison": d.get("poison"),
                               "shrink": d.get("shrink"),
                               "hearts": (s.get("pending_token_choice") or {}).get("hearts")})


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
        log_after = state.get("log_seq", 0)
        gl.yield_decision(state, me.pid, leave)
        _log_event(game, {"type": "yield", "pid": me.pid, "leave": leave,
                          "attacker": py.get("attacker")},
                   state=state, log_after=log_after)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)
    _bot_kick(code)


@socketio.on("buy_card")
def on_buy(data):
    index = (data or {}).get("index")
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.buy_card(s, pid, index),
         event=lambda s, pid: {"type": "buy", "index": index,
                               "card": (s["shop"][index]
                                        if isinstance(index, int) and 0 <= index < len(s["shop"])
                                        else None)})


@socketio.on("sweep_shop")
def on_sweep(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.sweep_shop(s, pid),
         event=lambda s, pid: {"type": "sweep", "shop": list(s["shop"])})


@socketio.on("card_action")
def on_card_action(data):
    d = data or {}
    # must_be_current=False: a couple of cards (Psychic Probe, Opportunist) are
    # reactions fired on someone else's turn; gl.card_action enforces which ones.
    _act(d.get("code", "").upper(),
         lambda g, s, pid: gl.card_action(s, pid, d.get("card"), d.get("choice")),
         must_be_current=False,
         event={"type": "card_action", "card": d.get("card"), "choice": d.get("choice")})


@socketio.on("end_turn")
def on_end_turn(data):
    _act((data or {}).get("code", "").upper(),
         lambda g, s, pid: gl.end_turn(s, pid),
         event={"type": "end_turn"})


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
        log_after = state.get("log_seq", 0)
        gl.resign(state, me.pid)
        _log_event(game, {"type": "resign", "pid": me.pid},
                   state=state, log_after=log_after)
        game.state = state
        game.last_activity_at = datetime.utcnow()
        if state["phase"] == "ended":
            _finalize(game, state)
        db.session.commit()
        _broadcast(game)
    _bot_kick(code)


# ---------------------------------------------------------------------------
# Bot orchestration
# ---------------------------------------------------------------------------
#
# Bots are ordinary KotPlayer rows (is_bot=True, no user_id) driven by eventlet
# timers. Every decision comes from bot.py and is applied through the same
# game_logic entry points a human's socket event would hit, so a bot can never
# make a move a player couldn't.
#
# _bot_kick is the single scheduler: it looks at the position, works out whether
# a bot owes an action, and arms one timer. Each timer re-enters _bot_kick when
# it lands, so the chain continues until it is a human's turn. Actions are keyed
# on state["seq"] (which bumps on every mutation) so the same move can never be
# scheduled twice.
#
# CRITICAL: _bot_kick takes the per-game lock, and eventlet semaphores are not
# reentrant - never call it while already holding that lock.

_bot_sched = {}

# How long a bot "thinks". Long enough to read as deliberate, short enough that
# a 6-monster table does not drag.
#
# The floor here is not arbitrary: the client's dice reel runs for 0.5s, and a
# roll whose reel is still spinning when the next one starts reads as the bot
# teleporting through its turn. Every delay leaves room for the animation to
# finish and for the result to be readable before anything else moves.
BOT_DELAY = {
    "roll":     (1.2, 2.0),   # >= reel (0.5s) + time to actually see the faces
    "resolve":  (1.1, 1.7),   # a beat on the final dice before results land
    "yield":    (1.2, 2.2),
    "buy":      (1.0, 1.8),
    "end_turn": (0.9, 1.4),
    "probe":    (0.9, 1.6),
    "token":    (0.8, 1.4),
}


def _bot_pids(game):
    return {p.pid for p in game.players if p.is_bot}


def _bot_delay(kind, why=None):
    lo, hi = BOT_DELAY.get(kind, (0.8, 1.4))
    if why == "start":
        return hi + 0.8          # let everyone's table finish loading first
    return random.uniform(lo, hi)


def _bot_kick(code, why=None):
    """Schedule whatever a bot owes the table right now, if anything.

    Establishes its own app context so it is safe to call from a bare greenlet
    as well as from a socket handler."""
    if not code:
        return
    with app.app_context():
        with _lock(code):
            game = KotGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if state.get("phase") == "ended":
                return
            bots = _bot_pids(game)
            if not bots:
                return
            seq = state.get("seq")
            sched = _bot_sched.setdefault(code, {})
            phase = state.get("phase")

            def arm(kind, pid, fn):
                if sched.get(kind) == seq:
                    return
                sched[kind] = seq
                eventlet.spawn_after(_bot_delay(kind, why), fn, code, seq, pid)

            # Off-turn obligations first: these BLOCK the whole game until the
            # bot answers, so a bot that stayed silent here would hang the table.
            if phase == "yield":
                py = state.get("pending_yield") or {}
                q = py.get("queue") or []
                if q and q[0] in bots:
                    arm("yield", q[0], _bot_yield)
                    return
            if phase == "probe_window":
                pp = state.get("pending_probe") or {}
                q = pp.get("queue") or []
                if q and q[0] in bots:
                    arm("probe", q[0], _bot_probe)
                    return
            if phase == "token_choice":
                pc = state.get("pending_token_choice") or {}
                if pc.get("pid") in bots:
                    arm("token", pc["pid"], _bot_token)
                    return

            cur = state.get("current")
            if cur not in bots:
                return
            if phase == "rolling":
                arm("roll", cur, _bot_roll)
            elif phase == "buying":
                arm("buy", cur, _bot_buy)


PROBE_CARD_ID = "psychic_probe"     # canonical id; gl.card_action checks the
                                    # mechanic key, so this also works for a
                                    # bot holding the ability through Mimic.


def _bot_step(code, seq, pid, phase, worker):
    """Run one bot step atomically.

    ``worker(state, pid, emit)`` does every engine call for the step while the
    lock is held, calling ``emit(event, log_after)`` for each move it makes so
    bot turns land in the replay exactly like human ones.

    Doing a whole step under one lock is deliberate. The scheduler refuses to
    arm the same (kind, seq) twice, so an action the engine silently rejects
    would leave the seq unchanged, nothing re-armed, and the table frozen. Every
    worker below is therefore written to guarantee forward progress, and doing
    it atomically means no other greenlet can slip in between a bot's decision
    and the move it based on that decision."""
    with app.app_context():
        with _lock(code):
            game = KotGame.query.filter_by(code=code).first()
            if not game or game.status != "playing":
                return
            state = game.state
            if state.get("seq") != seq or state.get("phase") != phase:
                return                  # position moved on; whoever moved re-kicked
            m = state.get("mon", {}).get(pid)
            if not m or not m["alive"]:
                return
            gl.set_names(state, _names(game))

            def emit(ev, log_after):
                ev.setdefault("pid", pid)
                ev["bot"] = True
                _log_event(game, ev, state=state, log_after=log_after)

            worker(state, pid, emit)

            game.state = state
            game.last_activity_at = datetime.utcnow()
            if state["phase"] == "ended":
                _finalize(game, state)
            db.session.commit()
            _broadcast(game)
    _bot_kick(code)


def _bot_roll(code, seq, pid):
    """Roll, reroll, or stop and bank the dice."""
    def worker(state, pid, emit):
        if state.get("current") != pid:
            return
        action, keep = bot.decide_roll(state, pid)
        la = state["log_seq"]
        if action == "roll":
            ev = {"type": "roll", "roll_num": state["roll_num"],
                  "keep": list(keep), "before": list(state["dice"])}
            gl.do_roll(state, pid, keep)
        else:
            ev = {"type": "resolve", "dice": list(state["dice"]),
                  "rolls_used": state["roll_num"]}
            gl.resolve(state, pid)
        emit(ev, la)

    _bot_step(code, seq, pid, "rolling", worker)


def _bot_yield(code, seq, pid):
    def worker(state, pid, emit):
        py = state.get("pending_yield") or {}
        if not (py.get("queue") or []) or py["queue"][0] != pid:
            return
        leave = bot.decide_yield(state, pid)
        la = state["log_seq"]
        gl.yield_decision(state, pid, leave)
        emit({"type": "yield", "leave": leave, "attacker": py.get("attacker")}, la)

    _bot_step(code, seq, pid, "yield", worker)


def _bot_token(code, seq, pid):
    def worker(state, pid, emit):
        pc = state.get("pending_token_choice") or {}
        if pc.get("pid") != pid:
            return
        poison, shrink = bot.decide_token_choice(state, pid)
        la = state["log_seq"]
        gl.token_choice_decision(state, pid, poison, shrink)
        emit({"type": "token_choice", "poison": poison, "shrink": shrink}, la)

    _bot_step(code, seq, pid, "token_choice", worker)


def _bot_probe(code, seq, pid):
    """Answer a Psychic Probe window.

    The engine holds the ENTIRE game in probe_window until every prober has
    decided, so this must always drain the bot from the queue. A rerolled die
    index the engine rejects would otherwise hang the table, hence the
    belt-and-braces pass at the end."""
    def worker(state, pid, emit):
        pp = state.get("pending_probe") or {}
        if not (pp.get("queue") or []) or pp["queue"][0] != pid:
            return
        die = bot.decide_probe(state, pid)
        if die is not None:
            la = state["log_seq"]
            choice = {"index": die}
            gl.card_action(state, pid, PROBE_CARD_ID, choice)
            emit({"type": "card_action", "card": PROBE_CARD_ID, "choice": choice}, la)
        pp = state.get("pending_probe") or {}
        if state.get("phase") == "probe_window" and (pp.get("queue") or [None])[0] == pid:
            la = state["log_seq"]
            gl.card_action(state, pid, PROBE_CARD_ID, {"pass": True})
            emit({"type": "card_action", "card": PROBE_CARD_ID,
                  "choice": {"pass": True}}, la)

    _bot_step(code, seq, pid, "probe_window", worker)


def _bot_buy(code, seq, pid):
    """Work the shop, then end the turn.

    The whole buy phase is one step so that a purchase the engine refuses can
    never leave the bot sitting in ``buying`` forever - whatever happens above,
    the turn ends below."""
    def worker(state, pid, emit):
        if state.get("current") != pid:
            return
        for kind, index in bot.decide_buys(state, pid):
            if state["phase"] != "buying" or state["current"] != pid:
                break
            la, before = state["log_seq"], state["seq"]
            if kind == "buy":
                ev = {"type": "buy", "index": index,
                      "card": state["shop"][index] if 0 <= index < len(state["shop"]) else None}
                gl.buy_card(state, pid, index)
            else:
                ev = {"type": "sweep", "shop": list(state["shop"])}
                gl.sweep_shop(state, pid)
            if state["seq"] != before:
                emit(ev, la)
        if state["phase"] == "buying" and state["current"] == pid:
            la = state["log_seq"]
            gl.end_turn(state, pid)
            emit({"type": "end_turn"}, la)

    _bot_step(code, seq, pid, "buying", worker)


# ---------------------------------------------------------------------------
# Finalize: ELO + stats into kot_stats
# ---------------------------------------------------------------------------

def _finalize(game, state):
    if game.status == "ended":
        return
    game.status = "ended"
    _bot_sched.pop(game.code, None)     # no more bot turns to schedule here
    _log_event(game, {"type": "end", "winner": state.get("winner"),
                      "standings": state.get("standings"),
                      "turns": state.get("turn")}, state=state)

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
