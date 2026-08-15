"""Running inside somebody else's page.

A portal (CrazyGames, Poki) does not host the game - it frames it, so the top
level site is theirs and every request the browser makes for us is third-party.
Two things break under that and neither breaks *loudly*, which is why they are
pinned here rather than left to be noticed:

* **the session cookie stops being sent.** An unset `SameSite` defaults to `Lax`
  in every current browser, and `Lax` means "not on a cross-site top-level".
  There is no error and no warning - the player simply appears logged out
  forever. The tests below assert the two attributes that fix it, and assert
  just as hard that a local `http://` checkout does *not* get them, because
  `Secure` on a plain-http dev box means no cookie at all.
* **the keyboard never arrives.** An iframe gets no key events until something
  inside it is clicked, so the game would load, render, and ignore W. The door
  is the fix and `html.framed` is what shows it; both are asserted to exist,
  since a door that is never shown is the same bug wearing a fix.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _boot(secure):
    """Import a fresh `app` with SESSION_COOKIE_SECURE on or off.

    The config is read at import time, so this cannot be a config poke after the
    fact - the `after_request` hook keys off what the import decided.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path
    os.environ["DRIVE_VERIFY"] = "0"
    if secure:
        os.environ["SESSION_COOKIE_SECURE"] = "1"
    else:
        os.environ.pop("SESSION_COOKIE_SECURE", None)
    for mod in ("app", "models"):
        sys.modules.pop(mod, None)
    import app as A
    A.app.config["TESTING"] = True
    with A.app.app_context():
        A.db.drop_all()
        A.db.create_all()
    return A, path


@pytest.fixture()
def secure_env():
    A, path = _boot(secure=True)
    yield A
    os.environ.pop("SESSION_COOKIE_SECURE", None)
    os.environ.pop("DRIVE_VERIFY", None)
    os.unlink(path)


@pytest.fixture()
def plain_env():
    A, path = _boot(secure=False)
    yield A
    os.environ.pop("DRIVE_VERIFY", None)
    os.unlink(path)


def _session_cookie(resp, name="session"):
    """The `Set-Cookie` line for our own session, or None.

    Every route here sets one (Flask writes a session cookie on anything that
    touches `session`), so `/guest` is used: it is the shortest route that puts
    something in the session on purpose.
    """
    for line in resp.headers.getlist("Set-Cookie"):
        if line.startswith(name + "="):
            return line
    return None


def _set_a_session(A):
    client = A.app.test_client()
    return client.post("/guest", json={"name": "Rosa"})


def test_a_framed_session_cookie_survives_being_third_party(secure_env):
    """SameSite=None and Partitioned, or the portal player has no session at all."""
    resp = _set_a_session(secure_env)
    assert resp.status_code == 200
    line = _session_cookie(resp)
    assert line is not None, "no session cookie was set at all"
    assert "SameSite=None" in line
    assert "Partitioned" in line
    # `None` without `Secure` is rejected outright by the browser, so the pair
    # has to travel together - asserting one without the other would pass over
    # a cookie no browser accepts.
    assert "Secure" in line


def test_a_plain_http_checkout_keeps_the_cookie_it_always_had(plain_env):
    """The local box is not framed and must not be given a Secure cookie.

    `Secure` over `http://localhost:5005` is not a lesser cookie, it is no
    cookie: the browser declines to send it, and every dev login would silently
    fail. This is the test that keeps the fix inside the `if`.
    """
    resp = _set_a_session(plain_env)
    line = _session_cookie(resp)
    assert line is not None
    assert "SameSite=None" not in line
    assert "Partitioned" not in line
    assert "Secure" not in line


def test_only_our_own_cookie_is_rewritten(secure_env):
    """The hook rebuilds the Set-Cookie list, so anything else on it must survive."""
    A = secure_env

    @A.app.route("/_t_extra")
    def _extra():
        from flask import make_response, session
        session["guest_name"] = "Rosa"
        r = make_response("ok")
        r.set_cookie("unrelated", "1")
        return r

    resp = A.app.test_client().get("/_t_extra")
    lines = resp.headers.getlist("Set-Cookie")
    ours = [c for c in lines if c.startswith("session=")]
    theirs = [c for c in lines if c.startswith("unrelated=")]
    assert len(ours) == 1 and "Partitioned" in ours[0]
    assert len(theirs) == 1 and "Partitioned" not in theirs[0]


def test_the_play_page_carries_the_door_and_the_class_that_shows_it(plain_env):
    """Both halves, because either alone is the bug.

    The door with no `framed` class is a click-through charged to every visitor
    at our own address; the class with no door is a portal player pressing W at
    a game that cannot hear them.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert 'id="frameStart"' in html
    assert "window.self !== window.top" in html
    assert "classList.add('framed')" in html


def test_the_door_is_in_the_head_and_not_behind_the_module(plain_env):
    """It has to be set before the stylesheet paints.

    A `framed` class that arrives with game.js arrives one whole track build
    late, and the overlay flashes in after the player has already tried the
    keys. Asserting the *order* is what catches that being moved: the marker
    must be above the module tag, not merely present.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert html.index("classList.add('framed')") < html.index("</head>")


def test_the_one_link_that_leaves_the_site_is_marked(plain_env):
    """`leaves-frame` is what hides it inside a portal, and it is a class in a
    template - so nothing but a test notices it being dropped."""
    html = plain_env.app.test_client().get("/leaderboard").get_data(as_text=True)
    assert "discord.gg" in html
    i = html.index("discord.gg")
    assert "leaves-frame" in html[max(0, i - 300):i]


def test_touch_is_decided_once(plain_env):
    """`window.DRIVE_TOUCH` is the only answer, and game.js must read it.

    It used to be computed inside game.js's `init`, which was fine while that was
    the only consumer. The framed door is drawn before the module loads and needs
    the same answer, so a second copy of the expression in a template was the
    obvious move and would have been a drift bug of exactly the kind this repo
    keeps writing down: two tests of "is this a phone" that agree until one of
    them is edited.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert "window.DRIVE_TOUCH" in html
    js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")
    js = open(js_path).read()
    assert "window.DRIVE_TOUCH" in js
    assert "ontouchstart" not in js, "game.js is deciding touch for itself again"


def test_the_door_is_not_nested_inside_the_hud(plain_env):
    """It has to be a sibling of `#rotate`, not a child of `.hud`.

    z-index is measured within the nearest stacking context, and `.hud` makes
    one - so the door nested in there sat at 9000 and still lost to `#rotate` at
    70, which printed the portrait notice straight through the middle of it. The
    fix was to move the element, so it is the element's *position* that has to be
    pinned; the z-index alone would pass and still be broken.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    door = html.index('id="frameStart"')
    hud_close = html.index('<div id="rotate"')
    assert door < hud_close, "the door moved back inside the HUD"
    # Everything the HUD owns closes before the door opens: the last `.hud`
    # descendant to appear is well above it in the document.
    assert html.index('class="hud"') < door


def test_no_template_comment_leaks_onto_the_page(plain_env):
    """A `{# #}` that loses its closer prints itself, and it prints *large*.

    This is not hypothetical - it happened while the door above was being
    written. An edit added a paragraph after a comment's `#}` instead of before
    it, and the result was two lines of prose about iframes rendered across the
    top of the game, in the page's own body text, on every play page. Nothing
    failed: the tests passed, the HTML was valid, the game worked. It was
    visible only in a screenshot.

    `#}` is the tell and it is a safe one - a closer that reaches the output is
    always a bug, and the character pair appears nowhere in the game's own copy.
    """
    client = plain_env.app.test_client()
    for path in ("/", "/solo/sunrise", "/leaderboard", "/lobbies", "/login"):
        html = client.get(path).get_data(as_text=True)
        assert "#}" not in html, "unclosed template comment leaked into " + path
        assert "{#" not in html, "unclosed template comment leaked into " + path


def test_nothing_refuses_to_be_framed(plain_env):
    """An `X-Frame-Options` or a `frame-ancestors` anywhere here is a blank frame.

    Nothing sets one today. This is a guard rather than a discovery: the header
    is the sort of thing a security sweep adds by default, and the symptom on a
    portal is a white box with no error in any console.
    """
    for path in ("/", "/solo/sunrise", "/leaderboard"):
        resp = plain_env.app.test_client().get(path)
        assert "X-Frame-Options" not in resp.headers, path
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors" not in csp, path
