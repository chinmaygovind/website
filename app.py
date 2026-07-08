"""Personal website server.

Serves the static site under ``site/`` (the Wii menu is the site root) and
redirects ``/ttr`` to the Ticket to Ride service.

The static tree was authored for GitHub Pages, which auto-serves ``foo/index.html``
for a request to ``/foo/`` and redirects ``/foo`` -> ``/foo/``. Flask does neither
out of the box, so ``serve()`` re-implements that directory-index behaviour; without
it every ``/projects/...``, ``/games/...`` and ``/channels/...`` link would 404.
"""

import os
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import Flask, Response, redirect, request, send_from_directory, abort
from werkzeug.utils import safe_join

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")

# Where the Wii "TTR" channel / the /ttr endpoint sends visitors. TTR runs as its
# own service (the ``ttr/`` git submodule); set TTR_URL to wherever it is reachable.
TTR_URL = os.environ.get("TTR_URL", "http://52.54.184.133")

# The roll game's NPC dialog talks to Google's Gemini API. The key MUST stay
# server-side — a key shipped in client JS is world-readable — so the browser
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


@app.route("/ttr")
@app.route("/ttr/")
def ttr():
    """Hand off to the Ticket to Ride service."""
    return redirect(TTR_URL, code=302)


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
