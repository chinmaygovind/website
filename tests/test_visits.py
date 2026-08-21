"""The visit log and the green dot.

``visits.py`` runs on *every* request of all five services, which is what makes
it worth testing carefully and what shapes most of these: the interesting cases
are not "does it write a row" but the ones where writing a row must not happen,
must not be wrong, and above all must not break the request it is attached to.

The wording lives in ``accounts/presence.py`` and is tested at the bottom,
because "last online 5 hours ago" is a sentence somebody reads on a public page
and the arithmetic behind it is the easiest thing here to get subtly wrong.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

import visits
from accounts import presence


@pytest.fixture()
def wipe(db):
    """The two tracking tables are raw SQL, so ``create_all`` never made them
    and ``drop_all`` never drops them - they outlive the per-test database and
    have to be emptied by hand."""
    db.session.execute(text("DELETE FROM site_visits"))
    db.session.execute(text("DELETE FROM user_presence"))
    db.session.commit()
    visits._SESSIONS.clear()
    visits._PRESENCE_AT.clear()
    yield db


def rows(db, sql="SELECT * FROM site_visits ORDER BY id"):
    return db.session.execute(text(sql)).mappings().all()


# --- what is a visit --------------------------------------------------------

def test_a_page_is_a_visit(client, wipe):
    client.get("/")
    got = rows(wipe)
    assert len(got) == 1
    assert got[0]["path"] == "/" and got[0]["service"] == "site"
    assert got[0]["status"] == 200


def test_furniture_is_not(client, wipe):
    """A page pulls in fonts, styles and images, and a log where those are rows
    is a log you cannot read. The line is drawn at "would a person call this a
    visit" - which is why a PDF is on the other side of it."""
    for path in ("/fonts/xkcd-script.woff", "/favicon.ico",
                 "/assets/icons/resume.png", "/static/accounts.css"):
        client.get(path)
    assert rows(wipe) == []


def test_the_resume_is_a_visit(client, wipe):
    """`.pdf` is deliberately absent from `ASSET_RE`: the resume is the one file
    on the site whose downloads are worth counting. Note it *is* under
    `/assets/`, which costs it nothing - the filter reads the extension, not the
    directory."""
    client.get("/assets/Chinmay_Govind_Resume.pdf")
    assert [r["path"] for r in rows(wipe)] == ["/assets/Chinmay_Govind_Resume.pdf"]


def test_a_404_is_still_a_visit(client, wipe):
    """Somebody arriving on a dead link is exactly the thing you want to find
    in here, so it is logged with the status that says so."""
    client.get("/nothing-here")
    got = rows(wipe)
    assert len(got) == 1 and got[0]["status"] == 404


# --- who it was -------------------------------------------------------------

def test_one_browser_is_one_visitor_across_requests(client, wipe):
    client.get("/")
    client.get("/accounts/")
    got = rows(wipe)
    assert got[0]["visitor_id"] == got[1]["visitor_id"]
    assert got[0]["session_id"] == got[1]["session_id"]


def test_two_browsers_are_two_visitors(flask_app, wipe):
    flask_app.test_client().get("/")
    flask_app.test_client().get("/")
    got = rows(wipe)
    assert got[0]["visitor_id"] != got[1]["visitor_id"]


def test_a_long_gap_is_a_new_session(client, wipe):
    """Thirty minutes, and the point of it is that closing the tab and coming
    back after lunch is two visits while reading one page for ten minutes is
    one. The cache is cleared here because it holds the timestamp in memory -
    what is under test is that the *table* is enough to work it out."""
    client.get("/")
    first = rows(wipe)[0]
    old = datetime.utcnow() - timedelta(minutes=45)
    wipe.session.execute(text("UPDATE site_visits SET ts = :t"),
                         {"t": visits.stamp(old)})
    wipe.session.commit()
    visits._SESSIONS.clear()
    client.get("/")
    got = rows(wipe)
    assert got[1]["visitor_id"] == first["visitor_id"], "same browser"
    assert got[1]["session_id"] != first["session_id"], "different visit"


def test_a_logged_in_visit_carries_the_account(client, logged_in, wipe):
    uid = logged_in()
    client.get("/accounts/")
    assert rows(wipe)[-1]["user_id"] == uid


def test_a_crawler_is_flagged_and_kept(client, wipe):
    """Flagged rather than dropped: a bot this misses is a row with is_bot 0,
    which is recoverable, where a bot it wrongly filters is a visit that never
    existed."""
    client.get("/", headers={"User-Agent": "Googlebot/2.1"})
    client.get("/", headers={"User-Agent": "Mozilla/5.0 (Macintosh)"})
    assert [r["is_bot"] for r in rows(wipe)] == [1, 0]


@pytest.mark.parametrize("agent", [
    # Every one of these was counted as a *person* on the thirty days around
    # Drive's launch, and each arrived once, to `/` or `/.env`, from a different
    # address. They are the reason `BOT_RE` grew its last three lines.
    "Python-urllib/3.13",
    "python-urllib3/2.7.0",
    "Mozilla/5.0 (l9scan/2.0.834313e20323e2735313e24353; +https://leakix.net)",
    "Mozilla/5.0 (compatible; research-scan/1.0)",
    "Mozilla/5.0 (compatible; CensysInspect/1.1; +https://about.censys.io/)",
    "Mozilla/5.0 (compatible; SecurityScanner/1.0)",
    "Mozilla/5.0 (compatible; NetcraftSurveyAgent/1.0; +info@netcraft.com)",
    "Mozilla/5.0 zgrab/0.x",
    "Go-http-client/1.1",
    "Hello from Palo Alto Networks, find out more about our scans in "
    "https://docs-cortex.paloaltonetworks.com/r/1/Cortex-Xpanse/Scanning-activity",
    "",                      # no User-Agent at all is never a browser
    "Mozilla/5.0",           # nor is the fossil on its own
])
def test_the_scanners_that_were_passing_as_people_are_flagged(agent):
    assert visits.is_crawler(agent), "%r still counts as a person" % agent


@pytest.mark.parametrize("agent", [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/151.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) Gecko/20100101"
    " Firefox/153.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 26_5_2 like Mac OS X)"
    " AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/151.0.7922.112"
    " Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/151.0.0.0 Mobile Safari/537.36",
])
def test_the_widened_pattern_still_lets_real_browsers_through(agent):
    """The half of the trade that matters. `scan`, `research` and `python-` are
    broad tokens deliberately, so the guard against them is a browser from every
    engine - these are the five commonest real agents on the box."""
    assert not visits.is_crawler(agent), "%r was mistaken for a crawler" % agent


def test_the_address_comes_from_the_proxy_header(client, wipe):
    """Every one of these services listens on 127.0.0.1 with nginx in front, so
    remote_addr is always the proxy - without this every row would say the box
    visited itself."""
    client.get("/", headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"})
    assert rows(wipe)[0]["ip"] == "203.0.113.7"


# --- presence ---------------------------------------------------------------

def test_being_logged_in_and_browsing_makes_you_online(client, logged_in, wipe):
    uid = logged_in()
    client.get("/accounts/")
    entry = visits.presence_for(wipe.session.connection(), [uid])[uid]
    assert entry["online"] and entry["service"] == "site"


def test_a_visit_alone_never_invents_a_detail(client, logged_in, wipe):
    """Loading a page says you are here and nothing more. Only a heartbeat,
    which passes a key through a whitelist, can say what you are doing."""
    uid = logged_in()
    client.get("/accounts/")
    assert visits.presence_for(wipe.session.connection(), [uid])[uid]["detail"] is None


def test_a_detail_survives_more_pages_in_the_same_game(wipe, make_user):
    """The heartbeat is a minute apart and pages are not, so an ordinary request
    must not wipe what the last heartbeat said - or a status would be blank for
    most of every minute."""
    uid = make_user("driver")
    visits.seen(wipe, uid, "drive", "Sunrise Circuit")
    visits.touch(wipe, uid, "drive")
    assert visits.presence_for(wipe.session.connection(), [uid])[uid]["detail"] \
        == "Sunrise Circuit"


def test_changing_game_drops_the_old_detail(wipe, make_user):
    """"Sunrise Circuit" is false the moment somebody opens King of Tokyo, and
    the next heartbeat is up to a minute away."""
    uid = make_user("driver")
    visits.seen(wipe, uid, "drive", "Sunrise Circuit")
    visits.touch(wipe, uid, "kot")
    entry = visits.presence_for(wipe.session.connection(), [uid])[uid]
    assert entry["service"] == "kot" and entry["detail"] is None


def test_going_quiet_takes_you_offline(wipe, make_user):
    uid = make_user("driver")
    visits.seen(wipe, uid, "drive", "Multiplayer")
    wipe.session.execute(text("UPDATE user_presence SET last_seen = :t"),
                         {"t": visits.stamp(datetime.utcnow() - timedelta(minutes=10))})
    wipe.session.commit()
    entry = visits.presence_for(wipe.session.connection(), [uid])[uid]
    assert not entry["online"]
    assert entry["last_seen"] is not None, "and it still knows when"


def test_online_now_leaves_the_bots_out(wipe, make_user, db):
    from accounts.models import User
    uid = make_user("person")
    bot = User(username="bot:shitter_bot", email="b@bots.local", is_bot=True)
    db.session.add(bot)
    db.session.commit()
    visits.seen(wipe, uid, "drive", "Multiplayer")
    visits.seen(wipe, bot.id, "ers", "In Game")
    names = [r["username"] for r in visits.online_now(wipe.session.connection())]
    assert names == ["person"]


def test_a_guest_is_not_a_presence(client, wipe):
    """Presence hangs off an account. A visit with no user_id writes a row in
    the log and nothing at all in the other table."""
    client.get("/")
    assert rows(wipe, "SELECT * FROM user_presence") == []


# --- it must never break the request ----------------------------------------

def test_a_broken_table_costs_a_row_and_not_the_page(client, wipe, monkeypatch):
    """The hook runs on every request of five services. A database that is
    missing, locked or half-migrated has to be a missing log line, never a 500
    on somebody's profile."""
    def explode(*_a, **_k):
        raise RuntimeError("the database is on fire")
    monkeypatch.setattr(visits, "_record", explode)
    assert client.get("/").status_code == 200


# --- the words --------------------------------------------------------------

def test_the_line_names_the_game_and_what_they_are_doing():
    online, txt = presence.line_for(
        {"online": True, "service": "drive", "detail": "Sunrise Circuit"})
    assert online and txt == "Playing Drive - Sunrise Circuit"
    _, txt = presence.line_for({"online": True, "service": "ttr", "detail": "In Lobby"})
    assert txt == "Playing Ticket to Ride - In Lobby"


def test_the_main_site_is_not_a_game():
    _, txt = presence.line_for({"online": True, "service": "site", "detail": None})
    assert txt == "Browsing cgovind.com"


def test_a_game_with_nothing_to_add_just_says_the_game():
    _, txt = presence.line_for({"online": True, "service": "kot", "detail": None})
    assert txt == "Playing King of Tokyo"


@pytest.mark.parametrize("delta,want", [
    (timedelta(seconds=20), "just now"),
    (timedelta(minutes=1), "1 minute ago"),
    (timedelta(minutes=59), "59 minutes ago"),
    (timedelta(hours=5), "5 hours ago"),
    (timedelta(days=1), "1 day ago"),
    (timedelta(days=9), "1 week ago"),
    (timedelta(days=40), "1 month ago"),
    (timedelta(days=400), "1 year ago"),
])
def test_how_long_ago_reads_in_whole_units(delta, want):
    now = datetime(2026, 8, 7, 12, 0, 0)
    assert presence.ago(now - delta, now=now) == want


def test_a_clock_slightly_ahead_is_not_a_negative_age():
    """Five processes, five clocks. One of them a second fast must not put
    "in -1 seconds" on a public page."""
    now = datetime(2026, 8, 7, 12, 0, 0)
    assert presence.ago(now + timedelta(seconds=3), now=now) == "just now"


def test_never_seen_at_all_is_offline_with_no_claim_about_when():
    online, txt = presence.line_for(None)
    assert not online and txt == "Offline"


def test_offline_says_how_long():
    entry = {"online": False, "service": "drive",
             "last_seen": datetime.utcnow() - timedelta(hours=3)}
    _, txt = presence.line_for(entry)
    assert txt == "Offline - last online 3 hours ago"
