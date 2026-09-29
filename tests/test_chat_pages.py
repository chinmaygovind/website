"""The website's half of chat: the dock on its pages, the profile buttons, the
privacy box in settings, and the admin console's view of every conversation.

The chat service owns its tables (`chat/models.py`); here they are made by
hand, in the shape it creates them, so the admin pages have something to read.
"""

from sqlalchemy import text

PASSWORD = "hunter2hunter2"

CHAT_TABLES = [
    "CREATE TABLE IF NOT EXISTS chat_conversations (id INTEGER PRIMARY KEY, is_group BOOLEAN,"
    " name TEXT, dm_key TEXT, created_by INT, created_at TEXT, last_message_at TEXT)",
    "CREATE TABLE IF NOT EXISTS chat_members (conversation_id INT, user_id INT,"
    " joined_at TEXT, last_read_id INT)",
    "CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY, conversation_id INT,"
    " sender_id INT, kind TEXT, body TEXT, game TEXT, room TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS chat_reports (id INTEGER PRIMARY KEY, reporter_id INT,"
    " message_id INT, reason TEXT, created_at TEXT)",
]


def page(resp):
    return resp.get_data(as_text=True)


def login(client, make_user, username):
    uid = make_user(username, password=PASSWORD)
    assert client.post("/accounts/login",
                       data={"username": username, "password": PASSWORD}).status_code == 302
    return uid


def test_the_dock_loads_for_people_who_are_logged_in_only(client, make_user):
    make_user("tyler")
    assert "dock.js" not in page(client.get("/accounts/tyler"))
    login(client, make_user, "chinmay")
    assert "https://chat.cgovind.com/static/dock.js" in page(client.get("/accounts/tyler"))


def test_profile_buttons_are_for_other_people(client, make_user):
    make_user("tyler")
    login(client, make_user, "chinmay")
    assert 'id="chat-acts"' in page(client.get("/accounts/tyler"))
    assert 'id="chat-acts"' not in page(client.get("/accounts/chinmay"))


def test_settings_has_the_messages_box(client, make_user):
    login(client, make_user, "chinmay")
    html = page(client.get("/accounts/settings"))
    assert 'name="dm_policy" value="anyone"' in html
    assert 'name="dm_policy" value="following"' in html


def test_admin_reads_every_chat_and_every_report(client, make_user, db):
    me = login(client, make_user, "chinmay")
    tyler = make_user("tyler")
    with db.engine.begin() as c:
        for s in CHAT_TABLES:
            c.execute(text(s))
        for t in ("chat_reports", "chat_messages", "chat_members", "chat_conversations"):
            c.execute(text("DELETE FROM %s" % t))
        c.execute(text("INSERT INTO chat_conversations VALUES (7, 0, NULL, :k, :a, "
                       "'2026-09-29 10:00:00', '2026-09-29 10:05:00')"),
                  {"k": "%d:%d" % (me, tyler), "a": me})
        c.execute(text("INSERT INTO chat_members VALUES (7, :u, NULL, 0), (7, :t, NULL, 0)"),
                  {"u": me, "t": tyler})
        c.execute(text("INSERT INTO chat_messages VALUES (1, 7, :t, 'text', 'rematch?', NULL, NULL,"
                       " '2026-09-29 10:05:00')"), {"t": tyler})
        c.execute(text("INSERT INTO chat_reports VALUES (1, :u, 1, 'rude', '2026-09-29 10:06:00')"),
                  {"u": me})
    listing = page(client.get("/admin/chats"))
    assert "rematch?" in listing and "rude" in listing
    detail = page(client.get("/admin/chats/7"))
    assert "rematch?" in detail and "1 report" in detail
    assert client.get("/admin/chats/8").status_code == 404
