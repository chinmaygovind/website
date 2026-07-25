"""King of Tokyo - the 66 base-game power cards and their effects.

The engine (``game_logic.py``) stays rules-of-the-dice only; everything a card
does hooks in here through a small interface it calls by name:

  CATALOG              id -> {id, name, cost, type, text, key}
  build_deck(rng)      the shuffled 66-card draw pile (list of ids)
  mod(state,pid,key)   sum of a passive numeric modifier over a monster's cards
  adjust_incoming(...) mitigate damage before it lands (Wings/Armor/Camouflage)
  on_acquire(...)      fire a card's effect the moment it's gained (Keep + Discard)
  trigger(...,hook)    event hooks (turn start/end, numbers, attack, damage, ...)
  on_deal_damage(...)  attacker dealt damage to a distinct target (counters, fire)
  on_any_elimination() a monster hit 0 HP (Eater of the Dead)
  card_action(...)     a manual ability the active monster fires this turn

Several highly interactive cards (Mimic, Psychic Probe, Made in a Lab,
Opportunist, Parasitic Tentacles, Healing Ray) are best-effort: they buy and
sit in play but have no automatic effect, since they need live table
negotiation this server doesn't model. Everything else is fully implemented.
"""

import random

import game_logic as gl

# (id, key, name, cost, type, text). ``key`` is the mechanic identity, shared by
# duplicate copies so ownership/stacking counts them together.
_DEFS = [
    ("acid_attack", "acid_attack", "Acid Attack", 6, "keep",
     "Deal 1 extra damage each turn (even when you don't otherwise attack)."),
    ("alien_metabolism", "alien_metabolism", "Alien Metabolism", 3, "keep",
     "Buying cards costs you 1 less ⚡."),
    ("alpha_monster", "alpha_monster", "Alpha Monster", 5, "keep",
     "Gain 1 VP when you attack."),
    ("apartment_building", "apartment_building", "Apartment Building", 5, "discard",
     "+3 VP"),
    ("armor_plating", "armor_plating", "Armor Plating", 4, "keep",
     "Ignore damage of 1."),
    ("background_dweller", "background_dweller", "Background Dweller", 4, "keep",
     "You can always reroll any [3] you have."),
    ("burrowing", "burrowing", "Burrowing", 5, "keep",
     "Deal 1 extra damage on Tokyo. Deal 1 damage when yielding Tokyo to the monster taking it."),
    ("camouflage", "camouflage", "Camouflage", 3, "keep",
     "If you take damage roll a die for each damage point. On a ❤ you do not take that damage point."),
    ("commuter_train", "commuter_train", "Commuter Train", 4, "discard",
     "+2 VP"),
    ("complete_destruction", "complete_destruction", "Complete Destruction", 3, "keep",
     "If you roll [1][2][3]❤[claw]⚡ gain 9 VP in addition to the regular results."),
    ("corner_store", "corner_store", "Corner Store", 3, "discard",
     "+1 VP"),
    ("dedicated_news_team", "dedicated_news_team", "Dedicated News Team", 3, "keep",
     "Gain 1 VP whenever you buy a card."),
    ("drop_from_high_altitude", "drop_from_high_altitude", "Drop from High Altitude", 5, "discard",
     "+2 VP and take control of Tokyo if you don't already control it."),
    ("eater_of_the_dead", "eater_of_the_dead", "Eater of the Dead", 4, "keep",
     "Gain 3 VP every time a monster's ❤ goes to 0."),
    ("energize", "energize", "Energize", 8, "discard",
     "+9⚡"),
    ("energy_hoarder", "energy_hoarder", "Energy Hoarder", 3, "keep",
     "You gain 1 VP for every 6⚡ you have at the end of your turn."),
    ("evacuation_orders", "evacuation_orders", "Evacuation Orders", 7, "discard",
     "All other monsters lose 5 VP."),
    ("evacuation_orders_2", "evacuation_orders", "Evacuation Orders", 7, "discard",
     "All other monsters lose 5 VP."),
    ("even_bigger", "even_bigger", "Even Bigger", 4, "keep",
     "Your maximum ❤ is increased by 2. Gain 2❤ when you get this card."),
    ("extra_head", "extra_head", "Extra Head", 7, "keep",
     "You get 1 extra die."),
    ("extra_head_2", "extra_head", "Extra Head", 7, "keep",
     "You get 1 extra die."),
    ("fire_blast", "fire_blast", "Fire Blast", 3, "discard",
     "Deal 2 damage to all other monsters."),
    ("fire_breathing", "fire_breathing", "Fire Breathing", 4, "keep",
     "Your neighbors take 1 extra damage when you deal damage."),
    ("freeze_time", "freeze_time", "Freeze Time", 5, "keep",
     "On a turn where you score [1][1][1], you can take another turn with one less die."),
    ("frenzy", "frenzy", "Frenzy", 7, "discard",
     "When you purchase this card take another turn immediately after this one."),
    ("friend_of_children", "friend_of_children", "Friend of Children", 3, "keep",
     "When you gain any ⚡ gain 1 extra ⚡."),
    ("gas_refinery", "gas_refinery", "Gas Refinery", 6, "discard",
     "+2 VP and deal 3 damage to all other monsters."),
    ("giant_brain", "giant_brain", "Giant Brain", 5, "keep",
     "You have one extra reroll each turn."),
    ("gourmet", "gourmet", "Gourmet", 4, "keep",
     "When scoring [1][1][1] gain 2 extra VP."),
    ("heal", "heal", "Heal", 3, "discard",
     "Heal 2 damage."),
    ("healing_ray", "healing_ray", "Healing Ray", 4, "keep",
     "You can heal other monsters with your ❤ results. They pay you 2⚡ for each damage healed."),
    ("herbivore", "herbivore", "Herbivore", 5, "keep",
     "Gain 1 VP on your turn if you don't damage anyone."),
    ("herd_culler", "herd_culler", "Herd Culler", 3, "keep",
     "You can change one of your dice to a [1] each turn."),
    ("high_altitude_bombing", "high_altitude_bombing", "High Altitude Bombing", 4, "discard",
     "All monsters (including you) take 3 damage."),
    ("it_has_a_child", "it_has_a_child", "It Has a Child", 7, "keep",
     "If you are eliminated discard all your cards, lose all your VP, heal to 10❤ and start again."),
    ("jet_fighters", "jet_fighters", "Jet Fighters", 5, "discard",
     "+5 VP and take 4 damage."),
    ("jets", "jets", "Jets", 5, "keep",
     "You suffer no damage when yielding Tokyo."),
    ("made_in_a_lab", "made_in_a_lab", "Made in a Lab", 2, "keep",
     "When purchasing cards you can peek at and purchase the top card of the deck."),
    ("metamorph", "metamorph", "Metamorph", 3, "keep",
     "At the end of your turn you can discard any keep cards to get their ⚡ cost back."),
    ("mimic", "mimic", "Mimic", 8, "keep",
     "Copy a card any monster has in play. Spend 1⚡ at the start of your turn to change it."),
    ("monster_batteries", "monster_batteries", "Monster Batteries", 2, "keep",
     "Store your ⚡ on this card, then take 2⚡ back at the start of each turn until it runs out."),
    ("national_guard", "national_guard", "National Guard", 3, "discard",
     "+2 VP and take 2 damage."),
    ("nova_breath", "nova_breath", "Nova Breath", 7, "keep",
     "Your attacks damage all other monsters."),
    ("nuclear_power_plant", "nuclear_power_plant", "Nuclear Power Plant", 6, "discard",
     "+2 VP and heal 3 damage."),
    ("omnivore", "omnivore", "Omnivore", 4, "keep",
     "Once each turn you can score [1][2][3] for 2 VP."),
    ("opportunist", "opportunist", "Opportunist", 3, "keep",
     "Whenever a new card is revealed you may purchase it right away."),
    ("parasitic_tentacles", "parasitic_tentacles", "Parasitic Tentacles", 4, "keep",
     "You can purchase cards from other monsters, paying them the ⚡ cost."),
    ("plot_twist", "plot_twist", "Plot Twist", 3, "keep",
     "Change one die to any result. Discard when used."),
    ("poison_quills", "poison_quills", "Poison Quills", 3, "keep",
     "When you score [2][2][2] also deal 2 damage."),
    ("poison_spit", "poison_spit", "Poison Spit", 4, "keep",
     "When you damage monsters give them a poison counter. They take 1 damage per counter at the end of their turn; a ❤ removes one."),
    ("psychic_probe", "psychic_probe", "Psychic Probe", 3, "keep",
     "You can reroll one dice of each other monster once each turn."),
    ("rapid_healing", "rapid_healing", "Rapid Healing", 3, "keep",
     "Spend 2⚡ at any time to heal 1 damage."),
    ("regeneration", "regeneration", "Regeneration", 4, "keep",
     "When you heal, heal 1 extra damage."),
    ("rooting_for_the_underdog", "rooting_for_the_underdog", "Rooting for the Underdog", 3, "keep",
     "At the end of a turn when you have the fewest VP gain 1 VP."),
    ("shrink_ray", "shrink_ray", "Shrink Ray", 6, "keep",
     "When you damage monsters give them a shrink counter. They roll one less die per counter; a ❤ removes one."),
    ("skyscraper", "skyscraper", "Skyscraper", 6, "discard",
     "+4 VP"),
    ("smoke_cloud", "smoke_cloud", "Smoke Cloud", 4, "keep",
     "Starts with 3 charges. Spend a charge for an extra reroll. Discard when empty."),
    ("solar_powered", "solar_powered", "Solar Powered", 2, "keep",
     "At the end of your turn gain 1⚡ if you have no ⚡."),
    ("spiked_tail", "spiked_tail", "Spiked Tail", 5, "keep",
     "When you attack deal 1 extra damage."),
    ("stretchy", "stretchy", "Stretchy", 3, "keep",
     "You can spend 2⚡ to change one of your dice to any result."),
    ("tanks", "tanks", "Tanks", 4, "discard",
     "+4 VP and take 3 damage."),
    ("telepath", "telepath", "Telepath", 4, "keep",
     "Spend 1⚡ to get 1 extra reroll."),
    ("urbavore", "urbavore", "Urbavore", 4, "keep",
     "Gain 1 extra VP when beginning the turn in Tokyo. Deal 1 extra damage when dealing damage from Tokyo."),
    ("vast_storm", "vast_storm", "Vast Storm", 6, "discard",
     "+2 VP. All other monsters lose 1⚡ for every 2⚡ they have."),
    ("were_only_making_it_stronger", "were_only_making_it_stronger", "We're Only Making It Stronger", 3, "keep",
     "When you lose 2❤ or more gain 1⚡."),
    ("wings", "wings", "Wings", 6, "keep",
     "Spend 2⚡ to negate damage to you until your next turn."),
]

# One emoji per distinct card (shared by both copies of a duplicated card, since
# they're the same physical card in the real deck).
_EMOJI = {
    "acid_attack": "🧪", "alien_metabolism": "🧬", "alpha_monster": "🐺",
    "apartment_building": "🏢", "armor_plating": "🛡️", "background_dweller": "🙈",
    "burrowing": "🕳️", "camouflage": "🦎", "commuter_train": "🚆",
    "complete_destruction": "💥", "corner_store": "🏪", "dedicated_news_team": "📰",
    "drop_from_high_altitude": "🪂", "eater_of_the_dead": "💀", "energize": "🔋",
    "energy_hoarder": "🏦", "evacuation_orders": "🚨", "even_bigger": "🦣",
    "extra_head": "🎲", "fire_blast": "🔥", "fire_breathing": "🌋",
    "freeze_time": "⏳", "frenzy": "🌀", "friend_of_children": "🧒",
    "gas_refinery": "🏭", "giant_brain": "🧠", "gourmet": "🍽️",
    "heal": "🩹", "healing_ray": "🚑", "herbivore": "🌿",
    "herd_culler": "🐑", "high_altitude_bombing": "💣", "it_has_a_child": "🥚",
    "jet_fighters": "🛩️", "jets": "🚀", "made_in_a_lab": "🧫",
    "metamorph": "🦋", "mimic": "🎭", "monster_batteries": "🔌",
    "national_guard": "🎖️", "nova_breath": "☄️", "nuclear_power_plant": "☢️",
    "omnivore": "🍖", "opportunist": "🕵️", "parasitic_tentacles": "🦑",
    "plot_twist": "🔀", "poison_quills": "🦔", "poison_spit": "☠️",
    "psychic_probe": "🔮", "rapid_healing": "💊", "regeneration": "♻️",
    "rooting_for_the_underdog": "🐶", "shrink_ray": "📉", "skyscraper": "🏙️",
    "smoke_cloud": "💨", "solar_powered": "☀️", "spiked_tail": "🦂",
    "stretchy": "🎈", "tanks": "🪖", "telepath": "📡",
    "urbavore": "🌆", "vast_storm": "⛈️", "were_only_making_it_stronger": "💪",
    "wings": "🪽",
}

CATALOG = {d[0]: {"id": d[0], "key": d[1], "name": d[2], "cost": d[3],
                  "type": d[4], "text": d[5], "emoji": _EMOJI.get(d[1], "🎴")}
           for d in _DEFS}

# Passive numeric modifiers, summed across a monster's Keep cards (per copy).
_CONTRIB = {
    "extra_head": {"extra_dice": 1},
    "giant_brain": {"extra_rerolls": 1},
    "acid_attack": {"damage_always": 1},
    "spiked_tail": {"damage_attack": 1},
    "burrowing": {"damage_in_tokyo": 1},
    "urbavore": {"damage_in_tokyo": 1, "tokyo_start_vp_bonus": 1},
    "friend_of_children": {"energy_per_gain": 1},
    "regeneration": {"heal_bonus": 1},
    "alien_metabolism": {"buy_discount": 1},
    "nova_breath": {"hits_everyone": 1},
}


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------

def _keys(state, pid):
    """Iterator over the mechanic keys of a monster's owned Keep cards."""
    for cid in state["mon"][pid]["cards"]:
        c = CATALOG.get(cid)
        if c:
            yield c["key"]


def _count(state, pid, key):
    return sum(1 for k in _keys(state, pid) if k == key)


def _has(state, pid, key):
    return _count(state, pid, key) > 0


def _mem(state, pid):
    return state["mon"][pid].setdefault("cardmem", {})


def build_deck(rng):
    ids = [d[0] for d in _DEFS]
    rng.shuffle(ids)
    return ids


def mod(state, pid, key):
    total = 0
    for k in _keys(state, pid):
        total += _CONTRIB.get(k, {}).get(key, 0)
    return total


# ---------------------------------------------------------------------------
# Damage mitigation
# ---------------------------------------------------------------------------

def adjust_incoming(state, target, n, attacker, rng):
    m = state["mon"][target]
    if _mem(state, target).get("wings"):
        return 0
    if _has(state, target, "armor_plating") and n == 1:
        return 0
    if _has(state, target, "camouflage") and n > 0:
        saved = sum(1 for _ in range(n) if rng.choice(gl.FACES) == "heart")
        n -= saved
        if saved:
            gl._log(state, f"{gl._nm(target)}'s camouflage shrugs off {saved} damage.",
                    pid=target, kind="sys")
    return max(0, n)


# ---------------------------------------------------------------------------
# Attacker-side effects when damage is dealt to a distinct target
# ---------------------------------------------------------------------------

def on_deal_damage(state, attacker, target, n):
    if _has(state, attacker, "poison_spit"):
        state["mon"][target]["tokens"]["poison"] = \
            state["mon"][target]["tokens"].get("poison", 0) + 1
    if _has(state, attacker, "shrink_ray"):
        state["mon"][target]["tokens"]["shrink"] = \
            state["mon"][target]["tokens"].get("shrink", 0) + 1


def on_any_elimination(state, pid):
    for q in state["players"]:
        if q != pid and state["mon"][q]["alive"] and _has(state, q, "eater_of_the_dead"):
            gl.gain_vp(state, q, 3)
            gl._log(state, f"{gl._nm(q)} feasts on the fallen (+3 VP).", pid=q, kind="vp")


# ---------------------------------------------------------------------------
# A card-driven attack (no yield decision) - used by Poison Quills etc.
# ---------------------------------------------------------------------------

def _card_attack(state, attacker, dmg):
    in_tok = gl._in_tokyo(state, attacker)
    if gl.mod(state, attacker, "hits_everyone") > 0:
        targets = [p for p in gl._alive(state) if p != attacker]
    elif in_tok:
        targets = [p for p in gl._alive(state) if gl._in_tokyo(state, p) is None and p != attacker]
    else:
        targets = [p for p in gl._tokyo_occupants(state) if state["mon"][p]["alive"]]
    for t in list(targets):
        gl.deal_damage(state, t, dmg, attacker=attacker)


# ---------------------------------------------------------------------------
# Acquire: fire a card's effect the moment it is bought
# ---------------------------------------------------------------------------

def on_acquire(state, pid, cid):
    c = CATALOG.get(cid)
    if not c:
        return
    key = c["key"]
    m = state["mon"][pid]

    # --- Keep-card setup ---
    if key == "even_bigger":
        m["maxhp"] += 2
        gl.heal(state, pid, 2)
    elif key == "monster_batteries":
        stored = m["energy"]
        gl.spend_energy(state, pid, stored)
        _mem(state, pid)["batteries"] = stored       # bank matches your stake, not double it
        gl._log(state, f"{gl._nm(pid)} charges the batteries with {stored}⚡.", pid=pid, kind="energy")
    elif key == "smoke_cloud":
        _mem(state, pid)["smoke"] = 3

    # --- Discard-card one-shots ---
    elif key == "apartment_building":
        gl.gain_vp(state, pid, 3)
    elif key == "commuter_train":
        gl.gain_vp(state, pid, 2)
    elif key == "corner_store":
        gl.gain_vp(state, pid, 1)
    elif key == "skyscraper":
        gl.gain_vp(state, pid, 4)
    elif key == "energize":
        gl.gain_energy(state, pid, 9)
    elif key == "heal":
        healed = gl.heal(state, pid, 2)
        gl._log(state, f"{gl._nm(pid)} heals {healed}❤.", pid=pid, kind="heal")
    elif key == "national_guard":
        gl.gain_vp(state, pid, 2)
        gl.deal_damage(state, pid, 2, attacker=None)
    elif key == "tanks":
        gl.gain_vp(state, pid, 4)
        gl.deal_damage(state, pid, 3, attacker=None)
    elif key == "jet_fighters":
        gl.gain_vp(state, pid, 5)
        gl.deal_damage(state, pid, 4, attacker=None)
    elif key == "nuclear_power_plant":
        gl.gain_vp(state, pid, 2)
        gl.heal(state, pid, 3)
    elif key == "gas_refinery":
        gl.gain_vp(state, pid, 2)
        for q in _others(state, pid):
            gl.deal_damage(state, q, 3, attacker=pid)
    elif key == "fire_blast":
        for q in _others(state, pid):
            gl.deal_damage(state, q, 2, attacker=pid)
    elif key == "high_altitude_bombing":
        for q in gl._alive(state):
            gl.deal_damage(state, q, 3, attacker=(pid if q != pid else None))
    elif key == "evacuation_orders":
        for q in _others(state, pid):
            gl.gain_vp(state, q, -5)
        gl._log(state, f"{gl._nm(pid)} orders an evacuation - everyone else loses 5 VP.", pid=pid, kind="vp")
    elif key == "vast_storm":
        gl.gain_vp(state, pid, 2)
        for q in _others(state, pid):
            gl.spend_energy(state, q, state["mon"][q]["energy"] // 2)
    elif key == "drop_from_high_altitude":
        gl.gain_vp(state, pid, 2)
        if not gl._in_tokyo(state, pid):
            occ = state["tokyo"]["city"]
            if occ:
                state["tokyo"]["city"] = None
                gl._log(state, f"{gl._nm(occ)} is shoved out of Tokyo.", pid=occ, kind="tokyo")
            gl._take_tokyo(state, pid, "city")
    elif key == "frenzy":
        m["_extra_turn"] = True
        gl._log(state, f"{gl._nm(pid)} goes into a frenzy - another turn!", pid=pid, kind="sys")


def _others(state, pid):
    return [q for q in gl._alive(state) if q != pid]


# ---------------------------------------------------------------------------
# Event hooks
# ---------------------------------------------------------------------------

def trigger(state, pid, hook, **ctx):
    fn = _HOOKS.get(hook)
    if fn:
        fn(state, pid, ctx)


def _h_turn_start(state, pid, ctx):
    m = state["mon"][pid]
    mem = _mem(state, pid)
    mem["freeze"] = False
    mem["herd_used"] = False
    if mem.get("wings"):
        mem["wings"] = False
    if _has(state, pid, "monster_batteries") and mem.get("batteries", 0) > 0:
        take = min(2, mem["batteries"])
        mem["batteries"] -= take
        gl.gain_energy(state, pid, take)
        gl._log(state, f"{gl._nm(pid)} draws {take}⚡ from the batteries.", pid=pid, kind="energy")
        if mem["batteries"] <= 0:
            _discard_card(state, pid, "monster_batteries")


def _h_numbers(state, pid, ctx):
    dice = ctx.get("dice", [])
    if _has(state, pid, "complete_destruction") and all(f in dice for f in gl.FACES):
        gl.gain_vp(state, pid, 9)
        gl._log(state, f"{gl._nm(pid)} rolls the rainbow - Complete Destruction! +9 VP.", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    if _has(state, pid, "gourmet") and dice.count("1") >= 3:
        gl.gain_vp(state, pid, 2)
        gl._log(state, f"{gl._nm(pid)} savors it (Gourmet +2 VP).", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    if _has(state, pid, "omnivore") and all(dice.count(n) >= 1 for n in ("1", "2", "3")):
        gl.gain_vp(state, pid, 2)
        gl._log(state, f"{gl._nm(pid)} eats a balanced meal (Omnivore +2 VP).", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    if _has(state, pid, "poison_quills") and dice.count("2") >= 3:
        gl._log(state, f"{gl._nm(pid)} looses poison quills (2 damage).", pid=pid, kind="attack")
        _card_attack(state, pid, 2)
    if _has(state, pid, "freeze_time") and dice.count("1") >= 3:
        _mem(state, pid)["freeze"] = True


def _h_attack(state, pid, ctx):
    if _has(state, pid, "alpha_monster"):
        gl.gain_vp(state, pid, 1)
        gl._log(state, f"{gl._nm(pid)} leads the pack (Alpha Monster +1 VP).", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    if _has(state, pid, "fire_breathing"):
        order = state["players"]
        i = order.index(pid)
        n = len(order)
        for nb in {order[(i - 1) % n], order[(i + 1) % n]}:
            if nb != pid and state["mon"][nb]["alive"]:
                gl.deal_damage(state, nb, 1, attacker=pid)


def _h_take_damage(state, pid, ctx):
    if ctx.get("amount", 0) >= 2 and _has(state, pid, "were_only_making_it_stronger"):
        gl.gain_energy(state, pid, 1)
        gl._log(state, f"{gl._nm(pid)} only gets stronger (+1⚡).", pid=pid, kind="energy")


def _h_would_die(state, pid, ctx):
    if _has(state, pid, "it_has_a_child"):
        m = state["mon"][pid]
        for cid in list(m["cards"]):
            state["discard"].append(cid)
        m["cards"] = []
        m["tokens"] = {}
        m["cardmem"] = {}
        m["vp"] = 0
        m["maxhp"] = gl.START_MAX_HP
        m["hp"] = 10
        gl._log(state, f"{gl._nm(pid)}'s offspring rises to fight on!", pid=pid, kind="sys")
        gl._bump(state)


def _h_yield(state, pid, ctx):
    attacker = ctx.get("attacker")
    if attacker and _has(state, pid, "burrowing") and state["mon"].get(attacker, {}).get("alive"):
        gl._log(state, f"{gl._nm(pid)} burrows out, clawing {gl._nm(attacker)} for 1.", pid=pid, kind="attack")
        gl.deal_damage(state, attacker, 1, attacker=pid)


def _h_buy_card(state, pid, ctx):
    if _has(state, pid, "dedicated_news_team"):
        gl.gain_vp(state, pid, 1)
        gl._log(state, f"{gl._nm(pid)} makes the news (+1 VP).", pid=pid, kind="vp")


def _h_turn_end(state, pid, ctx):
    m = state["mon"][pid]
    # Poison counters bite at the end of the poisoned monster's own turn.
    poison = m["tokens"].get("poison", 0)
    if poison > 0:
        gl._log(state, f"{gl._nm(pid)} suffers {poison} poison damage.", pid=pid, kind="attack")
        gl.deal_damage(state, pid, poison, attacker=None)
        if not m["alive"] or state["phase"] == "ended":
            return
    if _has(state, pid, "energy_hoarder"):
        bonus = m["energy"] // 6
        if bonus:
            gl.gain_vp(state, pid, bonus)
            gl._log(state, f"{gl._nm(pid)} hoards energy (+{bonus} VP).", pid=pid, kind="vp")
    if _has(state, pid, "solar_powered") and m["energy"] == 0:
        gl.gain_energy(state, pid, 1)
    if _has(state, pid, "herbivore") and m.get("_dmg", 0) == 0:
        gl.gain_vp(state, pid, 1)
        gl._log(state, f"{gl._nm(pid)} grazes in peace (Herbivore +1 VP).", pid=pid, kind="vp")
    if _has(state, pid, "rooting_for_the_underdog"):
        others = [state["mon"][q]["vp"] for q in gl._alive(state) if q != pid]
        if not others or m["vp"] <= min(others):
            gl.gain_vp(state, pid, 1)
            gl._log(state, f"{gl._nm(pid)} roots for the underdog (+1 VP).", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    if _mem(state, pid).get("freeze"):
        m["_extra_turn"] = True
        m["_freeze_penalty"] = 1
        gl._log(state, f"{gl._nm(pid)} freezes time - another turn!", pid=pid, kind="sys")


_HOOKS = {
    "on_turn_start": _h_turn_start,
    "on_numbers": _h_numbers,
    "on_attack": _h_attack,
    "on_no_attack": lambda s, p, c: None,
    "on_take_damage": _h_take_damage,
    "on_would_die": _h_would_die,
    "on_yield": _h_yield,
    "on_enter_tokyo": lambda s, p, c: None,
    "on_buy_phase": lambda s, p, c: None,
    "on_before_gain_card": lambda s, p, c: None,
    "on_buy_card": _h_buy_card,
    "on_turn_end": _h_turn_end,
}


def _discard_card(state, pid, key):
    """Remove one Keep card with the given key from a monster and discard it."""
    cards = state["mon"][pid]["cards"]
    for i, cid in enumerate(cards):
        if CATALOG.get(cid, {}).get("key") == key:
            cards.pop(i)
            state["discard"].append(cid)
            return True
    return False


# ---------------------------------------------------------------------------
# Manual actions (fired by the active monster this turn)
# ---------------------------------------------------------------------------

def card_action(state, pid, card, choice):
    key = CATALOG.get(card, {}).get("key")
    if not key or not _has(state, pid, key):
        return
    m = state["mon"][pid]
    rolling = state["phase"] == "rolling" and state["current"] == pid and state["roll_num"] > 0

    if key == "herd_culler":
        if not rolling or _mem(state, pid).get("herd_used"):
            return
        i = _die_index(state, choice)
        if i is None:
            return
        state["dice"][i] = "1"
        _mem(state, pid)["herd_used"] = True
        gl._log(state, f"{gl._nm(pid)} culls a die to a 1.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "plot_twist":
        if not rolling:
            return
        i, f = _die_and_face(state, choice)
        if i is None:
            return
        state["dice"][i] = f
        _discard_card(state, pid, "plot_twist")
        gl._log(state, f"{gl._nm(pid)} twists a die to {f}.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "background_dweller":
        if not rolling:
            return
        i = _die_index(state, choice)
        if i is None or state["dice"][i] != "3":
            return
        rng = random.Random()
        state["dice"][i] = rng.choice(gl.FACES)
        gl._log(state, f"{gl._nm(pid)} freely rerolls a [3] (Background Dweller).", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "stretchy":
        if not rolling or m["energy"] < 2:
            return
        i, f = _die_and_face(state, choice)
        if i is None:
            return
        gl.spend_energy(state, pid, 2)
        state["dice"][i] = f
        gl._log(state, f"{gl._nm(pid)} stretches a die to {f} (2⚡).", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "telepath":
        if state["phase"] != "rolling" or m["energy"] < 1:
            return
        gl.spend_energy(state, pid, 1)
        state["rolls_left"] += 1
        gl._log(state, f"{gl._nm(pid)} reads the dice (Telepath +1 reroll).", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "smoke_cloud":
        if state["phase"] != "rolling" or _mem(state, pid).get("smoke", 0) <= 0:
            return
        _mem(state, pid)["smoke"] -= 1
        state["rolls_left"] += 1
        gl._log(state, f"{gl._nm(pid)} vanishes in smoke (+1 reroll).", pid=pid, kind="sys")
        if _mem(state, pid)["smoke"] <= 0:
            _discard_card(state, pid, "smoke_cloud")
        gl._bump(state)

    elif key == "rapid_healing":
        if m["energy"] < 2 or m["hp"] >= m["maxhp"]:
            return
        gl.spend_energy(state, pid, 2)
        gl.heal(state, pid, 1)
        gl._log(state, f"{gl._nm(pid)} rapidly heals 1❤ (2⚡).", pid=pid, kind="heal")

    elif key == "wings":
        if m["energy"] < 2 or _mem(state, pid).get("wings"):
            return
        gl.spend_energy(state, pid, 2)
        _mem(state, pid)["wings"] = True
        gl._log(state, f"{gl._nm(pid)} takes wing - damage negated until its next turn.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "metamorph":
        if state["phase"] != "buying":
            return
        cid = choice.get("card") if isinstance(choice, dict) else None
        if not cid or cid not in m["cards"]:
            return
        C = CATALOG.get(cid)
        if not C:
            return
        m["cards"].remove(cid)
        state["discard"].append(cid)
        gl.gain_energy(state, pid, C["cost"])
        gl._log(state, f"{gl._nm(pid)} morphs {C['name']} back into {C['cost']}⚡.", pid=pid, kind="energy")
        gl._bump(state)


def _die_index(state, choice):
    if choice is None:
        return None
    i = choice.get("index") if isinstance(choice, dict) else choice
    try:
        i = int(i)
    except (TypeError, ValueError):
        return None
    return i if 0 <= i < len(state["dice"]) else None


def _die_and_face(state, choice):
    i = _die_index(state, choice)
    if i is None or not isinstance(choice, dict):
        return None, None
    f = choice.get("face")
    return (i, f) if f in gl.FACES else (None, None)
