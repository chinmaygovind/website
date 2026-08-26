"""The short paths that hand off to the other services.

Every service on cgovind.com has a subdomain and a short path on the main site
that redirects to it, and the two lists are kept in step here: a service that
appears on a profile page but has no way in from the landing page is a service
somebody has to know the URL of.

TTR is the one that *must* be a redirect rather than a proxy - its templates
hardcode root-absolute paths and connect Socket.IO at the root, so it only runs
at a host's root. The rest are redirects for consistency with it.
"""

from accounts.gamestats import GAMES

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
        assert game["key"] + ".cgovind.com" in r.headers["Location"], game["key"]


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
        assert hasattr(app_module, game["key"].upper() + "_URL"), game["key"]
