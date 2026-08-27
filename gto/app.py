"""gto.cgovind.com - the trainer's web server.

**No lobby.** Opening the page puts you in the seat. The other four games at
cgovind.com are multiplayer and need somewhere to wait for people; this one has
five opponents who are always there, so a waiting room would be a page whose
only purpose is a button that says "begin".

**Plain synchronous Flask.** Nothing here pushes - every change of state is the
answer to a request the browser just made - so there is no eventlet and no
Socket.IO, unlike ers/kot/drive. Three sync gunicorn workers.

**The bots never sleep on the server.** Each bot action comes back with a
``delay`` in seconds and the browser paces them out. A server that slept nine
seconds for Bell's tank would hold one of three workers for nine seconds.

**The table lives in the database.** See ``models.GtoTable``: three workers and
a deploy that restarts the service both make in-memory state wrong.

**The opponents' photographs are of real people and this repo is public.** They
are gitignored, they live outside the tree in production (``GTO_AVATAR_DIR``,
defaulting to ``/home/ubuntu/gto-avatars`` - the same arrangement, and the same
reasoning, as ``accounts``' ``AVATAR_DIR``), and ``/avatars/<key>`` serves them
**only to Chinmay**. Everybody else plays the same five personalities under
invented names with drawn initials, which is ``profiles.STRANGERS``. The
tendencies are the interesting part and they are not private; the people are.
"""

import json
import os
import random
import uuid

from dotenv import load_dotenv
from flask import (
    Flask, abort, jsonify, redirect, render_template, request, send_from_directory,
    session,
)

import bots
import profiles
import review as review_module
import stats as stats_module
import table as table_module
import visits
from models import (
    DEFAULT_PREFS, GtoDecision, GtoHand, GtoPrefs, GtoSession, GtoTable, User,
    database_url, db,
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# The session cookie is shared across cgovind.com's subdomains, which is what
# makes one account work in all five games.
_cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
if _cookie_domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain
if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True

db.init_app(app)
with app.app_context():
    db.create_all()
    visits.ensure_tables(db)
visits.init_app(app, db, "gto")

MAIN_SITE_URL = os.environ.get("MAIN_SITE_URL", "https://cgovind.com").rstrip("/")

#: Outside the repository on purpose. A ``git reset --hard`` on the box must not
#: be able to touch these, and a public checkout must not contain them.
AVATAR_DIR = os.environ.get(
    "GTO_AVATAR_DIR",
    os.path.join(os.path.dirname(__file__), "avatars"))

#: Who sees the real names and faces. Everybody else gets ``profiles.STRANGERS``.
OWNERS = {n.strip().lower() for n in
          os.environ.get("GTO_OWNERS", "chinmay").split(",") if n.strip()}


# --------------------------------------------------------------- identity


def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def is_owner(user):
    return bool(user) and user.username.lower() in OWNERS


def session_key():
    if "gto_key" not in session:
        session["gto_key"] = str(uuid.uuid4())
    return session["gto_key"]


def hero_name(user):
    return user.username if user else "you"


# ------------------------------------------------------------ preferences


def load_prefs(user):
    settings = dict(DEFAULT_PREFS)
    if user:
        row = GtoPrefs.query.filter_by(user_id=user.id).first()
        if row:
            settings.update(row.settings)
    return settings


def save_prefs(user, incoming):
    """Only the keys that exist, only the types they should be.

    An unknown key from the settings panel is dropped rather than stored: this
    row is read straight into the table's constructor, so anything that gets in
    here gets to decide how the game is set up.
    """
    if not user:
        return load_prefs(None)
    row = GtoPrefs.query.filter_by(user_id=user.id).first()
    if not row:
        row = GtoPrefs(user_id=user.id)
        db.session.add(row)
    settings = dict(DEFAULT_PREFS)
    settings.update(row.settings)
    for key, default in DEFAULT_PREFS.items():
        if key not in incoming:
            continue
        value = incoming[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif isinstance(default, int):
            settings[key] = max(0, int(value))
        elif isinstance(default, float):
            settings[key] = float(value)
        elif isinstance(default, dict) and isinstance(value, dict):
            settings[key] = value
    settings["sb"] = max(1, min(100_000, settings["sb"]))
    settings["bb"] = max(settings["sb"], min(100_000, settings["bb"]))
    settings["buyin"] = max(settings["bb"] * 10, min(10_000_000, settings["buyin"]))
    settings["seats"] = settings["seats"] if settings["seats"] in (0, 5, 6) else 0
    row.settings = settings
    db.session.commit()
    return settings


def opponents_for(user, prefs):
    """The five of them, tuned by anything the gear menu has changed."""
    people = profiles.table(private=is_owner(user))
    tuning = prefs.get("profiles") or {}
    out = []
    for p in people:
        for field, value in (tuning.get(p.key) or {}).items():
            if field in profiles.Profile.FIELDS:
                setattr(p, field, value)
        out.append(bots.Bot(p, random.Random()))
    return out


# ------------------------------------------------------------- the table


def table_row(user):
    if user:
        return GtoTable.query.filter_by(user_id=user.id).first()
    return GtoTable.query.filter_by(session_key=session_key()).first()


def load_table(user, create=True):
    """The player's table, restored from the database or freshly sat down."""
    row = table_row(user)
    prefs = load_prefs(user)
    if row and row.state_json and row.state_json != "{}":
        try:
            return row, table_module.Table.from_dict(row.state), prefs
        except Exception:
            # A stored table from an older shape is not worth a 500. Sit down
            # again rather than refusing to deal.
            db.session.delete(row)
            db.session.commit()
            row = None
    if not create:
        return None, None, prefs

    seats = prefs["seats"] or random.choice([5, 6])
    t = table_module.Table(
        hero_name(user), opponents_for(user, prefs), buyin=prefs["buyin"],
        sb=prefs["sb"], bb=prefs["bb"], bounty_on=prefs["bounty_on"],
        seats=seats)

    played = GtoSession(user_id=user.id if user else None, sb=t.sb, bb=t.bb,
                        buyin=t.buyin, seats=seats, bounty_on=t.bounty_on,
                        bought_in=t.buyin, stack=t.buyin)
    db.session.add(played)
    db.session.flush()

    row = GtoTable(user_id=user.id if user else None,
                   session_key=None if user else session_key(),
                   session_id=played.id)
    row.state = t.to_dict()
    db.session.add(row)
    db.session.commit()
    return row, t, prefs


def store(row, t):
    row.state = t.to_dict()
    played = db.session.get(GtoSession, row.session_id) if row.session_id else None
    if played:
        played.hands = t.hands_played
        played.bought_in = t.bought_in.get(t.hero, 0)
        played.stack = t.stacks.get(t.hero, 0)
    db.session.commit()


def view(t, prefs, user, reveal=False):
    """Everything the page needs to draw itself."""
    state = t.state(reveal=reveal)
    owner = is_owner(user)
    for seat in state["seats"]:
        bot = t.bots.get(seat["name"])
        if bot:
            seat["blurb"] = bot.profile.blurb
            seat["key"] = bot.profile.key
            seat["avatar"] = f"/avatars/{bot.profile.key}" if (
                owner and bot.profile.avatar) else None
            seat["tilt"] = round(bot.tilt, 2)
        else:
            seat["you"] = True
    state["bounty_on"] = t.bounty_on
    state["bb"] = t.bb
    state["sb"] = t.sb
    state["profit"] = t.profit()
    state["needs_rebuy"] = t.needs_rebuy()
    state["prefs"] = prefs
    return state


# ---------------------------------------------------------------- pages


@app.route("/")
def index():
    user = current_user()
    row, t, prefs = load_table(user)
    return render_template(
        "table.html", state=view(t, prefs, user), user=user,
        owner=is_owner(user), main_site=MAIN_SITE_URL, presence_where="table",
        opponents=[b.profile.to_dict() for b in t.bots.values()])


@app.route("/proof")
def proof_page():
    """Where the numbers were checked against somebody else's numbers.

    Rendered from ``validation.json`` rather than run live: the checks need
    ``eval7``, which is a test-only dependency this box does not install, and
    the full run is four seconds. ``tools/validate_report.py`` regenerates the
    file and ``tests/test_validation.py`` runs the same checks live, so the page
    being stale cannot make a failing check look like a passing one - it can only
    make a current one look old, which is what the date is for.
    """
    user = current_user()
    report = None
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "validation.json")
    try:
        with open(path) as fh:
            report = json.load(fh)
    except (OSError, ValueError):
        report = None
    return render_template("proof.html", user=user, main_site=MAIN_SITE_URL,
                           presence_where="stats", report=report)


@app.route("/stats")
def stats_page():
    user = current_user()
    return render_template("stats.html", user=user, main_site=MAIN_SITE_URL,
                           presence_where="stats", summary=lifetime_stats(user))


@app.route("/avatars/<key>")
def avatar(key):
    """A photograph of a real person, served to exactly one account.

    Not a 403 for anybody else, because a 403 confirms the file is there. This
    is the same reasoning ``/admin`` uses on the main site.
    """
    user = current_user()
    if not is_owner(user):
        abort(404)
    if key not in {p.key for p in profiles.FRIENDS}:
        abort(404)
    name = f"{key}.jpg"
    if not os.path.exists(os.path.join(AVATAR_DIR, name)):
        abort(404)
    return send_from_directory(AVATAR_DIR, name, max_age=3600)


@app.route("/healthz")
def healthz():
    return "ok"


# ------------------------------------------------------------------ api


@app.route("/api/state")
def api_state():
    user = current_user()
    row, t, prefs = load_table(user)
    return jsonify(view(t, prefs, user))


@app.route("/api/hand", methods=["POST"])
def api_hand():
    user = current_user()
    row, t, prefs = load_table(user)
    if t.needs_rebuy():
        return jsonify({"error": "rebuy", "state": view(t, prefs, user)}), 409
    events = t.new_hand()
    store(row, t)
    return jsonify({"events": events, "state": view(t, prefs, user)})


@app.route("/api/act", methods=["POST"])
def api_act():
    user = current_user()
    row, t, prefs = load_table(user)
    if not t.hand or t.hand.complete:
        return jsonify({"error": "no hand in progress"}), 409

    body = request.get_json(silent=True) or {}
    action = {"action": body.get("action")}
    legal = {a["action"]: a for a in t.hand.legal_actions()}
    if action["action"] not in legal:
        return jsonify({"error": "not a legal action"}), 400
    if action["action"] == "call":
        action["amount"] = legal["call"]["amount"]
    if action["action"] in ("bet", "raise"):
        want = int(body.get("to") or 0)
        action["to"] = max(legal[action["action"]]["min"],
                           min(legal[action["action"]]["max"], want))

    events = t.hero_act(action)
    finished = t.hand.complete
    marks = record_hand(user, row, t) if finished else []
    store(row, t)
    return jsonify({
        "events": events,
        "state": view(t, prefs, user, reveal=finished),
        "review": marks,
        "adaptation": review_module.adaptation_notes(t) if finished else [],
    })


@app.route("/api/rebuy", methods=["POST"])
def api_rebuy():
    user = current_user()
    row, t, prefs = load_table(user)
    body = request.get_json(silent=True) or {}
    amount = int(body.get("amount") or t.buyin)
    t.rebuy(max(t.bb * 10, min(t.buyin * 5, amount)))
    store(row, t)
    return jsonify(view(t, prefs, user))


@app.route("/api/leave", methods=["POST"])
def api_leave():
    """Stand up. The record stays; the table does not."""
    user = current_user()
    row = table_row(user)
    if row:
        played = db.session.get(GtoSession, row.session_id) if row.session_id else None
        if played and not played.ended_at:
            from datetime import datetime
            played.ended_at = datetime.utcnow()
        db.session.delete(row)
        db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/prefs", methods=["GET", "POST"])
def api_prefs():
    user = current_user()
    if request.method == "GET":
        return jsonify(load_prefs(user))
    if not user:
        return jsonify({"error": "sign in to keep settings"}), 401
    settings = save_prefs(user, request.get_json(silent=True) or {})
    # Stakes and seat count only take effect at a fresh sit-down, so the table
    # is torn down rather than mutated underneath a hand in progress.
    row = table_row(user)
    if row:
        db.session.delete(row)
        db.session.commit()
    return jsonify(settings)


@app.route("/api/profiles")
def api_profiles():
    user = current_user()
    prefs = load_prefs(user)
    return jsonify([b.profile.to_dict() for b in opponents_for(user, prefs)])


@app.route("/api/stats")
def api_stats():
    return jsonify(lifetime_stats(current_user()))


#: What a heartbeat may say somebody is doing here. A *key* comes off the wire
#: and one of these words comes back - the status line is drawn on a public
#: profile, so nothing a browser sends ever reaches it.
PRESENCE_WHERE = {
    "table": "At the table",
    "stats": "Reading the numbers",
}


@app.route("/api/presence", methods=["POST"])
def api_presence():
    """The heartbeat behind the green dot on cgovind.com/accounts.

    Sent on load and then once a minute while the tab is visible. Guests get a
    200 and no row: presence hangs off an account and there is nowhere to hang
    a guest's.
    """
    user = current_user()
    if not user:
        return jsonify({"ok": True})
    where = str((request.get_json(silent=True) or {}).get("where", ""))[:20]
    visits.seen(db, user.id, "gto", PRESENCE_WHERE.get(where))
    return jsonify({"ok": True})


# --------------------------------------------------------- the record


def record_hand(user, row, t):
    """Write the finished hand and its marks, and return the marks."""
    marks = review_module.review_hand(t, rng=random.Random(),
                                      iters=int(os.environ.get("GTO_REVIEW_ITERS", 2500)))
    if not row.session_id:
        return [m.to_dict() for m in marks]

    summary = t.last_hand
    if not summary:
        return [m.to_dict() for m in marks]

    hand_row = GtoHand(
        session_id=row.session_id, user_id=user.id if user else None,
        hand_no=summary["hand_no"],
        position=summary["position"],
        hole=" ".join(str(c) for c in summary["hole"]),
        board=" ".join(str(c) for c in summary["board"]),
        result_cents=summary["result_cents"],
        ev_cents=(summary["ev_cents"] if summary["ev_cents"] is not None
                  else summary["result_cents"]),
        bounty_cents=summary["bounty_cents"],
        vpip=summary["vpip"], pfr=summary["pfr"],
        three_bet=summary["three_bet"],
        three_bet_chance=summary["three_bet_chance"],
        saw_flop=summary["saw_flop"], showdown=summary["showdown"],
        won=summary["won"], won_showdown=summary["won_showdown"],
        streak_after=summary["streak_after"],
    )
    db.session.add(hand_row)
    db.session.flush()

    for m in marks:
        d = m.decision
        db.session.add(GtoDecision(
            hand_id=hand_row.id, user_id=user.id if user else None,
            street=d.street, position=d.position,
            hole=" ".join(str(c) for c in d.hole),
            board=" ".join(str(c) for c in d.board),
            node=json.dumps(d.node) if d.node else None,
            pot=d.pot, to_call=d.to_call, stack=d.stack,
            opponents=d.opponents, streak=d.streak,
            opponent=_sole_opponent(d),
            action=d.action, amount=d.amount or 0,
            verdict=m.verdict, loss_bb=m.loss_bb, headline=m.headline,
            lines_json=json.dumps([x.to_dict() for x in m.lines]),
        ))
    db.session.commit()
    return [m.to_dict() for m in marks]


def _sole_opponent(d):
    """The one live opponent, or ``None`` if there was more than one."""
    live = [o["name"] for o in getattr(d, "opponents_in", [])
            if o["action"] != "fold"]
    return live[0] if len(live) == 1 else None


def lifetime_stats(user):
    """Everything, across every session this account has played."""
    running = stats_module.Running()
    if not user:
        return running.summary()

    # ``result_cents`` is what that one hand did, not a running total - see
    # ``Table._hand_summary``. Differencing it here (which is what this used to
    # do) charged the whole of the previous session to the first hand of the
    # next one, because profit restarts at zero at every fresh sit-down.
    hands = (GtoHand.query.filter_by(user_id=user.id)
             .order_by(GtoHand.played_at).all())
    for h in hands:
        result = h.result_cents or 0
        running.add_hand(result, ev_cents=h.ev_cents if h.ev_cents is not None else result,
                         bounty_cents=h.bounty_cents or 0,
                         vpip=h.vpip, pfr=h.pfr, three_bet=h.three_bet,
                         three_bet_chance=h.three_bet_chance,
                         saw_flop=h.saw_flop, showdown=h.showdown,
                         won_showdown=h.won_showdown, won=h.won)

    marks = GtoDecision.query.filter_by(user_id=user.id).all()
    for m in marks:
        running.add_review(m, opponent=m.opponent)
    running.error_bb = round(running.error_bb, 1)

    out = running.summary()
    out["headline"] = running.headline()
    return out


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5006)), debug=True)
