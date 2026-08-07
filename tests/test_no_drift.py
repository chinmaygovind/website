"""The copies that are allowed to exist, and what stops them rotting.

Five services share one database and none of them import each other - each owns
its copy of ``User``, and now of ``UserProfile``. That is the convention this
repo already had, and it is the right one for five processes that deploy
separately. What it costs is that a copy can drift, and a drifted copy is worse
than no copy at all: a leaderboard would quietly stop showing flags, or a tier
name would disagree with the game that owns it.

So every deliberate duplication in this feature has a test here that reads the
*other* file and fails when the two stop agreeing. None of these test behaviour;
they test that two files still say the same thing.
"""

import ast
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = ("ers", "kot", "drive", "ttr")


def source(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        pytest.skip("%s is not checked out here" % os.path.join(*parts))
    return open(path).read()


# --- rating tiers -----------------------------------------------------------

def tiers_in(src, class_name):
    """Pull ``elo_tier``'s ladder out of a game's models.py by reading it."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "elo_tier":
                    return _ladder(ast.get_source_segment(src, item))
    raise AssertionError("no %s.elo_tier" % class_name)


def _ladder(text):
    pairs = [(int(n), name) for n, name in
             re.findall(r'>=\s*(\d+):\s*return\s+"([^"]+)"', text)]
    fallback = re.findall(r'^\s*return\s+"([^"]+)"', text, re.M)
    if fallback:
        pairs.append((0, fallback[-1]))
    return pairs


# TTR's ladder is on `User`, not on `TtrStats`: the stats moved into their own
# table but the properties stayed put and proxy through to it, so a template
# that said `user.elo_tier` before the refactor still says it.
@pytest.mark.parametrize("key, path, class_name", [
    ("ttr", ("ttr", "models.py"), "User"),
    ("ers", ("ers", "models.py"), "ErsStats"),
    ("kot", ("kot", "models.py"), "KotStats"),
    ("drive", ("drive", "models.py"), "DriveStats"),
])
def test_tiers_match_the_games(key, path, class_name):
    """A profile says "1108 · Engineer". The number comes from the game's table
    and the word from a copy of the game's ladder, so if the game retunes its
    ladder and this does not follow, the profile calls somebody something the
    game itself no longer would."""
    from accounts.gamestats import TIERS
    assert tiers_in(source(*path), class_name) == TIERS[key], (
        "%s's tiers have moved - update accounts/gamestats.py TIERS" % key)


# --- Drive's track names ----------------------------------------------------

def test_track_names_match_drive():
    """Copied rather than imported because importing `drive/tracks.py` costs
    1.7 seconds of geometry assembly at boot, in a process whose other job is
    serving static files, to learn nine strings."""
    from accounts.gamestats import DRIVE_TRACKS
    src = source("drive", "tracks.py")
    # `_POOL` is a list of tuples whose first two members are the slug and the
    # display name. Read rather than imported, for the reason above.
    pool = re.search(r"^_POOL = \[(.*?)^\]", src, re.S | re.M)
    assert pool, "could not find _POOL in drive/tracks.py"
    found = dict(re.findall(r'\(\s*"([a-z0-9]+)",\s*"([^"]+)"', pool.group(1)))
    assert found, "could not read the track pool out of drive/tracks.py"
    assert found == DRIVE_TRACKS, (
        "Drive's track pool has changed - update accounts/gamestats.py DRIVE_TRACKS")


# --- reserved usernames -----------------------------------------------------

@pytest.mark.parametrize("game", GAMES[:3])       # TTR validates via its own copy
def test_reserved_names_match_the_accounts_site(game):
    """A username that collides with a page under /accounts would be an account
    whose own profile URL went somewhere else. Registration happens in the
    games, so the games have to know the same list."""
    from accounts.naming import RESERVED
    src = source(game, "app.py")
    block = re.search(r"RESERVED_USERNAMES = \{(.*?)\}", src, re.S)
    assert block, "%s has no RESERVED_USERNAMES" % game
    assert set(re.findall(r'"([^"]+)"', block.group(1))) == RESERVED


# --- the shared profile table ----------------------------------------------

PROFILE_COLUMNS = {
    "user_id", "display_name", "display_name_lc", "avatar",
    "country", "us_state", "flag_pref", "created_at", "updated_at",
}


@pytest.mark.parametrize("game", GAMES)
def test_every_service_maps_the_same_profile_columns(game):
    """One physical table, five mappings. A service that mapped a column the
    others do not have would create it on first boot and the rest would never
    see it; one that is missing a column would read `None` for something that
    is set."""
    src = source(game, "models.py")
    block = re.search(r"class UserProfile\(db\.Model\):(.*?)(?=\n\nclass )", src, re.S)
    assert block, "%s/models.py has no UserProfile" % game
    assert '__tablename__ = "user_profiles"' in block.group(1)
    columns = set(re.findall(r"^\s{4}(\w+) = db\.Column", block.group(1), re.M))
    assert columns == PROFILE_COLUMNS, "%s maps %s" % (game, sorted(columns))


@pytest.mark.parametrize("game", GAMES)
def test_every_service_shows_the_display_name(game):
    """The name on a seat comes from `get_effective_name`, which is the single
    place a display name reaches the games from. If one of them went back to
    reading `username`, that game alone would ignore the name people chose."""
    src = source(game, "app.py")
    block = re.search(r"def get_effective_name\(.*?\n(?=\n\n)", src, re.S)
    assert block, "%s has no get_effective_name" % game
    assert ".display" in block.group(0), game
    assert ".username" not in block.group(0), game


@pytest.mark.parametrize("game", GAMES)
def test_every_login_page_offers_a_way_back_in(game):
    """The whole reason the accounts site has a forgot page is that four login
    screens had nowhere to send somebody who had forgotten their password."""
    src = source(game, "templates", "login.html")
    assert "/accounts/forgot" in src, "%s's login page has no reset link" % game


@pytest.mark.parametrize("game", GAMES)
def test_the_flag_url_does_not_borrow_the_wrong_site(game):
    """`SITE_URL` already means "this service's own address" on the box - drive's
    .env sets it to https://drive.cgovind.com. Reusing that name for the main
    site would point every flag at a host that does not serve them."""
    src = source(game, "app.py")
    assert "MAIN_SITE_URL" in src, game
    assert re.search(r'"site_url":\s*MAIN_SITE_URL', src) \
        or "'site_url': MAIN_SITE_URL" in src, game


@pytest.mark.parametrize("game", GAMES)
def test_every_board_can_reach_a_profile(game):
    """A flag next to a name is the moment somebody wonders who that is. The
    link uses the *username*, which is the permanent one - a display name can
    change and would break every link the moment it did.

    Drive is one step longer on purpose: a name on one of its boards goes to
    its *own* account page, since the question a lap time raises is about that
    driver's other laps. What must not drift is that the step out to the shared
    profile still exists - see the test below.
    """
    src = source(game, "templates", "_player.html")
    target = "/account/" if game == "drive" else "/accounts/"
    assert target + "{{ user.username }}" in src, game
    assert "user.display" in src, game


def test_drives_own_account_page_leads_on_to_the_shared_profile():
    """The one board that does not link straight out has to link out somewhere.

    Drive's boards point at Drive's account page instead, which is right - but
    it makes that page the only remaining route from a Drive leaderboard to the
    profile spanning all four games. By username, for the same reason every
    other link is."""
    src = source("drive", "templates", "account.html")
    assert "{{ site_url }}/accounts/{{ user.username }}" in src


# --- the visit log and the presence row -------------------------------------
#
# `visits.py` is the strongest form of this repo's copy-per-service convention:
# not five files that must agree, but five copies of *one* file. That makes the
# check trivial and total - a byte comparison - and it makes fixing a failure a
# copy rather than a merge. It also means nothing in that file may ever be
# service-specific, which is why it takes its `db` as an argument and reads
# `flask.session` for the rest.

@pytest.mark.parametrize("game", GAMES)
def test_every_service_carries_the_same_visits_module(game):
    assert source(game, "visits.py") == source("visits.py"), (
        "%s/visits.py has drifted from the root copy. It is meant to be the "
        "same file: copy the root one over it rather than merging by hand." % game)


@pytest.mark.parametrize("game", GAMES)
def test_every_service_logs_its_visits_under_its_own_name(game):
    """The one line each copy is *called* with, which is the only difference
    between them - and the string that decides what a profile says somebody is
    playing, so a typo here is a status nobody can read."""
    src = source(game, "app.py")
    assert 'visits.init_app(app, db, "%s")' % game in src, \
        "%s/app.py does not start visit tracking as '%s'" % (game, game)


@pytest.mark.parametrize("game", GAMES)
def test_a_status_can_only_say_what_the_game_offers(game):
    """The status line is drawn on a public profile, so what a browser sends is
    a *key* and never words. Every game looks the key up in its own table and a
    miss is no detail at all; the one exception is Drive's track, which is a
    slug looked up in the track pool. This test is the thing that notices if a
    heartbeat ever starts passing the payload straight through."""
    src = source(game, "app.py")
    body = re.search(r"def api_presence\(\):.*?\n    return jsonify", src, re.S)
    assert body, "%s has no /api/presence handler" % game
    body = body.group(0)
    assert "PRESENCE_WHERE.get(" in body or "PRESENCE_WHERE.get" in body, \
        "%s builds its status without the whitelist" % game
    # The detail handed to `seen` must be the *result* of a lookup, never
    # anything read off the request. `PRESENCE_WHERE.get(where)` is the whole
    # point - `where` is a key and what comes back is ours - so what this bans
    # is the request object reaching the call at all.
    seen_call = re.search(r"visits\.seen\((.*?)\)\n", body, re.S)
    assert seen_call, "%s never records presence" % game
    args = seen_call.group(1)
    for banned in ("request.", "data.get", ".json"):
        assert banned not in args, \
            "%s passes %s straight into the status line" % (game, banned)
