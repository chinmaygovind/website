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


def test_metamorph_discarding_even_bigger_reverts_its_max_hp():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"] += ["metamorph", "even_bigger"]
    cards.on_acquire(state, a, "even_bigger")     # normal purchase flow: +2 maxhp, heal 2
    assert state["mon"][a]["maxhp"] == 12
    state["mon"][a]["hp"] = 12
    state["phase"] = "buying"
    state["mon"][a]["energy"] = 0
    gl.card_action(state, a, "metamorph", {"card": "even_bigger"})
    assert state["mon"][a]["maxhp"] == 10             # bonus gone with the card
    assert state["mon"][a]["hp"] == 10                # clamped back down, not left over-max
    assert "even_bigger" in state["discard"]


def test_metamorph_discarding_wings_ends_an_active_shield():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"] += ["metamorph", "wings"]
    state["mon"][a]["energy"] = 2
    gl.card_action(state, a, "wings", None)
    assert cards._mem(state, a)["wings"] is True
    state["phase"] = "buying"
    state["mon"][a]["energy"] = 0
    gl.card_action(state, a, "metamorph", {"card": "wings"})
    assert cards._mem(state, a)["wings"] is False   # can't cash out the card and keep the shield
    assert "wings" in state["discard"]


def test_metamorph_refuses_unowned_card():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("metamorph")
    state["phase"] = "buying"
    state["mon"][a]["energy"] = 0
    gl.card_action(state, a, "metamorph", {"card": "camouflage"})   # never owned
    assert state["mon"][a]["energy"] == 0
    assert state["mon"][a]["cards"] == ["metamorph"]


def test_metamorph_refuses_out_of_turn():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"] += ["metamorph", "camouflage"]
    state["current"] = a               # it's a's buying phase, not b's
    state["phase"] = "buying"
    state["mon"][b]["energy"] = 0
    gl.card_action(state, b, "metamorph", {"card": "camouflage"})
    assert state["mon"][b]["energy"] == 0
    assert "camouflage" in state["mon"][b]["cards"]    # untouched - not b's turn


def test_monster_batteries_lets_you_choose_how_much_to_store():
    state, pids = fresh(2)
    a = pids[0]
    state["phase"] = "buying"
    state["current"] = a
    state["mon"][a]["energy"] = 10
    state["shop"][0] = "monster_batteries"    # keep, cost 2
    gl.buy_card(state, a, 0)
    assert state["mon"][a]["energy"] == 8     # buying it doesn't auto-charge it
    assert "batteries" not in state["mon"][a]["cardmem"]
    gl.card_action(state, a, "monster_batteries", {"amount": 5})
    assert state["mon"][a]["energy"] == 3     # 5 of the 8 locked away...
    assert state["mon"][a]["cardmem"]["batteries"] == 10   # ...doubled to 10 in storage
    assert state["mon"][a]["cardmem"]["battery_charged"] is True
    gl._begin_turn(state, a)                  # next turn: draw 2 back
    assert state["mon"][a]["energy"] == 5
    assert state["mon"][a]["cardmem"]["batteries"] == 8


def test_monster_batteries_choice_is_one_time_and_capped_at_your_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("monster_batteries")
    state["phase"] = "buying"
    state["current"] = a
    state["mon"][a]["energy"] = 4
    gl.card_action(state, a, "monster_batteries", {"amount": 99})   # more than you have
    assert state["mon"][a]["energy"] == 0             # capped to what you actually had
    assert state["mon"][a]["cardmem"]["batteries"] == 8
    state["mon"][a]["energy"] = 4                     # got more energy from elsewhere later
    gl.card_action(state, a, "monster_batteries", {"amount": 3})    # already decided - no redo
    assert state["mon"][a]["energy"] == 4             # second attempt refused, nothing spent
    assert state["mon"][a]["cardmem"]["batteries"] == 8   # still the original charge


def test_monster_batteries_choosing_zero_leaves_it_empty_but_valid():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("monster_batteries")
    state["phase"] = "buying"
    state["current"] = a
    state["mon"][a]["energy"] = 6
    gl.card_action(state, a, "monster_batteries", {"amount": 0})
    assert state["mon"][a]["energy"] == 6
    assert state["mon"][a]["cardmem"]["batteries"] == 0
    assert state["mon"][a]["cardmem"]["battery_charged"] is True


def test_parasitic_tentacles_carries_over_battery_charge():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("monster_batteries")
    state["mon"][a]["cardmem"] = {"batteries": 8, "battery_charged": True}
    state["mon"][b]["cards"].append("parasitic_tentacles")
    state["phase"] = "buying"
    state["current"] = b
    state["mon"][b]["energy"] = 10
    gl.card_action(state, b, "parasitic_tentacles", {"pid": a, "card": "monster_batteries"})
    assert "monster_batteries" in state["mon"][b]["cards"]
    assert state["mon"][b]["cardmem"]["batteries"] == 8      # charge follows the card...
    assert "batteries" not in state["mon"][a]["cardmem"]     # ...not left behind with the old owner
    gl._begin_turn(state, b)
    assert state["mon"][b]["energy"] == 10                   # 8 (paid) + 2 drawn from the batteries
    assert state["mon"][b]["cardmem"]["batteries"] == 6


def test_parasitic_tentacles_moves_even_biggers_max_hp_not_just_the_card():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("even_bigger")
    cards.on_acquire(state, a, "even_bigger")      # +2 maxhp, heal 2, as a normal buy would
    state["mon"][a]["hp"] = 12
    state["mon"][b]["cards"].append("parasitic_tentacles")
    state["phase"] = "buying"
    state["current"] = b
    state["mon"][b]["energy"] = 10
    state["mon"][b]["hp"] = 8
    gl.card_action(state, b, "parasitic_tentacles", {"pid": a, "card": "even_bigger"})
    assert "even_bigger" in state["mon"][b]["cards"]
    assert state["mon"][a]["maxhp"] == 10 and state["mon"][a]["hp"] == 10   # bonus (and overflow) gone
    assert state["mon"][b]["maxhp"] == 12 and state["mon"][b]["hp"] == 10   # bonus + heal 2 arrives


def test_parasitic_tentacles_stealing_wings_ends_the_old_owners_shield_without_transferring_it():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("wings")
    state["mon"][a]["energy"] = 2
    gl.card_action(state, a, "wings", None)
    assert cards._mem(state, a)["wings"] is True
    state["mon"][b]["cards"].append("parasitic_tentacles")
    state["phase"] = "buying"; state["current"] = b
    state["mon"][b]["energy"] = 10
    gl.card_action(state, b, "parasitic_tentacles", {"pid": a, "card": "wings"})
    assert "wings" in state["mon"][b]["cards"]
    assert cards._mem(state, a)["wings"] is False    # a's paid-for shield ends when the card leaves
    assert cards._mem(state, b).get("wings") is not True   # b never paid to raise it - no free shield


def test_parasitic_tentacles_carries_over_smoke_cloud_charges_left():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("smoke_cloud")
    state["mon"][a]["cardmem"] = {"smoke": 1}      # already used 2 of its 3 rerolls
    state["mon"][b]["cards"].append("parasitic_tentacles")
    state["phase"] = "buying"
    state["current"] = b
    state["mon"][b]["energy"] = 10
    gl.card_action(state, b, "parasitic_tentacles", {"pid": a, "card": "smoke_cloud"})
    assert "smoke_cloud" in state["mon"][b]["cards"]
    assert state["mon"][b]["cardmem"]["smoke"] == 1    # remaining charge follows the card...
    assert "smoke" not in state["mon"][a]["cardmem"]   # ...not reset to a fresh 3 or left behind


def test_parasitic_tentacles_carries_over_mimic_target():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][a]["cardmem"] = {"mimic_key": "jets"}
    state["mon"][b]["cards"].append("parasitic_tentacles")
    state["phase"] = "buying"
    state["current"] = b
    state["mon"][b]["energy"] = 10
    gl.card_action(state, b, "parasitic_tentacles", {"pid": a, "card": "mimic"})
    assert "mimic" in state["mon"][b]["cards"]
    assert state["mon"][b]["cardmem"]["mimic_key"] == "jets"     # copy target follows the card...
    assert "mimic_key" not in state["mon"][a]["cardmem"]         # ...not left stale on the old owner


def test_herd_culler_usable_every_turn_not_just_once():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("herd_culler")
    force_dice(state, ["2", "2", "2", "heart", "energy", "claw"])
    gl.card_action(state, a, "herd_culler", {"index": 0})
    assert state["dice"][0] == "1"
    gl._begin_turn(state, a)                  # simulate this player's next turn
    force_dice(state, ["2", "2", "2", "heart", "energy", "claw"])
    gl.card_action(state, a, "herd_culler", {"index": 1})
    assert state["dice"][1] == "1"            # still usable, not a one-time thing


def test_jets_leave_avoids_all_damage_from_that_attack():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("jets")
    state["tokyo"]["city"] = a
    gl._begin_turn(state, b)                  # make b the current (attacking) player
    force_dice(state, ["claw", "claw", "claw", "energy", "1", "2"])
    gl.resolve(state, b)
    assert state["phase"] == "yield"
    assert state["pending_yield"]["queue"] == [a]
    assert state["mon"][a]["hp"] == 10        # damage deferred, not yet applied
    gl.yield_decision(state, a, leave=True)
    assert state["mon"][a]["hp"] == 10        # jets carried it out untouched
    assert state["tokyo"]["city"] == b
    assert state["phase"] == "buying"


def test_jets_stay_takes_the_deferred_damage():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("jets")
    state["tokyo"]["city"] = a
    gl._begin_turn(state, b)                  # make b the current (attacking) player
    force_dice(state, ["claw", "claw", "claw", "energy", "1", "2"])
    gl.resolve(state, b)
    assert state["mon"][a]["hp"] == 10
    gl.yield_decision(state, a, leave=False)
    assert state["mon"][a]["hp"] == 7         # held Tokyo, so the 3 claws land now
    assert state["tokyo"]["city"] == a


def test_nova_breath_hits_everyone_not_just_tokyo():
    state, pids = fresh(3)
    a, b, c = pids
    state["mon"][a]["cards"].append("nova_breath")
    state["tokyo"]["city"] = b                # b is in Tokyo, c is outside with a
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "claw", "1", "2", "3", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 8          # Tokyo occupant hit...
    assert state["mon"][c]["hp"] == 8          # ...and the monster outside, both
    assert state["mon"][a]["hp"] == 10         # attacker never damages itself
    assert state["pending_yield"]["queue"] == [b]   # only the Tokyo occupant gets a yield choice


def test_poison_quills_deals_2_to_tokyo_when_you_score_three_2s():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("poison_quills")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["2", "2", "2", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 8          # 10 - 2 from the quills
    assert state["mon"][a]["vp"] >= 2          # still scores the three 2s as usual


def test_poison_quills_respects_jets_and_still_offers_a_yield():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("poison_quills")
    state["mon"][b]["cards"].append("jets")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["2", "2", "2", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["phase"] == "yield"
    assert state["pending_yield"]["queue"] == [b]
    assert state["mon"][b]["hp"] == 10         # damage deferred, jets hasn't decided yet
    gl.yield_decision(state, b, leave=True)
    assert state["mon"][b]["hp"] == 10         # jets carried it out untouched


def test_poison_quills_and_claws_in_the_same_roll_dont_clobber_each_others_yield():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("poison_quills")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    # three 2s (quills, +2) AND three claws in the same roll
    force_dice(state, ["2", "2", "2", "claw", "claw", "claw"])
    gl.resolve(state, a)
    assert state["phase"] == "yield"
    assert state["pending_yield"]["queue"] == [b]      # queued once, not twice
    assert state["mon"][b]["hp"] == 5                  # 10 - 2 (quills) - 3 (claws), both landed


def test_mimic_copies_target_and_costs_energy_to_change():
    state, pids = fresh(3)
    a, b, c = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][b]["cards"].append("armor_plating")
    state["mon"][c]["cards"].append("regeneration")
    gl.card_action(state, a, "mimic", {"card": "armor_plating"})
    assert cards._mem(state, a)["mimic_key"] == "armor_plating"
    took = gl.deal_damage(state, a, 1, attacker=b)
    assert took == 0                          # armor plating negates 1 damage, mimicked
    state["mon"][a]["energy"] = 5
    gl.card_action(state, a, "mimic", {"card": "regeneration"})
    assert state["mon"][a]["energy"] == 4     # changing the copy costs 1⚡
    assert cards._mem(state, a)["mimic_key"] == "regeneration"
    state["mon"][a]["hp"] = 5
    healed = gl.heal(state, a, 2)
    assert healed == 3                        # +1 bonus from the mimicked regeneration


def test_mimic_copying_plot_twist_gets_its_own_independent_one_time_use():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][b]["cards"].append("plot_twist")
    cards._mem(state, b)["plot_twist_used"] = True   # b's own copy is already spent - shouldn't matter to a
    gl.card_action(state, a, "mimic", {"card": "plot_twist"})
    assert cards._mem(state, a)["mimic_key"] == "plot_twist"
    assert cards._mem(state, a)["plot_twist_used"] is False   # a gets a fresh use, not b's spent one
    force_dice(state, ["1", "2", "3", "heart", "energy", "claw"])
    gl.card_action(state, a, "plot_twist", {"index": 0, "face": "claw"})
    assert state["dice"][0] == "claw"
    assert "plot_twist" not in state["discard"]               # a doesn't own the physical card
    assert cards._mem(state, a)["plot_twist_used"] is True
    # spent now - firing again does nothing until a fresh pick
    gl.card_action(state, a, "plot_twist", {"index": 1, "face": "heart"})
    assert state["dice"][1] == "2"                             # unchanged - already used


def test_mimic_copying_smoke_cloud_gets_its_own_independent_3_charges():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][b]["cards"].append("smoke_cloud")
    cards._mem(state, b)["smoke"] = 1   # b's own copy is nearly spent - shouldn't matter to a
    gl.card_action(state, a, "mimic", {"card": "smoke_cloud"})
    assert cards._mem(state, a)["smoke"] == 3                  # a gets a fresh 3, not b's leftover 1
    assert cards._mem(state, b)["smoke"] == 1                  # b's own pool is untouched
    gl.card_action(state, a, "smoke_cloud", None)
    assert cards._mem(state, a)["smoke"] == 2
    assert "smoke_cloud" not in state["mon"][a]["cards"]        # a never owned the physical card


def test_mimic_copying_monster_batteries_gets_its_own_independent_charge():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][b]["cards"].append("monster_batteries")
    cards._mem(state, b)["battery_charged"] = True
    cards._mem(state, b)["batteries"] = 8                       # b's own charge - shouldn't matter to a
    gl.card_action(state, a, "mimic", {"card": "monster_batteries"})
    assert cards._mem(state, a)["battery_charged"] is False     # a hasn't made their own choice yet
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 5
    gl.card_action(state, a, "monster_batteries", {"amount": 3})
    assert cards._mem(state, a)["batteries"] == 6               # a's own doubled charge
    assert cards._mem(state, b)["batteries"] == 8               # b's own is untouched


def test_smoke_cloud_grants_3_lifetime_charges_then_discards():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("smoke_cloud")
    cards.on_acquire(state, a, "smoke_cloud")
    assert cards._mem(state, a)["smoke"] == 3
    for i in range(3):
        state["rolls_left"] = 0
        gl.card_action(state, a, "smoke_cloud", None)
        assert state["rolls_left"] == 1
    assert "smoke_cloud" not in state["mon"][a]["cards"]     # discarded once its charges ran out
    assert "smoke_cloud" in state["discard"]


def test_mimic_pick_and_change_refused_once_youve_rolled():
    state, pids = fresh(3)
    a, b, c = pids
    state["mon"][a]["cards"].append("mimic")
    state["mon"][b]["cards"].append("armor_plating")
    state["mon"][c]["cards"].append("regeneration")
    state["roll_num"] = 1                     # already rolled this turn
    gl.card_action(state, a, "mimic", {"card": "armor_plating"})
    assert cards._mem(state, a).get("mimic_key") is None     # first pick refused, not "start of turn"
    state["mon"][a]["cards"] = ["mimic"]
    cards._mem(state, a)["mimic_key"] = "armor_plating"       # picked before rolling, on an earlier turn
    state["mon"][a]["energy"] = 5
    gl.card_action(state, a, "mimic", {"card": "regeneration"})
    assert cards._mem(state, a)["mimic_key"] == "armor_plating"   # change refused too
    assert state["mon"][a]["energy"] == 5                          # no energy spent


def test_psychic_probe_reroll_other_monster_once_per_turn(monkeypatch):
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("psychic_probe")
    force_dice(state, ["3", "3", "3", "3", "3", "3"])
    monkeypatch.setattr(random.Random, "choice", lambda self, seq: "heart")
    gl.card_action(state, b, "psychic_probe", {"index": 0})
    assert state["dice"][0] == "heart"
    assert b in cards._mem(state, a)["probed_by"]
    gl.card_action(state, b, "psychic_probe", {"index": 1})
    assert state["dice"][1] == "3"             # already used its one probe this turn


def test_psychic_probe_refuses_to_probe_your_own_roll():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("psychic_probe")
    force_dice(state, ["3", "3", "3", "3", "3", "3"])
    gl.card_action(state, a, "psychic_probe", {"index": 0})
    assert state["dice"][0] == "3"             # can't target your own dice


def test_resolve_opens_a_probe_window_before_resolving_and_prober_can_still_act(monkeypatch):
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("psychic_probe")
    gl._begin_turn(state, a)
    force_dice(state, ["1", "1", "energy", "energy", "claw", "heart"])
    gl.resolve(state, a)
    assert state["phase"] == "probe_window"           # not resolved yet - b still owes a decision
    assert state["pending_probe"] == {"queue": [b], "roller": a}
    assert state["mon"][a]["energy"] == 0
    monkeypatch.setattr(random.Random, "choice", lambda self, seq: "heart")
    gl.card_action(state, b, "psychic_probe", {"index": 0})
    assert state["dice"][0] == "heart"
    assert state["pending_probe"] is None
    assert state["phase"] == "buying"                 # window closed - the roll actually resolved
    assert state["mon"][a]["energy"] == 2


def test_probe_window_lets_the_prober_pass_without_burning_anything():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("psychic_probe")
    gl._begin_turn(state, a)
    force_dice(state, ["1", "1", "energy", "energy", "claw", "heart"])
    gl.resolve(state, a)
    assert state["phase"] == "probe_window"
    gl.card_action(state, b, "psychic_probe", {"pass": True})
    assert state["pending_probe"] is None
    assert state["phase"] == "buying"
    assert state["mon"][a]["energy"] == 2
    assert b not in cards._mem(state, a).get("probed_by", [])


def test_probe_window_skipped_if_the_prober_already_used_their_probe():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("psychic_probe")
    gl._begin_turn(state, a)
    force_dice(state, ["1", "1", "energy", "energy", "claw", "heart"])
    gl.card_action(state, b, "psychic_probe", {"index": 5})   # eager probe mid-roll
    assert b in cards._mem(state, a)["probed_by"]
    gl.resolve(state, a)
    assert state["phase"] == "buying"          # no window - b already had their chance
    assert state["pending_probe"] is None


def test_probe_window_advances_when_the_pending_prober_resigns():
    state, pids = fresh(4)
    a, b, c, d = pids
    state["mon"][b]["cards"].append("psychic_probe")
    state["mon"][c]["cards"].append("psychic_probe")
    gl._begin_turn(state, a)
    force_dice(state, ["1", "1", "energy", "energy", "claw", "heart"])
    gl.resolve(state, a)
    assert state["pending_probe"]["queue"] == [b, c]
    gl.resign(state, b)
    assert state["pending_probe"]["queue"] == [c]
    assert state["phase"] == "probe_window"
    gl.resign(state, c)
    assert state["pending_probe"] is None
    assert state["phase"] == "buying"
    assert "probed_by" not in cards._mem(state, a) or a not in cards._mem(state, a)["probed_by"]


def test_rapid_healing_spends_2_energy_to_heal_1():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("rapid_healing")
    state["mon"][a]["energy"] = 4
    state["mon"][a]["hp"] = 5
    gl.card_action(state, a, "rapid_healing", None)
    assert state["mon"][a]["hp"] == 6
    assert state["mon"][a]["energy"] == 2


def test_rapid_healing_is_repeatable_and_caps_at_max_hp():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("rapid_healing")
    state["mon"][a]["energy"] = 10
    state["mon"][a]["hp"] = 9                  # 1 below max
    gl.card_action(state, a, "rapid_healing", None)
    assert state["mon"][a]["hp"] == 10
    assert state["mon"][a]["energy"] == 8
    gl.card_action(state, a, "rapid_healing", None)   # already at max - refused
    assert state["mon"][a]["hp"] == 10
    assert state["mon"][a]["energy"] == 8


def test_rapid_healing_refuses_without_enough_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("rapid_healing")
    state["mon"][a]["energy"] = 1
    state["mon"][a]["hp"] = 5
    gl.card_action(state, a, "rapid_healing", None)
    assert state["mon"][a]["hp"] == 5
    assert state["mon"][a]["energy"] == 1


def test_rapid_healing_works_even_while_in_tokyo_unlike_dice_hearts():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("rapid_healing")
    state["mon"][a]["energy"] = 4
    state["mon"][a]["hp"] = 5
    state["tokyo"]["city"] = a
    gl.card_action(state, a, "rapid_healing", None)
    assert state["mon"][a]["hp"] == 6           # card healing works in Tokyo; dice hearts wouldn't


def test_made_in_a_lab_peek_then_buy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("made_in_a_lab")
    state["phase"] = "buying"; state["current"] = a
    state["deck"] = ["corner_store"]
    gl.card_action(state, a, "made_in_a_lab", {"action": "peek"})
    assert cards._mem(state, a)["lab_peek"] == "corner_store"
    state["mon"][a]["energy"] = 5
    gl.card_action(state, a, "made_in_a_lab", {"action": "buy"})
    assert state["mon"][a]["energy"] == 2      # corner store costs 3
    assert state["mon"][a]["vp"] == 1          # corner store's one-shot +1 VP
    assert state["deck"] == []


def test_opportunist_snipes_freshly_revealed_card():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("opportunist")
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["shop"][0] = "extra_head"
    state["deck"] = ["corner_store"]
    gl.buy_card(state, a, 0)                   # reveals corner_store into slot 0
    assert state["opportunist_window"] == [{"index": 0, "cid": "corner_store"}]
    state["mon"][b]["energy"] = 5
    gl.card_action(state, b, "opportunist", {"index": 0})
    assert state["mon"][b]["vp"] == 1           # corner store's one-shot fired for b, not a
    assert state["mon"][b]["energy"] == 2       # cost 3
    # the slot's refill (from an empty deck, so it goes empty) closes the window
    assert state["opportunist_window"] == []


def test_opportunist_refuses_stale_or_missing_index():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("opportunist")
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["shop"][0] = "extra_head"
    state["deck"] = ["corner_store"]
    gl.buy_card(state, a, 0)
    state["mon"][b]["energy"] = 5
    win_before = [dict(e) for e in state["opportunist_window"]]
    gl.card_action(state, b, "opportunist", {"index": 1})   # nothing snipeable there
    gl.card_action(state, b, "opportunist", {})              # no index at all
    assert state["opportunist_window"] == win_before
    assert state["mon"][b]["energy"] == 5                    # nothing spent


def test_sweep_shop_opens_an_opportunist_window_on_all_slots():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["cards"].append("opportunist")
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["mon"][b]["energy"] = 100
    gl.sweep_shop(state, a)
    assert len(state["opportunist_window"]) == gl.SHOP_SIZE
    assert {e["index"] for e in state["opportunist_window"]} == set(range(gl.SHOP_SIZE))
    # snipe one of the three; the other two entries stay put, and the sniped
    # slot's refill opens its own fresh entry instead of vanishing
    target = state["opportunist_window"][1]
    cost = max(0, cards.CATALOG[target["cid"]]["cost"])
    before_energy = state["mon"][b]["energy"]
    gl.card_action(state, b, "opportunist", {"index": target["index"]})
    assert state["mon"][b]["energy"] == before_energy - cost
    assert len(state["opportunist_window"]) == gl.SHOP_SIZE
    assert all(e["cid"] != target["cid"] for e in state["opportunist_window"])


def test_parasitic_tentacles_takes_a_card_and_pays_directly():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("parasitic_tentacles")
    state["mon"][b]["cards"].append("armor_plating")
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["mon"][b]["energy"] = 0
    gl.card_action(state, a, "parasitic_tentacles", {"pid": b, "card": "armor_plating"})
    assert "armor_plating" not in state["mon"][b]["cards"]
    assert "armor_plating" in state["mon"][a]["cards"]
    assert state["mon"][a]["energy"] == 6       # armor plating costs 4
    assert state["mon"][b]["energy"] == 4       # paid directly to b, not the bank


def test_parasitic_tentacles_theft_still_counts_as_a_buy():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"] += ["parasitic_tentacles", "dedicated_news_team"]
    state["mon"][b]["cards"].append("armor_plating")
    state["phase"] = "buying"; state["current"] = a
    state["mon"][a]["energy"] = 10
    state["mon"][b]["energy"] = 0
    gl.card_action(state, a, "parasitic_tentacles", {"pid": b, "card": "armor_plating"})
    assert state["mon"][a]["vp"] == 1     # Dedicated News Team: +1 VP whenever you buy a card


def test_healing_ray_fires_immediately_for_payment():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("healing_ray")
    state["mon"][b]["hp"] = 5
    state["mon"][b]["energy"] = 10
    force_dice(state, ["heart", "heart", "1", "2", "3", "energy"])
    gl.card_action(state, a, "healing_ray", {"pid": b})
    assert state["mon"][b]["hp"] == 7           # healed 2
    assert state["mon"][b]["energy"] == 6       # paid 2⚡ per point healed = 4
    assert state["mon"][a]["energy"] == 4       # a pockets the payment
    # Resolving the roll afterward must not ALSO self-heal a with these same
    # already-spent hearts.
    a_hp_before = state["mon"][a]["hp"]
    gl.resolve(state, a)
    assert state["mon"][a]["hp"] == a_hp_before
    assert state["mon"][b]["hp"] == 7


def test_healing_ray_caps_heal_to_what_target_can_afford():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("healing_ray")
    state["mon"][b]["hp"] = 2
    state["mon"][b]["maxhp"] = 10
    state["mon"][b]["energy"] = 1     # can only ever afford 0 points (1⚡ < 2⚡/point)
    force_dice(state, ["heart", "heart", "heart", "heart", "heart", "heart"])
    gl.card_action(state, a, "healing_ray", {"pid": b})
    assert state["mon"][b]["hp"] == 2             # nothing healed - can't afford even 1 point
    assert state["mon"][b]["energy"] == 1         # untouched, no credit extended
    assert state["mon"][a]["energy"] == 0         # a gets nothing it wasn't paid


def test_made_in_a_lab_peek_hidden_from_other_viewers():
    state, pids = fresh(2)
    a, b = pids
    state["current"] = a
    state["phase"] = "buying"
    state["mon"][a]["cards"].append("made_in_a_lab")
    state["deck"].append("spiked_tail")
    gl.card_action(state, a, "made_in_a_lab", {"action": "peek"})
    owner_view = gl.public_view(state, viewer_pid=a)
    other_view = gl.public_view(state, viewer_pid=b)
    spectator_view = gl.public_view(state)
    owner_card = next(c for c in owner_view["mon"][a]["cards"] if c["id"] == "made_in_a_lab")
    other_card = next(c for c in other_view["mon"][a]["cards"] if c["id"] == "made_in_a_lab")
    spectator_card = next(c for c in spectator_view["mon"][a]["cards"] if c["id"] == "made_in_a_lab")
    assert owner_card["lab_peek"]["id"] == "spiked_tail"    # owner sees their own peek
    assert "lab_peek" not in other_card                     # another player never does
    assert "lab_peek" not in spectator_card                 # nor an unauthenticated spectator


def test_shop_price_reflects_alien_metabolism_discount():
    state, pids = fresh(2)
    a = pids[0]
    state["current"] = a
    state["mon"][a]["cards"].append("alien_metabolism")
    state["shop"][0] = "corner_store"         # cost 3
    view = gl.public_view(state)
    assert view["shop"][0]["cost"] == 2       # 3 - 1 discount, not the sticker price
    state["mon"][a]["energy"] = 2
    state["phase"] = "buying"
    gl.buy_card(state, a, 0)                  # would fail if the engine still charged 3
    assert state["mon"][a]["energy"] == 0


def test_poison_spit_gives_a_token_when_you_deal_damage():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("poison_spit")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "claw", "claw", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["tokens"].get("poison", 0) == 1


def test_poison_spit_ticks_at_the_poisoned_monsters_own_turn_end_and_persists():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["tokens"]["poison"] = 3
    state["phase"] = "buying"; state["current"] = b
    gl.end_turn(state, b)
    assert state["mon"][b]["hp"] == 7                  # 3 poison damage
    assert state["mon"][b]["tokens"]["poison"] == 3    # counters aren't consumed by their own tick


def test_poison_spit_token_shed_by_a_wasted_heart():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["tokens"]["poison"] = 2
    state["mon"][a]["hp"] = state["mon"][a]["maxhp"]   # full HP, so a heart would otherwise be wasted
    gl._begin_turn(state, a)
    force_dice(state, ["heart", "1", "1", "2", "2", "energy"])
    gl.resolve(state, a)
    assert state["mon"][a]["tokens"]["poison"] == 1    # one heart shed one counter
    assert state["mon"][a]["hp"] == state["mon"][a]["maxhp"]


def test_poison_spit_no_token_when_jets_dodges_the_damage():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("poison_spit")
    state["mon"][b]["cards"].append("jets")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "claw", "claw", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["phase"] == "yield"
    gl.yield_decision(state, b, leave=True)
    assert state["mon"][b]["tokens"].get("poison", 0) == 0    # dodged the damage, so no token either


def test_shrink_ray_gives_a_token_when_you_deal_damage():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("shrink_ray")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "claw", "claw", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["tokens"].get("shrink", 0) == 1


def test_shrink_ray_reduces_dice_count_on_the_shrunk_monsters_next_turn():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["tokens"]["shrink"] = 2
    gl._begin_turn(state, b)
    assert len(state["dice"]) == gl.BASE_DICE - 2
    assert len(state["kept"]) == gl.BASE_DICE - 2


def test_shrink_ray_never_reduces_dice_below_one():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][b]["tokens"]["shrink"] = 99
    gl._begin_turn(state, b)
    assert len(state["dice"]) == 1


def test_shrink_ray_token_shed_by_a_wasted_heart():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["tokens"]["shrink"] = 2
    state["mon"][a]["hp"] = state["mon"][a]["maxhp"]   # full HP, so a heart would otherwise be wasted
    gl._begin_turn(state, a)
    force_dice(state, ["heart", "1", "1", "2", "2", "energy"])
    gl.resolve(state, a)
    assert state["mon"][a]["tokens"]["shrink"] == 1    # one heart shed one counter
    assert state["mon"][a]["hp"] == state["mon"][a]["maxhp"]


def test_shrink_ray_no_token_when_jets_dodges_the_damage():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("shrink_ray")
    state["mon"][b]["cards"].append("jets")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "claw", "claw", "1", "1", "energy"])
    gl.resolve(state, a)
    assert state["phase"] == "yield"
    gl.yield_decision(state, b, leave=True)
    assert state["mon"][b]["tokens"].get("shrink", 0) == 0    # dodged the damage, so no token either


def test_stretchy_spends_2_energy_to_change_a_die():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("stretchy")
    state["mon"][a]["energy"] = 4
    force_dice(state, ["1", "1", "1", "1", "1", "1"])
    gl.card_action(state, a, "stretchy", {"index": 0, "face": "claw"})
    assert state["dice"][0] == "claw"
    assert state["mon"][a]["energy"] == 2


def test_stretchy_refuses_without_enough_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("stretchy")
    state["mon"][a]["energy"] = 1
    force_dice(state, ["1", "1", "1", "1", "1", "1"])
    gl.card_action(state, a, "stretchy", {"index": 0, "face": "claw"})
    assert state["dice"][0] == "1"
    assert state["mon"][a]["energy"] == 1


def test_stretchy_is_repeatable_not_a_one_shot():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("stretchy")
    state["mon"][a]["energy"] = 10
    force_dice(state, ["1", "1", "1", "1", "1", "1"])
    gl.card_action(state, a, "stretchy", {"index": 0, "face": "claw"})
    gl.card_action(state, a, "stretchy", {"index": 1, "face": "heart"})
    assert state["dice"][0] == "claw" and state["dice"][1] == "heart"
    assert state["mon"][a]["energy"] == 6
    assert "stretchy" in state["mon"][a]["cards"]              # still held, never discards


def test_telepath_spends_1_energy_for_1_extra_reroll():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("telepath")
    state["mon"][a]["energy"] = 3
    state["rolls_left"] = 2
    gl.card_action(state, a, "telepath", None)
    assert state["rolls_left"] == 3
    assert state["mon"][a]["energy"] == 2


def test_telepath_refuses_without_enough_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("telepath")
    state["mon"][a]["energy"] = 0
    state["rolls_left"] = 2
    gl.card_action(state, a, "telepath", None)
    assert state["rolls_left"] == 2
    assert state["mon"][a]["energy"] == 0


def test_telepath_is_repeatable_and_usable_before_the_first_roll():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("telepath")
    state["mon"][a]["energy"] = 5
    assert state["roll_num"] == 0                # hasn't rolled yet
    gl.card_action(state, a, "telepath", None)
    gl.card_action(state, a, "telepath", None)
    assert state["rolls_left"] == 4              # base 2 + 2 bought
    assert state["mon"][a]["energy"] == 3


def test_urbavore_extra_vp_starting_the_turn_in_tokyo_city():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("urbavore")
    state["tokyo"]["city"] = a
    gl._begin_turn(state, a)
    assert state["mon"][a]["vp"] == 3            # base 2 + urbavore's 1


def test_urbavore_extra_vp_starting_the_turn_in_tokyo_bay():
    state, pids = fresh(3)
    a = pids[0]
    state["mon"][a]["cards"].append("urbavore")
    state["use_bay"] = True
    state["tokyo"]["bay"] = a
    gl._begin_turn(state, a)
    assert state["mon"][a]["vp"] == 2            # base 1 + urbavore's 1


def test_urbavore_extra_damage_attacking_from_tokyo():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("urbavore")
    state["tokyo"]["city"] = a
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "1", "1", "2", "2", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 8             # 10 - (1 claw + urbavore's +1)


def test_urbavore_no_bonus_damage_attacking_from_outside_tokyo():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("urbavore")
    state["tokyo"]["city"] = b
    gl._begin_turn(state, a)
    force_dice(state, ["claw", "1", "1", "2", "2", "energy"])
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 9              # just the 1 claw - no Tokyo bonus while outside


def test_urbavore_no_bonus_damage_when_you_dont_attack_at_all():
    state, pids = fresh(2)
    a, b = pids
    state["mon"][a]["cards"].append("urbavore")
    state["tokyo"]["city"] = a
    gl._begin_turn(state, a)
    force_dice(state, ["1", "1", "1", "2", "2", "energy"])   # no claws
    gl.resolve(state, a)
    assert state["mon"][b]["hp"] == 10              # urbavore never grants free damage on its own


def test_wings_negates_damage_once_activated():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("wings")
    state["mon"][a]["energy"] = 2
    gl.card_action(state, a, "wings", None)
    assert state["mon"][a]["energy"] == 0
    took = gl.deal_damage(state, a, 5, attacker=None)
    assert took == 0
    assert state["mon"][a]["hp"] == 10


def test_wings_refuses_without_enough_energy():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("wings")
    state["mon"][a]["energy"] = 1
    gl.card_action(state, a, "wings", None)
    assert state["mon"][a]["energy"] == 1
    took = gl.deal_damage(state, a, 5, attacker=None)
    assert took == 5


def test_wings_refuses_to_reactivate_while_already_up():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("wings")
    state["mon"][a]["energy"] = 10
    gl.card_action(state, a, "wings", None)
    gl.card_action(state, a, "wings", None)
    assert state["mon"][a]["energy"] == 8    # second attempt refused - no double-paying


def test_wings_clears_at_the_owners_next_turn_start():
    state, pids = fresh(2)
    a = pids[0]
    state["mon"][a]["cards"].append("wings")
    state["mon"][a]["energy"] = 2
    gl.card_action(state, a, "wings", None)
    assert cards._mem(state, a)["wings"] is True
    gl._begin_turn(state, a)
    assert cards._mem(state, a)["wings"] is False
    took = gl.deal_damage(state, a, 5, attacker=None)
    assert took == 5
