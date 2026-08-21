"""The track maker: the routes, the caps, and the one invariant that matters.

Everything here is about a document that nobody has published yet. The most
important test in the file is `test_a_draft_lap_cannot_reach_the_board`, and it
is worth saying why it is a *test* rather than a comment: a draft is driven in
solo mode on the real play page with the real physics, so every board API the
game calls is one that would happily have taken a time on it. What stops that is
`draft` being a reserved slug, which means `tracks.get` can never resolve it,
which means `/api/run` rejects it - three facts in three files, held together by
nothing but this test.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tracks import checks, look, moves, starters             # noqa: E402
import tracks as tracks_mod                                  # noqa: E402


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    close_app(path, verify="0")


@pytest.fixture()
def c(env):
    return env.app.test_client()


# -- the starting shapes -----------------------------------------------------
@pytest.mark.parametrize("shape", starters.ORDER)
def test_every_starting_shape_is_a_legal_track(shape):
    """A starting shape that will not build teaches somebody the editor is broken.

    So each one is held to the same structural bar a pool track is: it builds,
    it has a start and a finish and at least one checkpoint, and no part of the
    road runs too close to another part of itself.
    """
    doc = starters.document(shape)
    t = tracks_mod.from_document("starter-" + shape, doc, timed=True)
    kinds = [g["kind"] for g in t["gates"]]
    assert kinds[0] == "start" and kinds[-1] == "finish"
    assert t["checkpoints"] >= 1
    assert t["spawn"], "nothing to spawn the car onto"
    assert not checks.self_proximity(t), "the road runs too close to itself"
    assert t["medals"]["gold"] < t["medals"]["silver"] < t["medals"]["bronze"]


def test_the_closed_starting_shape_closes_without_the_solver_helping():
    """Circuit closes to the unit, and that is on purpose.

    The first thing anybody does to a closed lap is drag a straight, and they
    should meet the closure solver working on a lap that was already closed
    rather than one that started 8% out. If this fails, the arithmetic in
    `_circuit` and the lengths `start`/`cp` actually lay have drifted apart.
    """
    t = tracks_mod.from_document("starter-circuit",
                                 starters.document("circuit"), timed=False)
    assert t["closed"]
    assert not t.get("closure"), (
        "the solver had to adjust %s; Circuit is supposed to close exactly"
        % t.get("closure"))


def test_a_starting_shape_borrows_a_hand_tuned_palette():
    """Not `look.DEFAULT`, which the contract itself calls unremarkable."""
    for shape in starters.ORDER:
        doc = starters.document(shape)
        assert doc.get("pal"), "%s has no palette" % shape
        assert doc["pal"] != dict(tracks_mod.look.DEFAULT), shape
        assert len(doc["pal"].get("sky", {}).get("stops", [])) >= 6, shape


def test_the_pick_screen_gets_a_plan_view_for_each_shape():
    for s in starters.summaries():
        assert s["plan"].startswith("M"), s["shape"]
        assert s["plan"].count("L") > 20, "%s: too few points to read" % s["shape"]


# -- the pages ---------------------------------------------------------------
def test_the_editor_opens_with_no_account(c):
    assert c.get("/make").status_code == 200
    r = c.get("/make/sprint")
    assert r.status_code == 200
    assert b"Sprint" in r.data


def test_an_unknown_shape_goes_back_to_the_pick_screen(c):
    r = c.get("/make/wormhole")
    assert r.status_code == 302 and r.headers["Location"].endswith("/make")


@pytest.mark.parametrize("url,method", [
    ("/make", "get"), ("/make/sprint", "get"), ("/api/make/build", "post"),
    ("/api/make/lap", "post"), ("/api/make/draft", "post"),
    ("/make/drive/whatever", "get"),
])
def test_the_editor_does_not_exist_in_the_portal_build(c, url, method):
    """CrazyGames forbids a game offering its own login, and authorship without
    identity is not a thing. So the whole maker 404s there, the way `/login`
    already does - not "works but cannot save"."""
    c.get("/solo/sunrise?portal=crazygames")          # sticks in the session
    r = getattr(c, method)(url, json={} if method == "post" else None)
    assert r.status_code == 404, url


# -- building ----------------------------------------------------------------
def test_a_document_builds_into_a_road_with_a_length_and_a_map(c):
    r = c.post("/api/make/build", json=starters.document("mountain"))
    assert r.status_code == 200
    t = r.get_json()["track"]
    assert t["units"] > 100
    assert len(t["spans"]) == len(starters.document("mountain")["moves"])
    # The editor needs a station range per move to highlight one and to put the
    # camera on it, and they have to be in order and cover the ribbon.
    assert t["spans"][0][0] == 0
    assert t["spans"][-1][1] == len(t["line"]) - 1
    for a, b in zip(t["spans"], t["spans"][1:]):
        assert b[0] >= a[0], "spans out of order"


def test_the_editor_build_does_not_pay_for_the_lap_model(c):
    """4ms against 550ms, so the road comes back and the lap does not.

    Named rather than absent: a caller that forgot would otherwise read a stale
    number instead of failing.
    """
    t = c.post("/api/make/build", json=starters.document("sprint")).get_json()["track"]
    assert t["ideal"] is None and t["medals"] is None


def test_the_lap_model_has_its_own_call(c):
    j = c.post("/api/make/lap", json=starters.document("sprint")).get_json()
    assert j["ideal"] > 1
    assert j["medals"]["gold"] < j["medals"]["bronze"]


@pytest.mark.parametrize("doc,expect", [
    ({}, "at least a start"),
    ({"moves": []}, "at least a start"),
    ({"moves": [{"t": "wormhole"}]}, "wormhole"),
    ({"moves": [{"t": "arc", "deg": 40}]}, "rad"),
    ({"moves": [{"t": "straight", "len": 40, "raduis": 3}]}, "raduis"),
])
def test_a_bad_document_is_refused_with_something_a_person_can_act_on(c, doc, expect):
    r = c.post("/api/make/build", json=doc)
    assert r.status_code == 400
    assert expect in r.get_json()["error"], r.get_json()

def test_something_that_is_not_a_document_at_all_is_refused(c):
    r = c.post("/api/make/build", json=[1, 2, 3])
    assert r.status_code == 400
    assert "not a track document" in r.get_json()["error"]


def test_too_many_moves_is_refused(c):
    doc = starters.document("blank")
    doc["moves"] = [doc["moves"][0]] + [{"t": "straight", "len": 10}] * 500
    r = c.post("/api/make/build", json=doc)
    assert r.status_code == 400 and "limit" in r.get_json()["error"]


def test_too_much_road_is_refused(c):
    doc = starters.document("blank")
    doc["moves"] = ([doc["moves"][0]]
                    + [{"t": "straight", "len": 300}] * 40
                    + [doc["moves"][-1]])
    r = c.post("/api/make/build", json=doc)
    assert r.status_code == 400 and "units of road" in r.get_json()["error"]


def test_a_lap_that_will_not_close_says_so_in_its_own_words(c):
    """Not a broken document - a shape that needs a change, and the editor
    tells the author differently."""
    doc = starters.document("circuit")
    for m in doc["moves"]:
        if m["t"] == "straight":
            m["len"] = 20                      # nowhere near closing
    r = c.post("/api/make/build", json=doc)
    assert r.status_code == 400
    assert r.get_json().get("kind") == "closure"


# -- driving a draft ---------------------------------------------------------
def test_a_draft_can_be_parked_and_then_driven(c):
    tok = c.post("/api/make/draft",
                 json=starters.document("stunt")).get_json()["token"]
    r = c.get("/make/drive/" + tok)
    assert r.status_code == 200
    assert b"Stunt Park" in r.data
    # The real play page, in solo mode, with the medals it needs on the first
    # frame - handing it `None` there is a null dereference on the medal card.
    assert b'"medals"' in r.data or b"'medals'" in r.data
    assert b"draft: true" in r.data


def test_an_expired_or_invented_token_goes_back_to_the_editor(c):
    r = c.get("/make/drive/deadbeef")
    assert r.status_code == 302 and r.headers["Location"].endswith("/make")


def test_a_draft_is_driven_under_a_slug_no_player_can_ever_own():
    """The whole board-safety argument in one assertion.

    `draft` is reserved, so no row can be created with it, so `tracks.get` can
    never resolve it, so every board API rejects a time against it.
    """
    import app as A
    assert A.DRAFT_SLUG in tracks_mod.RESERVED
    ok, _why = tracks_mod.slug_is_available(A.DRAFT_SLUG)
    assert not ok
    assert tracks_mod.get(A.DRAFT_SLUG) is None


def test_a_draft_lap_cannot_reach_the_board(c):
    """The one that would actually cost somebody something if it broke."""
    for path in ("/api/run", "/api/start"):
        r = c.post(path, json={"track": "draft", "time_ms": 1234,
                               "splits": [], "inputs": [], "anchors": []})
        assert r.status_code >= 400 or not r.get_json().get("stored"), (
            "%s accepted a lap on an unpublished draft" % path)


def test_the_game_knows_a_draft_has_no_board(c):
    """`countsForTheBoard()` is the single answer, so the flag it reads has to
    reach it - and must not be set on an ordinary solo page."""
    tok = c.post("/api/make/draft",
                 json=starters.document("blank")).get_json()["token"]
    assert b"draft: true" in c.get("/make/drive/" + tok).data
    assert b"draft: false" in c.get("/solo/sunrise").data


def test_countsfortheboard_reads_the_draft_flag():
    """Read out of game.js, because there is no browser in CI.

    Same trick `test_rules_js.py` uses: the source is the specification, and a
    gate that silently stopped mentioning drafts would put laps back on the
    board with every other test still green.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "game.js")).read()
    i = src.index("function countsForTheBoard()")
    body = src[i:src.index("}", i)]
    assert "CFG.draft" in body, (
        "countsForTheBoard no longer excludes drafts:\n" + body)


def test_the_draft_store_is_swept_and_capped(env):
    """It is a dict in memory, so it needs both a clock and a ceiling."""
    A = env
    A._DRAFTS.clear()
    doc = starters.document("blank")
    with A.app.test_client() as c:
        first = c.post("/api/make/draft", json=doc).get_json()["token"]
    A._DRAFTS[first] = (doc, 0.0)                  # pretend it aged out
    A._sweep_drafts()
    assert first not in A._DRAFTS
    for i in range(A._DRAFT_MAX + 20):
        A._DRAFTS["t%d" % i] = (doc, 9e9)
    A._sweep_drafts()
    assert len(A._DRAFTS) <= A._DRAFT_MAX


# ---------------------------------------------------------------- the editor's
# live preview. Read out of the source, because CI has no browser and every one
# of these was a bug first: each is a single token that reverts silently, leaves
# the whole suite green, and breaks dragging a slider.

def _make_js():
    return open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                             "make.js")).read()


def _make_css():
    return open(os.path.join(os.path.dirname(__file__), "..", "templates",
                             "make.html")).read()


def test_the_inspector_threads_the_live_flag_into_setfield():
    """`v => setField(key, v)` drops the flag, and dropping it kills the drag.

    Without it every input event counts as a settled edit, so `commit` rebuilds
    the inspector and replaces the range input under the cursor one frame in.
    The road then sits still for the rest of the drag - measured as exactly one
    preview across a twelve-step drag instead of twelve.
    """
    src = _make_js()
    for call in ("(v, live) => setField(key, v, live)",
                 "(v, live) => setField('w', v, live)"):
        assert call in src, "the inspector stopped passing `live`: " + call


def test_the_rebuild_is_throttled_and_not_debounced():
    """A debounce is cleared by every event, so it never fires during a drag.

    Which is the whole bug: a pointer emitting a change per frame keeps pushing
    the trailing edge away, and the preview only lands once the pointer stops -
    exactly the behaviour the live preview replaced.
    """
    src = _make_js()
    assert "throttle(rebuild" in src, "the rebuild went back to a debounce"
    assert "function throttle(" in src


def test_a_pointer_drag_does_not_end_on_change():
    """Chromium fires `change` on a range input the instant the pointer lands.

    Clicking the track *is* a commit, so ending the drag there tore down the
    inspector one frame in - the same dead-slider symptom by another route.
    Only a keyboard drag, where `change` means one arrow press, may end on it.
    """
    src = _make_js()
    i = src.index("input.addEventListener('change'")
    body = src[i:src.index("});", i)]
    assert "dragMode !== 'key'" in body, (
        "a pointer drag ends on `change` again:\n" + body)


def test_editing_never_moves_the_camera_angle():
    """The 'edit' branch of `aim` may touch the distance, never the angle.

    An editor that re-frames on every keystroke cannot be dragged in: you lose
    the view you were judging the change against, which is the only reason to
    have a live preview at all.
    """
    src = _make_js()
    i = src.index("if (why === 'edit') {")
    branch = src[i:src.index("} else if", i)]
    for banned in ("cam.pitch", "cam.yaw"):
        assert banned not in branch, (
            "editing moves the camera angle again:\n" + branch)
    assert "Math.max(cam.dist" in branch, (
        "the edit branch no longer expands-only:\n" + branch)


def test_selecting_a_move_keeps_a_hand_placed_camera():
    """`select` used to clear `userMoved`, which threw away their orbit."""
    src = _make_js()
    i = src.index("function select(i)")
    body = src[i:src.index("\n  }", i)]
    assert "userMoved" not in body, (
        "selecting a move forgets the camera the author placed:\n" + body)


def test_the_pending_indicator_is_delayed_and_held():
    """Both halves, because each alone is worse than nothing.

    Raised instantly it strobes once per frame of a drag against a fast server;
    dropped instantly it flashes for two frames and reads as a glitch.
    """
    src = _make_js()
    assert "SHOW_AFTER" in src and "SHOW_LEAST" in src
    i = src.index("const SHOW_AFTER")
    after, least = re.search(r"SHOW_AFTER = (\d+), SHOW_LEAST = (\d+)",
                             src[i:i + 80]).groups()
    assert int(after) >= 80, "shown too eagerly to avoid strobing: " + after
    assert int(least) >= int(after), "held for less than it waits: " + least


def test_the_pending_state_has_something_to_show():
    """The class is nothing without the rules, and they live in the template."""
    css = _make_css()
    assert "body.make.building .view::after" in css, "the progress bar is gone"
    assert "body.make.building .spin" in css, "the chip no longer lights up"
    assert "body.make .field.live" in css, (
        "the dragged field is no longer marked, which is the one signal that "
        "shows even when the build is too fast for the bar")


def test_the_drag_registers_one_window_listener_for_all_sliders():
    """`slider()` runs on every redraw of the inspector, which is every commit.

    A window listener registered in there leaks one per slider per commit, each
    holding a detached input alive.
    """
    src = _make_js()
    i = src.index("function slider(key")
    body = src[i:src.index("\n  function segment(", i)]
    assert "window.addEventListener" not in body, (
        "a per-slider window listener is back:\n" + body)
    assert "window.addEventListener('pointerup'" in src


def test_there_is_a_way_back_to_a_wide_view():
    """Holding the angle through every edit removed the only thing that used to
    widen the shot, so it has to be replaced with a deliberate one.

    Otherwise an author who has zoomed in to place a kerb has no route back to
    the whole lap except spinning the wheel.
    """
    src = _make_js()
    i = src.index("if (why === 'frame' || why === 'frame-all') {")
    branch = src[i:src.index("} else if", i)]
    assert "cam.userMoved = false" in branch, (
        "the re-frame no longer overrides a hand-placed camera:\n" + branch)
    assert "cam.pitch" in branch and "cam.dist = fit" in branch
    assert "aim(e.shiftKey ? 'frame-all' : 'frame')" in src, "the F key is gone"
    css = _make_css()
    assert 'id="frame"' in css, "the re-frame button is gone from the page"


def test_only_a_deliberate_reframe_resets_the_angle():
    """One place may write `cam.pitch` outside the frame branch - the untouched
    camera path - and no edit may reach it."""
    src = _make_js()
    i = src.index("function aim(why)")
    body = src[i:src.index("\n  function highlight(", i)]
    assert body.count("cam.pitch") == 2, (
        "the pitch is written from somewhere new in aim():\n" + body)


# --------------------------------------------------------------- driving a draft
# The play page is the pool's play page, so everything a draft must *not* show is
# something being switched off rather than something never built - which is the
# direction that rots. A board control that survives on a draft is a control that
# either opens an empty sheet or silently throws the draft away.

def _draft_page(A):
    """A draft, driven, as HTML - plus the token it is driving under."""
    doc = starters.document("sprint")
    with A.app.test_client() as c:
        token = c.post("/api/make/draft", json=doc).get_json()["token"]
        return c.get("/make/drive/%s" % token).data.decode(), token


def test_a_draft_offers_the_way_back_to_the_editor(env):
    """Driving a draft is a full page navigation, so the editor is gone.

    `history.back()` is not the way back - it reloads the starting shape and
    drops every change. The link has to carry the token.
    """
    html, token = _draft_page(env)
    assert "/make/edit/%s" % token in html, "no link back to the editor"
    assert "Back to the editor" in html


def test_reopening_a_draft_keeps_the_document(env):
    """The whole point of the token round trip: edit, drive, edit, same track."""
    A = env
    doc = starters.document("mountain")
    doc["moves"][1]["len"] = 137.0            # a straight, so `len` is its own
    with A.app.test_client() as c:
        token = c.post("/api/make/draft", json=doc).get_json()["token"]
        page = c.get("/make/edit/%s" % token)
        assert page.status_code == 200
        assert b"137" in page.data, "the reopened editor lost the edit"
        gone = c.get("/make/edit/nope-not-a-token")
        assert gone.status_code == 302, "an expired token should go to /make"


@pytest.mark.parametrize("needle", ['id="btnBoard"', 'id="btnTracks"'])
def test_a_draft_has_no_board_and_no_switcher(env, needle):
    """Board: nothing can hold a time against a draft, so it opens empty.

    Switcher: it navigates to a real track, and a draft has no address to come
    back to - so it is a button that quietly discards the thing being built.

    The key that reaches it is *not* guarded at the key: `test_rules_js.py`
    pins P's exact form, and the rule belongs in `toggleTracks` anyway, where
    it covers the button and the key and whatever calls it next.
    """
    html, _ = _draft_page(env)
    assert needle not in html, "a draft still shows %s" % needle
    with env.app.test_client() as c:                 # and the pool still does
        assert needle in c.get("/solo/sunrise").data.decode()


def test_a_draft_offers_no_ghost_but_off(env):
    """Every other option needs a board to come from."""
    html, _ = _draft_page(env)
    assert html.count("data-ghost=") == 1, "a draft offers a ghost it cannot load"
    assert 'data-ghost="off"' in html


def test_a_draft_does_not_call_a_session_best_a_personal_best(env):
    """It is real, and it was not kept. Saying `personal best` implies it was."""
    html, _ = _draft_page(env)
    assert "Best this session" in html
    assert "Personal best" not in html


def test_a_draft_does_not_share_a_stored_best_with_the_next_draft():
    """Every draft drives under the one reserved slug, so the key is shared.

    Without the guard, setting a 20s lap on one draft and then opening a
    completely different one greets you with a personal best of 20s on a road
    you have never driven.
    """
    src = _game_js()
    for fn in ("function localBest(", "function storedBest("):
        body = src[src.index(fn):src.index("\n}", src.index(fn))]
        assert "CFG.draft" in body, "%s does not skip drafts:\n%s" % (fn, body)


def test_a_draft_shows_the_medals_but_not_the_record():
    """The medals are derived from the road and are the most useful thing an
    author can read here. The record is a board row that can only be a dash."""
    src = _game_js()
    assert "CFG.draft ? '' :" in src, "the WR row is back on drafts"
    assert "GHOST_CYCLE_DRAFT" in src


def _game_js():
    return open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                             "game.js")).read()


# ----------------------------------------------------------------- the palette
# `look.check` refuses palettes that cannot work; `look.advise` says so about
# palettes that work and are wrong. The split matters: one raises and one is only
# ever read, and a taste threshold that blocks would be a house style enforced on
# somebody else's track.

def _bad(**over):
    """look.DEFAULT with something wrong with it."""
    import copy
    p = copy.deepcopy(look.DEFAULT)
    for path, v in over.items():
        node, keys = p, path.split("__")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = v
    return p


def test_the_default_palette_is_silent():
    """It is what a brand new track gets. It cannot arrive already complaining."""
    assert look.advise(look.DEFAULT) == []


def test_no_palette_in_the_pool_is_told_it_is_wrong():
    """A `warn` is `this is very likely wrong`, so a shipped track tripping one
    is a broken threshold - and a threshold a real track trips is one nobody
    believes the second time.

    Notes are allowed here on purpose: somebody forking Tokyo Drift inherits
    Tokyo Drift's actual trade-offs and is better off being told what they are.
    """
    loud = {}
    for t in tracks_mod.TRACKS:
        warns = [k for lvl, k, _ in look.advise(t.get("pal") or {}) if lvl == "warn"]
        if warns:
            loud[t["slug"]] = warns
    assert not loud, "advise() warns about shipped tracks: %r" % loud


@pytest.mark.parametrize("name,pal,want", [
    ("blob",     _bad(ground=look.DEFAULT["road"]),                    "ground"),
    ("mud",      _bad(road=0x606060, sky__light={"color": 0xff9040,
                                                 "intensity": 1.3,
                                                 "dir": [0.5, 0.8, 0.3]}), "road"),
    ("bounce",   _bad(sky__hemi={"sky": 0xdfe9f2, "ground": 0xff7a10,
                                 "intensity": 1.1}),                   "hemi"),
    ("glow",     _bad(sky__glowStrength=0.9, sky__glowFocus=3),  "glowStrength"),
    ("junkyard", _bad(density=1.4),                                   "density"),
    ("fog near", _bad(sky__fogFar=300),                                "fogFar"),
    ("fog far",  _bad(sky__fogFar=4000),                               "fogFar"),
    ("flat sky", _bad(sky__stops=look.DEFAULT["sky"]["stops"][:3]),     "stops"),
    ("too dark", _bad(road=0x0a0b10,
                      sky__hemi={"sky": 0x101014, "ground": 0x30303a,
                                 "intensity": 0.4},
                      sky__light={"color": 0xaab0c0, "intensity": 0.5,
                                  "dir": [0.5, 0.8, 0.3]}),            "road"),
])
def test_every_taste_warning_can_actually_fire(name, pal, want):
    """A threshold nothing reaches is a threshold that does nothing."""
    keys = [k for _, k, _ in look.advise(pal)]
    assert want in keys, "%s did not fire (got %r)" % (name, keys)


def test_advice_says_which_key_it_is_about():
    """The editor puts each message under the control that caused it, so the key
    has to be a real palette field rather than prose."""
    for _, key, text in look.advise(_bad(density=1.4, sky__fogFar=4000)):
        assert key in look.KNOWN or key in ("stops", "hemi", "glowStrength",
                                            "fogFar"), key
        assert len(text) > 40, "a message too short to be actionable: %r" % text


def test_the_look_endpoint_advises_and_refuses(env):
    A = env
    with A.app.test_client() as c:
        ok = c.post("/api/make/look", json=look.DEFAULT).get_json()
        assert ok["ok"] is True and ok["advice"] == []
        loud = c.post("/api/make/look", json=_bad(density=1.4)).get_json()
        assert [a["level"] for a in loud["advice"]] == ["warn"]
        broken = c.post("/api/make/look", json={"road": 1}).get_json()
        assert broken["ok"] is False
        # and the message may not send a player looking for a file that is not
        # theirs and does not exist
        assert "tracks/" not in broken["error"].split("look.py")[0]
        assert c.post("/api/make/look", json=[]).status_code == 400


def test_the_editor_draws_a_control_for_every_palette_key():
    """`Full palette editor, every key, for everyone` was the decision, so a key
    added to `look.py` has to be a decision about the editor too.

    The exclusions are not colour. They are geometry derived off the ribbon -
    a height field, a grandstand, a shoreline - and they belong to the scenery
    editor. A palette carrying them keeps them untouched through a borrow.
    """
    SCENERY = {"terrain", "furniture", "building", "shore",
               "rainbow", "rainbowLanes", "props", "below", "rain"}
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "make.js")).read()
    schema = src[src.index("const LOOK = ["):src.index("];", src.index("const LOOK = ["))]
    missing = [k for k in look.KNOWN
               if k not in SCENERY and ("'" + k + "'") not in schema
               and ("'" + k + ".") not in schema and k != "sky"]
    assert not missing, (
        "these palette keys have no control in the editor, and are not listed "
        "as scenery: %r" % missing)


def test_the_editor_repaints_a_palette_without_the_server():
    """A palette is read by buildTrack and the renderer and by nothing else, so
    a colour change is a few milliseconds of local work. Routing it through
    /api/make/build would put a ribbon replay behind every drag of a colour."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "make.js")).read()
    body = src[src.index("function repaint()"):src.index("\n  }", src.index(
        "function repaint()"))]
    assert "buildTrack" in body and "setTrack" in body
    assert "api/make/build" not in body


def test_the_ride_uses_the_games_own_chase_geometry():
    """A palette is judged in motion. If the preview's framing is invented, the
    thing being judged is not the thing that ships."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                            "make.js")).read()
    body = src[src.index("function rideCamera"):src.index(
        "\n  function placeCamera")]
    for n in ("8.2", "3.4", "0.075", "3.2", "1.1", "0.02", "0.16"):
        assert n in body, "the ride camera no longer matches render.js (%s)" % n
    render = open(os.path.join(os.path.dirname(__file__), "..", "static", "js",
                              "render.js")).read()
    assert "8.2 + Math.min(3.4, speed * 0.075)" in render, (
        "render.js's chase camera moved; the ride preview now lies")


def test_the_switcher_is_refused_inside_togglettracks_not_at_the_key():
    """Where the rule lives is the point. At the key it covers one caller and
    breaks `test_rules_js.py`, which pins P's exact form; in the function it
    covers the key, the button, and whatever reaches it next."""
    src = _game_js()
    body = src[src.index("function toggleTracks("):
               src.index("\n  const on =", src.index("function toggleTracks("))]
    assert "CFG.draft" in body, "toggleTracks no longer refuses a draft"


# ------------------------------------------------------- what a layout may be
# `replay` raises on a document it cannot build. `moves.advise` is the other
# half: documents that build perfectly and describe a track nobody can drive.
# A corner of radius 4 is valid geometry and the builder is right to lay it; the
# reason it must not ship is a fact about the physics, not about the schema.
#
# These rules were assertions in `test_tracks.py` and nowhere else, which was
# fine while every track was a file somebody wrote on purpose. A document now
# arrives from an editor - or from somebody's AI - so they have to be sayable to
# the person who caused them.

def _sprint_with(extra, at=4):
    doc = starters.document("sprint")
    doc["moves"].insert(at, extra)
    return doc


def test_a_corner_nothing_can_drive_is_refused():
    """The complaint that started the whole rewrite was one corner shape, and
    its radius was four."""
    got = moves.advise(_sprint_with(
        {"t": "arc", "deg": 90, "rad": 4, "w": 12, "rail": ""}))
    refused = [(i, t) for lvl, i, t in got if lvl == "refuse"]
    assert refused, "a 4-unit corner was not refused: %r" % got
    assert refused[0][0] == 4, "the refusal does not say which move"
    assert "4" in refused[0][1] and str(int(checks.MIN_RADIUS)) in refused[0][1]


def test_a_loop_too_tight_is_a_note_and_not_a_refusal():
    """It is drivable, barely, and somebody may want it that way. Under about 18
    there is nothing holding the car over the top but gravity - which is worth
    saying and not worth forbidding."""
    got = moves.advise(_sprint_with({"t": "loop", "rad": 11, "w": 12}))
    levels = {lvl for lvl, _, _ in got}
    assert "note" in levels and "refuse" not in levels, got


@pytest.mark.parametrize("doc,why", [
    ({"moves": []}, "no moves"),
    ({"moves": [{"t": "straight", "len": 40}, {"t": "finish"}]}, "no start"),
    ({"moves": [{"t": "start"}, {"t": "straight", "len": 40}]}, "no finish"),
    ({"moves": [{"t": "start"}, {"t": "finish"}, {"t": "straight", "len": 9}]},
     "finish is not last"),
])
def test_a_track_without_both_ends_is_refused(doc, why):
    assert any(lvl == "refuse" for lvl, _, _ in moves.advise(doc)), why


def test_corners_that_are_all_the_same_corner_get_said_out_loud():
    """The Circuit starter is four identical 46s, which is exactly the note."""
    got = moves.advise(starters.document("circuit"))
    texts = " ".join(t for lvl, _, t in got if lvl == "note")
    assert "radi" in texts, got
    assert not [1 for lvl, _, _ in got if lvl == "refuse"]


def test_no_starting_shape_is_refused():
    """They are the first thing anybody sees. A starter that arrives unplayable
    is worse than no starter."""
    bad = {}
    for shape in starters.SHAPES:
        r = [t for lvl, _, t in moves.advise(starters.document(shape))
             if lvl == "refuse"]
        if r:
            bad[shape] = r
    assert not bad, bad


def test_no_track_in_the_pool_is_refused():
    """Nineteen tracks that ship. A rule any of them breaks is a wrong rule."""
    from tools import to_moves
    loud = {}
    for slug in to_moves.slugs():
        doc, _dropped = to_moves.document(slug)
        r = [t for lvl, _, t in moves.advise(doc) if lvl == "refuse"]
        if r:
            loud[slug] = r
    assert not loud, loud


def test_the_build_endpoint_returns_the_notes_beside_the_road(env):
    """Beside, and not instead: the editor shows the road you asked for and says
    what is wrong with it. A 400 here would mean the preview went blank the
    moment a radius crossed 12, mid-drag."""
    A = env
    with A.app.test_client() as c:
        r = c.post("/api/make/build", json=_sprint_with(
            {"t": "arc", "deg": 90, "rad": 4, "w": 12, "rail": ""}))
        assert r.status_code == 200, "an undrivable corner must still build"
        j = r.get_json()
        assert j["track"]["line"], "no road came back"
        levels = [n["level"] for n in j["notes"]]
        assert "refuse" in levels, j["notes"]
        assert [n for n in j["notes"] if n["at"] == 4]


def test_the_vocabulary_handed_to_a_model_describes_every_move(env):
    """`_moves_spec` is generated from SPEC and HELP together, so a move gaining
    a field is a move whose description gains it too."""
    v = env._moves_spec()
    assert {m["t"] for m in v["moves"]} == set(moves.SPEC)
    for m in v["moves"]:
        assert len(m["what"]) > 40, "no useful description of %s" % m["t"]
        assert set(m["fields"]) == set(moves.SPEC[m["t"]]), m["t"]
    # And the numbers are the ones that are enforced, not a second copy.
    assert v["limits"]["min_arc_radius"] == checks.MIN_RADIUS
    assert v["limits"]["min_loop_radius"] == checks.MIN_LOOP_RADIUS
    assert v["limits"]["distinct_radii"] == checks.RADII_DISTINCT


def test_the_ai_is_given_both_halves_of_the_job():
    """One assistant, layout and scenery. A panel that could only help with the
    scenery would be help with the easier half: scenery at least looks like
    graphics code, and a document of {"t": "arc", "deg": -150} looks like
    nothing at all."""
    src = _make_js()
    body = src[src.index("function promptBlocks()"):
               src.index("\n  }", src.index("function promptBlocks()"))]
    assert "layoutSpec()" in body and "apiSpec()" in body, body
    # Rebuilt per turn, not captured once: after three edits the model has to be
    # looking at the track as it is rather than as it was when the chat opened.
    ask = src[src.index("async function ask()"):src.index("\n  }", src.index(
        "async function ask()"))]
    assert "promptBlocks()" in ask


def test_a_layout_that_cannot_be_driven_is_never_offered():
    """It built, so there is a diff to draw and an Apply button to draw it
    under. Applying would leave the author several edits later in a state the
    submit gate refuses, with no memory of where it came from."""
    src = _make_js()
    body = src[src.index("async function proposeLayout"):
               src.index("\n  }\n", src.index("async function proposeLayout"))]
    i = body.index("refused")
    assert "level === 'refuse'" in body
    assert body.index("return;", i) < body.index("diffMoves", i), (
        "a refused layout still reaches the diff and the Apply button")


def test_the_diff_is_a_real_edit_script():
    """A model asked to add a hairpin returns the whole document and can quietly
    rewrite four other corners on the way past, so a positional comparison would
    report every move after an insertion as changed."""
    src = _make_js()
    body = src[src.index("function diffMoves"):src.index(
        "\n  }", src.index("function diffMoves"))]
    assert "Uint16Array" in body, "the diff is no longer an LCS"


def test_the_track_maker_doc_does_not_state_a_stale_number():
    """`docs/track-maker.md` is the file a future session reads instead of this
    code, and its two most load-bearing numbers are the two most likely to rot.

    Only these two: the point is not to pin prose, it is that a doc claiming
    thirty-eight models when there are forty-one teaches somebody the wrong
    thing about a library they are about to extend.
    """
    import re
    here = os.path.dirname(__file__)
    # Whitespace-normalised: the doc is wrapped at 80 columns, so "Fifteen" and
    # "move types" are routinely on different lines.
    doc = re.sub(r"\s+", " ",
                 open(os.path.join(here, "..", "docs",
                                   "track-maker.md")).read())
    kit = open(os.path.join(here, "..", "static", "js",
                            "scenery_kit.js")).read()
    n = len(re.findall(r"^  ([a-z]+): \{",
                       kit[kit.index("const MODELS = {"):], re.M))
    assert "%d models" % n in doc, (
        "the doc says a different number of scenery models than the %d there "
        "are" % n)
    words = {15: "Fifteen", 16: "Sixteen", 17: "Seventeen", 14: "Fourteen"}
    assert "%s move types" % words.get(len(moves.SPEC), "?") in doc, (
        "the doc miscounts the move vocabulary; there are %d"
        % len(moves.SPEC))
