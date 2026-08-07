"""King of Tokyo - bot regression tests.

Two things are being protected here. First, that the bot always makes a legal,
progress-making decision in every phase: the engine parks the WHOLE game in
``yield`` / ``probe_window`` / ``token_choice`` until the monster on the clock
answers, so a bot that returned nothing would hang a live table, not just play
badly. Second, that it is actually strong - the weights in ``bot.W`` were tuned
by self-play, and it is easy to "clean up" one of them and quietly ship a bot
that loses.
"""

import collections
import random
import time

import pytest

import game_logic as gl
import bot

MAX_STEPS = 4000


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

class Smart:
    name = "smart"
    roll = staticmethod(bot.decide_roll)
    yld = staticmethod(bot.decide_yield)
    token = staticmethod(bot.decide_token_choice)
    buys = staticmethod(bot.decide_buys)


class Greedy:
    """A plausible casual player: chase claws and the biggest number set, heal
    when hurt, bail out of Tokyo at low health, buy whatever is affordable."""
    name = "greedy"

    @staticmethod
    def roll(state, pid):
        if state["roll_num"] == 0:
            return "roll", []
        if state["rolls_left"] <= 0:
            return "resolve", None
        dice = state["dice"]
        m = state["mon"][pid]
        hurt = m["hp"] <= 5 and gl._in_tokyo(state, pid) is None
        counts = collections.Counter(dice)
        best_num = max(("1", "2", "3"), key=lambda f: counts[f])
        keep = [i for i, d in enumerate(dice)
                if d == "claw" or d == best_num or (d == "heart" and hurt)]
        if len(keep) == len(dice):
            return "resolve", None
        return "roll", keep

    @staticmethod
    def yld(state, pid):
        return state["mon"][pid]["hp"] <= 5

    @staticmethod
    def token(state, pid):
        h = (state.get("pending_token_choice") or {}).get("hearts", 0)
        tok = state["mon"][pid].get("tokens", {})
        return min(tok.get("poison", 0), h), 0

    @staticmethod
    def buys(state, pid):
        cards = gl._cards()
        e = state["mon"][pid]["energy"]
        for i, cid in enumerate(state["shop"]):
            C = cards.CATALOG.get(cid) if cid else None
            if C and C["cost"] <= e:
                return [("buy", i)]
        return []


def play(policies, seed=None, setup=None):
    """Drive one full game through the real engine. Returns (winning seat, state).

    ``setup(state, pids)`` runs once on the fresh state, for tests that need to
    put a particular card or condition in play before the first turn."""
    pids = [f"p{i}" for i in range(len(policies))]
    state = gl.new_game(pids, seed=seed)
    gl.set_names(state, {p: policies[i].name for i, p in enumerate(pids)})
    if setup:
        setup(state, pids)
    pol = {p: policies[i] for i, p in enumerate(pids)}

    for _ in range(MAX_STEPS):
        ph = state["phase"]
        if ph == "ended":
            break
        if ph == "yield":
            q = (state.get("pending_yield") or {}).get("queue") or []
            if not q:
                break
            gl.yield_decision(state, q[0], pol[q[0]].yld(state, q[0]))
        elif ph == "probe_window":
            q = (state.get("pending_probe") or {}).get("queue") or []
            if not q:
                break
            who = q[0]
            die = bot.decide_probe(state, who) if pol[who] is Smart else None
            gl.card_action(state, who, "psychic_probe",
                           {"pass": True} if die is None else {"index": die})
            # Mirrors app._bot_probe: never leave the window undrained.
            q = (state.get("pending_probe") or {}).get("queue") or []
            if state["phase"] == "probe_window" and q and q[0] == who:
                gl.card_action(state, who, "psychic_probe", {"pass": True})
        elif ph == "token_choice":
            who = (state.get("pending_token_choice") or {}).get("pid")
            if not who:
                break
            p, sh = pol[who].token(state, who)
            gl.token_choice_decision(state, who, p, sh)
        elif ph == "rolling":
            cur = state["current"]
            action, keep = pol[cur].roll(state, cur)
            if action == "roll":
                gl.do_roll(state, cur, keep)
            else:
                gl.resolve(state, cur)
        elif ph == "buying":
            cur = state["current"]
            plan = pol[cur].buys(state, cur)
            if plan:
                kind, idx = plan[0]
                if kind == "buy":
                    gl.buy_card(state, cur, idx)
                else:
                    gl.sweep_shop(state, cur)
            else:
                gl.end_turn(state, cur)
        else:
            break

    w = state.get("winner")
    return (pids.index(w) if w in pids else None), state


# ---------------------------------------------------------------------------
# Liveness: every decision is legal and moves the game forward
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_players", [2, 3, 4, 6])
def test_games_always_finish(n_players):
    """An all-bot table always reaches a winner - no phase where nobody acts."""
    for seed in range(6):
        seat, state = play([Smart()] * n_players, seed=seed)
        assert state["phase"] == "ended", f"{n_players}p seed {seed} stalled"
        assert seat is not None


def test_decide_roll_returns_legal_keeps():
    state = gl.new_game(["p0", "p1"], seed=3)
    for _ in range(300):
        state["dice"] = [random.choice(gl.FACES) for _ in range(len(state["dice"]))]
        state["roll_num"] = random.choice([1, 2, 3])
        state["rolls_left"] = random.choice([0, 1, 2])
        action, keep = bot.decide_roll(state, "p0")
        assert action in ("roll", "resolve")
        if action == "roll":
            assert len(set(keep)) == len(keep)
            assert all(0 <= i < len(state["dice"]) for i in keep)
        else:
            assert keep is None


def test_first_roll_keeps_nothing():
    """Nothing to hold before any dice exist."""
    state = gl.new_game(["p0", "p1"], seed=1)
    assert state["roll_num"] == 0
    assert bot.decide_roll(state, "p0") == ("roll", [])


def test_out_of_rerolls_resolves():
    state = gl.new_game(["p0", "p1"], seed=1)
    gl.do_roll(state, "p0", [])
    state["rolls_left"] = 0
    assert bot.decide_roll(state, "p0")[0] == "resolve"


def test_token_choice_never_overspends_hearts():
    state = gl.new_game(["p0", "p1"], seed=5)
    m = state["mon"]["p0"]
    for hearts in range(1, 5):
        for poison in range(3):
            for shrink in range(3):
                for hp in (1, 4, 8, 10):
                    m["hp"] = hp
                    m["tokens"] = {"poison": poison, "shrink": shrink}
                    state["pending_token_choice"] = {"pid": "p0", "hearts": hearts}
                    sp, ss = bot.decide_token_choice(state, "p0")
                    assert sp >= 0 and ss >= 0
                    assert sp + ss <= hearts
                    assert sp <= poison and ss <= shrink


def test_buys_are_affordable_and_distinct():
    for seed in range(25):
        state = gl.new_game(["p0", "p1"], seed=seed)
        state["mon"]["p0"]["energy"] = random.randint(0, 20)
        state["phase"] = "buying"
        plan = bot.decide_buys(state, "p0")
        idxs = [i for kind, i in plan if kind == "buy"]
        assert len(set(idxs)) == len(idxs)
        spent = sum(gl._cards().CATALOG[state["shop"][i]]["cost"] for i in idxs
                    if state["shop"][i])
        assert spent <= state["mon"]["p0"]["energy"] + len(idxs)  # discounts only help


def test_bot_leaves_tokyo_when_nearly_dead():
    state = gl.new_game(["p0", "p1", "p2"], seed=2)
    state["tokyo"]["city"] = "p0"
    state["mon"]["p0"]["hp"] = 1
    assert bot.decide_yield(state, "p0") is True


def test_bot_holds_tokyo_at_full_health():
    state = gl.new_game(["p0", "p1", "p2"], seed=2)
    state["tokyo"]["city"] = "p0"
    state["mon"]["p0"]["hp"] = 10
    assert bot.decide_yield(state, "p0") is False


# ---------------------------------------------------------------------------
# Latency: one eventlet worker serves every live game
# ---------------------------------------------------------------------------

def test_dice_decision_is_fast():
    """A slow search would block every other player's socket traffic, not just
    the bot's own game."""
    state = gl.new_game(["p0", "p1"], seed=1)
    gl.do_roll(state, "p0", [])
    bot.decide_roll(state, "p0")           # warm the static caches

    worst = 0.0
    for _ in range(40):
        state["dice"] = [random.choice(gl.FACES) for _ in range(6)]
        state["rolls_left"] = random.choice([1, 2])
        t = time.time()
        bot.decide_roll(state, "p0")
        worst = max(worst, time.time() - t)
    assert worst < 0.05, f"dice search took {worst*1000:.0f}ms"


# ---------------------------------------------------------------------------
# Strength
# ---------------------------------------------------------------------------

def _duel_winrate(a, b, n=200):
    """Seat-balanced: the first seat has a big advantage in this game, so play
    both orders and average.

    Sample sizes here are deliberately large. ``gl.do_roll`` builds a fresh
    unseeded ``random.Random()`` per roll, so these games are genuinely
    stochastic no matter what seed is passed - the thresholds below are set
    several standard errors under the measured win rate so a healthy bot does
    not fail CI on a bad night."""
    wins = 0
    for i in range(n):
        seat, _ = play([a, b], seed=i)
        wins += (seat == 0)
    for i in range(n):
        seat, _ = play([b, a], seed=i + 10_000)
        wins += (seat == 1)
    return wins / (2 * n)


@pytest.mark.strength
def test_beats_a_random_player_overwhelmingly():
    class Rando:
        name = "random"

        @staticmethod
        def roll(state, pid):
            if state["roll_num"] == 0:
                return "roll", []
            if state["rolls_left"] <= 0 or random.random() < 0.3:
                return "resolve", None
            return "roll", [i for i in range(len(state["dice"])) if random.random() < 0.5]

        @staticmethod
        def yld(state, pid):
            return random.random() < 0.5

        @staticmethod
        def token(state, pid):
            return 0, 0

        @staticmethod
        def buys(state, pid):
            return []

    # Halved from n=100. Measured mean 0.994, sd 0.007 over 8 reps at n=50, so 0.90
    # is 12.6 sd under it - by far the roomiest of the three, which is why it is the
    # one that can lose half its games without argument.
    assert _duel_winrate(Smart, Rando, n=50) > 0.90


@pytest.mark.strength
def test_beats_a_greedy_player():
    """Re-measured 2026-08-07 over 8 repetitions at n=100 (200 seat-balanced games):
    **mean 0.712, sd 0.031, worst 0.655**, so 0.55 sits 5.3 standard deviations under
    it and a healthy bot will not fail on a bad night. The sample was halved from
    n=200 and the margin is still large.

    The previous note here said "around 62% over 2000 games", and both halves of that
    were wrong: `_duel_winrate` plays `2 * n` games, so the default was 400 rather
    than 2000, and the bot measures 71% rather than 62%. Stale numbers in a docstring
    are worse than none, because the next person sets a threshold from them.
    """
    assert _duel_winrate(Smart, Greedy, n=100) > 0.55


@pytest.mark.strength
def test_wins_a_crowded_table():
    """Three greedy opponents, the bot's seat rotated so position cannot flatter
    it. A fair share would be 25%; measured mean 0.466, sd 0.043 over 8 reps.

    **This one keeps its full sample deliberately.** Halved to n=100 it measures
    sd 0.079 with a worst observed run of 0.32 - i.e. *below* its own 0.35
    threshold, so it would fail outright some nights. At n=200 the threshold sits
    2.7 sd under the mean. A four-way game is far noisier than a duel because
    winning is a 1-in-4 event, so it needs the games the duel can spare.
    """
    n, wins = 200, 0
    for i in range(n):
        seats = [Greedy(), Greedy(), Greedy(), Greedy()]
        pos = i % 4
        seats[pos] = Smart
        seat, _ = play(seats, seed=i + 20_000)
        wins += (seat == pos)
    assert wins / n > 0.35


# ---------------------------------------------------------------------------
# Every card in the box
# ---------------------------------------------------------------------------

ALL_CARD_IDS = sorted(gl._cards().CATALOG)


@pytest.mark.parametrize("cid", ALL_CARD_IDS)
def test_every_card_in_a_bots_hand_still_finishes(cid):
    """Hand the bot each of the 66 cards in turn and make sure the game still
    runs to a winner.

    This is the test that matters most for liveness: several cards open a
    decision window the engine will not leave on its own (Psychic Probe parks
    the whole table in ``probe_window``), and others change the dice tray out
    from under the search (Extra Head, Shrink Ray). A bot that owns one and
    does not answer for it hangs a real game."""
    C = gl._cards().CATALOG[cid]

    def setup(state, pids):
        state["mon"][pids[0]]["cards"].append(cid)
        state["mon"][pids[0]]["energy"] = 12
        gl._cards().on_acquire(state, pids[0], cid)

    for seed in range(2):
        seat, state = play([Smart(), Smart()], seed=seed, setup=setup)
        assert state["phase"] == "ended", f"{C['name']} stalled the game"


def test_bot_holding_psychic_probe_drains_the_window():
    """The probe window blocks every player, so the bot must always answer."""
    def setup(state, pids):
        state["mon"][pids[1]]["cards"].append("psychic_probe")

    for seed in range(6):
        _, state = play([Smart(), Smart(), Smart()], seed=seed, setup=setup)
        assert state["phase"] == "ended"
        assert state.get("pending_probe") in (None, {}) or not state["pending_probe"]["queue"]


def test_no_pending_decision_is_left_dangling():
    for seed in range(8):
        _, state = play([Smart()] * 4, seed=seed)
        assert state["phase"] == "ended"
        assert not (state.get("pending_yield") or {}).get("queue")
        assert not (state.get("pending_probe") or {}).get("queue")
        assert state.get("pending_token_choice") in (None, {})


# ---------------------------------------------------------------------------
# Odd dice trays
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ndice", [1, 2, 3, 5, 6, 7, 8])
def test_any_tray_size_is_handled(ndice):
    """Shrink counters take dice away; Extra Head adds them. The search must
    cope with both without going quadratic or returning an illegal keep."""
    state = gl.new_game(["p0", "p1"], seed=1)
    for rolls_left in (0, 1, 2):
        state["dice"] = [random.choice(gl.FACES) for _ in range(ndice)]
        state["kept"] = [False] * ndice
        state["roll_num"] = 1
        state["rolls_left"] = rolls_left
        t = time.time()
        action, keep = bot.decide_roll(state, "p0")
        assert time.time() - t < 0.5
        assert action in ("roll", "resolve")
        if action == "roll":
            assert all(0 <= i < ndice for i in keep)
            assert len(set(keep)) == len(keep)
            assert len(keep) < ndice     # keeping everything means resolving


def test_large_tray_stays_fast():
    """Extra Head plus Mimic can reach 8 dice; the search still must not block
    the single eventlet worker."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["dice"] = ["claw"] * 4 + ["1", "2", "heart", "energy"]
    state["roll_num"] = 1
    state["rolls_left"] = 2
    bot.decide_roll(state, "p0")
    t = time.time()
    for _ in range(10):
        state["dice"] = [random.choice(gl.FACES) for _ in range(8)]
        bot.decide_roll(state, "p0")
    assert (time.time() - t) / 10 < 0.20


# ---------------------------------------------------------------------------
# Fuzz: no state should make a decision function raise or answer illegally
# ---------------------------------------------------------------------------

def _random_state(rng, n_players=3):
    state = gl.new_game([f"p{i}" for i in range(n_players)], seed=rng.randint(0, 9999))
    pids = state["players"]
    for pid in pids:
        m = state["mon"][pid]
        m["hp"] = rng.randint(0, 12)
        m["maxhp"] = rng.choice([10, 10, 12])
        m["hp"] = min(m["hp"], m["maxhp"])
        m["alive"] = m["hp"] > 0
        m["vp"] = rng.randint(0, 24)
        m["energy"] = rng.randint(0, 30)
        m["tokens"] = {"poison": rng.randint(0, 3), "shrink": rng.randint(0, 3)}
        m["cards"] = rng.sample(ALL_CARD_IDS, rng.randint(0, 4))
    # at least one monster must be standing for the decisions to mean anything
    state["mon"][pids[0]]["alive"] = True
    state["mon"][pids[0]]["hp"] = max(1, state["mon"][pids[0]]["hp"])
    slot = rng.choice([None, "city", "bay"])
    if slot:
        state["tokyo"][slot] = rng.choice(pids)
    ndice = rng.randint(1, 8)
    state["dice"] = [rng.choice(gl.FACES) for _ in range(ndice)]
    state["kept"] = [False] * ndice
    state["roll_num"] = rng.randint(1, 3)
    state["rolls_left"] = rng.randint(0, 2)
    state["shop"] = [rng.choice(ALL_CARD_IDS + [None]) for _ in range(gl.SHOP_SIZE)]
    return state


def test_fuzz_decisions_are_legal():
    rng = random.Random(99)
    for _ in range(400):
        state = _random_state(rng)
        pid = state["players"][0]

        action, keep = bot.decide_roll(state, pid)
        assert action in ("roll", "resolve")
        if action == "roll":
            assert all(0 <= i < len(state["dice"]) for i in keep)
            assert len(set(keep)) == len(keep)

        assert bot.decide_yield(state, pid) in (True, False)

        hearts = rng.randint(1, 4)
        state["pending_token_choice"] = {"pid": pid, "hearts": hearts}
        sp, ss = bot.decide_token_choice(state, pid)
        tok = state["mon"][pid]["tokens"]
        assert 0 <= sp <= tok["poison"] and 0 <= ss <= tok["shrink"]
        assert sp + ss <= hearts

        state["phase"] = "buying"
        plan = bot.decide_buys(state, pid)
        idxs = [i for k, i in plan if k == "buy"]
        assert len(set(idxs)) == len(idxs)
        assert all(0 <= i < len(state["shop"]) and state["shop"][i] for i in idxs)
        assert sum(1 for k, _ in plan if k == "sweep") <= 1

        die = bot.decide_probe(state, pid)
        assert die is None or 0 <= die < len(state["dice"])

        idx = bot.decide_opportunist(state, pid)
        assert idx is None or 0 <= idx < len(state["shop"])


def test_fuzz_buys_are_always_affordable():
    """The engine silently drops an unaffordable buy, which would strand a bot
    in the buying phase, so the plan must never exceed the bank."""
    rng = random.Random(1234)
    cards = gl._cards()
    for _ in range(300):
        state = _random_state(rng)
        pid = state["players"][0]
        state["phase"] = "buying"
        state["current"] = pid
        energy = state["mon"][pid]["energy"]
        discount = gl.mod(state, pid, "buy_discount")
        for kind, i in bot.decide_buys(state, pid):
            if kind == "sweep":
                assert energy >= gl.SWEEP_COST
                energy -= gl.SWEEP_COST
                continue
            cost = max(0, cards.CATALOG[state["shop"][i]]["cost"] - discount)
            assert cost <= energy
            energy -= cost


# ---------------------------------------------------------------------------
# Strategy: the bot should reach the obvious conclusion in obvious spots
# ---------------------------------------------------------------------------

def _forced_keep(state, pid, dice, rolls_left=2):
    state["dice"] = list(dice)
    state["kept"] = [False] * len(dice)
    state["roll_num"] = 1
    state["rolls_left"] = rolls_left
    action, keep = bot.decide_roll(state, pid)
    if action == "resolve":
        return set(range(len(dice)))
    return set(keep)


def test_keeps_the_claw_that_finishes_an_opponent():
    """One claw is lethal to the monster in Tokyo - it must not be rerolled."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["tokyo"]["city"] = "p1"
    state["mon"]["p1"]["hp"] = 1
    state["mon"]["p0"]["hp"] = 10
    keep = _forced_keep(state, "p0", ["claw", "1", "2", "energy", "heart", "3"])
    assert 0 in keep, "kept dice did not include the lethal claw"


def test_keeps_hearts_when_nearly_dead_outside_tokyo():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["tokyo"]["city"] = "p1"
    state["mon"]["p0"]["hp"] = 2
    keep = _forced_keep(state, "p0", ["heart", "heart", "1", "2", "energy", "3"])
    assert {0, 1} <= keep


def test_does_not_keep_hearts_while_in_tokyo():
    """Heart dice cannot heal a monster sitting in Tokyo, so holding them is
    pure waste unless there are counters to shed."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["tokyo"]["city"] = "p0"
    state["mon"]["p0"]["hp"] = 4
    state["mon"]["p0"]["tokens"] = {}
    keep = _forced_keep(state, "p0", ["heart", "heart", "heart", "claw", "energy", "1"])
    assert not ({0, 1, 2} & keep), "held useless hearts in Tokyo"


def test_keeps_a_completed_number_set():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["mon"]["p0"]["hp"] = 10
    keep = _forced_keep(state, "p0", ["3", "3", "3", "heart", "energy", "1"])
    assert {0, 1, 2} <= keep


def test_resolves_when_the_tray_is_already_ideal():
    """Six claws with a knockout on the table - there is nothing to improve."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["tokyo"]["city"] = "p1"
    state["mon"]["p1"]["hp"] = 10
    action, _ = bot.decide_roll(
        dict(state, dice=["claw"] * 6, kept=[False] * 6, roll_num=1, rolls_left=2), "p0")
    assert action == "resolve"


def test_yield_matrix_is_monotonic_in_health():
    """Whatever the thresholds are, being healthier must never make the bot
    more eager to abandon Tokyo."""
    for n in (2, 3, 4):
        state = gl.new_game([f"p{i}" for i in range(n)], seed=1)
        state["tokyo"]["city"] = "p0"
        decisions = []
        for hp in range(1, 11):
            state["mon"]["p0"]["hp"] = hp
            decisions.append(bot.decide_yield(state, "p0"))
        # once it decides to stay, it must not flip back to leaving
        first_stay = next((i for i, d in enumerate(decisions) if not d), len(decisions))
        assert all(not d for d in decisions[first_stay:]), \
            f"{n}p yield decisions not monotonic: {decisions}"


def test_stays_in_tokyo_when_it_would_win_the_game():
    """Two more Tokyo points carries it over 20; worth the risk at high health."""
    state = gl.new_game(["p0", "p1", "p2"], seed=1)
    state["tokyo"]["city"] = "p0"
    state["mon"]["p0"]["vp"] = 18
    state["mon"]["p0"]["hp"] = 9
    assert bot.decide_yield(state, "p0") is False


def test_token_choice_prefers_healing_when_nearly_dead():
    state = gl.new_game(["p0", "p1"], seed=1)
    m = state["mon"]["p0"]
    m["hp"], m["maxhp"] = 2, 10
    m["tokens"] = {"poison": 2, "shrink": 2}
    state["pending_token_choice"] = {"pid": "p0", "hearts": 2}
    sp, ss = bot.decide_token_choice(state, "p0")
    assert sp + ss == 0, "burned hearts on counters while about to die"


def test_token_choice_sheds_poison_when_healthy():
    state = gl.new_game(["p0", "p1"], seed=1)
    m = state["mon"]["p0"]
    m["hp"], m["maxhp"] = 10, 10
    m["tokens"] = {"poison": 2, "shrink": 0}
    state["pending_token_choice"] = {"pid": "p0", "hearts": 2}
    sp, ss = bot.decide_token_choice(state, "p0")
    assert sp == 2


def test_buys_nothing_with_no_energy():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["phase"] = "buying"
    state["mon"]["p0"]["energy"] = 0
    assert bot.decide_buys(state, "p0") == []


def test_buys_something_when_rich():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["phase"] = "buying"
    state["mon"]["p0"]["energy"] = 30
    assert bot.decide_buys(state, "p0"), "sat on 30 energy and bought nothing"


def test_empty_shop_is_handled():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["phase"] = "buying"
    state["shop"] = [None, None, None]
    state["mon"]["p0"]["energy"] = 20
    plan = bot.decide_buys(state, "p0")
    assert all(k != "buy" for k, _ in plan)


def test_refuses_a_discard_card_that_would_kill_it():
    """Jet Fighters is +5 VP and 4 damage. On 3 HP that is suicide, and the
    engine will not stop you."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["phase"] = "buying"
    state["mon"]["p0"]["hp"] = 3
    state["mon"]["p0"]["energy"] = 20
    state["shop"] = ["jet_fighters", None, None]
    assert all(k != "buy" for k, _ in bot.decide_buys(state, "p0"))


def test_probe_passes_when_the_roll_is_harmless():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["current"] = "p1"
    state["dice"] = ["heart", "energy", "1", "2", "heart", "energy"]
    assert bot.decide_probe(state, "p0") is None


def test_probe_breaks_up_a_scoring_set():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["current"] = "p1"
    state["mon"]["p1"]["vp"] = 16
    state["dice"] = ["3", "3", "3", "heart", "energy", "1"]
    die = bot.decide_probe(state, "p0")
    assert die is not None and state["dice"][die] == "3"


def test_probe_never_targets_the_roller_it_is():
    state = gl.new_game(["p0", "p1"], seed=1)
    state["current"] = "p0"
    assert bot.decide_probe(state, "p0") is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_decisions_are_deterministic_without_the_slip():
    """With the human-inconsistency roll disabled, the same position must
    always produce the same move - otherwise the weights cannot be tuned."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["dice"] = ["claw", "claw", "1", "2", "heart", "energy"]
    state["roll_num"] = 1
    state["rolls_left"] = 2
    fixed = random.Random(0)

    class NoSlip:
        @staticmethod
        def random():
            return 1.0          # never below SLIP_CHANCE

    first = bot.decide_roll(state, "p0", rng=NoSlip)
    for _ in range(20):
        assert bot.decide_roll(state, "p0", rng=NoSlip) == first
    assert fixed is not None


def test_slip_stays_within_a_hair_of_the_best_line():
    """The bot is allowed to look human, not to blunder."""
    state = gl.new_game(["p0", "p1"], seed=1)
    state["dice"] = ["claw", "claw", "claw", "2", "heart", "energy"]
    state["roll_num"] = 1
    state["rolls_left"] = 2
    ctx = bot._ctx(state, "p0")
    memo = {}
    ranked = bot._ranked_keeps(bot._counts(state["dice"]), 2, ctx, memo)
    seen = set()
    rng = random.Random(5)
    for _ in range(200):
        _, keep = bot.decide_roll(state, "p0", rng=rng)
        seen.add(tuple(keep) if keep is not None else None)
    # every line the bot actually plays is at worst a hair off the best one
    best = ranked[0][0]
    allowed = {k for v, k in ranked if v >= best - 0.35}
    for keep in seen:
        if keep is None:
            continue
        counts = [0] * 6
        for i in keep:
            counts[gl.FACES.index(state["dice"][i])] += 1
        assert tuple(counts) in allowed
