"""Database models for King of Tokyo.

The ``users`` table is shared with Ticket to Ride and Egyptian Rat Screw - same
physical table, same columns - so one account works across every game at
cgovind.com. This module maps only the account/identity columns of ``users``;
King of Tokyo keeps its own per-user stats in ``kot_stats`` and its own
games/players in ``kot_games`` / ``kot_players``. ``create_all`` uses CREATE
TABLE IF NOT EXISTS, so KoT never clobbers the shared ``users`` table.
"""

from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Shared account. Column definitions mirror TTR/ERS's ``users`` table exactly."""
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

    def _ensure_stats(self):
        if self.kot is None:
            self.kot = KotStats()
        return self.kot

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, pw)

    @property
    def display(self):
        """What to call this person on screen - here, and on every other game.

        The username is the login and the address of their profile, so it never
        changes; the display name is the one they chose, and it is what a
        lobby, a table and a leaderboard all show.
        """
        p = self.profile
        return p.display_name if p and p.display_name else self.username

    @property
    def flag_path(self):
        return self.profile.flag_path if self.profile else None



class UserProfile(db.Model):
    """The shared profile: who this person is across all four games.

    Owned by the accounts pages at cgovind.com/accounts (``accounts/models.py``
    in the website repo), and mapped here read-only for the two things a game
    draws: the display name and the flag. Same physical table, same columns,
    same convention as ``User`` above - ``create_all`` is CREATE TABLE IF NOT
    EXISTS, so whichever of the five services starts first makes it and the
    rest find it.

    Every column is optional and the row itself is optional: it appears the
    first time somebody saves something on their profile, so ``user.profile``
    is ``None`` for most accounts and both helpers on ``User`` cope with that.
    """
    __tablename__ = "user_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    display_name = db.Column(db.String(30), nullable=True)
    display_name_lc = db.Column(db.String(30), unique=True, index=True, nullable=True)
    avatar = db.Column(db.String(64), nullable=True)
    country = db.Column(db.String(2), nullable=True)
    us_state = db.Column(db.String(2), nullable=True)
    flag_pref = db.Column(db.String(8), default="country")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("profile", uselist=False,
                                                      cascade="all, delete-orphan"))

    @property
    def flag_path(self):
        """Site-relative path of the flag this profile flies, or None.

        Just string formatting: the flag art lives on the main site and the
        list of which codes exist lives with the picker that validates them, so
        a game does not need either - it renders what was stored. A state flag
        is only flown by somebody in the US who asked for one, which is checked
        here as well as there, so a stale ``flag_pref`` left over from a move
        cannot fly the wrong flag.
        """
        if self.country == "us" and self.flag_pref == "state" and self.us_state:
            return "/assets/flags/us/%s.png" % self.us_state.lower()
        if self.country:
            return "/assets/flags/country/%s.svg" % self.country.lower()
        return None


class KotStats(db.Model):
    """King of Tokyo stats, one row per user."""
    __tablename__ = "kot_stats"

    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    elo           = db.Column(db.Integer, default=1000)
    games_played  = db.Column(db.Integer, default=0)
    games_won     = db.Column(db.Integer, default=0)
    vp_scored     = db.Column(db.Integer, default=0)   # total victory points across games
    damage_dealt  = db.Column(db.Integer, default=0)
    monsters_koed = db.Column(db.Integer, default=0)   # monsters you dealt the killing blow to
    tokyo_turns   = db.Column(db.Integer, default=0)   # turns started while holding Tokyo
    cards_bought  = db.Column(db.Integer, default=0)
    best_place    = db.Column(db.Integer, nullable=True)  # 1 = a win
    highest_vp    = db.Column(db.Integer, default=0)   # most VP held in a single game

    user = db.relationship("User", backref=db.backref("kot", uselist=False,
                                                       cascade="all, delete-orphan"))

    @property
    def elo_tier(self):
        e = self.elo or 1000
        if e >= 1400: return "Kaiju King"
        if e >= 1250: return "City Wrecker"
        if e >= 1100: return "Brawler"
        if e >= 1000: return "Monster"
        if e >= 800:  return "Lizard"
        return "Newt"

    @property
    def win_rate(self):
        gp = self.games_played or 0
        return round(100 * (self.games_won or 0) / gp) if gp else 0

    @property
    def avg_vp(self):
        gp = self.games_played or 0
        return round((self.vp_scored or 0) / gp, 1) if gp else 0


class KotGame(db.Model):
    __tablename__ = "kot_games"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="waiting")  # waiting | playing | ended
    max_players = db.Column(db.Integer, default=4)
    is_private = db.Column(db.Boolean, default=False)
    passcode = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, nullable=True)

    state_json = db.Column(db.Text, default="{}")
    # Full chronological replay: every roll, resolve, attack, Tokyo move, buy,
    # elimination, start/end. Server timestamps in ms.
    events_json = db.Column(db.Text, default="[]")

    players = db.relationship("KotPlayer", backref="game", lazy=True,
                              order_by="KotPlayer.seat_order")

    @property
    def state(self):
        return json.loads(self.state_json or "{}")

    @state.setter
    def state(self, value):
        self.state_json = json.dumps(value)

    def to_lobby_dict(self):
        return {
            "code": self.code,
            "status": self.status,
            "max_players": self.max_players,
            "is_private": self.is_private,
            "player_count": len(self.players),
            "players": [p.to_dict() for p in self.players],
        }


class KotPlayer(db.Model):
    __tablename__ = "kot_players"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("kot_games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    session_key = db.Column(db.String(64), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    monster = db.Column(db.String(30), nullable=False)   # display monster name
    seat_order = db.Column(db.Integer, default=0)
    is_host = db.Column(db.Boolean, default=False)
    is_bot = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    linked_user = db.relationship("User", foreign_keys="KotPlayer.user_id", lazy="select")

    @property
    def pid(self):
        """Stable player id used inside the game state."""
        return f"p{self.id}"

    def to_dict(self):
        elo = None
        if self.linked_user and self.linked_user.kot:
            elo = self.linked_user.kot.elo
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "color": self.color,
            "monster": self.monster,
            "seat_order": self.seat_order,
            "is_host": self.is_host,
            "is_bot": self.is_bot,
            "elo": elo,
        }
