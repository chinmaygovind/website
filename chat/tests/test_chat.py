import os
import tempfile
from datetime import datetime

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = "sqlite:///" + _db
os.environ["CHAT_ASYNC_MODE"] = "threading"

import pytest
from sqlalchemy import text

import app as chat
from models import db

ORIGIN = {"Origin": "https://drive.cgovind.com"}

SHARED = [
    "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, is_bot BOOLEAN)",
    "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, display_name TEXT,"
    " display_name_lc TEXT, avatar TEXT)",
    "CREATE TABLE user_presence (user_id INTEGER PRIMARY KEY, service TEXT, detail TEXT,"
    " last_seen TEXT, updated_at TEXT)",
    "CREATE TABLE kot_games (id INTEGER PRIMARY KEY, code TEXT, status TEXT, max_players INT,"
    " created_at TEXT, last_activity_at TEXT)",
    "CREATE TABLE kot_players (id INTEGER PRIMARY KEY, game_id INT, user_id INT)",
]


@pytest.fixture(scope="session", autouse=True)
def shared_tables():
    with chat.app.app_context():
        with db.engine.begin() as c:
            for s in SHARED:
                c.execute(text(s))
    yield
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(_db + suffix)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def clean():
    chat._hits.clear()
    with chat.app.app_context():
        with db.engine.begin() as c:
            for t in ("chat_reports", "chat_messages", "chat_members", "chat_conversations",
                      "chat_follows", "chat_blocks", "chat_prefs", "users", "user_profiles",
                      "user_presence", "kot_games", "kot_players"):
                c.execute(text("DELETE FROM %s" % t))
            for i, name in enumerate(["chinmay", "tyler", "sam", "dana"], start=1):
                c.execute(text("INSERT INTO users VALUES (:i, :n, 0)"), {"i": i, "n": name})
    yield


def client(uid):
    c = chat.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
    return c


def post(c, url, data=None):
    return c.post(url, json=data or {}, headers=ORIGIN)


def dm(a, b):
    return post(client(a), "/api/conversations", {"user_ids": [b]}).get_json()["conversation"]["id"]


def test_guests_get_nothing():
    assert chat.app.test_client().get("/api/me").status_code == 401


def test_the_root_is_the_full_page_chat():
    r = chat.app.test_client().get("/")
    assert r.status_code == 200 and b"/static/dock.js" in r.data


def test_a_dm_is_one_thread_whoever_opens_it():
    assert dm(1, 2) == dm(2, 1)


def test_message_round_trip_and_unread():
    cid = dm(1, 2)
    assert post(client(1), "/api/conversations/%d/messages" % cid, {"body": "race?"}).status_code == 200
    tyler = client(2)
    assert tyler.get("/api/me").get_json()["unread"] == 1
    msgs = tyler.get("/api/conversations/%d/messages" % cid).get_json()["messages"]
    assert [m["body"] for m in msgs] == ["race?"]
    post(tyler, "/api/conversations/%d/read" % cid)
    assert tyler.get("/api/me").get_json()["unread"] == 0


def test_writes_from_another_site_are_refused():
    c = client(1)
    r = c.post("/api/conversations", json={"user_ids": [2]}, headers={"Origin": "https://evil.com"})
    assert r.status_code == 403
    r = c.post("/api/conversations", data="user_ids=2", headers=ORIGIN)
    assert r.status_code == 415


def test_block_stops_new_dms_and_existing_ones_and_is_silent():
    cid = dm(1, 2)
    post(client(2), "/api/block/1")
    r = post(client(1), "/api/conversations/%d/messages" % cid, {"body": "hi"})
    assert r.status_code == 403
    assert r.get_json()["error"] == "You can't message this person."
    assert post(client(1), "/api/conversations", {"user_ids": [3]}).status_code == 200


def test_blocked_senders_vanish_from_a_group_for_the_blocker():
    g = post(client(1), "/api/conversations", {"user_ids": [2, 3], "group": True, "name": "crew"})
    cid = g.get_json()["conversation"]["id"]
    post(client(3), "/api/block/2")
    post(client(2), "/api/conversations/%d/messages" % cid, {"body": "from tyler"})
    seen_by_sam = [m["body"] for m in client(3).get("/api/conversations/%d/messages" % cid).get_json()["messages"]]
    seen_by_me = [m["body"] for m in client(1).get("/api/conversations/%d/messages" % cid).get_json()["messages"]]
    assert "from tyler" not in seen_by_sam
    assert "from tyler" in seen_by_me


def test_following_only_policy():
    post(client(2), "/api/prefs", {"dm_policy": "following"})
    assert post(client(1), "/api/conversations", {"user_ids": [2]}).status_code == 403
    post(client(2), "/api/follow/1")
    assert post(client(1), "/api/conversations", {"user_ids": [2]}).status_code == 200


def test_group_add_and_leave():
    cid = post(client(1), "/api/conversations", {"user_ids": [2], "group": True}).get_json()["conversation"]["id"]
    post(client(1), "/api/conversations/%d/members" % cid, {"user_ids": [3]})
    names = {m["username"] for m in client(3).get("/api/conversations/%d" % cid).get_json()["conversation"]["members"]}
    assert names == {"chinmay", "tyler", "sam"}
    post(client(3), "/api/conversations/%d/leave" % cid)
    assert client(3).get("/api/conversations/%d" % cid).status_code == 404


def test_outsiders_cannot_read():
    cid = dm(1, 2)
    assert client(3).get("/api/conversations/%d/messages" % cid).status_code == 404


def test_message_rate_limit():
    cid = dm(1, 2)
    c = client(1)
    codes = [post(c, "/api/conversations/%d/messages" % cid, {"body": str(i)}).status_code
             for i in range(chat.LIMITS["message"][0] + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def _seat(uid, code="ABC123", status="waiting"):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with chat.app.app_context():
        with db.engine.begin() as c:
            gid = c.execute(text("SELECT id FROM kot_games WHERE code=:c"), {"c": code}).scalar()
            if not gid:
                c.execute(text("INSERT INTO kot_games (code, status, max_players, created_at,"
                               " last_activity_at) VALUES (:c, :s, 4, :t, :t)"),
                          {"c": code, "s": status, "t": now})
                gid = c.execute(text("SELECT id FROM kot_games WHERE code=:c"), {"c": code}).scalar()
            c.execute(text("INSERT INTO kot_players (game_id, user_id) VALUES (:g, :u)"),
                      {"g": gid, "u": uid})


def test_invite_only_into_a_room_you_are_in():
    cid = dm(1, 2)
    r = post(client(1), "/api/conversations/%d/invite" % cid, {"game": "kot", "code": "ABC123"})
    assert r.status_code == 403
    _seat(1)
    r = post(client(1), "/api/conversations/%d/invite" % cid, {"game": "kot", "code": "abc123"})
    assert r.status_code == 200
    mid = r.get_json()["message"]["id"]
    card = client(2).get("/api/invite/%d" % mid).get_json()
    assert card["joinable"] and card["players"] == 1 and card["max"] == 4
    assert card["url"] == "https://kot.cgovind.com/j/ABC123"
    assert client(3).get("/api/invite/%d" % mid).status_code == 404


def test_invite_card_closes_when_the_game_starts():
    _seat(1)
    mid = post(client(1), "/api/invite", {"user_id": 2, "game": "kot", "code": "ABC123"}).get_json()["message"]["id"]
    with chat.app.app_context():
        with db.engine.begin() as c:
            c.execute(text("UPDATE kot_games SET status='playing'"))
    assert client(2).get("/api/invite/%d" % mid).get_json()["joinable"] is False


def test_my_rooms():
    _seat(1)
    rooms = client(1).get("/api/rooms").get_json()["rooms"]
    assert [(r["game"], r["code"]) for r in rooms] == [("kot", "ABC123")]
    assert client(2).get("/api/rooms").get_json()["rooms"] == []


def test_report_lands_once_and_not_on_your_own():
    cid = dm(1, 2)
    mid = post(client(1), "/api/conversations/%d/messages" % cid, {"body": "gg"}).get_json()["message"]["id"]
    assert post(client(1), "/api/messages/%d/report" % mid).status_code == 404
    assert post(client(2), "/api/messages/%d/report" % mid, {"reason": "spam"}).status_code == 200


def test_friends_are_one_way_and_sorted_online_first():
    post(client(1), "/api/follow/3")
    post(client(1), "/api/follow/2")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with chat.app.app_context():
        with db.engine.begin() as c:
            c.execute(text("INSERT INTO user_presence VALUES (3, 'drive', 'Sunrise Circuit', :t, :t)"),
                      {"t": now})
    friends = client(1).get("/api/friends").get_json()["friends"]
    assert [f["username"] for f in friends] == ["sam", "tyler"]
    assert friends[0]["status"] == "Playing Drive - Sunrise Circuit"
    assert client(2).get("/api/friends").get_json()["friends"] == []


def test_search_skips_bots_and_yourself():
    with chat.app.app_context():
        with db.engine.begin() as c:
            c.execute(text("INSERT INTO users VALUES (9, 'tylerbot', 1)"))
    found = client(2).get("/api/people?q=ty").get_json()["people"]
    assert found == []
    assert [p["username"] for p in client(1).get("/api/people?q=TY").get_json()["people"]] == ["tyler"]


def test_socket_push_reaches_only_members():
    cid = dm(1, 2)
    tyler = chat.socketio.test_client(chat.app, flask_test_client=client(2))
    sam = chat.socketio.test_client(chat.app, flask_test_client=client(3))
    assert tyler.is_connected() and sam.is_connected()
    post(client(1), "/api/conversations/%d/messages" % cid, {"body": "now"})
    assert [e["args"][0]["body"] for e in tyler.get_received() if e["name"] == "chat_message"] == ["now"]
    assert not [e for e in sam.get_received() if e["name"] == "chat_message"]


def test_guest_socket_is_refused():
    guest = chat.socketio.test_client(chat.app, flask_test_client=chat.app.test_client())
    assert not guest.is_connected()
