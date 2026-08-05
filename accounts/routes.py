"""Every page under /accounts.

Three groups, and the middle one is the reason the other two exist:

* **Public** - the directory and ``/accounts/<username>``. Anybody can read
  anybody's profile. The stats on it are already on four public leaderboards;
  what is *not* on it is the email address, which is the only thing here that
  was ever private.
* **Yours** - settings, reachable by the cog that only appears on your own
  profile. Changing an email or a password needs the current password typed
  again, because a session cookie is left behind on shared machines and the
  account is worth more than the convenience.
* **Getting back in** - forgot, reset, confirm. These are the ones the four
  games' login screens link to, and the only pages here that a logged-out
  stranger is expected to use.

The session cookie is the games'. There is no separate accounts login state.
"""

import os
from datetime import datetime

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)
from sqlalchemy import func, or_

from . import avatars, gamestats, mail, naming, places, tokens
from .models import User, UserProfile, db

bp = Blueprint("accounts", __name__, url_prefix="/accounts",
               template_folder="templates", static_folder="static",
               static_url_path="/accounts/static")

DIRECTORY_PAGE = 60


# ---------------------------------------------------------------------------
# Who is asking
# ---------------------------------------------------------------------------

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def _secret():
    return current_app.config["SECRET_KEY"]


def _avatar_dir():
    return current_app.config["AVATAR_DIR"]


def _profile(user, create=False):
    """The user's profile row, made on first write rather than on first read.

    Most accounts have never opened this page, and a row per account that says
    nothing is a row that has to be joined for ever after. ``create=True`` is
    only ever passed by something about to write to it.
    """
    if user.profile is None and create:
        user.profile = UserProfile()
    return user.profile


@bp.app_template_filter("usdate")
def _usdate(value):
    """9/22/2024. Written out here rather than with strftime because ``%-m`` is
    a glibc extension - correct on the box, wrong on anything else."""
    if not value:
        return ""
    return "%d/%d/%d" % (value.month, value.day, value.year)


@bp.app_template_filter("shortdate")
def _shortdate(value):
    """8/2, or 8/2/25 once it is not this year - a list of recent games is read
    for its order, and four digits of year on every row is four digits of noise."""
    if not value:
        return ""
    if value.year == datetime.utcnow().year:
        return "%d/%d" % (value.month, value.day)
    return "%d/%d/%02d" % (value.month, value.day, value.year % 100)


@bp.app_template_filter("ordinal")
def _ordinal(n):
    if n is None:
        return ""
    if 10 <= (n % 100) <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


@bp.app_context_processor
def _inject():
    """Things every accounts template needs, including on the error pages."""
    return {
        "me": current_user(),
        "places": places,
        "avatars": avatars,
        "now": datetime.utcnow(),
    }


# ---------------------------------------------------------------------------
# Public: the directory and a profile
# ---------------------------------------------------------------------------

@bp.route("/")
def directory():
    """Everybody, newest account last, with all four ratings on one row.

    Bots are excluded - they have accounts because the games needed somewhere
    to hang a rating, not because they are people - and so is any account with
    no rating anywhere *and* no profile, which is what a registration that
    never went anywhere looks like.
    """
    q = (request.args.get("q") or "").strip()
    users = User.query.filter(User.is_bot.isnot(True))
    if q:
        like = "%%%s%%" % q.lower()
        users = (users.outerjoin(UserProfile, UserProfile.user_id == User.id)
                 .filter(or_(func.lower(User.username).like(like),
                             func.lower(UserProfile.display_name).like(like))))
    users = users.order_by(User.created_at.asc()).limit(DIRECTORY_PAGE * 4).all()

    conn = db.session.connection()
    ratings = gamestats.ratings_for(conn, [u.id for u in users])
    rows = [{"user": u, "ratings": ratings.get(u.id, {})} for u in users]
    # Somebody who has played something goes above somebody who has not; within
    # each, the order is when they joined, which is the only neutral one.
    rows.sort(key=lambda r: (0 if r["ratings"] else 1, r["user"].created_at or datetime.min))

    return render_template("accounts/directory.html", rows=rows, q=q,
                           games=gamestats.GAMES)


@bp.route("/<username>")
def profile(username):
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if user is None:
        abort(404)
    # One canonical spelling per profile, so a link is one link.
    if user.username != username:
        return redirect(url_for("accounts.profile", username=user.username), code=301)

    blocks = gamestats.for_user(db.session.connection(), user.id)
    active = request.args.get("game")
    if active not in {b["key"] for b in blocks}:
        # Open on the game they have played most, which is the one a visitor
        # came to look at. Everything else is a click away and none of it moves.
        active = max(blocks, key=lambda b: (b["played"], b["elo"] or 0))["key"]

    return render_template("accounts/profile.html", user=user, blocks=blocks,
                           active=active, is_me=(current_user() is not None
                                                 and current_user().id == user.id))


@bp.route("/avatar/<name>")
def avatar(name):
    """Serve a stored avatar.

    The name is content-stamped, so it can be cached for a year: a new picture
    is a new name and the old one simply stops being linked. ``is_safe_name``
    re-checks the shape rather than trusting a column four other services can
    write to.
    """
    if not avatars.is_safe_name(name):
        abort(404)
    directory = _avatar_dir()
    if not os.path.isfile(os.path.join(directory, name)):
        abort(404)
    resp = send_from_directory(directory, name)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    """The same credentials as every game - this just sets the same cookie."""
    nxt = request.args.get("next") or request.form.get("next") or ""
    if request.method == "GET":
        if current_user():
            return redirect(nxt or url_for("accounts.profile",
                                           username=current_user().username))
        return render_template("accounts/login.html", next=nxt, mode="login")

    ident = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = User.query.filter(or_(User.username == ident,
                                 func.lower(User.email) == ident.lower())).first()
    if not user or not user.check_password(password):
        return render_template("accounts/login.html", next=nxt, mode="login",
                               error="Wrong username or password.",
                               ident=ident), 401
    _sign_in(user)
    return redirect(nxt or url_for("accounts.profile", username=user.username))


@bp.route("/register", methods=["GET", "POST"])
def register():
    nxt = request.args.get("next") or request.form.get("next") or ""
    if request.method == "GET":
        if current_user():
            return redirect(url_for("accounts.profile",
                                    username=current_user().username))
        return render_template("accounts/login.html", next=nxt, mode="register")

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    error = (naming.check_username(username) or naming.check_email(email)
             or naming.check_password(password))
    # 409 for "somebody already has that", 400 for "that is not a valid one",
    # which is the split the four games' own register routes already make.
    status = 400
    if not error and User.query.filter(func.lower(User.username) == username.lower()).first():
        error, status = ("That username is taken. If it's yours, log in - the same "
                         "account works on every game here."), 409
    if not error and User.query.filter(func.lower(User.email) == email).first():
        error, status = ("There's already an account with that email address. "
                         "Log in instead."), 409
    if error:
        return render_template("accounts/login.html", next=nxt, mode="register",
                               error=error, ident=username, email=email), status

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _sign_in(user)
    return redirect(nxt or url_for("accounts.settings"))


@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("guest_name", None)
    return redirect(url_for("accounts.directory"))


def _sign_in(user):
    session.permanent = True
    session["user_id"] = user.id
    session.pop("guest_name", None)


def _require_login():
    user = current_user()
    if user is None:
        return None, redirect(url_for("accounts.login", next=request.full_path))
    return user, None


# ---------------------------------------------------------------------------
# Yours: settings
# ---------------------------------------------------------------------------

@bp.route("/settings")
def settings():
    user, bounce = _require_login()
    if bounce:
        return bounce
    pinned, rest = places.picker_countries()
    return render_template("accounts/settings.html", user=user,
                           profile=user.profile,
                           pinned_countries=pinned, countries=rest,
                           states=places.US_STATES,
                           notice=request.args.get("ok"),
                           error=request.args.get("err"))


def _back(ok=None, err=None, anchor=None):
    """Back to the settings page, saying how it went.

    An error rolls the session back explicitly rather than trusting the request
    to end without a commit. The profile form is one save of four fields, and
    the checks are spread through it - the display name is assigned before the
    country is validated, and validating it runs a query, which flushes the
    assignment. Nothing after an error path commits today, so leaving it would
    work; it would work by coincidence, and the coincidence is one added line
    away from becoming a form that half-saves.
    """
    if err:
        db.session.rollback()
    url = url_for("accounts.settings")
    if ok:
        url += "?ok=" + ok
    elif err:
        url += "?err=" + err
    return redirect(url + ("#" + anchor if anchor else ""))


@bp.route("/settings/profile", methods=["POST"])
def save_profile():
    """Display name, where you're from, and which flag.

    The picture used to be part of this form and is not any more. Cropping it
    ends in a decision of its own - "use this one" - and having said that, being
    told the picture is not actually saved until you scroll past the country and
    press a second button is the wrong answer. So the crop dialog saves it, and
    this form is the three fields that genuinely are one thought.
    """
    user, bounce = _require_login()
    if bounce:
        return bounce
    profile = _profile(user, create=True)

    name = (request.form.get("display_name") or "").strip()
    if name:
        error = naming.check_display_name(name)
        if error:
            return _back(err=error)
        folded = naming.fold(name)
        clash = UserProfile.query.filter(UserProfile.display_name_lc == folded,
                                         UserProfile.user_id != user.id).first()
        if clash:
            return _back(err="Somebody is already using that display name.")
        # A display name may not be somebody else's username either - that is
        # the impersonation the uniqueness rule is actually about.
        taken = User.query.filter(func.lower(User.username) == folded,
                                  User.id != user.id).first()
        if taken:
            return _back(err="That name belongs to another account.")
        profile.display_name = name
        profile.display_name_lc = folded
    else:
        # Clearing it falls back to the username, which is never taken.
        profile.display_name = None
        profile.display_name_lc = None

    country = (request.form.get("country") or "").strip().lower()
    if country and country not in places.COUNTRY_NAMES:
        return _back(err="That isn't a country we have a flag for.")
    state = (request.form.get("us_state") or "").strip().upper()
    if state and state not in places.US_STATE_NAMES:
        return _back(err="That isn't a US state we have a flag for.")
    profile.country = country or None
    # A state is only meaningful under the US; keeping one against another
    # country would fly the wrong flag the moment somebody moved.
    profile.us_state = state if country == "us" else None
    profile.flag_pref = ("state" if request.form.get("flag_pref") == "state"
                         and profile.us_state else "country")

    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return _back(ok="Profile saved.")


@bp.route("/settings/avatar", methods=["POST"])
def save_avatar():
    """Take the cropped picture and answer in JSON.

    Its own endpoint because the crop dialog is its own decision: the page
    swaps the picture in place and says so, rather than sending you back to a
    reloaded form to look for what changed.

    The crop happens in the browser, so what arrives is already square - and is
    still decoded, cropped, resized and re-encoded here exactly as before. A
    client that crops is a convenience, not evidence about the bytes.
    """
    user, bounce = _require_login()
    if bounce:
        # A JSON caller wants a fact, not somebody else's login page.
        return jsonify({"ok": False, "error": "You're not logged in any more."}), 401

    upload = request.files.get("avatar")
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "No picture was sent."}), 400

    profile = _profile(user, create=True)
    try:
        stored = avatars.store(_avatar_dir(), user.id, upload.read())
    except avatars.AvatarError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    if profile.avatar and profile.avatar != stored:
        avatars.remove(_avatar_dir(), profile.avatar)
    profile.avatar = stored
    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "url": url_for("accounts.avatar", name=stored)})


@bp.route("/settings/avatar/remove", methods=["POST"])
def remove_avatar():
    """Also JSON, so removing and replacing feel like the same kind of thing.

    Hands back what the default looks like, since taking a picture away means
    putting the initial back and the page has to draw it without a reload.
    """
    user, bounce = _require_login()
    if bounce:
        return jsonify({"ok": False, "error": "You're not logged in any more."}), 401
    profile = _profile(user)
    if profile and profile.avatar:
        avatars.remove(_avatar_dir(), profile.avatar)
        profile.avatar = None
        profile.updated_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True, "url": None,
                    "initial": avatars.initial_for(user.display),
                    "colour": avatars.colour_for(user.username)})


@bp.route("/settings/password", methods=["POST"])
def change_password():
    user, bounce = _require_login()
    if bounce:
        return bounce

    if not user.check_password(request.form.get("current") or ""):
        return _back(err="That isn't your current password.", anchor="security")
    new = request.form.get("new") or ""
    error = naming.check_password(new)
    if error:
        return _back(err=error, anchor="security")
    if new != (request.form.get("confirm") or ""):
        return _back(err="The two new passwords don't match.", anchor="security")

    user.set_password(new)
    db.session.commit()
    # Not a question, a warning: if this was not them, this is how they find out.
    mail.password_changed_notice(user.email, user.display)
    return _back(ok="Password changed.", anchor="security")


@bp.route("/settings/email", methods=["POST"])
def change_email():
    """Ask for an address change. Nothing moves until the new address answers."""
    user, bounce = _require_login()
    if bounce:
        return bounce

    if not user.check_password(request.form.get("current") or ""):
        return _back(err="That isn't your current password.", anchor="security")
    new = (request.form.get("email") or "").strip().lower()
    error = naming.check_email(new)
    if error:
        return _back(err=error, anchor="security")
    if new == (user.email or "").lower():
        return _back(err="That's already your email address.", anchor="security")
    if User.query.filter(func.lower(User.email) == new, User.id != user.id).first():
        return _back(err="Another account already uses that address.", anchor="security")

    link = url_for("accounts.confirm_email", t=tokens.make_email_change(_secret(), user, new),
                   _external=True)
    mail.confirm_new_email(new, user.display, link)
    return _back(ok="Check %s for a link to confirm it. Until you do, your "
                    "address stays as it is." % new, anchor="security")


@bp.route("/confirm-email")
def confirm_email():
    try:
        user, new_email = tokens.read_email_change(
            _secret(), request.args.get("t", ""),
            lambda uid: db.session.get(User, uid))
    except ValueError as exc:
        return render_template("accounts/message.html", title="That link didn't work",
                               body=str(exc)), 400

    # Re-check at the last moment: the address could have been taken by somebody
    # else in the day since the link went out.
    if User.query.filter(func.lower(User.email) == new_email, User.id != user.id).first():
        return render_template(
            "accounts/message.html", title="That address is taken",
            body="Another account has claimed %s since this link was sent." % new_email), 409

    old = user.email
    user.email = new_email
    db.session.commit()
    mail.email_changed_notice(old, user.display, new_email)
    _sign_in(user)
    return render_template("accounts/message.html", title="Email address changed",
                           body="Your account now uses %s. We've let %s know, in "
                                "case that wasn't you." % (new_email, old),
                           link=url_for("accounts.settings"), link_text="Back to settings")


# ---------------------------------------------------------------------------
# Getting back in
# ---------------------------------------------------------------------------

@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    """Ask for a reset link.

    The answer is the same whatever happens - sent, not sent, no such account,
    mail server down. Anything else turns this box into a way of asking which
    email addresses have accounts here.
    """
    if request.method == "GET":
        return render_template("accounts/forgot.html")

    ident = (request.form.get("username") or "").strip()
    user = User.query.filter(or_(User.username == ident,
                                 func.lower(User.email) == ident.lower())).first()
    if user and user.email and not user.is_bot:
        link = url_for("accounts.reset", t=tokens.make_reset(_secret(), user),
                       _external=True)
        mail.password_reset(user.email, user.display, link)

    return render_template("accounts/message.html", title="Check your email",
                           body="If there's an account for %s, a link to set a new "
                                "password is on its way. It works once and expires "
                                "in an hour." % (ident or "that"),
                           link=url_for("accounts.login"), link_text="Back to log in")


@bp.route("/reset", methods=["GET", "POST"])
def reset():
    token = request.args.get("t") or request.form.get("t") or ""
    try:
        user = tokens.read_reset(_secret(), token,
                                 lambda uid: db.session.get(User, uid))
    except ValueError as exc:
        return render_template("accounts/message.html", title="That link didn't work",
                               body=str(exc), link=url_for("accounts.forgot"),
                               link_text="Send a new one"), 400

    if request.method == "GET":
        return render_template("accounts/reset.html", t=token, user=user)

    new = request.form.get("new") or ""
    error = naming.check_password(new)
    if not error and new != (request.form.get("confirm") or ""):
        error = "The two passwords don't match."
    if error:
        return render_template("accounts/reset.html", t=token, user=user,
                               error=error), 400

    user.set_password(new)
    db.session.commit()
    _sign_in(user)                       # straight in, rather than back to a form
    return render_template("accounts/message.html", title="Password set",
                           body="You're logged in. The same password works on "
                                "Ticket to Ride, Egyptian Rat Screw, King of "
                                "Tokyo and Drive.",
                           link=url_for("accounts.profile", username=user.username),
                           link_text="Go to your profile")


# ---------------------------------------------------------------------------
# The one thing the games ask this service for
# ---------------------------------------------------------------------------

@bp.route("/api/profile/<username>")
def api_profile(username):
    """Display name and flag for one account, as JSON.

    Not used by the games - they read the same table directly, since they are
    already connected to it - but it is the honest way for anything that is not
    to ask, and it is how the profile page's own links are checked in tests.
    """
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user:
        return jsonify({"error": "No such account."}), 404
    p = user.profile
    flag = places.flag_of(p.country if p else None,
                          p.us_state if p else None,
                          bool(p and p.flag_pref == "state"))
    return jsonify({
        "username": user.username,
        "display": user.display,
        "flag": flag[0] if flag else None,
        "flag_alt": flag[1] if flag else None,
        "profile_url": url_for("accounts.profile", username=user.username),
    })
