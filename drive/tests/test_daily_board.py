"""The daily points: what a day records, what it scores, and when it freezes."""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import boot_app, close_app                      # noqa: E402
import tracks as tracks_mod                                   # noqa: E402
from test_publish import _user, _login, _publish, _row        # noqa: E402
from test_app import _run_payload                             # noqa: E402


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    tracks_mod.set_resolver(None)
    close_app(path, verify="0")


def _daily(A, name, day=None):
    """A live generated track, approved - so scheduled for the next free day -
    or pinned to `day`."""
    c = A.app.test_client()
    _login(c, _user(A, "maker_" + name.split()[0].lower()))
    slug = _publish(A, c, name=name)
    with A.app.app_context():
        row = A.DriveUserTrack.query.filter_by(slug=slug).first()
        row.doc_json = json.dumps(dict(row.doc, generated=True))
        A.db.session.commit()
    _login(c, _admin(A))
    c.post("/admin/tracks/%s/approve" % slug)
    if day is not None:
        with A.app.app_context():
            row = A.DriveUserTrack.query.filter_by(slug=slug).first()
            row.daily_on = day
            A.db.session.commit()
    return slug


def _admin(A):
    with A.app.app_context():
        u = A.User.query.filter_by(username="chinmay").first()
    return u.id if u else _user(A, "chinmay")


def test_a_day_is_an_eastern_day():
    import app as A
    # 3am UTC on the 27th is still 11pm on the 26th in New York.
    assert A.daily_date(datetime(2026, 9, 27, 3, 0)).isoformat() == "2026-09-26"
    assert A.daily_date(datetime(2026, 9, 27, 4, 30)).isoformat() == "2026-09-27"
    ends = A.daily_ends_at()
    assert A.daily_date(ends.replace(tzinfo=None)) == A.daily_date() + timedelta(days=1)


def test_a_lap_on_todays_daily_is_that_days_result(env):
    A = env
    slug = _daily(A, "Foggy Ridge")
    assert _row(A, slug).daily_on == A.daily_date()
    c = A.app.test_client()
    _login(c, _user(A, "ada"))
    with A.app.app_context():
        payload = _run_payload(A, slug)
    assert c.post("/api/run", json=payload).get_json()["ok"]
    with A.app.app_context():
        got = A.DriveDailyTime.query.all()
        assert [(g.track, g.time_ms) for g in got] == [(slug, payload["time_ms"])]


def test_only_the_days_own_track_on_its_own_day_counts(env):
    A = env
    today = A.daily_date()
    slug = _daily(A, "Foggy Ridge", day=today + timedelta(days=1))
    uid = _user(A, "ada")
    with A.app.app_context():
        A._note_daily(uid, "sunrise", 20000)          # a pool track
        A._note_daily(uid, slug, 20000)               # tomorrow's, driven today
        A.db.session.commit()
        assert A.DriveDailyTime.query.count() == 0


def _times(A, slug, day, laps):
    ids = {}
    for name, _ in laps:
        with A.app.app_context():
            u = A.User.query.filter_by(username=name).first()
            ids[name] = u.id if u else None
        ids[name] = ids[name] or _user(A, name)
    with A.app.app_context():
        for name, ms in laps:
            uid = ids[name]
            A.db.session.add(A.DriveDailyTime(day=day, user_id=uid, track=slug,
                                              time_ms=ms))
        A.db.session.commit()


def test_places_score_15_12_10_and_a_tie_shares(env):
    A = env
    y = A.daily_date() - timedelta(days=1)
    slug = _daily(A, "Foggy Ridge", day=y)
    _times(A, slug, y, [("a", 20000), ("b", 21000), ("c", 21000), ("d", 22000)])
    with A.app.app_context():
        days = A._daily_days()
        board = [(r["user"].username, r["pos"], r["points"]) for r in days[0]["rows"]]
        assert board == [("a", 1, 15), ("b", 2, 12), ("c", 2, 12), ("d", 4, 8)]
        pts = {e["user"].username: e["points"] for e in A._daily_points(days)}
        assert pts == {"a": 15, "b": 12, "c": 12, "d": 8}


def test_today_is_a_projection_and_not_in_the_totals(env):
    A = env
    today = A.daily_date()
    y = today - timedelta(days=1)
    s1 = _daily(A, "Foggy Ridge", day=y)
    s2 = _daily(A, "Misty Gap", day=today)
    _times(A, s1, y, [("a", 20000)])
    _times(A, s2, today, [("b", 20000)])
    with A.app.app_context():
        days = A._daily_days()
        assert days[0]["today"] and days[0]["rows"][0]["points"] == 15
        assert [e["user"].username for e in A._daily_points(days)] == ["a"]
        # A week that started today holds nothing finished.
        assert A._daily_points(days, since=today) == []


def test_eleventh_scores_nothing(env):
    A = env
    y = A.daily_date() - timedelta(days=1)
    slug = _daily(A, "Foggy Ridge", day=y)
    _times(A, slug, y, [("p%d" % i, 20000 + i) for i in range(11)])
    with A.app.app_context():
        pts = [r["points"] for r in A._daily_days()[0]["rows"]]
    assert pts == [15, 12, 10, 8, 6, 5, 4, 3, 2, 1, 0]


def test_the_page_has_all_five_boards_and_the_countdown(env):
    A = env
    today = A.daily_date()
    slug = _daily(A, "Foggy Ridge", day=today)
    _times(A, slug, today, [("ada", 20000)])
    html = A.app.test_client().get("/leaderboard").get_data(as_text=True)
    at = [html.index(h) for h in ("Track Records", "Time Trials Leaderboard",
                                  "Multiplayer Leaderboard",
                                  "Daily Tracks Leaderboard", "Today's Daily")]
    assert at == sorted(at)
    assert 'class="dday-clock" data-ends=' in html
    assert ">Projected<" in html and "+15" in html
