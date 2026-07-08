"""Personal website server.

Serves the static site under ``site/`` (the Wii menu is the site root) and
redirects ``/ttr`` to the Ticket to Ride service.

The static tree was authored for GitHub Pages, which auto-serves ``foo/index.html``
for a request to ``/foo/`` and redirects ``/foo`` -> ``/foo/``. Flask does neither
out of the box, so ``serve()`` re-implements that directory-index behaviour; without
it every ``/projects/...``, ``/games/...`` and ``/channels/...`` link would 404.
"""

import os

from flask import Flask, redirect, send_from_directory, abort
from werkzeug.utils import safe_join

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")

# Where the Wii "TTR" channel / the /ttr endpoint sends visitors. TTR runs as its
# own service (the ``ttr/`` git submodule); set TTR_URL to wherever it is reachable.
TTR_URL = os.environ.get("TTR_URL", "http://52.54.184.133")

app = Flask(__name__)


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
