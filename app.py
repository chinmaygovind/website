"""Personal website server.

Serves the static site under ``site/`` (the Wii menu is the site root) and
redirects ``/ttr`` to the Ticket to Ride service. Also hosts ``/accounts``, the
one page on this domain that is not static: the shared profile for the four
games, which lives in the ``accounts`` package and is registered at the bottom
of this file.

The static tree was authored for GitHub Pages, which auto-serves ``foo/index.html``
for a request to ``/foo/`` and redirects ``/foo`` -> ``/foo/``. Flask does neither
out of the box, so ``serve()`` re-implements that directory-index behaviour; without
it every ``/projects/...``, ``/games/...`` and ``/channels/...`` link would 404.
"""

import base64
import hmac
import json
import os
import threading
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

import accounts
from dotenv import load_dotenv
from flask import Flask, redirect, request, send_from_directory, abort
from werkzeug.utils import safe_join

# In production systemd passes the box's .env in through EnvironmentFile, so
# this does nothing there. Locally it is the only way the accounts pages find a
# database, and the four games all load it the same way.
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")

# Where the Wii "TTR" channel / the /ttr endpoint sends visitors. TTR runs as its
# own service (the ``ttr/`` git submodule); set TTR_URL to wherever it is reachable.
TTR_URL = os.environ.get("TTR_URL", "https://ttr.cgovind.com")

# Where /ers redirects. Egyptian Rat Screw runs as its own service (website/ers),
# like TTR; point this at wherever it is reachable.
ERS_URL = os.environ.get("ERS_URL", "https://ers.cgovind.com")

# Where /kot redirects. King of Tokyo runs as its own service (website/kot),
# like TTR and ERS; point this at wherever it is reachable.
KOT_URL = os.environ.get("KOT_URL", "https://kot.cgovind.com")

# Where /drive redirects. Drive runs as its own service (website/drive), like the
# other three; point this at wherever it is reachable.
DRIVE_URL = os.environ.get("DRIVE_URL", "https://drive.cgovind.com")

# The roll game and its `/api/roll/gemini` proxy are **gone** (August 2026), and
# the proxy is why. It forwarded the caller's JSON body verbatim to Gemini with
# this box's API key attached, with no login, no rate limit and no origin check -
# so it was a free Gemini endpoint for the internet, billed here, with the caller
# in full control of the prompt. It was also two requests away from taking the
# site down: `website` runs `gunicorn -w 2` *sync* workers and that call blocked
# for up to thirty seconds.
#
# Nothing linked to the game - it was reachable only by typing its URL - so the
# whole thing went rather than being put behind a login. If it ever comes back it
# needs a session, a per-account budget, and a pinned request shape rather than a
# pass-through. **Remove `GEMINI_API_KEY` from the box's .env and revoke the key**;
# deleting the route stops the spending, revoking it stops a leaked key mattering.

app = Flask(__name__)


# Chinmay's live Duolingo streak for the landing page's "fast facts". Duolingo's
# user API sends no CORS headers, so the browser can't read it directly; this
# same-origin proxy fetches it server-side and caches it (the streak ticks at
# most once a day, so an hour of staleness is fine and spares Duolingo the load).
DUOLINGO_USERNAME = "ChinmayGov"
DUOLINGO_API_URL = "https://www.duolingo.com/2017-06-30/users?username=" + DUOLINGO_USERNAME
DUOLINGO_CACHE_TTL = 3600  # seconds
_duolingo_cache = {"streak": None, "fetched_at": 0.0}


@app.route("/api/duolingo-streak")
def duolingo_streak():
    """Return Chinmay's current Duolingo streak (see the note by the constants)."""
    now = time.time()
    if (
        _duolingo_cache["streak"] is not None
        and now - _duolingo_cache["fetched_at"] < DUOLINGO_CACHE_TTL
    ):
        return {"streak": _duolingo_cache["streak"]}

    req = urlrequest.Request(
        DUOLINGO_API_URL,
        headers={"User-Agent": "Mozilla/5.0 (cgovind.com fast-facts)"},
    )
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        streak = int(data["users"][0]["streak"])
    except (urlerror.URLError, KeyError, IndexError, ValueError, TypeError, TimeoutError):
        # Serve the last good value if we have one; otherwise let the page keep
        # its built-in fallback number.
        if _duolingo_cache["streak"] is not None:
            return {"streak": _duolingo_cache["streak"], "stale": True}
        return {"streak": None}, 502

    _duolingo_cache["streak"] = streak
    _duolingo_cache["fetched_at"] = now
    return {"streak": streak}


# Every commit Chinmay has ever pushed to a public repo, for the same "fast
# facts" list. GitHub's commit *search* is the only endpoint that answers this in
# one call - the REST API can only list commits per repository, which would be 35
# calls and still miss forks. The catch is that search is limited to **10 requests
# a minute for anonymous callers**, shared by everyone behind this box's IP, so the
# hourly cache is not politeness here, it is the thing that keeps the endpoint
# working. Search also only indexes **public** repos, which is why the line on the
# page says so rather than claiming a total it cannot see. Setting GITHUB_TOKEN in
# .env raises the limit to 30/min; it is not needed and nothing breaks without it.
GITHUB_USERNAME = "chinmaygovind"
GITHUB_CACHE_TTL = 3600  # seconds
_github_cache = {"commits": None, "fetched_at": 0.0}


@app.route("/api/github-commits")
def github_commits():
    """Return Chinmay's all-time public commit count (see the note above)."""
    now = time.time()
    if (
        _github_cache["commits"] is not None
        and now - _github_cache["fetched_at"] < GITHUB_CACHE_TTL
    ):
        return {"commits": _github_cache["commits"]}

    query = "author:%s" % GITHUB_USERNAME
    url = "https://api.github.com/search/commits?per_page=1&q=" + urlparse.quote(query)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cgovind.com fast-facts",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlrequest.urlopen(urlrequest.Request(url, headers=headers), timeout=5) as resp:
            data = json.loads(resp.read())
        commits = int(data["total_count"])
    except (urlerror.URLError, KeyError, ValueError, TypeError, TimeoutError):
        # A rate-limited minute or a flaky search index shouldn't blank the line;
        # serve the last good count, or let the page keep the number in its markup.
        if _github_cache["commits"] is not None:
            return {"commits": _github_cache["commits"], "stale": True}
        return {"commits": None}, 502

    _github_cache["commits"] = commits
    _github_cache["fetched_at"] = now
    return {"commits": commits}


# Steps walked today, for the same "fast facts" list. **Nothing here fetches
# anything** - Apple Health is on-device only and iCloud health sync is
# end-to-end encrypted, so no server can ever ask Apple for this. The data flows
# the other way: an hourly iOS Shortcuts automation on Chinmay's phone POSTs the
# number here, and this endpoint only ever repeats back what it was last told.
#
# Two consequences worth knowing before changing any of it:
#
# * **It is stored on disk, not in memory.** The website runs `gunicorn -w 2`,
#   so the worker that receives the POST is usually not the worker answering the
#   next GET; an in-process variable would make the number appear and disappear
#   depending on which worker you landed on. Same reason the Spotify refresh
#   token is a file. The write is a temp-file rename so a reader never catches a
#   half-written file.
# * **A stale number is worse than no number**, because "steps today" reading
#   yesterday's total is simply false. So the GET reports how old the reading is
#   and the page *hides the line entirely* past STEPS_MAX_AGE rather than
#   showing a stale count. Phone off, out of signal, automation disabled - the
#   row quietly vanishes and comes back on its own. That is also why the row is
#   `hidden` in the markup instead of carrying a placeholder number: every other
#   fast fact can fall back to a hardcoded value that stays true, and this one
#   cannot.
#
# The POST is authenticated by a shared secret in the box .env (STEPS_SECRET),
# compared with hmac.compare_digest. Without it set, the endpoint refuses every
# write - it must never be the case that a missing config turns into an open
# "write anything to Chinmay's website" endpoint.
STEPS_FILE = os.path.join(BASE_DIR, "instance", "steps.json")
STEPS_MAX_AGE = 3 * 3600  # seconds; hourly automation, with slack for a missed run
STEPS_MAX = 500000  # a plausibility ceiling; the world record day is ~350k


def _steps_read():
    try:
        with open(STEPS_FILE) as f:
            data = json.load(f)
        return int(data["steps"]), float(data["at"])
    except (OSError, ValueError, TypeError, KeyError):
        return None, 0.0


def _steps_write(steps, at):
    """Atomically replace the stored reading (see the note about -w 2)."""
    tmp = STEPS_FILE + ".tmp"
    os.makedirs(os.path.dirname(STEPS_FILE), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump({"steps": steps, "at": at}, f)
    os.replace(tmp, STEPS_FILE)


@app.route("/api/steps", methods=["GET", "POST"])
def steps():
    """GET the last reported step count; POST a new one from the phone."""
    if request.method == "GET":
        steps_value, at = _steps_read()
        if steps_value is None:
            return {"steps": None}
        age = time.time() - at
        return {"steps": steps_value, "age": int(age), "fresh": age < STEPS_MAX_AGE}

    secret = os.environ.get("STEPS_SECRET", "")
    if not secret:
        return {"error": "not configured"}, 503
    body = request.get_json(silent=True) or {}
    given = body.get("secret", "")
    if not isinstance(given, str) or not hmac.compare_digest(given, secret):
        return {"error": "nope"}, 403
    try:
        steps_value = int(body["steps"])
    except (KeyError, ValueError, TypeError):
        return {"error": "steps must be a number"}, 400
    if not 0 <= steps_value <= STEPS_MAX:
        return {"error": "steps out of range"}, 400

    _steps_write(steps_value, time.time())
    return {"ok": True, "steps": steps_value}


# Chinmay's own Spotify account (recently played + top artists) for the landing
# page's music popup, shown to every visitor. Since it's one account read-only,
# auth happens once: visit /api/spotify/login (logged in as chinmay), approve
# the scopes, and the refresh token is cached to instance/spotify_refresh_token.txt.
# Set SPOTIFY_REFRESH_TOKEN in .env instead (e.g. in prod) to skip that file.
#
# The website service runs gunicorn -w 2 (two worker processes), so the refresh
# token can't be cached in memory across a rotation -- if worker A refreshes and
# Spotify rotates the token, worker B must see the new one on its very next
# refresh, or it'll keep retrying a dead token forever. So the cache file (or
# the static env var, if no file exists yet) is re-read on every refresh instead
# of trusting an in-process copy; only the short-lived access token is cached
# per-worker.
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get(
    "SPOTIFY_REDIRECT_URI", "http://localhost:5002/api/spotify/callback"
)
SPOTIFY_SCOPES = "user-read-recently-played user-top-read"
SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_CACHE_FILE = os.path.join(BASE_DIR, "instance", "spotify_refresh_token.txt")
SPOTIFY_DATA_CACHE_TTL = 300  # seconds
# Spotify may invalidate a refresh token that's gone unused for ~180 days.
# Exercising it daily -- even with zero site visitors -- keeps it well inside
# that window indefinitely.
SPOTIFY_KEEPALIVE_INTERVAL = 24 * 3600  # seconds

_spotify = {"access_token": None, "expires_at": 0.0}
_spotify_data_cache = {
    "recent": None, "recent_at": 0.0,
    "top_artists": None, "top_artists_at": 0.0,
}


def _spotify_current_refresh_token():
    """The freshest known refresh token: the on-disk cache (shared across
    gunicorn's worker processes) if present, else the static env value."""
    try:
        with open(SPOTIFY_TOKEN_CACHE_FILE) as f:
            token = f.read().strip()
        if token:
            return token
    except OSError:
        pass
    return os.environ.get("SPOTIFY_REFRESH_TOKEN", "")


def _spotify_save_refresh_token(token):
    try:
        os.makedirs(os.path.dirname(SPOTIFY_TOKEN_CACHE_FILE), exist_ok=True)
        with open(SPOTIFY_TOKEN_CACHE_FILE, "w") as f:
            f.write(token)
    except OSError:
        pass


def _spotify_token_request(data):
    body = urlparse.urlencode(data).encode()
    creds = base64.b64encode(
        (SPOTIFY_CLIENT_ID + ":" + SPOTIFY_CLIENT_SECRET).encode()
    ).decode()
    req = urlrequest.Request(
        SPOTIFY_TOKEN_URL,
        data=body,
        headers={
            "Authorization": "Basic " + creds,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _spotify_access_token():
    """Return a live access token, refreshing it if needed. None if unconfigured/failed."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    now = time.time()
    if _spotify["access_token"] and now < _spotify["expires_at"]:
        return _spotify["access_token"]
    refresh_token = _spotify_current_refresh_token()
    if not refresh_token:
        return None
    try:
        data = _spotify_token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
    except (urlerror.URLError, ValueError):
        return None
    _spotify["access_token"] = data.get("access_token")
    _spotify["expires_at"] = now + int(data.get("expires_in", 3600)) - 30
    if data.get("refresh_token"):
        _spotify_save_refresh_token(data["refresh_token"])
    return _spotify["access_token"]


def _spotify_keepalive_loop():
    while True:
        time.sleep(SPOTIFY_KEEPALIVE_INTERVAL)
        _spotify_access_token()


if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    threading.Thread(target=_spotify_keepalive_loop, daemon=True).start()


def _spotify_api_get(path, token):
    req = urlrequest.Request(
        SPOTIFY_API_BASE + path, headers={"Authorization": "Bearer " + token}
    )
    with urlrequest.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@app.route("/api/spotify/login")
def spotify_login():
    """One-time OAuth kickoff. Visit this logged in as chinmay to authorize."""
    if not SPOTIFY_CLIENT_ID:
        return {"error": "Spotify client id not configured on the server."}, 503
    params = urlparse.urlencode({
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "show_dialog": "true",
    })
    return redirect(SPOTIFY_AUTHORIZE_URL + "?" + params, code=302)


@app.route("/api/spotify/callback")
def spotify_callback():
    """Spotify redirects here with a code after the user approves the scopes."""
    error = request.args.get("error")
    if error:
        return "Spotify authorization failed: " + error, 400
    code = request.args.get("code")
    if not code:
        return "Missing code.", 400
    try:
        data = _spotify_token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        })
    except urlerror.URLError:
        return "Could not reach Spotify.", 502
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return "No refresh token in Spotify's response.", 502
    _spotify_save_refresh_token(refresh_token)
    _spotify["access_token"] = data.get("access_token")
    _spotify["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 30
    return "Spotify connected! You can close this tab."


@app.route("/api/spotify/recent")
def spotify_recent():
    now = time.time()
    if (
        _spotify_data_cache["recent"] is not None
        and now - _spotify_data_cache["recent_at"] < SPOTIFY_DATA_CACHE_TTL
    ):
        return {"tracks": _spotify_data_cache["recent"]}

    token = _spotify_access_token()
    if not token:
        return {"tracks": None}, 503
    try:
        data = _spotify_api_get("/me/player/recently-played?limit=10", token)
        tracks = []
        seen = set()
        for item in data.get("items", []):
            track = item.get("track") or {}
            track_id = track.get("id")
            if track_id:
                if track_id in seen:
                    continue
                seen.add(track_id)
            images = (track.get("album") or {}).get("images") or []
            tracks.append({
                "name": track.get("name"),
                "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                "image": images[-1]["url"] if images else None,
                "url": (track.get("external_urls") or {}).get("spotify"),
                "played_at": item.get("played_at"),
            })
    except (urlerror.URLError, KeyError, ValueError, TypeError):
        if _spotify_data_cache["recent"] is not None:
            return {"tracks": _spotify_data_cache["recent"], "stale": True}
        return {"tracks": None}, 502

    _spotify_data_cache["recent"] = tracks
    _spotify_data_cache["recent_at"] = now
    return {"tracks": tracks}


@app.route("/api/spotify/top-artists")
def spotify_top_artists():
    now = time.time()
    if (
        _spotify_data_cache["top_artists"] is not None
        and now - _spotify_data_cache["top_artists_at"] < SPOTIFY_DATA_CACHE_TTL
    ):
        return {"artists": _spotify_data_cache["top_artists"]}

    token = _spotify_access_token()
    if not token:
        return {"artists": None}, 503
    try:
        data = _spotify_api_get("/me/top/artists?limit=5&time_range=short_term", token)
        artists = []
        for a in data.get("items", []):
            images = a.get("images") or []
            artists.append({
                "name": a.get("name"),
                "image": images[-1]["url"] if images else None,
                "url": (a.get("external_urls") or {}).get("spotify"),
            })
    except (urlerror.URLError, KeyError, ValueError, TypeError):
        if _spotify_data_cache["top_artists"] is not None:
            return {"artists": _spotify_data_cache["top_artists"], "stale": True}
        return {"artists": None}, 502

    _spotify_data_cache["top_artists"] = artists
    _spotify_data_cache["top_artists_at"] = now
    return {"artists": artists}


@app.route("/ttr")
@app.route("/ttr/")
def ttr():
    """Hand off to the Ticket to Ride service."""
    return redirect(TTR_URL, code=302)


@app.route("/ers")
@app.route("/ers/")
def ers():
    """Hand off to the Egyptian Rat Screw service."""
    return redirect(ERS_URL, code=302)


@app.route("/kot")
@app.route("/kot/")
def kot():
    """Hand off to the King of Tokyo service."""
    return redirect(KOT_URL, code=302)


@app.route("/drive")
@app.route("/drive/")
def drive():
    """Hand off to the Drive service."""
    return redirect(DRIVE_URL, code=302)


# **The fonts are the one thing here worth caching hard, and not caching them
# was visible.** Flask's default for a static file is `Cache-Control: no-cache`,
# which does not mean "do not store" - it means "revalidate every time" - so a
# returning visitor still paid a network round trip to be told the font had not
# changed. Every page on this domain is set in that font and blocks on it, so
# that round trip was the flash of Comic Sans people saw on *every* load, not
# just their first. `/accounts` shares the same file (`/fonts/…`), so this fixes
# both.
#
# A year is safe because the file is immutable in practice - it is a font, it has
# not changed since it was added, and nothing generates it. **If it is ever
# replaced, change its filename**, because for a year the old one is all anybody
# who has been here will use. Everything else keeps the revalidating default:
# `index.html` in particular must never be cached like this, or an edit would
# take a year to reach the people who visit most.
FONT_MAX_AGE = 31536000  # one year, in seconds


def _max_age(path):
    """How long the browser may keep this file without asking again."""
    return FONT_MAX_AGE if path.startswith("fonts/") else None


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    """Serve a static file, or a directory's index.html (GitHub Pages style)."""
    target = safe_join(SITE_DIR, path)
    if target is None:  # path traversal attempt
        abort(404)

    if os.path.isdir(target):
        # Keep relative links correct: /projects/astro -> /projects/astro/
        if path and not path.endswith("/"):
            return redirect("/" + path + "/")
        index = safe_join(SITE_DIR, path, "index.html")
        if index and os.path.isfile(index):
            return send_from_directory(SITE_DIR, os.path.relpath(index, SITE_DIR))
        abort(404)

    if os.path.isfile(target):
        return send_from_directory(SITE_DIR, path, max_age=_max_age(path))

    abort(404)


@app.errorhandler(404)
def not_found(_e):
    """Fall back to the custom 404 (a small Mario-style platformer)."""
    return send_from_directory(SITE_DIR, "404.html"), 404


# The accounts pages. Registered last, though the order does not matter to the
# routing - Werkzeug sorts rules by how specific they are, so `/accounts/chinmay`
# beats the `/<path:path>` catch-all above without either having to know about
# the other. `test_accounts_beats_the_static_catch_all` pins that.
#
# Attaching them is conditional on a DATABASE_URL being set, so a checkout that
# only wants to serve the static site still boots with no database and no
# database driver anywhere near it.
accounts_enabled = accounts.init_app(app)

# Visit logging, on the same condition and for the same reason: it writes to
# the database the accounts pages brought with them, so a checkout without one
# serves the static tree exactly as before and records nothing. `visits.py` is
# the copy shared by all five services - see its docstring.
if accounts_enabled:
    import visits
    from accounts.models import db as accounts_db

    visits.init_app(app, accounts_db, "site")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=True)
