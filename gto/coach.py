"""The coach: one decision, handed to a model, worked out from scratch.

**This module is given none of the trainer's analysis, on purpose.**
``review.py`` produces equity, pot odds, a range read and a verdict for every
decision, and ``validate.py`` checks that equity against an independent
enumeration to the last place a float has. None of it goes in the prompt. What
is sent is the *situation only*: the cards, the seats, the blinds, the bounty
rules, every action so far with its size, and how the five of them play. Claude
does its own arithmetic from there.

That is a deliberate trade and it cuts both ways.

- It buys a **second opinion** rather than a paraphrase. Where the panel and the
  review agree, that is two independent readings of the same spot. Where they
  disagree, one of them is wrong, and knowing which spots those are is worth
  more than either answer alone.
- It costs **verification**. Every number ``review.py`` prints carries a label
  saying where it came from, and the whole trainer turns on nothing ever being
  labelled better than it is. Nothing here can carry one of those labels. An
  equity a model worked out in its head is a sixth thing - unchecked - and the
  panel says so in as many words rather than letting it sit next to `solver` and
  look like a peer. **This matters more on the free tier than it would on a
  frontier model**: Gemini 2.5 Pro is good and it is still doing the arithmetic
  in its head, so the disagreements are what to read, not the numbers.

**Two providers, and the key decides which.** ``ANTHROPIC_API_KEY`` wins if it
is set; otherwise ``GEMINI_API_KEY``, which is the free tier and what this
actually runs on. Only ``ask`` knows the difference - everything above it builds
one prompt and everything below reads back one ``(text, usage)`` - so moving
between them is an env var and not a rewrite. ``GTO_COACH_PROVIDER`` forces one.

The Gemini call is plain ``urllib``, deliberately. It is one POST of JSON, this
repo has no build step, and the previous Gemini caller here was written the same
way; a dependency for that would be the largest thing in the install.

**Chinmay only, and off until a key exists.** The endpoint is gated on
``is_owner`` and 404s for everybody else, the same reasoning as
``/avatars/<key>``. With no key at all the feature reports itself unconfigured
rather than half-working. This is the one route in the repo that spends on an
outside account, so it is worth listing what stands in front of it: an account
check, a per-answer cache, two daily ceilings, and a thread so a slow call
cannot hold a worker.

**Every call is metered, in the unit that provider bills in.** A paid one is
counted in **micro-dollars** rather than the integer cents money uses elsewhere
here, because an answer costs a few hundredths of a dollar and cents would round
a quiet day to zero. The free tier bills in neither - what is scarce there is
*requests per day* - so the meter counts calls and tokens too, and the panel
shows whichever of the two is the real limit.
"""

import os
import time

import cards

#: Dollars per million tokens, input and output. Only the models this is
#: plausibly pointed at; an unknown one is priced as the dearest so that a wrong
#: guess over-reports the bill rather than under-reporting it.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

ANTHROPIC, GEMINI = "anthropic", "gemini"

DEFAULT_MODELS = {
    ANTHROPIC: "claude-opus-5",
    #: **Flash, not Pro** - the free tier has no Pro quota at all. Every Pro
    #: model, and the `gemini-pro-latest` alias, answers a free-tier key with a
    #: 429 before it ever reads the prompt.
    #:
    #: Pinned rather than `gemini-flash-latest`, which is the obvious choice and
    #: is the wrong one here: the aliases point at whatever is newest, which is
    #: whatever is busiest, and both it and `gemini-3.7-flash` answer 503 "high
    #: demand" while this one answers. A pin that goes stale fails *loudly* -
    #: Google's 404 names its own replacement - which is the better failure.
    GEMINI: "gemini-3.5-flash",
}

DEFAULT_MODEL = DEFAULT_MODELS[ANTHROPIC]


def provider():
    """Whichever key exists, with Anthropic winning if both do.

    Forced by ``GTO_COACH_PROVIDER`` when there are two keys on the box and the
    cheaper one is wanted anyway.
    """
    forced = os.environ.get("GTO_COACH_PROVIDER", "").strip().lower()
    if forced in (ANTHROPIC, GEMINI):
        return forced
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return ANTHROPIC
    if os.environ.get("GEMINI_API_KEY"):
        return GEMINI
    return None


def model():
    """The model, which follows the provider unless one is named."""
    named = os.environ.get("GTO_COACH_MODEL")
    if named:
        return named
    return DEFAULT_MODELS.get(provider() or ANTHROPIC, DEFAULT_MODEL)


def is_free(model_id=None):
    """Whether this model is metered in requests rather than in money.

    A prefix rather than a list of names, and that is the lesson rather than the
    shortcut: the model catalogue is exactly the wrong thing to keep a copy of.
    The name this was first written against was retired before it ever shipped,
    and a stale entry here would quietly price a Gemini answer at Opus rates.

    It assumes an AI Studio free-tier key, which is what this runs on. A key on
    a billed Google Cloud project costs real money per token and would be
    reported here as free - if that ever happens this needs the rates, not just
    a narrower prefix.
    """
    return (model_id or model()).startswith("gemini-")


def effort():
    """How hard it thinks. **Anthropic only** - Gemini has no equivalent.

    Thinking tokens are billed as output, so on a paid provider effort - not
    ``max_tokens`` - is what a typical answer costs. ``medium`` is the default
    because the numbers here are unverified and the arithmetic is the whole
    point; ``low`` is roughly half the spend. It is recorded on the row either
    way, so a stored answer says how it was produced, and it reads ``-`` on the
    free tier rather than a setting that did nothing.
    """
    if provider() == GEMINI:
        return "-"
    return os.environ.get("GTO_COACH_EFFORT", "medium")


def max_tokens():
    """A ceiling, not a target. Thinking counts against it, so it is not tight.

    Too low and the answer is truncated mid-sentence, which reads as a broken
    feature rather than as a budget. The word limit in the system prompt is what
    keeps the visible answer short; this only stops a runaway.

    **It is far higher on Gemini, and that is not generosity.** 2.5 Pro always
    thinks and cannot be told not to, and its thinking is billed against
    ``maxOutputTokens`` - so a ceiling sized for the visible answer is spent
    entirely on thinking and the response comes back with `MAX_TOKENS` and an
    empty text part. An empty answer is the failure this number exists to
    prevent, and on the free tier there is nothing to save by risking it.
    """
    named = os.environ.get("GTO_COACH_MAX_TOKENS")
    if named:
        return int(named)
    return 8000 if provider() == GEMINI else 3000


def daily_cap_micros():
    return int(float(os.environ.get("GTO_COACH_DAILY_USD", "1.00")) * 1_000_000)


def daily_cap_calls():
    """The ceiling that actually binds on a free tier.

    Money is not the scarce thing there - requests per day are - so a dollar cap
    of any size would never trip and the feature would have no ceiling at all.
    This one applies to both providers, because a loop that asks the same
    question two hundred times is a bug worth stopping either way.
    """
    return int(os.environ.get("GTO_COACH_DAILY_CALLS", 100))


def enabled():
    """Whether there is anything to call with.

    The box sets its key in ``gto/.env`` by hand - the deploy does not touch
    that file. Checking for one rather than trying a call means an unconfigured
    install says so once, instead of failing on every click.
    """
    return provider() is not None


# ------------------------------------------------------------ the situation


def money(cents):
    return "$%.2f" % (cents / 100.0)


def context(t, d):
    """Everything about the spot, and nothing this repo concluded about it.

    Reads only the engine's own record - the snapshot ``table._record_decision``
    took at the moment the hero was put on the clock - plus the profiles, which
    are the opponents' defining parameters rather than anything computed. It
    must stay that way: the moment a number out of ``equity.py``, ``rollout.py``
    or ``review.py`` appears in here, the answer stops being independent and the
    disagreement that makes this worth having disappears.
    """
    seats = list(getattr(d, "seats_at", []) or [])
    hero = next((s for s in seats if s["name"] == t.hero), None)
    return {
        "seats": getattr(d, "seats", len(seats)) or len(seats),
        "sb": t.sb,
        "bb": t.bb,
        "buyin": t.buyin,
        "bounty_on": t.bounty_on,
        "streak": getattr(d, "streak", 0) or 0,
        "street": d.street,
        "position": d.position,
        "in_position": bool(getattr(d, "in_position", False)),
        "hole": cards.cards_str(d.hole),
        "board": cards.cards_str(d.board),
        "pot": d.pot,
        "to_call": d.to_call,
        "stack": d.stack,
        "legal": list(getattr(d, "legal", []) or []),
        "hero": t.hero,
        "hero_stack": (hero or {}).get("stack", d.stack),
        "players": _players(t, d, seats),
        "actions": list(getattr(d, "actions_before", []) or []),
        "action": getattr(d, "action", None),
        "amount": getattr(d, "amount", 0) or 0,
    }


def _players(t, d, seats):
    """The other seats, with the tendencies that define how each one plays.

    The tendencies are sent because without them the read is against five
    strangers, which is advice about poker rather than about this game. They are
    profile fields - what the bot *is* - not a range this code inferred.
    """
    out = []
    for s in seats:
        if s["name"] == t.hero:
            continue
        bot = t.bots.get(s["name"])
        p = bot.profile if bot else None
        out.append({
            "name": s["name"],
            "position": s.get("position"),
            "stack": s.get("stack", 0),
            "in_hand": bool(s.get("in_hand")),
            "style": None if not p else {
                "vpip": p.vpip, "pfr": p.pfr, "three_bet": p.three_bet,
                "fold_to_three_bet": p.fold_to_three_bet,
                "cbet": p.cbet, "fold_to_cbet": p.fold_to_cbet,
                "wtsd": p.wtsd, "aggression": p.aggression, "bluff": p.bluff,
                "blurb": p.blurb,
            },
        })
    return out


# ---------------------------------------------------------------- the prompt


SYSTEM = """You are a poker coach sitting behind one player in a small home \
game, explaining the spot they just played.

You are given the situation only - cards, seats, stacks, the betting, and how \
each opponent plays. You are deliberately NOT given any analysis: no equity, no \
pot odds, no ranges, no verdict. Work all of it out yourself.

Rules:
- Do your own arithmetic and show it inline, briefly: "you need 1.5/6.9 = 22% \
and you have about 34%".
- Count combinations when it matters. Say the count.
- Distinguish what you calculated from what you estimated. Write "about" or \
"roughly" in front of any number you did not actually compute, and never state \
an equity to more than the nearest whole percent.
- If the spot cannot be settled without solving a subgame, say that plainly \
instead of inventing a number.
- Judge the action against THESE opponents' tendencies, not against a chart. \
A play a solver folds can be right against someone playing 58% of hands - say \
so when it is.

Watch for two things this game does that most do not:
- The blinds may be EQUAL. When they are, the small blind has already matched \
the big blind, so folding it is strictly worse than checking, and an open faces \
more dead money than the usual charts assume.
- There may be a BOUNTY on winning hands in a row. When one is live, the value \
of taking the pot is well above the chips in it, and folding breaks a streak \
exactly as surely as losing does. Price it in rather than mentioning it.

Format: one sentence on whether the action was right, then at most four lines \
each starting with "- ". Under 160 words. Plain text - no headings, no bold, no \
markdown."""


def prompt(ctx):
    """The situation as prose, kept short because every line of it is billed."""
    bb = ctx["bb"] or 1
    lines = []

    blinds = "%s/%s" % (money(ctx["sb"]), money(ctx["bb"]))
    equal = " (equal blinds)" if ctx["sb"] == ctx["bb"] else ""
    lines.append("%d-handed cash game, blinds %s%s, big blind %s."
                 % (ctx["seats"], blinds, equal, money(bb)))

    if ctx["bounty_on"]:
        lines.append(
            "Bounty is on: winning 3 hands in a row pays $1 from every other "
            "player, 4 in a row pays $2, 5 or more pays $3. You are currently "
            "on a streak of %d." % ctx["streak"])

    lines.append("")
    lines.append("Seats, in the order they act preflop:")
    seats = [{"position": ctx["position"], "name": ctx["hero"],
              "stack": ctx["hero_stack"], "in_hand": True, "style": None,
              "hero": True}] + list(ctx["players"])
    for p in sorted(seats, key=lambda s: _seat_order(s["position"])):
        style = p.get("style")
        tail = ""
        if style:
            tail = ("  %.0f/%.0f, 3bet %.0f%%, c-bets %.0f%%, folds to c-bet "
                    "%.0f%%, aggression %.1f - %s"
                    % (style["vpip"], style["pfr"], style["three_bet"],
                       style["cbet"], style["fold_to_cbet"],
                       style["aggression"], style["blurb"]))
        out = "  %-4s %-10s %s%s" % (p["position"] or "?", p["name"],
                                     money(p["stack"]), tail)
        if p.get("hero"):
            out += "  <- you"
        elif not p["in_hand"]:
            out += "  [folded]"
        lines.append(out)

    lines.append("")
    for street, text in _betting(ctx):
        lines.append("%s: %s" % (street, text))

    lines.append("")
    lines.append("You hold %s%s."
                 % (ctx["hole"], " on %s" % ctx["board"] if ctx["board"] else ""))
    lines.append("Pot is %s. It is %s to you."
                 % (money(ctx["pot"]),
                    money(ctx["to_call"]) if ctx["to_call"] else "checked"))
    lines.append("You have %s behind and you are %s."
                 % (money(ctx["stack"]),
                    "last to act" if ctx["in_position"] else "out of position"))
    lines.append("You may %s." % _legal(ctx))

    took = ctx["action"]
    if took:
        did = _took(took, ctx["amount"])
        lines.append("")
        lines.append("You %s. Was that right, and why?" % did)
    else:
        lines.append("")
        lines.append("What should you do here, and why?")

    return "\n".join(lines)


#: Preflop acting order, which is how a player reads a table and is not the
#: order the engine happens to hold the seats in.
_SEAT_ORDER = ("UTG", "UTG1", "UTG2", "MP", "HJ", "CO", "BTN", "SB", "BB")


def _seat_order(position):
    try:
        return _SEAT_ORDER.index(position)
    except ValueError:
        return len(_SEAT_ORDER)


def _took(action, amount):
    """What the hero did. Only a bet or a raise is described with a total."""
    if action in ("fold", "check") or not amount:
        return action
    if action == "call":
        return "call %s" % money(amount)
    return "%s to %s" % (action, money(amount))


def _betting(ctx):
    """The action so far, one line per street, in the order it happened."""
    out, current, buf = [], None, []
    board = (ctx["board"] or "").split()
    seen = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
    for a in ctx["actions"]:
        if a.get("street") != current:
            if buf:
                out.append((_street_label(current, board, seen), ", ".join(buf)))
            current, buf = a.get("street"), []
        buf.append(_one_action(a))
    if buf:
        out.append((_street_label(current, board, seen), ", ".join(buf)))
    if not out:
        out.append((_street_label(ctx["street"], board, seen), "checked to you"))
    return out


def _street_label(street, board, seen):
    n = seen.get(street, 0)
    if not n or len(board) < n:
        return (street or "preflop").capitalize()
    return "%s (%s)" % (street.capitalize(), " ".join(board[:n]))


def _one_action(a):
    name, kind = a.get("name", "?"), a.get("action", "?")
    if kind in ("fold", "check"):
        return "%s %ss" % (name, kind)
    if kind == "call":
        return "%s calls %s" % (name, money(a.get("to") or a.get("amount") or 0))
    if kind == "post":
        return "%s posts %s" % (name, money(a.get("amount") or 0))
    return "%s %ss to %s" % (name, kind, money(a.get("to") or a.get("amount") or 0))


def _legal(ctx):
    bits = []
    for a in ctx["legal"]:
        kind = a.get("action")
        if kind in ("fold", "check"):
            bits.append(kind)
        elif kind == "call":
            bits.append("call %s" % money(a.get("amount", 0)))
        else:
            bits.append("%s to between %s and %s"
                        % (kind, money(a.get("min", 0)), money(a.get("max", 0))))
    return ", ".join(bits) if bits else "act"


# ------------------------------------------------------------------ the call


class CoachError(Exception):
    """Anything that stopped an answer coming back, phrased for the panel."""


def ask(ctx):
    """One question, one answer, and what it cost.

    Returns ``(text, usage, ms)``. ``usage`` is plain integers rather than
    anything belonging to a response object, because the caller runs on a thread
    and writes it to the database - and because the two providers agree on
    nothing else.
    """
    which = provider()
    if which is None:
        raise CoachError("there is no API key on this box")
    started = time.time()
    text, usage = (_ask_gemini(ctx) if which == GEMINI else _ask_anthropic(ctx))
    return text, usage, int((time.time() - started) * 1000)


# ------------------------------------------------------------------ anthropic


def _ask_anthropic(ctx):
    try:
        import anthropic
    except ImportError:                                     # pragma: no cover
        raise CoachError("the anthropic package is not installed on this box")

    client = anthropic.Anthropic(
        timeout=float(os.environ.get("GTO_COACH_TIMEOUT", "120")),
        max_retries=1)
    try:
        r = client.messages.create(
            model=model(),
            max_tokens=max_tokens(),
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": effort()},
            messages=[{"role": "user", "content": prompt(ctx)}],
        )
    except anthropic.APIStatusError as e:                    # pragma: no cover
        raise CoachError("the API said %s: %s" % (e.status_code, e.message))
    except anthropic.APIConnectionError:                     # pragma: no cover
        raise CoachError("could not reach the API")

    usage = {
        "input_tokens": getattr(r.usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(r.usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(r.usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_tokens":
            getattr(r.usage, "cache_creation_input_tokens", 0) or 0,
    }
    if r.stop_reason == "refusal":
        raise CoachError("the model declined to answer this one")

    text = "\n".join(b.text for b in r.content if b.type == "text").strip()
    if not text:
        raise CoachError("the answer came back empty")
    if r.stop_reason == "max_tokens":
        text += "\n\n- (cut off at the token ceiling - raise GTO_COACH_MAX_TOKENS)"
    return text, usage


# --------------------------------------------------------------------- gemini


GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "%s:generateContent")


def _gemini_body(ctx):
    """The request, as a dict, so the shape of it can be tested without a key.

    ``temperature`` is low because this is arithmetic and a read, not writing.
    No ``thinkingConfig``: 2.5 Pro always thinks and the budget cannot be turned
    off, so setting one is either a no-op or a way to get an empty answer.
    """
    return {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt(ctx)}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens(),
            "temperature": 0.3,
        },
    }


def _ask_gemini(ctx):
    """One POST of JSON, over ``urllib``. See the module docstring."""
    import json
    from urllib import error as urlerror
    from urllib import request as urlrequest

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise CoachError("there is no GEMINI_API_KEY on this box")

    req = urlrequest.Request(
        GEMINI_URL % model(),
        data=json.dumps(_gemini_body(ctx)).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST")
    try:
        with urlrequest.urlopen(
                req, timeout=float(os.environ.get("GTO_COACH_TIMEOUT", "120"))
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:                          # pragma: no cover
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8"))["error"]["message"]
        except Exception:
            pass
        if e.code == 429:
            raise CoachError("Gemini's free tier is out of quota for this model "
                             "- wait a minute, or point GTO_COACH_MODEL at a "
                             "smaller one")
        if e.code == 503:
            # The busiest models are the newest ones, and this is how they say
            # so. Transient, and asking again is the whole fix.
            raise CoachError("that model is busy - ask again, or point "
                             "GTO_COACH_MODEL at a less popular one")
        if e.code == 404:
            # Passed straight through: when a model is retired Google's own
            # message names the one to move to.
            raise CoachError("Gemini said 404: %s" % (detail or "unknown model"))
        raise CoachError("Gemini said %s%s" % (e.code, ": " + detail if detail else ""))
    except urlerror.URLError:                                # pragma: no cover
        raise CoachError("could not reach Gemini")
    except ValueError:                                       # pragma: no cover
        raise CoachError("Gemini sent something that was not JSON")

    return _gemini_read(payload)


def _gemini_read(payload):
    """Pull the answer and the token counts out of a response.

    The awkward case is the one worth naming: **2.5 Pro can return a candidate
    with no text at all.** It thinks before it writes, its thinking is billed
    against ``maxOutputTokens``, and if the ceiling runs out first the candidate
    comes back ``MAX_TOKENS`` with an empty ``parts`` - a 200, with usage, and
    nothing to show. That is the failure this reads for explicitly, because
    letting it through prints an empty panel and looks like the button is
    broken.
    """
    usage_raw = payload.get("usageMetadata") or {}
    usage = {
        "input_tokens": usage_raw.get("promptTokenCount", 0) or 0,
        # Thinking is billed and is not in `candidatesTokenCount`, so leaving it
        # out would under-report every answer by most of what it actually used.
        "output_tokens": ((usage_raw.get("candidatesTokenCount", 0) or 0)
                          + (usage_raw.get("thoughtsTokenCount", 0) or 0)),
        "cache_read_tokens": usage_raw.get("cachedContentTokenCount", 0) or 0,
        "cache_creation_tokens": 0,
    }

    candidates = payload.get("candidates") or []
    if not candidates:
        blocked = ((payload.get("promptFeedback") or {}).get("blockReason"))
        raise CoachError("Gemini returned nothing%s"
                         % (" (%s)" % blocked if blocked else ""))

    top = candidates[0]
    finish = top.get("finishReason")
    parts = ((top.get("content") or {}).get("parts")) or []
    text = "\n".join(p["text"] for p in parts if p.get("text")).strip()

    if not text:
        if finish == "MAX_TOKENS":
            raise CoachError(
                "it spent the whole token ceiling thinking and wrote nothing - "
                "raise GTO_COACH_MAX_TOKENS")
        raise CoachError("the answer came back empty%s"
                         % (" (%s)" % finish if finish else ""))
    if finish == "MAX_TOKENS":
        text += "\n\n- (cut off at the token ceiling - raise GTO_COACH_MAX_TOKENS)"
    return text, usage


def cost_micros(usage, model_id=None):
    """What one answer cost, in millionths of a dollar.

    Cached reads bill at a tenth of the input rate and cache writes at one and a
    quarter, which is why they are counted separately rather than folded into
    the input count. A free-tier model prices to zero and the panel counts
    *calls* for it instead - see ``daily_cap_calls``. Nothing here sets a cache
    breakpoint today - the system
    prompt is well under the shortest prefix any model will cache, so a
    breakpoint on it would report zero reads forever - but the response carries
    the fields and a future prompt may be long enough to earn them.
    """
    model_id = model_id or model()
    if is_free(model_id):
        return 0
    rate_in, rate_out = PRICES.get(model_id, PRICES[DEFAULT_MODEL])
    dollars = (
        usage.get("input_tokens", 0) * rate_in
        + usage.get("output_tokens", 0) * rate_out
        + usage.get("cache_read_tokens", 0) * rate_in * 0.1
        + usage.get("cache_creation_tokens", 0) * rate_in * 1.25
    ) / 1_000_000.0
    return int(round(dollars * 1_000_000))
