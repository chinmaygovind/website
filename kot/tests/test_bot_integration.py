"""King of Tokyo - bot orchestration, end to end through app.py.

``test_bot.py`` proves the brain decides well; this proves the plumbing around
it works: that a seated bot actually takes its turns, that its moves land in the
replay, and - most importantly - that a table containing bots always reaches a
winner instead of freezing in a phase nobody answers for.

Timers are collapsed: ``eventlet.spawn_after`` is patched to push the callback
onto a queue that ``drain()`` then works through, so a game that would take
minutes of wall-clock pacing runs in milliseconds. A missing re-schedule shows
up as a game that settles in a phase other than "ended" - the same thing a
frozen live table would look like.
"""

import os
import tempfile
import uuid

import pytest


@pytest.fixture(scope="module")
def kot():
    """Import app.py against a throwaway database."""
    db_path = os.path.join(tempfile.mkdtemp(), "kot-test.db")
    os.environ["DATABASE_URL"] = "sqlite:///" + db_path
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import app as kot_app
    return kot_app


class _Sched:
    """The collapsed scheduler: `kot` plus a `drain()` that runs pending work."""

    def __init__(self, kot, pending):
        self.kot = kot
        self._pending = pending

    def drain(self, limit=50_000):
        """Run scheduled callbacks until the game settles.

        Deliberately a trampoline rather than calling the callback inline.
        ``_bot_kick`` schedules from INSIDE the per-game lock, so running a
        callback inline would re-enter that lock from the same greenlet and
        deadlock - eventlet semaphores are not reentrant. Deferring to this
        queue reproduces what real timers do: the lock is always released
        before the next bot step starts."""
        ran = 0
        while self._pending:
            fn, a, kw = self._pending.pop(0)
            fn(*a, **kw)
            ran += 1
            assert ran < limit, "bot scheduler never settled"
        return ran


@pytest.fixture
def collapse_timers(kot, monkeypatch):
    import eventlet

    pending = []

    def defer(_delay, fn, *a, **kw):
        pending.append((fn, a, kw))

    monkeypatch.setattr(eventlet, "spawn_after", defer)
    monkeypatch.setattr(kot.socketio, "emit", lambda *a, **kw: None)
    return _Sched(kot, pending)


def _make_game(kot, n_bots, n_humans=1):
    """A started game with the requested seats. Returns the game code."""
    with kot.app.app_context():
        code = uuid.uuid4().hex[:6].upper()
        game = kot.KotGame(code=code, status="waiting", max_players=6)
        kot.db.session.add(game)
        kot.db.session.commit()

        seat = 0
        for i in range(n_humans):
            monster, color = kot.MONSTERS[seat % len(kot.MONSTERS)]
            kot.db.session.add(kot.KotPlayer(
                game_id=game.id, session_key=f"human{i}", name=f"Human{i}",
                color=color, monster=monster, seat_order=seat, is_host=(seat == 0)))
            seat += 1
        for i in range(n_bots):
            monster, color = kot.MONSTERS[seat % len(kot.MONSTERS)]
            kot.db.session.add(kot.KotPlayer(
                game_id=game.id, session_key=f"bot_{i}", name=kot.BOT_NAMES[i],
                color=color, monster=monster, seat_order=seat, is_bot=True))
            seat += 1
        kot.db.session.commit()

        players = sorted(game.players, key=lambda p: p.seat_order)
        pids = [p.pid for p in players]
        state = kot.gl.new_game(pids)
        kot.gl.set_names(state, {p.pid: p.name for p in players})
        game.state = state
        game.status = "playing"
        game.events_json = "[]"
        kot.db.session.commit()
        return code


def _reload(kot, code):
    with kot.app.app_context():
        return kot.KotGame.query.filter_by(code=code).first().state


def test_all_bot_game_plays_itself_to_a_winner(collapse_timers):
    """No human ever acts, so every single move must come from the scheduler.
    If any phase failed to re-arm, the game settles somewhere that is not
    "ended" - which is exactly what a frozen live table would look like."""
    sched = collapse_timers
    kot = sched.kot
    for _ in range(5):
        code = _make_game(kot, n_bots=3, n_humans=0)
        kot._bot_kick(code, why="start")
        sched.drain()
        state = _reload(kot, code)
        assert state["phase"] == "ended", f"stalled in {state['phase']}"
        assert state["winner"]


def test_bot_moves_are_recorded_in_the_replay(collapse_timers):
    sched = collapse_timers
    kot = sched.kot
    import json
    code = _make_game(kot, n_bots=2, n_humans=0)
    kot._bot_kick(code, why="start")
    sched.drain()
    with kot.app.app_context():
        game = kot.KotGame.query.filter_by(code=code).first()
        events = json.loads(game.events_json)

    kinds = {e["type"] for e in events}
    assert {"roll", "resolve", "end_turn"} <= kinds, kinds
    assert all(e.get("bot") for e in events if e["type"] == "roll")
    # every entry carries the position it produced, which is what makes the
    # log a replay rather than a list of button presses
    for e in events:
        if e["type"] in ("roll", "resolve", "buy", "end_turn"):
            assert "mon" in e and "turn" in e and "seq" in e
            assert set(e["mon"]) == set(_reload(kot, code)["players"])


def test_bot_stops_and_waits_for_the_human(collapse_timers):
    """With a human in seat 0 the scheduler must go quiet on their turn rather
    than playing for them."""
    sched = collapse_timers
    kot = sched.kot
    code = _make_game(kot, n_bots=1, n_humans=1)
    state = _reload(kot, code)
    human = state["players"][0]
    assert state["current"] == human

    kot._bot_kick(code, why="start")
    sched.drain()
    after = _reload(kot, code)
    assert after["current"] == human
    assert after["phase"] != "ended"
    assert after["seq"] == state["seq"], "a bot moved on the human's turn"


def test_bot_takes_over_once_the_human_ends_their_turn(collapse_timers):
    sched = collapse_timers
    kot = sched.kot
    code = _make_game(kot, n_bots=1, n_humans=1)
    state = _reload(kot, code)
    human = state["players"][0]

    # play the human's turn the crudest legal way
    with kot.app.app_context():
        game = kot.KotGame.query.filter_by(code=code).first()
        state = game.state
        kot.gl.set_names(state, kot._names(game))
        kot.gl.do_roll(state, human, [])
        kot.gl.resolve(state, human)
        while state["phase"] == "yield":
            q = state["pending_yield"]["queue"]
            kot.gl.yield_decision(state, q[0], True)
        if state["phase"] == "token_choice":
            kot.gl.token_choice_decision(state, human, 0, 0)
        game.state = state
        kot.db.session.commit()

    # _act normally runs inside the context Flask-SocketIO sets up per event.
    with kot.app.app_context():
        kot._act(code, lambda g, s, pid: kot.gl.end_turn(s, pid),
                 event={"type": "end_turn"}, actor_pid=human)
    sched.drain()

    after = _reload(kot, code)
    assert after["turn"] > 1, "the bot never took its turn"

    # The bot plays on until either its turn is over, the game is won, or it
    # runs into a decision that belongs to the human - being attacked out of
    # Tokyo is the common one, and the scheduler must stop there rather than
    # answering on the human's behalf.
    if after["phase"] == "yield":
        assert after["pending_yield"]["queue"][0] == human
    elif after["phase"] == "probe_window":
        assert after["pending_probe"]["queue"][0] == human
    elif after["phase"] == "token_choice":
        assert after["pending_token_choice"]["pid"] == human
    else:
        assert after["current"] == human or after["phase"] == "ended"


def test_scheduler_waits_on_a_humans_yield_decision(collapse_timers):
    """A bot attacking a human in Tokyo must leave the stay-or-leave call to
    them. Answering it for the human would be the bot playing someone else's
    seat; never answering an equivalent BOT prompt would freeze the table."""
    sched = collapse_timers
    kot = sched.kot
    code = _make_game(kot, n_bots=1, n_humans=1)

    with kot.app.app_context():
        game = kot.KotGame.query.filter_by(code=code).first()
        state = game.state
        human, bot_pid = state["players"][0], state["players"][1]
        # put the human in Tokyo and hand the bot a guaranteed attack
        state["tokyo"]["city"] = human
        state["current"] = bot_pid
        state["phase"] = "rolling"
        state["dice"] = ["claw"] * 6
        state["kept"] = [False] * 6
        state["roll_num"] = 1
        state["rolls_left"] = 0
        game.state = state
        kot.db.session.commit()
        seq = state["seq"]

    kot._bot_kick(code)
    sched.drain()

    after = _reload(kot, code)
    assert after["phase"] == "yield"
    assert after["pending_yield"]["queue"] == [human]
    assert after["mon"][human]["hp"] < 10, "the attack never landed"
    assert after["seq"] != seq


def test_scheduler_is_a_no_op_without_bots(collapse_timers):
    sched = collapse_timers
    kot = sched.kot
    code = _make_game(kot, n_bots=0, n_humans=2)
    before = _reload(kot, code)
    kot._bot_kick(code, why="start")
    assert sched.drain() == 0
    assert _reload(kot, code)["seq"] == before["seq"]


def test_bot_name_weighting(kot):
    """Bot-zilla headlines half the time; the rest split the remainder, and a
    full table never repeats a name."""
    counts = {}
    for _ in range(6000):
        n = kot._pick_bot_name(set())
        counts[n] = counts.get(n, 0) + 1
    assert 0.45 < counts["Bot-zilla"] / 6000 < 0.55
    for other in kot.BOT_NAMES[1:]:
        assert 0.08 < counts[other] / 6000 < 0.18

    used = set()
    for _ in range(len(kot.BOT_NAMES)):
        n = kot._pick_bot_name(used)
        assert n and n not in used
        used.add(n)
    assert used == set(kot.BOT_NAMES)
    assert kot._pick_bot_name(used) is None
