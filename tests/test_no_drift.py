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


def checked_out(service):
    """Whether a service's code is actually here.

    Any Python at its top level, rather than the directory existing: `ttr/` is a
    submodule, and an uninitialised one still leaves a directory behind with an
    untracked `instance/` sitting in it.
    """
    d = os.path.join(ROOT, service)
    return os.path.isdir(d) and any(f.endswith(".py") for f in os.listdir(d))


def source(*parts):
    """A file from another service, read rather than imported.

    A whole service being absent is a legitimate skip - `ttr/` is a submodule
    that is not checked out in CI or in a plain clone, and every job in the
    Action is a sparse checkout of one module. **A file missing from a service
    that *is* here is a failure**, because that is a rename, and a skip reads as
    a pass: this skipped `drive/tracks.py` for the entire life of three tracks
    after the pool became the `drive/tracks/` package, and the profile it guards
    printed `costco` and `mountjoy` at people for all of it.
    """
    path = os.path.join(ROOT, *parts)
    if os.path.exists(path):
        return open(path).read()
    service = parts[0] if len(parts) > 1 else None
    if service and not checked_out(service):
        pytest.skip("%s is not checked out here" % service)
    raise AssertionError(
        "%s is missing, but %s is checked out. If the file moved, move this "
        "test with it - letting it skip would read as a pass."
        % (os.path.join(*parts), service or "the repo root"))


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
    """Copied rather than imported because importing `drive/tracks` builds every
    ribbon in the pool - about 1.7 seconds - in a process whose other job is
    serving static files, to learn sixteen strings.

    **This read `drive/tracks.py`, and that file stopped existing.** The pool
    became one folder per track, `source` skipped a path it could not find, and
    a skip reads as a pass - so this sat green while Spa, the Costco and Mount
    Joy were added and a profile showed all three as their slugs. `source`
    fails on a rename now, and this reads the folders, which are the same thing
    the game itself reads.
    """
    from accounts.gamestats import DRIVE_TRACKS
    if not checked_out("drive"):
        pytest.skip("drive is not checked out here")
    pool = os.path.join(ROOT, "drive", "tracks")
    assert os.path.isdir(pool), (
        "drive is checked out but drive/tracks is not a directory. If the pool "
        "has moved again, move this test with it rather than letting it skip.")
    found = {}
    for folder in sorted(os.listdir(pool)):
        # A track is a folder with a `track.py` in it; everything else in here
        # (builder.py, solver.py, __pycache__) is not a track.
        p = os.path.join(pool, folder, "track.py")
        if not os.path.exists(p):
            continue
        src = open(p).read()
        slug = re.search(r'^slug\s*=\s*"([^"]+)"', src, re.M)
        name = re.search(r'^name\s*=\s*"([^"]+)"', src, re.M)
        assert slug and name, (
            "drive/tracks/%s/track.py declares no %s"
            % (folder, "slug" if not slug else "name"))
        found[slug.group(1)] = name.group(1)
    # Or a regex that matched nothing would agree with an empty copy of the map.
    assert len(found) > 10, (
        "only read %d tracks out of drive/tracks/, which cannot be right - the "
        "declarations have probably changed shape" % len(found))
    assert found == DRIVE_TRACKS, (
        "Drive's track pool and accounts/gamestats.py DRIVE_TRACKS disagree. A "
        "slug missing from the map is printed raw on a profile.\n"
        "  only in drive:    %s\n  only in accounts: %s\n"
        "  spelt differently: %s"
        % (sorted(set(found) - set(DRIVE_TRACKS)),
           sorted(set(DRIVE_TRACKS) - set(found)),
           sorted(s for s in set(found) & set(DRIVE_TRACKS)
                  if found[s] != DRIVE_TRACKS[s])))


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


def test_drive_rejects_the_same_characters_in_a_guest_name_as_a_display_name():
    """Drive's guest names are the one piece of text that took no validation.

    A guest name goes into the same roster an account's display name goes into,
    and that roster is embedded in a `<script>` block - so it needs the same
    character rule. Drive is its own service with its own venv and cannot import
    `accounts/naming.py`, so it carries a copy, which is this repo's convention
    (`visits.py` is the same idea) and which is why this test exists: it reads
    the other file and fails when the two stop agreeing.
    """
    # Through `source`, not `open`, so this skips rather than errors where the
    # module is not checked out. CI gives each job a sparse checkout of its own
    # module, so `drive/` is not there for the `site` suite that owns this file -
    # the same reason the TTR checks in here read as passes on CI. It runs on any
    # machine with the tree, which is where drift actually gets introduced.
    naming_src = source("accounts", "naming.py")
    drive_src = source("drive", "app.py")

    want = re.search(r"_BAD_CHARS = re\.compile\((.+)\)\n", naming_src)
    assert want, "accounts/naming.py no longer defines _BAD_CHARS"
    got = re.search(r"GUEST_BAD_CHARS = re\.compile\((.+)\)\n", drive_src)
    assert got, "drive/app.py no longer defines GUEST_BAD_CHARS"

    # Compare what the two patterns *do*, not how they are spelled - one is
    # written with literal characters and the other with escapes.
    import accounts.naming as naming
    guest_re = re.compile(eval(got.group(1)))
    for ch in ("\x00", "\x1f", "\x7f", "<", ">", "​", "‮", "⁦"):
        assert naming._BAD_CHARS.search(ch), "naming stopped rejecting %r" % ch
        assert guest_re.search(ch), \
            "drive's guest names still allow %r, which naming.py rejects" % ch
    for ch in ("a", " ", "'", "é", "3"):
        assert not guest_re.search(ch), "drive rejects %r, which is a name" % ch


def test_a_display_name_cannot_carry_the_angle_brackets():
    """The XSS that was live: `</script><svg onload=alert(1)>` is exactly 30
    characters, which was exactly the limit. The escaping in each service's
    `script_json` is what actually closes it; this is the half that does not
    depend on anybody remembering to use it."""
    import accounts.naming as naming
    assert naming.check_display_name("</script><svg onload=alert(1)>")
    assert naming.check_display_name("a<b")
    assert naming.check_display_name("a>b")
    assert naming.check_display_name("‮evil") 
    assert naming.check_display_name("Chinmay") is None
    assert naming.check_display_name("José O'Neill") is None


@pytest.mark.parametrize("game", ["drive", "ers", "kot"])
def test_every_roster_is_escaped_before_it_reaches_a_script_block(game):
    """`json.dumps` does not escape `<`, and every roster is embedded in one."""
    src = source(game, "app.py")
    assert "def script_json(" in src, "%s has no script_json helper" % game
    assert "roster_json=script_json(" in src, \
        "%s still builds its roster with a raw json dump" % game


def test_a_portal_avatar_lands_on_a_name_the_site_will_serve():
    """Drive writes profile pictures into `accounts/`'s avatar directory now.

    A player signing in through CrazyGames arrives with a `profilePictureUrl`,
    and `drive/portal.py` fetches it, re-encodes it through Pillow and stores it
    beside every uploaded avatar - so it is *two* services writing files that one
    route serves. `accounts.avatars.is_safe_name` re-checks the shape at serve
    time rather than trusting a column five services can write, which means a
    name of any other shape is stored successfully, recorded successfully, and
    then 404s for ever, with nothing anywhere reporting it.

    So this asserts the two ends agree: the name drive builds is a name accounts
    will serve.
    """
    import accounts.avatars as avatars
    src = source("drive", "portal.py")
    got = re.search(r'name = ("%[ds]-%s\.webp".*)\n', src)
    assert got, "drive/portal.py no longer names its avatars in one place"
    # The literal drive actually writes, evaluated with the same kind of inputs.
    import hashlib
    name = "%d-%s.webp" % (7, hashlib.sha256(b"whatever").hexdigest()[:8])
    assert avatars.is_safe_name(name), (
        "drive stores avatars under a name accounts/ refuses to serve: %s" % name)
    assert "hexdigest()[:8]" in src, (
        "the digest length has to match `is_safe_name`, which wants exactly 8")
