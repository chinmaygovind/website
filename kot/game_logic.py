"""King of Tokyo - pure game engine.

No Flask, no I/O: every function takes a plain ``state`` dict and mutates it in
place, returning nothing (the human-readable feed lives in ``state["log"]`` and
the client re-renders from ``public_view``). Keeping the rules here and
side-effect-free is what lets ``tests/test_engine.py`` prove the game is correct.

Turn flow (one monster at a time):
  start_turn -> rolling (roll + up to 2 rerolls) -> resolve dice
    (energy / numbers->VP / hearts->heal / claws->attack) -> optional yield
    decisions from monsters in Tokyo -> buying (shop / cards) -> end_turn.

Card effects live in ``cards.py`` and hook in through ``_cards()`` (lazy import to
avoid a cycle): passive numeric modifiers via ``cards.mod``, one-shot effects via
``cards.on_acquire``, and event hooks via ``cards.trigger``.
"""

import random

FACES = ["1", "2", "3", "heart", "energy", "claw"]

START_HP = 10
START_MAX_HP = 10
START_VP = 0
START_ENERGY = 0
WIN_VP = 20
BASE_DICE = 6
BASE_REROLLS = 2          # rerolls after the initial roll (3 rolls total)
SHOP_SIZE = 3
SWEEP_COST = 2            # energy to discard the 3 shop cards and redraw

# Seconds a yield decision waits before auto-staying (kept for parity/UI); the app
# owns any timers. The engine itself never blocks.
YIELD_GRACE_SECONDS = 20


def _cards():
    import cards
    return cards


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def new_game(players, seed=None):
    """``players`` is a list of pids in seat order. Returns a fresh state."""
    rng = random.Random(seed)
    pids = list(players)
    deck = _cards().build_deck(rng)
    shop = [deck.pop() for _ in range(min(SHOP_SIZE, len(deck)))]
    while len(shop) < SHOP_SIZE:
        shop.append(None)
    state = {
        "players": pids,
        "current": pids[0],
        "phase": "rolling",              # rolling | yield | buying | ended
        "mon": {pid: {
            "hp": START_HP, "maxhp": START_MAX_HP, "vp": START_VP,
            "energy": START_ENERGY, "alive": True,
            "cards": [],                 # owned Keep cards (ids)
            "tokens": {},                # shrink / poison / smoke / ...
            "stat": {"damage": 0, "kos": 0, "cards": 0, "tokyo_turns": 0},
        } for pid in pids},
        "tokyo": {"city": None, "bay": None},
        "use_bay": len(pids) >= 5,
        "dice": [],                      # current faces
        "kept": [],                      # which dice the player has locked
        "rolls_left": 0,
        "roll_num": 0,                   # rolls taken this turn (0 = not rolled yet)
        "deck": deck,
        "discard": [],
        "shop": shop,
        "opportunist_window": None,      # {"index":slot, "cid":card} - Opportunist's snipeable freshly-revealed card
        "pending_yield": None,           # {"queue":[pid...], "attacker":pid}
        "ko_order": [],                  # pids in the order they were eliminated
        "winner": None,
        "standings": [],                 # filled at game end: [{pid, place, vp}]
        "turn": 0,
        "log": [],
        "log_seq": 0,
        "seq": 0,                        # bumps on every mutation (client de-dupe)
    }
    _log(state, "The monsters gather. Tokyo awaits.", kind="sys")
    _begin_turn(state, pids[0], first=True)
    return state


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _bump(state):
    state["seq"] += 1


def _log(state, text, pid=None, kind=None):
    state["log_seq"] += 1
    state.setdefault("log", []).append({"id": state["log_seq"], "text": text,
                                        "pid": pid, "kind": kind})
    state["log"] = state["log"][-80:]


def _alive(state):
    return [p for p in state["players"] if state["mon"][p]["alive"]]


def _in_tokyo(state, pid):
    t = state["tokyo"]
    if t["city"] == pid:
        return "city"
    if t["bay"] == pid:
        return "bay"
    return None


def _tokyo_occupants(state):
    return [p for p in (state["tokyo"]["city"], state["tokyo"]["bay"]) if p]


def _next_alive(state, pid):
    order = state["players"]
    n = len(order)
    i = order.index(pid) if pid in order else -1
    for k in range(1, n + 1):
        cand = order[(i + k) % n]
        if state["mon"][cand]["alive"]:
            return cand
    return None


def mod(state, pid, key):
    """Sum of a passive numeric modifier across the monster's Keep cards."""
    return _cards().mod(state, pid, key)


# ---------------------------------------------------------------------------
# Resource helpers (also called by cards.py)
# ---------------------------------------------------------------------------

def gain_energy(state, pid, n):
    if n <= 0:
        return
    m = state["mon"][pid]
    m["energy"] += n + (mod(state, pid, "energy_per_gain") if n > 0 else 0)
    _bump(state)


def spend_energy(state, pid, n):
    state["mon"][pid]["energy"] = max(0, state["mon"][pid]["energy"] - n)
    _bump(state)


def gain_vp(state, pid, n):
    if n == 0:
        return
    m = state["mon"][pid]
    m["vp"] = max(0, m["vp"] + n)
    _bump(state)
    if n > 0 and m["vp"] >= WIN_VP and state["phase"] != "ended":
        _end_game(state, pid, reason="vp")


def heal(state, pid, n, via_dice=False):
    """Heal n. Heart dice can't heal a monster while it's in Tokyo; card healing can."""
    m = state["mon"][pid]
    if not m["alive"] or n <= 0:
        return 0
    if via_dice and _in_tokyo(state, pid):
        return 0
    n += mod(state, pid, "heal_bonus") if n > 0 else 0
    before = m["hp"]
    m["hp"] = min(m["maxhp"], m["hp"] + n)
    if m["hp"] != before:
        _bump(state)
    return m["hp"] - before


def deal_damage(state, target, n, attacker=None):
    """Apply n damage to target after card mitigation. Returns damage actually taken."""
    m = state["mon"][target]
    if not m["alive"] or n <= 0:
        return 0
    rng = random.Random()
    n = _cards().adjust_incoming(state, target, n, attacker, rng)
    if n <= 0:
        _bump(state)          # a mitigation card (Camouflage/Armor Plating/Wings) still changed the game
        return 0
    m["hp"] = max(0, m["hp"] - n)
    _bump(state)
    if attacker:
        state["mon"][attacker].setdefault("_dmg", 0)
        state["mon"][attacker]["_dmg"] += n
        state["mon"][attacker]["stat"]["damage"] += n
        if attacker != target:
            _cards().on_deal_damage(state, attacker, target, n)  # Poison Spit / Shrink Ray
    _cards().trigger(state, target, "on_take_damage", attacker=attacker, amount=n)
    if m["hp"] <= 0 and m["alive"]:
        _cards().trigger(state, target, "on_would_die", attacker=attacker)
        if m["hp"] <= 0 and m["alive"]:      # card (It Has a Child) may have revived
            _eliminate(state, target, by=attacker)
    return n


def _eliminate(state, pid, by=None):
    m = state["mon"][pid]
    if not m["alive"]:
        return
    m["alive"] = False
    slot = _in_tokyo(state, pid)
    if slot:
        state["tokyo"][slot] = None
    state["ko_order"].append(pid)
    if by and by != pid and state["mon"].get(by):
        state["mon"][by]["stat"]["kos"] += 1
    if by and by != pid:
        _log(state, f"{_nm(pid)} is knocked out by {_nm(by)}!", pid=pid, kind="ko")
    else:
        _log(state, f"{_nm(pid)} is knocked out!", pid=pid, kind="ko")
    _bump(state)
    _cards().on_any_elimination(state, pid)   # Eater of the Dead
    if state["phase"] == "ended":
        return
    # Tokyo Bay closes once the field is down to 4 or fewer monsters: its occupant
    # slides into Tokyo City if it's empty, otherwise leaves Tokyo.
    if state["use_bay"] and len(_alive(state)) <= 4:
        state["use_bay"] = False
        bay = state["tokyo"]["bay"]
        if bay:
            state["tokyo"]["bay"] = None
            if state["tokyo"]["city"] is None:
                state["tokyo"]["city"] = bay
    alive = _alive(state)
    if len(alive) <= 1 and state["phase"] != "ended":
        _end_game(state, alive[0] if alive else None, reason="last")


# The app injects a pid->display-name map via set_names so the engine can write
# readable log lines. _sync_names loads it into a module global before each action.
_CURRENT_NAMES = {}


def set_names(state, names):
    state["names"] = dict(names)


def _nm(pid):
    return _CURRENT_NAMES.get(pid, pid)


# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------

def _begin_turn(state, pid, first=False):
    _sync_names(state)
    state["current"] = pid
    state["turn"] += 1
    state["phase"] = "rolling"
    state["opportunist_window"] = None
    m = state["mon"][pid]
    # Start-of-turn Tokyo victory points.
    slot = _in_tokyo(state, pid)
    if slot:
        m["stat"]["tokyo_turns"] += 1
    if slot == "city":
        gain_vp(state, pid, 2 + mod(state, pid, "tokyo_start_vp_bonus"))
        _log(state, f"{_nm(pid)} starts the turn in Tokyo City (+{2 + mod(state, pid, 'tokyo_start_vp_bonus')} VP).", pid=pid, kind="vp")
    elif slot == "bay":
        gain_vp(state, pid, 1 + mod(state, pid, "tokyo_start_vp_bonus"))
        _log(state, f"{_nm(pid)} starts the turn in Tokyo Bay (+{1 + mod(state, pid, 'tokyo_start_vp_bonus')} VP).", pid=pid, kind="vp")
    if state["phase"] == "ended":
        return
    _cards().trigger(state, pid, "on_turn_start")
    if state["phase"] == "ended":
        return
    m["_dmg"] = 0
    # Fresh dice tray (Extra Head adds dice; shrink counters remove them).
    ndice = BASE_DICE + mod(state, pid, "extra_dice") - m["tokens"].get("shrink", 0)
    ndice = max(1, ndice - m.pop("_freeze_penalty", 0))
    state["dice"] = ["?" for _ in range(ndice)]
    state["kept"] = [False for _ in range(ndice)]
    state["rolls_left"] = BASE_REROLLS + mod(state, pid, "extra_rerolls")
    state["roll_num"] = 0
    _bump(state)


def _sync_names(state):
    global _CURRENT_NAMES
    _CURRENT_NAMES = state.get("names", {})


def do_roll(state, pid, keep):
    """Roll (first time) or reroll the dice not in ``keep`` (a list of indices)."""
    if state["phase"] != "rolling" or state["current"] != pid:
        return
    _sync_names(state)
    rng = random.Random()
    n = len(state["dice"])
    keep = set(i for i in (keep or []) if 0 <= i < n)
    if state["roll_num"] == 0:
        state["dice"] = [rng.choice(FACES) for _ in range(n)]
        state["kept"] = [False] * n
        state["roll_num"] = 1
    else:
        if state["rolls_left"] <= 0 and not _spend_smoke(state, pid):
            return
        for i in range(n):
            if i not in keep:
                state["dice"][i] = rng.choice(FACES)
        state["kept"] = [i in keep for i in range(n)]
        if state["rolls_left"] > 0:
            state["rolls_left"] -= 1
        state["roll_num"] += 1
    _bump(state)


def _spend_smoke(state, pid):
    tok = state["mon"][pid]["tokens"]
    if tok.get("smoke", 0) > 0:
        tok["smoke"] -= 1
        return True
    return False


def set_keep(state, pid, keep):
    """Just record which dice are locked (visual); rerolling uses the keep set too."""
    if state["phase"] != "rolling" or state["current"] != pid or state["roll_num"] == 0:
        return
    n = len(state["dice"])
    keep = set(i for i in (keep or []) if 0 <= i < n)
    state["kept"] = [i in keep for i in range(n)]
    _bump(state)


def resolve(state, pid):
    """Stop rolling and resolve the dice."""
    if state["phase"] != "rolling" or state["current"] != pid or state["roll_num"] == 0:
        return
    _sync_names(state)
    dice = state["dice"]
    m = state["mon"][pid]
    m["_dmg"] = 0

    # 1) Energy.
    e = dice.count("energy")
    if e:
        gain_energy(state, pid, e)
        _log(state, f"{_nm(pid)} takes {e}⚡ energy.", pid=pid, kind="energy")

    # 2) Numbers -> victory points (three of a kind = that number, +1 each extra).
    for face in ("1", "2", "3"):
        c = dice.count(face)
        if c >= 3:
            v = int(face) + (c - 3)
            v += mod(state, pid, "set_vp_bonus")
            gain_vp(state, pid, v)
            _log(state, f"{_nm(pid)} scores {c}×{face} for +{v} VP.", pid=pid, kind="vp")
            if state["phase"] == "ended":
                return
    _cards().trigger(state, pid, "on_numbers", dice=list(dice))
    if state["phase"] == "ended":
        return

    # 3) Hearts -> heal (blocked while in Tokyo). A Heart that would be wasted
    #    (in Tokyo, or already at full Health) is instead used to shed a poison
    #    or shrink counter. Healing Ray fires as its own manual action mid-roll
    #    (card_action, immediately spending the hearts on another monster who
    #    pays 2⚡ per point healed) - if that already happened this roll, these
    #    same hearts don't ALSO do the normal things below.
    if not _cards().heal_ray_already_fired(state, pid):
        h = dice.count("heart")
        tok = m["tokens"]
        if h and (_in_tokyo(state, pid) or m["hp"] >= m["maxhp"]):
            for kind in ("poison", "shrink"):
                while h > 0 and tok.get(kind, 0) > 0:
                    tok[kind] -= 1
                    h -= 1
                    _log(state, f"{_nm(pid)} sheds a {kind} counter.", pid=pid, kind="heal")
        if h:
            healed = heal(state, pid, h, via_dice=True)
            if healed:
                _log(state, f"{_nm(pid)} heals {healed}❤.", pid=pid, kind="heal")
            elif _in_tokyo(state, pid):
                _log(state, f"{_nm(pid)} can't heal while in Tokyo.", pid=pid, kind="sys")

    # 4) Claws -> attack. Acid Attack adds damage even with no claws; Spiked
    #    Tail / Urbavore / Burrowing add on top when you actually attack.
    claws = dice.count("claw")
    dmg = claws + mod(state, pid, "damage_always")
    if dmg > 0:
        dmg += mod(state, pid, "damage_attack")
        if _in_tokyo(state, pid):
            dmg += mod(state, pid, "damage_in_tokyo")
    attacked = dmg > 0
    if attacked:
        _cards().trigger(state, pid, "on_attack", amount=dmg)
        if state["phase"] == "ended":
            return
        _attack(state, pid, dmg)
        if state["phase"] == "ended":
            return
    else:
        _cards().trigger(state, pid, "on_no_attack")

    _bump(state)
    if state["pending_yield"] and state["pending_yield"]["queue"]:
        state["phase"] = "yield"
        return
    _settle_tokyo(state, pid, attacked)
    if state["phase"] == "ended":
        return
    _enter_buying(state, pid)


def _attack(state, attacker, dmg):
    """Deal ``dmg`` to the right targets, queue yield decisions for survivors."""
    nova = mod(state, attacker, "hits_everyone") > 0
    in_tok = _in_tokyo(state, attacker)
    if nova:
        targets = [p for p in _alive(state) if p != attacker]
    elif in_tok:
        targets = [p for p in _alive(state) if _in_tokyo(state, p) is None and p != attacker]
    else:
        targets = [p for p in _tokyo_occupants(state) if state["mon"][p]["alive"]]

    where = "everyone" if nova else ("the monsters outside" if in_tok else "Tokyo")
    _log(state, f"{_nm(attacker)} attacks {where} for {dmg} damage.", pid=attacker, kind="attack")

    yield_queue = []
    deferred = {}   # pid -> damage held back for a Jets holder's stay/leave choice
    for t in list(targets):
        was_in = _in_tokyo(state, t)
        if was_in and _cards().has_jets(state, t):
            # Jets: don't apply this attack's damage yet - if they choose to
            # leave Tokyo below, they never take it at all.
            deferred[t] = dmg
            yield_queue.append(t)
            continue
        took = deal_damage(state, t, dmg, attacker=attacker)
        if took and was_in and state["mon"][t]["alive"] and _in_tokyo(state, t):
            yield_queue.append(t)
    # The active player entering an empty slot is handled by _settle_tokyo, run
    # by resolve() (or by yield_decision once every damaged monster has decided).
    state["pending_yield"] = {"queue": yield_queue, "attacker": attacker, "deferred": deferred} if yield_queue else None


def yield_decision(state, pid, leave):
    """A monster in Tokyo that took damage decides to stay or leave."""
    py = state.get("pending_yield")
    if state["phase"] != "yield" or not py:
        return
    if not py["queue"] or py["queue"][0] != pid:
        return
    py["queue"].pop(0)
    pending_dmg = py.get("deferred", {}).pop(pid, None)
    if leave:
        slot = _in_tokyo(state, pid)
        if slot:
            state["tokyo"][slot] = None
            _log(state, f"{_nm(pid)} yields Tokyo {slot.title()}.", pid=pid, kind="tokyo")
            _cards().trigger(state, pid, "on_yield", attacker=py["attacker"])
        if pending_dmg:
            _log(state, f"{_nm(pid)}'s jets carry it out untouched.", pid=pid, kind="sys")
    else:
        _log(state, f"{_nm(pid)} holds Tokyo.", pid=pid, kind="tokyo")
        if pending_dmg:
            deal_damage(state, pid, pending_dmg, attacker=py["attacker"])
            if state["phase"] == "ended":
                return
    _bump(state)
    if not py["queue"]:
        attacker = py["attacker"]
        state["pending_yield"] = None
        _settle_tokyo(state, attacker, True)
        if state["phase"] != "ended":
            _enter_buying(state, attacker)


def _settle_tokyo(state, pid, attacked):
    """The 'Enter Tokyo' step: if Tokyo City is empty, the active monster MUST
    take it (this is why the very first player enters with no claws). Tokyo Bay
    (5-6 players) is only taken by a monster that attacked into an occupied City."""
    if not state["mon"][pid]["alive"] or _in_tokyo(state, pid):
        return
    if state["tokyo"]["city"] is None:
        _take_tokyo(state, pid, "city")
    elif state["use_bay"] and state["tokyo"]["bay"] is None and attacked:
        _take_tokyo(state, pid, "bay")


def _take_tokyo(state, pid, slot):
    state["tokyo"][slot] = pid
    gain_vp(state, pid, 1)
    _log(state, f"{_nm(pid)} takes Tokyo {slot.title()} (+1 VP).", pid=pid, kind="tokyo")
    _cards().trigger(state, pid, "on_enter_tokyo")
    _bump(state)


def _enter_buying(state, pid):
    if state["phase"] == "ended":
        return
    state["phase"] = "buying"
    _cards().trigger(state, pid, "on_buy_phase")
    _bump(state)


# ---------------------------------------------------------------------------
# Buying
# ---------------------------------------------------------------------------

def buy_card(state, pid, index):
    if state["phase"] != "buying" or state["current"] != pid:
        return
    if not (0 <= index < len(state["shop"])):
        return
    cid = state["shop"][index]
    if cid is None:
        return
    C = _cards().CATALOG.get(cid)
    if not C:
        return
    cost = max(0, C["cost"] - mod(state, pid, "buy_discount"))
    m = state["mon"][pid]
    if m["energy"] < cost:
        return
    spend_energy(state, pid, cost)
    m["stat"]["cards"] += 1
    _log(state, f"{_nm(pid)} buys {C['name']} for {cost}⚡.", pid=pid, kind="buy")
    _cards().trigger(state, pid, "on_before_gain_card", card=cid)
    if C["type"] == "keep":
        m["cards"].append(cid)
    else:
        state["discard"].append(cid)
    _cards().on_acquire(state, pid, cid)
    _cards().trigger(state, pid, "on_buy_card", card=cid)
    # Refill the shop slot - and open an Opportunist window on whatever's revealed.
    state["shop"][index] = state["deck"].pop() if state["deck"] else None
    state["opportunist_window"] = {"index": index, "cid": state["shop"][index]} if state["shop"][index] else None
    _bump(state)


def sweep_shop(state, pid):
    if state["phase"] != "buying" or state["current"] != pid:
        return
    m = state["mon"][pid]
    if m["energy"] < SWEEP_COST:
        return
    spend_energy(state, pid, SWEEP_COST)
    for c in state["shop"]:
        if c is not None:
            state["deck"].insert(0, c)
    state["shop"] = [state["deck"].pop() if state["deck"] else None for _ in range(SHOP_SIZE)]
    _log(state, f"{_nm(pid)} sweeps the shop for {SWEEP_COST}⚡.", pid=pid, kind="buy")
    _bump(state)


# Card keys usable by someone OTHER than the active player - a reaction to
# another monster's roll (Psychic Probe) or to a freshly-revealed shop card
# (Opportunist). Everything else stays limited to the active player only.
_OFF_TURN_CARD_KEYS = {"psychic_probe", "opportunist", "camouflage"}


def card_action(state, pid, card, choice=None):
    """Player-triggered card ability (e.g. paying energy to fire an effect, or
    answering a prompt the engine raised). Delegated to cards.py, which owns the
    per-card logic and any phase/cost checks."""
    if state["phase"] == "ended":
        return
    key = _cards().CATALOG.get(card, {}).get("key")
    if state["current"] != pid and key not in _OFF_TURN_CARD_KEYS:
        return
    _sync_names(state)
    _cards().card_action(state, pid, card, choice)
    _bump(state)


def end_turn(state, pid):
    if state["phase"] != "buying" or state["current"] != pid:
        return
    _sync_names(state)
    _cards().trigger(state, pid, "on_turn_end")
    if state["phase"] == "ended":
        return
    # Advance.
    nxt = _next_alive(state, pid)
    if nxt is None:
        return
    if state["mon"][pid].get("_extra_turn"):
        state["mon"][pid]["_extra_turn"] = False
        _begin_turn(state, pid)
    else:
        _begin_turn(state, nxt)


def resign(state, pid):
    """A player leaves an in-progress game."""
    if state["phase"] == "ended" or not state["mon"].get(pid, {}).get("alive"):
        return
    was_current = state["current"] == pid
    # Clear any pending yield they owned.
    py = state.get("pending_yield")
    if py and pid in py.get("queue", []):
        py["queue"] = [q for q in py["queue"] if q != pid]
    _log(state, f"{_nm(pid)} flees the city.", pid=pid, kind="sys")
    _eliminate(state, pid, by=None)
    if state["phase"] == "ended":
        return
    if py and not py["queue"]:
        attacker = py["attacker"]
        state["pending_yield"] = None
        if state["mon"][attacker]["alive"]:
            _settle_tokyo(state, attacker, attacked=True)
            if state["phase"] == "yield":
                _enter_buying(state, attacker)
    if was_current:
        nxt = _next_alive(state, pid)
        if nxt is not None:
            _begin_turn(state, nxt)


# ---------------------------------------------------------------------------
# Game end
# ---------------------------------------------------------------------------

def _end_game(state, winner, reason="vp"):
    if state["phase"] == "ended":
        return
    state["phase"] = "ended"
    state["winner"] = winner
    alive = _alive(state)
    alive_sorted = sorted(alive, key=lambda p: (p != winner, -state["mon"][p]["vp"]))
    dead = list(reversed(state["ko_order"]))
    ranking = alive_sorted + [p for p in dead if p not in alive_sorted]
    for p in state["players"]:
        if p not in ranking:
            ranking.append(p)
    state["standings"] = [{"pid": p, "place": i + 1, "vp": state["mon"][p]["vp"]}
                          for i, p in enumerate(ranking)]
    if winner:
        _log(state, f"{_nm(winner)} is the King of Tokyo!", pid=winner, kind="win")
    _bump(state)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

def _shop_view(state):
    # Priced for the current player specifically (only they can buy right now) so
    # a buy_discount card (Alien Metabolism) shows the price they'll actually pay
    # instead of the sticker price - the client also uses this same number to
    # decide whether a card is affordable, so an undiscounted price here used to
    # both mislead the display AND wrongly grey out cards they could afford.
    current = state.get("current")
    discount = mod(state, current, "buy_discount") if current else 0
    out = []
    for cid in state["shop"]:
        if cid is None:
            out.append(None)
        else:
            C = _cards().CATALOG.get(cid, {})
            cost = max(0, C.get("cost", 0) - discount)
            out.append({"id": cid, "name": C.get("name"), "cost": cost,
                        "type": C.get("type"), "text": C.get("text"), "emoji": C.get("emoji")})
    return out


def _cards_view(state, pid, viewer_pid):
    out = []
    for cid in state["mon"][pid]["cards"]:
        C = _cards().CATALOG.get(cid, {})
        entry = {"id": cid, "name": C.get("name"), "cost": C.get("cost"),
                 "type": C.get("type"), "text": C.get("text"), "emoji": C.get("emoji")}
        extra = _cards().card_extra_view(state, pid, cid, C.get("key"))
        if extra:
            # Made in a Lab's peek is private - only the owner's own view of
            # their own cards includes it, never a broadcast to other players
            # or spectators (mimic_target and everything else stay public).
            if "lab_peek" in extra and viewer_pid != pid:
                extra = {k: v for k, v in extra.items() if k != "lab_peek"}
            entry.update(extra)
        out.append(entry)
    return out


def public_view(state, viewer_pid=None):
    return {
        "players": state["players"],
        "current": state["current"],
        "phase": state["phase"],
        "mon": {pid: {
            "hp": m["hp"], "maxhp": m["maxhp"], "vp": m["vp"], "energy": m["energy"],
            "alive": m["alive"], "tokens": m["tokens"],
            "cards": _cards_view(state, pid, viewer_pid),
            "probed_by": m.get("cardmem", {}).get("probed_by", []),
            "camo_roll": m.get("cardmem", {}).get("camo_roll"),
        } for pid, m in state["mon"].items()},
        "tokyo": state["tokyo"],
        "use_bay": state["use_bay"],
        "dice": state["dice"],
        "kept": state["kept"],
        "rolls_left": state["rolls_left"],
        "roll_num": state["roll_num"],
        "shop": _shop_view(state),
        "deck_left": len(state["deck"]),
        "opportunist_window": state.get("opportunist_window"),
        "pending_yield": state.get("pending_yield"),
        "winner": state["winner"],
        "standings": state["standings"],
        "turn": state["turn"],
        "log": state.get("log", [])[-50:],
        "seq": state["seq"],
    }
