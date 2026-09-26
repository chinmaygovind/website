"""The dailies review loop, the admin dashboard, and the fix tool."""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from conftest import boot_app, close_app                      # noqa: E402
import tracks as tracks_mod                                   # noqa: E402
from test_publish import _user, _login, _publish, _row        # noqa: E402


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    tracks_mod.set_resolver(None)
    close_app(path, verify="0")


def _queued_dailies(A, c, names):
    """Queued tracks marked generated, the way gen_daily writes them."""
    slugs = []
    for name in names:
        slug = _publish(A, c, name=name)
        with A.app.app_context():
            row = A.DriveUserTrack.query.filter_by(slug=slug).first()
            row.doc_json = json.dumps(dict(row.doc, generated={"seed": 1, "look": "sunrise"}))
            A.db.session.commit()
        slugs.append(slug)
    return slugs


def _setup(A):
    c = A.app.test_client()
    _login(c, _user(A, "ada"))
    slugs = _queued_dailies(A, c, ["Foggy Ridge", "Misty Gap", "Stony Bend"])
    _login(c, _user(A, "chinmay"))
    return c, slugs


def _drive_target(c, url):
    """Follow /admin/review to the play page and return (slug under review, html)."""
    r = c.get(url)
    assert r.status_code == 302
    r = c.get(r.headers["Location"])          # /admin/tracks/<slug>/drive?review=1
    assert r.status_code == 302
    page = c.get(r.headers["Location"]).get_data(as_text=True)
    return page.split('action="/admin/review/')[1].split('"')[0], page


def test_review_walks_the_queue_with_one_press_each(env):
    A = env
    c, (a, b, d) = _setup(A)
    slug, page = _drive_target(c, "/admin/review")
    assert slug == a and "Reviewing a daily" in page and "3 in the queue" in page

    # Send back with a note: out of the queue, note kept, on to the next.
    r = c.post("/admin/review/%s" % a, data={"action": "fix", "note": "too twisty"})
    assert r.status_code == 302
    assert _row(A, a).status == "needs_fix" and _row(A, a).review_note == "too twisty"
    slug, _ = _drive_target(c, r.headers["Location"])
    assert slug == b

    # Skip leaves it queued and moves on; approve schedules and numbers it.
    r = c.post("/admin/review/%s" % b, data={"action": "skip"})
    assert _row(A, b).status == "queued"
    slug, _ = _drive_target(c, r.headers["Location"])
    assert slug == d
    r = c.post("/admin/review/%s" % d, data={"action": "approve"})
    assert _row(A, "daily-1").daily_on is not None

    # Wraps round to what was skipped.
    slug, _ = _drive_target(c, r.headers["Location"])
    assert slug == b


def test_sending_back_needs_a_note_and_an_empty_queue_goes_home(env):
    A = env
    c, (a, b, d) = _setup(A)
    assert c.post("/admin/review/%s" % a, data={"action": "fix", "note": " "}).status_code == 400
    assert _row(A, a).status == "queued"
    for s in (a, b, d):
        c.post("/admin/review/%s" % s, data={"action": "approve"})
    r = c.get("/admin/review")
    assert r.headers["Location"].endswith("/admin")


def test_nobody_else_can_review(env):
    A = env
    c, (a, _, _) = _setup(A)
    other = A.app.test_client()
    _login(other, _user(A, "bea"))
    assert other.get("/admin/review").status_code == 404
    assert other.post("/admin/review/%s" % a, data={"action": "approve"}).status_code == 404
    assert _row(A, a).status == "queued"


def test_a_plain_draft_drive_has_no_review_card(env):
    A = env
    c, (a, _, _) = _setup(A)
    r = c.get("/admin/tracks/%s/drive" % a)
    page = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "review-card" not in page and "Back to the editor" in page


def test_generated_dailies_stay_out_of_the_builders_own_list(env):
    A = env
    c = A.app.test_client()
    _login(c, _user(A, "ada"))
    _publish(A, c, name="Hand Made")
    _queued_dailies(A, c, ["Foggy Ridge"])
    page = c.get("/make").get_data(as_text=True)
    assert "Hand Made" in page, "the author's own tracks are listed"
    assert "Foggy Ridge" not in page, "a generated daily is not"


def _visit(A, ts, visitor, session, ip, path="/", status=200, user_id=None):
    with A.app.app_context():
        A.db.session.execute(A.db.text(
            "INSERT INTO site_visits (ts, service, visitor_id, session_id, user_id,"
            " method, path, status, ip, is_bot) VALUES (:ts, 'drive', :v, :s, :u,"
            " 'GET', :p, :st, :ip, 0)"),
            {"ts": ts, "v": visitor, "s": session, "u": user_id, "p": path,
             "st": status, "ip": ip})
        A.db.session.commit()


def test_the_dashboard_counts_players_and_ignores_a_scanner(env):
    A = env
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for i in range(3):
        for p in ("/", "/api/start", "/api/run"):
            _visit(A, now, "real%d" % i, "s%d" % i, "10.0.0.%d" % i, path=p)
    for i in range(60):
        _visit(A, now, "scan%d" % i, "x%d" % i, "6.6.6.6", path="/.env.%d" % i, status=404)
    c = A.app.test_client()
    _login(c, _user(A, "chinmay"))
    page = c.get("/admin").get_data(as_text=True)
    tile = page.split("Players today</span><b>")[1].split("<")[0]
    assert tile == "3", "sixty cookieless one-request visitors from one address are a scanner"
    assert "Recent sessions" in page and "Start reviewing" not in page
    stranger = A.app.test_client()
    assert stranger.get("/admin").status_code == 404


def test_the_fix_tool_puts_a_reworked_track_back_in_the_queue(env, capsys, tmp_path):
    A = env
    c, (a, _, _) = _setup(A)
    c.post("/admin/review/%s" % a, data={"action": "fix", "note": "boring"})
    import daily_fixes
    daily_fixes.main(["list"])
    assert "boring" in capsys.readouterr().out
    with A.app.app_context():
        doc = A.DriveUserTrack.query.filter_by(slug=a).first().doc
    f = tmp_path / "doc.json"
    f.write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="refused"):
        daily_fixes.main(["put", a, str(f)])      # a starter shape is no daily
    assert _row(A, a).status == "needs_fix"
    daily_fixes.main(["regen", a])
    row = _row(A, a)
    assert row.status == "queued" and row.review_note == "regenerated: boring"
    assert row.doc["generated"]["seed"] != 1


def test_a_generated_track_is_stored_with_no_name_of_its_own(env):
    A = env
    _user(A, "chinmay")
    import gen_daily
    kept = gen_daily.propose(1, 395874002, verbose=False)
    slug, = gen_daily.store(kept)
    row = _row(A, slug)
    assert slug == "daily-draft-395874002"
    assert row.name == row.doc["name"] == "Daily (in review)"
