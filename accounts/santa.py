"""CIS 1600 Secret Santa 2026: sign-up, a draw Chinmay can see, then one email run.

The page is static (`site/cis-1600/secret-santa-26/`); this is its JSON. Anyone
may sign up. An admin (see `admin.admin_user`) is put on the list by visiting,
sees the list and the draw, and can redraw as often as they like. **The site
never sends the assignment emails**: that is `mail_assignments()`, run by hand
on the box (see `site/CLAUDE.md`), so nothing goes out until Chinmay says so.
"""

import random
import re
import threading
from datetime import datetime

from flask import Blueprint, abort, jsonify, request

from . import mail
from .admin import admin_user
from .models import db

bp = Blueprint("santa", __name__, url_prefix="/cis-1600/secret-santa-26/api")

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SantaSignup(db.Model):
    __tablename__ = "santa_signups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    giftee_id = db.Column(db.Integer, db.ForeignKey("santa_signups.id"))
    emailed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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


def _clear_draw():
    SantaSignup.query.update({SantaSignup.giftee_id: None})


@bp.get("/status")
def status():
    user = admin_user()
    out = {"admin": user is not None, "sent": _emailed()}
    if user:
        me = _admin_signup(user)
        out["me"] = me and me.name
    people = _people()
    out["count"] = len(people)
    if user:
        by_id = {p.id: p for p in people}
        out["people"] = [{"name": p.name, "email": p.email} for p in people]
        out["pairs"] = [{"from": p.name, "to": by_id[p.giftee_id].name}
                        for p in people if p.giftee_id in by_id]
    return jsonify(out)


@bp.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:60]
    email = (data.get("email") or "").strip().lower()[:120]
    if not name or not EMAIL.match(email):
        return jsonify(error="We need your name and a real email."), 400
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
        "Hi %s,\n\nYou're signed up for the CIS 1600 Secret Santa. When "
        "everyone's in, names get drawn and you'll get an email telling you "
        "who you're shopping for.\n\nMerry Christmas!\n" % name)).start()
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
            "    %s\n\nKeep it a secret!\n\nMerry Christmas!\n"
            % (p.name, by_id[p.giftee_id].name))
        if ok:
            p.emailed_at = datetime.utcnow()
            db.session.commit()
        print(("sent  " if ok else "FAILED") + "  %s <%s>" % (p.name, p.email))
