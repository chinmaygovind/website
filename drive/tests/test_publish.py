"""Keeping a track: saving it, proving it, queueing it, and going live.

The bet the whole feature rests on is one line in `app.py`:

    tracks_mod.set_resolver(_resolve_user_track)

`tracks.get` is the single chokepoint `/solo`, `/api/track`, `/api/run`,
`/api/start`, `/api/ghost`, rooms, replays, share cards, `robots.txt`,
`sitemap.xml` and the switcher all go through, so teaching it to resolve a live
slug is what makes every one of them work on somebody's track without being
edited. These tests drive the round trip through the real routes, because the
thing worth proving is not that a row can be written - it is that a row becomes
a track the rest of the game cannot tell from Spa.

Two rules get most of the attention here, and both are about a leaderboard
meaning something:

* **what was approved is what is live.** A cosmetic edit saves onto a live
  track; anything that moves the road drops it back to the queue, because every
  time on that board was driven against the old one.
* **you cannot submit a track you have not driven.** It proves finishability by
  demonstration rather than by inference, and the proof is keyed on the geometry
  - so driving it and *then* moving a corner does not count.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tracks as tracks_mod                                   # noqa: E402
from tracks import moves, starters                            # noqa: E402


@pytest.fixture()
def env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path
    os.environ["DRIVE_VERIFY"] = "0"
    for mod in ("app", "models", "portal"):
        sys.modules.pop(mod, None)
    import app as A
    A.app.config["TESTING"] = True
    with A.app.app_context():
        A.db.drop_all()
        A.db.create_all()
    yield A
    tracks_mod.set_resolver(None)
    os.environ.pop("DRIVE_VERIFY", None)
    os.unlink(path)


def _user(A, name="ada", admin=False):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        if hasattr(u, "set_password"):
            u.set_password("x")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _login(c, uid):
    with c.session_transaction() as s:
        s["user_id"] = uid


def _row(A, slug):
    """A row, read inside an application context - which a request always has."""
    with A.app.app_context():
        return A.DriveUserTrack.query.filter_by(slug=slug).first()


def _doc(shape="sprint", **over):
    d = starters.document(shape)
    d.update(over)
    return d


# --------------------------------------------------------------------- saving

def test_building_needs_no_account_and_saving_does(env):
    """An editor that asks who you are before it shows you a road is an editor
    most people close. A saved track has an author, an address and a board, and
    none of those exist without an identity."""
    A = env
    c = A.app.test_client()
    assert c.get("/make/sprint").status_code == 200
    assert c.post("/api/make/build", json=_doc()).status_code == 200
    r = c.post("/api/make/save", json={"doc": _doc()})
    assert r.status_code == 401
    assert r.get_json()["need_login"] is True


def test_saving_gives_a_track_an_address_nobody_else_can_take(env):
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    got = c.post("/api/make/save",
                 json={"doc": _doc(name="Foggy Ridge")}).get_json()
    assert got["slug"] == "foggy-ridge"
    assert got["status"] == "draft"
    # And it is taken from here on, so the same name lands on a new address.
    again = c.post("/api/make/save",
                   json={"doc": _doc(name="Foggy Ridge")}).get_json()
    assert again["slug"] == "foggy-ridge-2", again


@pytest.mark.parametrize("name", ["draft", "make", "admin", "api", "spa",
                                  "sunrise"])
def test_a_track_can_never_take_a_reserved_or_pool_name(env, name):
    """`draft` in particular: it is the slug every draft is driven under, and a
    row holding it would let a draft lap reach a real board."""
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    slug = c.post("/api/make/save",
                  json={"doc": _doc(name=name)}).get_json()["slug"]
    assert slug != name, "%r was allowed as a slug" % name


def test_somebody_elses_track_is_not_yours_to_change(env):
    A = env
    mine, theirs = _user(A, "ada"), _user(A, "bob")
    c = A.app.test_client()
    _login(c, mine)
    slug = c.post("/api/make/save", json={"doc": _doc()}).get_json()["slug"]
    _login(c, theirs)
    r = c.post("/api/make/save", json={"doc": _doc(name="stolen"),
                                       "slug": slug})
    assert r.status_code == 403


# ----------------------------------------------------------------- the gate

def test_you_cannot_submit_a_track_you_have_not_driven(env):
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    slug = c.post("/api/make/save", json={"doc": _doc()}).get_json()["slug"]
    r = c.post("/api/make/submit", json={"slug": slug})
    assert r.status_code == 400
    labels = {x["label"]: x["ok"] for x in r.get_json()["checks"]}
    assert labels["You have driven it"] is False
    assert _row(A, slug).status == "draft"


def test_driving_it_opens_the_gate(env):
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    doc = _doc()
    slug = c.post("/api/make/save", json={"doc": doc}).get_json()["slug"]
    token = c.post("/api/make/draft", json=doc).get_json()["token"]
    assert c.post("/api/make/drove",
                  json={"token": token, "ms": 12345}).get_json()["ok"] is True
    r = c.post("/api/make/submit", json={"slug": slug})
    assert r.status_code == 200, r.get_json()
    row = _row(A, slug)
    assert row.status == "queued" and row.queued_at is not None


def test_the_lap_proves_the_road_it_was_driven_on_and_no_other(env):
    """Driving it and then moving a corner is not proof of anything. The record
    is keyed on the geometry fingerprint, so the gate closes again."""
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    doc = _doc()
    token = c.post("/api/make/draft", json=doc).get_json()["token"]
    c.post("/api/make/drove", json={"token": token, "ms": 12345})
    moved = _doc()
    moved["moves"][2]["len"] = 90.0
    slug = c.post("/api/make/save", json={"doc": moved}).get_json()["slug"]
    r = c.post("/api/make/submit", json={"slug": slug})
    assert r.status_code == 400
    labels = {x["label"]: x["ok"] for x in r.get_json()["checks"]}
    assert labels["You have driven it"] is False


def test_the_checks_are_the_pools_own_checks(env):
    """Not a second standard for what a track is. The Circuit starter is four
    identical corners, and the pool's own varied-radii rule says so."""
    A = env
    c = A.app.test_client()
    got = c.post("/api/make/checks", json=_doc("circuit")).get_json()
    failing = [x["label"] for x in got["checks"] if not x["ok"]]
    assert "Corner radii are varied" in failing
    ok = c.post("/api/make/checks", json=_doc("sprint")).get_json()
    assert [x["label"] for x in ok["checks"] if not x["ok"]] \
        == ["You have driven it"]


# ------------------------------------------------------------------ going live

def _publish(A, c, doc=None, name="Foggy Ridge"):
    doc = doc or _doc(name=name)
    slug = c.post("/api/make/save", json={"doc": doc}).get_json()["slug"]
    token = c.post("/api/make/draft", json=doc).get_json()["token"]
    c.post("/api/make/drove", json={"token": token, "ms": 12345})
    assert c.post("/api/make/submit", json={"slug": slug}).status_code == 200
    return slug


def test_a_live_track_is_a_track(env):
    """The whole bet, in one test. Nothing below was edited to make this work."""
    A = env
    author = _user(A, "ada")
    admin = _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    slug = _publish(A, c)
    # Queued is not live: not resolvable, and not drivable by anybody.
    with A.app.app_context():
        assert tracks_mod.get(slug) is None
    assert c.get("/solo/%s" % slug).status_code in (302, 404)

    _login(c, admin)
    assert c.post("/admin/tracks/%s/approve" % slug).status_code in (302, 200)

    with A.app.app_context():
        t = tracks_mod.get(slug)
    assert t is not None, "tracks.get still cannot see an approved track"
    assert t["name"] == "Foggy Ridge"
    assert t["author"] == "ada"
    assert t["user"] is True
    assert t["medals"]["gold"] < t["medals"]["silver"] < t["medals"]["bronze"]
    assert t["spawn"] and t["line"] and t["gates"]
    # And the routes that were never touched.
    assert c.get("/solo/%s" % slug).status_code == 200
    assert c.get("/api/track/%s" % slug).status_code in (200, 404)


def test_the_queue_and_the_console_do_not_exist_for_anybody_else(env):
    """A 403 would confirm the console is there, which is the same reasoning the
    rest of /admin uses."""
    A = env
    c = A.app.test_client()
    assert c.get("/admin/tracks").status_code == 404
    _login(c, _user(A, "ada"))
    assert c.get("/admin/tracks").status_code == 404
    slug = _publish(A, c)
    assert c.post("/admin/tracks/%s/approve" % slug).status_code == 404
    _login(c, _user(A, "chinmay"))
    assert c.get("/admin/tracks").status_code == 200


def test_a_cosmetic_edit_keeps_the_board_and_a_moved_corner_does_not(env):
    """The rule that makes a leaderboard mean something, and the reason it is a
    hash of the built ribbon rather than a diff of the document: a no-op edit -
    drag a slider and drag it back - costs nobody their record, and a change
    that looks cosmetic but moves the road is caught anyway."""
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    doc = _doc(name="Foggy Ridge")
    slug = _publish(A, c, doc)
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    _login(c, author)

    # A colour. Still live, still on the board.
    cosmetic = json.loads(json.dumps(doc))
    cosmetic["pal"]["road"] = 0x101820
    cosmetic["name"] = "Foggy Ridge II"
    got = c.post("/api/make/save", json={"doc": cosmetic, "slug": slug}).get_json()
    assert got["requeued"] is False, got
    assert _row(A, slug).status == "live"
    with A.app.app_context():
        assert tracks_mod.get(slug)["name"] == "Foggy Ridge II"

    # A corner. Back to the queue, and out of the pool until approved again.
    moved = json.loads(json.dumps(cosmetic))
    moved["moves"][2]["len"] = 91.0
    got = c.post("/api/make/save", json={"doc": moved, "slug": slug}).get_json()
    assert got["requeued"] is True, got
    with A.app.app_context():
        assert tracks_mod.get(slug) is None


def test_a_no_op_edit_costs_nobody_their_record(env):
    """Drag a slider and drag it back. The document is byte-different (it has
    been round-tripped through JSON); the road is not."""
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    doc = _doc(name="Foggy Ridge")
    slug = _publish(A, c, doc)
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    _login(c, author)
    there = json.loads(json.dumps(doc))
    there["moves"][2]["len"] = 137.0
    c.post("/api/make/save", json={"doc": there, "slug": slug})
    back = json.loads(json.dumps(doc))
    got = c.post("/api/make/save", json={"doc": back, "slug": slug}).get_json()
    assert got["geom_changed"] is True   # it moved, and moved back
    # Approve once more and the hash is the original again, so a later save of
    # the same document is a no-op.
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    _login(c, author)
    got = c.post("/api/make/save", json={"doc": back, "slug": slug}).get_json()
    assert got["requeued"] is False and got["geom_changed"] is False


def test_hiding_a_track_takes_it_out_of_the_pool_and_keeps_the_row(env):
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    slug = _publish(A, c)
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    with A.app.app_context():
        assert tracks_mod.get(slug) is not None
    c.post("/admin/tracks/%s/hide" % slug)
    with A.app.app_context():
        assert tracks_mod.get(slug) is None
    assert _row(A, slug) is not None
    c.post("/admin/tracks/%s/unhide" % slug)
    with A.app.app_context():
        assert tracks_mod.get(slug) is not None


# --------------------------------------------------------------------- forking

def test_forking_a_pool_track_credits_it_and_says_what_it_dropped(env):
    """Costco's shell, Mount Joy's and Shroom Street's height fields are code,
    and a fork says so rather than quietly producing a track missing the thing
    it was famous for."""
    A = env
    c = A.app.test_client()
    got = c.post("/api/make/fork/costco").get_json()
    assert got["origin"]
    assert got["dropped"], "forking Costco dropped nothing, which cannot be true"
    page = c.get(got["url"])
    assert page.status_code == 200
    assert b'"forked_from"' in page.data or b"forked_from" in page.data


def test_a_fork_is_credited_forever(env):
    A = env
    uid = _user(A)
    c = A.app.test_client()
    _login(c, uid)
    tok = c.post("/api/make/fork/chicane").get_json()["token"]
    doc = A._DRAFTS[tok][0]
    assert doc["forked_from"] == "chicane"
    slug = c.post("/api/make/save", json={"doc": doc}).get_json()["slug"]
    assert _row(A, slug).forked_from \
        == "chicane"


def test_a_draft_cannot_be_forked_by_a_stranger(env):
    A = env
    mine, theirs = _user(A, "ada"), _user(A, "bob")
    c = A.app.test_client()
    _login(c, mine)
    slug = c.post("/api/make/save", json={"doc": _doc()}).get_json()["slug"]
    _login(c, theirs)
    assert c.post("/api/make/fork/%s" % slug).status_code == 404


# --------------------------------------------------------------------- gallery

def test_the_gallery_lists_what_is_live_and_your_own_drafts(env):
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    live = _publish(A, c, name="Published One")
    c.post("/api/make/save", json={"doc": _doc(name="Still Mine")})
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % live)
    _login(c, author)
    body = c.get("/tracks").data.decode()
    assert "Published One" in body
    assert "Still Mine" in body, "the author cannot see their own draft"
    # And a stranger sees only what is published.
    _login(c, _user(A, "carl"))
    body = c.get("/tracks").data.decode()
    assert "Published One" in body and "Still Mine" not in body


# ------------------------------------------------------- the shelf and the UI

def test_the_switcher_shelves_community_tracks_under_the_pool(env):
    """Under, not mixed in. The pool is the game and this is what people have
    made in it; shuffled together, finding Spa would be a search."""
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    slug = _publish(A, c, name="Foggy Ridge")
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    # `_track_cards` reads your PB map, which needs a session - so it is asked
    # inside a request, which is the only place it is ever called from.
    with A.app.test_request_context("/solo"):
        cards = A._track_cards()
    shelves = [x["shelf"] for x in cards]
    assert set(shelves) == {"pool", "community"}
    # Every pool card before every community card.
    assert shelves.index("community") == len(
        [x for x in shelves if x == "pool"])
    mine = [x for x in cards if x["slug"] == slug][0]
    assert mine["author"] == "ada"
    # No cover shot yet, so it is painted off its own palette rather than
    # pointing at an image that does not exist.
    assert mine["image"] is None
    assert mine["tint"].startswith("#") and mine["sky"].startswith("#")


def test_drawing_the_switcher_never_builds_a_track(env):
    """A card wants a name, a difficulty and your time. Replaying every stored
    document to draw a menu would put seconds into a panel that opens mid-race,
    on the one eventlet worker that is also relaying race poses."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "app.py")).read()
    body = src[src.index("def _community_cards("):
               src.index("\n\n\n", src.index("def _community_cards("))]
    for banned in ("from_document", "_track_from_row", "_draft_track"):
        assert banned not in body, (
            "_community_cards builds tracks (%s), which it must not" % banned)


def test_the_editor_offers_saving_and_the_gate(env):
    """The publish sheet is the only place a login is mentioned, and the only
    place the checks are shown."""
    A = env
    body = A.app.test_client().get("/make/sprint").data.decode()
    for want in ('id="save"', 'id="pubPane"', 'id="pubChecks"',
                 'id="pubSubmit"', 'Submit for review'):
        assert want in body, want


def test_a_lap_on_a_draft_is_reported_and_a_pool_lap_is_not():
    """`reportDraftLap` is gated on CFG.draft. A pool lap going to the editor's
    gate would be harmless and wrong; a draft lap *not* going there is the gate
    never opening."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "game.js")).read()
    body = src[src.index("function reportDraftLap("):
               src.index("\n}", src.index("function reportDraftLap("))]
    assert "CFG.draft" in body and "CFG.draftToken" in body
    assert "/api/make/drove" in body


# --------------------------------------------------------------------- adopting

def test_adopting_a_track_writes_a_folder_that_builds_the_same_road(env):
    """The load-bearing claim of `tools/adopt_track.py`.

    Emitting `build(b)` source is a second implementation of what
    `moves.replay` does at runtime, and the way to keep a second implementation
    honest is not care - it is comparing the two on real input every time the
    tool runs. So the tool writes the folder, imports it as the pool would,
    builds the ribbon and compares fingerprints; this test is that, on a track
    that went the whole way round.
    """
    import shutil
    import importlib
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    doc = _doc("stunt", name="Adopted Park")
    # Something in every corner of the schema: a placement, a wider bit, and a
    # barrier - so the generator is not just tested on straights and arcs.
    doc["scenery"] = [{"o": "stand", "at": 0.1, "side": -1, "tiers": 9},
                      {"o": "wall", "at": 0.4, "to": 0.46, "side": -1,
                       "off": 13, "h": 1.6}]
    doc["moves"][3]["w"] = 15.0
    doc["moves"][3]["rail"] = "lr"
    slug = _publish(A, c, doc, name="Adopted Park")
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    adopt = importlib.import_module("adopt_track")
    folder = None
    try:
        with A.app.app_context():
            row = adopt._row_like(slug)
        folder = adopt.write_folder(slug, row, order=999)
        assert os.path.exists(os.path.join(folder, "track.py"))
        got, want = adopt.verify(slug, row["want_hash"])
        assert got == want, (
            "the adopted folder builds a different road from the row it came "
            "from, which means the source generator has drifted from "
            "moves.replay")

        # And it reads like a pool track rather than like generated output.
        src = open(os.path.join(folder, "track.py")).read()
        assert "def build(b):" in src
        assert "b.start(" in src and "b.cp()" in src
        assert "b.width(15" in src, "the sticky width was not put back"
        assert "b.rail('lr')" in src, "the sticky barriers were not put back"
        assert "placed = [" in src, "the placements were dropped"
        assert "0x" in open(os.path.join(folder, "palette.py")).read(), \
            "the palette was written in decimal, which nobody can read"
        assert "medals = (" in src

        # The pool can now actually load it.
        importlib.invalidate_caches()
        mod = importlib.import_module("tracks.%s.track" % slug)
        assert mod.slug == slug and mod.order == 999
    finally:
        if folder and os.path.isdir(folder):
            shutil.rmtree(folder)


def test_adopting_refuses_a_track_nobody_has_reviewed(env):
    """Adopting puts a track in the repository. Doing that to something still in
    the queue is committing a road nobody has driven."""
    import importlib
    A = env
    _login_c = A.app.test_client()
    _login(_login_c, _user(A, "ada"))
    slug = _publish(A, _login_c, name="Not Yet")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    adopt = importlib.import_module("adopt_track")
    with A.app.app_context():
        with pytest.raises(SystemExit) as e:
            adopt._row_like(slug)
    assert "queued" in str(e.value)


def test_a_pool_folder_can_carry_placements(env):
    """Which is what makes adoption lossless: a community track's scenery is a
    list, and the pool can hold a list. Nothing has to be rewritten as code."""
    doc = _doc("sprint")
    doc["scenery"] = [{"o": "pine", "at": 0.3, "side": 1, "off": 40}]
    t = tracks_mod.from_document("x", doc, timed=False)
    assert t["placed"] == doc["scenery"]
    # And the key is not the `scenery` boolean, which would be read as
    # `true.length` in JavaScript and silently draw nothing.
    assert t["scenery"] is False


# ----------------------------------------------------------------------- rooms

def test_a_room_can_be_raced_on_a_community_track(env):
    """The claim that a user track is not a second kind of track, tested on the
    hardest consumer of it.

    A room is where the most goes wrong: `_room_track` resolves the slug on
    every car on every tick, the grid comes from `pole_side`, the checkpoint
    window comes from `gate_ceil`, and the replay stores the slug and resolves
    it again days later. All of it goes through `tracks.get`, which is the whole
    point - but "should work" and "does work" are different claims.
    """
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    slug = _publish(A, c, name="Room Test")
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)

    seat_key = "seat-key"
    with c.session_transaction() as sess:
        sess["session_key"] = seat_key
    with A.app.app_context():
        game = A.DriveGame(code="USRT", status="waiting", track=slug)
        A.db.session.add(game)
        A.db.session.commit()
        # `/room/<code>` needs a seat, not just a room - so take one, the way
        # joining does.
        A.db.session.add(A.DrivePlayer(game_id=game.id, name="Ada",
                                       color="#ffffff", session_key=seat_key))
        A.db.session.commit()
        # The one query a room makes about its track, on every tick.
        t = A._room_track("USRT")
        assert t is not None, "a room cannot see the track it is on"
        assert t["name"] == "Room Test"
        # And the things a race reads off it.
        assert t["pole_side"] in (-1, 1)
        assert A.checks.GATE_CEIL_MIN <= t["gate_ceil"] <= A.checks.GATE_CEIL_MAX
        assert t["spawn"] and t["gates"] and t["checkpoints"] >= 1

    page = c.get("/room/USRT")
    assert page.status_code == 200, "the room page will not open"
    body = page.data.decode()
    assert "Room Test" in body, "the room does not name the track"


def test_the_switcher_in_a_room_offers_community_tracks(env):
    """Changing track mid-room goes through the same card list, so a host can
    put everybody on somebody's track."""
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    slug = _publish(A, c, name="Room Test")
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    with c.session_transaction() as sess:
        sess["session_key"] = "seat-key-2"
    with A.app.app_context():
        g = A.DriveGame(code="USRT", status="waiting", track="sunrise")
        A.db.session.add(g)
        A.db.session.commit()
        A.db.session.add(A.DrivePlayer(game_id=g.id, name="Ada",
                                       color="#ffffff", session_key="seat-key-2"))
        A.db.session.commit()
    body = c.get("/room/USRT").data.decode()
    assert slug in body, "the room's switcher does not list community tracks"


# ------------------------------------------------------- the two lists agreeing

def test_the_python_and_javascript_agree_about_what_collides():
    """`moves.COLLIDING_MODELS` decides whether a board gets wiped;
    `scenery_kit.js` decides whether the car actually hits the thing. A model in
    one list and not the other is either a wall that never wiped a board, or a
    board wiped by a tree."""
    import re
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                           "scenery_kit.js")).read()
    body = js[js.index("const MODELS = {"):js.index("\n};", js.index(
        "const MODELS = {"))]
    ids = re.findall(r"^  ([a-z]+): \{", body, re.M)
    in_js = {o for o in ids
             if "collides: true" in body[body.index("\n  %s: {" % o):
                                         body.index("\n  },", body.index(
                                             "\n  %s: {" % o))]}
    assert in_js == set(moves.COLLIDING_MODELS), (
        "JavaScript says %r collides and Python says %r"
        % (sorted(in_js), sorted(moves.COLLIDING_MODELS)))


def test_a_tree_does_not_cost_anybody_their_lap_time(env):
    """The mesh/collider split, through the real save path: adding decoration to
    a live track re-queues it (what was approved was a particular scene) but
    keeps the board (lap times do not depend on a tree)."""
    A = env
    author, admin = _user(A, "ada"), _user(A, "chinmay")
    c = A.app.test_client()
    _login(c, author)
    doc = _doc(name="Scene Test")
    slug = _publish(A, c, doc)
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    _login(c, author)

    with_tree = json.loads(json.dumps(doc))
    with_tree["scenery"] = [{"o": "tree", "at": 0.3, "side": 1, "off": 30}]
    got = c.post("/api/make/save",
                 json={"doc": with_tree, "slug": slug}).get_json()
    assert got["requeued"] is True, "a changed scene must come back for review"
    assert got["geom_changed"] is False, "a tree is not a road"
    assert got["board_kept"] is True

    # A wall is the other case: the car hits it, so the board went with it.
    _login(c, admin)
    c.post("/admin/tracks/%s/approve" % slug)
    _login(c, author)
    with_wall = json.loads(json.dumps(with_tree))
    with_wall["scenery"].append({"o": "wall", "at": 0.4, "to": 0.46,
                                 "side": -1, "off": 13, "h": 1.6})
    got = c.post("/api/make/save",
                 json={"doc": with_wall, "slug": slug}).get_json()
    assert got["geom_changed"] is True, "a barrier changes where the car can go"
    assert got["board_kept"] is False


@pytest.mark.parametrize("configured,username,allowed", [
    ("chinmay", "chinmay", True),
    ("Chinmay", "chinmay", True),      # the case that was broken
    ("chinmay", "Chinmay", True),
    ("chinmay,ada", "ada", True),
    ("chinmay", "ada", False),
    ("", "chinmay", False),
])
def test_the_queue_and_the_accounts_console_admit_the_same_people(
        env, configured, username, allowed):
    """Two gates, one `ADMIN_USERNAMES`, and they have to agree.

    `accounts/admin.py:admin_names` lowercases the configured list and the
    username. This one did not, so `ADMIN_USERNAMES=Chinmay` opened `/admin`
    and 404'd the track queue - at the one person who is meant to review
    tracks, with nothing anywhere saying why.
    """
    A = env
    A.ADMIN_NAMES = frozenset(n.strip().lower() for n in configured.split(",")
                              if n.strip())
    uid = _user(A, username)
    c = A.app.test_client()
    _login(c, uid)
    want = 200 if allowed else 404
    assert c.get("/admin/tracks").status_code == want


def test_the_two_admin_gates_parse_the_variable_the_same_way():
    """Cross-checked against `accounts/admin.py` by reading it, not importing it.

    Drive's CI job is a sparse checkout of `drive/` alone - `accounts/` is
    checked out for the *site* job - so an import here passes on a laptop and
    fails in the Action. Skipped rather than faked when the file is not there,
    because a green tick from a test that did not run is worse than a skip.
    """
    here = os.path.dirname(__file__)
    other = os.path.join(here, "..", "..", "accounts", "admin.py")
    if not os.path.exists(other):
        pytest.skip("accounts/ is not in this checkout (drive's CI job)")
    src = open(other).read()
    i = src.index("def admin_names(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert ".strip().lower()" in body, (
        "accounts/admin.py no longer lowercases the configured names, so "
        "drive's gate is now the stricter of the two")
    assert ".lower() in admin_names()" in src, (
        "accounts/admin.py no longer lowercases the username")
