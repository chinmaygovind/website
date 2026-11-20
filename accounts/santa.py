"""CIS 1600 Secret Santa 2026: sign-up, wishlists, a draw Chinmay can see, then one email run.

The page is static (`site/cis-1600/secret-santa-26/`); this is its JSON. Signing
up takes a cgovind.com account - the same login as the rest of the site - and
puts you on the list under that account's name and email. Everyone on the list
keeps a wishlist of Amazon items (`santa_wishes`, read by `amazon.lookup`), and
once the assignments have been emailed, your Santa sees yours on the page. An admin (see `admin.admin_user`) is put on the list by visiting,
sees the list and the draw, and can redraw as often as they like. **The site
never sends the assignment emails**: that is `mail_assignments()`, run by hand
on the box (see `site/CLAUDE.md`), so nothing goes out until Chinmay says so.
"""

import random
import threading
from datetime import datetime

from flask import Blueprint, abort, jsonify, request

from . import amazon, mail
from .admin import admin_user
from .models import db
from .routes import current_user

bp = Blueprint("santa", __name__, url_prefix="/cis-1600/secret-santa-26/api")

PAGE = "/cis-1600/secret-santa-26/"
LOGIN = "/accounts/login?next=" + PAGE
MAX_WISHES = 25


class SantaSignup(db.Model):
    __tablename__ = "santa_signups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    giftee_id = db.Column(db.Integer, db.ForeignKey("santa_signups.id"))
    emailed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    idea = db.Column(db.String(500))


def add_columns():
    """`create_all` never adds a column to an existing table, so add `idea` here once."""
    if "idea" not in {c["name"] for c in db.inspect(db.engine).get_columns("santa_signups")}:
        db.session.execute(db.text("ALTER TABLE santa_signups ADD COLUMN idea VARCHAR(500)"))
        db.session.commit()


class SantaWish(db.Model):
    """One thing somebody would like. A table of its own so `create_all` adds it to the live database."""
    __tablename__ = "santa_wishes"
    id = db.Column(db.Integer, primary_key=True)
    signup_id = db.Column(db.Integer, db.ForeignKey("santa_signups.id"), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    asin = db.Column(db.String(10))
    title = db.Column(db.String(300), nullable=False)
    image = db.Column(db.String(500))
    price = db.Column(db.String(20))
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_json(self):
        return {"id": self.id, "url": self.url, "title": self.title, "image": self.image,
                "price": self.price, "note": self.note}


def derange(ids):
    """Each id gives to the next one around a shuffled circle: nobody draws themselves."""
    ids = list(ids)
    random.shuffle(ids)
    return {a: ids[(i + 1) % len(ids)] for i, a in enumerate(ids)}


def _people():
    return SantaSignup.query.order_by(SantaSignup.created_at, SantaSignup.id).all()


def _emailed():
    return SantaSignup.query.filter(SantaSignup.emailed_at.isnot(None)).first() is not None


def _admin_signup(user):
    """The admin is always in. Added on their first visit, never twice."""
    email = (user.email or "").strip().lower()
    me = SantaSignup.query.filter_by(email=email).first()
    if me is None and not _emailed():
        me = SantaSignup(name=user.username.title(), email=email)
        db.session.add(me)
        _clear_draw()
        db.session.commit()
    return me


def _signup_of(user):
    """The list entry for this account, matched on its email, or None."""
    email = (user.email or "").strip().lower()
    return SantaSignup.query.filter_by(email=email).first() if email else None


def _wishes(signup):
    return [w.as_json() for w in
            SantaWish.query.filter_by(signup_id=signup.id).order_by(SantaWish.created_at, SantaWish.id)]


def _clear_draw():
    SantaSignup.query.update({SantaSignup.giftee_id: None})


@bp.get("/status")
def status():
    """Everything the page draws, cut down to what this visitor may see.

    Logged out: the head count and a login link. On the list: your own
    wishlist, and - only once the assignments are emailed, because a redraw
    before then would change it - who you are shopping for and their list.
    An admin also gets the whole list and the draw.
    """
    user = current_user()
    admin = admin_user()
    sent = _emailed()
    out = {"admin": admin is not None, "sent": sent, "login": LOGIN,
           "user": user.display if user else None}
    me = _admin_signup(admin) if admin else (_signup_of(user) if user else None)
    if me:
        out["me"] = me.name
        out["wishes"] = _wishes(me)
        out["idea"] = me.idea
        giftee = db.session.get(SantaSignup, me.giftee_id) if (sent and me.giftee_id) else None
        if giftee:
            out["giftee"] = {"name": giftee.name, "idea": giftee.idea, "wishes": _wishes(giftee)}
    people = _people()
    out["count"] = len(people)
    if admin:
        by_id = {p.id: p for p in people}
        counts = dict(db.session.query(SantaWish.signup_id, db.func.count(SantaWish.id))
                      .group_by(SantaWish.signup_id).all())
        out["people"] = [{"name": p.name, "email": p.email, "idea": p.idea,
                          "wishes": counts.get(p.id, 0)}
                         for p in people]
        out["pairs"] = [{"from": p.name, "to": by_id[p.giftee_id].name}
                        for p in people if p.giftee_id in by_id]
    return jsonify(out)


@bp.post("/signup")
def signup():
    """Put the logged-in account on the list, under its own name and email."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in with your cgovind.com account first.", login=LOGIN), 401
    name = (user.display or user.username).strip()[:60]
    email = (user.email or "").strip().lower()[:120]
    if not email:
        return jsonify(error="Your account has no email address on it."), 400
    if _emailed():
        return jsonify(error="Names have already been drawn!"), 409
    existing = SantaSignup.query.filter_by(email=email).first()
    if existing:
        return jsonify(ok=True, name=existing.name, already=True)
    db.session.add(SantaSignup(name=name, email=email))
    _clear_draw()          # a draw that leaves someone out is not a draw
    db.session.commit()
    threading.Thread(target=mail.send, daemon=True, args=(
        email, "You're in the CIS 1600 Secret Santa!",
        "Hi %s,\n\nYou're signed up for the CIS 1600 Secret Santa. Add a few "
        "things you'd like to your wishlist, so your Santa has some ideas:\n\n"
        "    https://cgovind.com%s\n\nWhen everyone's in, names get drawn and "
        "you'll get an email telling you who you're shopping for.\n\n"
        "Merry Christmas!\n" % (name, PAGE))).start()
    return jsonify(ok=True, name=name)


@bp.post("/draw")
def draw():
    if admin_user() is None:
        abort(404)
    if _emailed():
        return jsonify(error="Emails already went out."), 409
    people = _people()
    if len(people) < 3:
        return jsonify(error="Need at least 3 people to draw names."), 400
    for giver, giftee in derange(p.id for p in people).items():
        db.session.get(SantaSignup, giver).giftee_id = giftee
    db.session.commit()
    return jsonify(ok=True)


def _my_signup_or_error():
    user = current_user()
    if user is None:
        return None, (jsonify(error="Log in first.", login=LOGIN), 401)
    me = _admin_signup(user) if admin_user() else _signup_of(user)
    if me is None:
        return None, (jsonify(error="Sign up first, then make your wishlist."), 403)
    return me, None


@bp.post("/wishlist")
def add_wish():
    """Add an Amazon item to your own wishlist.

    The link is read by `amazon.lookup`. When Amazon will not show the server
    the page there is no title, and the response says ``need_title`` so the page
    can ask what the thing is; a ``title`` sent with the link always wins.
    """
    me, err = _my_signup_or_error()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    pasted = (data.get("url") or "").strip()[:1000]
    typed = " ".join((data.get("title") or "").split())[:300]
    note = " ".join((data.get("note") or "").split())[:200] or None
    if SantaWish.query.filter_by(signup_id=me.id).count() >= MAX_WISHES:
        return jsonify(error="That's a long list already! Remove something first."), 400
    try:
        item = amazon.lookup(pasted)
    except amazon.NotAmazon:
        return jsonify(error="Paste a link to something on Amazon."), 400
    title = typed or item["title"]
    if not title:
        return jsonify(error="Amazon wouldn't tell us what that is. What is it?",
                       need_title=True), 422
    wish = SantaWish(signup_id=me.id, url=item["url"][:500], asin=item["asin"],
                     title=title, image=(item["image"] or None) and item["image"][:500],
                     price=item["price"], note=note)
    db.session.add(wish)
    db.session.commit()
    return jsonify(ok=True, wish=wish.as_json())


@bp.post("/idea")
def set_idea():
    """Your free-text gift idea, for things that aren't an Amazon link."""
    me, err = _my_signup_or_error()
    if err:
        return err
    me.idea = ((request.get_json(silent=True) or {}).get("idea") or "").strip()[:500] or None
    db.session.commit()
    return jsonify(ok=True, idea=me.idea)


@bp.post("/wishlist/<int:wish_id>/delete")
def delete_wish(wish_id):
    me, err = _my_signup_or_error()
    if err:
        return err
    wish = db.session.get(SantaWish, wish_id)
    if wish is None or wish.signup_id != me.id:
        abort(404)
    db.session.delete(wish)
    db.session.commit()
    return jsonify(ok=True)


def mail_assignments():
    """Email everyone their giftee. Run by hand on the box; never from a route.

    Synchronous and one at a time, so the output says exactly who got one, and
    a rerun only mails the people who did not.
    """
    people = _people()
    by_id = {p.id: p for p in people}
    if not people or any(p.giftee_id not in by_id for p in people):
        raise SystemExit("not everyone has an assignment: draw names first")
    for p in people:
        if p.emailed_at:
            continue
        ok = mail.send(
            p.email, "Your CIS 1600 Secret Santa assignment",
            "Hi %s,\n\nNames have been drawn! You are Secret Santa for:\n\n"
            "    %s\n\nTheir wishlist is on the Secret Santa page when you log "
            "in:\n\n    https://cgovind.com%s\n\nKeep it a secret!\n\n"
            "Merry Christmas!\n" % (p.name, by_id[p.giftee_id].name, PAGE))
        if ok:
            p.emailed_at = datetime.utcnow()
            db.session.commit()
        print(("sent  " if ok else "FAILED") + "  %s <%s>" % (p.name, p.email))
