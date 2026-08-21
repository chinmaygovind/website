"""The CrazyGames build of Drive: what it is, and what it is not.

Drive is submitted to CrazyGames as an iframe game, and their review is a
checklist rather than an opinion. Two of its items are the reason this file
exists, and both fail *silently* in the sense that matters - the game works
perfectly and the submission is refused.

* **"Does not offer external login options."** Facebook, Google and email login
  are all forbidden inside the frame; only CrazyGames' own account may sign
  somebody in. Drive's login is username-and-password over email, so in the
  portal build it is gone - and gone means the routes 404, not that a template
  stopped linking to them. A reviewer who finds `/login` by typing it has found
  an external login option.
* **Sitelock.** `frame-ancestors` has to name every domain they serve from.
  That half is in `test_embedding.py`, with the rest of what a frame changes.

Everything here runs against the real app on a throwaway database, and the
token half runs against a key pair made in the test - `verify_token` is handed a
real RS256 JWT and asked to take it, and handed several near-misses and asked to
refuse them.
"""

import os
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


def _portal_client(A):
    """A client that has arrived through CrazyGames, the way a player does."""
    client = A.app.test_client()
    client.get("/solo/sunrise?portal=crazygames")
    return client


# ---------------------------------------------------------------------------
# Which build am I
# ---------------------------------------------------------------------------

def test_the_portal_flag_sticks_for_the_rest_of_the_visit(env):
    """A portal sets the entry URL and nothing after it.

    Every link, form and socket handshake from then on is ours and none of them
    would carry `?portal=`, so the flag has to live in the session. Without
    this, page two of the portal build is the cgovind.com build, complete with
    the login form the whole exercise is about removing.
    """
    client = _portal_client(env)
    with client.session_transaction() as s:
        assert s["portal"] == "crazygames"
    assert client.get("/login").status_code == 200
    assert "Sign in with CrazyGames" in client.get("/login").get_data(as_text=True)


def test_an_ordinary_visitor_is_never_in_the_portal_build(env):
    client = env.app.test_client()
    with client.session_transaction() as s:
        assert "portal" not in s
    html = client.get("/login").get_data(as_text=True)
    assert "Password" in html and "Sign in with CrazyGames" not in html


def test_an_unknown_portal_leaves_rather_than_sticking(env):
    """`?portal=none` is the way out, and so is anything unrecognised.

    A stale flag would be a session with no login page and no way to reach one,
    which is a worse state than either build.
    """
    client = _portal_client(env)
    client.get("/?portal=none")
    with client.session_transaction() as s:
        assert "portal" not in s
    assert "Password" in client.get("/login").get_data(as_text=True)


# ---------------------------------------------------------------------------
# No external login options
# ---------------------------------------------------------------------------

def test_the_password_routes_do_not_exist_in_the_portal(env):
    """404, and from the *routes* rather than from the page that linked to them.

    A template that stops rendering a form is a game that still offers an email
    login to anybody who types the address, and "we took the link away" is not
    what the rule says.
    """
    client = _portal_client(env)
    assert client.post("/login", json={"username": "a", "password": "b"}).status_code == 404
    assert client.post("/register", json={"username": "a", "email": "a@b.co",
                                          "password": "password123"}).status_code == 404
    assert client.get("/logout").status_code == 404

    # And all three are perfectly ordinary on cgovind.com's own site.
    plain = env.app.test_client()
    assert plain.post("/login", json={"username": "a", "password": "b"}).status_code == 401
    assert plain.get("/logout").status_code == 302


def test_no_page_in_the_portal_build_carries_a_password_field(env):
    """The sweep, because the rule is about the game rather than about one page.

    A reviewer reads what is on screen. `type="password"` is the shape of the
    thing they are looking for, and it may not be anywhere - including on a page
    nobody thought of as a login page.
    """
    client = _portal_client(env)
    for path in ("/", "/login", "/lobbies", "/leaderboard", "/solo/sunrise",
                 "/privacy", "/track/sunrise"):
        html = client.get(path).get_data(as_text=True)
        assert 'type="password"' not in html, path
        assert "Forgot your password" not in html, path
        assert 'href="/logout"' not in html, path


def test_a_guest_can_still_pick_a_name(env):
    """Typing a name is not a login and no rule touches it.

    CrazyGames forbid Facebook, Google and email auth; a display name to race
    under is neither, and taking it away would cost the portal build the whole
    of multiplayer for anybody not signed in to CrazyGames.
    """
    client = _portal_client(env)
    assert "Play as guest" in client.get("/login").get_data(as_text=True)
    assert client.post("/guest", json={"name": "Rosa"}).status_code == 200
    with client.session_transaction() as s:
        assert s["guest_name"] == "Rosa"


def test_the_sign_in_button_is_not_the_primary_call_to_action(env):
    """Their rule for a login offered to guests, and it is about weight.

    "It shouldn't be the primary call-to-action and must not prevent gameplay
    access" - so the page also carries the guest form and a way to drive with no
    name at all, and neither the nav nor anything else blocks the way to /solo.
    """
    client = _portal_client(env)
    html = client.get("/login").get_data(as_text=True)
    assert "Play as guest" in html
    assert "drive alone with no name at all" in html
    assert client.get("/solo/sunrise").status_code == 200


# ---------------------------------------------------------------------------
# The token
# ---------------------------------------------------------------------------

def _keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        # PKCS#1, which is the shape CrazyGames publish - `BEGIN RSA PUBLIC KEY`
        # rather than `BEGIN PUBLIC KEY`. Which of the two a given PyJWT accepts
        # has moved between releases, which is why `portal.py` loads the key
        # itself, and why this test uses their shape rather than the easy one.
        format=serialization.PublicFormat.PKCS1,
    ).decode()
    return key, pem


def _token(key, **claims):
    import jwt
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture()
def signed(env, monkeypatch):
    """A key pair standing in for CrazyGames', with the fetch stubbed out."""
    pytest.importorskip("jwt")
    pytest.importorskip("cryptography")
    import portal
    key, pem = _keypair()
    monkeypatch.setattr(portal, "_key", {"pem": pem, "fetched_at": 9e18})
    return key


def test_a_genuine_token_is_accepted(env, signed):
    import portal
    claims = portal.verify_token(_token(signed, userId="u-1", username="Nick"))
    assert claims["userId"] == "u-1"
    assert claims["username"] == "Nick"


def test_a_token_signed_by_somebody_else_is_refused(env, signed):
    """The whole point of verifying rather than decoding.

    A client that read its own token could claim to be anybody; so could anybody
    who posted one to `/api/portal/auth`. This is the check that makes the
    userId mean something.
    """
    import portal
    other, _ = _keypair()
    assert portal.verify_token(_token(other, userId="u-1")) is None


def test_a_tampered_token_is_refused(env, signed):
    import portal
    good = _token(signed, userId="u-1", username="Nick")
    head, body, sig = good.split(".")
    assert portal.verify_token("%s.%s.%s" % (head, body, sig[:-4] + "AAAA")) is None


def test_an_expired_token_is_refused(env, signed):
    import portal
    assert portal.verify_token(_token(signed, userId="u-1", exp=1)) is None


def test_a_token_with_no_user_is_refused(env, signed):
    import portal
    assert portal.verify_token(_token(signed, username="Nick")) is None
    assert portal.verify_token(None) is None
    assert portal.verify_token("not-a-token") is None


def test_a_token_for_another_game_is_refused_once_the_id_is_known(env, signed, monkeypatch):
    """`CRAZYGAMES_GAME_ID` is what stops any CrazyGames token working here.

    Unset - which is the state before submission - a token is still checked
    against their signature, so the worst case is a player from another game of
    theirs getting an account here. Set, it has to be a token minted for Drive.
    """
    import portal
    monkeypatch.setattr(portal, "GAME_ID", "drive-123")
    assert portal.verify_token(_token(signed, userId="u-1", gameId="other")) is None
    assert portal.verify_token(_token(signed, userId="u-1", gameId="drive-123"))


def test_their_key_endpoint_being_down_does_not_sign_anybody_in(env, monkeypatch):
    import portal
    monkeypatch.setattr(portal, "_key", {"pem": None, "fetched_at": 0.0})
    monkeypatch.setattr(portal, "_public_key", lambda: None)
    assert portal.verify_token("anything.at.all") is None


# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------

def _auth(client, key, **claims):
    return client.post("/api/portal/auth", json={"token": _token(key, **claims)})


def test_signing_in_makes_an_account_and_keeps_it(env, signed):
    """Auto-registration, which is the requirement: nobody types anything.

    And the second call is the same account, not a second one - the link table
    is keyed on their userId, which is the identifier CrazyGames say to use
    because a username can change.
    """
    client = _portal_client(env)
    r = _auth(client, signed, userId="u-1", username="Nick")
    assert r.get_json() == {"ok": True, "name": "Nick", "loggedIn": True}

    with env.app.app_context():
        assert env.User.query.count() == 1
        user = env.User.query.first()
        assert user.username.startswith("cg-")
        assert user.display == "Nick"
        # No password, so `/login` could not accept this account even if the
        # route existed - which it does not in here.
        assert user.password_hash is None
        assert user.check_password("") is False

    _auth(client, signed, userId="u-1", username="Nick")
    with env.app.app_context():
        assert env.User.query.count() == 1


def test_a_renamed_player_is_renamed_here(env, signed):
    """Their requirement, and the reason the userId is the key and not the name."""
    client = _portal_client(env)
    _auth(client, signed, userId="u-1", username="Nick")
    _auth(client, signed, userId="u-1", username="Dominique")
    with env.app.app_context():
        assert env.User.query.count() == 1
        assert env.User.query.first().display == "Dominique"


def test_a_portal_name_cannot_take_an_existing_one(env, signed):
    """The impersonation the display-name constraint exists to stop.

    A portal is the first place names arrive that nobody on this site vetted, so
    a CrazyGames player called "chinmay" must not end up as a second row reading
    "chinmay" on the same leaderboard as the first.
    """
    with env.app.app_context():
        u = env.User(username="chinmay", email="c@example.com")
        u.set_password("password123")
        env.db.session.add(u)
        env.db.session.commit()

    client = _portal_client(env)
    r = _auth(client, signed, userId="u-1", username="chinmay")
    assert r.get_json()["name"] != "chinmay"
    assert r.get_json()["name"].startswith("chinmay")


def test_a_portal_username_is_never_a_name_somebody_chose(env, signed):
    """It is a hash, and it is permanent, which is why.

    A username here is the login and the address of a public profile and can
    never be changed. Minting one out of a CrazyGames name would hand somebody a
    permanent public address they did not ask for, out of a namespace real
    accounts are named from.
    """
    client = _portal_client(env)
    _auth(client, signed, userId="u-1", username="Nick")
    with env.app.app_context():
        name = env.User.query.first().username
    assert name.startswith("cg-") and len(name) == 15
    assert "nick" not in name.lower()

    # Same player, same username, for ever - it is derived from their id.
    import portal
    assert portal._portal_username("crazygames", "u-1") == name


def test_a_bad_token_leaves_you_a_guest_rather_than_an_error(env, signed):
    """Nothing here may cost somebody a lap.

    An expired token, a clock a minute out, their key endpoint having a bad
    morning: all of it resolves itself on the next load, and none of it is worth
    a screen. The answer is the same shape either way so the page has one branch.
    """
    client = _portal_client(env)
    other, _ = _keypair()
    r = _auth(client, other, userId="u-1", username="Nick")
    assert r.status_code == 200
    assert r.get_json() == {"ok": False, "name": "Guest", "loggedIn": False}
    with env.app.app_context():
        assert env.User.query.count() == 0


def test_the_auth_endpoint_does_not_exist_outside_the_portal(env, signed):
    """It is the portal build's login, so on cgovind.com it is not a thing.

    Left open it would be a way to make an account on this site with no email
    and no password, from anywhere, which is a stranger shape than it needs to be.
    """
    client = env.app.test_client()
    assert _auth(client, signed, userId="u-1").status_code == 404


def test_a_portal_player_is_an_ordinary_account_everywhere_else(env, signed):
    """One board, unmarked. A lap is a lap.

    They are a row in the shared `users` table, so Ticket to Ride and King of
    Tokyo would take them too, and their profile page here works like anybody's.
    """
    client = _portal_client(env)
    _auth(client, signed, userId="u-1", username="Nick")
    with env.app.app_context():
        user = env.User.query.first()
        username = user.username
    assert client.get("/account").status_code == 200
    assert "Nick" in env.app.test_client().get("/account/" + username).get_data(as_text=True)


def test_the_link_survives_the_account_being_deleted(env, signed):
    """A dead link would make the player permanently unable to sign in."""
    client = _portal_client(env)
    _auth(client, signed, userId="u-1", username="Nick")
    with env.app.app_context():
        env.db.session.delete(env.User.query.first())
        env.db.session.commit()
    r = _auth(env.app.test_client(), signed, userId="u-1", username="Nick")
    assert r.status_code == 404  # a fresh client is not in the portal build yet

    client2 = _portal_client(env)
    assert _auth(client2, signed, userId="u-1", username="Nick").get_json()["ok"]
    with env.app.app_context():
        assert env.User.query.count() == 1


def test_a_name_that_is_not_printable_is_cleaned_rather_than_refused(env, signed):
    """The guest form rejects; a portal name has nobody to tell.

    Refusing would mean an account with no name at all, so the same rule is
    applied by removal - and `app.clean_display_name` is the one rule, handed to
    `portal.py` rather than copied into it.
    """
    client = _portal_client(env)
    r = _auth(client, signed, userId="u-1", username="<script>Nick</script>")
    assert "<" not in r.get_json()["name"] and ">" not in r.get_json()["name"]
    assert "Nick" in r.get_json()["name"]


def test_a_cross_site_post_cannot_sign_this_browser_in(env, signed):
    """Login CSRF, which the portal build is the only part of Drive exposed to.

    The session cookie is `SameSite=None` in production - it has to be, or a
    framed player has no session at all - so without this check a form on any
    site could post a token of the attacker's own and log a stranger's browser
    into the attacker's account, quietly collecting the laps they then drove.
    """
    client = _portal_client(env)
    r = client.post("/api/portal/auth",
                    json={"token": _token(signed, userId="u-1", username="Nick")},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    with env.app.app_context():
        assert env.User.query.count() == 0

    # The page's own fetch is same-origin and is fine.
    r = client.post("/api/portal/auth",
                    json={"token": _token(signed, userId="u-1", username="Nick")},
                    headers={"Origin": "http://localhost"})
    assert r.status_code == 200 and r.get_json()["ok"]


# ---------------------------------------------------------------------------
# The fallback, for a frame that arrived without the parameter
# ---------------------------------------------------------------------------

def test_a_crazygames_frame_is_the_portal_build_even_without_the_parameter(env):
    """The expensive failure, and the one nobody would notice in testing.

    The parameter is on the URL submitted to CrazyGames, but what they actually
    frame is not entirely ours to decide - a QA preview, a share link, an embed
    built from the bare domain. Without the flag that frame gets the cgovind.com
    build, login form and all, which is the one thing their checklist refuses a
    game for.
    """
    client = env.app.test_client()
    html = client.get("/login", headers={
        "Sec-Fetch-Dest": "iframe",
        "Referer": "https://www.crazygames.com/game/drive",
    }).get_data(as_text=True)
    assert 'type="password"' not in html
    assert "Sign in with CrazyGames" in html


def test_the_fallback_takes_the_language_domains_too(env):
    """It reads the sitelock list, so anywhere allowed to frame us is a portal."""
    for ref in ("https://de.crazygames.com/g", "https://www.crazygames.fr/g",
                "https://games.crazygames.com/g", "https://crazygames.com/g"):
        client = env.app.test_client()
        client.get("/", headers={"Sec-Fetch-Dest": "iframe", "Referer": ref})
        with client.session_transaction() as s:
            assert s.get("portal") == "crazygames", ref


def test_somebody_elses_frame_is_not_a_portal(env):
    """A lookalike domain must not reach it, and an ordinary embed must not either.

    `crazygames.evil.example` is the one the obvious regex over the string
    "crazygames." would have let through. Nothing terrible follows from a false
    positive - the flag can only take login UI away, and signing in still needs
    a token CrazyGames signed - but a site that embeds Drive should get Drive.
    """
    for ref in ("https://crazygames.evil.example/g", "https://evil-crazygames.com/g",
                "https://itch.io/g", ""):
        client = env.app.test_client()
        client.get("/", headers={"Sec-Fetch-Dest": "iframe", "Referer": ref})
        with client.session_transaction() as s:
            assert "portal" not in s, ref


def test_an_ordinary_navigation_from_crazygames_is_not_a_frame(env):
    """Somebody clicking a link to Drive *from* CrazyGames is a visitor here.

    `Sec-Fetch-Dest` is `document` for that, not `iframe`, and they should get
    the real site with a real login - they left the portal to come here.
    """
    client = env.app.test_client()
    client.get("/", headers={"Sec-Fetch-Dest": "document",
                             "Referer": "https://www.crazygames.com/game/drive"})
    with client.session_transaction() as s:
        assert "portal" not in s
