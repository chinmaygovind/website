"""Database models for Drive.

The ``users`` table is shared with Ticket to Ride, Egyptian Rat Screw and King
of Tokyo - same physical table, same columns - so one account works across
every game at cgovind.com. This module maps only the account/identity columns of
``users``; Drive keeps its own per-user stats in ``drive_stats``, its best times
in ``drive_times``, its attempt counts in ``drive_starts``, what each car looks
like in ``drive_garage``, the two settings that follow an account in
``drive_prefs`` and its lobbies in ``drive_games`` / ``drive_players``.
``create_all`` uses CREATE TABLE IF NOT EXISTS, so Drive never clobbers the
shared ``users`` table.

Note what is *not* here: live race state. A race ticks twenty times a second, so
positions live in memory in ``app.py`` (one eventlet worker, same as the other
games) and only the finished result is written back.
"""

from datetime import datetime
import json
import os

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    """WAL and a busy timeout, on every connection anything here opens.

    Here rather than in ``app.py`` because the anti-cheat runs in a second
    process (``verify.py``) that writes to the same file and never imports
    ``app``. WAL is a property of the database and would have been set already;
    **the busy timeout is per connection**, so without this the verifier's write
    would fail outright the moment it landed at the same time as a request's,
    instead of waiting the five seconds that makes two writers a non-event.
    """
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
    except Exception:
        pass


def database_url():
    """Which database Drive uses, resolved the one way.

    Here rather than in ``app.py`` because ``verify.py`` runs in a process of its
    own and has to reach the *same* file. Two copies of this that drifted would
    not fail: they would quietly verify laps in a database nobody is reading.
    """
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        shared = os.path.join(os.path.dirname(__file__), "..", "ttr",
                              "instance", "tickettoride.db")
        url = "sqlite:///" + os.path.abspath(shared)
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    return url


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


class DrivePortalUser(db.Model):
    """Which CrazyGames player is which cgovind.com account.

    **Drive's table, not a column on ``users``.** ``google_id`` sits on the
    shared row and it would have been the obvious place to put a
    ``crazygames_id`` beside it - but that row is defined five times, once per
    service, and adding a column means editing all five copies, moving the drift
    tests, and ALTERing the live database by hand. A portal is something *Drive*
    is submitted to; the account it lands on is an ordinary shared account that
    the other four games can use without ever knowing where it came from. So the
    knowledge lives here, on the one side that has it.

    ``portal`` is a slug rather than a flag so a second portal costs a row and
    not a schema. The two of them are the key together, since two portals will
    happily hand out the same id for different people.

    The three ``last_`` columns are a cache of what the portal last told us, and
    they are what keeps `_sync_profile` from doing two indexed lookups and a
    picture download on every page load that changed nothing.
    """
    __tablename__ = "drive_portal_users"

    portal         = db.Column(db.String(16), primary_key=True)
    portal_user_id = db.Column(db.String(64), primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"),
                               nullable=False, index=True)
    last_username  = db.Column(db.String(30), nullable=True)
    last_avatar_url = db.Column(db.String(512), nullable=True)
    last_seen      = db.Column(db.DateTime, default=datetime.utcnow)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


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


class DriveRunCheck(db.Model):
    """A lap fast enough to be re-driven on the server before it goes on the board.

    **The lap lives here until it passes, rather than in ``drive_times`` with a
    flag on it.** `drive_times` keeps one row per player per track and a better
    run overwrites it wholesale, ghost and all - so storing first and reverting
    on a fail is not available: the time it overwrote is gone. Holding it here
    instead means the public board, the record, the ghost and everybody's rank
    are simply untouched by a lap that has not been checked, with no read path
    anywhere having to remember to exclude one.

    Its own table for the reason ``drive_starts`` and ``drive_races`` are:
    ``create_all`` makes tables and not columns, so it arrives on the live
    database by itself where a column on ``drive_times`` would need a migration
    over SSH.

    **The absence of a row means verified**, which is what grandfathers the 82
    laps that were on the board before any of this existed. They carry no input
    stream and never can - nothing recorded one - and all 82 measure clean under
    `tools/audit_times.py`.

    ``status`` is pending -> pass | fail | error. ``error`` is the verifier
    falling over rather than the lap being wrong, and it is deliberately not
    ``fail``: a missing quickjs or a bad deploy must not be able to throw
    somebody's record away. ``applied_at`` is when `app.py` acted on the
    verdict, which is a second step because the verifier runs in another process
    and only ever writes its own row.
    """
    __tablename__ = "drive_run_checks"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    track       = db.Column(db.String(32), nullable=False, index=True)
    time_ms     = db.Column(db.Integer, nullable=False)
    splits_json = db.Column(db.Text, default="[]")
    ghost       = db.Column(db.Text, nullable=True)
    evidence    = db.Column(db.Text, nullable=True)     # runcheck.pack_verify
    status      = db.Column(db.String(10), default="pending", index=True)
    reason      = db.Column(db.String(200), nullable=True)
    stats_json  = db.Column(db.Text, default="{}")
    # Set when this row became the player's stored time, so a verdict is acted
    # on exactly once however many times the board is read.
    drive_time_id = db.Column(db.Integer, nullable=True)
    queued_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    checked_at  = db.Column(db.DateTime, nullable=True)
    applied_at  = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", lazy="select")

    @property
    def splits(self):
        try:
            return json.loads(self.splits_json or "[]")
        except Exception:
            return []

    @property
    def stats(self):
        try:
            return json.loads(self.stats_json or "{}")
        except Exception:
            return {}


class DriveRace(db.Model):
    """One finished race, with every car's replay - so it can be watched again.

    Deliberately not part of ``drive_games``. A lobby is deleted the moment it
    empties or goes idle, taking its ``results_json`` with it, which is right
    for a room and wrong for a race: the whole point of a replay is that it is
    still there tomorrow and the link to it still works. Its own table also
    means ``create_all`` brings it into being on the live database with no
    migration, the same reason ``drive_starts`` is a table.

    ``cars_json`` is one entry per car - name, colour, finishing time - each
    with a ``ghost`` packed exactly the way a lap's ghost is packed, at the
    same rate and with the same flag byte. So a replay is not a new format,
    it is several ghosts that share a clock: frame *n* of every car in here is
    the same instant, ``n / hz`` seconds after the lights went out.
    """
    __tablename__ = "drive_races"

    id         = db.Column(db.Integer, primary_key=True)
    code       = db.Column(db.String(6), nullable=False, index=True)
    track      = db.Column(db.String(32), nullable=False, index=True)
    hz         = db.Column(db.Integer, default=15)
    ms         = db.Column(db.Integer, default=0)          # how long it ran
    why        = db.Column(db.String(32), nullable=True)   # how it ended
    cars_json  = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def cars(self):
        try:
            return json.loads(self.cars_json or "[]")
        except Exception:
            return []


class DriveCheatFlag(db.Model):
    """A car whose race stopped being rated, and why.

    The verdict itself is **silent**: a flagged car keeps its place in the
    standings and nobody in the room is told anything. What it loses is the
    rating - ``_rate_race`` skips it exactly the way it already skips a guest -
    and that is the whole of the punishment on purpose. Announcing it would put
    the server in the middle of an argument it cannot referee, on evidence that
    is deliberately calibrated to be wrong in the harmless direction; kicking on
    it would let a false positive end somebody's afternoon.

    So the finding goes here instead, where a person can look at it. There is no
    admin page yet and no read path in the app at all - this table is written
    and never queried, which is the intended state until there is something to
    read it with. ``reasons_json`` keeps the tally per rule rather than a single
    verdict string, because the useful question of a row like this is always
    *which* check fired and how often: twelve of one thing is a bad connection
    finding a soft edge, hundreds of one thing is somebody's build of the game.

    Its own table for the reason ``drive_starts`` and ``drive_races`` are: a
    live database gets it from ``create_all`` with no migration.
    """
    __tablename__ = "drive_cheat_flags"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"),
                             nullable=True, index=True)
    name         = db.Column(db.String(32), nullable=False)   # guests have no user_id
    code         = db.Column(db.String(6), nullable=False, index=True)
    race_id      = db.Column(db.Integer, nullable=True)       # the replay, if one was kept
    track        = db.Column(db.String(32), nullable=False)
    phase        = db.Column(db.String(16), nullable=False)   # what it was caught in
    strikes      = db.Column(db.Integer, default=0)
    reasons_json = db.Column(db.Text, default="{}")
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def reasons(self):
        try:
            return json.loads(self.reasons_json or "{}")
        except Exception:
            return {}


class DriveGarage(db.Model):
    """What one account's car looks like, and what it has earned the right to.

    Its own table for the reason ``drive_starts`` and ``drive_races`` are:
    ``create_all`` makes tables and not columns, so a new table arrives on the
    live database by itself where a new column on ``drive_stats`` would need a
    hand migration over SSH.

    ``livery_json`` holds **only the slots that differ from the defaults** (see
    ``garage.dumps``), which keeps a row small and, more usefully, means changing
    a default later moves the car of everybody who never touched that slot -
    which is what a default is for. A missing row is therefore not a special
    case: it is the same thing as a row full of defaults, and both render exactly
    the car Drive drew before any of this existed.

    ``earned_json`` is deliberately a **second column rather than a key in the
    blob**, because the two are different kinds of fact. The livery is what
    somebody asked for and the client sends it; the earns are what the server has
    decided about them. Folding a fact into a blob the client POSTs is precisely
    how a gated item gets worn by somebody who has not earned it. Only the
    record badge is ever written here - the other three gates are recomputed from
    counters that cannot go down, and storing those would be a second copy of
    something the database already knows.
    """
    __tablename__ = "drive_garage"

    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    livery_json = db.Column(db.Text, default="{}")
    earned_json = db.Column(db.Text, default="[]")
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("garage", uselist=False,
                                                      cascade="all, delete-orphan"))

    @property
    def earned(self):
        try:
            got = json.loads(self.earned_json or "[]")
            return set(got) if isinstance(got, list) else set()
        except Exception:
            return set()


class DrivePrefs(db.Model):
    """The settings that follow the account rather than the browser.

    Everything in the settings sheet is remembered in ``localStorage``, which is
    the right store for it: Drive is playable with no account at all, and a
    per-user table would leave every guest without a memory. This table is the
    other half - **for somebody logged in, two of those settings follow them**
    instead of staying on the machine they last drove on. Which lap the splits
    are measured against and whether the ghost car is drawn are the two, because
    they are the two that change how the road looks, and having them reset by
    walking from a time trial into a room is the complaint that put this here.

    One JSON column rather than a column per setting, and that is the same
    reason ``drive_garage`` is its own table: ``create_all`` makes tables and not
    columns, so a third setting added to a blob arrives on the live database by
    itself where a third column would need a hand migration over SSH.

    **A missing row is not a special case.** It means "nothing chosen yet", which
    is exactly what an account that has never opened the sheet should get: the
    defaults, from the same code a guest runs.
    """
    __tablename__ = "drive_prefs"

    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    prefs_json = db.Column(db.Text, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("drive_prefs", uselist=False,
                                                      cascade="all, delete-orphan"))

    @property
    def prefs(self):
        try:
            got = json.loads(self.prefs_json or "{}")
            return got if isinstance(got, dict) else {}
        except Exception:
            return {}


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
    # A bot is an ordinary seat with nobody behind it - see `botsim`. It has no
    # `user_id`, which is what makes it invisible to ELO and to the win and
    # podium tallies by construction rather than by remembering to exclude it.
    is_bot = db.Column(db.Boolean, default=False, index=True)
    # Which of `bots.LEVELS` it drives at. Null for a person.
    bot_level = db.Column(db.String(10), nullable=True)

    linked_user = db.relationship("User", foreign_keys="DrivePlayer.user_id", lazy="select")

    @property
    def pid(self):
        """Stable player id used inside the live race state."""
        return f"p{self.id}"

    def to_dict(self, livery=None):
        """The seat, as the room sees it.

        ``livery`` is handed in rather than read off ``linked_user`` here,
        because working it out means applying the gates and this module must not
        import ``garage`` - ``garage`` imports models, and the cycle would be
        real. The caller in ``app.py`` has the session anyway, and it computes
        the record holders once for the whole roster rather than once per seat.

        ``None`` is a car with no livery, which is not a broken one: the renderer
        falls back to ``color`` and draws exactly the car it always did.

        **``color`` is answered from the livery when there is one**, and that is
        not tidiness. The car on the road is drawn from ``livery``, but the
        minimap dot, the standings row, the chat name and the *nameplate over
        your own car* are all drawn from ``color`` - so with the column reported
        raw, somebody who had chosen a colour got it on the bodywork and the
        hashed one on everything that points at them. A nametag in a different
        colour from the car under it is worse than either colour on its own. The
        column stays as the seed and the fallback: it is what a guest has, and
        what a seat joined before any of this existed has.
        """
        elo = None
        if self.linked_user and self.linked_user.drive:
            elo = self.linked_user.drive.elo
        return {
            "id": self.id,
            "pid": self.pid,
            "name": self.name,
            "color": (livery or {}).get("body") or self.color,
            "livery": livery,
            "seat_order": self.seat_order,
            "is_host": self.is_host,
            # A bot has no account, so it reads as a guest to everything that
            # asks - which is right for the rating and wrong for the roster,
            # where "GUEST" next to a car nobody is driving is a lie. Hence the
            # two fields: `guest` stays what it was, and the room tags a bot
            # with the level it drives at.
            "guest": self.user_id is None and not self.is_bot,
            "bot": bool(self.is_bot),
            "level": self.bot_level if self.is_bot else None,
            "elo": elo,
        }


class DriveUserTrack(db.Model):
    """A track somebody built, as a row.

    **A user track is not a second kind of track.** The row holds the authored
    *document* - the moves, the palette, the scenery - and `tracks.moves.build`
    replays it through the same `Builder` that builds Spa, so everything
    downstream (medals, pole side, the checkpoint ceiling, the ideal lap, ghosts,
    the anti-cheat) is the code that already exists. Nothing here is a parallel
    implementation of a track; it is a different way of *storing* one.

    No user Python and no user JavaScript is ever stored here to be run. `doc`
    is data: a move list validated against `tracks.moves.SPEC`, a palette
    validated against `tracks.look.KNOWN`, and - for a track whose author wrote
    scenery in code - the *baked geometry* that code produced in a sandbox in
    their browser, never the code itself. The code is kept for people to read
    (see `source`), not for anything to execute.

    One JSON column for the document rather than a column per field, for the
    reason `drive_prefs` gives: the shape of a document will change, and a blob
    changes with it while a column needs `models.ensure_columns` or a hand
    migration. What *is* a column is only what a query needs to filter or sort
    on without parsing every row.

    Statuses, and the one rule that matters:

    ``draft``   the author's, on an unlisted link. Not in the pool.
    ``queued``  submitted. Still only reachable by its author and by Chinmay.
    ``live``    approved. `tracks.get` resolves it, and everything works.
    ``hidden``  was live, taken down. The row and its board are kept.

    **What was approved is what is live.** A cosmetic edit saves onto a live
    track; anything that changes the *collider* wipes the board and sends it back
    to ``queued``, because every time on that board was driven against the old
    one - the same rule `tests/test_scenery.py` states in its own failure
    message. `geom_hash` is what makes that a fact rather than a guess.
    """
    __tablename__ = "drive_user_tracks"

    id         = db.Column(db.Integer, primary_key=True)
    # The slug is in the URL (`/solo/<slug>`), on every saved time and in every
    # share link, so it is unique across user tracks *and* reserved against the
    # pool - see `tracks.slug_is_available`. It can never change.
    slug       = db.Column(db.String(60), unique=True, nullable=False, index=True)
    # Null for the starting shapes shipped with the editor, which belong to
    # nobody and cannot be edited or published by the player who forks one.
    author_id  = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    status     = db.Column(db.String(10), default="draft", nullable=False,
                           index=True)

    # Denormalised out of the document because the gallery sorts and filters on
    # them, and parsing every row's JSON to list a page would be silly.
    name       = db.Column(db.String(60), nullable=False)
    difficulty = db.Column(db.Integer, default=3, nullable=False)

    doc_json   = db.Column(db.Text, nullable=False, default="{}")
    # The scenery source, when its author wrote code rather than dropping
    # placements. Stored to be *read* - published with the track when it goes
    # live - and never executed anywhere. What executes is the baked geometry in
    # `doc`, which the browser produced under sandbox and the server validated
    # as numbers.
    source     = db.Column(db.Text)

    # A fingerprint of the built ribbon and its collider. See
    # `tracks.moves.fingerprint`. Two rows with the same hash are the same road,
    # so a board is only ever wiped when the road actually moved.
    geom_hash  = db.Column(db.String(40), index=True)
    # The slug this was forked from, pool track or user track. Kept forever: the
    # card says "based on Spa-Francorchamps" for as long as the track exists.
    forked_from = db.Column(db.String(60))
    review_note = db.Column(db.Text)
    # The layout from above, as an SVG path. Derived from the built ribbon and
    # stored *here* rather than computed per card, because a gallery of sixty
    # cards must not replay sixty documents to draw itself - and it is written
    # in the one place the ribbon is already built, beside `geom_hash`, so it
    # cannot drift from the road it is a picture of.
    plan_path  = db.Column(db.Text)
    # Everything you can *see*, which is a different question from the road. A
    # swapped-out city does not invalidate a lap time, so the board survives -
    # but what was approved was a particular city, so it still comes back to the
    # queue. See `tracks.moves.look_fingerprint`.
    look_hash  = db.Column(db.String(40))

    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow)
    queued_at    = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)

    author = db.relationship("User", backref=db.backref("drive_user_tracks",
                                                        lazy="dynamic"))

    @property
    def doc(self):
        """The document, or `{}` - never an exception.

        A row whose JSON cannot be parsed is a row that fails to load, and the
        pool's answer to that is `tracks.BROKEN`: leave it out, say so, do not
        take anything else down with it.
        """
        try:
            got = json.loads(self.doc_json or "{}")
            return got if isinstance(got, dict) else {}
        except Exception:
            return {}

    @property
    def is_live(self):
        return self.status == "live"


# ---------------------------------------------------------------------------
# The one migration
# ---------------------------------------------------------------------------

# Every other new thing in this file arrived as a whole **table**, because
# ``create_all`` is ``CREATE TABLE IF NOT EXISTS`` and brings one into being on
# the live database by itself - and that is the convention here precisely so
# that nothing needs a hand-run migration over SSH.
#
# ``drive_players.is_bot`` could not be a table. A bot *is* a seat: it has to be
# in the roster, on the grid, in the standings and in the stored replay, and all
# four of those read ``game.players``. A parallel table would mean every one of
# them learning about a second kind of player, which is four places to forget.
#
# So it is two columns and this is what adds them. Done in code rather than by
# hand on the box for one reason: a mapped column that is missing from the table
# makes **every** query against ``drive_players`` fail, so a deploy where
# somebody forgot the ALTER is not a feature that does not work, it is Drive
# down. Idempotent, dialect-agnostic enough for the SQLite this actually runs
# on, and it costs one ``PRAGMA`` at boot.
_ADDED = {
    "drive_players": [
        ("is_bot", "BOOLEAN DEFAULT 0"),
        ("bot_level", "VARCHAR(10)"),
    ],
    # `create_all` makes a new table with every column, so this list is only for
    # columns added to a table that already exists on the box.
    "drive_user_tracks": [
        ("plan_path", "TEXT"),
        ("look_hash", "VARCHAR(40)"),
    ],
}


def ensure_columns(app_db, log=None):
    """Add any mapped column the live table does not have yet.

    Loud on failure and does not raise: the next query will fail anyway and say
    so far more precisely than a boot-time traceback with no context would.
    """
    from sqlalchemy import inspect, text
    try:
        insp = inspect(app_db.engine)
        tables = set(insp.get_table_names())
    except Exception as e:                                # pragma: no cover
        if log:
            log.warning("could not inspect the database for columns: %s", e)
        return
    for table, cols in _ADDED.items():
        if table not in tables:
            continue                                      # create_all made it
        have = {c["name"] for c in insp.get_columns(table)}
        for name, decl in cols:
            if name in have:
                continue
            try:
                with app_db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE %s ADD COLUMN %s %s"
                                      % (table, name, decl)))
                if log:
                    log.warning("added %s.%s to the live database", table, name)
            except Exception as e:                        # pragma: no cover
                if log:
                    log.error("could not add %s.%s (%s) - queries against %s "
                              "will fail until it exists", table, name, e, table)
