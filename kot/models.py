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
