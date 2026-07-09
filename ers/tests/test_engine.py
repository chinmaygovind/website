"""Rules coverage for the Egyptian Rat Screw engine."""

import game_logic as gl
from game_logic import flip, slap, slap_reasons, award_pile, resolve_pending, new_deal


def C(rank, suit="♠"):
    return {"rank": rank, "suit": suit}


def mk(hands, current=None, pile=None, challenge=None, rules=("ten", "kingqueen")):
    players = list(hands.keys())
    return {
        "players": players,
        "hands": {k: list(v) for k, v in hands.items()},
        "pile": list(pile or []),
        "current": current or players[0],
        "challenge": challenge,
        "eliminated": [],
        "pending_win": None,
        "slap_locked": [],
        "phase": "playing",
        "winner": None,
        "rules": list(rules),
        "turns": 0,
        "standings": [],
        "log": [],
        "seq": 0,
    }


# ----- deal --------------------------------------------------------------

def test_even_deal_four():
    s = new_deal(["A", "B", "C", "D"], seed=1)
    assert [len(s["hands"][p]) for p in s["players"]] == [13, 13, 13, 13]
    all_cards = [tuple(c.values()) for p in s["players"] for c in s["hands"][p]]
    assert len(set(all_cards)) == 52


def test_even_deal_three():
    s = new_deal(["A", "B", "C"], seed=1)
    assert sorted(len(s["hands"][p]) for p in s["players"]) == [17, 17, 18]


# ----- slap detection ----------------------------------------------------

def test_double():
    assert "double" in slap_reasons([C(3), C(7), C(7)], gl.DEFAULT_RULES)


def test_sandwich():
    r = slap_reasons([C(5), C(9), C(5)], gl.DEFAULT_RULES)
    assert "sandwich" in r and "double" not in r


def test_top_bottom():
    r = slap_reasons([C(8), C(2), C(3), C(8)], gl.DEFAULT_RULES)
    assert "top_bottom" in r and "double" not in r


def test_add_to_ten():
    assert "ten" in slap_reasons([C(6), C(4)], gl.DEFAULT_RULES)
    assert "ten" in slap_reasons([C(14), C(9)], gl.DEFAULT_RULES)  # A(=1)+9
    assert "ten" not in slap_reasons([C(10), C(2)], gl.DEFAULT_RULES)


def test_king_queen():
    assert "kingqueen" in slap_reasons([C(13), C(12)], gl.DEFAULT_RULES)
    assert "kingqueen" in slap_reasons([C(12), C(13)], gl.DEFAULT_RULES)


def test_no_slap():
    assert slap_reasons([C(2), C(9)], gl.DEFAULT_RULES) == []


def test_ten_disabled_when_rule_off():
    assert slap_reasons([C(6), C(4)], ["kingqueen"]) == []


# ----- slapping ----------------------------------------------------------

def test_valid_slap_wins_pile():
    s = mk({"A": [C(7)], "B": [C(9)]}, pile=[C(4), C(4)], current="A")
    slap(s, "B")
    assert s["pile"] == []
    assert len(s["hands"]["B"]) == 3  # own card + the 2-card pile
    assert s["current"] == "B"


def test_false_slap_burns_and_locks():
    s = mk({"A": [C(2), C(3), C(4)]}, pile=[C(7), C(9)])
    ev = slap(s, "A")
    assert ev[0]["type"] == "false_slap" and ev[0]["burned"] == 1
    assert s["hands"]["A"] == [C(3), C(4)]     # one card burned off the top
    assert s["pile"][0] == C(2)                # burned to the bottom of the pile
    assert s["last_burn"]["card"] == C(2) and s["last_burn"]["pid"] == "A"
    assert "A" in s["slap_locked"]
    assert slap(s, "A") == []                  # locked out until next flip


def test_slap_back_in_from_zero_cards():
    s = mk({"A": [C(7)], "B": []}, current="A", pile=[C(4), C(4)])
    slap(s, "B")
    assert s["hands"]["B"] == [C(4), C(4)]
    assert "B" not in s["eliminated"]
    assert s["phase"] == "playing"


# ----- tribute -----------------------------------------------------------

def test_king_tribute_three_then_fail():
    s = mk({"A": [C(13), C(2)], "B": [C(3), C(4), C(5)]}, current="A")
    flip(s, "A")                       # King -> challenge 3, turn to B
    assert s["challenge"]["chances_left"] == 3 and s["current"] == "B"
    flip(s, "B"); flip(s, "B"); flip(s, "B")   # 3 non-royalty -> fail
    assert s["pending_win"]["pid"] == "A"
    resolve_pending(s)
    assert s["winner"] == "A"
    assert "B" in s["eliminated"]


def test_tribute_passes_on_royalty():
    s = mk({"A": [C(13)], "B": [C(12), C(2)], "C": [C(3), C(4)]}, current="A")
    flip(s, "A")                       # King -> B owes 3
    flip(s, "B")                       # Queen -> passes to C, C owes 2
    assert s["challenge"]["beneficiary"] == "B" and s["current"] == "C"
    flip(s, "C"); flip(s, "C")         # 2 non-royalty -> C fails
    resolve_pending(s)
    assert s["winner"] == "B"


def test_slap_beats_tribute_fail():
    s = mk({"A": [C(2)], "B": [C(3)]}, pile=[C(5), C(5)])
    s["pending_win"] = {"pid": "A", "reason": "tribute"}
    slap(s, "B")                       # valid double beats the pending collection
    assert s["hands"]["B"] == [C(3), C(5), C(5)]
    assert s["pending_win"] is None
    assert resolve_pending(s) == []    # nothing left to resolve


# ----- standings / win ---------------------------------------------------

def test_standings_and_win_places():
    s = mk({"A": [C(13), C(2)], "B": [C(3), C(4), C(5)]}, current="A")
    flip(s, "A"); flip(s, "B"); flip(s, "B"); flip(s, "B")
    resolve_pending(s)
    places = {st["pid"]: st["place"] for st in s["standings"]}
    assert places == {"A": 1, "B": 2}
    assert all("turns_lasted" in st for st in s["standings"])


def _play_no_slaps(seed):
    s = new_deal(["A", "B", "C", "D"], seed=seed)
    for _ in range(200000):
        if s["phase"] == "ended":
            break
        if s["pending_win"]:
            resolve_pending(s)
            continue
        cur = s["current"]
        if not s["hands"][cur]:
            resolve_pending(s)
            break
        flip(s, cur)
    return s


def test_full_game_terminates_and_conserves_cards():
    for seed in range(6):
        s = _play_no_slaps(seed)
        assert s["phase"] == "ended", f"seed {seed} did not end"
        assert s["winner"] is not None
        assert len(s["hands"][s["winner"]]) == 52
        assert s["pile"] == []
        assert len(s["standings"]) == 4
        assert sorted(st["place"] for st in s["standings"]) == [1, 2, 3, 4]
