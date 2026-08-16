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


def _css():
    return open(os.path.join(os.path.dirname(__file__), "..", "static", "css",
                             "style.css"), encoding="utf-8").read()


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


def _a_user(A, name="rosa"):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _login(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid


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


def test_the_visitor_cookie_survives_being_third_party_too(secure_env):
    """`cgv` is the analytics id, and `Lax` made it useless in a frame.

    Not a crash and not a gap in the data - something worse, because it looks
    like data. A `Lax` cookie is never sent from a framed page, so every request
    a portal player made arrived with no id, was handed a fresh one, and counted
    as a new person: one "new visitor" per page view, which has the shape of a
    traffic spike and is indistinguishable from one afterwards.
    """
    resp = _set_a_session(secure_env)
    line = _session_cookie(resp, "cgv")
    assert line is not None, "no visitor cookie was set at all"
    assert "SameSite=None" in line
    assert "Partitioned" in line
    assert "Secure" in line


def test_the_visitor_cookie_is_unchanged_on_a_plain_http_box(plain_env):
    """Same reasoning as the session cookie: Secure over http is no cookie."""
    resp = _set_a_session(plain_env)
    line = _session_cookie(resp, "cgv")
    assert line is not None
    assert "SameSite=Lax" in line
    assert "Partitioned" not in line
    assert "Secure" not in line


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


def test_the_door_is_shown_once_per_tab_and_not_once_per_page(plain_env):
    """`needs-door` is a different question from `framed`, and that is the point.

    The door buys exactly one thing: the keyboard, which an iframe does not get
    until something inside it is clicked. Focus then belongs to this browsing
    context and survives navigating *within* the frame - so the trip out to the
    leaderboard and back was charging a second and third click for something
    already paid for, which is what a portal player actually complained about.

    `sessionStorage` is the right lifetime rather than a convenient one: per tab
    and per partition, so a genuinely new browsing context - a new tab, which has
    not been clicked in - correctly gets the door again.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert "classList.add('needs-door')" in html
    assert "sessionStorage.getItem('drive.door')" in html
    assert "sessionStorage.setItem('drive.door', '1')" in html
    css = _css()
    assert "html.needs-door #frameStart" in css
    assert "html.framed #frameStart" not in css, (
        "the door is back on `framed`, so it reappears on every framed page")


def test_the_door_flag_is_read_before_the_stylesheet_paints(plain_env):
    """Same reason `framed` is in the head: a class that arrives late flashes.

    A door that paints and then removes itself a moment later is worse than
    either behaviour on its own - it reads as the game glitching on load, on the
    one screen a portal reviewer actually watches.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert html.index("classList.add('needs-door')") < html.index("</head>")


def test_a_browser_with_no_session_storage_still_gets_the_door(plain_env):
    """The `catch` adds the class rather than skipping it.

    No storage means no memory of the click, and the two ways to be wrong are not
    equal: a door shown twice is a nuisance, a keyboard that never arrives is a
    game that ignores W forever.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    i = html.index("sessionStorage.getItem('drive.door')")
    tail = html[i:i + 700]
    catch = tail[tail.index("catch"):]
    assert "classList.add('needs-door')" in catch, catch[:300]


def test_the_door_is_in_the_head_and_not_behind_the_module(plain_env):
    """It has to be set before the stylesheet paints.

    A `framed` class that arrives with game.js arrives one whole track build
    late, and the overlay flashes in after the player has already tried the
    keys. Asserting the *order* is what catches that being moved: the marker
    must be above the module tag, not merely present.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert html.index("classList.add('framed')") < html.index("</head>")


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


def test_every_link_that_leaves_drive_opens_a_new_tab(plain_env):
    """A link out navigates *the frame*, which is how a portal loses the game.

    The player ends up looking at cgovind.com in a 960px box on somebody else's
    page, with no back button and no way to return - and the portal counts that
    as the game sending its traffic away, which both CrazyGames and Poki name as
    grounds for rejection.

    Written as a sweep over the rendered HTML rather than a list of three known
    links, because the failure mode is a *fourth* one being added later: there is
    nothing about writing `href="{{ site_url }}/accounts/..."` that suggests it
    needs a target, and at our own address the omission is invisible.
    """
    import re
    client = plain_env.app.test_client()
    uid = _a_user(plain_env)
    _login(client, uid)
    for path in ("/account", "/lobbies", "/login", "/leaderboard", "/"):
        html = client.get(path).get_data(as_text=True)
        for tag in re.findall(r"<a\b[^>]*>", html):
            href = re.search(r'href="([^"]*)"', tag)
            if not href:
                continue
            url = href.group(1)
            leaves = url.startswith("http") and "drive.cgovind.com" not in url
            if not leaves:
                continue
            assert 'target="_blank"' in tag, (
                "%s: link to %s would navigate the frame away: %s"
                % (path, url, tag))
            assert "noopener" in tag, "%s: %s needs rel=noopener" % (path, url)


def test_the_portal_sdk_is_never_fetched_off_a_portal(plain_env):
    """The script tag must not be in the markup - it is built at runtime, framed only.

    Two separate promises rest on this. Their SDK is a third-party script on
    somebody else's CDN, and /privacy says in as many words that this site loads
    no third-party anything; a `<script src="sdk.crazygames.com">` sitting in the
    play page would make that untrue for every player on drive.cgovind.com. And
    off a CrazyGames domain the SDK is documented to enter "disabled" mode where
    every call throws, so fetching it here buys a request and a hazard and no
    feature.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert "<script src=\"https://sdk.crazygames.com" not in html
    assert "sdk.crazygames.com/crazygames-sdk-v2.js" in html, (
        "the loader is gone entirely; a portal launch needs gameplayStart")
    # The guard that keeps it that way, and the flag that lets it be watched.
    i = html.index("sdk.crazygames.com")
    guard = html[max(0, i - 1200):i]
    assert "classList.contains('framed')" in guard
    assert "useLocalSdk=true" in guard


def test_nothing_calls_the_sdk_without_a_guard(plain_env):
    """Every call goes through `send`, which is the only place with a try/catch.

    "All the calls to the SDK methods will throw an error" is their own
    description of the disabled environment, so a direct
    `CrazyGames.SDK.game.gameplayStart()` anywhere would raise on this site at
    the moment the game became playable. game.js may only speak to the wrapper.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")
    js = open(js_path).read()
    assert "CrazyGames" not in js, "game.js is talking to the SDK directly"
    assert "window.DrivePortal" in js
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    # In the page, the module is only ever reached through the wrapper's `send`.
    for call in ("gameplayStart", "gameplayStop"):
        direct = "SDK.game.%s(" % call
        assert direct not in html, "unguarded %s in the page" % call


def test_the_door_waits_for_a_warm_renderer(plain_env):
    """Both halves of the loading gate, because either alone is a bug.

    The gate exists because of what CrazyGames saw and this site never could:
    WebGL links a shader program the first time a material is drawn and Chrome
    caches those per origin, so a cold origin ran at about 2fps for ten seconds
    and then perfectly. The fix is to draw those frames behind an opaque door.

    Without the click guard, an impatient player opens the door onto the
    juddering game the door exists to hide. Without the timer, a throttled iframe
    (below the fold, background tab) never gets the frames that would notice it
    should open, and the game is unreachable behind a Loading screen for ever.
    """
    html = plain_env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    assert "fs-wait" in html and "fs-ready" in html
    assert "isReady()" in html, "the click is not gated on the door being open"
    assert "setTimeout(ready, 8000)" in html, "the door has no guaranteed opening"
    # And the listener may not be spent by a press that did nothing.
    #
    # Comments are stripped before looking, because the line that says why this
    # is not `{ once: true }` contains the words `{ once: true }` - the first
    # version of this test failed on the note explaining the fix.
    door = html[html.index("window.DriveDoor"):]
    code = "\n".join(l for l in door[:6000].splitlines()
                     if not l.lstrip().startswith("//"))
    assert "once: true" not in code, (
        "a press while Loading would consume the only listener")


def test_the_shaders_are_built_before_the_first_frame(plain_env):
    """`precompile` hangs off `setTrack`, which is the one place a world is installed.

    Both paths need it and only one is obvious: the initial load, and the track
    switcher, which builds a whole new world without navigating. Hanging it off
    `setTrack` is what makes the second one free.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "render.js")
    js = open(js_path).read()
    assert "precompile()" in js
    assert "renderer.compile(" in js
    # It has to be called from setTrack, after the world and its lights are in.
    set_track = js[js.index("  setTrack(built) {"):]
    body = set_track[:set_track.index("\n  /**")]
    assert "this.precompile();" in body, "precompile is not called from setTrack"


def test_the_privacy_notice_exists_and_can_be_found(plain_env):
    """A policy nobody can reach is not a policy, and a portal checks for it.

    CrazyGames will not take a game that collects anything beyond the SDK's own
    events without a notice, and `visits.py` writes a row per request carrying
    an IP and a user agent. Reachability is the half worth pinning: the page
    itself is hard to delete by accident, whereas the two links to it are one
    line each in templates nobody edits for this reason.
    """
    client = plain_env.app.test_client()
    assert client.get("/privacy").status_code == 200
    for path in ("/", "/solo/sunrise"):
        assert "/privacy" in client.get(path).get_data(as_text=True), (
            "no way to reach the privacy notice from %s" % path)
    assert "/privacy" in client.get("/sitemap.xml").get_data(as_text=True)


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
