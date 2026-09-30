"""chat.cgovind.com: messages, groups and game invites across the whole site.

One JSON API that the dock (``static/dock.js``) calls from every page on every
subdomain, plus one Socket.IO connection per open page that the server pushes
new messages, read receipts and typing down. Everything a client *does* goes
over HTTP; the socket only ever carries things *to* the client, which keeps
every action testable with a plain test client.
"""

import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, session
from flask_socketio import SocketIO, join_room
from sqlalchemy import event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

import people
import rooms
from models import Block, Conversation, Follow, Member, Message, Prefs, Report, db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
if os.environ.get("SESSION_COOKIE_DOMAIN"):
    app.config["SESSION_COOKIE_DOMAIN"] = os.environ["SESSION_COOKIE_DOMAIN"]
if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _shared = os.path.join(os.path.dirname(__file__), "..", "ttr", "instance", "tickettoride.db")
    DATABASE_URL = "sqlite:///" + os.path.abspath(_shared)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

SITE_URL = os.environ.get("MAIN_SITE_URL", "https://cgovind.com")

# Which pages may call this API with the visitor's cookie. Every subdomain of
# cgovind.com, and nothing else - this is the whole CSRF story, together with
# requiring a JSON body, which no cross-site form can send without a preflight
# that this list then refuses.
ORIGIN_RE = re.compile(os.environ.get("CHAT_ORIGIN_RE", r"^https://([a-z0-9-]+\.)?cgovind\.com$"))

MAX_BODY = 2000
MAX_GROUP = 25
PAGE = 50


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
    except Exception:                                    # noqa: BLE001
        pass


db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins=lambda o: bool(o and ORIGIN_RE.match(o)),
                    async_mode=os.environ.get("CHAT_ASYNC_MODE") or None)

with app.app_context():
    db.create_all()


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------
# ponytail: in-process counters, fine on one worker; a restart forgets them,
# and a second worker would need them in the database.
LIMITS = {
    "message": (20, 60),              # 20 messages a minute
    "conversation": (20, 24 * 3600),  # 20 new threads a day
    "report": (20, 24 * 3600),
    "search": (60, 60),
}
_hits = defaultdict(deque)


def limited(kind, user_id):
    """True if ``user_id`` is over the ``kind`` limit; counts the hit if not."""
    count, window = LIMITS[kind]
    q = _hits[(kind, user_id)]
    cut = time.time() - window
    while q and q[0] < cut:
        q.popleft()
    if len(q) >= count:
        return True
    q.append(time.time())
    return False


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

def err(message, status=400):
    return jsonify({"error": message}), status


@app.after_request
def _cors(resp):
    origin = request.headers.get("Origin")
    if origin and ORIGIN_RE.match(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE"
        resp.headers["Vary"] = "Origin"
    return resp


def me_id():
    uid = session.get("user_id")
    if not uid:
        return None
    ok = db.session.execute(db.text("SELECT 1 FROM users WHERE id = :u"), {"u": uid}).first()
    return uid if ok else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if request.method == "OPTIONS":
            return "", 204
        uid = me_id()
        if not uid:
            return err("Log in to chat.", 401)
        if request.method in ("POST", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and not ORIGIN_RE.match(origin):
                return err("Bad origin.", 403)
            if not request.is_json:
                return err("Expected JSON.", 415)
        return fn(uid, *a, **kw)
    return wrapper


def body():
    return request.get_json(silent=True) or {}


def conn():
    return db.session.connection()


def blocked_either(a, b):
    return Block.query.filter(or_((Block.user_id == a) & (Block.target_id == b),
                                  (Block.user_id == b) & (Block.target_id == a))).first() is not None


def may_contact(sender, recipient):
    """Whether ``sender`` may start talking to, add or invite ``recipient``."""
    if sender == recipient or blocked_either(sender, recipient):
        return False
    prefs = db.session.get(Prefs, recipient)
    if prefs and prefs.dm_policy == "following":
        return Follow.query.filter_by(user_id=recipient, target_id=sender).first() is not None
    return True


def blocked_by(uid):
    return {b.target_id for b in Block.query.filter_by(user_id=uid)}


def member_ids(cid):
    return [m.user_id for m in Member.query.filter_by(conversation_id=cid)]


def membership(uid, cid):
    return Member.query.filter_by(conversation_id=cid, user_id=uid).first()


def stamp(dt):
    return dt.isoformat() + "Z" if dt else None


def message_dict(m):
    return {"id": m.id, "conversation_id": m.conversation_id, "sender": m.sender_id,
            "kind": m.kind, "body": m.body, "game": m.game, "room": m.room,
            "at": stamp(m.created_at)}


def push(user_ids, event_name, payload):
    for uid in set(user_ids):
        socketio.emit(event_name, payload, to="u%d" % uid)


def conversation_dict(c, uid, hidden=None):
    hidden = blocked_by(uid) if hidden is None else hidden
    ids = member_ids(c.id)
    who = people.users(conn(), ids, SITE_URL)
    here = people.presence(conn(), ids)
    members = [dict(who[i], **here.get(i, {"online": False, "status": "Offline"}))
               for i in ids if i in who]
    others = [m for m in members if m["id"] != uid]
    if c.is_group:
        title = c.name or ", ".join(m["name"] for m in others[:4]) or "Just you"
    else:
        title = others[0]["name"] if others else "Nobody"
    mine = membership(uid, c.id)
    q = Message.query.filter(Message.conversation_id == c.id)
    if hidden:
        q = q.filter(Message.sender_id.notin_(hidden))
    last = q.order_by(Message.id.desc()).first()
    unread = q.filter(Message.id > (mine.last_read_id if mine else 0),
                      Message.sender_id != uid).count()
    return {"id": c.id, "is_group": c.is_group, "name": c.name, "title": title,
            "members": members, "last": message_dict(last) if last else None,
            "unread": unread, "at": stamp(c.last_message_at)}


def post_message(uid, c, kind="text", text_body="", game=None, room=None):
    m = Message(conversation_id=c.id, sender_id=uid, kind=kind, body=text_body,
                game=game, room=room)
    db.session.add(m)
    c.last_message_at = datetime.utcnow()
    db.session.flush()
    mine = membership(uid, c.id)
    if mine:
        mine.last_read_id = m.id
    db.session.commit()
    payload = message_dict(m)
    ids = member_ids(c.id)
    # Somebody who blocked the sender never has it pushed, and never sees it in
    # history either - `messages` filters the same way.
    deaf = {b.user_id for b in Block.query.filter(Block.target_id == uid,
                                                  Block.user_id.in_(ids))}
    push([i for i in ids if i not in deaf], "chat_message", payload)
    return m


def find_or_open_dm(uid, other):
    """The DM between two people, made if it does not exist. None if not allowed."""
    key = "%d:%d" % (min(uid, other), max(uid, other))
    c = Conversation.query.filter_by(dm_key=key).first()
    if c:
        # An existing thread is still subject to blocks, but not to the policy:
        # switching to "people I added" should not cut off a friend mid-chat.
        return None if blocked_either(uid, other) else c
    if not may_contact(uid, other) or limited("conversation", uid):
        return None
    c = Conversation(is_group=False, dm_key=key, created_by=uid)
    db.session.add(c)
    try:
        db.session.flush()
    except IntegrityError:                  # the other person got there first
        db.session.rollback()
        return Conversation.query.filter_by(dm_key=key).first()
    db.session.add_all([Member(conversation_id=c.id, user_id=uid),
                        Member(conversation_id=c.id, user_id=other)])
    db.session.commit()
    return c


def can_send(uid, c):
    """A DM whose other half has since blocked (or been blocked) is read-only."""
    if c.is_group:
        return True
    others = [i for i in member_ids(c.id) if i != uid]
    return bool(others) and not blocked_either(uid, others[0])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/me", methods=["GET", "OPTIONS"])
@login_required
def api_me(uid):
    hidden = blocked_by(uid)
    total = 0
    for m in Member.query.filter_by(user_id=uid):
        q = Message.query.filter(Message.conversation_id == m.conversation_id,
                                 Message.id > m.last_read_id, Message.sender_id != uid)
        if hidden:
            q = q.filter(Message.sender_id.notin_(hidden))
        total += q.count()
    prefs = db.session.get(Prefs, uid)
    return jsonify({"user": people.users(conn(), [uid], SITE_URL).get(uid),
                    "unread": total,
                    "dm_policy": prefs.dm_policy if prefs else "anyone"})


@app.route("/api/prefs", methods=["POST", "OPTIONS"])
@login_required
def api_prefs(uid):
    policy = body().get("dm_policy")
    if policy not in ("anyone", "following"):
        return err("dm_policy is 'anyone' or 'following'.")
    prefs = db.session.get(Prefs, uid) or Prefs(user_id=uid)
    prefs.dm_policy = policy
    db.session.add(prefs)
    db.session.commit()
    return jsonify({"dm_policy": policy})


@app.route("/api/conversations", methods=["GET", "POST", "OPTIONS"])
@login_required
def api_conversations(uid):
    if request.method == "GET":
        hidden = blocked_by(uid)
        convs = (Conversation.query.join(Member, Member.conversation_id == Conversation.id)
                 .filter(Member.user_id == uid)
                 .order_by(Conversation.last_message_at.desc()).limit(50).all())
        return jsonify({"conversations": [conversation_dict(c, uid, hidden) for c in convs]})

    data = body()
    try:
        ids = sorted({int(i) for i in data.get("user_ids") or []} - {uid})
    except (TypeError, ValueError):
        return err("user_ids must be ids.")
    if not ids:
        return err("Pick somebody to talk to.")
    known = people.users(conn(), ids)
    if len(known) != len(ids):
        return err("No such person.", 404)

    if len(ids) == 1 and not data.get("group"):
        c = find_or_open_dm(uid, ids[0])
        if not c:
            return err("You can't message this person.", 403)
        return jsonify({"conversation": conversation_dict(c, uid)})

    if len(ids) + 1 > MAX_GROUP:
        return err("Groups top out at %d people." % MAX_GROUP)
    if not all(may_contact(uid, i) for i in ids):
        return err("Somebody on that list can't be added by you.", 403)
    if limited("conversation", uid):
        return err("That's a lot of new chats today. Try again tomorrow.", 429)
    name = (data.get("name") or "").strip()[:60] or None
    c = Conversation(is_group=True, name=name, created_by=uid)
    db.session.add(c)
    db.session.flush()
    db.session.add_all([Member(conversation_id=c.id, user_id=i) for i in [uid] + ids])
    db.session.commit()
    post_message(uid, c, kind="system", text_body="created the group")
    return jsonify({"conversation": conversation_dict(c, uid)})


def _conversation_for(uid, cid):
    c = db.session.get(Conversation, cid)
    if not c or not membership(uid, cid):
        return None
    return c


@app.route("/api/conversations/<int:cid>", methods=["GET", "POST", "OPTIONS"])
@login_required
def api_conversation(uid, cid):
    c = _conversation_for(uid, cid)
    if not c:
        return err("Not found.", 404)
    if request.method == "POST":                       # rename a group
        if not c.is_group:
            return err("Only groups have names.")
        c.name = (body().get("name") or "").strip()[:60] or None
        db.session.commit()
        post_message(uid, c, kind="system",
                     text_body="renamed the group to %s" % c.name if c.name else "cleared the group name")
    return jsonify({"conversation": conversation_dict(c, uid)})


@app.route("/api/conversations/<int:cid>/messages", methods=["GET", "POST", "OPTIONS"])
@login_required
def api_messages(uid, cid):
    c = _conversation_for(uid, cid)
    if not c:
        return err("Not found.", 404)

    if request.method == "POST":
        text_body = (body().get("body") or "").strip()
        if not text_body:
            return err("Say something.")
        if len(text_body) > MAX_BODY:
            return err("Keep it under %d characters." % MAX_BODY)
        if not can_send(uid, c):
            return err("You can't message this person.", 403)
        if limited("message", uid):
            return err("Slow down a little.", 429)
        return jsonify({"message": message_dict(post_message(uid, c, text_body=text_body))})

    q = Message.query.filter(Message.conversation_id == cid)
    hidden = blocked_by(uid)
    if hidden:
        q = q.filter(Message.sender_id.notin_(hidden))
    before = request.args.get("before", type=int)
    if before:
        q = q.filter(Message.id < before)
    page = q.order_by(Message.id.desc()).limit(PAGE).all()
    reads = {m.user_id: m.last_read_id for m in Member.query.filter_by(conversation_id=cid)}
    return jsonify({"messages": [message_dict(m) for m in reversed(page)],
                    "more": len(page) == PAGE, "reads": reads,
                    "can_send": can_send(uid, c)})


@app.route("/api/conversations/<int:cid>/read", methods=["POST", "OPTIONS"])
@login_required
def api_read(uid, cid):
    mine = membership(uid, cid)
    if not mine:
        return err("Not found.", 404)
    newest = db.session.execute(db.text(
        "SELECT MAX(id) FROM chat_messages WHERE conversation_id = :c"), {"c": cid}).scalar() or 0
    want = body().get("message_id")
    upto = min(int(want), newest) if isinstance(want, int) else newest
    if upto > mine.last_read_id:
        mine.last_read_id = upto
        db.session.commit()
        push(member_ids(cid), "read", {"conversation_id": cid, "user_id": uid,
                                       "last_read_id": upto})
    return jsonify({"last_read_id": mine.last_read_id})


@app.route("/api/conversations/<int:cid>/members", methods=["POST", "OPTIONS"])
@login_required
def api_add_members(uid, cid):
    c = _conversation_for(uid, cid)
    if not c or not c.is_group:
        return err("Not found.", 404)
    try:
        ids = {int(i) for i in body().get("user_ids") or []} - set(member_ids(cid))
    except (TypeError, ValueError):
        return err("user_ids must be ids.")
    if len(member_ids(cid)) + len(ids) > MAX_GROUP:
        return err("Groups top out at %d people." % MAX_GROUP)
    known = people.users(conn(), ids)
    if len(known) != len(ids) or not all(may_contact(uid, i) for i in ids):
        return err("Somebody on that list can't be added by you.", 403)
    db.session.add_all([Member(conversation_id=cid, user_id=i) for i in ids])
    db.session.commit()
    if ids:
        post_message(uid, c, kind="system",
                     text_body="added " + ", ".join(known[i]["name"] for i in sorted(ids)))
    return jsonify({"conversation": conversation_dict(c, uid)})


@app.route("/api/conversations/<int:cid>/leave", methods=["POST", "OPTIONS"])
@login_required
def api_leave(uid, cid):
    c = _conversation_for(uid, cid)
    if not c or not c.is_group:
        return err("Not found.", 404)
    post_message(uid, c, kind="system", text_body="left the group")
    Member.query.filter_by(conversation_id=cid, user_id=uid).delete()
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/conversations/<int:cid>/invite", methods=["POST", "OPTIONS"])
@login_required
def api_invite_here(uid, cid):
    c = _conversation_for(uid, cid)
    if not c:
        return err("Not found.", 404)
    return _invite(uid, c)


@app.route("/api/invite", methods=["POST", "OPTIONS"])
@login_required
def api_invite_person(uid):
    """Invite one person from their profile or the online list: the DM is
    found or opened on the way."""
    try:
        other = int(body().get("user_id"))
    except (TypeError, ValueError):
        return err("Who to?")
    if not people.users(conn(), [other]):
        return err("No such person.", 404)
    c = find_or_open_dm(uid, other)
    if not c:
        return err("You can't invite this person.", 403)
    return _invite(uid, c)


def _invite(uid, c):
    data = body()
    game, code = data.get("game"), (data.get("code") or "").upper()
    if not can_send(uid, c):
        return err("You can't message this person.", 403)
    if not rooms.is_in(conn(), uid, game, code):
        return err("You can only invite people into a room you're in.", 403)
    if limited("message", uid):
        return err("Slow down a little.", 429)
    m = post_message(uid, c, kind="invite", game=game, room=code)
    return jsonify({"message": message_dict(m), "conversation_id": c.id})


@app.route("/api/invite/<int:mid>", methods=["GET", "OPTIONS"])
@login_required
def api_invite_state(uid, mid):
    m = db.session.get(Message, mid)
    if not m or m.kind != "invite" or not membership(uid, m.conversation_id):
        return err("Not found.", 404)
    return jsonify(rooms.state(conn(), m.game, m.room))


@app.route("/api/rooms", methods=["GET", "OPTIONS"])
@login_required
def api_rooms(uid):
    return jsonify({"rooms": rooms.mine(conn(), uid)})


@app.route("/api/people", methods=["GET", "OPTIONS"])
@login_required
def api_people(uid):
    if limited("search", uid):
        return err("Slow down a little.", 429)
    ids = people.search(conn(), request.args.get("q"), uid)
    who = people.users(conn(), ids, SITE_URL)
    here = people.presence(conn(), ids)
    following = {f.target_id for f in Follow.query.filter_by(user_id=uid)}
    return jsonify({"people": [dict(who[i], following=i in following,
                                    **here.get(i, {"online": False, "status": "Offline"}))
                               for i in ids if i in who]})


@app.route("/api/friends", methods=["GET", "OPTIONS"])
@login_required
def api_friends(uid):
    ids = [f.target_id for f in Follow.query.filter_by(user_id=uid)]
    who = people.users(conn(), ids, SITE_URL)
    here = people.presence(conn(), ids)
    out = [dict(who[i], following=True, **here.get(i, {"online": False, "status": "Offline"}))
           for i in ids if i in who]
    out.sort(key=lambda p: (not p["online"], p["name"].lower()))
    return jsonify({"friends": out})


@app.route("/api/people/<int:other>", methods=["GET", "OPTIONS"])
@login_required
def api_person(uid, other):
    """What the profile page's buttons need to know about one person."""
    if not people.users(conn(), [other]):
        return err("No such person.", 404)
    return jsonify({"following": Follow.query.filter_by(user_id=uid, target_id=other).first() is not None,
                    "blocked": Block.query.filter_by(user_id=uid, target_id=other).first() is not None,
                    "can_message": may_contact(uid, other) or bool(
                        Conversation.query.filter_by(
                            dm_key="%d:%d" % (min(uid, other), max(uid, other))).first()
                        and not blocked_either(uid, other))})


def _toggle(model, uid, other, on):
    if other == uid or not people.users(conn(), [other]):
        return err("No such person.", 404)
    row = model.query.filter_by(user_id=uid, target_id=other).first()
    if on and not row:
        db.session.add(model(user_id=uid, target_id=other))
    elif not on and row:
        db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True, "on": on})


@app.route("/api/follow/<int:other>", methods=["POST", "DELETE", "OPTIONS"])
@login_required
def api_follow(uid, other):
    return _toggle(Follow, uid, other, request.method == "POST")


@app.route("/api/block/<int:other>", methods=["POST", "DELETE", "OPTIONS"])
@login_required
def api_block(uid, other):
    return _toggle(Block, uid, other, request.method == "POST")


@app.route("/api/messages/<int:mid>/report", methods=["POST", "OPTIONS"])
@login_required
def api_report(uid, mid):
    m = db.session.get(Message, mid)
    if not m or not membership(uid, m.conversation_id) or m.sender_id == uid:
        return err("Not found.", 404)
    if limited("report", uid):
        return err("That's a lot of reports today.", 429)
    db.session.add(Report(reporter_id=uid, message_id=mid,
                          reason=(body().get("reason") or "").strip()[:300] or None))
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Socket: server -> client only, plus the typing indicator
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect(_auth=None):
    uid = me_id()
    if not uid:
        return False
    join_room("u%d" % uid)


@socketio.on("typing")
def on_typing(data):
    uid = me_id()
    try:
        cid = int((data or {}).get("conversation_id"))
    except (TypeError, ValueError):
        return
    if not uid or not membership(uid, cid):
        return
    deaf = {b.user_id for b in Block.query.filter_by(target_id=uid)}
    push([i for i in member_ids(cid) if i != uid and i not in deaf],
         "typing", {"conversation_id": cid, "user_id": uid})
    db.session.remove()


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 5007)), debug=True)
