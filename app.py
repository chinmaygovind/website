"""Personal website server.

Serves the static site under ``site/`` (the Wii menu is the site root) and
redirects ``/ttr`` to the Ticket to Ride service.

The static tree was authored for GitHub Pages, which auto-serves ``foo/index.html``
for a request to ``/foo/`` and redirects ``/foo`` -> ``/foo/``. Flask does neither
out of the box, so ``serve()`` re-implements that directory-index behaviour; without
it every ``/projects/...``, ``/games/...`` and ``/channels/...`` link would 404.
"""

import base64
import json
import os
import threading
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from flask import Flask, Response, redirect, request, send_from_directory, abort
from werkzeug.utils import safe_join

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

# The roll game's NPC dialog talks to Google's Gemini API. The key MUST stay
# server-side - a key shipped in client JS is world-readable - so the browser
# hits /api/roll/gemini here and this process adds the key. Set GEMINI_API_KEY in
# .env (empty by default; the feature just degrades gracefully when unset).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
MAX_GEMINI_BODY = 16 * 1024  # generous for a line of dialog; caps proxy abuse

app = Flask(__name__)


@app.route("/api/roll/gemini", methods=["POST"])
def roll_gemini():
    """Proxy the roll game's dialog request to Gemini, injecting the API key.

    Keeps the key out of the browser. Forwards the client's JSON body verbatim
    and relays Gemini's response (and error) straight back.
    """
    if not GEMINI_API_KEY:
        return {"error": "Gemini API key not configured on the server."}, 503

    body = request.get_data()
    if len(body) > MAX_GEMINI_BODY:
        return {"error": "Request too large."}, 413

    proxied = urlrequest.Request(
        GEMINI_API_URL + "?key=" + GEMINI_API_KEY,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(proxied, timeout=30) as resp:
            return Response(resp.read(), status=resp.status, mimetype="application/json")
    except urlerror.HTTPError as exc:
        return Response(exc.read(), status=exc.code, mimetype="application/json")
    except urlerror.URLError:
        return {"error": "Could not reach the Gemini API."}, 502


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
        return send_from_directory(SITE_DIR, path)

    abort(404)


@app.errorhandler(404)
def not_found(_e):
    """Fall back to the custom 404 (a small Mario-style platformer)."""
    return send_from_directory(SITE_DIR, "404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=True)
