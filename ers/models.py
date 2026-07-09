"""Database models for Egyptian Rat Screw.

The ``users`` table is shared with the Ticket to Ride app - same physical table,
same columns - so one account works on both sites. This module maps only the
account/identity columns of ``users`` (TTR owns its own ``ttr_stats``); ERS keeps
its own per-user stats in ``ers_stats`` and its own games/players in ``ers_games``
/ ``ers_players``. ``create_all`` uses CREATE TABLE IF NOT EXISTS, so ERS never
clobbers the shared ``users`` table that TTR created.
"""

from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Shared account. Column definitions mirror TTR's ``users`` table exactly."""
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
        if self.ers is None:
            self.ers = ErsStats()
        return self.ers

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, pw)


class ErsStats(db.Model):
    """Egyptian Rat Screw stats, one row per user."""
    __tablename__ = "ers_stats"

    user_id            = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    elo                = db.Column(db.Integer, default=1000)
    games_played       = db.Column(db.Integer, default=0)
    games_won          = db.Column(db.Integer, default=0)
    turns_played       = db.Column(db.Integer, default=0)
    cards_flipped      = db.Column(db.Integer, default=0)  # cards played to the pile
    cards_won          = db.Column(db.Integer, default=0)  # cards picked up
    piles_won          = db.Column(db.Integer, default=0)
    slaps_won          = db.Column(db.Integer, default=0)
    false_slaps        = db.Column(db.Integer, default=0)
    slap_opportunities = db.Column(db.Integer, default=0)  # slappable piles they could reach
    reaction_ms_total  = db.Column(db.Integer, default=0)  # sum of winning-slap reaction times
    reaction_samples   = db.Column(db.Integer, default=0)
    fastest_slap_ms    = db.Column(db.Integer, nullable=True)
    best_place         = db.Column(db.Integer, nullable=True)  # 1 = a win

    user = db.relationship("User", backref=db.backref("ers", uselist=False,
                                                       cascade="all, delete-orphan"))

    @property
    def elo_tier(self):
        e = self.elo or 1000
        if e >= 1400: return "Rat King"
        if e >= 1250: return "Card Shark"
        if e >= 1100: return "Sharp"
        if e >= 1000: return "Dealer"
        if e >= 800:  return "Shuffler"
        return "Greenhorn"

    @property
    def win_rate(self):
        gp = self.games_played or 0
        return round(100 * (self.games_won or 0) / gp) if gp else 0

    @property
    def slap_accuracy(self):
        """Won slaps as a share of all slap attempts (won + false)."""
        total = (self.slaps_won or 0) + (self.false_slaps or 0)
        return round(100 * (self.slaps_won or 0) / total) if total else 0

    @property
    def slap_conversion(self):
        """Won slaps as a share of slappable piles you had a chance at."""
        opp = self.slap_opportunities or 0
        return round(100 * (self.slaps_won or 0) / opp) if opp else 0

    @property
    def avg_reaction_ms(self):
        n = self.reaction_samples or 0
        return round((self.reaction_ms_total or 0) / n) if n else None


class ErsGame(db.Model):
    __tablename__ = "ers_games"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="waiting")  # waiting | playing | ended
    max_players = db.Column(db.Integer, default=6)
    is_private = db.Column(db.Boolean, default=False)
    passcode = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, nullable=True)

    state_json = db.Column(db.Text, default="{}")
    # Full chronological replay: every flip (pid, card, ts), slap (valid, reasons,
    # reaction_ms, ts), pile win, elimination, start/end. Server timestamps in ms.
    events_json = db.Column(db.Text, default="[]")

    players = db.relationship("ErsPlayer", backref="game", lazy=True,
                              order_by="ErsPlayer.seat_order")

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


class ErsPlayer(db.Model):
    __tablename__ = "ers_players"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("ers_games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    session_key = db.Column(db.String(64), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    seat_order = db.Column(db.Integer, default=0)
    is_host = db.Column(db.Boolean, default=False)
    is_bot = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    linked_user = db.relationship("User", foreign_keys="ErsPlayer.user_id", lazy="select")

    @property
    def pid(self):
        """Stable player id used inside the game state (bots included)."""
        return f"p{self.id}"

    def to_dict(self):
        elo = None
        if self.linked_user and self.linked_user.ers:
            elo = self.linked_user.ers.elo
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "color": self.color,
            "seat_order": self.seat_order,
            "is_host": self.is_host,
            "is_bot": self.is_bot,
            "elo": elo,
        }


class ErsSlap(db.Model):
    """One row per slap attempt, for easy analysis (e.g. a reaction-time
    distribution: SELECT reaction_ms FROM ers_slaps WHERE valid AND reaction_ms).
    The full move-by-move replay lives in ErsGame.events_json."""
    __tablename__ = "ers_slaps"

    id          = db.Column(db.Integer, primary_key=True)
    game_code   = db.Column(db.String(6), index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    pid         = db.Column(db.String(8))
    name        = db.Column(db.String(50))
    valid       = db.Column(db.Boolean, default=False, index=True)
    reasons     = db.Column(db.String(80))
    reaction_ms = db.Column(db.Integer, nullable=True)
    cards       = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)
