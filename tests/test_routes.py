"""The pages themselves, driven through the real routes.

Grouped the way the site is: what anyone can see, what only you can change, and
how you get back in when you cannot log in at all. The last group is the one
worth reading - it is the only part of this feature a stranger can reach without
a password, so nearly all of its tests are about what it refuses to do.
"""

import io

import pytest
from PIL import Image

from accounts.models import User, UserProfile
from urllib.parse import unquote

from conftest import link_from_log


def png(colour=(20, 90, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), colour).save(buf, format="PNG")
    return buf.getvalue()


def body(resp):
    return resp.data.decode()


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def test_a_profile_shows_the_person_and_all_four_games(client, make_user):
    make_user("chinmay")
    page = body(client.get("/accounts/chinmay"))

    assert "chinmay" in page
    assert "@chinmay" in page
    for game in ("Ticket to Ride", "Egyptian Rat Screw", "King of Tokyo", "Drive"):
        assert game in page, "%s has no panel" % game


def test_a_game_nobody_has_played_still_gets_its_tab(client, make_user):
    """A tab that vanishes when it is empty is a tab you go looking for."""
    make_user("newcomer")
    page = body(client.get("/accounts/newcomer"))
    assert page.count('data-panel=') == 4
    assert "not played yet" in page


def test_the_joined_date_is_written_the_way_a_person_would_say_it(client, make_user, db):
    from datetime import datetime
    uid = make_user("dated")
    db.session.get(User, uid).created_at = datetime(2024, 9, 22, 15, 0)
    db.session.commit()
    assert "joined on 9/22/2024" in body(client.get("/accounts/dated"))


def test_a_profile_has_one_spelling(client, make_user):
    """So a link to somebody is one link, however it was typed."""
    make_user("Chinmay")
    resp = client.get("/accounts/CHINMAY")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/accounts/Chinmay")


def test_a_profile_that_is_not_there_is_a_404(client):
    assert client.get("/accounts/nobody-at-all").status_code == 404


def test_the_tab_can_be_named_in_the_url(client, make_user):
    make_user("tabbed")
    page = body(client.get("/accounts/tabbed?game=kot"))
    assert 'data-panel="kot"' in page
    # The chosen panel is the one that is not hidden.
    assert 'data-panel="kot"\n         >' in page or 'data-panel="kot"' in page
    assert page.index('data-panel="kot"') > 0
    assert 'class="tab on" style="--accent: #5c2678"' in page


def test_a_nonsense_tab_falls_back_rather_than_erroring(client, make_user):
    make_user("tabbed")
    assert client.get("/accounts/tabbed?game=chess").status_code == 200


def test_a_recent_result_says_what_time_of_day_it_happened(client, make_user, db):
    """A date on its own puts two games from the same evening on the same row
    twice, and "when did I actually set that" is what this list is read for.

    Served in UTC, which is what the database holds and what is right before
    any script runs; the script at the foot of the profile rewrites it into the
    reader's own timezone. The `<time datetime>` is what it rewrites from, so
    both halves are pinned here.
    """
    from sqlalchemy import text
    uid = make_user("driver")
    # Drive's own tables are not in this app's metadata - `gamestats` reads the
    # games with raw SQL for exactly that reason - so the row goes in the same
    # way it is read back out.
    db.session.execute(text(
        "CREATE TABLE drive_times (user_id INT, track TEXT, time_ms INT,"
        " medal TEXT, updated_at TEXT)"))
    db.session.execute(text(
        "INSERT INTO drive_times VALUES (:u, 'sunrise', 21480, 'gold',"
        " '2024-03-04T14:23:05')"), {"u": uid})
    db.session.commit()

    page = body(client.get("/accounts/driver?game=drive"))
    assert "3/4/24 \u00b7 14:23:05" in page, "the date, and the clock time it happened at"
    assert 'datetime="2024-03-04T14:23:05Z"' in page, "which the script rewrites from"


def test_the_cog_is_only_on_your_own_profile(client, make_user, logged_in):
    make_user("someone-else")
    assert "Account settings" not in body(client.get("/accounts/someone-else"))

    logged_in("me-myself")
    assert "Account settings" in body(client.get("/accounts/me-myself"))
    assert "Account settings" not in body(client.get("/accounts/someone-else"))


def test_the_directory_lists_everybody_and_finds_them_by_either_name(client, make_user, db):
    make_user("chinmay")
    uid = make_user("fishy")
    db.session.add(UserProfile(user_id=uid, display_name="Krish M",
                               display_name_lc="krish m"))
    db.session.commit()

    page = body(client.get("/accounts/"))
    assert "chinmay" in page and "Krish M" in page

    assert "Krish M" in body(client.get("/accounts/?q=krish"))
    assert "chinmay" not in body(client.get("/accounts/?q=krish"))
    # Found by the permanent username as well as the chosen one.
    assert "Krish M" in body(client.get("/accounts/?q=fishy"))
    assert "Nobody here is called" in body(client.get("/accounts/?q=zzzz"))


def test_an_account_a_game_portal_made_is_not_in_the_directory(client, make_user, db):
    """Somebody who arrived at Drive through CrazyGames is a real account here -
    same table, same leaderboard, and their profile page works - but they did
    not come to cgovind.com and did not choose a name on it. This list is the
    people you might go and play with; if Drive does well on a portal, an
    unfiltered one is a page of `cg-9f3a1c2b` with the handful of people this
    site is actually for somewhere underneath.

    The table belongs to Drive, so this is raw SQL behind a `table_exists`
    check - a box without Drive installed has to render the directory, not 500.
    """
    from sqlalchemy import text
    make_user("chinmay")
    uid = make_user("cg-9f3a1c2b")
    db.session.execute(text(
        "CREATE TABLE IF NOT EXISTS drive_portal_users ("
        "portal TEXT, portal_user_id TEXT, user_id INTEGER)"))
    db.session.execute(text(
        "INSERT INTO drive_portal_users (portal, portal_user_id, user_id) "
        "VALUES ('crazygames', 'u-1', :uid)"), {"uid": uid})
    db.session.commit()

    page = body(client.get("/accounts/"))
    assert "chinmay" in page
    assert "cg-9f3a1c2b" not in page
    # Off the roll call, not off the site: the profile is still a profile,
    # because a leaderboard row has to link somewhere.
    assert client.get("/accounts/cg-9f3a1c2b").status_code == 200


def test_the_directory_survives_drive_not_being_installed(client, make_user, db):
    """No `drive_portal_users` table is an ordinary state, not an error - the
    same reason every read in `gamestats.py` is guarded that way."""
    make_user("chinmay")
    assert "chinmay" in body(client.get("/accounts/"))


def test_bots_are_not_people(client, make_user, db):
    """They have accounts because the games needed somewhere to hang a rating."""
    make_user("chinmay")
    uid = make_user("bot:shitter_bot")
    db.session.get(User, uid).is_bot = True
    db.session.commit()
    assert "bot:shitter_bot" not in body(client.get("/accounts/"))


def test_the_accounts_pages_beat_the_static_catch_all(client, make_user):
    """`app.py` serves the whole site through a `/<path:path>` rule. Werkzeug
    sorts by specificity so these win, but it is worth pinning: if it ever
    stopped being true, every accounts page would 404 into the Mario game."""
    make_user("chinmay")
    for path in ("/accounts/", "/accounts/chinmay", "/accounts/login",
                 "/accounts/forgot", "/accounts/api/profile/chinmay"):
        assert client.get(path).status_code in (200, 301, 302), path
    # And the static site still works.
    assert client.get("/").status_code == 200


def test_the_json_view_of_a_profile(client, make_user, db):
    uid = make_user("chinmay")
    db.session.add(UserProfile(user_id=uid, display_name="Chinny G",
                               display_name_lc="chinny g", country="us",
                               us_state="CA", flag_pref="state"))
    db.session.commit()

    data = client.get("/accounts/api/profile/chinmay").get_json()
    assert data["display"] == "Chinny G"
    assert data["flag"] == "/assets/flags/us/ca.png"
    assert data["flag_alt"] == "California"
    assert client.get("/accounts/api/profile/nobody").status_code == 404


# ---------------------------------------------------------------------------
# Yours
# ---------------------------------------------------------------------------

def test_settings_needs_a_login_and_comes_back_to_itself(client):
    resp = client.get("/accounts/settings")
    assert resp.status_code == 302
    assert "/accounts/login" in resp.headers["Location"]
    assert "next=" in resp.headers["Location"]


def test_saving_a_profile_sets_the_name_the_flag_and_the_place(client, logged_in, db):
    uid = logged_in("driver")
    client.post("/accounts/settings/profile",
                data={"display_name": "Chinny G", "country": "us",
                      "us_state": "CA", "flag_pref": "state"})

    profile = db.session.get(UserProfile, uid)
    assert profile.display_name == "Chinny G"
    assert profile.display_name_lc == "chinny g"
    assert profile.flag_path == "/assets/flags/us/ca.png"
    assert db.session.get(User, uid).display == "Chinny G"

    page = body(client.get("/accounts/driver"))
    assert "Chinny G" in page
    assert "California, United States" in page
    assert "/assets/flags/us/ca.png" in page


def test_a_state_is_dropped_when_you_are_not_in_the_us(client, logged_in, db):
    """Otherwise moving abroad leaves a state behind that a later `flag_pref`
    could fly over the wrong country."""
    uid = logged_in("mover")
    client.post("/accounts/settings/profile",
                data={"country": "us", "us_state": "CA", "flag_pref": "state"})
    client.post("/accounts/settings/profile",
                data={"country": "gb", "us_state": "CA", "flag_pref": "state"})

    profile = db.session.get(UserProfile, uid)
    assert profile.us_state is None
    assert profile.flag_pref == "country"
    assert profile.flag_path == "/assets/flags/country/gb.svg"


def test_two_people_cannot_have_the_same_display_name(client, logged_in, make_user, db):
    """Which is the entire reason it is enforced: two identical names on one
    leaderboard is not a cosmetic problem."""
    other = make_user("other")
    db.session.add(UserProfile(user_id=other, display_name="Chinny G",
                               display_name_lc="chinny g"))
    db.session.commit()

    logged_in("me")
    resp = client.post("/accounts/settings/profile", data={"display_name": "CHINNY g"})
    assert "already using that display name" in unquote(resp.headers["Location"])


def test_a_display_name_cannot_be_somebody_elses_username(client, logged_in, make_user):
    """The impersonation the uniqueness rule is actually about: a username is
    what people know somebody by."""
    make_user("chinmay")
    logged_in("impostor")
    resp = client.post("/accounts/settings/profile", data={"display_name": "Chinmay"})
    assert "belongs to another account" in unquote(resp.headers["Location"])


def test_your_own_display_name_is_not_a_clash_with_itself(client, logged_in, db):
    uid = logged_in("steady")
    client.post("/accounts/settings/profile", data={"display_name": "Steady Eddie"})
    resp = client.post("/accounts/settings/profile",
                       data={"display_name": "Steady Eddie", "country": "ie"})
    assert "err=" not in resp.headers["Location"]
    assert db.session.get(UserProfile, uid).country == "ie"


@pytest.mark.parametrize("cleared", ["", "   "])
def test_clearing_the_display_name_goes_back_to_the_username(client, logged_in, db, cleared):
    """Whitespace counts as clearing it. Somebody selecting the box and hitting
    space means "I do not want this any more", not "call me a space"."""
    uid = logged_in("plain")
    client.post("/accounts/settings/profile", data={"display_name": "Fancy Name"})
    client.post("/accounts/settings/profile", data={"display_name": cleared})

    assert db.session.get(UserProfile, uid).display_name is None
    assert db.session.get(User, uid).display == "plain"


@pytest.mark.parametrize("bad", ["x", "!!!", "a" * 31, "settings"])
def test_a_display_name_has_to_be_a_name(client, logged_in, bad):
    logged_in("namer")
    resp = client.post("/accounts/settings/profile", data={"display_name": bad})
    assert "err=" in resp.headers["Location"], bad


def test_a_country_we_have_no_flag_for_is_refused(client, logged_in):
    logged_in("nowhere")
    resp = client.post("/accounts/settings/profile", data={"country": "zz"})
    assert "isn't a country" in unquote(resp.headers["Location"])


def upload(client, blob, name="me.png"):
    """Post a picture the way the crop dialog does: its own request, JSON back."""
    return client.post("/accounts/settings/avatar",
                       data={"avatar": (io.BytesIO(blob), name)},
                       content_type="multipart/form-data")


def test_uploading_and_removing_a_picture(client, logged_in, db):
    """The picture saves on its own, because cropping ends in a decision of its
    own - being told afterwards that it is not saved until you press a second
    button further down the page would be the wrong answer."""
    uid = logged_in("snapper")
    resp = upload(client, png())
    assert resp.status_code == 200 and resp.get_json()["ok"]

    stored = db.session.get(UserProfile, uid).avatar
    assert stored.startswith("%d-" % uid) and stored.endswith(".webp")
    # The reply carries the new URL, since the page swaps the picture in place.
    assert resp.get_json()["url"].endswith(stored)

    served = client.get("/accounts/avatar/" + stored)
    assert served.status_code == 200
    assert "immutable" in served.headers["Cache-Control"]
    assert served.data[:4] == b"RIFF"                  # a WebP, not the PNG sent

    gone = client.post("/accounts/settings/avatar/remove")
    assert gone.get_json()["ok"]
    # ...and what to draw instead, since the initial has to go back without a reload.
    assert gone.get_json()["initial"] == "S"
    assert gone.get_json()["colour"].startswith("#")
    assert db.session.get(UserProfile, uid).avatar is None
    assert client.get("/accounts/avatar/" + stored).status_code == 404


def test_replacing_a_picture_takes_the_old_one_off_the_disk(client, logged_in, db):
    uid = logged_in("swapper")
    upload(client, png())
    first = db.session.get(UserProfile, uid).avatar
    upload(client, png(colour=(220, 40, 40)))
    second = db.session.get(UserProfile, uid).avatar

    assert second != first
    assert client.get("/accounts/avatar/" + first).status_code == 404
    assert client.get("/accounts/avatar/" + second).status_code == 200


def test_a_file_that_is_not_an_image_is_turned_away(client, logged_in, db):
    """The browser crops before sending, so what arrives is normally a canvas
    export - which is exactly why the server cannot take that on trust."""
    uid = logged_in("chancer")
    resp = upload(client, b"<?php echo 1; ?>", "shell.php.png")
    assert resp.status_code == 400
    assert not resp.get_json()["ok"]
    assert db.session.get(UserProfile, uid) is None or \
        db.session.get(UserProfile, uid).avatar is None


def test_a_picture_request_with_no_picture_says_so(client, logged_in):
    logged_in("empty")
    resp = client.post("/accounts/settings/avatar", data={},
                       content_type="multipart/form-data")
    assert resp.status_code == 400
    assert not resp.get_json()["ok"]


def test_a_logged_out_picture_request_gets_a_fact_not_a_login_page(client):
    """It is called by script, and a 302 to HTML would be parsed as success."""
    resp = client.post("/accounts/settings/avatar", data={},
                       content_type="multipart/form-data")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_a_failed_save_changes_nothing_at_all(client, logged_in, db):
    """The profile form is one save, so a rejected field must not leave the
    earlier ones half-applied - and the display name is assigned before the
    country is checked."""
    uid = logged_in("careful")
    client.post("/accounts/settings/profile",
                data={"display_name": "Careful", "country": "ie"})
    client.post("/accounts/settings/profile",
                data={"display_name": "Renamed", "country": "zz"})

    profile = db.session.get(UserProfile, uid)
    assert profile.display_name == "Careful"
    assert profile.country == "ie"


@pytest.mark.parametrize("path", [
    "/accounts/avatar/../../app.py",
    "/accounts/avatar/7-9f3a1c2b.png",
    "/accounts/avatar/x-9f3a1c2b.webp",
])
def test_the_avatar_route_only_serves_names_it_could_have_written(client, path):
    assert client.get(path).status_code == 404


# --- password and email -----------------------------------------------------

def test_changing_a_password_needs_the_old_one(client, logged_in, db, capsys):
    uid = logged_in("changer")

    resp = client.post("/accounts/settings/password",
                       data={"current": "wrong", "new": "brandnew123",
                             "confirm": "brandnew123"})
    assert "isn't your current password" in unquote(resp.headers["Location"])
    assert db.session.get(User, uid).check_password("hunter2hunter2")

    resp = client.post("/accounts/settings/password",
                       data={"current": "hunter2hunter2", "new": "brandnew123",
                             "confirm": "brandnew123"})
    assert "ok=" in resp.headers["Location"]
    assert db.session.get(User, uid).check_password("brandnew123")
    # And the account is told, which is the only warning a takeover would give.
    assert "password was changed" in capsys.readouterr().err


@pytest.mark.parametrize("new, confirm, why", [
    ("short", "short", "at least 8"),
    ("longenough1", "longenough2", "don't match"),
])
def test_a_new_password_has_to_be_one(client, logged_in, new, confirm, why):
    logged_in("picky")
    resp = client.post("/accounts/settings/password",
                       data={"current": "hunter2hunter2", "new": new, "confirm": confirm})
    assert "err=" in resp.headers["Location"]


def test_an_email_change_waits_for_the_new_address(client, logged_in, db, capsys):
    """Nothing moves on the POST. A typo has to be recoverable, and the only
    thing that proves the address was typed right is the address answering."""
    uid = logged_in("mover")
    resp = client.post("/accounts/settings/email",
                       data={"current": "hunter2hunter2", "email": "new@example.com"})
    assert "ok=" in resp.headers["Location"]
    assert db.session.get(User, uid).email == "mover@example.com"      # unchanged

    link = link_from_log(capsys.readouterr(), "confirm-email")
    assert client.get(link.split("cgovind.test")[-1]).status_code == 200
    assert db.session.get(User, uid).email == "new@example.com"

    # The old address is told, because a takeover changes the address first.
    out = capsys.readouterr().err
    assert "email address was changed" in out
    assert "mover@example.com" in out


def test_an_email_change_needs_the_password_and_a_free_address(client, logged_in, make_user, db):
    uid = logged_in("asker")
    make_user("taken", email="taken@example.com")

    for data in ({"current": "nope", "email": "fine@example.com"},
                 {"current": "hunter2hunter2", "email": "not-an-email"},
                 {"current": "hunter2hunter2", "email": "taken@example.com"},
                 {"current": "hunter2hunter2", "email": "asker@example.com"}):
        resp = client.post("/accounts/settings/email", data=data)
        assert "err=" in resp.headers["Location"], data
    assert db.session.get(User, uid).email == "asker@example.com"


def test_a_confirmation_link_cannot_be_used_twice(client, logged_in, capsys):
    logged_in("twice")
    client.post("/accounts/settings/email",
                data={"current": "hunter2hunter2", "email": "twice2@example.com"})
    link = link_from_log(capsys.readouterr(), "confirm-email").split("cgovind.test")[-1]

    assert client.get(link).status_code == 200
    assert client.get(link).status_code == 400


def test_a_confirmation_link_loses_to_whoever_took_the_address_first(client, logged_in,
                                                                    make_user, capsys):
    """A day is a long time for an address to stay free."""
    logged_in("slowcoach")
    client.post("/accounts/settings/email",
                data={"current": "hunter2hunter2", "email": "contested@example.com"})
    link = link_from_log(capsys.readouterr(), "confirm-email").split("cgovind.test")[-1]

    make_user("quickdraw", email="contested@example.com")
    assert client.get(link).status_code == 409


# ---------------------------------------------------------------------------
# Getting back in
# ---------------------------------------------------------------------------

def test_forgot_says_the_same_thing_whoever_asks(client, make_user):
    """Otherwise the box is a way of asking which addresses have accounts."""
    make_user("real", email="real@example.com")
    known = body(client.post("/accounts/forgot", data={"username": "real@example.com"}))
    unknown = body(client.post("/accounts/forgot", data={"username": "ghost@example.com"}))

    assert "Check your email" in known and "Check your email" in unknown
    # The only difference is the address echoed back, which the asker typed.
    assert known.replace("real@example.com", "X") == unknown.replace("ghost@example.com", "X")


def test_no_mail_goes_to_an_address_with_no_account(client, capsys):
    client.post("/accounts/forgot", data={"username": "ghost@example.com"})
    assert "Reset your cgovind.com password" not in capsys.readouterr().err


def test_a_reset_link_sets_a_password_and_logs_you_in(client, make_user, db, capsys):
    uid = make_user("forgetful", email="forgetful@example.com")
    client.post("/accounts/forgot", data={"username": "forgetful"})
    link = link_from_log(capsys.readouterr(), "reset").split("cgovind.test")[-1]

    assert client.get(link).status_code == 200
    token = link.split("t=")[1]
    resp = client.post("/accounts/reset",
                       data={"t": token, "new": "a whole new one",
                             "confirm": "a whole new one"})
    assert resp.status_code == 200
    assert db.session.get(User, uid).check_password("a whole new one")
    # Straight in, rather than back to a login form.
    assert client.get("/accounts/settings").status_code == 200


def test_a_reset_link_dies_when_it_is_used(client, make_user, capsys):
    make_user("once", email="once@example.com")
    client.post("/accounts/forgot", data={"username": "once"})
    link = link_from_log(capsys.readouterr(), "reset").split("cgovind.test")[-1]
    token = link.split("t=")[1]

    client.post("/accounts/reset", data={"t": token, "new": "first one here",
                                         "confirm": "first one here"})
    assert client.get(link).status_code == 400
    resp = client.post("/accounts/reset", data={"t": token, "new": "second attempt",
                                                "confirm": "second attempt"})
    assert resp.status_code == 400


def test_a_reset_link_that_was_never_ours_is_refused(client):
    assert client.get("/accounts/reset?t=not-a-token").status_code == 400
    assert client.get("/accounts/confirm-email?t=not-a-token").status_code == 400


def test_a_bot_account_is_not_sent_mail(client, make_user, db, capsys):
    uid = make_user("bot:slapper", email="slapper@bots.local")
    db.session.get(User, uid).is_bot = True
    db.session.commit()
    client.post("/accounts/forgot", data={"username": "bot:slapper"})
    assert "Reset your cgovind.com password" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Logging in and signing up
# ---------------------------------------------------------------------------

def test_logging_in_and_out(client, make_user):
    make_user("comeandgo")
    assert client.post("/accounts/login",
                       data={"username": "comeandgo", "password": "wrong"}).status_code == 401
    assert client.post("/accounts/login",
                       data={"username": "comeandgo",
                             "password": "hunter2hunter2"}).status_code == 302
    assert client.get("/accounts/settings").status_code == 200
    client.get("/accounts/logout")
    assert client.get("/accounts/settings").status_code == 302


def test_you_can_log_in_with_your_email(client, make_user):
    make_user("emailer", email="emailer@example.com")
    assert client.post("/accounts/login",
                       data={"username": "EMAILER@example.com",
                             "password": "hunter2hunter2"}).status_code == 302


@pytest.mark.parametrize("username, why", [
    ("settings", "reserved - it is a page under /accounts"),
    ("x", "too short"),
    ("9lives", "does not start with a letter"),
    ("has spaces", "not allowed in a username"),
])
def test_registration_refuses_a_username_that_would_not_work(client, username, why):
    resp = client.post("/accounts/register",
                       data={"username": username, "email": "a@example.com",
                             "password": "hunter2hunter2"})
    assert resp.status_code == 400, why


def test_registration_will_not_duplicate_an_account(client, make_user):
    make_user("taken", email="taken@example.com")
    assert client.post("/accounts/register",
                       data={"username": "TAKEN", "email": "other@example.com",
                             "password": "hunter2hunter2"}).status_code == 409
    assert client.post("/accounts/register",
                       data={"username": "fresh", "email": "TAKEN@example.com",
                             "password": "hunter2hunter2"}).status_code == 409


def test_registering_leaves_you_logged_in_at_your_settings(client):
    resp = client.post("/accounts/register",
                       data={"username": "brandnew", "email": "bn@example.com",
                             "password": "hunter2hunter2"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/accounts/settings")
    assert client.get("/accounts/settings").status_code == 200


def test_an_upload_far_too_large_is_refused_before_it_is_read(client, logged_in):
    """nginx allows 20m through, so without a limit here a request could put
    20MB in memory just to be told the picture is over 5MB."""
    logged_in("hefty")
    resp = upload(client, b"x" * (7 * 1024 * 1024), "huge.png")
    assert resp.status_code == 413
    assert "under 5MB" in body(resp)


def test_the_country_dropdown_opens_on_the_united_states(client, logged_in):
    logged_in("picker")
    page = body(client.get("/accounts/settings"))
    options = page.split('id="country"')[1].split("</select>")[0]
    first = options.split('<option value="us"')[0]
    # Nothing above it but the empty choice.
    assert first.count("<option") == 1
    assert 'value=""' in first
    # ...and a rule under it, or the top entry just reads as a sorting bug.
    assert options.index("<option disabled") > options.index('<option value="us"')
    # It is not also down in the alphabet.
    assert options.count('<option value="us"') == 1


def test_the_flag_controls_are_always_in_the_page_so_it_cannot_reflow(client, logged_in):
    """The state picker and the flag choice are rendered for everybody, faded
    rather than absent, and the script only ever changes a class. Rendering
    them conditionally here - or toggling `hidden` there - is what made the
    form jump: choosing the United States used to push everything below the
    country box down by two rows."""
    logged_in("steady")
    page = body(client.get("/accounts/settings"))

    for part in ('id="stateCol"', 'id="flagPrefRow"', 'id="us_state"'):
        assert part in page, part
    # Faded, not hidden: `hidden` takes a box out of the layout.
    assert 'class="field fade" id="stateCol"' in page
    assert 'id="flagPrefRow"' in page and "flagchoice fade" in page
    assert "hidden" not in page.split('id="stateCol"')[0][-120:]


def test_the_flag_choice_names_the_flags(client, logged_in):
    """"USA Flag" and "<state> Flag" - the two pictures on offer, one of which
    is about to be next to your name. The state's own name is filled in by the
    script from whichever state is selected."""
    logged_in("namer")
    page = body(client.get("/accounts/settings"))
    assert "Choose flag" in page
    assert "USA Flag" in page
    assert 'id="stateFlagLabel"' in page
    assert "Displayed Flag:" in page
