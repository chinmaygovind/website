"""The short paths that hand off to the other services.

Every service on cgovind.com has a subdomain and a short path on the main site
that redirects to it, and the two lists are kept in step here: a service that
appears on a profile page but has no way in from the landing page is a service
somebody has to know the URL of.

Conductor is the one that *must* be a redirect rather than a proxy - its
templates hardcode root-absolute paths and connect Socket.IO at the root, so it
only runs at a host's root. The rest are redirects for consistency with it.

**A service's key is not always its hostname.** For four of the five it is, and
these tests used to assume it always would be. Conductor's key stayed `ttr`
through the Sep 2026 rename because it is written into live presence rows, the
admin counts and the shared database, while its host and its environment
variable both became `conductor` - so the two facts are now listed separately
below rather than derived from the key. See the root CLAUDE.md.
"""

from accounts.gamestats import GAMES

# key -> the hostname and env-var prefix it actually uses, where that is not the
# key itself. One entry, and it is the rename.
RENAMED = {"ttr": "conductor"}


def host_of(game):
    return RENAMED.get(game["key"], game["key"]) + ".cgovind.com"


def env_prefix_of(game):
    return RENAMED.get(game["key"], game["key"]).upper()

# `app` is imported through the `flask_app` fixture and never at module level:
# it builds itself at import time and reads the environment while doing it, so
# importing it before conftest has set `DATABASE_URL` would attach no accounts
# blueprint and break every test in the session, not only these.


def test_every_service_on_a_profile_has_a_way_in_from_the_landing_page(flask_app):
    """The profile page lists five services. Five short paths have to exist,
    or one of them is reachable only by typing its subdomain."""
    rules = {str(r) for r in flask_app.url_map.iter_rules()}
    for game in GAMES:
        assert "/" + game["key"] in rules, \
            "%s is on the profile page but /%s does not exist" % (
                game["name"], game["key"])


def test_each_short_path_lands_on_that_service(client):
    for game in GAMES:
        r = client.get("/" + game["key"])
        assert r.status_code == 302, game["key"]
        assert host_of(game) in r.headers["Location"], game["key"]


def test_the_trailing_slash_goes_to_the_same_place(client):
    """Both spellings are registered on purpose: without the second, `/gto/`
    would 301 to `/gto` and then 302 away, which is two round trips to do one
    thing."""
    for game in GAMES:
        bare = client.get("/" + game["key"])
        slashed = client.get("/" + game["key"] + "/")
        assert slashed.status_code == 302, game["key"]
        assert slashed.headers["Location"] == bare.headers["Location"]


def test_a_redirect_target_can_be_pointed_somewhere_else(flask_app):
    """Each one reads an environment variable so a box can run a service
    locally or on another host without a code change."""
    import app as app_module
    for game in GAMES:
        assert hasattr(app_module, env_prefix_of(game) + "_URL"), game["key"]
