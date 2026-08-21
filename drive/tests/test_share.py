"""What a link to Drive looks like when somebody pastes it, and how they get one.

Two halves of one feature. **The card**: a page about one track unfurls with that
track's own picture and name rather than the site's wheel, and a link that names
a lap unfurls with the time and whose it is. **The button**: `/api/run` hands
back the id of the row the lap is on, which is what the finish sheet's Share
turns into `/solo/<slug>?watch=<id>`.

That URL is not new - it is how the public board has always handed a lap to the
game - so nothing here tests that the ghost plays. It tests that the link points
at a lap that exists, and that what a crawler reads off it is true.

The re-simulation is off, for the reason `test_app.py`'s fixture gives: these
laps were built rather than driven, and with the anti-cheat live every one of
them would be held in the queue and this would be a file about the queue.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    close_app(path, verify="0")


def _og(html):
    """The og: tags off a rendered page, as a dict."""
    return dict(re.findall(r'<meta property="og:(\w+)" content="([^"]*)"', html))


def _user(A, name="chinmay"):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _lap(A, uid, slug="sunrise", ms=25000, ghost=b"x"):
    """A row on the board. `ghost` is only ever checked for being there."""
    with A.app.app_context():
        row = A.DriveTime(user_id=uid, track=slug, time_ms=ms, ghost=ghost)
        A.db.session.add(row)
        A.db.session.commit()
        return row.id


def _login(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------

def test_a_track_page_unfurls_as_that_track(env):
    """The whole point of the per-track card: a link to Big Red shows Big Red."""
    og = _og(env.app.test_client().get("/solo/bigred").get_data(as_text=True))
    # Absolute, because nothing that reads one of these ever resolves a relative
    # path - and carrying the `?v=` cache token, like every other asset.
    assert og["image"].startswith("https://")
    assert "/static/img/og/bigred.png?v=" in og["image"]
    assert og["title"].startswith("Big Red")
    # The *title* is what is specific now. A track has no description of its own
    # any more, so this falls through to the site's one-liner - and that is worth
    # asserting rather than skipping, because the way removing the field would
    # have gone wrong is `content=""`: a card with a blank second line, which is
    # not an error anywhere and is only ever seen in somebody else's feed.
    assert "Race to set the best lap" in og["description"]


def test_the_public_board_unfurls_as_its_track_too(env):
    og = _og(env.app.test_client().get("/track/bigred").get_data(as_text=True))
    assert "/static/img/og/bigred.png" in og["image"]


def test_pages_that_are_not_about_a_track_keep_the_wheel(env):
    """The home page and the leaderboard are about the site, so they get its card."""
    c = env.app.test_client()
    for url in ("/", "/leaderboard"):
        og = _og(c.get(url).get_data(as_text=True))
        assert "/static/img/og.png?v=" in og["image"], url


def test_every_track_has_a_share_card_on_disk(env):
    """Same failure as a missing preview and the same fix: a card nothing renders
    is a link that unfurls as a broken image. `python tools/shoot_tracks.py`
    makes both, or `tools/shoot_og_cards.py` for the cards alone."""
    import tracks as tracks_mod
    here = os.path.join(os.path.dirname(__file__), "..", "static", "img", "og")
    missing = [t["slug"] for t in tracks_mod.TRACKS
               if not os.path.exists(os.path.join(here, t["slug"] + ".png"))]
    assert not missing, "no share card for: " + ", ".join(missing)


# ---------------------------------------------------------------------------
# A link that names a lap
# ---------------------------------------------------------------------------

def test_a_shared_lap_unfurls_with_the_time_and_the_driver(env):
    """What makes the link worth sending: it is an argument, not a homepage."""
    uid = _user(env, "chinmay")
    lap = _lap(env, uid, "sunrise", ms=25000)
    og = _og(env.app.test_client()
             .get("/solo/sunrise?watch=%d" % lap).get_data(as_text=True))
    assert "0:25.000" in og["title"]
    assert "Sunrise" in og["title"]
    assert "chinmay" in og["description"]
    # Still that track's picture - there is no per-lap art.
    assert "/static/img/og/sunrise.png" in og["image"]


def test_a_lap_id_from_another_track_is_not_believed(env):
    """`?watch=` is scoped to the track for the same reason `/api/ghost` scopes
    it: an id from elsewhere would otherwise describe a lap that cannot be
    played here."""
    uid = _user(env)
    lap = _lap(env, uid, "sunrise", ms=25000)
    og = _og(env.app.test_client()
             .get("/solo/bigred?watch=%d" % lap).get_data(as_text=True))
    assert "0:25.000" not in og["title"]
    assert og["title"].startswith("Big Red")


def test_a_lap_with_no_replay_does_not_get_a_card_promising_one(env):
    """The oldest rows have a time and no ghost. A card offering a lap that then
    toasts "that lap is no longer there" is worse than the generic one."""
    uid = _user(env)
    lap = _lap(env, uid, "sunrise", ms=25000, ghost=None)
    og = _og(env.app.test_client()
             .get("/solo/sunrise?watch=%d" % lap).get_data(as_text=True))
    assert "0:25.000" not in og["title"]


def test_nonsense_in_watch_is_ignored_rather_than_fatal(env):
    """It is a query string on a public URL, so it is whatever anybody types."""
    c = env.app.test_client()
    for bad in ("", "abc", "-1", "9999999", "1;drop", "../../etc/passwd"):
        r = c.get("/solo/sunrise?watch=" + bad)
        assert r.status_code == 200, bad
        assert _og(r.get_data(as_text=True))["title"].startswith("Sunrise"), bad


# ---------------------------------------------------------------------------
# What a crawler sees
# ---------------------------------------------------------------------------

def test_a_shared_lap_canonicalises_to_the_bare_track(env):
    """The one duplicate the share button creates, and the one line that fixes it.

    Every lap on a board is a `?watch=` of the same page, so without a canonical
    a track with forty times on it is forty near-identical URLs.
    """
    can = re.compile(r'<link rel="canonical" href="([^"]+)"')
    c = env.app.test_client()
    plain = can.search(c.get("/solo/bigred").get_data(as_text=True)).group(1)
    shared = can.search(
        c.get("/solo/bigred?watch=7").get_data(as_text=True)).group(1)
    assert plain == shared == "https://drive.cgovind.com/solo/bigred"


def test_a_room_is_not_indexed_and_a_track_is(env):
    """A room code lives for one evening; indexing it buys a dead result."""
    c = env.app.test_client()
    _login(c, _user(env))
    c.post("/create", json={"track": "sunrise"})
    with env.app.app_context():
        code = env.DriveGame.query.first().code
    assert b'name="robots" content="noindex' in c.get("/room/" + code).data
    assert b'name="robots" content="noindex' not in c.get("/solo/sunrise").data


def test_robots_names_the_sitemap_and_hides_what_is_ephemeral(env):
    txt = env.app.test_client().get("/robots.txt").get_data(as_text=True)
    assert "Sitemap: https://drive.cgovind.com/sitemap.xml" in txt
    for path in ("/api/", "/room/", "/j/", "/race/"):
        assert "Disallow: %s" % path in txt


def test_the_sitemap_is_valid_and_lists_every_track(env):
    """Generated from the pool, so a new track is in it the day it lands."""
    import xml.etree.ElementTree as ET
    import tracks as tracks_mod
    body = env.app.test_client().get("/sitemap.xml").get_data(as_text=True)
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    root = ET.fromstring(body)
    assert root.tag == ns + "urlset"
    locs = {e.text for e in root.iter(ns + "loc")}
    for t in tracks_mod.TRACKS:
        assert "https://drive.cgovind.com/solo/%s" % t["slug"] in locs
        assert "https://drive.cgovind.com/track/%s" % t["slug"] in locs
    # Nothing robots.txt just said to stay out of.
    assert not [u for u in locs if "/room/" in u or "/race/" in u or "/api/" in u]


# ---------------------------------------------------------------------------
# The button
# ---------------------------------------------------------------------------

def test_a_stored_run_comes_back_with_the_id_its_link_needs(env):
    """`time_id` is the whole of what the Share button is built from."""
    from test_app import _run_payload
    uid = _user(env)
    c = env.app.test_client()
    _login(c, uid)
    d = c.post("/api/run", json=_run_payload(env)).get_json()
    assert d["stored"] and d["time_id"]
    # It names the row that is actually on the board, which is what the link
    # will be resolved against.
    with env.app.app_context():
        row = env.db.session.get(env.DriveTime, d["time_id"])
    assert row.user_id == uid and row.track == "sunrise"


def test_the_id_is_the_row_and_not_the_run(env):
    """A second, slower lap does not mint a new link - `drive_times` keeps one
    row per player per track, so the shareable lap is always their best."""
    from test_app import _run_payload
    import tracks as tracks_mod
    uid = _user(env)
    c = env.app.test_client()
    _login(c, uid)
    first = c.post("/api/run", json=_run_payload(env)).get_json()
    slow = _run_payload(env, seconds=tracks_mod.get("sunrise")["ideal"] * 1.3)
    second = c.post("/api/run", json=slow).get_json()
    assert second["time_id"] == first["time_id"]
    assert not second["improved"]


def test_a_guest_gets_no_link_because_they_have_no_lap(env):
    """Nothing to point at, and the finish sheet says so rather than going grey:
    it is the one moment where an account buys something immediate."""
    from test_app import _run_payload
    d = env.app.test_client().post("/api/run", json=_run_payload(env)).get_json()
    assert d["guest"] and not d["stored"]
    assert not d.get("time_id")


def test_the_finish_sheet_carries_a_share_button_in_solo_only(env):
    """A lap set in a room never reaches the board, so there is nothing to link
    to and the button is not rendered at all."""
    c = env.app.test_client()
    assert b'id="btnShare"' in c.get("/solo/sunrise").data
    uid = _user(env)
    _login(c, uid)
    c.post("/create", json={"track": "sunrise"})
    with env.app.app_context():
        code = env.DriveGame.query.first().code
    assert b'id="btnShare"' not in c.get("/room/" + code).data
