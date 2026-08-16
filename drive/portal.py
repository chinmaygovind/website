"""Running as somebody else's game: CrazyGames.

A portal does not host Drive - it puts ``<iframe src="drive.cgovind.com/solo">``
on a page of its own. `test_embedding.py` already covers what the *browser* does
differently in there (the session cookie needs ``SameSite=None; Partitioned``,
and the keyboard does not arrive until the door is clicked). This module is
about what the *portal* asks of us, which is a different list and a stricter one,
because failing any of it means the game is not accepted at all.

**Two rules shape everything here.**

*No external login options.* CrazyGames forbids Facebook, Google or email login
inside the frame - their own account is the only one a player may sign in with.
Drive's login page is username-and-password, so in portal mode it does not exist:
not hidden, *gone*, routes included (`app.portal_only_404`). What replaces it is
this module - the SDK hands the page a JWT, `verify_token` checks it against
CrazyGames' published key, and `resolve_user` turns it into an ordinary
cgovind.com account. The player never types anything.

*Sitelock.* `frame_ancestors` is the header that says who may frame the game, and
it has to name every domain they serve from or the game is blank in half of
Europe. Their documentation offers ``crazygames.*`` as a wildcard **and that is
not valid CSP** - the grammar has no TLD wildcard, so a browser drops the whole
source expression and every ccTLD host with it. They are enumerated below.

**The accounts made here are ordinary accounts.** A row in the shared ``users``
table, usable in Ticket to Ride and King of Tokyo, on the same leaderboard as
everybody else, with a `drive_portal_users` row saying where it came from. The
only two things that mark them out: the username is a hash rather than a name
they chose (see `resolve_user`), and cgovind.com's accounts directory leaves
them out, because that list is meant to be people you might go and play with.
"""

import hashlib
import io
import json
import os
import threading
import time
from datetime import datetime
from urllib import error as urlerror
from urllib import request as urlrequest

from models import DrivePortalUser, User, UserProfile, db

# The one portal so far. A slug rather than a boolean because the second one
# (Poki, itch) differs in every detail of its SDK while differing in *none* of
# what the rest of the codebase does about it - the pages ask "am I in a portal",
# never "am I in CrazyGames".
CRAZYGAMES = "crazygames"
PORTALS = {CRAZYGAMES}


# ---------------------------------------------------------------------------
# Sitelock
# ---------------------------------------------------------------------------

# Every host CrazyGames frames a game from, from their sitelock documentation.
#
# `https://*.crazygames.com` covers www, games (which is where the video ads
# run), developer (which is where the QA preview and the submission flow frame
# it, so leaving it out fails the review rather than the game), and the language
# subdomains - de, it, vn, gr, ar, th. The apex is listed on its own because a
# wildcard does not match it.
#
# **The rest are separate registrable domains and each one has to be named.**
# This is the part their own docs get wrong: they suggest `crazygames.*`, and
# CSP has no such thing. An unrecognised source expression is ignored by the
# browser - silently - so the header would look right, pass a reading, and leave
# www.crazygames.fr with a blank frame.
CRAZYGAMES_ANCESTORS = [
    "https://*.crazygames.com",
    "https://crazygames.com",
    "https://www.crazygames.fr",
    "https://www.crazygames.co.id",
    "https://www.crazygames.cz",
    "https://www.crazygames.dk",
    "https://www.crazygames.hu",
    "https://www.crazygames.nl",
    "https://www.crazygames.no",
    "https://www.crazygames.pl",
    "https://www.crazygames.com.br",
    "https://www.crazygames.ro",
    "https://www.crazygames.fi",
    "https://www.crazygames.se",
    "https://www.crazygames.ru",
    "https://www.crazygames.com.ua",
    "https://www.crazygames.at",
    "https://www.crazygames.jp",
    "https://www.crazygames.pt",
    "https://www.crazygames.vn",
    "https://www.crazygames.com.vn",
    "https://www.crazygames.co.kr",
]


def host_portal(host):
    """The portal whose page this hostname is, or None.

    Derived from the sitelock list rather than written twice: the question "may
    this site frame us" and the question "is this site a portal" have to have
    the same answer, and a second list would drift.

    Used only as a *fallback* for a frame that arrived without `?portal=` on it
    (see `app._remember_the_portal`). Matching is exact, or one label under a
    wildcard - so `de.crazygames.com` matches `*.crazygames.com` and
    `crazygames.evil.example` matches nothing, which the obvious regex over the
    string "crazygames." would have let through.
    """
    host = (host or "").lower().rstrip(".")
    if not host:
        return None
    for entry in CRAZYGAMES_ANCESTORS:
        pattern = entry.split("://", 1)[-1]
        if pattern.startswith("*."):
            if host == pattern[2:] or host.endswith(pattern[1:]):
                return CRAZYGAMES
        elif host == pattern:
            return CRAZYGAMES
    return None


def frame_ancestors():
    """The value of ``Content-Security-Policy: frame-ancestors``.

    ``'self'`` first, which is not about portals at all: the game frames its own
    pages nowhere today, but a CSP that forgot it would be one refactor away
    from a blank panel on our own site, and that is the sort of thing nobody
    tests for.

    `FRAME_ANCESTORS` in the box `.env` replaces the whole list. The deploy
    never touches that file, so this exists for the case it is needed *now* -
    a second portal, or CrazyGames adding a domain - without waiting for a
    release. Set it to `*` to turn the sitelock off entirely.
    """
    override = os.environ.get("FRAME_ANCESTORS", "").strip()
    if override:
        return override
    return " ".join(["'self'"] + CRAZYGAMES_ANCESTORS)


# ---------------------------------------------------------------------------
# The token
# ---------------------------------------------------------------------------

PUBLIC_KEY_URL = "https://sdk.crazygames.com/publicKey.json"

# Their key is long-lived, so this is cached for a day rather than fetched per
# sign-in - a portal player arriving is a page load, and a page load may not
# wait on somebody else's CDN. A failure keeps the last good key rather than
# clearing it, for the same reason the Spotify proxy does: an outage at their
# end should not sign everybody out here.
_KEY_TTL = 24 * 3600
_key = {"pem": None, "fetched_at": 0.0}
_key_lock = threading.Lock()

# Set from the box `.env` once the game has an id. Unset means "do not check",
# which is the honest state before submission - a token is still verified
# against CrazyGames' signature, this only pins *which* game it was minted for.
# Worth setting after approval: without it a token from any other CrazyGames
# game would be accepted here.
GAME_ID = os.environ.get("CRAZYGAMES_GAME_ID", "").strip()


def _public_key():
    with _key_lock:
        now = time.time()
        if _key["pem"] and now - _key["fetched_at"] < _KEY_TTL:
            return _key["pem"]
        try:
            req = urlrequest.Request(PUBLIC_KEY_URL,
                                     headers={"User-Agent": "drive.cgovind.com"})
            with urlrequest.urlopen(req, timeout=5) as resp:
                pem = json.loads(resp.read())["publicKey"]
        except (urlerror.URLError, KeyError, ValueError, TypeError, TimeoutError):
            return _key["pem"]
        _key["pem"] = pem
        _key["fetched_at"] = now
        return pem


def verify_token(token):
    """CrazyGames' JWT -> its claims, or None if it is not theirs.

    Verified on the server and never read on the client, which is their
    instruction and the only version that means anything: the claims name who
    the player is, and a client that decoded its own token could name anybody.

    Returns a dict with at least ``userId``; ``username`` and
    ``profilePictureUrl`` are what the account is built from and may be absent.
    """
    if not token or not isinstance(token, str) or len(token) > 4096:
        return None
    pem = _public_key()
    if not pem:
        return None
    try:
        import jwt
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
    except ImportError:
        # No JWT library on this box: portal sign-in is off, and the game is
        # otherwise unaffected. Deliberately not fatal - a checkout that only
        # wants to serve drive.cgovind.com needs none of this.
        return None
    try:
        # Loaded here rather than handed to PyJWT as a string: their key is
        # PKCS#1 (`BEGIN RSA PUBLIC KEY`), and which of the two PEM shapes a
        # given PyJWT version accepts has changed between releases. `cryptography`
        # takes both and is the thing PyJWT would call anyway.
        key = load_pem_public_key(pem.encode())
        claims = jwt.decode(token, key, algorithms=["RS256"],
                            options={"require": ["userId"]})
    except Exception:
        # A bad signature, an expired token, a shape we do not know: all of them
        # are the same answer here, which is "this is not a signed-in player".
        return None
    if not claims.get("userId"):
        return None
    if GAME_ID and str(claims.get("gameId", "")) != GAME_ID:
        return None
    return claims


# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------

# What a name may not contain. Not a second copy of `app.GUEST_BAD_CHARS` - the
# caller passes the cleaning in (`resolve_user(clean_name=...)`) precisely so
# there is one rule - but a portal username also has to survive being a *column*,
# so it is trimmed to the 30 characters `user_profiles.display_name` holds.
DISPLAY_MAX = 30


def _portal_username(portal, portal_user_id):
    """The permanent, public username for a portal account.

    **It is a hash, and that is the whole design.** A username here is the login
    and the address of a profile at cgovind.com/accounts/<username>, and it can
    never be changed. A CrazyGames player never asked for one, so minting
    `nick2` out of their portal name would hand somebody a permanent public
    address they did not choose and cannot get rid of - and would put a name a
    stranger picked into the namespace real accounts are named from, where
    `chinmay` is already taken and taking it is the impersonation the whole
    display-name constraint exists to stop.

    So the username is machinery and the *display name* is theirs. Hashed rather
    than sequential so it does not publish how many people have played.
    """
    h = hashlib.sha256(("%s:%s" % (portal, portal_user_id)).encode()).hexdigest()
    return "cg-" + h[:12]


def _free_display_name(wanted, user_id):
    """`wanted` if nobody has it, else `wanted (2)`, `(3)`... else None.

    Two collisions to dodge, not one. `user_profiles.display_name_lc` is unique,
    and a display name may not equal anybody else's *username* either - two rows
    reading "chinmay" on one leaderboard is exactly what that rule is for, and a
    portal is the first place names arrive that nobody here vetted.
    """
    for n in range(1, 12):
        cand = wanted if n == 1 else "%s (%d)" % (wanted[:DISPLAY_MAX - 4], n)
        lc = cand.lower()
        clash = (UserProfile.query
                 .filter(UserProfile.display_name_lc == lc,
                         UserProfile.user_id != user_id).first()
                 or User.query.filter(db.func.lower(User.username) == lc,
                                      User.id != user_id).first())
        if not clash:
            return cand
    return None


def resolve_user(portal, claims, clean_name):
    """The account behind a verified token, made on the spot the first time.

    `clean_name` is `app`'s own name rule, passed in rather than copied: the
    drift test pins that regex to `app.py` and a second version of it here is
    the exact failure `visits.py`'s copy-don't-merge convention exists to avoid.

    Returns ``(user, created)``.
    """
    pid = str(claims["userId"])
    link = DrivePortalUser.query.filter_by(portal=portal, portal_user_id=pid).first()

    created = False
    user = db.session.get(User, link.user_id) if link else None
    if user is None:
        # Either this player is new, or the account was deleted out from under
        # an existing link. The second is why the link is *repointed* rather
        # than deleted and remade: its primary key is (portal, portal_user_id),
        # so a delete and an insert of the same key in one flush is SQLAlchemy
        # being asked to order two statements it has no reason to order.
        username = _portal_username(portal, pid)
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                # Unique by construction and deliberately undeliverable: there
                # is no password to reset and no address to reset it to. The
                # column is NOT NULL, so it needs *something*, and `.invalid` is
                # the TLD reserved for exactly this (RFC 2606).
                email=username + "@crazygames.invalid",
                # None, like a Google account: there is no password, so there is
                # nothing for `/login` to accept even if somebody found the page.
                password_hash=None,
            )
            db.session.add(user)
            db.session.flush()
            created = True
        if link:
            link.user_id = user.id
        else:
            link = DrivePortalUser(portal=portal, portal_user_id=pid,
                                   user_id=user.id)
            db.session.add(link)

    _sync_profile(user, link, claims, clean_name)

    # `last_seen` is coarse on purpose. The page calls this on *every* load, so
    # stamping it to the second would make a write out of every request that had
    # nothing to say - and the whole point of the `last_` columns above is that
    # the ordinary load is a read. Ten minutes is finer than anything ever asks
    # of this column.
    now = datetime.utcnow()
    if link.last_seen is None or (now - link.last_seen).total_seconds() > 600:
        link.last_seen = now

    if db.session.dirty or db.session.new:
        db.session.commit()
    return user, created


def _sync_profile(user, link, claims, clean_name):
    """Keep the display name and picture in step with the portal's copy.

    Required rather than tidy: CrazyGames ask that a player renaming themselves
    or changing their picture is reflected in the game. `last_username` and
    `last_avatar_url` are what make that a no-op on every load but the one where
    something actually moved - the name lookup is two indexed queries and the
    picture is a download, and neither belongs on a page load that changes nothing.
    """
    raw = (claims.get("username") or "").strip()
    name = clean_name(raw)[:DISPLAY_MAX].strip() if raw else ""
    avatar_url = (claims.get("profilePictureUrl") or "").strip()

    profile = user.profile
    if name and (name != link.last_username or profile is None
                 or not profile.display_name):
        chosen = _free_display_name(name, user.id)
        if chosen:
            if profile is None:
                profile = UserProfile(user_id=user.id)
                db.session.add(profile)
            profile.display_name = chosen
            profile.display_name_lc = chosen.lower()
            profile.updated_at = datetime.utcnow()
        link.last_username = name

    if avatar_url and avatar_url != link.last_avatar_url:
        stored = import_avatar(user.id, avatar_url)
        if stored:
            if profile is None:
                profile = UserProfile(user_id=user.id)
                db.session.add(profile)
            if profile.avatar and profile.avatar != stored:
                _remove_avatar(profile.avatar)
            profile.avatar = stored
            profile.updated_at = datetime.utcnow()
        # Recorded either way. A picture their CDN will not give us today is not
        # a reason to try again on every single page load for the rest of time.
        link.last_avatar_url = avatar_url


# ---------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------

# Where the accounts pages keep avatars. In prod that is `/home/ubuntu/avatars`,
# outside the repo so the deploy's `git reset --hard` can never be near it, and
# it has to be set in `drive/.env` by hand for the same reason it is set in the
# website's - **the deploy never touches a box `.env`**. Unset, this falls back
# to a path inside the checkout, and a portal player simply keeps the drawn
# initial that anybody with no picture gets. That is a supported state, not a
# broken one: Drive itself renders no avatars anywhere, so the only screen this
# changes is the shared profile at cgovind.com/accounts.
AVATAR_DIR = os.environ.get(
    "AVATAR_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "instance", "avatars"))

# The same numbers `accounts/avatars.py` stores at, because these files land in
# the same directory and are served by the same route.
AVATAR_PX = 256
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}


def import_avatar(user_id, url):
    """Fetch a portal's profile picture and store it the way `accounts/` does.

    The bytes that arrive are never the bytes that are kept: Pillow decodes,
    checks the format it really is, centre-crops, resizes and **re-encodes**, and
    only what Pillow writes goes to disk. That is the rule the upload path at
    cgovind.com/accounts already follows and the reason is the same one - an
    image that survives that round trip is not carrying a payload, and a file
    that was never an image does not survive it at all. It matters no less for
    coming from CrazyGames' CDN than for coming from a form: it is still a URL a
    stranger's account controls.

    **The stored name has to be `<user id>-<8 hex>.webp` and not merely unique.**
    `accounts.avatars.is_safe_name` re-checks that shape at serve time rather
    than trusting a column five services can write, so a name of any other shape
    is stored successfully, recorded successfully, and then 404s for ever.
    `test_no_drift.py` holds the two ends together.
    """
    if not url.startswith("https://"):
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        req = urlrequest.Request(url, headers={"User-Agent": "drive.cgovind.com"})
        with urlrequest.urlopen(req, timeout=6) as resp:
            raw = resp.read(AVATAR_MAX_BYTES + 1)
        if len(raw) > AVATAR_MAX_BYTES:
            return None
        img = Image.open(io.BytesIO(raw))
        fmt = (img.format or "").upper()
        img.load()
        if fmt not in AVATAR_FORMATS:
            return None
        img = ImageOps.exif_transpose(img)
        img = (img.convert("RGBA") if img.mode in ("RGBA", "LA", "P")
               else img.convert("RGB"))
        img = ImageOps.fit(img, (AVATAR_PX, AVATAR_PX), method=Image.LANCZOS,
                           centering=(0.5, 0.5))
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=86, method=4)
        data = out.getvalue()
    except Exception:
        # Their CDN, a format Pillow will not take, a redirect to something that
        # is not an image. None of it may cost the player their sign-in.
        return None
    name = "%d-%s.webp" % (user_id, hashlib.sha256(data).hexdigest()[:8])
    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        path = os.path.join(AVATAR_DIR, name)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
    except OSError:
        return None
    return name


def _remove_avatar(name):
    """Drop the picture a portal player has just replaced. Never raises."""
    if not name or "/" in name or "\\" in name or not name.endswith(".webp"):
        return
    try:
        os.remove(os.path.join(AVATAR_DIR, name))
    except OSError:
        pass
