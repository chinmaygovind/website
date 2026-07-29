"""King of Tokyo - the bot brain.

Pure decision-making: every function here takes the same plain ``state`` dict the
engine uses and returns a *choice*, never mutating anything and never touching
Flask, the database or the clock. ``app.py`` owns the eventlet timers that give
the bot its human-looking pacing and is the only thing that applies these
choices through the normal ``game_logic`` entry points, so a bot can never do
something a player couldn't.

The dice decision is the one that matters, so it gets a real search: a memoized
expectimax over the remaining rerolls that scores every reachable final dice
multiset with a context-aware utility (``_score_dice``). Everything else - when
to yield Tokyo, what to buy, how to split hearts between healing and shedding
counters - is a policy written in the same VP-equivalent units the dice search
uses, so the whole bot trades in one currency.

Calibrated against the 68 finished games in prod, where the 67%-winrate player
out-damaged the 26% player 682 to 440 with 27 KOs to 9 and more Tokyo turns,
while buying *fewer* cards. Half those games (35 of 68) were won by elimination
rather than on points, so the bot values aggression and Tokyo control well above
card accumulation.
"""

import itertools
import random
from functools import lru_cache

import game_logic as gl

# Index into a counts tuple, matching gl.FACES order.
ONE, TWO, THREE, HEART, ENERGY, CLAW = range(6)
NFACES = 6

# How often the bot takes the second-best dice keep instead of the best. Real
# players are not solvers; a little noise keeps it from playing identically in
# identical spots without meaningfully weakening it.
SLIP_CHANCE = 0.10

# Every strategic weight the bot trades on, in one place. These are not guesses:
# each was swept against the real engine over several thousand headless games,
# always in both seat orders because the first seat has a large built-in edge
# (a mirror match is 64/36 unbalanced). tests/test_bot.py holds the strength
# thresholds that keep them honest - re-run the sweep if you change one.
W = {
    # --- damage ---
    # 0.65 is the single most important number here. Sweeping it: 0.45 wins 66%
    # of heads-up games, 0.65 wins 72%, 0.85 wins 77% - but 0.85 drops 3-player
    # from 61% to 51%, because at a crowded table an over-aggressive monster
    # just paints a target on itself and splits its damage among people who all
    # shoot back. 0.65 keeps nearly all the duel gain for a couple of points of
    # multiplayer, which is the right trade when 64 of the 75 games played in
    # prod were 1v1.
    "dmg_per_point":    0.65,   # a point of damage that does not kill
    "ko_base":          5.0,    # knocking a monster out
    "ko_per_vp":        0.25,   # ...worth more if they were winning
    "ko_solo_bonus":    7.0,    # heads-up, a knockout IS the win
    "nearly_dead":      0.5,    # bonus for leaving a target on <=3 HP
    "tokyo_shake":      0.35,   # chance hitting Tokyo shakes its occupant loose
    "deny_leader":      0.30,   # extra per point against a 15+ VP opponent
    # --- healing ---
    "heal_1hp":         3.0,
    "heal_3hp":         1.8,
    "heal_5hp":         0.9,
    "heal_7hp":         0.5,
    "heal_full":        0.25,
    "shed_token":       0.45,
    # --- energy ---
    "energy_base":      0.58,
    "energy_rich":      0.45,   # at 8+
    "energy_glut":      0.30,   # at 12+
    # --- Tokyo ---
    "tokyo_hold":       3.4,    # per-turn worth of holding Tokyo City
    "tokyo_hurt":       1.1,    # ...when down to 4-5 HP
    "tokyo_dying":      0.2,    # ...when down to 3 or less
    # --- buying ---
    "buy_threshold":    0.6,    # net utility a card must clear to be worth it
}


# ---------------------------------------------------------------------------
# Dice combinatorics (static, so cached across every game in the process)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _reroll_dist(k):
    """Distribution over the outcome of rerolling ``k`` fair dice, as a tuple of
    ``(counts, probability)``. 462 entries at k=6, so it is worth computing once."""
    if k <= 0:
        return ((tuple([0] * NFACES), 1.0),)
    dist = {tuple([0] * NFACES): 1.0}
    for _ in range(k):
        nxt = {}
        for counts, p in dist.items():
            for f in range(NFACES):
                c = list(counts)
                c[f] += 1
                key = tuple(c)
                nxt[key] = nxt.get(key, 0.0) + p / NFACES
        dist = nxt
    return tuple(dist.items())


@lru_cache(maxsize=None)
def _transitions(keep, k):
    """Every ``(resulting counts, probability)`` from holding ``keep`` and
    rolling ``k`` fresh dice.

    Cached globally because it depends only on the dice, never on the game, and
    the whole table is small - about 12k entries for a 6-die tray. Precomputing
    it is what keeps the search off the critical path: the inner loop becomes a
    couple of float multiplies instead of rebuilding a tuple per outcome, which
    matters a great deal when one eventlet worker serves every live game."""
    return tuple((tuple(keep[i] + oc[i] for i in range(NFACES)), p)
                 for oc, p in _reroll_dist(k))


@lru_cache(maxsize=None)
def _candidate_keeps(counts):
    """The keep-subsets worth considering for a roll.

    Keeping a strict subset of identical faces is almost always dominated - if
    one claw is worth holding, so is the second - so the candidates are "keep
    all of face X or none of it" for each face. The one real exception is a
    number you already have three of: the fourth 1 is worth only +1 VP and is
    usually better spent chasing claws, so number faces also get a capped-at-3
    option. That keeps the branching factor near 64 instead of the ~700 a fully
    general subset enumeration would produce."""
    options = []
    for i in range(NFACES):
        c = counts[i]
        opts = {0, c}
        if i <= THREE and c > 3:
            opts.add(3)
        options.append(sorted(opts))
    return tuple(set(itertools.product(*options)))


# ---------------------------------------------------------------------------
# Context: everything the dice scorer needs, computed once per decision
# ---------------------------------------------------------------------------

def _ctx(state, pid):
    m = state["mon"][pid]
    slot = gl._in_tokyo(state, pid)
    alive = [p for p in state["players"] if state["mon"][p]["alive"]]
    others = [p for p in alive if p != pid]

    nova = gl.mod(state, pid, "hits_everyone") > 0
    if nova:
        targets = others
    elif slot:
        targets = [p for p in others if gl._in_tokyo(state, p) is None]
    else:
        targets = [p for p in others if gl._in_tokyo(state, p) is not None]

    tok = m.get("tokens", {}) or {}
    return {
        "pid": pid,
        "vp": m["vp"], "hp": m["hp"], "maxhp": m["maxhp"], "energy": m["energy"],
        "slot": slot, "in_tokyo": slot is not None,
        "tokens": tok.get("poison", 0) + tok.get("shrink", 0),
        "set_vp_bonus": gl.mod(state, pid, "set_vp_bonus"),
        "damage_always": gl.mod(state, pid, "damage_always"),
        "damage_attack": gl.mod(state, pid, "damage_attack"),
        "damage_in_tokyo": gl.mod(state, pid, "damage_in_tokyo"),
        "energy_per_gain": gl.mod(state, pid, "energy_per_gain"),
        "heal_bonus": gl.mod(state, pid, "heal_bonus"),
        # hp of everyone this monster's claws would actually land on
        "target_hp": [state["mon"][p]["hp"] for p in targets],
        "target_vp": [state["mon"][p]["vp"] for p in targets],
        "city_taken": state["tokyo"]["city"] is not None,
        "city_is_mine": state["tokyo"]["city"] == pid,
        "n_others": len(others),
        "opp_max_vp": max([state["mon"][p]["vp"] for p in others], default=0),
        "opp_min_hp": min([state["mon"][p]["hp"] for p in others], default=99),
        "solo": len(others) <= 1,
    }


def _vp_value(ctx):
    """One victory point, in utility. Points get more valuable the closer the
    finish line is - the last few matter far more than the first few."""
    need = max(1, gl.WIN_VP - ctx["vp"])
    return 1.0 + 0.9 * max(0, 10 - need) / 10.0


def _heal_value(ctx):
    """One point of healing, in utility. Cheap at full health, close to
    priceless at 1-2 HP where it is the difference between playing on and being
    knocked out."""
    hp = ctx["hp"]
    if hp <= 1:
        return W["heal_1hp"]
    if hp <= 3:
        return W["heal_3hp"]
    if hp <= 5:
        return W["heal_5hp"]
    if hp <= 7:
        return W["heal_7hp"]
    return W["heal_full"]


def _energy_value(ctx):
    """One energy cube. Worth real tempo early; the pile stops converting into
    anything once it is large enough to buy whatever the shop offers."""
    if ctx["energy"] >= 12:
        return W["energy_glut"]
    if ctx["energy"] >= 8:
        return W["energy_rich"]
    return W["energy_base"]


def _tokyo_entry_value(ctx):
    """Taking Tokyo: +1 VP now, ~2 VP a turn while it holds, minus the fact that
    everyone shoots at you and you cannot heal there. Deeply unattractive on low
    health, which is exactly when players talk themselves into it."""
    hp = ctx["hp"]
    if hp <= 3:
        return W["tokyo_dying"]
    if hp <= 5:
        return W["tokyo_hurt"]
    return W["tokyo_hold"] * _vp_value(ctx)


def _score_dice(ctx, counts):
    """Utility of ending the roll holding this multiset of faces.

    This is the whole strategic model: it converts points, energy, healing and
    damage into one comparable number so the search can trade them off. It
    deliberately mirrors what the engine will actually do with these dice
    (``gl._finish_resolve``), including that hearts do nothing for a monster
    sitting in Tokyo."""
    s = 0.0
    vpv = _vp_value(ctx)

    # Numbers: three of a kind scores that number, +1 for each extra die.
    for face in (ONE, TWO, THREE):
        c = counts[face]
        if c >= 3:
            s += ((face + 1) + (c - 3) + ctx["set_vp_bonus"]) * vpv

    # Energy.
    e = counts[ENERGY]
    if e:
        s += (e + ctx["energy_per_gain"]) * _energy_value(ctx)

    # Hearts: healing outside Tokyo, otherwise only good for shedding counters.
    h = counts[HEART]
    if h:
        if ctx["in_tokyo"]:
            # Heart dice cannot heal a monster in Tokyo; counters are all they buy.
            s += min(h, ctx["tokens"]) * W["shed_token"]
        else:
            room = max(0, ctx["maxhp"] - ctx["hp"])
            # Mirror decide_token_choice, so the value of a heart here matches
            # what the bot will actually do with it: heal first when the next
            # hit would be fatal, otherwise clear counters first.
            if ctx["hp"] <= 3:
                healed = min(h, room)
                shed = min(h - healed, ctx["tokens"])
            else:
                shed = min(h, ctx["tokens"])
                healed = min(h - shed, room)
            if healed:
                healed = min(healed + ctx["heal_bonus"], room)
            s += shed * W["shed_token"] + healed * _heal_value(ctx)

    # Claws.
    dmg = counts[CLAW] + ctx["damage_always"]
    if dmg > 0:
        dmg += ctx["damage_attack"]
        if ctx["in_tokyo"]:
            dmg += ctx["damage_in_tokyo"]
        s += _attack_value(ctx, dmg)

    return s


def _attack_value(ctx, dmg):
    """What ``dmg`` damage is worth right now, summed over everyone it lands on."""
    if dmg <= 0:
        return 0.0
    v = 0.0
    for hp, vp in zip(ctx["target_hp"], ctx["target_vp"]):
        if dmg >= hp:
            # A knockout removes a rival outright and is a win condition of its
            # own - 35 of 68 prod games ended this way, not on points.
            v += W["ko_base"] + W["ko_per_vp"] * vp
            if ctx["solo"]:
                v += W["ko_solo_bonus"]
        else:
            v += W["dmg_per_point"] * dmg
            # Softening someone up matters more the closer they are to dying.
            if hp - dmg <= 3:
                v += W["nearly_dead"]
    # Hitting Tokyo from outside can shake its occupant loose and hand the slot
    # (and its points) over.
    if not ctx["in_tokyo"] and ctx["city_taken"] and ctx["target_hp"]:
        v += W["tokyo_shake"] * _tokyo_entry_value(ctx)
    # Deny a runaway leader.
    if ctx["opp_max_vp"] >= 15:
        v += W["deny_leader"] * dmg
    return v


# ---------------------------------------------------------------------------
# The dice search
# ---------------------------------------------------------------------------

def _score_cached(ctx, counts, memo):
    key = ("s", counts)
    v = memo.get(key)
    if v is None:
        v = memo[key] = _score_dice(ctx, counts)
    return v


def _ev_keep(keep, rerolls, n, ctx, memo):
    """Expected utility of holding ``keep`` and rerolling the rest, with
    ``rerolls`` rolls left. Keeping the whole tray means standing pat, so
    "stop rolling" needs no separate rule - it is just the k=0 case."""
    k = n - sum(keep)
    if k == 0:
        return _score_cached(ctx, keep, memo)
    key = ("e", keep, rerolls)
    hit = memo.get(key)
    if hit is not None:
        return hit
    v = 0.0
    if rerolls <= 1:
        for nc, p in _transitions(keep, k):
            v += p * _score_cached(ctx, nc, memo)
    else:
        for nc, p in _transitions(keep, k):
            v += p * _best_value(nc, rerolls - 1, n, ctx, memo)
    memo[key] = v
    return v


def _best_value(counts, rerolls, n, ctx, memo):
    """Value of a tray played optimally from here.

    Memoizing on the keep rather than on the node is the whole trick: different
    trays reach the same keep constantly, and the expected value of a keep
    depends only on the keep, so the work collapses from millions of tuple
    builds to a few tens of thousands of dictionary hits."""
    key = ("b", counts, rerolls)
    hit = memo.get(key)
    if hit is not None:
        return hit
    if rerolls <= 0:
        v = _score_cached(ctx, counts, memo)
    else:
        v = max(_ev_keep(keep, rerolls, n, ctx, memo)
                for keep in _candidate_keeps(counts))
    memo[key] = v
    return v


def _ranked_keeps(counts, rerolls, ctx, memo):
    """Every candidate keep scored and sorted, best first - so the bot can
    occasionally take the second-best line instead of always the top one."""
    n = sum(counts)
    scored = [(_ev_keep(keep, rerolls, n, ctx, memo), keep)
              for keep in _candidate_keeps(counts)]
    scored.sort(key=lambda t: -t[0])
    return scored


def _counts(dice):
    c = [0] * NFACES
    for d in dice:
        if d in gl.FACES:
            c[gl.FACES.index(d)] += 1
    return tuple(c)


def _keep_indices(dice, keep_counts):
    """Turn a per-face keep count back into the concrete die indices to lock."""
    need = list(keep_counts)
    out = []
    for i, d in enumerate(dice):
        if d not in gl.FACES:
            continue
        f = gl.FACES.index(d)
        if need[f] > 0:
            need[f] -= 1
            out.append(i)
    return out


def decide_roll(state, pid, rng=None):
    """The dice decision. Returns ``("resolve", None)`` to stop and bank the
    dice, or ``("roll", [indices to keep])`` to reroll everything else."""
    rng = rng or random
    dice = state["dice"]
    if state["roll_num"] == 0:
        return "roll", []                      # nothing to keep on the first roll
    if state["rolls_left"] <= 0:
        return "resolve", None

    ctx = _ctx(state, pid)
    counts = _counts(dice)
    memo = {}
    ranked = _ranked_keeps(counts, state["rolls_left"], ctx, memo)
    pick = ranked[0]
    # A little human inconsistency, but never at the cost of a real blunder:
    # only slip to the runner-up when it is within a hair of the best line.
    if len(ranked) > 1 and rng.random() < SLIP_CHANCE:
        alt = ranked[1]
        if alt[0] >= pick[0] - 0.35:
            pick = alt

    keep = pick[1]
    if sum(keep) == sum(counts):
        return "resolve", None
    return "roll", _keep_indices(dice, keep)


# ---------------------------------------------------------------------------
# Yield: stay in Tokyo or bail out
# ---------------------------------------------------------------------------

# Expected claw damage from one monster taking a full three-roll turn and
# keeping claws: 6 dice * (1 - (5/6)^3) ~ 2.5, discounted because not every
# player commits their whole turn to attacking.
_THREAT_PER_OPPONENT = 2.1


def decide_yield(state, pid):
    """Whether to give up Tokyo after taking a hit. Returns True to leave."""
    m = state["mon"][pid]
    hp, vp = m["hp"], m["vp"]
    ctx = _ctx(state, pid)

    attackers = [p for p in state["players"]
                 if p != pid and state["mon"][p]["alive"]
                 and gl._in_tokyo(state, p) is None]
    threat = _THREAT_PER_OPPONENT * max(1, len(attackers))

    # Being knocked out ends the game, and you cannot heal in Tokyo, so a
    # genuinely dangerous position is the one reason to give up the slot.
    if hp <= 2:
        return True
    if hp <= 4 and threat >= hp - 1:
        return True

    # One more turn in Tokyo would carry it over the line: points are only
    # banked at the end of a turn survived, so this is worth some risk.
    if vp + 2 >= gl.WIN_VP and hp > threat * 0.8:
        return False

    # Heads-up, holding Tokyo is much stronger - there is only one monster
    # shooting back, and giving up the slot hands them the points.
    if ctx["solo"]:
        return hp <= 4

    # Expected incoming damage before the next turn comes round would finish us.
    if hp <= threat:
        return True

    # Otherwise hold. Tokyo is where the points are, and the prod games back
    # that up: 57% of winners ended the game sitting in Tokyo City.
    return False


# ---------------------------------------------------------------------------
# Hearts: heal, or shed poison / shrink counters
# ---------------------------------------------------------------------------

def decide_token_choice(state, pid):
    """Split this roll's hearts between shedding counters and healing.
    Returns ``(shed_poison, shed_shrink)``; the rest heals."""
    pc = state.get("pending_token_choice") or {}
    h = pc.get("hearts", 0)
    m = state["mon"][pid]
    tok = m.get("tokens", {}) or {}
    poison, shrink = tok.get("poison", 0), tok.get("shrink", 0)
    room = max(0, m["maxhp"] - m["hp"])

    # On the brink, healing beats everything - counters only matter if you live.
    if m["hp"] <= 3:
        spare = max(0, h - room)
        sp = min(poison, spare)
        return sp, min(shrink, spare - sp)

    # Poison first: it ticks for damage every turn end. Shrink only costs dice.
    sp = min(poison, h)
    ss = min(shrink, h - sp)
    # Never burn hearts on counters that healing needs more.
    while sp + ss > 0 and (h - sp - ss) < min(room, 2) and m["hp"] <= 6:
        if ss > 0:
            ss -= 1
        else:
            sp -= 1
    return sp, ss


# ---------------------------------------------------------------------------
# Buying
# ---------------------------------------------------------------------------

# Ongoing value of a Keep card, in VP-equivalent utility. Deliberately
# conservative: prod's strongest player bought the FEWEST cards, and energy
# spent on a mediocre card is energy not spent staying alive.
_KEEP_VALUE = {
    "extra_head": 9.0,          # a 7th die is the single biggest dice upgrade
    "giant_brain": 7.5,         # an extra reroll every turn
    "nova_breath": 7.0,
    "acid_attack": 6.0,
    "urbavore": 6.0,
    "spiked_tail": 5.5,
    "shrink_ray": 5.0,
    "poison_spit": 5.0,
    "alpha_monster": 4.5,
    "burrowing": 4.5,
    "even_bigger": 4.5,
    "eater_of_the_dead": 4.5,
    "fire_breathing": 4.0,
    "regeneration": 4.0,
    "armor_plating": 4.0,
    "jets": 4.0,
    "wings": 3.5,
    "smoke_cloud": 3.5,
    "gourmet": 3.5,
    "friend_of_children": 3.5,
    "herd_culler": 3.5,
    "energy_hoarder": 3.0,
    "dedicated_news_team": 3.0,
    "alien_metabolism": 3.0,
    "background_dweller": 3.0,
    "telepath": 3.0,
    "rapid_healing": 3.0,
    "camouflage": 3.0,
    "freeze_time": 3.0,
    "complete_destruction": 2.5,
    "made_in_a_lab": 2.5,
    "monster_batteries": 2.5,
    "solar_powered": 2.0,
    "opportunist": 2.5,
    "plot_twist": 2.5,
    "stretchy": 2.5,
    "poison_quills": 2.5,
    "psychic_probe": 2.5,
    "metamorph": 2.0,
    "parasitic_tentacles": 2.0,
    "healing_ray": 2.0,
    "rooting_for_the_underdog": 2.0,
    "herbivore": 1.5,
    "were_only_making_it_stronger": 1.5,
    "it_has_a_child": 3.0,
    "mimic": 4.0,
}

# One-shot Discard cards, as (victory points, self-damage, damage to everyone
# else, self-heal). Scored contextually below rather than with a flat number.
_DISCARD_EFFECT = {
    "corner_store": (1, 0, 0, 0),
    "commuter_train": (2, 0, 0, 0),
    "apartment_building": (3, 0, 0, 0),
    "skyscraper": (4, 0, 0, 0),
    "national_guard": (2, 2, 0, 0),
    "tanks": (4, 3, 0, 0),
    "jet_fighters": (5, 4, 0, 0),
    "high_altitude_bombing": (0, 3, 3, 0),
    "fire_blast": (0, 0, 2, 0),
    "gas_refinery": (2, 0, 3, 0),
    "nuclear_power_plant": (2, 0, 0, 3),
    "heal": (0, 0, 0, 2),
    "vast_storm": (2, 0, 0, 0),
}


def _card_value(state, pid, cid, ctx):
    """Utility of owning (or firing) one card, in the same units as the dice."""
    C = gl._cards().CATALOG.get(cid) or {}
    key = C.get("key")
    vpv = _vp_value(ctx)

    if C.get("type") == "discard":
        if key in _DISCARD_EFFECT:
            vp, self_dmg, all_dmg, self_heal = _DISCARD_EFFECT[key]
            v = vp * vpv
            if self_dmg:
                # Buying a card that kills you is never worth the points.
                if self_dmg >= ctx["hp"]:
                    return -50.0
                v -= self_dmg * _heal_value(ctx)
            if all_dmg:
                v += _attack_value(dict(ctx, target_hp=[state["mon"][p]["hp"]
                                                        for p in state["players"]
                                                        if p != pid and state["mon"][p]["alive"]],
                                        target_vp=[state["mon"][p]["vp"]
                                                   for p in state["players"]
                                                   if p != pid and state["mon"][p]["alive"]],
                                        in_tokyo=ctx["in_tokyo"]), all_dmg)
            if self_heal:
                v += min(self_heal, max(0, ctx["maxhp"] - ctx["hp"])) * _heal_value(ctx)
            return v
        if key == "evacuation_orders":
            return 5.0 * vpv                       # strips 5 VP off everyone else
        if key == "frenzy":
            return 6.0                              # a whole extra turn
        if key == "energize":
            return 9 * _energy_value(ctx)
        if key == "drop_from_high_altitude":
            return 2 * vpv + (0 if ctx["city_is_mine"] else _tokyo_entry_value(ctx))
        return 2.0

    v = _KEEP_VALUE.get(key, 2.5)
    # A Keep card only pays off over the turns still to come, so it is worth
    # much less to someone about to win or about to die.
    if ctx["vp"] >= 17 or ctx["opp_max_vp"] >= 18:
        v *= 0.5
    if ctx["hp"] <= 3:
        v *= 0.6
    if key == "even_bigger" and ctx["hp"] <= 5:
        v += 2.0
    if key in ("armor_plating", "camouflage", "jets", "wings") and ctx["in_tokyo"]:
        v += 1.0
    return v


def decide_buys(state, pid):
    """Plan the buy phase. Returns a list of actions, in order:
    ``("buy", index)`` and at most one ``("sweep", None)``."""
    cards = gl._cards()
    ctx = _ctx(state, pid)
    m = state["mon"][pid]
    energy = m["energy"]
    discount = gl.mod(state, pid, "buy_discount")
    plan = []
    taken = set()

    # Energy is only worth spending on something clearly better than the energy
    # itself; this threshold is what keeps the bot from hoarding trinkets.
    for _ in range(len(state["shop"])):
        best = None
        for i, cid in enumerate(state["shop"]):
            if cid is None or i in taken:
                continue
            C = cards.CATALOG.get(cid)
            if not C:
                continue
            cost = max(0, C["cost"] - discount)
            if cost > energy:
                continue
            v = _card_value(state, pid, cid, ctx)
            net = v - cost * _energy_value(ctx)
            if net > W["buy_threshold"] and (best is None or net > best[0]):
                best = (net, i, cost)
        if best is None:
            break
        plan.append(("buy", best[1]))
        taken.add(best[1])
        energy -= best[2]

    # Sweeping is worth it only with energy to spare and a shop worth clearing.
    if not plan and energy >= gl.SWEEP_COST + 3:
        affordable_any = any(
            cid is not None
            and _card_value(state, pid, cid, ctx) > 1.0
            for cid in state["shop"])
        if not affordable_any:
            plan.append(("sweep", None))
    return plan


# ---------------------------------------------------------------------------
# Off-turn reactions
# ---------------------------------------------------------------------------

def decide_probe(state, pid):
    """Psychic Probe: which of the roller's dice to reroll, or None to pass.

    The bot MUST answer when it is at the head of ``pending_probe``'s queue -
    the engine holds the whole game in ``probe_window`` until every prober has
    decided, so a silent bot would stall the table."""
    roller = state.get("current")
    if not roller or roller == pid:
        return None
    dice = state.get("dice") or []
    counts = _counts(dice)

    # Break up a scoring set, or blunt a big attack aimed at us.
    best_face, best_gain = None, 0.0
    rvp = state["mon"][roller]["vp"]
    for face in (ONE, TWO, THREE):
        if counts[face] >= 3:
            gain = (face + 1) + (counts[face] - 3)
            if rvp >= 14:
                gain += 3
            if gain > best_gain:
                best_face, best_gain = face, gain
    hits_me = (gl._in_tokyo(state, roller) is None) == (gl._in_tokyo(state, pid) is not None)
    if counts[CLAW] >= 3 and hits_me:
        threat = counts[CLAW] * (2.0 if state["mon"][pid]["hp"] <= counts[CLAW] + 2 else 1.0)
        if threat > best_gain:
            best_face, best_gain = CLAW, threat

    if best_face is None or best_gain < 3.0:
        return None
    for i, d in enumerate(dice):
        if d == gl.FACES[best_face]:
            return i
    return None


def decide_opportunist(state, pid):
    """Opportunist: snipe a freshly revealed card, or None. Purely optional -
    nothing blocks on this one."""
    cards = gl._cards()
    ctx = _ctx(state, pid)
    energy = state["mon"][pid]["energy"]
    discount = gl.mod(state, pid, "buy_discount")
    best = None
    for e in (state.get("opportunist_window") or []):
        cid = e.get("cid")
        C = cards.CATALOG.get(cid)
        if not C:
            continue
        cost = max(0, C["cost"] - discount)
        if cost > energy:
            continue
        net = _card_value(state, pid, cid, ctx) - cost * _energy_value(ctx)
        if net > 1.5 and (best is None or net > best[0]):
            best = (net, e.get("index"))
    return best[1] if best else None
