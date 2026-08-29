"""The coach, tested everywhere except the network.

Two of these matter more than the rest.

``test_the_prompt_carries_none_of_this_repos_analysis`` is the one that guards
the whole point of the feature. The value of a second opinion is that it is
arrived at independently; the moment an equity or a verdict out of ``review.py``
leaks into the prompt, the answer becomes a paraphrase and nothing is learned by
comparing them. That leak would be silent - the panel would still fill with
plausible prose - so it is checked here rather than noticed later.

``test_a_cost_is_never_rounded_to_nothing`` is the spend meter's own proof. A
meter that reports zero for a real call is worse than no meter, because it reads
as "this is free".
"""

import random

import pytest

import bots
import coach
import profiles
import table as table_module


def a_table(sb=25, bb=25, bounty_on=True, seed=7):
    rng = random.Random(seed)
    people = profiles.table(private=False)[:5]
    opponents = [bots.Bot(p, random.Random(seed + i)) for i, p in enumerate(people)]
    return table_module.Table("chinmay", opponents, buyin=5000, sb=sb, bb=bb,
                              bounty_on=bounty_on, rng=rng, seats=6)


def a_decision(t=None):
    """Deal until the hero is actually asked something, then take the spot."""
    t = t or a_table()
    for _ in range(60):
        t.new_hand()
        if t.decisions:
            return t, t.decisions[-1]
        # Nobody asked the hero anything - fold the hand on and deal again.
        if t.hand and not t.hand.complete:
            t.hero_act({"action": "fold"})
    raise AssertionError("no hand put the hero on the clock")


# ------------------------------------------------------------ the snapshot


def test_a_decision_records_the_spot_as_the_engine_saw_it():
    t, d = a_decision()
    assert getattr(d, "seats_at", None), "no seat snapshot on the decision"
    assert getattr(d, "actions_before", None) is not None
    names = {s["name"] for s in d.seats_at}
    assert t.hero in names
    assert len(names) == len(t.seat_names)


def test_the_snapshot_is_the_betting_up_to_here_not_the_whole_hand():
    """Taken at the moment of the decision, because it cannot be had later."""
    t, d = a_decision()
    before = len(d.actions_before)
    if t.hand.complete:
        pytest.skip("the hand ended on the deal")
    t.hero_act({"action": "fold"})
    assert len(t.hand.actions) >= before
    assert len(d.actions_before) == before, "the snapshot moved with the hand"


def test_the_snapshot_survives_a_round_trip_through_the_database():
    t, d = a_decision()
    back = table_module.Table.from_dict(t.to_dict())
    d2 = back.decisions[-1]
    assert d2.seats_at == d.seats_at
    assert d2.actions_before == d.actions_before


# ------------------------------------------------------------- the context


def test_the_context_describes_the_situation():
    t, d = a_decision()
    ctx = coach.context(t, d)
    assert ctx["hole"] and len(ctx["hole"].split()) == 2
    assert ctx["bb"] == t.bb and ctx["sb"] == t.sb
    assert ctx["hero"] == t.hero
    assert ctx["players"], "nobody else at the table"
    assert all(p["name"] != t.hero for p in ctx["players"])


def test_the_context_carries_how_each_opponent_plays():
    """Without the tendencies the read is against five strangers.

    They are profile fields - what a bot *is* - and not a range this code
    inferred, which is why they are allowed through when nothing else is.
    """
    t, d = a_decision()
    ctx = coach.context(t, d)
    styled = [p for p in ctx["players"] if p["style"]]
    assert styled
    for p in styled:
        assert 0 <= p["style"]["pfr"] <= p["style"]["vpip"] <= 100


def test_the_context_holds_nothing_this_repo_worked_out():
    """No equity, no ranges, no verdict - see the module docstring."""
    t, d = a_decision()
    ctx = coach.context(t, d)
    banned = {"equity", "range", "ranges", "opponents_in", "verdict", "loss_bb",
              "headline", "lines", "ev_bb", "chart", "node"}
    assert not (set(ctx) & banned), sorted(set(ctx) & banned)


# -------------------------------------------------------------- the prompt


def test_the_prompt_carries_none_of_this_repos_analysis():
    """The guard on the whole feature. See the module docstring."""
    import review

    t, d = a_decision()
    d.action, d.amount = "fold", 0
    mark = review.review_decision(d, bb=t.bb, bounty_on=t.bounty_on,
                                  opponents=d.opponents,
                                  rng=random.Random(1), iters=200)
    ctx = coach.context(t, d)
    text = coach.prompt(ctx)

    assert mark.headline not in text
    for line in mark.lines:
        as_dict = line.to_dict()
        assert as_dict["text"] not in text, as_dict["label"]

    # The word scan runs with the opponents' blurbs blanked. They are prose
    # somebody wrote about a friend - one of them says "close-to-solver game" -
    # so scanning them for the label names finds the word and not the leak.
    for p in ctx["players"]:
        if p["style"]:
            p["style"]["blurb"] = ""
    bare = coach.prompt(ctx).lower()
    for word in ("equity", "pot odds", "solver", "derived", "heuristic",
                 "break-even", "minimum defence", "combinations"):
        assert word not in bare, word


def test_the_prompt_says_when_the_blinds_are_equal():
    """The largest structural difference from any published chart."""
    t, d = a_decision(a_table(sb=25, bb=25))
    assert "equal blinds" in coach.prompt(coach.context(t, d))

    t2, d2 = a_decision(a_table(sb=10, bb=25, seed=11))
    assert "equal blinds" not in coach.prompt(coach.context(t2, d2))


def test_the_prompt_prices_the_bounty_or_leaves_it_out():
    t, d = a_decision(a_table(bounty_on=True))
    assert "Bounty is on" in coach.prompt(coach.context(t, d))

    t2, d2 = a_decision(a_table(bounty_on=False, seed=3))
    assert "Bounty" not in coach.prompt(coach.context(t2, d2))


def test_the_prompt_names_the_action_that_was_taken():
    t, d = a_decision()
    d.action, d.amount = "raise", 300
    text = coach.prompt(coach.context(t, d))
    assert "You raise to $3.00" in text

    d.action, d.amount = None, 0
    assert "What should you do here" in coach.prompt(coach.context(t, d))


def test_the_prompt_stays_small():
    """Every line of it is billed on every click."""
    t, d = a_decision()
    text = coach.prompt(coach.context(t, d))
    assert len(text) < 2500, len(text)


def test_the_system_prompt_asks_for_its_own_arithmetic():
    lower = coach.SYSTEM.lower()
    assert "not given any analysis" in lower
    assert "do your own arithmetic" in lower
    # It must be told to mark an estimate as one, or an unchecked number reads
    # exactly like a checked one.
    assert "roughly" in lower and "estimated" in lower


# ---------------------------------------------------------------- the bill


def test_a_cost_is_never_rounded_to_nothing():
    """A meter that reports zero for a real call reads as "this is free"."""
    micros = coach.cost_micros(
        {"input_tokens": 900, "output_tokens": 400,
         "cache_read_tokens": 0, "cache_creation_tokens": 0},
        "claude-opus-5")
    assert micros > 0
    # 900 in at $5/M plus 400 out at $25/M is $0.0145.
    assert micros == pytest.approx(14_500, abs=50)


def test_cached_and_written_tokens_are_priced_differently():
    plain = coach.cost_micros({"input_tokens": 10_000, "output_tokens": 0,
                               "cache_read_tokens": 0,
                               "cache_creation_tokens": 0}, "claude-opus-5")
    read = coach.cost_micros({"input_tokens": 0, "output_tokens": 0,
                              "cache_read_tokens": 10_000,
                              "cache_creation_tokens": 0}, "claude-opus-5")
    written = coach.cost_micros({"input_tokens": 0, "output_tokens": 0,
                                 "cache_read_tokens": 0,
                                 "cache_creation_tokens": 10_000},
                                "claude-opus-5")
    assert read == pytest.approx(plain * 0.1, rel=0.01)
    assert written == pytest.approx(plain * 1.25, rel=0.01)


def test_an_unknown_model_is_priced_as_the_dearest_one():
    """A wrong guess must over-report the bill, never under-report it."""
    usage = {"input_tokens": 1000, "output_tokens": 1000,
             "cache_read_tokens": 0, "cache_creation_tokens": 0}
    unknown = coach.cost_micros(usage, "claude-something-new")
    assert unknown == coach.cost_micros(usage, coach.DEFAULT_MODEL)
    assert unknown > coach.cost_micros(usage, "claude-haiku-4-5")


def test_the_daily_cap_reads_dollars(monkeypatch):
    monkeypatch.setenv("GTO_COACH_DAILY_USD", "2.50")
    assert coach.daily_cap_micros() == 2_500_000


def test_a_free_model_is_metered_in_calls_not_dollars():
    """Money never runs out on a free tier; requests per day do."""
    usage = {"input_tokens": 5000, "output_tokens": 5000,
             "cache_read_tokens": 0, "cache_creation_tokens": 0}
    assert coach.cost_micros(usage, "gemini-3.5-flash") == 0
    assert not coach.is_free("claude-opus-5")
    assert coach.daily_cap_calls() > 0


def test_free_is_decided_by_prefix_not_by_a_list_of_names():
    """Google retired the model this was first written against. Names move."""
    for name in ("gemini-3.5-flash", "gemini-2.5-pro", "gemini-9-whatever"):
        assert coach.is_free(name), name
        assert coach.cost_micros({"input_tokens": 9_000_000,
                                  "output_tokens": 9_000_000,
                                  "cache_read_tokens": 0,
                                  "cache_creation_tokens": 0}, name) == 0


# ------------------------------------------------------------ which provider


def no_keys(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY",
              "GTO_COACH_PROVIDER", "GTO_COACH_MODEL", "GTO_COACH_MAX_TOKENS"):
        monkeypatch.delenv(k, raising=False)


def test_it_is_off_without_a_key(monkeypatch):
    no_keys(monkeypatch)
    assert coach.provider() is None
    assert not coach.enabled()


def test_the_key_on_the_box_picks_the_provider(monkeypatch):
    no_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    assert coach.provider() == coach.GEMINI
    assert coach.model() == "gemini-3.5-flash"
    assert coach.enabled()

    # Anthropic wins when both are set - the paid one is the one deliberately
    # added, so it is the one meant.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    assert coach.provider() == coach.ANTHROPIC
    assert coach.model() == "claude-opus-5"

    monkeypatch.setenv("GTO_COACH_PROVIDER", "gemini")
    assert coach.provider() == coach.GEMINI


def test_gemini_gets_far_more_room_to_think(monkeypatch):
    """2.5 Pro bills thinking against the ceiling and cannot be told not to."""
    no_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    gemini = coach.max_tokens()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    assert gemini > coach.max_tokens()


def test_effort_is_not_claimed_where_it_does_nothing(monkeypatch):
    no_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert coach.effort() == "-"


# ------------------------------------------------------------------- gemini


def test_the_gemini_request_carries_the_prompt_and_a_ceiling(monkeypatch):
    no_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    t, d = a_decision()
    body = coach._gemini_body(coach.context(t, d))
    assert body["system_instruction"]["parts"][0]["text"] == coach.SYSTEM
    assert "You hold" in body["contents"][0]["parts"][0]["text"]
    assert body["generationConfig"]["maxOutputTokens"] == coach.max_tokens()
    # Setting a thinking budget on 2.5 Pro is either a no-op or a way to get an
    # empty answer, so there must not be one.
    assert "thinkingConfig" not in body["generationConfig"]


def test_a_gemini_answer_is_read_with_its_thinking_counted():
    """`candidatesTokenCount` excludes thinking, which is most of the spend."""
    text, usage = coach._gemini_read({
        "candidates": [{"content": {"parts": [{"text": "Calling is fine."}]},
                        "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 812, "candidatesTokenCount": 200,
                          "thoughtsTokenCount": 1400},
    })
    assert text == "Calling is fine."
    assert usage["input_tokens"] == 812
    assert usage["output_tokens"] == 1600, "thinking was not counted"


def test_gemini_spending_the_whole_ceiling_on_thinking_is_an_error():
    """A 200, with usage, and no text. It must not print an empty panel."""
    with pytest.raises(coach.CoachError) as e:
        coach._gemini_read({
            "candidates": [{"content": {"parts": []},
                            "finishReason": "MAX_TOKENS"}],
            "usageMetadata": {"promptTokenCount": 800,
                              "thoughtsTokenCount": 8000},
        })
    assert "GTO_COACH_MAX_TOKENS" in str(e.value)


def test_a_truncated_gemini_answer_says_it_was_cut_off():
    text, _ = coach._gemini_read({
        "candidates": [{"content": {"parts": [{"text": "Calling is fine bec"}]},
                        "finishReason": "MAX_TOKENS"}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    })
    assert "cut off" in text


def test_a_blocked_gemini_prompt_says_so():
    with pytest.raises(coach.CoachError) as e:
        coach._gemini_read({"promptFeedback": {"blockReason": "SAFETY"}})
    assert "SAFETY" in str(e.value)


def test_asking_with_no_key_at_all_is_refused_before_the_network(monkeypatch):
    no_keys(monkeypatch)
    with pytest.raises(coach.CoachError) as e:
        coach.ask({})
    assert "no API key" in str(e.value)


# ------------------------------------------------------- gemini, over the wire


def test_the_gemini_call_is_made_the_way_google_expects(monkeypatch):
    """The one test that runs the `urllib` code rather than around it.

    Against a stand-in on localhost, so it exercises the request that would go
    out - URL, headers, body - and the parse of what comes back, without a key,
    a network or a bill. The key goes in ``x-goog-api-key`` rather than in the
    query string this API also accepts, so it cannot be read off an access log
    or a referrer.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["key"] = self.headers.get("x-goog-api-key")
            length = int(self.headers["Content-Length"])
            seen["body"] = json.loads(self.rfile.read(length))
            out = json.dumps({
                "candidates": [{"content": {"parts": [{"text": "Calling is fine."}]},
                                "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 640,
                                  "candidatesTokenCount": 180,
                                  "thoughtsTokenCount": 1220},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        no_keys(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setattr(
            coach, "GEMINI_URL",
            "http://127.0.0.1:%d/v1beta/models/%%s:generateContent"
            % server.server_address[1])

        t, d = a_decision()
        d.action, d.amount = "call", d.to_call
        text, usage, ms = coach.ask(coach.context(t, d))
    finally:
        server.shutdown()

    assert seen["key"] == "test-key-123"
    assert "key=" not in seen["path"], "the key went into the URL"
    assert "gemini-3.5-flash:generateContent" in seen["path"]
    assert seen["body"]["generationConfig"]["maxOutputTokens"] == 8000
    assert "You hold" in seen["body"]["contents"][0]["parts"][0]["text"]

    assert text == "Calling is fine."
    assert usage["input_tokens"] == 640
    assert usage["output_tokens"] == 1400          # 180 written + 1220 thought
    assert coach.cost_micros(usage) == 0
    assert ms >= 0
