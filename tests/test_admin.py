"""The admin console.

Most of this file is about what the console *refuses*, which is the right
proportion: everything it shows is a read of data four other tests already
cover, and the only genuinely new risk it introduces is that somebody who is
not Chinmay can see email addresses and IP addresses. So the gate gets the
first half of the file, including a test that walks the blueprint's own routing
table rather than a hand-written list - a console whose next route arrives
ungated would pass any test that only knows about today's four.

The content half leans on inserting ``site_visits`` rows by hand. That table is
created by raw DDL when the app boots (``visits.init_app``) rather than by
``db.create_all``, so it survives the ``db`` fixture's ``drop_all`` and carries
rows over between tests - hence ``clean_log``, and hence asserting on
distinctive values rather than on counts.
"""

from datetime import datetime, timedelta

import pytest
from flask import url_for
from sqlalchemy import text

import visits
from accounts import admin
from accounts.models import User

PASSWORD = "hunter2hunter2"


def body(resp):
    return resp.data.decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_log(db):
    """Start every test with an empty visit log and no presence rows.

    ``site_visits`` is not a mapped model, so ``db.drop_all()`` leaves it alone
    and one test's traffic would otherwise be the next one's history. The test
    client's *own* requests land in here too, which is realistic and is why the
    assertions below look for values no real request would have.
    """
    for table in ("site_visits", "user_presence"):
        try:
            db.session.execute(text("DELETE FROM " + table))
        except Exception:                                # noqa: BLE001
            db.session.rollback()
    db.session.commit()
    yield


@pytest.fixture
def as_admin(client, make_user):
    """A client logged in as somebody the console accepts."""
    def _login(username="chinmay"):
        uid = make_user(username, password=PASSWORD)
        resp = client.post("/accounts/login",
                           data={"username": username, "password": PASSWORD})
        assert resp.status_code == 302, body(resp)[:400]
        return uid
    return _login


@pytest.fixture
def admin_routes(flask_app):
    """Every URL the admin blueprint answers, read out of the routing table.

    Discovered rather than listed, so a route added to ``accounts/admin.py``
    next year is covered by the gate tests without anybody remembering to come
    back here and add it.
    """
    urls = []
    with flask_app.test_request_context():
        for rule in flask_app.url_map.iter_rules():
            if rule.endpoint.startswith("admin."):
                urls.append(url_for(rule.endpoint,
                                    **{arg: "x" for arg in rule.arguments}))
    assert urls, "no admin routes found - did the blueprint stop registering?"
    return sorted(set(urls))


def visit(db, **kw):
    """One row in the visit log. Defaults are an ordinary human page view."""
    row = {"ts": visits.stamp(kw.pop("at", None) or datetime.utcnow()),
           "service": "site", "visitor_id": "v-test", "session_id": "s-test",
           "user_id": None, "method": "GET", "path": "/", "query": None,
           "status": 200, "referrer": None,
           "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "ip": "203.0.113.9", "is_bot": 0}
    row.update(kw)
    db.session.execute(text(
        "INSERT INTO site_visits (ts, service, visitor_id, session_id, user_id,"
        " method, path, query, status, referrer, user_agent, ip, is_bot)"
        " VALUES (:ts, :service, :visitor_id, :session_id, :user_id, :method,"
        " :path, :query, :status, :referrer, :user_agent, :ip, :is_bot)"), row)
    db.session.commit()


# ---------------------------------------------------------------------------
# The gate - the half of this feature that matters
# ---------------------------------------------------------------------------

def test_a_stranger_sees_nothing_at_all(client, admin_routes):
    """Not 403, not a login page - the same 404 as an address that isn't there.

    A 403 saying "that's not for you" is a 403 saying "there is a console
    here", and nothing on the site links to this one.
    """
    for url in admin_routes:
        resp = client.get(url)
        assert resp.status_code == 404, "%s let a stranger in (%s)" % (url, resp.status_code)


def test_somebody_else_logged_in_sees_nothing_either(client, logged_in, admin_routes):
    logged_in("alice")
    for url in admin_routes:
        assert client.get(url).status_code == 404, "%s let alice in" % url


def test_the_console_never_redirects_a_stranger(client):
    """The trailing-slash redirect was a leak, and this is the test for it.

    Werkzeug raises its "you missed the slash" redirect while *routing*, which
    happens before any ``before_request``, so with default ``strict_slashes``
    the bare ``/admin`` answered a logged-out stranger with a 308 to
    ``/admin/`` while every other missing address answered 404. That difference
    is the console announcing itself.
    """
    reference = client.get("/definitely-not-a-page-here").status_code
    for url in ("/admin", "/admin/", "/admin/sessions", "/admin/sessions/",
                "/admin/accounts", "/admin/accounts/"):
        resp = client.get(url)
        assert resp.status_code == reference == 404, (
            "%s answered %s where a missing page answers %s"
            % (url, resp.status_code, reference))
        assert "Location" not in resp.headers, "%s leaked a redirect" % url


def test_the_admin_gets_in(client, as_admin):
    as_admin("chinmay")
    page = body(client.get("/admin/"))
    assert "Console" in page
    assert "accounts" in page


def test_both_spellings_of_every_address_work_for_the_admin(client, as_admin):
    """`cgovind.com/admin` is what gets typed; `/admin/` is what Flask builds."""
    as_admin("chinmay")
    for url in ("/admin", "/admin/", "/admin/sessions", "/admin/sessions/",
                "/admin/accounts", "/admin/accounts/"):
        assert client.get(url).status_code == 200, "%s did not answer" % url


def test_who_counts_as_an_admin_is_configurable(flask_app, client, as_admin):
    """In app config rather than read from the environment at import, because
    the app is built once for the whole test session."""
    was = flask_app.config["ADMIN_USERNAMES"]
    flask_app.config["ADMIN_USERNAMES"] = "someone-else"
    try:
        as_admin("chinmay")
        assert client.get("/admin/").status_code == 404
    finally:
        flask_app.config["ADMIN_USERNAMES"] = was


def test_more_than_one_name_can_be_listed(flask_app, client, as_admin):
    was = flask_app.config["ADMIN_USERNAMES"]
    flask_app.config["ADMIN_USERNAMES"] = "chinmay, deputy"
    try:
        as_admin("deputy")
        assert client.get("/admin/").status_code == 200
    finally:
        flask_app.config["ADMIN_USERNAMES"] = was


def test_the_admin_name_is_matched_case_insensitively(flask_app, client, as_admin):
    """A username is permanent and its case is whatever it was typed as; the
    gate turning on capitalisation would be a lockout waiting to happen."""
    was = flask_app.config["ADMIN_USERNAMES"]
    flask_app.config["ADMIN_USERNAMES"] = "ChinMay"
    try:
        as_admin("chinmay")
        assert client.get("/admin/").status_code == 200
    finally:
        flask_app.config["ADMIN_USERNAMES"] = was


def test_a_bot_account_with_the_admin_name_is_still_refused(client, db, as_admin):
    """Bots have accounts because the games needed somewhere to hang a rating.
    One of them holding the admin name should not be a way in."""
    uid = as_admin("chinmay")
    db.session.get(User, uid).is_bot = True
    db.session.commit()
    assert client.get("/admin/").status_code == 404


def test_the_console_beats_the_static_catch_all(client, as_admin):
    """`/<path:path>` in app.py would otherwise swallow /admin into the 404
    game. Werkzeug sorts by specificity, and this pins that it stays that way."""
    as_admin("chinmay")
    page = body(client.get("/admin/"))
    assert "Console" in page
    assert "<canvas" not in page, "served the 404 game instead of the console"


def test_the_console_asks_not_to_be_indexed(client, as_admin):
    as_admin("chinmay")
    assert 'name="robots"' in body(client.get("/admin/"))


def test_nothing_on_the_console_writes(flask_app):
    """Read-only is a security property, not a description: no POST means no
    CSRF surface, and a gate that ever failed would leak rather than destroy."""
    for rule in flask_app.url_map.iter_rules():
        if rule.endpoint.startswith("admin."):
            assert rule.methods <= {"GET", "HEAD", "OPTIONS"}, (
                "%s accepts %s" % (rule, rule.methods - {"GET", "HEAD", "OPTIONS"}))


# ---------------------------------------------------------------------------
# What it shows
# ---------------------------------------------------------------------------

def test_a_new_account_appears_with_the_one_thing_a_profile_hides(client, as_admin,
                                                                  make_user):
    as_admin("chinmay")
    make_user("newbie", email="newbie@example.com")
    page = body(client.get("/admin/"))
    assert "newbie" in page
    # The email is the whole reason this list is not just the public directory.
    assert "newbie@example.com" in page


def test_visits_are_grouped_into_sessions(client, db, as_admin):
    as_admin("chinmay")
    start = datetime.utcnow() - timedelta(minutes=10)
    visit(db, session_id="abc123", path="/accounts/chinmay", at=start)
    visit(db, session_id="abc123", path="/", at=start + timedelta(seconds=30))
    visit(db, session_id="abc123", path="/assets/Chinmay_Govind_Resume.pdf",
          at=start + timedelta(seconds=90))

    page = body(client.get("/admin/sessions"))
    assert "abc123" in page, "the session is not listed"
    # "Landed on" is the session's *first* request and not its last. The entry
    # has to be a path distinctive enough to find in the page, which "/" is not.
    assert "/accounts/chinmay" in page
    assert "Chrome" in page, "the user agent was not read"
    assert "203.0.113.9" in page


def test_a_session_shows_its_pages_in_order(client, db, as_admin):
    as_admin("chinmay")
    start = datetime.utcnow() - timedelta(minutes=5)
    visit(db, session_id="clickpath", path="/first", at=start)
    visit(db, session_id="clickpath", path="/second", at=start + timedelta(seconds=10))
    visit(db, session_id="clickpath", path="/third", at=start + timedelta(seconds=20))

    page = body(client.get("/admin/sessions/clickpath"))
    assert page.index("/first") < page.index("/second") < page.index("/third")


def test_a_session_that_never_happened_is_a_404(client, as_admin):
    as_admin("chinmay")
    assert client.get("/admin/sessions/no-such-session").status_code == 404


def test_a_session_is_credited_to_whoever_logged_in_during_it(client, db, as_admin,
                                                              make_user):
    """A visit starts anonymous and the id only appears partway through, which
    is why the query takes MAX(user_id) over the session rather than the first
    row's."""
    as_admin("chinmay")
    uid = make_user("latecomer")
    start = datetime.utcnow() - timedelta(minutes=3)
    visit(db, session_id="signedin", path="/accounts/login", at=start)
    visit(db, session_id="signedin", path="/accounts/settings", user_id=uid,
          at=start + timedelta(seconds=20))

    page = body(client.get("/admin/sessions"))
    assert "latecomer" in page, "the session was left as anonymous"


def test_crawlers_are_hidden_until_you_ask_for_them(client, db, as_admin):
    """visits.py flags rather than filters, and the console keeps that: the row
    is kept, and the default view just does not lead with it."""
    as_admin("chinmay")
    visit(db, session_id="a-person", path="/human-page")
    visit(db, session_id="a-crawler", path="/robot-page", is_bot=1,
          user_agent="Googlebot/2.1")

    without = body(client.get("/admin/sessions"))
    assert "a-person" in without
    assert "a-crawler" not in without, "a crawler was in the default view"

    with_bots = body(client.get("/admin/sessions?bots=1"))
    assert "a-crawler" in with_bots, "asking for crawlers did not produce them"
    assert "a-person" in with_bots


def test_the_window_can_be_widened_and_cannot_be_absurd(client, db, as_admin):
    as_admin("chinmay")
    visit(db, session_id="last-year", path="/old",
          at=datetime.utcnow() - timedelta(days=60))

    assert "last-year" not in body(client.get("/admin/sessions"))
    assert "last-year" in body(client.get("/admin/sessions?days=90"))
    # Out of range, not an error: a bad number falls back rather than 500ing.
    assert client.get("/admin/sessions?days=99999").status_code == 200
    assert client.get("/admin/sessions?days=nonsense").status_code == 200
    assert client.get("/admin/sessions?page=nonsense").status_code == 200


@pytest.mark.parametrize("sort", ["joined", "seen", "games", "name", "nonsense", ""])
def test_every_way_of_sorting_the_accounts_works(client, as_admin, make_user, sort):
    """``?sort=seen`` was a 500 for every account that had never been seen.

    The key was ``-(r["seen"] or datetime.min).timestamp()``, and
    ``datetime.min.timestamp()`` raises on macOS - year 1 is not
    representable - so the one column most likely to be empty was the one that
    took the page down. ``joined`` had the same latent bug for a null
    ``created_at``. Nothing sorts on ``.timestamp()`` any more.
    """
    as_admin("chinmay")
    make_user("neverseen")
    resp = client.get("/admin/accounts?sort=" + sort)
    assert resp.status_code == 200, body(resp)[:500]
    assert "neverseen" in body(resp)


def test_an_account_never_seen_sorts_after_the_ones_that_have_been(client, db,
                                                                   as_admin, make_user):
    """"never" belongs after real dates, not among them - which a sentinel date
    would not have given."""
    as_admin("chinmay")
    seen_uid = make_user("wasseen")
    make_user("neverseen")
    db.session.execute(text(
        "INSERT INTO user_presence (user_id, service, detail, last_seen, updated_at)"
        " VALUES (:u, 'site', NULL, :t, :t)"),
        {"u": seen_uid, "t": visits.stamp(datetime.utcnow() - timedelta(hours=2))})
    db.session.commit()

    page = body(client.get("/admin/accounts?sort=seen"))
    assert page.index("wasseen") < page.index("neverseen")


def test_an_internal_referrer_is_not_a_source(client, db, as_admin):
    """A referrer table that is nine tenths cgovind.com has told you nothing -
    the column is read to find out who is *sending* people."""
    as_admin("chinmay")
    visit(db, session_id="from-inside", path="/a",
          referrer="https://cgovind.com/")
    visit(db, session_id="from-outside", path="/b",
          referrer="https://news.ycombinator.com/item?id=1")

    page = body(client.get("/admin/"))
    assert "news.ycombinator.com" in page
    assert "Sent here by" in page


def test_a_dead_link_is_visible_in_a_clickpath(client, db, as_admin):
    """A 404 in the log is somebody arriving on a broken link, which is most of
    what the log is worth keeping for."""
    as_admin("chinmay")
    visit(db, session_id="brokenlink", path="/old-url-that-moved", status=404)
    page = body(client.get("/admin/sessions/brokenlink"))
    assert "404" in page
    assert "/old-url-that-moved" in page


# ---------------------------------------------------------------------------
# Counting games
# ---------------------------------------------------------------------------

def test_a_four_handed_game_is_one_game(client, db, as_admin):
    """The bug this is here to stop: ``*_stats.games_played`` is per player, so
    summing it across a table turns one four-handed game into four. TTR is
    counted from the distinct game codes in ``game_results`` instead.
    """
    as_admin("chinmay")
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS game_results ("
        " id INTEGER PRIMARY KEY, game_code TEXT, user_id INTEGER,"
        " played_at TEXT, placement INTEGER, score INTEGER,"
        " elo_before INTEGER, elo_after INTEGER, opponents TEXT)"))
    for seat in range(4):
        db.session.execute(text(
            "INSERT INTO game_results (game_code, user_id, played_at, placement,"
            " score) VALUES ('GAME01', :u, '2026-08-01 12:00:00', :p, 100)"),
            {"u": seat + 1, "p": seat + 1})
    db.session.commit()

    conn = db.session.connection()
    counts, _laps = admin.game_counts(conn)
    assert counts["ttr"] == 1, "one game of four players counted as %s" % counts["ttr"]

    db.session.execute(text("DROP TABLE game_results"))
    db.session.commit()


def test_drive_laps_are_counted_apart_from_games(client, db, as_admin):
    """A lap alone against the clock is a real thing somebody did and is not a
    game; folding it into the total would make one number mean two things."""
    as_admin("chinmay")
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS drive_stats ("
        " user_id INTEGER PRIMARY KEY, elo INTEGER, races INTEGER, wins INTEGER,"
        " podiums INTEGER, runs INTEGER, golds INTEGER, silvers INTEGER,"
        " bronzes INTEGER, authors INTEGER, distance REAL, drive_time REAL)"))
    db.session.execute(text(
        "INSERT INTO drive_stats (user_id, runs, races) VALUES (1, 37, 0)"))
    db.session.commit()

    counts, laps = admin.game_counts(db.session.connection())
    assert laps == 37
    assert counts.get("drive", 0) == 0, "laps leaked into the games total"

    db.session.execute(text("DROP TABLE drive_stats"))
    db.session.commit()


def test_a_player_is_somebody_who_drove_and_not_somebody_who_arrived(
        client, db, as_admin):
    """The tile exists because `visitors` is not a count of people, and this is
    the specific mistake it must not repeat.

    ``/api/start`` is the tempting path - "who began a lap" - and it is wrong,
    because ``noteStart()`` in `drive/static/js/game.js` returns early unless
    the driver is logged in. On the r/WebGames launch, 21 people drove and 3 had
    accounts; reading starts would have called that three players. So: a guest
    who finishes a lap counts, and a browser that only ever loaded the page does
    not.
    """
    as_admin("chinmay")
    db.session.execute(text("DELETE FROM site_visits"))
    now = datetime.utcnow()

    def visit(visitor, path, user_id=None, service="drive", is_bot=0):
        db.session.execute(text(
            "INSERT INTO site_visits (ts, service, visitor_id, session_id,"
            " user_id, method, path, status, is_bot)"
            " VALUES (:ts, :sv, :v, :v, :u, 'POST', :p, 200, :b)"),
            {"ts": visits.stamp(now), "sv": service, "v": visitor,
             "u": user_id, "p": path, "b": is_bot})

    visit("guest", "/api/run")                    # a stranger who drove
    visit("guest", "/api/run")                    # ...twice
    visit("member", "/api/run", user_id=1)        # somebody with an account
    visit("member", "/api/start", user_id=1)      # which only they can post
    visit("looker", "/")                          # loaded the page, never drove
    visit("robot", "/api/run", is_bot=1)          # and a crawler cannot be one
    db.session.commit()

    got = admin.drive_players(db.session.connection(), now - timedelta(days=30))
    assert got["players"] == 2, "expected the guest and the member, got %s" % got
    assert got["signed_in"] == 1
    assert got["laps"] == 3

    old = admin.drive_players(db.session.connection(), now + timedelta(days=1))
    assert old["players"] == 0, "the tile ignored its own window"


def test_drive_flagged_laps_are_finally_readable(client, db, as_admin):
    """``drive_cheat_flags`` is written by the lap verifier and, until this
    page, was never read by anything at all."""
    as_admin("chinmay")
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS drive_cheat_flags ("
        " id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, code TEXT,"
        " race_id INTEGER, track TEXT, phase TEXT, strikes INTEGER,"
        " reasons_json TEXT, created_at TEXT)"))
    db.session.execute(text(
        "INSERT INTO drive_cheat_flags (name, code, track, phase, strikes,"
        " reasons_json, created_at) VALUES ('speedy', 'AB12', 'sunrise',"
        " 'flying', 14, '{\"airtime\": 9, \"jerk\": 5}', '2026-08-10 09:00:00')"))
    db.session.commit()

    page = body(client.get("/admin/"))
    assert "speedy" in page
    assert "Sunrise Circuit" in page, "the track slug was not given its name"
    assert "airtime" in page, "the per-rule tally is the point of the row"

    db.session.execute(text("DROP TABLE drive_cheat_flags"))
    db.session.commit()


# ---------------------------------------------------------------------------
# The state a fresh clone is actually in
# ---------------------------------------------------------------------------

def test_an_empty_database_still_renders_every_page(client, as_admin, admin_routes,
                                                    db):
    """Four of the five tables this page reads belong to other services, and a
    box without a game installed - or a development database holding nothing
    but ``users`` - is an ordinary state, not an error. An admin console that
    500s on an empty database is one you cannot use on the day you need it.
    """
    as_admin("chinmay")
    for url in admin_routes:
        resp = client.get(url)
        # The session detail route is the one honest 404 here: it is asked for
        # a specific session, and 'x' is not one.
        assert resp.status_code in (200, 404), "%s -> %s" % (url, resp.status_code)
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# The two little readers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ua, expected", [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
     " (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36", "Chrome 130 · macOS"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
     " like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
     "Edge 129 · Windows"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
     " (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "Safari 17 · iPhone"),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
     "Firefox 120 · Linux"),
    ("", "—"),
])
def test_a_user_agent_is_read_down_to_the_two_words_worth_showing(ua, expected):
    """Ordered patterns, because every one of these strings contains several of
    the others: Edge says Chrome, Chrome says Safari, everything says Mozilla."""
    assert admin._agent(ua) == expected


def test_an_unrecognised_agent_keeps_its_own_words():
    """Not "Unknown" - a new browser or an odd script stays legible."""
    assert admin._agent("SomeNewThing/1.0") == "SomeNewThing/1.0"


@pytest.mark.parametrize("url, expected", [
    ("https://news.ycombinator.com/item?id=1", "news.ycombinator.com"),
    ("https://www.google.com/search?q=x", "google.com"),
    ("https://cgovind.com/", None),
    ("https://drive.cgovind.com/play", None),
    ("http://localhost:5002/", None),
    (None, None),
])
def test_a_referrer_is_folded_to_the_host_that_is_not_us(url, expected):
    assert admin._referrer(url) == expected


@pytest.mark.parametrize("seconds, expected", [
    (None, "—"), (0, "0s"), (45, "45s"), (60, "1m 00s"),
    (605, "10m 05s"), (3600, "1h 00m"), (7860, "2h 11m"),
])
def test_a_length_of_time_is_written_in_whole_units(seconds, expected):
    assert admin._duration(seconds) == expected
