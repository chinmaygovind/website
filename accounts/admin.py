"""The one console: everything this box already records, finally readable.

Nothing here collects anything new. Five services have been writing
``site_visits`` - a row per request, with the address, the referrer, the agent,
a stitched session id and a crawler flag - since visit logging landed, and the
only thing that has ever read it back is the green dot on a profile.
``drive_cheat_flags`` is blunter still: its own docstring says it "is written
and never queried, which is the intended state until there is something to read
it with". This is that something. It is the missing *read* path, not a new
write one, which is also why every route on it is a GET.

Three properties hold it together, and each is load-bearing.

**A stranger gets a 404, not a 403.** Logged out, or logged in as anybody else,
``/admin`` is the Mario game - byte for byte what any other address that is not
there returns. A 403 saying "not for you" is a 403 saying "there is a console
here", and nothing on the site links to this one. The gate is a blueprint-wide
``before_request`` rather than a decorator per route, so a route added to this
file next year is gated by *existing* rather than by somebody remembering; on a
page that prints email addresses and IP addresses that is the difference worth
paying a whole blueprint for.

**It is read-only, and that is a security property.** No POST, no form, no
write anywhere in this module. So there is no CSRF surface to get wrong, no
confirmation dialog to mis-wire, and if the gate above ever did fail the worst
case is a disclosure rather than a deleted account.

**A missing table is zero, not a stack trace.** Every query here reads a table
some *other* service owns, exactly as ``gamestats`` does, and for the same
reason it uses raw SQL and ``_table_exists``: a box without King of Tokyo
installed, or a fresh clone whose database holds nothing but ``users``, is an
ordinary state this page has to render. An admin console that 500s on an empty
database is an admin console you cannot use on the day you most need it.
"""

import json
import re
from datetime import datetime, timedelta

from flask import (Blueprint, abort, current_app, render_template, request,
                   session)

from . import gamestats, presence
from .gamestats import GAMES, GAME_BY_KEY, DRIVE_TRACKS
# Package-internal helpers, read from inside the same package. They are the
# ones that make a query against another service's schema safe - `_rows`
# swallows the error a missing column raises, `_table_exists` answers for a
# game that was never installed - and a second copy of that care here would be
# a second copy to get wrong.
from .gamestats import _row, _rows, _table_exists, _when
from .models import User, db

# ``visits`` lives at the repo root beside ``app.py`` rather than in this
# package, because four other services carry byte-identical copies of it and it
# must stay one file. Imported defensively for the reason ``routes._status_for``
# does it: a checkout without it should render a console with the visit panels
# empty, not raise ImportError at boot and take the whole site with it.
try:
    import visits
except ImportError:                                      # pragma: no cover
    visits = None

bp = Blueprint("admin", __name__, url_prefix="/admin",
               template_folder="templates")

# How much of the log a page reads unless asked otherwise, and the ceiling on
# asking. Bounded on purpose: every query below rides `ix_visits_ts`, and an
# unbounded one would degrade quietly as the table grows rather than loudly.
DEFAULT_DAYS = 30
MAX_DAYS = 365
SESSIONS_PER_PAGE = 40
ACCOUNTS_PER_PAGE = 100


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def admin_names():
    """Who may read this, folded to lower case.

    Held in app config rather than read from the environment at import, so a
    test can move it: ``conftest`` builds the app once for the whole session,
    which makes an import-time ``os.environ`` read impossible to override
    afterwards. The default is ``chinmay`` and that is deliberate too - the
    deploy explicitly never touches the box's ``.env``, so anything that
    *required* a new variable there would need a hand-run SSH step before the
    console worked in production.
    """
    raw = current_app.config.get("ADMIN_USERNAMES", "")
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


def admin_user():
    """The signed-in admin, or None. Never raises, never redirects."""
    uid = session.get("user_id")
    if not uid:
        return None
    user = db.session.get(User, uid)
    if user is None or user.is_bot:
        return None
    return user if (user.username or "").lower() in admin_names() else None


@bp.before_request
def _admin_only():
    """404 for everybody else - see this module's docstring.

    On the blueprint, so it covers every route here including ones that do not
    exist yet. ``abort(404)`` falls through to ``app.errorhandler(404)``, which
    serves ``site/404.html``: the same Mario game a typo in the address bar
    gets, with nothing in it that says this URL is special.
    """
    if admin_user() is None:
        abort(404)


@bp.app_context_processor
def _inject_admin():
    """So a template can ask whether it is being read by an admin.

    Registered app-wide, like the accounts blueprint's own context processor,
    because the answer is also what decides whether the ordinary pages show a
    link back into the console.
    """
    try:
        me = admin_user()
    except Exception:                                    # noqa: BLE001
        # Runs on *every* template in the app, including the 404 page, which
        # can be rendered from places with no database behind them at all.
        me = None
    return {"admin_me": me, "game_by_key": GAME_BY_KEY}


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

def _clamp(value, low, high, fallback):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def _window():
    """``(days, cutoff_datetime)`` for this request."""
    days = _clamp(request.args.get("days"), 1, MAX_DAYS, DEFAULT_DAYS)
    return days, datetime.utcnow() - timedelta(days=days)


def _stamp(dt):
    """A datetime in the text shape ``site_visits.ts`` is stored in.

    Delegated to ``visits`` rather than re-stating its format, because the two
    agreeing is the whole basis of every comparison below and a second copy of
    ``"%Y-%m-%d %H:%M:%S.%f"`` here is a second thing to keep in step.
    """
    return visits.stamp(dt) if visits else dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _parse(value):
    return visits.parse(value) if visits else _when(value)


def _have_visits(conn):
    return visits is not None and _table_exists(conn, "site_visits")


def _bots_wanted():
    return request.args.get("bots") in ("1", "true", "yes", "on")


# What a user agent actually is, in the two words worth showing in a table.
# Ordered, because every one of these strings contains several of the others:
# Edge says "Chrome", Chrome says "Safari", and everything says "Mozilla/5.0".
# First match wins, so the list runs most-specific first.
_BROWSERS = (
    ("Edge", r"Edg(?:e|A|iOS)?/(\d+)"),
    ("Opera", r"OPR/(\d+)"),
    ("Samsung", r"SamsungBrowser/(\d+)"),
    ("Firefox", r"(?:Firefox|FxiOS)/(\d+)"),
    ("Chrome", r"(?:Chrome|CriOS)/(\d+)"),
    ("Safari", r"Version/(\d+).*Safari"),
)
_PLATFORMS = (
    ("iPhone", r"iPhone"),
    ("iPad", r"iPad"),
    ("Android", r"Android"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("Windows", r"Windows NT"),
    ("Linux", r"Linux|X11"),
)


def _agent(ua):
    """``Chrome 130 · macOS`` out of ninety characters of Mozilla cosplay.

    Deliberately a dozen patterns rather than a user-agent library: this is a
    convenience for reading a table, nothing is filtered or counted by it, and
    the full string is one hover away in every place this is shown. Anything
    unrecognised keeps its first forty characters, which is how a new browser
    or an odd script stays legible instead of becoming "Unknown".
    """
    if not ua:
        return "—"
    browser = next((("%s %s" % (name, m.group(1))) for name, pat in _BROWSERS
                    for m in [re.search(pat, ua)] if m), None)
    platform = next((name for name, pat in _PLATFORMS if re.search(pat, ua)), None)
    if browser and platform:
        return "%s · %s" % (browser, platform)
    if browser or platform:
        return browser or platform
    return ua[:40]


def _duration(seconds):
    """``4m 12s``. Whole units, and never an empty string for a real length."""
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm %02ds" % (seconds // 60, seconds % 60)
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


@bp.app_template_filter("commas")
def _commas(n):
    try:
        return "{:,}".format(int(n or 0))
    except (TypeError, ValueError):
        return n


@bp.app_template_filter("duration")
def _duration_filter(seconds):
    return _duration(seconds)


@bp.app_template_filter("ago")
def _ago_filter(when):
    return presence.ago(when) if when else "never"


# ---------------------------------------------------------------------------
# Counting what has been played
# ---------------------------------------------------------------------------
#
# Never by summing `*_stats.games_played`: that column is per player, so one
# four-handed game of King of Tokyo would count as four. Each game is counted
# from the table that holds one row per *game*.

def game_counts(conn):
    """``{game_key: games finished}`` plus Drive's solo laps, counted honestly."""
    counts = {}

    # TTR keeps a row per player per game, so the games are the distinct codes.
    if _table_exists(conn, "game_results"):
        row = _row(conn, "SELECT COUNT(DISTINCT game_code) AS n FROM game_results")
        counts["ttr"] = (row or {}).get("n") or 0

    for key in ("ers", "kot"):
        if _table_exists(conn, key + "_games"):
            row = _row(conn, "SELECT COUNT(*) AS n FROM %s_games"
                             " WHERE status = 'ended'" % key)
            counts[key] = (row or {}).get("n") or 0

    # `drive_races` is one row per race actually run, with an indexed
    # `created_at`. gamestats reads races back out of `drive_games.results_json`
    # because it needs one player's standings; for a total, the race table is
    # both cheaper and the thing that cannot disagree with itself.
    if _table_exists(conn, "drive_races"):
        counts["drive"] = (_row(conn, "SELECT COUNT(*) AS n FROM drive_races")
                           or {}).get("n") or 0

    # Laps are counted apart from the total on purpose. Most of Drive is one
    # person alone against a clock, which is a real thing somebody did and is
    # not a game; folding it in would quietly make "games played" mean two
    # different things at once.
    laps = 0
    if _table_exists(conn, "drive_stats"):
        laps = (_row(conn, "SELECT COALESCE(SUM(runs), 0) AS n FROM drive_stats")
                or {}).get("n") or 0

    return counts, laps


def played_for(conn, user_ids):
    """``{user_id: {game_key: games played}}`` for a page of people.

    Per user, ``games_played`` *is* the right column - the double counting the
    function above avoids only happens when you add different people's rows
    together. Four queries for a page rather than four per row, like
    ``gamestats.ratings_for`` beside it.
    """
    out = {uid: {} for uid in user_ids}
    if not user_ids:
        return out
    wanted = set(user_ids)
    for key in ("ttr", "ers", "kot", "drive"):
        table = key + "_stats"
        if not _table_exists(conn, table):
            continue
        column = "races" if key == "drive" else "games_played"
        for r in _rows(conn, "SELECT user_id, %s AS n FROM %s" % (column, table)):
            if r["user_id"] in wanted:
                out[r["user_id"]][key] = r["n"] or 0
    return out


def recent_games(conn, limit=12):
    """The last few finished games, whichever game they were.

    Four sources with four shapes, merged and re-sorted, the same way
    ``gamestats._drive_recent`` interleaves laps with races. Each is read a
    little past ``limit`` so that the merge has something to choose between,
    and a game whose result cannot be read - an abandoned replay with no
    standings - is skipped rather than shown as a game nobody won.
    """
    out = []

    if _table_exists(conn, "game_results"):
        # One row per player, so the game is the group and the winner is the
        # placement-1 row in it.
        for r in _rows(conn,
                       "SELECT g.game_code, MAX(g.played_at) AS at,"
                       "       COUNT(*) AS players,"
                       "       MAX(CASE WHEN g.placement = 1 THEN u.username END) AS winner"
                       "  FROM game_results g LEFT JOIN users u ON u.id = g.user_id"
                       " GROUP BY g.game_code ORDER BY at DESC LIMIT :n", n=limit):
            out.append({"game": "ttr", "code": r["game_code"], "when": _when(r["at"]),
                        "players": r["players"], "winner": r["winner"]})

    for key in ("ers", "kot"):
        if not _table_exists(conn, key + "_games"):
            continue
        for r in _rows(conn,
                       "SELECT g.code, g.last_activity_at, g.created_at, g.state_json,"
                       "       COUNT(p.id) AS players"
                       "  FROM {k}_games g LEFT JOIN {k}_players p ON p.game_id = g.id"
                       " WHERE g.status = 'ended'"
                       " GROUP BY g.id ORDER BY g.id DESC LIMIT :n".format(k=key),
                       n=limit):
            try:
                standings = (json.loads(r["state_json"] or "{}") or {}).get("standings") or []
            except ValueError:
                standings = []
            first = next((s for s in standings if s.get("place") == 1), None)
            out.append({"game": key, "code": r["code"],
                        "when": _when(r["last_activity_at"] or r["created_at"]),
                        "players": r["players"] or len(standings),
                        "winner": (first or {}).get("name")})

    if _table_exists(conn, "drive_races"):
        for r in _rows(conn, "SELECT code, track, cars_json, created_at"
                             " FROM drive_races ORDER BY id DESC LIMIT :n", n=limit):
            try:
                cars = json.loads(r["cars_json"] or "[]")
            except ValueError:
                cars = []
            out.append({"game": "drive", "code": r["code"],
                        "when": _when(r["created_at"]),
                        "players": len(cars) or None,
                        "detail": DRIVE_TRACKS.get(r["track"], r["track"]),
                        "winner": (cars[0].get("name") if cars
                                   and isinstance(cars[0], dict) else None)})

    out.sort(key=lambda e: e["when"] or datetime.min, reverse=True)
    for entry in out:
        entry["meta"] = GAME_BY_KEY.get(entry["game"])
    return out[:limit]


def cheat_flags(conn, limit=10):
    """Drive's anti-cheat findings, which nothing has ever read.

    ``drive_cheat_flags`` is written by the lap verifier and, by its own
    docstring, "never queried" - the verdict is deliberately silent, so the
    only way this was ever going to be seen was a page like this one. A row is
    not an accusation: the checks are calibrated to be wrong in the harmless
    direction, so what is worth reading is the shape of the tally rather than
    its existence. Hence ``strikes`` and the per-rule reasons, not a verdict.
    """
    if not _table_exists(conn, "drive_cheat_flags"):
        return []
    out = []
    for r in _rows(conn,
                   "SELECT f.name, f.user_id, f.track, f.phase, f.strikes,"
                   "       f.reasons_json, f.created_at, u.username"
                   "  FROM drive_cheat_flags f LEFT JOIN users u ON u.id = f.user_id"
                   " ORDER BY f.id DESC LIMIT :n", n=limit):
        try:
            reasons = json.loads(r["reasons_json"] or "{}") or {}
        except ValueError:
            reasons = {}
        out.append({
            "name": r["username"] or r["name"], "username": r["username"],
            "track": DRIVE_TRACKS.get(r["track"], r["track"]),
            "phase": r["phase"], "strikes": r["strikes"] or 0,
            "when": _when(r["created_at"]),
            "reasons": ", ".join("%s×%s" % (k, v) for k, v in
                                 sorted(reasons.items(), key=lambda kv: -kv[1])),
        })
    return out


# ---------------------------------------------------------------------------
# The visit log
# ---------------------------------------------------------------------------

def traffic(conn, cut, days):
    """Visits per day since ``cut``, humans and crawlers apart.

    ``substr(ts, 1, 10)`` is the date, which works because ``visits.TS_FMT``
    puts the year first and pads everything - the same property that lets every
    other comparison in this file be a string comparison. Days with no traffic
    are filled in rather than skipped, or a quiet week would draw as a narrower
    chart instead of an empty one.
    """
    if not _have_visits(conn):
        return []
    rows = {r["day"]: r for r in _rows(
        conn,
        "SELECT substr(ts, 1, 10) AS day,"
        "       SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS humans,"
        "       SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END) AS bots,"
        "       COUNT(DISTINCT visitor_id) AS visitors"
        "  FROM site_visits WHERE ts > :cut GROUP BY day", cut=_stamp(cut))}

    out = []
    start = datetime.utcnow().date() - timedelta(days=days - 1)
    for i in range(days):
        day = start + timedelta(days=i)
        r = rows.get(day.isoformat())
        out.append({"day": day,
                    "humans": (r["humans"] if r else 0) or 0,
                    "bots": (r["bots"] if r else 0) or 0,
                    "visitors": (r["visitors"] if r else 0) or 0})
    peak = max((d["humans"] + d["bots"]) for d in out) if out else 0
    for d in out:
        d["height"] = round(100 * (d["humans"] + d["bots"]) / peak) if peak else 0
        d["human_share"] = (round(100 * d["humans"] / (d["humans"] + d["bots"]))
                            if (d["humans"] + d["bots"]) else 0)
    return out


# One query for the session list. The window functions give the aggregates on
# every row of a session; taking `rn = 1` then hands back the aggregates *and*
# the first row's own columns, which is where the landing page, the address and
# the agent come from. The alternative - a GROUP BY plus a second query per
# session for its first row - is one query per row on the page.
#
# `MAX(user_id)` is how a session that starts anonymous and then logs in gets
# attributed to the person: the id appears partway through, and MAX over the
# partition finds it wherever it is.
_SESSION_SQL = """
WITH windowed AS (
  SELECT session_id, ts, path, query, ip, user_agent, referrer, service,
         ROW_NUMBER()  OVER (PARTITION BY session_id ORDER BY ts, id) AS rn,
         COUNT(*)      OVER (PARTITION BY session_id)                 AS hits,
         MAX(ts)       OVER (PARTITION BY session_id)                 AS ended,
         MAX(user_id)  OVER (PARTITION BY session_id)                 AS who,
         MAX(is_bot)   OVER (PARTITION BY session_id)                 AS botty
    FROM site_visits
   WHERE ts > :cut
)
SELECT session_id, ts AS started, ended, hits, who, botty,
       path AS entry, query, ip, user_agent, referrer, service
  FROM windowed
 WHERE rn = 1 %s
 ORDER BY started DESC
 LIMIT :lim OFFSET :off
"""


def sessions(conn, cut, limit, offset=0, bots=False):
    """Recent visits, one row per session, newest first."""
    if not _have_visits(conn):
        return []
    sql = _SESSION_SQL % ("" if bots else "AND botty = 0")
    rows = _rows(conn, sql, cut=_stamp(cut), lim=limit, off=offset)

    who = [r["who"] for r in rows if r["who"]]
    people = _people(conn, who)
    out = []
    for r in rows:
        started, ended = _parse(r["started"]), _parse(r["ended"])
        out.append({
            "id": r["session_id"],
            "started": started, "ended": ended,
            "seconds": (ended - started).total_seconds() if started and ended else None,
            "hits": r["hits"], "bot": bool(r["botty"]),
            "user": people.get(r["who"]),
            "entry": r["entry"] + (("?" + r["query"]) if r["query"] else ""),
            "ip": r["ip"], "agent": _agent(r["user_agent"]),
            "user_agent": r["user_agent"],
            "referrer": _referrer(r["referrer"]),
            "service": r["service"],
        })
    return out


def session_count(conn, cut, bots=False):
    if not _have_visits(conn):
        return 0
    # Counted over sessions rather than rows, and the bot filter is applied per
    # session (any bot row makes the session one) so that the number below the
    # table can never disagree with the length of the table.
    sql = ("SELECT COUNT(*) AS n FROM ("
           "  SELECT session_id, MAX(is_bot) AS botty FROM site_visits"
           "   WHERE ts > :cut GROUP BY session_id) s"
           "%s" % ("" if bots else " WHERE s.botty = 0"))
    return (_row(conn, sql, cut=_stamp(cut)) or {}).get("n") or 0


def session_detail(conn, session_id):
    """Every request in one session, in the order they happened."""
    if not _have_visits(conn):
        return []
    return [{
        "when": _parse(r["ts"]),
        "method": r["method"], "service": r["service"],
        "path": r["path"] + (("?" + r["query"]) if r["query"] else ""),
        "status": r["status"], "referrer": _referrer(r["referrer"]),
        "user_id": r["user_id"], "ip": r["ip"],
        "agent": _agent(r["user_agent"]), "user_agent": r["user_agent"],
        "bot": bool(r["is_bot"]),
    } for r in _rows(conn,
                     "SELECT ts, method, service, path, query, status, referrer,"
                     "       user_id, ip, user_agent, is_bot"
                     "  FROM site_visits WHERE session_id = :s"
                     " ORDER BY ts, id LIMIT 500", s=session_id)]


def _referrer(url):
    """Just the host, unless it is us - an internal referrer is navigation.

    A table of referrers that is nine tenths ``cgovind.com`` has told you
    nothing; the question the column is read for is who is *sending* people.
    """
    if not url:
        return None
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    host = host[4:] if host.startswith("www.") else host
    if host.endswith("cgovind.com") or host.startswith("localhost"):
        return None
    return host or None


def top_paths(conn, cut, limit=12):
    if not _have_visits(conn):
        return []
    return _rows(conn,
                 "SELECT service, path, COUNT(*) AS hits,"
                 "       COUNT(DISTINCT visitor_id) AS visitors"
                 "  FROM site_visits WHERE ts > :cut AND is_bot = 0"
                 " GROUP BY service, path ORDER BY hits DESC LIMIT :n",
                 cut=_stamp(cut), n=limit)


def top_referrers(conn, cut, limit=10):
    """Where people came from, counted by host rather than by full URL.

    Grouped in Python because the folding is - one host arrives as five URLs
    with five query strings, and ``GROUP BY referrer`` would list all five.
    """
    if not _have_visits(conn):
        return []
    tally = {}
    for r in _rows(conn,
                   "SELECT referrer, COUNT(*) AS hits FROM site_visits"
                   "  WHERE ts > :cut AND is_bot = 0 AND referrer IS NOT NULL"
                   "  GROUP BY referrer", cut=_stamp(cut)):
        host = _referrer(r["referrer"])
        if host:
            tally[host] = tally.get(host, 0) + (r["hits"] or 0)
    return sorted(({"host": h, "hits": n} for h, n in tally.items()),
                  key=lambda e: -e["hits"])[:limit]


def _people(conn, user_ids):
    """``{id: User}`` in one query, for the tables that show a name per row."""
    ids = {int(u) for u in user_ids if u}
    if not ids:
        return {}
    return {u.id: u for u in User.query.filter(User.id.in_(ids)).all()}


# ---------------------------------------------------------------------------
# The numbers at the top
# ---------------------------------------------------------------------------

def headline(conn, cut, days):
    """The tiles: accounts, play, traffic. One dict, read straight by the page."""
    now = datetime.utcnow()
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)

    people = User.query.filter(User.is_bot.isnot(True))
    stats = {
        "accounts": people.count(),
        "bots": User.query.filter(User.is_bot.is_(True)).count(),
        "new_today": people.filter(User.created_at > day_ago).count(),
        "new_week": people.filter(User.created_at > week_ago).count(),
        "new_window": people.filter(User.created_at > cut).count(),
        "days": days,
    }

    counts, laps = game_counts(conn)
    stats["games"] = sum(counts.values())
    stats["per_game"] = counts
    stats["laps"] = laps

    stats.update({"visits": 0, "bot_visits": 0, "visitors": 0,
                  "sessions": 0, "visits_today": 0, "online": 0})
    if _have_visits(conn):
        row = _row(conn,
                   "SELECT SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS humans,"
                   "       SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END) AS bots,"
                   "       COUNT(DISTINCT CASE WHEN is_bot = 0 THEN visitor_id END) AS visitors,"
                   "       COUNT(DISTINCT CASE WHEN is_bot = 0 THEN session_id END) AS sessions"
                   "  FROM site_visits WHERE ts > :cut", cut=_stamp(cut)) or {}
        stats.update({"visits": row.get("humans") or 0,
                      "bot_visits": row.get("bots") or 0,
                      "visitors": row.get("visitors") or 0,
                      "sessions": row.get("sessions") or 0})
        today = _row(conn, "SELECT COUNT(*) AS n FROM site_visits"
                           "  WHERE ts > :cut AND is_bot = 0", cut=_stamp(day_ago))
        stats["visits_today"] = (today or {}).get("n") or 0
        stats["online"] = len(visits.online_now(conn, limit=200))
    return stats


def who_is_online(conn, limit=20):
    """Everybody on the site right now, with the sentence a profile would show."""
    if not _have_visits(conn):
        return []
    rows = visits.online_now(conn, limit=limit)
    people = _people(conn, [r["user_id"] for r in rows])
    out = []
    for r in rows:
        _, line = presence.line_for({"service": r["service"], "detail": r["detail"],
                                     "last_seen": r["last_seen"], "online": True})
        out.append({"user": people.get(r["user_id"]), "text": line,
                    "accent": presence.accent_for(r), "last_seen": r["last_seen"]})
    return [o for o in out if o["user"]]


def new_accounts(conn, limit=12):
    """The newest registrations, with the one thing a public profile omits.

    The email address is here because this is the page where it belongs: it is
    the only field on an account that has never been public, and "who just
    signed up" is not answerable without it when three of them are called some
    variant of the same word.
    """
    users = (User.query.filter(User.is_bot.isnot(True))
             .order_by(User.created_at.desc()).limit(limit).all())
    ids = [u.id for u in users]
    played = played_for(conn, ids)
    seen = visits.presence_for(conn, ids) if _have_visits(conn) else {}
    return [{"user": u, "played": sum(played.get(u.id, {}).values()),
             "seen": (seen.get(u.id) or {}).get("last_seen"),
             "online": bool((seen.get(u.id) or {}).get("online"))} for u in users]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

# `strict_slashes=False` on every route here, and it is the gate's business
# rather than a tidiness preference. Werkzeug's automatic "you missed the
# trailing slash" redirect is raised during *routing*, which happens before any
# `before_request` runs - so with the default, `/admin` answered a logged-out
# stranger with a 308 to `/admin/` while every other address that is not there
# answered 404. That redirect is the console announcing itself, which is the one
# thing the 404 exists to prevent. Matching both spellings on one rule means
# there is no redirect to leak and the gate sees every request.
# `test_the_console_never_redirects_a_stranger` pins it.

@bp.route("/", strict_slashes=False)
def overview():
    days, cut = _window()
    conn = db.session.connection()
    return render_template(
        "admin/overview.html",
        days=days,
        stats=headline(conn, cut, days),
        chart=traffic(conn, cut, days),
        online=who_is_online(conn),
        newest=new_accounts(conn),
        recent=sessions(conn, cut, limit=12, bots=_bots_wanted()),
        games=recent_games(conn),
        paths=top_paths(conn, cut),
        referrers=top_referrers(conn, cut),
        flags=cheat_flags(conn),
        game_list=GAMES,
        bots=_bots_wanted(),
        no_log=not _have_visits(conn),
    )


@bp.route("/sessions", strict_slashes=False)
def session_list():
    days, cut = _window()
    page = _clamp(request.args.get("page"), 1, 10_000, 1)
    bots = _bots_wanted()
    conn = db.session.connection()
    total = session_count(conn, cut, bots=bots)
    rows = sessions(conn, cut, limit=SESSIONS_PER_PAGE,
                    offset=(page - 1) * SESSIONS_PER_PAGE, bots=bots)
    return render_template(
        "admin/sessions.html", rows=rows, page=page, days=days, bots=bots,
        total=total, per_page=SESSIONS_PER_PAGE,
        pages=max(1, -(-total // SESSIONS_PER_PAGE)),
        no_log=not _have_visits(conn),
    )


@bp.route("/sessions/<session_id>", strict_slashes=False)
def session_page(session_id):
    conn = db.session.connection()
    hits = session_detail(conn, session_id)
    if not hits:
        abort(404)
    people = _people(conn, [h["user_id"] for h in hits])
    who = next((people[h["user_id"]] for h in hits
                if h["user_id"] and h["user_id"] in people), None)
    started, ended = hits[0]["when"], hits[-1]["when"]
    return render_template(
        "admin/session.html", hits=hits, session_id=session_id, user=who,
        started=started, ended=ended,
        seconds=(ended - started).total_seconds() if started and ended else None,
    )


@bp.route("/accounts", strict_slashes=False)
def account_list():
    sort = request.args.get("sort", "joined")
    page = _clamp(request.args.get("page"), 1, 10_000, 1)
    conn = db.session.connection()

    query = User.query
    if request.args.get("bots") not in ("1", "true", "yes", "on"):
        query = query.filter(User.is_bot.isnot(True))
    total = query.count()
    users = (query.order_by(User.created_at.desc())
             .limit(ACCOUNTS_PER_PAGE).offset((page - 1) * ACCOUNTS_PER_PAGE).all())

    ids = [u.id for u in users]
    played = played_for(conn, ids)
    ratings = gamestats.ratings_for(conn, ids)
    seen = visits.presence_for(conn, ids) if _have_visits(conn) else {}
    rows = [{"user": u, "played": played.get(u.id, {}),
             "total": sum(played.get(u.id, {}).values()),
             "ratings": ratings.get(u.id, {}),
             "seen": (seen.get(u.id) or {}).get("last_seen"),
             "online": bool((seen.get(u.id) or {}).get("online"))} for u in users]

    # Sorted here rather than in SQL because two of the four keys - games
    # played and last seen - live in other services' tables and in the presence
    # row, so there is no one query to order by. The page is capped at a
    # hundred, which is what makes that affordable.
    #
    # Each key sorts on the *value*, never on `.timestamp()`, and pairs the
    # datetime with a "has one at all" flag rather than substituting a sentinel
    # date. Both halves of that were a bug: `datetime.min.timestamp()` raises
    # outright on macOS (year 1 is not representable), which is what made
    # `?sort=seen` a 500 for every account that had never been seen, and a
    # sentinel would have sorted "never" in among real dates instead of after
    # them. With `reverse` the flag also puts the empty rows last rather than
    # first, which is where "never" belongs.
    sorts = {
        "joined": (lambda r: (r["user"].created_at is not None,
                              r["user"].created_at or datetime.min), True),
        "seen": (lambda r: (r["seen"] is not None, r["seen"] or datetime.min), True),
        "games": (lambda r: r["total"], True),
        "name": (lambda r: (r["user"].display or "").lower(), False),
    }
    key, backwards = sorts.get(sort, sorts["joined"])
    rows.sort(key=key, reverse=backwards)

    return render_template("admin/accounts.html", rows=rows, sort=sort, page=page,
                           total=total, per_page=ACCOUNTS_PER_PAGE,
                           pages=max(1, -(-total // ACCOUNTS_PER_PAGE)),
                           game_list=GAMES)
