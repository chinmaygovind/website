"""The shared account, and the one table this site adds to it.

``users`` is the account table every game already shares - Ticket to Ride,
Egyptian Rat Screw, King of Tokyo and Drive all map it, all with the same
columns, in their own ``models.py``. This module maps the identity columns of
that same physical table for the accounts pages, following the established
convention rather than inventing a shared package: five services already each
own their copy of ``User``, and a copy that drifts is easier to notice than an
import that quietly binds five processes together.

What is new here is ``user_profiles``: the display name, picture and flag that
belong to *the person* rather than to any one game. It is a new table and not
new columns on ``users`` for the reason Drive's ``drive_starts`` is:
``create_all`` creates whole tables and nothing else, so a new table lands on
the live database on its own where a new column would need a hand-run migration
across five services.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Shared account. Column definitions mirror TTR/ERS/KoT/Drive's ``users``."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    google_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    notify_new_game = db.Column(db.Boolean, default=False)
    is_bot = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, pw)

    @property
    def display(self):
        """What to call this person on screen.

        The username is permanent - it is the login and the profile URL - so
        the name everything *shows* is the profile's, and falls back to the
        username for the accounts that have never set one.
        """
        p = self.profile
        return (p.display_name if p and p.display_name else self.username)


class UserProfile(db.Model):
    """One row per user: who they are across all four games.

    Every column is optional. A profile row exists as soon as somebody touches
    their settings and not before, so ``user.profile`` is routinely ``None`` and
    every reader has to cope with that - which is why the display name, the flag
    and the picture are all read through helpers that take the user rather than
    the profile.
    """
    __tablename__ = "user_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)

    # The editable name, shown everywhere. `display_name_lc` is the same string
    # folded to lower case and carries the uniqueness constraint: two people
    # called "Chinmay" and "chinmay" on one leaderboard is exactly the
    # impersonation the constraint exists to stop, and SQLite's UNIQUE is
    # case-sensitive, so the folded copy is what gets indexed.
    display_name = db.Column(db.String(30), nullable=True)
    display_name_lc = db.Column(db.String(30), unique=True, index=True, nullable=True)

    # Filename under the avatar directory, stamped with a hash of the contents
    # (`7-9f3a1c2b.webp`) so that replacing a picture changes its URL and no
    # cache anywhere has to be persuaded to let go of the old one.
    avatar = db.Column(db.String(64), nullable=True)

    country = db.Column(db.String(2), nullable=True)     # ISO 3166-1 alpha-2
    us_state = db.Column(db.String(2), nullable=True)    # only meaningful if country == 'us'
    # Which flag to fly. Only ever 'state' for someone in the US who asked;
    # `places.flag_of` is what enforces that, so a stale value cannot leak.
    flag_pref = db.Column(db.String(8), default="country")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("profile", uselist=False,
                                                      cascade="all, delete-orphan"))

    @property
    def flag_path(self):
        """Site-relative path of the flag this profile flies, or None.

        The same property the four games have on their copy of this model, and
        it has to stay the same: they are the ones drawing it on a leaderboard,
        and a profile that previewed one flag while the boards showed another
        would be worse than no flag at all. ``places.flag_of`` is where the
        rule actually lives - this is the one-line way to ask it.
        """
        from . import places
        flag = places.flag_of(self.country, self.us_state,
                              self.flag_pref == "state")
        return flag[0] if flag else None
