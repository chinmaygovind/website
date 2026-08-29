"""Where the trainer keeps things.

The ``users`` table is shared with Ticket to Ride, Egyptian Rat Screw, King of
Tokyo and Drive - same physical table, same columns - so one cgovind.com account
sits down here too. This module maps only the identity columns of it and
``create_all`` uses CREATE TABLE IF NOT EXISTS, so nothing here can clobber the
account other games depend on.

Six tables of its own, and the split between the first two is the interesting
one:

``gto_tables``
    **The live table, as JSON.** Whose seat this is, everyone's stack, the
    button, the bounty streaks, the hand in progress. It is in the database
    rather than in a worker's memory for two reasons: gunicorn runs three sync
    workers and your next request may not reach the one holding your table, and
    a deploy restarts the service - which with in-memory state would end every
    session mid-hand every time anything ships.

``gto_sessions`` / ``gto_hands`` / ``gto_decisions``
    The permanent record. One row per sit-down, one per hand, one per decision
    you were asked to make, with the mark the review gave it. This is what every
    statistic is computed from, so it stores the *inputs* - what you held, what
    was in the pot, what you did - and not just the verdict, because a scoring
    change should be able to re-mark old hands rather than orphan them.

``gto_prefs``
    The gear menu, per account: stakes, buy-in, whether the bounty is on, and
    any tuning done to the opponents. Follows you between devices.

``gto_coach``
    One row per decision that has been sent to a model for a second opinion: the
    answer, and what it used. See ``coach.py`` for why it is a second opinion
    rather than a summary, and why the usage is worth storing.

Money is **integer cents** everywhere, as it is in the engine. A trainer that
reports edges of a hundredth of a big blind cannot afford to hold them in
floats.
"""

from datetime import datetime
import json
import os
import time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _rec):
    """WAL and a busy timeout on every connection, as the other services do.

    The busy timeout is **per connection**, so without it a write landing at the
    same moment as another service's fails outright instead of waiting the five
    seconds that makes two writers a non-event. Five services share this file.
    """
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
    except Exception:
        pass


def database_url():
    """Which database this uses, resolved the same way every other service does."""
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
    """The shared account. Columns mirror the other services' ``users`` table."""
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


class GtoTable(db.Model):
    """One live table, serialised. At most one per player."""
    __tablename__ = "gto_tables"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True,
                        nullable=True)
    #: Signed-out visitors get a table too, keyed on their browser session, so
    #: somebody can try it without an account. Nothing about them is kept.
    session_key = db.Column(db.String(64), index=True, nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey("gto_sessions.id"),
                           nullable=True)
    state_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, index=True)

    @property
    def state(self):
        return json.loads(self.state_json or "{}")

    @state.setter
    def state(self, value):
        self.state_json = json.dumps(value)


class GtoSession(db.Model):
    """One sit-down: from taking a seat to walking away."""
    __tablename__ = "gto_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True,
                        nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    sb = db.Column(db.Integer, default=25)
    bb = db.Column(db.Integer, default=25)
    buyin = db.Column(db.Integer, default=5000)
    seats = db.Column(db.Integer, default=6)
    bounty_on = db.Column(db.Boolean, default=True)

    hands = db.Column(db.Integer, default=0)
    bought_in = db.Column(db.Integer, default=0)
    #: Chips in front of the hero right now. Profit is this minus ``bought_in``,
    #: which is the only honest way to state it once anybody has rebought.
    stack = db.Column(db.Integer, default=0)
    bounty_cents = db.Column(db.Integer, default=0)

    @property
    def profit(self):
        return (self.stack or 0) - (self.bought_in or 0)


class GtoHand(db.Model):
    """One hand, from the hero's point of view."""
    __tablename__ = "gto_hands"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("gto_sessions.id"),
                           index=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True,
                        nullable=True)
    hand_no = db.Column(db.Integer, default=0)
    played_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    position = db.Column(db.String(4))
    hole = db.Column(db.String(8))
    board = db.Column(db.String(16))
    hand_class = db.Column(db.String(4), index=True)

    result_cents = db.Column(db.Integer, default=0)
    #: The same result with every all-in replaced by its equity. Over a few
    #: hundred hands this removes most of the variance that has nothing to do
    #: with how the hand was played, which is why it is the headline number.
    ev_cents = db.Column(db.Integer, default=0)
    bounty_cents = db.Column(db.Integer, default=0)

    vpip = db.Column(db.Boolean, default=False)
    pfr = db.Column(db.Boolean, default=False)
    three_bet = db.Column(db.Boolean, default=False)
    three_bet_chance = db.Column(db.Boolean, default=False)
    saw_flop = db.Column(db.Boolean, default=False)
    showdown = db.Column(db.Boolean, default=False)
    won_showdown = db.Column(db.Boolean, default=False)
    won = db.Column(db.Boolean, default=False)
    streak_after = db.Column(db.Integer, default=0)


class GtoDecision(db.Model):
    """One spot the hero was put in, and how it was marked.

    The *inputs* are stored, not only the verdict, so that a change to the
    scoring can re-mark old hands instead of orphaning them.
    """
    __tablename__ = "gto_decisions"

    id = db.Column(db.Integer, primary_key=True)
    hand_id = db.Column(db.Integer, db.ForeignKey("gto_hands.id"), index=True,
                        nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True,
                        nullable=True)

    street = db.Column(db.String(8), index=True)
    position = db.Column(db.String(4), index=True)
    hole = db.Column(db.String(8))
    board = db.Column(db.String(16))
    node = db.Column(db.String(24))
    pot = db.Column(db.Integer, default=0)
    to_call = db.Column(db.Integer, default=0)
    stack = db.Column(db.Integer, default=0)
    opponents = db.Column(db.Integer, default=1)
    streak = db.Column(db.Integer, default=0)
    #: Who the spot was against, but **only when there was exactly one person
    #: it could have been against**. Three-way, a mistake belongs to the
    #: situation rather than to any one of them, and pinning it on whoever
    #: happened to bet would put a number on the stats page that reads like
    #: evidence and is not.
    opponent = db.Column(db.String(32), index=True, nullable=True)

    action = db.Column(db.String(8))
    amount = db.Column(db.Integer, default=0)

    verdict = db.Column(db.String(12), index=True)
    loss_bb = db.Column(db.Float, nullable=True)
    headline = db.Column(db.Text)
    #: Every labelled line the review produced, kept whole so a hand can be
    #: reopened months later and read exactly as it was shown at the time.
    lines_json = db.Column(db.Text, default="[]")

    #: The spot as the engine saw it, with none of the above in it: the seats,
    #: the stacks, the betting. Written for ``coach.py``, which must be able to
    #: read a decision months later without reading anything this repo
    #: concluded about it. It is the *only* column here that is not an input to
    #: the marking, and it is a column rather than a table because it is one
    #: blob per decision that is read exactly when that decision is - see
    #: ``ensure_columns``, which is what puts it on the live database.
    context_json = db.Column(db.Text, nullable=True)

    @property
    def lines(self):
        return json.loads(self.lines_json or "[]")

    @property
    def context(self):
        return json.loads(self.context_json or "null")


class GtoPrefs(db.Model):
    """The gear menu, per account."""
    __tablename__ = "gto_prefs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True,
                        nullable=False)
    settings_json = db.Column(db.Text, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    @property
    def settings(self):
        return json.loads(self.settings_json or "{}")

    @settings.setter
    def settings(self, value):
        self.settings_json = json.dumps(value)


class GtoCoach(db.Model):
    """One decision explained by Claude, and the bill for it.

    One row per decision, ever: the answer to "why was that hand like that" does
    not change, so a second click reads this row rather than paying for the same
    paragraph twice. That cache is also the cheapest of the guards on a route
    that spends money - the others being the owner check and the two daily
    ceilings in ``coach``.

    **Cost is in micro-dollars**, not the integer cents money uses everywhere
    else here. An answer costs a few hundredths of a dollar; in cents most of
    them would round to zero and so would a day of them, which is the one thing
    a spend meter may not do.

    ``status`` exists because the call is made on a background thread - three
    sync workers and a request that blocks for half a minute is a third of the
    server gone - so the row is written ``pending``, the browser polls, and the
    thread fills the rest in. A worker restarted mid-call leaves a ``pending``
    row that nothing will ever finish, which is what ``started_at`` is for: the
    route treats an old one as abandoned and runs it again.
    """
    __tablename__ = "gto_coach"

    id = db.Column(db.Integer, primary_key=True)
    decision_id = db.Column(db.Integer, db.ForeignKey("gto_decisions.id"),
                            unique=True, index=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True,
                        nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    status = db.Column(db.String(8), default="pending", index=True)
    text = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)

    model = db.Column(db.String(40))
    effort = db.Column(db.String(8))
    ms = db.Column(db.Integer, default=0)

    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cache_read_tokens = db.Column(db.Integer, default=0)
    cache_creation_tokens = db.Column(db.Integer, default=0)
    cost_micros = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "decision_id": self.decision_id,
            "status": self.status,
            "text": self.text,
            "error": self.error,
            "model": self.model,
            "effort": self.effort,
            "ms": self.ms or 0,
            "input_tokens": self.input_tokens or 0,
            "output_tokens": self.output_tokens or 0,
            "cost_micros": self.cost_micros or 0,
        }


# ---------------------------------------------------------------------------
# The one migration
# ---------------------------------------------------------------------------

# Everything else new here has arrived as a whole **table**, because
# ``create_all`` is CREATE TABLE IF NOT EXISTS and brings one into being on the
# live database by itself - ``gto_coach`` above needs nothing doing to it.
#
# ``gto_decisions.context_json`` could not be a table without splitting one
# decision across two of them for no gain. So it is a column, and this is what
# adds it. In code rather than by hand over SSH for one reason: a mapped column
# that the live table does not have makes **every** query against
# ``gto_decisions`` fail, so a deploy where somebody forgot the ALTER is not a
# feature that does not work, it is the stats page and the review both down.
# Same arrangement, and the same reasoning, as ``drive/models.py``.
_ADDED = {
    "gto_decisions": [
        ("context_json", "TEXT"),
    ],
}


def ensure_schema(app_db, log=None):
    """Everything the database needs at boot, safe against three workers at once.

    ``create_all`` is a check-then-CREATE with a gap in the middle, and three
    sync workers import this module at the same instant. On the first boot after
    a **new table** is added they all look, they all see it missing, and they all
    issue the CREATE. One wins. The losers used to raise ``table gto_coach
    already exists``, which killed the worker, which halted the gunicorn master,
    and only systemd's automatic restart brought the service back - by which
    point the table existed and the second boot was clean.

    That is the worst shape a failure can take here: the deploy went green, the
    box had the right code, and the service was dead for seven seconds in
    between. It also only fires on the *first* boot after a schema change, so it
    cannot be reproduced by restarting afterwards and looks like a fluke.

    So the race is expected rather than guarded against: losing it means somebody
    else did the work, and the second attempt finds everything already there and
    does nothing. Anything that is *not* that race still raises.
    """
    from sqlalchemy.exc import OperationalError
    for attempt in (1, 2):
        try:
            app_db.create_all()
            break
        except OperationalError as e:
            if attempt == 2 or "already exists" not in str(e).lower():
                raise
            if log:
                log.warning("another worker created a table first, retrying: %s",
                            e.orig)
            time.sleep(0.25)
    ensure_columns(app_db, log=log)


def ensure_columns(app_db, log=None):
    """Add any mapped column the live table does not have yet.

    Loud on failure and does not raise: the next query fails anyway and says so
    far more precisely than a boot-time traceback with no context would.
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


DEFAULT_PREFS = {
    "sb": 25,
    "bb": 25,
    "buyin": 5000,
    "bounty_on": True,
    "seats": 0,            # 0 means "randomly five or six, like the real game"
    "auto_rebuy": False,
    "show_ranges": True,
    "review_after_each_hand": True,
    "bot_speed": 1.0,
    "four_colour_deck": False,
    "profiles": {},        # per-opponent tuning laid over the defaults
}
