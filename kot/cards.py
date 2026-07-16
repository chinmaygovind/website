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
  card_action(...)     a manual ability a monster fires - usually on its own
                       turn, but Psychic Probe and Opportunist react on
                       someone else's (see game_logic._OFF_TURN_CARD_KEYS)
  card_extra_view(...) per-card extra display fields (Mimic's current target,
                       a pending Made in a Lab peek, Healing Ray's aim)

Mimic works by making ``_keys`` also yield whatever key it's currently
copying, so every other card's ``_has``/``_count``/``mod`` checks in this file
pick up a mimicked ability for free, with no special-casing needed anywhere
else. Everything in the 66-card set is implemented.
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
     "Store any amount of your ⚡ here to double it, then take 2⚡ back at the "
     "start of each turn until it runs out."),
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
    """Iterator over the mechanic keys of a monster's owned Keep cards - plus
    whatever key Mimic is currently copying, so every other check in this file
    (``_has``/``_count``/``mod``) picks up a mimicked ability for free."""
    for cid in state["mon"][pid]["cards"]:
        c = CATALOG.get(cid)
        if not c:
            continue
        yield c["key"]
        if c["key"] == "mimic":
            mk = _mem(state, pid).get("mimic_key")
            if mk:
                yield mk


def _physical_keys(state, pid):
    """Like ``_keys`` but never substitutes in a mimicked key - for the one
    self-discarding card (Plot Twist) where mimicry shouldn't grant unlimited
    free uses of what's meant to be a one-shot effect."""
    for cid in state["mon"][pid]["cards"]:
        c = CATALOG.get(cid)
        if c:
            yield c["key"]


def _physically_has(state, pid, key):
    return any(k == key for k in _physical_keys(state, pid))


def _count(state, pid, key):
    return sum(1 for k in _keys(state, pid) if k == key)


def _has(state, pid, key):
    return _count(state, pid, key) > 0


def has_jets(state, pid):
    """Jets: a monster in Tokyo who's attacked may leave and take none of that
    attack's damage - checked by game_logic before applying yield-time damage,
    so it needs to be public (game_logic never reaches into cards.py internals)."""
    return _has(state, pid, "jets")


def eligible_psychic_probers(state, roller):
    """Who can still use Psychic Probe against ``roller`` this turn - anyone
    else, alive, who owns (or mimics) it and hasn't already used their one
    probe against this same roller yet. Checked by game_logic.resolve() to
    open a last-chance window before a fast Done robs them of it, so it
    needs to be public (game_logic never reaches into cards.py internals)."""
    probed = _mem(state, roller).get("probed_by", [])
    return [q for q in state["players"]
            if q != roller and state["mon"][q]["alive"]
            and _has(state, q, "psychic_probe") and q not in probed]


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


def heal_ray_already_fired(state, pid):
    """Healing Ray fires immediately (card_action), spending this roll's whole
    heart count on the chosen target right then. Checked by game_logic.resolve()
    so it doesn't ALSO self-heal/shed poison with those same, already-used hearts."""
    return _mem(state, pid).get("heal_ray_spent_roll") == state["roll_num"]


def card_extra_view(state, pid, cid, key):
    """Extra client-display fields for one owned card, beyond its static
    CATALOG entry - only Mimic/Made in a Lab/Monster Batteries/Wings need
    this (Mimic also surfaces a mimicked Plot Twist/Smoke Cloud/Wings/Monster
    Batteries' own independent charge state, same shape as the real card)."""
    if key == "mimic":
        mk = _mem(state, pid).get("mimic_key")
        if mk:
            t = CATALOG.get(mk, {})
            target = {"id": mk, "name": t.get("name"), "emoji": t.get("emoji")}
            mem = _mem(state, pid)
            # A mimicked Plot Twist, Smoke Cloud or Monster Batteries draws
            # from the mimicker's own independent pool (set up in
            # card_action's "mimic" branch) - surface it the same way the
            # real card would, so the client can hide the button once it's
            # actually spent.
            if mk == "monster_batteries" and mem.get("battery_charged"):
                target["battery_left"] = mem.get("batteries", 0)
            elif mk == "smoke_cloud":
                target["smoke_left"] = mem.get("smoke", 0)
            elif mk == "plot_twist":
                target["used"] = bool(mem.get("plot_twist_used"))
            elif mk == "wings" and mem.get("wings"):
                target["wings_active"] = True
            return {"mimic_target": target}
    elif key == "made_in_a_lab":
        lk = _mem(state, pid).get("lab_peek")
        if lk and state["deck"] and state["deck"][-1] == lk:
            t = CATALOG.get(lk, {})
            cost = max(0, t.get("cost", 0) - mod(state, pid, "buy_discount"))
            return {"lab_peek": {"id": lk, "name": t.get("name"), "emoji": t.get("emoji"), "cost": cost}}
    elif key == "monster_batteries":
        mem = _mem(state, pid)
        if mem.get("battery_charged"):
            return {"battery_left": mem.get("batteries", 0)}
    elif key == "wings":
        if _mem(state, pid).get("wings"):
            return {"wings_active": True}
    return None


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
        faces = [rng.choice(gl.FACES) for _ in range(n)]
        saved = faces.count("heart")
        mem = _mem(state, target)
        mem["camo_seq"] = mem.get("camo_seq", 0) + 1
        mem["camo_roll"] = {"id": mem["camo_seq"], "dice": faces, "saved": saved, "blocked": len(faces)}
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
    if _has(state, attacker, "fire_breathing") and not state.get("_fb_lock"):
        # Guard against the neighbor hit below re-entering this same branch
        # (it's itself a distinct deal_damage call with attacker=attacker).
        order = state["players"]
        i = order.index(attacker)
        n_players = len(order)
        state["_fb_lock"] = True
        try:
            for nb in {order[(i - 1) % n_players], order[(i + 1) % n_players]}:
                if nb != attacker and state["mon"][nb]["alive"]:
                    gl.deal_damage(state, nb, 1, attacker=attacker)
        finally:
            state.pop("_fb_lock", None)


def on_any_elimination(state, pid):
    for q in state["players"]:
        if q != pid and state["mon"][q]["alive"] and _has(state, q, "eater_of_the_dead"):
            gl.gain_vp(state, q, 3)
            gl._log(state, f"{gl._nm(q)} feasts on the fallen (+3 VP).", pid=q, kind="vp")


# ---------------------------------------------------------------------------
# A card-driven attack (dice-claw targeting/Jets/yield rules apply) - used by
# Poison Quills.
# ---------------------------------------------------------------------------

def _card_attack(state, attacker, dmg):
    # Shares _attack's Jets-aware, yield-queue-merging damage application so
    # this hits exactly like a claw attack would - a Tokyo occupant still
    # gets to yield afterward, and Jets still lets them dodge it by leaving.
    targets = gl._attack_targets(state, attacker)
    gl._apply_attack(state, attacker, dmg, targets)


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
            if state["tokyo"]["city"] is None:
                gl._take_tokyo(state, pid, "city")
            elif state["use_bay"] and state["tokyo"]["bay"] is None:
                gl._take_tokyo(state, pid, "bay")
            else:
                occ = state["tokyo"]["city"]
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
    mem["probed_by"] = []       # Psychic Probe: who's already probed this roll this turn
    mem["heal_ray_spent_roll"] = None   # Healing Ray: hasn't fired yet this turn
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
        gl._log(state, f"{gl._nm(pid)}'s offspring rises to fight on!", pid=pid, kind="revive")
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


def _detach_keep_card(state, pid, key):
    """Undo whatever standing effect a Keep card grants when it stops being
    held by pid - the mirror of on_acquire's one-time setup, for the handful
    of keys where that setup would otherwise leak (a permanent +maxhp that
    outlives the card) or go dead for whoever takes it next (a mid-use
    counter reset to zero). Called wherever a still-active Keep card leaves
    a monster's hand: Metamorph's discard-for-energy and Parasitic Tentacles'
    theft. Returns any per-card memory the card was carrying, so a thief can
    inherit it instead of it just evaporating.
    """
    m = state["mon"][pid]
    mem = _mem(state, pid)
    if key == "even_bigger":
        m["maxhp"] -= 2
        m["hp"] = min(m["hp"], m["maxhp"])
    elif key == "wings":
        # An already-paid-for shield protects the monster that bought it,
        # not the card itself - it doesn't transfer to a thief (who never
        # paid the 2⚡ to raise it) and it can't be cashed out by buying
        # Wings, activating it, then Metamorphing the card away for a
        # refund while keeping the protection.
        mem["wings"] = False
    elif key == "monster_batteries":
        return {"battery_charged": mem.pop("battery_charged", False), "batteries": mem.pop("batteries", 0)}
    elif key == "smoke_cloud":
        return {"smoke": mem.pop("smoke", 0)}
    elif key == "mimic":
        if "mimic_key" in mem:
            return {"mimic_key": mem.pop("mimic_key")}
    return None


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
        owns_physically = _physically_has(state, pid, "plot_twist")
        mem = _mem(state, pid)
        if not owns_physically and mem.get("plot_twist_used"):
            return
        i, f = _die_and_face(state, choice)
        if i is None:
            return
        state["dice"][i] = f
        # A real copy discards itself; a mimicked copy just marks its own
        # one-time use spent, until the mimicker re-picks it for a fresh one.
        if owns_physically:
            _discard_card(state, pid, "plot_twist")
        else:
            mem["plot_twist_used"] = True
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
        if state["phase"] != "buying" or state["current"] != pid:
            return
        cid = choice.get("card") if isinstance(choice, dict) else None
        if not cid or cid not in m["cards"]:
            return
        C = CATALOG.get(cid)
        if not C:
            return
        m["cards"].remove(cid)
        _detach_keep_card(state, pid, C["key"])
        state["discard"].append(cid)
        gl.gain_energy(state, pid, C["cost"])
        gl._log(state, f"{gl._nm(pid)} morphs {C['name']} back into {C['cost']}⚡.", pid=pid, kind="energy")
        gl._bump(state)

    elif key == "monster_batteries":
        # One-time choice (any amount, including 0) of how much of your
        # current energy to lock away - doubled - in the batteries. Once
        # decided (even at 0) it can't be redecided; _h_turn_start drains
        # 2⚡/turn from whatever got stored until it runs out.
        if state["phase"] != "buying" or state["current"] != pid:
            return
        mem = _mem(state, pid)
        if mem.get("battery_charged"):
            return
        amt = choice.get("amount") if isinstance(choice, dict) else None
        try:
            amt = int(amt)
        except (TypeError, ValueError):
            return
        amt = max(0, min(amt, m["energy"]))
        gl.spend_energy(state, pid, amt)
        mem["battery_charged"] = True
        mem["batteries"] = amt * 2
        if amt > 0:
            gl._log(state, f"{gl._nm(pid)} stores {amt}⚡ in its batteries, doubled to {amt * 2}⚡.", pid=pid, kind="energy")
        else:
            gl._log(state, f"{gl._nm(pid)} leaves its batteries empty.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "mimic":
        # "At the start of your turn" - the real card gates the (free first
        # pick or 1-energy change) to before you've rolled, so you can't peek
        # at your dice and then reactively pick whatever passive ability
        # would help that specific roll most.
        if state["current"] != pid or state["roll_num"] != 0:
            return
        cid = choice.get("card") if isinstance(choice, dict) else None
        if not cid or cid == "mimic":
            return
        target_key = None
        for q in state["players"]:
            if q == pid:
                continue
            if cid in state["mon"][q]["cards"]:
                target_key = CATALOG.get(cid, {}).get("key")
                break
        if not target_key:
            return
        mem = _mem(state, pid)
        changing = mem.get("mimic_key") is not None
        if changing:
            if m["energy"] < 1:
                return
            gl.spend_energy(state, pid, 1)
        mem["mimic_key"] = target_key
        # Plot Twist, Smoke Cloud and Monster Batteries are one-time-charge
        # cards, not repeatable passives - "treat this as if you had that
        # card" means the mimicker gets their OWN independent pool (never
        # shared with, or drained from, the card's actual owner), fresh every
        # time they (re)commit to copying it, same as a real purchase would.
        if target_key == "plot_twist":
            mem["plot_twist_used"] = False
        elif target_key == "smoke_cloud":
            mem["smoke"] = 3
        elif target_key == "monster_batteries":
            mem["battery_charged"] = False
            mem["batteries"] = 0
        name = CATALOG.get(cid, {}).get("name", cid)
        suffix = " (1⚡)" if changing else ""
        gl._log(state, f"{gl._nm(pid)} mimics {name}{suffix}.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "psychic_probe":
        roller = state["current"]
        if roller == pid:
            return
        pp = state.get("pending_probe")
        in_window = bool(pp and pp.get("roller") == roller and pp["queue"] and pp["queue"][0] == pid)
        if not in_window and (state["phase"] != "rolling" or state["roll_num"] <= 0):
            return
        probed = _mem(state, roller).setdefault("probed_by", [])
        if pid in probed:
            return
        if isinstance(choice, dict) and choice.get("pass"):
            if not in_window:
                return
            gl._log(state, f"{gl._nm(pid)} lets it go.", pid=pid, kind="sys")
            gl._probe_window_step(state, pid)
            gl._bump(state)
            return
        i = _die_index(state, choice)
        if i is None:
            return
        rng = random.Random()
        state["dice"][i] = rng.choice(gl.FACES)
        probed.append(pid)
        gl._log(state, f"{gl._nm(pid)} psychically rerolls one of {gl._nm(roller)}'s dice.", pid=pid, kind="sys")
        if in_window:
            gl._probe_window_step(state, pid)
        gl._bump(state)

    elif key == "made_in_a_lab":
        if state["phase"] != "buying" or state["current"] != pid:
            return
        action = choice.get("action") if isinstance(choice, dict) else "peek"
        if action == "peek":
            if not state["deck"]:
                return
            cid = state["deck"][-1]
            _mem(state, pid)["lab_peek"] = cid
            name = CATALOG.get(cid, {}).get("name", cid)
            gl._log(state, f"{gl._nm(pid)} peeks at the deck (Made in a Lab): {name}.", pid=pid, kind="sys")
            gl._bump(state)
        elif action == "buy":
            cid = _mem(state, pid).get("lab_peek")
            if not cid or not state["deck"] or state["deck"][-1] != cid:
                return
            C = CATALOG.get(cid)
            if not C:
                return
            cost = max(0, C["cost"] - gl.mod(state, pid, "buy_discount"))
            if m["energy"] < cost:
                return
            gl.spend_energy(state, pid, cost)
            state["deck"].pop()
            m["stat"]["cards"] += 1
            gl._log(state, f"{gl._nm(pid)} buys {C['name']} for {cost}⚡ (Made in a Lab).", pid=pid, kind="buy")
            trigger(state, pid, "on_before_gain_card", card=cid)
            if C["type"] == "keep":
                m["cards"].append(cid)
            else:
                state["discard"].append(cid)
            on_acquire(state, pid, cid)
            trigger(state, pid, "on_buy_card", card=cid)
            _mem(state, pid)["lab_peek"] = None
            gl._bump(state)

    elif key == "opportunist":
        # A card revealed by a purchase or a Sweep Shop is snipeable, whoever's
        # turn it is, until it's bought (by anyone) or reshuffled away. A
        # sweep opens a window on all 3 slots at once, so the player picks
        # which (if any) to snap up from a list, one at a time.
        idx = choice.get("index") if isinstance(choice, dict) else None
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            return
        win = state.get("opportunist_window") or []
        entry = next((e for e in win if e["index"] == idx), None)
        if not entry or state["shop"][idx] != entry["cid"]:
            return
        cid = entry["cid"]
        C = CATALOG.get(cid)
        if not C:
            return
        cost = max(0, C["cost"] - gl.mod(state, pid, "buy_discount"))
        if m["energy"] < cost:
            return
        gl.spend_energy(state, pid, cost)
        m["stat"]["cards"] += 1
        gl._log(state, f"{gl._nm(pid)} buys {C['name']} for {cost}⚡ (Opportunist).", pid=pid, kind="buy")
        trigger(state, pid, "on_before_gain_card", card=cid)
        if C["type"] == "keep":
            m["cards"].append(cid)
        else:
            state["discard"].append(cid)
        on_acquire(state, pid, cid)
        trigger(state, pid, "on_buy_card", card=cid)
        state["shop"][idx] = state["deck"].pop() if state["deck"] else None
        gl._set_opportunist_slot(state, idx)
        gl._bump(state)

    elif key == "parasitic_tentacles":
        if state["phase"] != "buying" or state["current"] != pid:
            return
        target_pid = choice.get("pid") if isinstance(choice, dict) else None
        cid = choice.get("card") if isinstance(choice, dict) else None
        if not target_pid or not cid or target_pid == pid:
            return
        tgt = state["mon"].get(target_pid)
        if not tgt or not tgt["alive"] or cid not in tgt["cards"]:
            return
        C = CATALOG.get(cid)
        if not C or C["type"] != "keep":
            return
        cost = max(0, C["cost"] - gl.mod(state, pid, "buy_discount"))
        if m["energy"] < cost:
            return
        gl.spend_energy(state, pid, cost)
        gl.gain_energy(state, target_pid, cost)
        tgt["cards"].remove(cid)
        # A card's standing effect belongs to whoever holds it, not whoever
        # bought it first - detach it from the old owner (undoing a permanent
        # +maxhp, or handing back its per-card memory) before it counts as
        # newly acquired for the thief.
        carried = _detach_keep_card(state, target_pid, C["key"]) or {}
        trigger(state, pid, "on_before_gain_card", card=cid)
        m["cards"].append(cid)
        if C["key"] == "even_bigger":
            m["maxhp"] += 2
            gl.heal(state, pid, 2)
        elif carried:
            _mem(state, pid).update(carried)
        trigger(state, pid, "on_buy_card", card=cid)
        gl._log(state, f"{gl._nm(pid)} rips {C['name']} from {gl._nm(target_pid)} for {cost}⚡ (Parasitic Tentacles).", pid=pid, kind="buy")
        gl._bump(state)

    elif key == "healing_ray":
        if state["phase"] != "rolling" or state["current"] != pid or state["roll_num"] <= 0:
            return
        mem = _mem(state, pid)
        if mem.get("heal_ray_spent_roll") == state["roll_num"]:
            return  # already fired this roll's hearts
        target_pid = choice.get("pid") if isinstance(choice, dict) else None
        tgt = state["mon"].get(target_pid) if target_pid else None
        if not tgt or target_pid == pid or not tgt["alive"]:
            return
        h = state["dice"].count("heart")
        if h <= 0:
            return
        mem["heal_ray_spent_roll"] = state["roll_num"]
        # The target can only ever pay for as much as they can afford - any
        # hearts beyond that are wasted, not free healing on credit.
        affordable = min(h, tgt["energy"] // 2)
        healed = gl.heal(state, target_pid, affordable, via_dice=True) if affordable > 0 else 0
        if healed:
            paid = healed * 2
            gl.spend_energy(state, target_pid, paid)
            gl.gain_energy(state, pid, paid)
            gl._log(state, f"{gl._nm(pid)} heals {gl._nm(target_pid)} for {healed} with its healing ray ({paid}⚡ paid).", pid=pid, kind="heal")
        elif gl._in_tokyo(state, target_pid):
            gl._log(state, f"{gl._nm(pid)} can't heal {gl._nm(target_pid)} while it's in Tokyo.", pid=pid, kind="sys")
        else:
            gl._log(state, f"{gl._nm(pid)} fires its healing ray at {gl._nm(target_pid)}, but it can't afford to pay.", pid=pid, kind="sys")
        gl._bump(state)

    elif key == "camouflage":
        # Purely an acknowledgement: the mitigation itself already happened
        # instantly in adjust_incoming (there's no game-state reason to make
        # anyone wait on it). This just clears the pending roll once its
        # owner has clicked through the client's reveal animation, so it
        # doesn't linger and re-show after a reload.
        mem = _mem(state, pid)
        if mem.get("camo_roll"):
            mem["camo_roll"] = None
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
