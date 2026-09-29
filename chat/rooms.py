"""The four games' rooms, read from their own tables in the shared database.

An invite is a game and a room code, and everything the card shows - which
game, how full, whether you can still get in - is read here, live, every time
the card is drawn. Nothing about a room is copied into chat, so there is
nothing to go stale.
"""

import os
from datetime import datetime, timedelta

from sqlalchemy import text

# game -> (rooms table, players table, host, what the room is called)
GAMES = {
    "drive": ("drive_games", "drive_players", "drive.cgovind.com", "Drive"),
    "ttr":   ("games",       "players",       "conductor.cgovind.com", "Conductor"),
    "kot":   ("kot_games",   "kot_players",   "kot.cgovind.com", "King of Tokyo"),
    "ers":   ("ers_games",   "ers_players",   "ers.cgovind.com", "Egyptian Rat Screw"),
}

# A room nobody has touched in this long is not one to invite anybody into.
# Rooms are not deleted when the last person wanders off, so without this a
# lobby from last Tuesday would be offered as somewhere to play.
FRESH_FOR = timedelta(hours=6)


def host_for(game):
    """Where a game lives. Overridable per game (``CHAT_HOST_DRIVE=localhost:5005``)
    so a laptop's invite links point at the laptop."""
    override = os.environ.get("CHAT_HOST_%s" % game.upper())
    if override:
        return override if "://" in override else "http://" + override
    return "https://" + GAMES[game][2]


def join_url(game, code):
    return "%s/j/%s" % (host_for(game), code)


def _has(conn, table):
    return conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                        {"t": table}).first() is not None


def _joinable(game, status, count, cap):
    if status == "ended":
        return False
    # Drive's room is a place you stay in between races, so a race in progress
    # does not close the door. In the other three a started game has no seat.
    if game != "drive" and status != "waiting":
        return False
    return count < (cap or 0)


def state(conn, game, code):
    """What an invite card shows. ``{"exists": False}`` once the room is gone."""
    if game not in GAMES or not code:
        return {"exists": False}
    rooms, players, _host, label = GAMES[game]
    if not _has(conn, rooms):
        return {"exists": False}
    row = conn.execute(text(
        "SELECT g.id, g.status, g.max_players, COALESCE(g.last_activity_at, g.created_at),"
        " (SELECT COUNT(*) FROM %s p WHERE p.game_id = g.id)"
        " FROM %s g WHERE g.code = :c" % (players, rooms)), {"c": code.upper()}).first()
    if not row:
        return {"exists": False}
    _id, status, cap, _touched, count = row
    if status == "ended":
        return {"exists": False}
    return {"exists": True, "game": game, "label": label, "code": code.upper(),
            "status": status or "waiting", "players": count, "max": cap,
            "joinable": _joinable(game, status or "waiting", count, cap),
            "url": join_url(game, code.upper())}


def mine(conn, user_id):
    """Every open room ``user_id`` is sitting in, newest first - what they can
    invite somebody into from anywhere on the site."""
    out = []
    cutoff = (datetime.utcnow() - FRESH_FOR).strftime("%Y-%m-%d %H:%M:%S")
    for game, (rooms, players, _host, _label) in GAMES.items():
        if not (_has(conn, rooms) and _has(conn, players)):
            continue
        rows = conn.execute(text(
            "SELECT g.code, COALESCE(g.last_activity_at, g.created_at) AS t FROM %s g"
            " JOIN %s p ON p.game_id = g.id"
            " WHERE p.user_id = :u AND g.status != 'ended' AND t > :cut"
            % (rooms, players)), {"u": user_id, "cut": cutoff})
        for code, touched in rows:
            s = state(conn, game, code)
            if s["exists"]:
                s["touched"] = str(touched)
                out.append(s)
    out.sort(key=lambda s: s["touched"], reverse=True)
    return out


def is_in(conn, user_id, game, code):
    """Whether ``user_id`` is in that room - you can only invite people into a
    room you are in, or an invite would be a way to send anybody anywhere."""
    if game not in GAMES:
        return False
    rooms, players, _host, _label = GAMES[game]
    if not (_has(conn, rooms) and _has(conn, players)):
        return False
    return conn.execute(text(
        "SELECT 1 FROM %s g JOIN %s p ON p.game_id = g.id"
        " WHERE g.code = :c AND p.user_id = :u AND g.status != 'ended'"
        % (rooms, players)), {"c": (code or "").upper(), "u": user_id}).first() is not None
