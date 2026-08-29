"""The coach's routes: the only ones here that spend money.

The first tests in this directory to boot the Flask app rather than a module,
and they exist for that reason. Everything else in ``gto/`` is a pure function
over a hand and is tested as one; ``/api/coach`` is four guards around a call to
somebody else's server, and a guard that has never been run is a guess. The four:

- **Anybody but Chinmay gets a 404**, logged in or out, on every method. Not a
  403, because a 403 confirms the endpoint is here.
- **One row per decision, ever.** A second click reads it back and calls nothing.
- **A rolling daily ceiling**, checked *before* the call rather than billed and
  regretted.
- **A GET never starts a call**, so a drawer left open cannot run up a bill.

The network is stubbed throughout. Nothing here may ever make a real request:
a test suite that bills an API is a test suite nobody runs twice.
"""

import os
import tempfile
import threading
import time

import pytest

os.environ.setdefault("GTO_OWNERS", "chinmay")
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mkdtemp() + "/coach-api.db"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-not-a-real-key"

import app as gto_app                                          # noqa: E402
import coach as coach_module                                   # noqa: E402
from models import GtoCoach, GtoDecision, GtoFinding, User, db  # noqa: E402

ANSWER = ("Calling is fine.\n"
          "- You need 0.25/0.75 = 33% and have about 35%.\n"
          "- 12 combinations beat you.")
FINDINGS = [{"tag": "call_too_wide",
             "label": "calls suited gappers from early position",
             "severity": "moderate"}]


def an_answer(findings=None, spots=None):
    return {"text": ANSWER,
            "spots": [{"n": 1, "call": "wrong", "why": "too wide from there"}]
                     if spots is None else spots,
            "findings": FINDINGS if findings is None else findings}
USAGE = {"input_tokens": 812, "output_tokens": 431,
         "cache_read_tokens": 0, "cache_creation_tokens": 0}


@pytest.fixture
def api(monkeypatch):
    """A logged-in owner, a clean coach table, and no network."""
    calls = []

    def fake_ask(ctx):
        calls.append(ctx)
        return an_answer(), dict(USAGE), 4210

    monkeypatch.setattr(coach_module, "ask", fake_ask)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")

    # A test that asks for an answer and does not wait for it leaves the
    # worker thread running into the next test, where it writes its findings
    # into the table this fixture just cleaned. Join the stragglers first.
    for t in threading.enumerate():
        if t.name == "coach":
            t.join(timeout=5)

    with gto_app.app.app_context():
        # Findings first: they hang off a coach row, and a leftover one makes
        # the next test's tally wrong rather than making it fail here.
        GtoFinding.query.delete()
        GtoCoach.query.delete()
        db.session.commit()
        owner = User.query.filter_by(username="chinmay").first()
        if not owner:
            owner = User(username="chinmay", email="chinmay@example.com")
            stranger = User(username="stranger", email="stranger@example.com")
            db.session.add_all([owner, stranger])
            db.session.commit()
        stranger = User.query.filter_by(username="stranger").first()
        ids = (owner.id, stranger.id)

    client = gto_app.app.test_client()
    client.calls = calls
    client.owner_id, client.stranger_id = ids
    login(client, ids[0])
    return client


def login(client, user_id):
    with client.session_transaction() as s:
        if user_id is None:
            s.clear()
        else:
            s["user_id"] = user_id


def a_hand(client):
    """Play folded hands until the review hands back a hand id to ask about."""
    for _ in range(80):
        r = client.post("/api/hand")
        if r.status_code == 409:
            client.post("/api/rebuy", json={})
            continue
        r = client.post("/api/act", json={"action": "fold"})
        if r.status_code != 200:
            continue
        ids = [m["hand_id"] for m in (r.get_json().get("review") or [])
               if m.get("hand_id")]
        if ids:
            return ids[0]
    pytest.skip("no hand put the hero on the clock in 80 deals")


def a_decision_of(hand_id):
    with gto_app.app.app_context():
        d = (GtoDecision.query.filter_by(hand_id=hand_id)
             .order_by(GtoDecision.id).first())
        return d.id if d else None


def finish(client, hand_id, tries=40):
    for _ in range(tries):
        body = client.get("/api/coach?hand=%d" % hand_id).get_json()
        if body["coach"] and body["coach"]["status"] != "pending":
            return body
        time.sleep(0.05)
    raise AssertionError("the answer never landed")


# ------------------------------------------------------------------ the gate


@pytest.mark.parametrize("who", ["stranger", "nobody"])
def test_everybody_else_gets_a_404_not_a_403(api, who):
    """A 403 would confirm there is an endpoint here that spends money."""
    login(api, api.stranger_id if who == "stranger" else None)
    assert api.get("/api/coach?hand=1").status_code == 404
    assert api.post("/api/coach", json={"hand": 1}).status_code == 404
    assert api.get("/api/coach/usage").status_code == 404
    assert not api.calls


def test_another_accounts_hand_is_a_404_even_for_the_owner(api):
    did = a_hand(api)
    with gto_app.app.app_context():
        for d in GtoDecision.query.filter_by(hand_id=did):
            d.user_id = api.stranger_id
        db.session.commit()
    assert api.post("/api/coach", json={"hand": did}).status_code == 404
    assert not api.calls


def test_a_hand_that_does_not_exist_is_a_404(api):
    assert api.post("/api/coach", json={"hand": 999_999}).status_code == 404
    assert api.post("/api/coach", json={}).status_code == 400


# ------------------------------------------------------------------ the call


def test_the_hand_is_written_down_without_any_of_the_marking(api):
    did = a_hand(api)
    with gto_app.app.app_context():
        ctx = (GtoDecision.query.filter_by(hand_id=did)
               .order_by(GtoDecision.id).first().context)
    assert ctx and ctx["hole"] and ctx["players"]
    assert not ({"verdict", "range", "equity", "headline"} & set(ctx))


def test_asking_answers_and_bills(api):
    did = a_hand(api)
    r = api.post("/api/coach", json={"hand": did})
    assert r.status_code == 202
    assert r.get_json()["coach"]["status"] == "pending"

    body = finish(api, did)
    assert body["coach"]["status"] == "done"
    assert body["coach"]["text"] == ANSWER
    # 812 in at $5/M plus 431 out at $25/M.
    assert body["coach"]["cost_micros"] == 14_835
    assert body["usage"]["day"]["micros"] == 14_835
    assert body["usage"]["life"]["answers"] == 1
    assert len(api.calls) == 1


def test_a_get_never_starts_a_call(api):
    """A drawer left open polls forever and must not be able to spend."""
    did = a_hand(api)
    for _ in range(3):
        body = api.get("/api/coach?hand=%d" % did).get_json()
        assert body["coach"] is None
    assert not api.calls


def test_the_same_decision_is_only_ever_paid_for_once(api):
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    finish(api, did)

    r = api.post("/api/coach", json={"hand": did})
    assert r.status_code == 200
    assert r.get_json()["coach"]["text"] == ANSWER
    assert len(api.calls) == 1, "a second click paid for the same paragraph"


def test_a_failed_call_says_so_and_is_not_billed(api, monkeypatch):
    def boom(ctx):
        raise coach_module.CoachError("could not reach the API")

    monkeypatch.setattr(coach_module, "ask", boom)
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    body = finish(api, did)
    assert body["coach"]["status"] == "error"
    assert "could not reach" in body["coach"]["error"]
    assert body["usage"]["day"]["micros"] == 0


def test_a_failed_answer_can_be_asked_for_again(api, monkeypatch):
    """A failure that is cached leaves the button broken with no way back."""
    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (_ for _ in ()).throw(
                            coach_module.CoachError("the API said 529")))
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    assert finish(api, did)["coach"]["status"] == "error"

    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (an_answer(), dict(USAGE), 10))
    r = api.post("/api/coach", json={"hand": did})
    assert r.status_code == 202, "the failure was served back instead of retried"
    body = finish(api, did)
    assert body["coach"]["status"] == "done"
    assert body["coach"]["error"] is None
    assert body["coach"]["text"] == ANSWER


# --------------------------------------------------------------- the ceiling


def test_the_daily_ceiling_stops_the_call_before_it_is_made(api):
    spent, unspent = a_hand(api), a_hand(api)
    api.post("/api/coach", json={"hand": spent})
    finish(api, spent)

    with gto_app.app.app_context():
        GtoCoach.query.filter_by(decision_id=spent).first().cost_micros = 2_000_000
        db.session.commit()

    before = len(api.calls)
    r = api.post("/api/coach", json={"hand": unspent})
    assert r.status_code == 429
    assert "daily ceiling" in r.get_json()["error"]
    assert len(api.calls) == before, "it called out past the ceiling"


def test_a_cached_answer_is_still_readable_at_the_ceiling(api):
    """The ceiling is on spending, not on reading what was already paid for."""
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    finish(api, did)
    with gto_app.app.app_context():
        GtoCoach.query.filter_by(decision_id=did).first().cost_micros = 9_000_000
        db.session.commit()
    body = api.get("/api/coach?hand=%d" % did).get_json()
    assert body["coach"]["text"] == ANSWER


def test_only_one_call_is_in_flight_at_a_time(api, monkeypatch):
    """Not for the money - for the workers. There are three of them."""
    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (time.sleep(2), (an_answer(), dict(USAGE), 1))[1])
    first, second = a_hand(api), a_hand(api)
    assert api.post("/api/coach", json={"hand": first}).status_code == 202
    r = api.post("/api/coach", json={"hand": second})
    assert r.status_code == 429
    assert "Still thinking" in r.get_json()["error"]


def test_a_pending_row_a_dead_worker_left_behind_is_retried(api):
    """A restart mid-call must not leave a row nothing will ever finish."""
    from datetime import datetime, timedelta

    did = a_hand(api)
    with gto_app.app.app_context():
        db.session.add(GtoCoach(
            decision_id=did, user_id=api.owner_id, status="pending",
            model=coach_module.model(),
            started_at=datetime.utcnow() - timedelta(seconds=600)))
        db.session.commit()

    assert api.post("/api/coach", json={"hand": did}).status_code == 202
    assert finish(api, did)["coach"]["status"] == "done"
    assert len(api.calls) == 1


# ---------------------------------------------------------------- unconfigured


def test_no_key_means_it_says_so_rather_than_half_working(api, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    did = a_hand(api)
    r = api.post("/api/coach", json={"hand": did})
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.get_json()["error"]
    assert not api.calls


# -------------------------------------------------------------- the free tier


def gemini_only(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")


def test_on_the_free_tier_the_meter_counts_answers_not_dollars(api, monkeypatch):
    """Showing "$0.00 of $1.00" would reassure about the wrong ceiling."""
    gemini_only(monkeypatch)
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    body = finish(api, did)

    assert body["usage"]["free"] is True
    assert body["usage"]["provider"] == "gemini"
    assert body["coach"]["cost_micros"] == 0
    assert body["usage"]["day"]["micros"] == 0
    # The tokens are still counted, because they are what was actually used.
    assert body["usage"]["day"]["input_tokens"] == USAGE["input_tokens"]
    assert body["usage"]["day"]["answers"] == 1
    assert body["usage"]["cap_calls"] > 0


def test_the_call_ceiling_is_what_binds_when_nothing_is_billed(api, monkeypatch):
    """A dollar cap never trips on a free tier, so it cannot be the only one."""
    gemini_only(monkeypatch)
    monkeypatch.setenv("GTO_COACH_DAILY_CALLS", "1")
    first, second = a_hand(api), a_hand(api)
    api.post("/api/coach", json={"hand": first})
    finish(api, first)

    before = len(api.calls)
    r = api.post("/api/coach", json={"hand": second})
    assert r.status_code == 429
    assert "answers in a day" in r.get_json()["error"]
    assert len(api.calls) == before


def test_the_page_is_told_which_model_answers(api, monkeypatch):
    gemini_only(monkeypatch)
    with gto_app.app.test_request_context():
        from models import User
        owner = User.query.filter_by(username="chinmay").first()
        view = gto_app.coach_view(owner)
    assert view["name"] == "Gemini" and view["model"] == "gemini-3.5-flash"
    assert gto_app.coach_view(None) is None


def test_a_hand_from_before_the_coach_existed_is_refused_kindly(api):
    """Old rows have no ``context_json`` and cannot get one retroactively."""
    did = a_hand(api)
    with gto_app.app.app_context():
        for d in GtoDecision.query.filter_by(hand_id=did):
            d.context_json = None
        db.session.commit()
    r = api.post("/api/coach", json={"hand": did})
    assert r.status_code == 409
    assert "before the coach existed" in r.get_json()["error"]
    assert not api.calls


# ------------------------------------------------------------- what accumulates


def test_findings_are_stored_and_counted_across_hands(api):
    """The reason the table exists: the ninth time is a different fact."""
    from models import GtoFinding

    first = a_hand(api)
    api.post("/api/coach", json={"hand": first})
    body = finish(api, first)
    assert [f["tag"] for f in body["coach"]["findings"]] == ["call_too_wide"]
    assert body["coach"]["findings"][0]["seen"] == 1

    second = a_hand(api)
    api.post("/api/coach", json={"hand": second})
    body = finish(api, second)
    assert body["coach"]["findings"][0]["seen"] == 2, "the tally did not add up"

    with gto_app.app.app_context():
        rows = GtoFinding.query.filter_by(user_id=api.owner_id).all()
        assert len(rows) == 2
        assert {r.street for r in rows} != {None}, "the street was not recorded"


def test_a_hand_played_fine_stores_nothing(api, monkeypatch):
    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (an_answer(findings=[]), dict(USAGE), 10))
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    body = finish(api, did)
    assert body["coach"]["findings"] == []
    assert api.get("/api/coach/leaks").get_json()["total"] == 0


def test_asking_the_same_hand_again_does_not_count_it_twice(api, monkeypatch):
    """A retry after a failure, or after a model change, is still one hand."""
    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (_ for _ in ()).throw(
                            coach_module.CoachError("busy")))
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    finish(api, did)

    monkeypatch.setattr(coach_module, "ask",
                        lambda ctx: (an_answer(), dict(USAGE), 10))
    api.post("/api/coach", json={"hand": did})
    finish(api, did)
    api.post("/api/coach", json={"hand": did})     # cached, no new call

    leaks = api.get("/api/coach/leaks").get_json()
    assert leaks["total"] == 1, leaks


def test_the_leaks_endpoint_ranks_by_how_often(api, monkeypatch):
    seq = [[{"tag": "limp", "label": "limps", "severity": "minor"}],
           [{"tag": "limp", "label": "limps again", "severity": "moderate"}],
           [{"tag": "bet_too_small", "label": "bets small", "severity": "minor"}]]
    box = {"i": 0}

    def fake(ctx):
        f = seq[box["i"] % len(seq)]
        box["i"] += 1
        return an_answer(findings=f), dict(USAGE), 10

    monkeypatch.setattr(coach_module, "ask", fake)
    for _ in range(3):
        did = a_hand(api)
        api.post("/api/coach", json={"hand": did})
        finish(api, did)

    leaks = api.get("/api/coach/leaks").get_json()
    assert leaks["total"] == 3
    assert [l["tag"] for l in leaks["leaks"]] == ["limp", "bet_too_small"]
    assert leaks["leaks"][0]["count"] == 2
    # The most recent wording is kept, so the tally is readable.
    assert leaks["leaks"][0]["label"] == "limps again"
    assert "other" in leaks["vocabulary"]


def test_the_leaks_endpoint_is_chinmays_alone(api):
    login(api, api.stranger_id)
    assert api.get("/api/coach/leaks").status_code == 404
    login(api, None)
    assert api.get("/api/coach/leaks").status_code == 404


# ---------------------------------------------------------------- the session


def test_the_table_carries_its_own_session_numbers(api):
    """Beside the table, not on /stats: a rate you leave to read is one you
    read after the session it would have changed."""
    s = api.get("/api/state").get_json()["session"]
    for key in ("hands", "vpip", "pfr", "three_bet", "bb100", "profit",
                "errors", "decisions", "headline"):
        assert key in s, key

    a_hand(api)
    s = api.get("/api/state").get_json()["session"]
    assert s["hands"] >= 1
    assert s["vpip"] is not None


def test_the_session_numbers_are_this_sit_down_and_not_all_time(api):
    from models import GtoHand

    a_hand(api)
    before = api.get("/api/state").get_json()["session"]["hands"]
    assert before >= 1

    api.post("/api/session/reset")
    after = api.get("/api/state").get_json()
    assert after["session"]["hands"] == 0, "the reset kept the old hands"
    # The record itself is untouched - only the sit-down restarted.
    with gto_app.app.app_context():
        assert GtoHand.query.filter_by(user_id=api.owner_id).count() >= before


def test_a_reset_puts_the_stacks_back_and_ends_the_old_session(api):
    from models import GtoSession

    state = api.get("/api/state").get_json()
    with gto_app.app.app_context():
        from models import GtoTable
        old = GtoTable.query.filter_by(user_id=api.owner_id).first().session_id

    for _ in range(4):
        a_hand(api)
    api.post("/api/session/reset")

    fresh = api.get("/api/state").get_json()
    buyin = fresh["prefs"]["buyin"]
    you = [s for s in fresh["seats"] if s.get("you")][0]
    assert you["stack"] == buyin, "the stacks did not go back to the buy-in"
    assert fresh["profit"] == 0

    with gto_app.app.app_context():
        assert db.session.get(GtoSession, old).ended_at is not None
        from models import GtoTable
        assert GtoTable.query.filter_by(user_id=api.owner_id).first().session_id != old


def test_a_reset_needs_no_coach_and_works_logged_out(api):
    """It is a table action, not a coach one, so it is not owner-gated."""
    login(api, api.stranger_id)
    assert api.post("/api/session/reset").status_code == 200
    login(api, None)
    assert api.post("/api/session/reset").status_code == 200


# --------------------------------------------------------------- whole hands


def test_one_answer_covers_every_spot_in_the_hand(api, monkeypatch):
    """The spots are not independent, and one call is cheaper than one each."""
    seen = {}

    def fake(contexts):
        seen["n"] = len(contexts)
        spots = [{"n": i, "call": "right", "why": "fine"}
                 for i in range(1, len(contexts) + 1)]
        return an_answer(spots=spots), dict(USAGE), 10

    monkeypatch.setattr(coach_module, "ask", fake)
    did = a_hand(api)
    api.post("/api/coach", json={"hand": did})
    body = finish(api, did)

    with gto_app.app.app_context():
        want = GtoDecision.query.filter_by(hand_id=did).count()
    assert seen["n"] == want, "the coach was not given the whole hand"
    assert len(body["coach"]["spots"]) == want
    assert body["coach"]["hand_id"] == did
