#!/usr/bin/env python
"""Turn a pool track into an editable document. `python tools/to_moves.py spa`

This is not a migration script and it is not test scaffolding: it is how
**"make my own" on one of the nineteen** works. A fork records the folder's
`build(b)` through `tracks.moves.Recorder` and hands the result to the editor,
so the player starts from Spa's real layout and Spa's real palette instead of
from an empty field and a colour wheel.

    python tools/to_moves.py spa                 # human-readable
    python tools/to_moves.py spa --json          # the document itself
    python tools/to_moves.py --all --check       # round-trip every track

Palette keys that need code rather than data are dropped, and the drop is
reported rather than silent: `furniture`, `terrain` and the rest are fine (they
are derived off the ribbon), but `building`, `shore` and `rainbow` are authored
against constants that only exist inside their own track.
"""

import argparse
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tracks import moves                                        # noqa: E402
from tracks.builder import Builder                              # noqa: E402
from tuning import ROAD_W                                       # noqa: E402

# Palette blocks a player's track cannot carry, because each is authored against
# numbers that live in one track's own module. Everything else is data derived
# off the ribbon and survives a fork intact.
NEEDS_CODE = ("building", "shore", "rainbow", "rainbowLanes")

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tracks")


def slugs():
    return sorted(d for d in os.listdir(HERE)
                  if os.path.exists(os.path.join(HERE, d, "track.py")))


def document(slug, *, keep_palette=True):
    """The folder at `slug`, as a document, plus what had to be left behind."""
    mod = importlib.import_module("tracks.%s.track" % slug)
    pal, dropped = None, []
    if keep_palette:
        try:
            pal = dict(importlib.import_module("tracks.%s.palette" % slug).PALETTE)
        except ModuleNotFoundError:
            pal = None
        if pal:
            dropped = [k for k in NEEDS_CODE if k in pal]
            for k in dropped:
                pal.pop(k)
    doc = moves.record(
        mod.build,
        name=getattr(mod, "name", slug),
        difficulty=getattr(mod, "difficulty", 3),
        width=getattr(mod, "width", ROAD_W),
        rails=bool(getattr(mod, "rails", False)),
        ground=getattr(mod, "ground", None),
        closed=bool(getattr(mod, "closed", False)),
        exposed=bool(getattr(mod, "exposed", False)),
        origin=tuple(getattr(mod, "origin", (0.0, 0.0, 0.0, 0.0))),
        pal=pal,
    )
    if getattr(mod, "scenery", False):
        dropped.append("scenery.js")
    return doc, dropped


def authored(slug):
    """The ribbon the folder builds, for comparison."""
    mod = importlib.import_module("tracks.%s.track" % slug)
    o = tuple(getattr(mod, "origin", (0.0, 0.0, 0.0, 0.0)))
    b = Builder(o[0], o[1], o[2], yaw=o[3],
                width=getattr(mod, "width", ROAD_W),
                rails=bool(getattr(mod, "rails", False)))
    return ((mod.build(b) or b)).build()


def describe(m):
    """One move, as the editor's list will read it."""
    t = m["t"]
    if t == "arc":
        deg = m["deg"]
        side = "right" if deg > 0 else "left"
        shape = "hairpin" if abs(deg) >= 140 else side
        s = "%-8s %g° r%g" % (shape, abs(deg), m.get("rad", 0))
    elif t in ("straight", "boost", "bounce"):
        s = "%-8s %g" % (t, m.get("len", 0))
    elif t in ("crest", "hump"):
        s = "%-8s %g over %g" % (t, m.get("rise", 0), m.get("len", 0))
    elif t == "jump":
        s = "jump     gap %g, drop %g" % (m.get("gap", 0), m.get("drop", 0))
    elif t == "gap":
        s = "gap      %g" % m.get("len", 0)
    elif t == "loop":
        s = "loop     r%g %s" % (m.get("rad", 20), m.get("dir", "l"))
    elif t == "cp":
        s = "⛳ checkpoint"
    elif t in ("start", "finish", "finish_at_start"):
        s = {"start": "▶ start", "finish": "⚑ finish",
             "finish_at_start": "⚑ finish (on the start line)"}[t]
    else:
        s = t
    extra = []
    if m.get("rise") and t not in ("crest", "hump", "jump"):
        extra.append("rise %+g" % m["rise"])
    if m.get("bank"):
        extra.append("bank %g°" % m["bank"])
    if m.get("free"):
        extra.append("free: %s" % ",".join(m["free"]))
    return s, extra


def show(slug, doc, dropped):
    print("\n\033[1m%s\033[0m  (%s)  difficulty %d  %d moves"
          % (doc["name"], slug, doc["difficulty"], len(doc["moves"])))
    bits = ["width %g" % doc["width"]]
    if doc["rails"]:
        bits.append("barriers on by default")
    if doc["ground"] is None:
        bits.append("no ground — off the road is a fall")
    if doc["closed"]:
        bits.append("closed lap")
    if doc["exposed"]:
        bits.append("exposed")
    print("  " + " · ".join(bits))
    if dropped:
        print("  \033[33mnot carried into a document: %s\033[0m" % ", ".join(dropped))
    print()
    w = rail = None
    for i, m in enumerate(doc["moves"]):
        if "w" in m and m["w"] != w:
            w = m["w"]
            print("        \033[2m— width %g\033[0m" % w)
        if "rail" in m and m["rail"] != rail:
            rail = m["rail"]
            print("        \033[2m— barriers %s\033[0m"
                  % ({"": "off", "l": "left", "r": "right",
                      "lr": "both sides"}[rail]))
        s, extra = describe(m)
        print("  %3d   %-28s %s" % (i, s, "\033[2m" + "  ".join(extra) + "\033[0m"
                                    if extra else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--all", action="store_true", help="every track in the pool")
    ap.add_argument("--json", action="store_true", help="print the document")
    ap.add_argument("--check", action="store_true",
                    help="replay it and compare against the folder")
    a = ap.parse_args()

    if not a.slug and not a.all:
        ap.error("name a track, or pass --all. Known: %s" % ", ".join(slugs()))
    todo = slugs() if a.all else [a.slug]
    if a.slug and a.slug not in slugs():
        ap.error("no track %r. Known: %s" % (a.slug, ", ".join(slugs())))

    worst = 0
    for slug in todo:
        doc, dropped = document(slug)
        if a.json:
            print(json.dumps(doc, indent=2))
        elif not a.check:
            show(slug, doc, dropped)
        if a.check:
            want, got = authored(slug), moves.build(doc).build()
            same = (want["line"] == got["line"] and want["gates"] == got["gates"]
                    and want["spawn"] == got["spawn"])
            print("%-13s %3d moves  %4d stations  %s%s"
                  % (slug, len(doc["moves"]), len(want["line"]),
                     "identical" if same else "\033[31mDIVERGED\033[0m",
                     "   (drops %s)" % ", ".join(dropped) if dropped else ""))
            worst |= 0 if same else 1
    return worst


if __name__ == "__main__":
    sys.exit(main())
