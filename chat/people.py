"""Who somebody is and whether they are around, read straight off shared tables.

``users`` and ``user_profiles`` belong to the accounts pages and
``user_presence`` to ``visits.py``. Chat only ever reads them, one query per
batch of ids, and copes with any of them being missing - a fresh dev database
may hold nothing but ``users``.
"""

from datetime import datetime, timedelta

from sqlalchemy import text

# Same window `visits.ONLINE_FOR` uses for the green dot, so chat and the
# profile page never disagree about who is online.
ONLINE_FOR = timedelta(minutes=2)

# Presence wording, as `accounts/presence.py` phrases it.
GAME_NAMES = {"ttr": "Conductor", "ers": "Egyptian Rat Screw",
              "kot": "King of Tokyo", "drive": "Drive", "gto": "GTO Trainer"}


def _has(conn, table):
    return conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                        {"t": table}).first() is not None


def _parse(value):
    if not value or isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def users(conn, ids, site_url=""):
    """``{id: {"id", "username", "name", "avatar"}}`` for the ids that exist."""
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    marks = ",".join(str(i) for i in ids)            # ints, so safe to inline
    profiles = _has(conn, "user_profiles")
    sql = ("SELECT u.id, u.username, %s FROM users u %s WHERE u.id IN (%s)"
           % ("p.display_name, p.avatar" if profiles else "NULL, NULL",
              "LEFT JOIN user_profiles p ON p.user_id = u.id" if profiles else "",
              marks))
    out = {}
    for uid, username, display, avatar in conn.execute(text(sql)):
        out[uid] = {"id": uid, "username": username, "name": display or username,
                    "avatar": ("%s/accounts/avatar/%s" % (site_url, avatar)) if avatar else None}
    return out


def search(conn, query, me, limit=8):
    """People whose username or display name starts with ``query``. Bots excluded."""
    q = (query or "").strip().lower()
    if not q:
        return []
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    profiles = _has(conn, "user_profiles")
    sql = ("SELECT u.id FROM users u %s WHERE u.id != :me"
           " AND (u.is_bot IS NULL OR u.is_bot = 0)"
           " AND (lower(u.username) LIKE :q ESCAPE '\\' %s)"
           " ORDER BY lower(u.username) LIMIT :lim"
           % ("LEFT JOIN user_profiles p ON p.user_id = u.id" if profiles else "",
              "OR p.display_name_lc LIKE :q ESCAPE '\\'" if profiles else ""))
    return [r[0] for r in conn.execute(text(sql), {"me": me, "q": like, "lim": limit})]


def presence(conn, ids):
    """``{id: {"online": bool, "status": str}}``, wording as the profile page's."""
    ids = sorted({int(i) for i in ids if i})
    if not ids or not _has(conn, "user_presence"):
        return {}
    rows = conn.execute(text(
        "SELECT user_id, service, detail, last_seen FROM user_presence WHERE user_id IN (%s)"
        % ",".join(str(i) for i in ids)))
    cutoff = datetime.utcnow() - ONLINE_FOR
    out = {}
    for uid, service, detail, last_seen in rows:
        seen = _parse(last_seen)
        online = bool(seen and seen > cutoff)
        if not online:
            status = "Offline"
        elif service in GAME_NAMES:
            status = "Playing %s" % GAME_NAMES[service]
            if detail:
                status += " - %s" % detail
        else:
            status = "Browsing cgovind.com"
        out[uid] = {"online": online, "status": status, "game": service if online else None}
    return out
