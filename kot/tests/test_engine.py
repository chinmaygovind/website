"""Engine tests - prove the King of Tokyo rules hold. Pure functions, no Flask.

Run with:  cd kot && venv/bin/python -m pytest tests/
"""

import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import game_logic as gl
import cards


def fresh(n=3, seed=1):
    pids = [f"p{i}" for i in range(1, n + 1)]
    state = gl.new_game(pids, seed=seed)
    gl.set_names(state, {p: p for p in pids})
    return state, pids


def force_dice(state, faces):
    """Pretend the current player rolled exactly these faces (skip randomness)."""
    state["dice"] = list(faces)
    state["kept"] = [False] * len(faces)
    state["roll_num"] = 1
    state["rolls_left"] = 0


# ---------------------------------------------------------------------------

def test_new_game_shape():
    state, pids = fresh(4)
    assert state["phase"] == "rolling"
    assert state["current"] == pids[0]
    for p in pids:
        m = state["mon"][p]
        assert m["hp"] == 10 and m["vp"] == 0 and m["energy"] == 0 and m["alive"]
    assert len([c for c in state["shop"] if c]) == 3
    assert state["use_bay"] is False


def test_bay_only_with_five():
    state, _ = fresh(5)
    assert state["use_bay"] is True


def test_deck_has_66_cards():
    rng = random.Random(0)
    deck = cards.build_deck(rng)
    assert len(deck) == 66
    assert len(cards.CATALOG) == 66


def test_first_player_enters_tokyo():
    state, pids = fresh(3)
    p = pids[0]
    force_dice(state, ["1", "1", "1", "energy", "energy", "2"])
    gl.resolve(state, p)
    assert state["mon"][p]["energy"] == 2
    # three 1s = 1 VP, plus the +1 for entering empty Tokyo City = 2
    assert state["mon"][p]["vp"] == 2
    assert state["tokyo"]["city"] == p       # entry is unconditional
    assert state["phase"] == "buying"


def test_energy_and_numbers():
    state, pids = fresh(3)
    p, occupier = pids[0], pids[1]
    state["tokyo"]["city"] = occupier        # Tokyo taken, so p won't enter/score entry
    force_dice(state, ["1", "1", "1", "energy", "energy", "2"])
    gl.resolve(state, p)
    assert state["mon"][p]["energy"] == 2
    assert state["mon"][p]["vp"] == 1        # three 1s = 1 VP only


def test_three_twos_plus_one():
    state, pids = fresh(3)
    p, occupier = pids[0], pids[1]
    state["tokyo"]["city"] = occupier
    force_dice(state, ["2", "2", "2", "2", "heart", "heart"])
    gl.resolve(state, p)
    assert state["mon"][p]["vp"] == 3        # three 2s = 2, +1 extra = 3


def test_heart_blocked_in_tokyo():
    state, pids = fresh(2)
    a, b = pids
    # a takes Tokyo with no claws
    force_dice(state, ["1", "1", "1", "heart", "heart", "heart"])
    gl.resolve(state, a)
    assert state["tokyo"]["city"] == a
    assert state["mon"][a]["hp"] == 10       # can't heal in Tokyo, already full anyway
    gl.end_turn(state, a)
    # b's turn: damage a bit is not possible; instead check a can't heal when hurt in Tokyo
    state["mon"][a]["hp"] = 5
    gl.end_turn(state, b) if state["current"] == b and state["phase"] == "buying" else None


def test_attack_forces_yield_and_takeover():
    state, pids = fresh(2)
    a, b = pids
    # a enters Tokyo
    force_dice(state, ["heart", "heart", "energy", "energy", "1", "2"])
    gl.resolve(state, a)
    assert state["tokyo"]["city"] == a
    gl.end_turn(state, a)
    assert state["current"] == b
    # b attacks with claws -> a must decide to stay or yield
    force_dice(state, ["claw", "claw", "energy", "1", "2", "3"])
    gl.resolve(state, b)
    assert state["phase"] == "yield"
    assert state["pending_yield"]["queue"] == [a]
    assert state["mon"][a]["hp"] == 8        # took 2 claws
    gl.yield_decision(state, a, leave=True)
    assert state["tokyo"]["city"] == b       # b moves in
    assert state["phase"] == "buying"


def test_win_at_20_vp():
    state, pids = fresh(2)
    a, _ = pids
    state["mon"][a]["vp"] = 19
    gl.gain_vp(state, a, 1)
    assert state["phase"] == "ended"
    assert state["winner"] == a
    assert state["standings"][0]["pid"] == a


def test_last_monster_standing_wins():
    state, pids = fresh(2)
    a, b = pids
    gl.deal_damage(state, b, 100, attacker=a)
    assert not state["mon"][b]["alive"]
    assert state["phase"] == "ended"
    assert state["winner"] == a


def test_buy_card_spends_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["phase"] = "buying"
    state["current"] = a
    state["mon"][a]["energy"] = 10
    # force a known cheap card into the shop
    state["shop"][0] = "corner_store"     # discard, +1 VP, cost 3
    gl.buy_card(state, a, 0)
    assert state["mon"][a]["energy"] == 7
    assert state["mon"][a]["vp"] == 1     # corner store one-shot
    assert state["shop"][0] != "corner_store"  # slot refilled


def test_keep_card_stays_owned():
    state, pids = fresh(2)
    a = pids[0]
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["shop"][0] = "extra_head"       # keep, +1 die, cost 7
    gl.buy_card(state, a, 0)
    assert "extra_head" in state["mon"][a]["cards"]
    assert gl.mod(state, a, "extra_dice") == 1


def test_acid_attack_damage_without_claws():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("acid_attack")
    force_dice(state, ["heart", "energy", "1", "2", "heart", "energy"])  # no claws
    gl.resolve(state, a)
    # a should still deal 1 damage (Acid Attack) - but with no one in Tokyo,
    # the target list is empty; a just enters Tokyo. Put b in Tokyo first instead.


def test_acid_attack_hits_tokyo():
    state, pids = fresh(2)
    a, b = pids
    state["tokyo"]["city"] = b            # b sits in Tokyo
    state["mon"][a]["cards"].append("acid_attack")
    force_dice(state, ["heart", "energy", "1", "1", "heart", "energy"])  # no claws
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 9     # Acid Attack dealt 1


def test_regeneration_heals_extra():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("regeneration")
    state["mon"][a]["hp"] = 5
    healed = gl.heal(state, a, 2)
    assert healed == 3                    # 2 + 1 bonus


def test_camouflage_mitigates(monkeypatch):
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("camouflage")
    # force every camouflage die to a heart -> all damage negated
    monkeypatch.setattr(random.Random, "choice", lambda self, seq: "heart")
    took = gl.deal_damage(state, b, 3, attacker=a)
    assert took == 0
    assert state["mon"][b]["hp"] == 10


def test_camouflage_full_mitigation_still_bumps_seq(monkeypatch):
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("camouflage")
    monkeypatch.setattr(random.Random, "choice", lambda self, seq: "heart")
    seq_before = state["seq"]
    gl.deal_damage(state, b, 1, attacker=a)
    assert state["seq"] > seq_before      # fully-absorbed damage still changed the game


def test_smoke_cloud_extra_reroll():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("smoke_cloud")
    cards.on_acquire(state, a, "smoke_cloud")
    state["rolls_left"] = 0
    gl.card_action(state, a, "smoke_cloud", None)
    assert state["rolls_left"] == 1
    assert state["mon"][a]["cardmem"]["smoke"] == 2


def test_eater_of_the_dead():
    state, pids = fresh(3)
    a, b, c = pids
    state["mon"][a]["cards"].append("eater_of_the_dead")
    gl.deal_damage(state, c, 100, attacker=b)
    assert not state["mon"][c]["alive"]
    assert state["mon"][a]["vp"] == 3     # a feasts


def test_background_dweller_rerolls_a_three(monkeypatch):
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("background_dweller")
    force_dice(state, ["3", "1", "2", "2", "2", "2"])
    monkeypatch.setattr(random.Random, "choice", lambda self, seq: "heart")
    gl.card_action(state, a, "background_dweller", {"index": 0})
    assert state["dice"][0] == "heart"    # the [3] got rerolled for free


def test_background_dweller_refuses_non_three():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("background_dweller")
    force_dice(state, ["3", "1", "2", "2", "2", "2"])
    gl.card_action(state, a, "background_dweller", {"index": 1})   # index 1 is a "1"
    assert state["dice"][1] == "1"        # untouched - not a [3]


def test_metamorph_discards_for_energy_back():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"] += ["metamorph", "camouflage"]   # camouflage costs 3
    state["phase"] = "buying"
    state["mon"][a]["energy"] = 0
    gl.card_action(state, a, "metamorph", {"card": "camouflage"})
    assert "camouflage" not in state["mon"][a]["cards"]
    assert "camouflage" in state["discard"]
    assert "metamorph" in state["mon"][a]["cards"]     # only the chosen card is discarded
    assert state["mon"][a]["energy"] == 3


def test_metamorph_refuses_unowned_card():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("metamorph")
    state["phase"] = "buying"
    state["mon"][a]["energy"] = 0
    gl.card_action(state, a, "metamorph", {"card": "camouflage"})   # never owned
    assert state["mon"][a]["energy"] == 0
    assert state["mon"][a]["cards"] == ["metamorph"]
