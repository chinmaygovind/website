"""`/admin`: Drive on one screen, for Chinmay and nobody else.

Everything here is read from what the service already writes - `site_visits`
(one row per request, from `visits.py`), `user_presence`, the Drive tables -
so there is nothing new to collect and nothing to keep in step. It is
Drive-only on purpose: `cgovind.com/admin` is the site-wide console, and every
session here links to its clickpath there rather than drawing it twice.

**Scanner floods are left out of every number.** A vulnerability scanner
arrives as hundreds or thousands of requests from one address in a day with no
cookie kept, so every request is a new visitor and a new session - one of them
made a single afternoon look like twenty times the site's best day. A real
browser keeps its `cgv` cookie. So an (address, day) where at least
`FLOOD_VISITORS` visitors each made about one request is dropped whole
(`_flood_keys`). The `is_bot` user-agent flag is applied as well, but scanners
send ordinary browser strings, which is why it is not enough on its own.

Every query is bounded (`WINDOW` days) and rides `ix_visits_ts`. SQLite-only
where it uses `julianday`/`substr` on the text timestamps, which is what both
the box and the suite run.
"""

import json as json_mod
import re
from datetime import datetime, timedelta

from flask import abort, render_template
from sqlalchemy import text

from app import (app, get_current_user, get_effective_name, daily_date,
                 MAIN_SITE_URL, LIVE_PHASES, _rooms, _humans)
from models import (db, DriveUserTrack, DriveRace, DriveRunCheck,
                    DriveCheatFlag, DriveStats, DriveDailyTime)
import maker
import tracks as tracks_mod

WINDOW = 30
FLOOD_VISITORS = 20


def _since(days):
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _q(sql, **params):
    return db.session.execute(text(sql), params).fetchall()


def _flood_keys():
    """`ip|day` for every flood in the window. Tens of rows at most."""
    return [r[0] for r in _q(
        "SELECT ip || '|' || substr(ts, 1, 10) FROM site_visits"
        " WHERE service = 'drive' AND ts >= :since"
        " GROUP BY ip, substr(ts, 1, 10)"
        " HAVING COUNT(DISTINCT visitor_id) >= :n"
        "    AND COUNT(DISTINCT visitor_id) >= 0.9 * COUNT(*)",
        since=_since(WINDOW), n=FLOOD_VISITORS)]


def _real(floods):
    """The WHERE clause and params for a real Drive visit in the window."""
    params = {"since": _since(WINDOW)}
    where = "service = 'drive' AND is_bot = 0 AND ts >= :since"
    if floods:
        names = []
        for i, k in enumerate(floods):
            params["f%d" % i] = k
            names.append(":f%d" % i)
        where += " AND (ip || '|' || substr(ts, 1, 10)) NOT IN (%s)" % ", ".join(names)
    return where, params


def _players(where, params):
    now = datetime.utcnow()
    cut = {d: (now - timedelta(days=d)).strftime("%Y-%m-%d %H:%M:%S")
           for d in (1, 7)}
    row = _q(
        "SELECT"
        " COUNT(DISTINCT CASE WHEN ts >= :d1 THEN visitor_id END),"
        " COUNT(DISTINCT CASE WHEN ts >= :d7 THEN visitor_id END),"
        " COUNT(DISTINCT visitor_id),"
        " COUNT(DISTINCT CASE WHEN ts >= :d7 THEN user_id END),"
        " SUM(CASE WHEN ts >= :d7 AND path = '/api/run' AND status = 200 THEN 1 ELSE 0 END)"
        " FROM site_visits WHERE " + where,
        d1=cut[1], d7=cut[7], **params)[0]
    back = _q(
        "SELECT COUNT(*) FROM (SELECT visitor_id FROM site_visits WHERE " + where +
        " GROUP BY visitor_id HAVING MAX(ts) >= :d7 AND MIN(ts) < :d7)",
        d7=cut[7], **params)[0][0]
    new = _q(
        "SELECT COUNT(*) FROM users u WHERE u.created_at >= :d7"
        " AND EXISTS (SELECT 1 FROM site_visits s WHERE s.user_id = u.id"
        "             AND s.service = 'drive')", d7=cut[7])[0][0]
    hours = (db.session.query(db.func.sum(DriveStats.drive_time)).scalar() or 0) / 3600
    return {"day": row[0], "week": row[1], "month": row[2],
            "signed_in": row[3] or 0, "laps": row[4] or 0,
            "returning": back, "returning_pct": round(100 * back / row[1]) if row[1] else 0,
            "new_accounts": new, "hours": hours}


def _daily_series(where, params):
    """Per UTC day in the window: players, laps finished."""
    got = {r[0]: (r[1], r[2] or 0) for r in _q(
        "SELECT substr(ts, 1, 10), COUNT(DISTINCT visitor_id),"
        " SUM(CASE WHEN path = '/api/run' AND status = 200 THEN 1 ELSE 0 END)"
        " FROM site_visits WHERE " + where + " GROUP BY 1", **params)}
    today = datetime.utcnow().date()
    out = []
    for i in range(WINDOW - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        p, l = got.get(d, (0, 0))
        out.append({"day": d, "players": p, "laps": l})
    return out


def _funnel(where, params):
    """Real sessions this week, and how far each got."""
    r = _q(
        "SELECT COUNT(*), SUM(started > 0), SUM(finished > 0), SUM(finished)"
        " FROM (SELECT session_id,"
        "  SUM(path = '/api/start') AS started,"
        "  SUM(path = '/api/run' AND status = 200) AS finished"
        "  FROM site_visits WHERE " + where + " AND ts >= :d7"
        "  GROUP BY session_id)",
        d7=_since(7), **params)[0]
    pbs = _q("SELECT COUNT(*) FROM drive_times WHERE updated_at >= :d7",
             d7=_since(7))[0][0]
    sessions, started, finished, laps = (r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0)
    steps = [("Sessions", sessions), ("Started a lap", started),
             ("Finished a lap", finished), ("Personal bests", pbs)]
    top = max(sessions, 1)
    return {"steps": [{"label": k, "n": n, "pct": round(100 * n / top)} for k, n in steps],
            "laps_per": round(laps / finished, 1) if finished else 0}


def _tracks():
    """All-time starts per track, most and least driven in the pool."""
    got = {r[0]: (r[1], r[2]) for r in _q(
        "SELECT track, SUM(starts), COUNT(DISTINCT user_id) FROM drive_starts GROUP BY track")}
    rows = [{"name": t["name"], "slug": t["slug"],
             "starts": got.get(t["slug"], (0, 0))[0] or 0,
             "drivers": got.get(t["slug"], (0, 0))[1]} for t in tracks_mod.TRACKS]
    rows.sort(key=lambda r: -r["starts"])
    top = max((r["starts"] for r in rows), default=1) or 1
    for r in rows:
        r["pct"] = round(100 * r["starts"] / top)
    return {"top": rows[:6], "bottom": rows[-3:][::-1]}


def _sessions(where, params):
    rows = _q(
        "SELECT session_id, MIN(ts), MAX(ts), MAX(user_id), COUNT(*),"
        " SUM(path = '/api/start'), SUM(path = '/api/run' AND status = 200),"
        " (julianday(MAX(ts)) - julianday(MIN(ts))) * 1440,"
        " MAX(referrer)"
        " FROM site_visits WHERE " + where + " AND ts >= :d7"
        " GROUP BY session_id ORDER BY MAX(ts) DESC LIMIT 40",
        d7=_since(7), **params)
    ids = {r[3] for r in rows if r[3]}
    names = dict(_q("SELECT id, username FROM users WHERE id IN (%s)"
                    % ",".join(str(int(i)) for i in ids))) if ids else {}
    out = []
    for sid, first, last, uid, reqs, starts, laps, mins, ref in rows:
        host = re.sub(r"^https?://(www\.)?", "", ref or "").split("/")[0]
        out.append({"id": sid, "at": first[:16], "last": last,
                    "who": names.get(uid), "reqs": reqs, "starts": starts or 0,
                    "laps": laps or 0, "mins": round(mins or 0),
                    "from": "" if host.endswith("cgovind.com") else host,
                    "href": "%s/admin/sessions/%s" % (MAIN_SITE_URL, sid)})
    return out


def _online():
    cut = (datetime.utcnow() - timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
    people = _q(
        "SELECT u.username, p.detail FROM user_presence p JOIN users u ON u.id = p.user_id"
        " WHERE p.service = 'drive' AND p.last_seen >= :cut ORDER BY p.last_seen DESC",
        cut=cut)
    anon = _q(
        "SELECT COUNT(DISTINCT visitor_id) FROM site_visits"
        " WHERE service = 'drive' AND is_bot = 0 AND user_id IS NULL AND ts >= :cut",
        cut=cut)[0][0]
    live = [c for c, r in _rooms.items() if r.get("phase") in LIVE_PHASES]
    return {"people": people, "guests": anon, "races": len(live),
            "racers": sum(len(_humans(_rooms[c])) for c in live)}


def _multiplayer():
    since = datetime.utcnow() - timedelta(days=WINDOW)
    races = DriveRace.query.filter(DriveRace.created_at >= since).all()
    today = datetime.utcnow().date()
    per = {}
    cars, humans, flagged = 0, 0, 0
    for r in races:
        per[r.created_at.date()] = per.get(r.created_at.date(), 0) + 1
        try:
            field = json_mod.loads(r.cars_json or "[]")
        except ValueError:
            field = []
        cars += len(field)
        if field and all("bot" in c for c in field):
            flagged += 1
            humans += sum(1 for c in field if not c["bot"])
    series = [per.get(today - timedelta(days=i), 0) for i in range(13, -1, -1)]
    return {"total": len(races), "series": series, "peak": max(series) or 1,
            "field": round(cars / len(races), 1) if races else 0,
            "humans": round(humans / flagged, 1) if flagged else None}


def _integrity():
    since = datetime.utcnow() - timedelta(days=WINDOW)
    checks = dict(db.session.query(DriveRunCheck.status, db.func.count())
                  .filter(DriveRunCheck.queued_at >= since)
                  .group_by(DriveRunCheck.status).all())
    rules = {}
    for (reasons,) in (db.session.query(DriveCheatFlag.reasons_json)
                       .filter(DriveCheatFlag.created_at >= since)):
        try:
            got = json_mod.loads(reasons or "{}")
        except ValueError:
            continue
        for k, n in got.items():
            k = re.sub(r"\d+(\.\d+)?", "N", k)
            rules[k] = rules.get(k, 0) + (n if isinstance(n, int) else 1)
    return {"checks": checks,
            "rules": sorted(rules.items(), key=lambda kv: -kv[1])[:5]}


def _dailies():
    today = daily_date()
    q = maker._review_queue()
    live_today = DriveUserTrack.query.filter_by(daily_on=today, status="live").first()
    return {
        "queue": len(q),
        "needs_fix": DriveUserTrack.query.filter_by(status="needs_fix").count(),
        "ahead": DriveUserTrack.query.filter(DriveUserTrack.daily_on > today,
                                             DriveUserTrack.status == "live").count(),
        "next_day": maker._next_free_daily(),
        "today": live_today,
        "today_drivers": DriveDailyTime.query.filter_by(day=today).count(),
    }


def _safely(fn, *a):
    """One failed panel is a blank panel, never a 500 on the whole console."""
    try:
        return fn(*a)
    except Exception as e:                                # pragma: no cover
        db.session.rollback()
        app.logger.warning("admin dashboard: %s failed: %s", fn.__name__, e)
        return None


@app.route("/admin")
def admin_home():
    user = get_current_user()
    if not maker._is_admin(user) or maker._make_forbidden():
        abort(404)
    floods = _safely(_flood_keys) or []
    where, params = _real(floods)
    series = _safely(_daily_series, where, params) or []
    return render_template(
        "admin_home.html", user=user, name=get_effective_name(),
        active_page="admin",
        players=_safely(_players, where, params),
        series=series,
        series_peak=max([s["players"] for s in series] or [1]) or 1,
        laps_peak=max([s["laps"] for s in series] or [1]) or 1,
        funnel=_safely(_funnel, where, params),
        tracks=_safely(_tracks),
        sessions=_safely(_sessions, where, params) or [],
        online=_safely(_online),
        mp=_safely(_multiplayer),
        integrity=_safely(_integrity),
        dailies=_safely(_dailies))
