"""What each of the five services knows about you, read straight out of the
shared database.

Deliberately raw SQL rather than four more sets of SQLAlchemy models. The games
own their schemas and this page only ever reads them, so mapping
``ers_stats`` / ``kot_stats`` / ``ttr_stats`` / ``drive_*`` here would be five
hundred lines of duplication that has to be kept in step with four other repos'
worth of columns for no gain. What it would *cost* is worse than the
duplication: a mapped table that does not exist is an error at query time, and a
game that is not installed on this box - or a fresh development database with
nothing in it but ``users`` - is a perfectly ordinary state that a profile page
must render, not crash on. ``_table_exists`` makes a missing game a game with no
stats, which is what it is.

The one thing that *is* duplicated on purpose is each game's rating tiers. They
live in that game's ``models.py`` as ``elo_tier``; a name like "Card Shark" is
part of what a rating means, and a profile that showed the number without it
would be the poorer for it. If a game retunes its tiers, this table has to
follow - ``test_tiers_match_the_games`` reads the four ``models.py`` files and
fails when they drift, so the copy cannot rot silently.

**The trainer is the one with no rating, and it says so rather than borrowing
one.** Elo measures you against other people; the poker trainer is one seat and
five bots, and there is nobody on the other side of it to be rated against. So
it fills the same slot with the thing it does measure - hands played and a win
rate in big blinds per hundred - and `for_user` leaves its `elo` at `None`,
which is what stops `tier()` inventing a name for a number that does not exist.

Every game's block answers the same two questions - a headline (rating, tier,
played, won) and a grid of that game's own figures - plus a short list of what
you have been doing lately. What "lately" means differs by game because the
games record different things: TTR keeps a per-player row per game, ERS and KoT
keep a whole-game replay whose standings have to be read out of it, and Drive's
solo record is a personal best per track rather than a game at all.
"""

import json
from datetime import datetime

from sqlalchemy import text


# ---------------------------------------------------------------------------
# Rating tiers - kept in step with each game's models.py by test_tiers_match
# ---------------------------------------------------------------------------

TIERS = {
    "ttr": [(1400, "Rail Baron"), (1250, "Station Master"), (1100, "Engineer"),
            (1000, "Conductor"), (800, "Brakeman"), (0, "Passenger")],
    "ers": [(1400, "Rat King"), (1250, "Card Shark"), (1100, "Sharp"),
            (1000, "Dealer"), (800, "Shuffler"), (0, "Greenhorn")],
    "kot": [(1400, "Kaiju King"), (1250, "City Wrecker"), (1100, "Brawler"),
            (1000, "Monster"), (800, "Lizard"), (0, "Newt")],
    "drive": [(1400, "Works Driver"), (1250, "Ace"), (1100, "Quick"),
              (1000, "Licensed"), (850, "Learner"), (0, "Cone Collector")],
}


# Drive's tracks, so a lap on a profile reads "Jump City" rather than
# "jumpcity". Copied for the same reason and with the same guard as the tiers
# above: importing `drive/tracks` to ask costs 1.7 seconds of geometry assembly
# at boot - it builds every ribbon in the pool - in a process whose entire other
# job is serving static files, to learn sixteen strings.
# `test_track_names_match_drive` reads the pool and fails when the two disagree.
#
# **It went three tracks stale before anybody noticed**, and the guard was green
# the whole time: it read `drive/tracks.py`, that file became the `drive/tracks/`
# package, and `source()` *skipped* a file it could not find instead of failing.
# So Spa, the Costco and Mount Joy were added, and every one of them appeared on
# a profile as its slug. The guard reads the folders now and cannot skip while
# drive is checked out.
DRIVE_TRACKS = {
    "sunrise": "Sunrise Circuit",
    "chicane": "Chicane Park",
    "skyline": "Skyline Sprint",
    "twist": "Twin Loop",
    "heights": "Hairpin Heights",
    "jumpcity": "Jump City",
    "spiral": "Spiral Ascent",
    "eight": "Figure Eight",
    "gauntlet": "The Gauntlet",
    "cove": "Sandy Cove",
    "pillars": "Cloudbreak",
    "rainbow": "Rainbow Road",
    "spa": "Spa-Francorchamps",
    "costco": "Costco Wholesale",
    "bigred": "Big Red",
    "mountjoy": "Mount Joy",
    "tokyo": "Tokyo Drift",
    "shroom": "Shroom Street",
    "silverstone": "Silverstone",
    "monaco": "Monaco",
    "dino": "Dino Park",
    "railway": "Rickety Rails",
}


def tier(game, elo):
    for floor, name in TIERS[game]:
        if (elo or 1000) >= floor:
            return name
    return TIERS[game][-1][1]


# ---------------------------------------------------------------------------
# The games themselves
# ---------------------------------------------------------------------------

# key, display name, where it lives, and the accent colour the landing page
# already gives it (site/index.html's :root). Order is the order they were
# built, which is also the order the tabs appear in.
GAMES = [
    {"key": "ttr",   "name": "Ticket to Ride",     "short": "TTR",
     "url": "https://ttr.cgovind.com",   "accent": "#6b4226"},
    {"key": "ers",   "name": "Egyptian Rat Screw", "short": "ERS",
     "url": "https://ers.cgovind.com",   "accent": "#b8860b"},
    {"key": "kot",   "name": "King of Tokyo",      "short": "KoT",
     "url": "https://kot.cgovind.com",   "accent": "#5c2678"},
    {"key": "drive", "name": "Drive",              "short": "Drive",
     "url": "https://drive.cgovind.com", "accent": "#c0182b"},
    {"key": "gto",   "name": "GTO Trainer",        "short": "GTO",
     "url": "https://gto.cgovind.com",   "accent": "#1f7a4d"},
]

GAME_BY_KEY = {g["key"]: g for g in GAMES}


def table_exists(conn, name):
    """Is this game's table on this box?

    The public spelling of the check below, for the one caller outside this
    module: the directory hides the accounts a game portal made, and "Drive is
    not installed here" has to be an answer rather than an exception for exactly
    the reason every read in this file does.
    """
    return _table_exists(conn, name)


def _table_exists(conn, name):
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name}).first()
    if row:
        return True
    # Not SQLite (a development Postgres, say): ask the catalogue instead, and
    # if that is not available either, assume it is there and let the query say.
    try:
        conn.execute(text("SELECT 1 FROM %s WHERE 1=0" % name))
        return True
    except Exception:                                   # noqa: BLE001
        return False


def _row(conn, sql, **params):
    try:
        return conn.execute(text(sql), params).mappings().first()
    except Exception:                                   # noqa: BLE001
        return None


def _rows(conn, sql, **params):
    try:
        return list(conn.execute(text(sql), params).mappings())
    except Exception:                                   # noqa: BLE001
        return []


def _pct(n, d):
    return round(100 * (n or 0) / d) if d else 0


def _ms(ms):
    """A lap time, the way Drive writes one: 1:12.480."""
    if ms is None:
        return "—"
    return "%d:%06.3f" % (ms // 60000, (ms % 60000) / 1000)


def _when(value):
    """Whatever the database handed back, as a date, or None.

    SQLite hands back a string through raw SQL where SQLAlchemy's mapper would
    have given a datetime, and the games write both ISO strings and epoch
    milliseconds depending on which one is doing the writing.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value / 1000 if value > 1e11 else value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


# --- Ticket to Ride ---------------------------------------------------------

def _ttr(conn, uid):
    if not _table_exists(conn, "ttr_stats"):
        return None
    s = _row(conn, "SELECT * FROM ttr_stats WHERE user_id = :u", u=uid)
    if not s:
        return None
    gp, gw = s["games_played"] or 0, s["games_won"] or 0
    return {
        "elo": s["elo"] or 1000, "played": gp, "won": gw,
        "cells": [
            ("Games", gp), ("Wins", gw), ("Win rate", "%d%%" % _pct(gw, gp)),
            ("Points", "{:,}".format(s["total_points"] or 0)),
            ("Trains placed", "{:,}".format(s["trains_placed"] or 0)),
            ("Tickets drawn", "{:,}".format(s["tickets_drawn"] or 0)),
            ("Points / game", round((s["total_points"] or 0) / gp, 1) if gp else 0),
            ("Trains / game", round((s["trains_placed"] or 0) / gp, 1) if gp else 0),
        ],
    }


def _ttr_recent(conn, uid, limit):
    """TTR keeps a row per player per game, which is exactly this list."""
    out = []
    for r in _rows(conn,
                   "SELECT game_code, played_at, placement, score,"
                   "       elo_before, elo_after, opponents"
                   "  FROM game_results WHERE user_id = :u"
                   " ORDER BY played_at DESC LIMIT :n", u=uid, n=limit):
        try:
            others = json.loads(r["opponents"] or "[]")
        except ValueError:
            others = []
        place = r["placement"]
        out.append({
            "when": _when(r["played_at"]),
            "what": "Game %s" % (r["game_code"] or ""),
            "place": place, "of": len(others) + 1,
            "detail": "%s points" % (r["score"] or 0),
            "delta": (r["elo_after"] - r["elo_before"]
                      if r["elo_after"] is not None and r["elo_before"] is not None
                      else None),
            "won": place == 1,
        })
    return out


# --- the two games that keep a replay instead of a result row ---------------

def _replay_recent(conn, uid, prefix, limit, detail):
    """Recent games for ERS and KoT, whose result lives inside the game.

    Neither keeps a per-player result row: the finishing order is
    ``state_json['standings']``, keyed by the pid (``p<players.id>``) rather
    than by user. So the player rows say which games were yours and what your
    pid was in each, and the standings say how it went. Games with no standings
    are ones that were abandoned rather than finished, and are skipped -
    reporting them as a result would be inventing one.
    """
    if not _table_exists(conn, prefix + "_games"):
        return []
    rows = _rows(conn,
                 "SELECT g.code, g.last_activity_at, g.created_at, g.state_json,"
                 "       p.id AS player_id"
                 "  FROM {p}_players p JOIN {p}_games g ON g.id = p.game_id"
                 " WHERE p.user_id = :u AND g.status = 'ended'"
                 " ORDER BY g.id DESC LIMIT :n".format(p=prefix),
                 u=uid, n=limit * 3)
    out = []
    for r in rows:
        try:
            standings = (json.loads(r["state_json"] or "{}") or {}).get("standings") or []
        except ValueError:
            standings = []
        mine = next((s for s in standings if s.get("pid") == "p%d" % r["player_id"]), None)
        if not mine:
            continue
        out.append({
            "when": _when(r["last_activity_at"] or r["created_at"]),
            "what": "Game %s" % r["code"],
            "place": mine.get("place"), "of": len(standings),
            "detail": detail(mine),
            "delta": None,
            "won": mine.get("place") == 1,
        })
        if len(out) >= limit:
            break
    return out


# --- Egyptian Rat Screw -----------------------------------------------------

def _ers(conn, uid):
    if not _table_exists(conn, "ers_stats"):
        return None
    s = _row(conn, "SELECT * FROM ers_stats WHERE user_id = :u", u=uid)
    if not s:
        return None
    gp, gw = s["games_played"] or 0, s["games_won"] or 0
    won, false = s["slaps_won"] or 0, s["false_slaps"] or 0
    samples = s["reaction_samples"] or 0
    avg = round((s["reaction_ms_total"] or 0) / samples) if samples else None
    return {
        "elo": s["elo"] or 1000, "played": gp, "won": gw,
        "cells": [
            ("Games", gp), ("Wins", gw), ("Win rate", "%d%%" % _pct(gw, gp)),
            ("Slaps won", "{:,}".format(won)),
            ("Slap accuracy", "%d%%" % _pct(won, won + false)),
            ("Missed slaps", "{:,}".format(false)),
            ("Average slap", "%dms" % avg if avg else "—"),
            ("Fastest slap", "%dms" % s["fastest_slap_ms"] if s["fastest_slap_ms"] else "—"),
            ("Cards won", "{:,}".format(s["cards_won"] or 0)),
            ("Piles won", "{:,}".format(s["piles_won"] or 0)),
        ],
    }


# --- King of Tokyo ----------------------------------------------------------

def _kot(conn, uid):
    if not _table_exists(conn, "kot_stats"):
        return None
    s = _row(conn, "SELECT * FROM kot_stats WHERE user_id = :u", u=uid)
    if not s:
        return None
    gp, gw = s["games_played"] or 0, s["games_won"] or 0
    return {
        "elo": s["elo"] or 1000, "played": gp, "won": gw,
        "cells": [
            ("Games", gp), ("Wins", gw), ("Win rate", "%d%%" % _pct(gw, gp)),
            ("Victory points", "{:,}".format(s["vp_scored"] or 0)),
            ("VP / game", round((s["vp_scored"] or 0) / gp, 1) if gp else 0),
            ("Best game", s["highest_vp"] or 0),
            ("Damage dealt", "{:,}".format(s["damage_dealt"] or 0)),
            ("Monsters KO'd", s["monsters_koed"] or 0),
            ("Turns in Tokyo", s["tokyo_turns"] or 0),
            ("Cards bought", s["cards_bought"] or 0),
        ],
    }


# --- Drive ------------------------------------------------------------------

def _drive(conn, uid):
    if not _table_exists(conn, "drive_stats"):
        return None
    s = _row(conn, "SELECT * FROM drive_stats WHERE user_id = :u", u=uid)
    if not s:
        return None
    races, wins = s["races"] or 0, s["wins"] or 0
    starts = (_row(conn, "SELECT COALESCE(SUM(starts), 0) AS n FROM drive_starts"
                         " WHERE user_id = :u", u=uid) or {"n": 0})["n"]
    # A retired medal: `author` was strictly faster than gold, so those rows
    # show up as golds rather than as a tier nobody can win any more.
    golds = (s["golds"] or 0) + (s["authors"] or 0)
    return {
        "elo": s["elo"] or 1000, "played": races, "won": wins,
        "medals": [("gold", golds), ("silver", s["silvers"] or 0),
                   ("bronze", s["bronzes"] or 0)],
        "cells": [
            ("Races", races), ("Wins", wins), ("Podiums", s["podiums"] or 0),
            ("Win rate", "%d%%" % _pct(wins, races)),
            ("Runs started", "{:,}".format(max(starts or 0, s["runs"] or 0))),
            ("Runs finished", "{:,}".format(s["runs"] or 0)),
            ("Distance (km)", round((s["distance"] or 0) / 1000, 1)),
            ("Driving (min)", round((s["drive_time"] or 0) / 60)),
        ],
    }


def _drive_recent(conn, uid, limit):
    """Drive's recent list is two different kinds of thing, interleaved.

    A personal best is not a game - it is a lap, set alone against the clock -
    but it is the thing you actually did, and on a site where most of Drive is
    solo it would be a strange history that left it out. Races come from the
    finished-race log on the lobby, whose standings are keyed by pid the same
    way ERS and KoT's are.
    """
    out = []
    for r in _rows(conn,
                   "SELECT track, time_ms, medal, updated_at FROM drive_times"
                   " WHERE user_id = :u ORDER BY updated_at DESC LIMIT :n",
                   u=uid, n=limit):
        medal = "gold" if r["medal"] == "author" else r["medal"]
        out.append({
            "when": _when(r["updated_at"]),
            # A track that has since left the pool keeps its slug rather than
            # vanishing - it is still a lap somebody drove.
            "what": DRIVE_TRACKS.get(r["track"], r["track"]), "kind": "lap",
            "place": None, "of": None,
            "detail": _ms(r["time_ms"]), "medal": medal,
            "delta": None, "won": False,
        })

    if _table_exists(conn, "drive_games"):
        mine = {"p%d" % r["id"] for r in
                _rows(conn, "SELECT id FROM drive_players WHERE user_id = :u", u=uid)}
        for g in _rows(conn, "SELECT results_json FROM drive_games"
                             " WHERE results_json IS NOT NULL AND results_json != '[]'"
                             " ORDER BY id DESC LIMIT 50"):
            try:
                races = json.loads(g["results_json"] or "[]")
            except ValueError:
                continue
            for race in races:
                standings = race.get("standings") or []
                idx = next((i for i, s in enumerate(standings) if s.get("pid") in mine), None)
                if idx is None:
                    continue
                ms = standings[idx].get("ms")
                slug = race.get("track") or ""
                out.append({
                    "when": _when(race.get("t")),
                    "what": "Race · " + DRIVE_TRACKS.get(slug, slug or "unknown track"),
                    "kind": "race",
                    "place": idx + 1, "of": len(standings),
                    "detail": _ms(ms) if ms else "DNF", "medal": None,
                    "delta": None, "won": idx == 0,
                })

    out.sort(key=lambda e: e["when"] or datetime.min, reverse=True)
    return out[:limit]


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def _gto(conn, uid):
    """The poker trainer: hands, not games, and no rating.

    A "win" here is a pot, and pots are won several times an hour, so the
    played/won pair means something different from the other four - which is
    why the headline is the win rate rather than a record. It is stated in big
    blinds per hundred hands, the unit poker actually uses, and it is left out
    entirely below a hundred hands because under that it is noise with a sign
    on it.
    """
    if not _table_exists(conn, "gto_hands"):
        return None
    s = _row(conn, "SELECT COUNT(*) AS hands,"
                   " COALESCE(SUM(result_cents), 0) AS won_cents,"
                   " COALESCE(SUM(bounty_cents), 0) AS bounty_cents,"
                   " COALESCE(SUM(vpip), 0) AS vpip,"
                   " COALESCE(SUM(pfr), 0) AS pfr,"
                   " COALESCE(SUM(won), 0) AS pots"
                   " FROM gto_hands WHERE user_id = :u", u=uid)
    if not s or not s["hands"]:
        return None

    hands = s["hands"]
    sessions = (_row(conn, "SELECT COUNT(*) AS n FROM gto_sessions"
                           " WHERE user_id = :u", u=uid) or {"n": 0})["n"]
    mistakes = (_row(conn, "SELECT COUNT(*) AS n FROM gto_decisions"
                           " WHERE user_id = :u AND verdict = 'error'", u=uid)
                or {"n": 0})["n"] if _table_exists(conn, "gto_decisions") else 0
    decisions = (_row(conn, "SELECT COUNT(*) AS n FROM gto_decisions"
                            " WHERE user_id = :u", u=uid)
                 or {"n": 0})["n"] if _table_exists(conn, "gto_decisions") else 0

    # The blind is 25 cents in every session so far, and reading it per session
    # to weight the rate properly is more machinery than the number deserves on
    # a profile page - the trainer's own stats page is where that lives.
    bb100 = 100.0 * (s["won_cents"] / 25.0) / hands
    rate = "%+.1f bb/100" % bb100 if hands >= 100 else "too few hands to say"

    return {
        "elo": None,
        "headline": "%s hand%s · %s" % ("{:,}".format(hands),
                                        "" if hands == 1 else "s", rate),
        "played": hands, "won": s["pots"],
        "cells": [
            ("Hands", "{:,}".format(hands)),
            ("Sessions", sessions),
            ("Pots won", "{:,}".format(s["pots"])),
            ("VPIP", "%d%%" % _pct(s["vpip"], hands)),
            ("PFR", "%d%%" % _pct(s["pfr"], hands)),
            ("Win rate", rate),
            ("Bounties", "$%.2f" % (s["bounty_cents"] / 100.0)),
            ("Mistakes", "%s of %s" % ("{:,}".format(mistakes),
                                       "{:,}".format(decisions))),
        ],
    }


_STATS = {"ttr": _ttr, "ers": _ers, "kot": _kot, "drive": _drive, "gto": _gto}


def for_user(conn, user_id, recent=8):
    """Every game's block for one user, in ``GAMES`` order.

    A game the user has never played still gets a block, with ``played`` at
    zero - "you have not played this" is worth saying on a profile, and a tab
    that vanishes when you are looking for it is worse than an empty one.
    """
    blocks = []
    for game in GAMES:
        key = game["key"]
        data = _STATS[key](conn, user_id)
        if data is None:
            data = {"elo": None, "played": 0, "won": 0, "cells": []}
        data = dict(game, **data)
        data["tier"] = tier(key, data["elo"]) if data["elo"] is not None else None
        # A service with no rating supplies its own one-line headline instead.
        # Without this the panel would read "rating None - None".
        data.setdefault("headline", None)
        data["recent"] = recent_for(conn, key, user_id, recent) if recent else []
        blocks.append(data)
    return blocks


def _gto_recent(conn, uid, limit):
    """Sessions, not hands.

    A hand is not a thing to list - there are thousands of them and one is
    worth nothing on its own. A sit-down is the unit somebody remembers, and
    what they remember about it is whether they got up ahead.
    """
    if not _table_exists(conn, "gto_sessions"):
        return []
    out = []
    for r in _rows(conn, "SELECT started_at, ended_at, hands, bought_in, stack,"
                         " bounty_cents FROM gto_sessions"
                         " WHERE user_id = :u AND hands > 0"
                         " ORDER BY started_at DESC LIMIT :n", u=uid, n=limit):
        profit = (r["stack"] or 0) - (r["bought_in"] or 0)
        out.append({
            "when": _when(r["ended_at"] or r["started_at"]),
            "what": "%s hand%s" % (r["hands"], "" if r["hands"] == 1 else "s"),
            "kind": "session", "place": None, "of": None,
            "detail": "$%+.2f" % (profit / 100.0), "medal": None,
            "delta": None,
            # There is nobody to beat here, so "won" means the only thing it
            # can mean at a cash game: you got up with more than you sat down
            # with.
            "won": profit > 0,
        })
    return out


def recent_for(conn, key, user_id, limit=8):
    if key == "ttr":
        return _ttr_recent(conn, user_id, limit)
    if key == "ers":
        return _replay_recent(conn, user_id, "ers", limit,
                              lambda s: "%s turns" % s.get("turns_lasted")
                              if s.get("turns_lasted") else "")
    if key == "kot":
        return _replay_recent(conn, user_id, "kot", limit,
                              lambda s: "%s VP" % s.get("vp") if s.get("vp") is not None else "")
    if key == "drive":
        return _drive_recent(conn, user_id, limit)
    if key == "gto":
        return _gto_recent(conn, user_id, limit)
    return []


def ratings_for(conn, user_ids):
    """``{user_id: {game_key: elo}}`` for a list of people, four queries flat.

    The directory lists everybody with all four ratings, so asking per user per
    game would be four hundred queries on a page that wants four.
    """
    out = {uid: {} for uid in user_ids}
    if not user_ids:
        return out
    for key in ("ttr", "ers", "kot", "drive"):
        table = key + "_stats"
        if not _table_exists(conn, table):
            continue
        for r in _rows(conn, "SELECT user_id, elo FROM %s" % table):
            if r["user_id"] in out:
                out[r["user_id"]][key] = r["elo"]
    return out
