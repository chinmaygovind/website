"""Database models for Drive.

The ``users`` table is shared with Ticket to Ride, Egyptian Rat Screw and King
of Tokyo - same physical table, same columns - so one account works across
every game at cgovind.com. This module maps only the account/identity columns of
``users``; Drive keeps its own per-user stats in ``drive_stats``, its best times
in ``drive_times``, its attempt counts in ``drive_starts`` and its lobbies in
``drive_games`` / ``drive_players``.
``create_all`` uses CREATE TABLE IF NOT EXISTS, so Drive never clobbers the
shared ``users`` table.

Note what is *not* here: live race state. A race ticks twenty times a second, so
positions live in memory in ``app.py`` (one eventlet worker, same as the other
games) and only the finished result is written back.
"""

from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Shared account. Column definitions mirror TTR/ERS/KoT's ``users`` table."""
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


class DriveStats(db.Model):
    """Drive stats, one row per user."""
    __tablename__ = "drive_stats"

    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    elo          = db.Column(db.Integer, default=1000)
    races        = db.Column(db.Integer, default=0)     # synced multiplayer races finished
    wins         = db.Column(db.Integer, default=0)
    podiums      = db.Column(db.Integer, default=0)
    runs         = db.Column(db.Integer, default=0)     # timed runs finished, solo or not
                                                        # (starts are per-track, in DriveStart)
    distance     = db.Column(db.Float, default=0.0)     # metres driven across every run
    drive_time   = db.Column(db.Float, default=0.0)     # seconds spent on a clock
    # The author medal is retired (see tuning.MEDAL_MULT); this column only ever
    # holds what was won while it existed, and shows up as golds.
    authors      = db.Column(db.Integer, default=0)
    golds        = db.Column(db.Integer, default=0)
    silvers      = db.Column(db.Integer, default=0)
    bronzes      = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("drive", uselist=False,
                                                      cascade="all, delete-orphan"))

    @property
    def elo_tier(self):
        e = self.elo or 1000
        if e >= 1400: return "Works Driver"
        if e >= 1250: return "Ace"
        if e >= 1100: return "Quick"
        if e >= 1000: return "Licensed"
        if e >= 850:  return "Learner"
        return "Cone Collector"

    @property
    def win_rate(self):
        r = self.races or 0
        return round(100 * (self.wins or 0) / r) if r else 0

    @property
    def medal_count(self):
        return (self.authors or 0) + (self.golds or 0) + (self.silvers or 0) + (self.bronzes or 0)


class DriveTime(db.Model):
    """One row per (user, track): their personal best and its ghost.

    Only the PB is kept - a better run overwrites the row, ghost and all - so
    the table stays one row per player per track no matter how much they grind.
    """
    __tablename__ = "drive_times"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    track      = db.Column(db.String(32), nullable=False, index=True)
    time_ms    = db.Column(db.Integer, nullable=False)
    medal      = db.Column(db.String(10), nullable=True)   # gold|silver|bronze|None
                                                           # (or a legacy "author")
    splits_json = db.Column(db.Text, default="[]")         # cumulative ms at each checkpoint
    # Quantised, zlib+base64 replay of the run. Raced against as the ghost car.
    ghost      = db.Column(db.Text, nullable=True)
    runs       = db.Column(db.Integer, default=1)          # attempts on this track
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", lazy="select")

    __table_args__ = (db.UniqueConstraint("user_id", "track", name="uq_drive_time_user_track"),)

    @property
    def splits(self):
        try:
            return json.loads(self.splits_json or "[]")
        except Exception:
            return []

    @property
    def medal_shown(self):
        """The medal to put on the screen, which is not always the stored one.

        Rows written while the author medal existed still say "author". It was
        strictly faster than gold, so every one of them is a gold too - showing
        them as such retires the medal from the whole site without rewriting
        anybody's history or taking a medal off them.
        """
        return "gold" if self.medal == "author" else self.medal


class DriveStart(db.Model):
    """One row per (user, track): how many runs they have *begun* there.

    A finish was always counted (``DriveTime.runs`` per track, ``DriveStats.runs``
    overall) and a start never was, which made every attempt that ended in the
    scenery invisible - on a hard track that is most of them, and the ratio of
    the two is the only number that says how hard a track actually is.

    Starts get their own table rather than a column on ``drive_stats`` or
    ``drive_times`` for two reasons. ``create_all`` creates whole tables and
    nothing else, so a new table arrives on a live database by itself where a
    new column would need a migration. And a start is not a time: you can begin
    a track fifty times without ever finishing one, so there is no
    ``drive_times`` row to keep the count in until you do - and that track is
    exactly the one whose start count is worth reading.

    Finishes are deliberately *not* duplicated here; the counters that already
    hold them keep holding them, history and all.
    """
    __tablename__ = "drive_starts"

    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    track      = db.Column(db.String(32), primary_key=True)
    starts     = db.Column(db.Integer, default=0, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class DriveGame(db.Model):
    __tablename__ = "drive_games"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="waiting")   # waiting | playing | ended
    track = db.Column(db.String(32), nullable=False, default="sunrise")
    max_players = db.Column(db.Integer, default=8)
    is_private = db.Column(db.Boolean, default=False)
    passcode = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, nullable=True)

    # Finished race standings, appended one entry per race run in this lobby.
    results_json = db.Column(db.Text, default="[]")

    players = db.relationship("DrivePlayer", backref="game", lazy=True,
                              order_by="DrivePlayer.seat_order")

    @property
    def results(self):
        try:
            return json.loads(self.results_json or "[]")
        except Exception:
            return []

    def add_result(self, entry):
        r = self.results
        r.append(entry)
        self.results_json = json.dumps(r)

    def to_lobby_dict(self):
        return {
            "code": self.code,
            "status": self.status,
            "track": self.track,
            "max_players": self.max_players,
            "is_private": self.is_private,
            "player_count": len(self.players),
            "players": [p.to_dict() for p in self.players],
        }


class DrivePlayer(db.Model):
    __tablename__ = "drive_players"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("drive_games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    session_key = db.Column(db.String(64), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    seat_order = db.Column(db.Integer, default=0)
    is_host = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    linked_user = db.relationship("User", foreign_keys="DrivePlayer.user_id", lazy="select")

    @property
    def pid(self):
        """Stable player id used inside the live race state."""
        return f"p{self.id}"

    def to_dict(self):
        elo = None
        if self.linked_user and self.linked_user.drive:
            elo = self.linked_user.drive.elo
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "color": self.color,
            "seat_order": self.seat_order,
            "is_host": self.is_host,
            "guest": self.user_id is None,
            "elo": elo,
        }
