"""Turning a presence row into the line under somebody's name.

The row itself is written by ``visits.py``, which is copied into all five
services and knows nothing about wording. This is the other half: one place
that decides what "online" reads as, so the profile page, the directory and
anywhere else that grows a dot cannot end up phrasing it three ways.

Two rules shape the wording.

**A status is a sentence about a person, so it is never text they chose.** The
detail is a short phrase the game looked up from its own whitelist - a track
name, "In Lobby", "Multiplayer" - and everything here does to it is escape it
and put a game's name in front. There is no path from a text box to this line.

**Offline is a length of time, not a timestamp.** "Last online 6 minutes ago"
is the thing you actually want to know; a date and time makes you do the
subtraction yourself, and on a profile that nobody has opened for a year the
answer is "a year ago" rather than a day in 2025 you then have to place.
"""

from datetime import datetime

from . import gamestats

# What the line says for each service. The four games are "Playing X"; the main
# site is not a game and saying somebody is playing cgovind.com would be a
# small lie on a page that is otherwise precise.
SITE_LABEL = "Browsing cgovind.com"


def line_for(entry):
    """The words for one presence entry: ``(online, text)``.

    ``entry`` is what ``visits.presence_for`` returns for a user, or None for
    somebody who has never been seen at all - which is not the same as offline
    and is why "Offline" is allowed to stand on its own with no "last online".
    """
    if not entry:
        return False, "Offline"

    if entry.get("online"):
        return True, _doing(entry)

    last = entry.get("last_seen")
    if not last:
        return False, "Offline"
    return False, "Offline - last online %s" % ago(last)


def _doing(entry):
    service = entry.get("service") or ""
    detail = (entry.get("detail") or "").strip()
    game = gamestats.GAME_BY_KEY.get(service)
    if not game:
        return SITE_LABEL
    if detail:
        return "Playing %s - %s" % (game["name"], detail)
    return "Playing %s" % game["name"]


def accent_for(entry):
    """The game's colour, for the dot's glow. None on the main site."""
    game = gamestats.GAME_BY_KEY.get((entry or {}).get("service") or "")
    return game["accent"] if game else None


# ---------------------------------------------------------------------------
# How long ago
# ---------------------------------------------------------------------------
#
# Whole units only, and the largest that fits: a person reading "last online
# 2 months ago" has learned everything "last online 63 days ago" would have
# told them. Months are 30 days and years 365 - this is a rounding of a
# rounding, and a calendar-accurate version would say the same words.

UNITS = (
    ("year", 365 * 24 * 3600),
    ("month", 30 * 24 * 3600),
    ("week", 7 * 24 * 3600),
    ("day", 24 * 3600),
    ("hour", 3600),
    ("minute", 60),
)


def ago(when, now=None):
    seconds = ((now or datetime.utcnow()) - when).total_seconds()
    # A clock that disagrees with itself across five processes can put a
    # timestamp slightly in the future, and "in -3 seconds" is a bug report.
    if seconds < 60:
        return "just now"
    for name, size in UNITS:
        if seconds >= size:
            n = int(seconds // size)
            return "%d %s%s ago" % (n, name, "" if n == 1 else "s")
    return "just now"
