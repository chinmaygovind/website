"""Post a daily's reel to Instagram, as @drive.cgovind.

    python3 drive/tools/post_reel.py daily-26

Runs **on the box**, from the daily-reel Action, after `shoot_daily.py`'s mp4 and
caption have been copied to `drive/static/reels/`. Instagram fetches the video
itself, which is why the file has to be on a public URL first.

**The token lives in `/home/ubuntu/data/ig_token`**, not in the Action. An
Instagram token lasts 60 days and is renewed by trading it for a new one, and an
Action cannot write its own secrets back; a file on the box can be rewritten
every run. The Action's `IG_TOKEN` secret only seeds the file the first time.
A token under a day old cannot be renewed yet, which is not an error.

Stdlib only: the box's system python runs this, not a venv.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://graph.instagram.com/v23.0"
REELS = "https://drive.cgovind.com/static/reels/"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.environ.get("IG_TOKEN_FILE", "/home/ubuntu/data/ig_token")


def call(method, path, **params):
    data = urllib.parse.urlencode(params).encode()
    url = API + path if path.startswith("/") else path
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    # A dev-mode app's hourly request limit came up 21 posts into the backlog;
    # Instagram marks that transient, so wait it out rather than give up.
    for wait in (60, 120, 300, 600, 900, None):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if wait is None or '"is_transient":true' not in body:
                raise SystemExit("%s %s: %s" % (method, path, body[:500]))
            print("  rate limited, retrying in %ds" % wait)
            time.sleep(wait)


def renewed(token):
    """A fresh 60 days, written back. Keeps the old one if Instagram says no."""
    try:
        got = call("GET", "https://graph.instagram.com/refresh_access_token",
                   grant_type="ig_refresh_token", access_token=token)
    except SystemExit as e:
        print("  token not renewed: %s" % e)
        return token
    token = got["access_token"]
    tmp = TOKEN_FILE + ".new"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(token)
    os.replace(tmp, TOKEN_FILE)
    print("  token renewed, %d days left" % (got["expires_in"] // 86400))
    return token


def main():
    slug = sys.argv[1]
    with open(TOKEN_FILE) as f:
        token = renewed(f.read().strip())
    with open(os.path.join(os.path.dirname(HERE), "static", "reels", slug + ".txt")) as f:
        caption = f.read()
    me = call("GET", "/me", fields="user_id,username", access_token=token)
    print("  posting %s as @%s" % (slug, me["username"]))

    box = call("POST", "/%s/media" % me["user_id"], media_type="REELS",
               video_url=REELS + slug + ".mp4", caption=caption, share_to_feed="true",
               access_token=token)["id"]
    # Instagram downloads and transcodes it before it can be published.
    for _ in range(60):
        status = call("GET", "/" + box, fields="status_code,status", access_token=token)
        if status["status_code"] == "FINISHED":
            break
        if status["status_code"] in ("ERROR", "EXPIRED"):
            raise SystemExit("  instagram rejected the video: %s" % status.get("status"))
        time.sleep(10)
    else:
        raise SystemExit("  instagram still processing after 10 minutes")
    post = call("POST", "/%s/media_publish" % me["user_id"], creation_id=box,
                access_token=token)
    link = call("GET", "/" + post["id"], fields="permalink", access_token=token)
    print("  posted: %s" % link.get("permalink"))
    if not slug.startswith("daily-"):
        return
    # Where `shoot_daily.next_up` resumes. Never backwards, so re-posting an old
    # one by hand does not send the queue round again.
    mark = os.path.join(os.path.dirname(HERE), "static", "reels", "last-posted.txt")
    try:
        with open(mark) as f:
            last = int(f.read().strip() or 0)
    except FileNotFoundError:
        last = 0
    with open(mark, "w") as f:
        f.write(str(max(last, int(slug.rsplit("-", 1)[1]))))


if __name__ == "__main__":
    main()
