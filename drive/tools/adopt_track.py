"""Promote a community track into the pool: a row becomes a folder.

**Why this exists at all.** A published community track already works - it is
resolved by `tracks.get`, it has a board, ghosts, rooms, share cards and the
anti-cheat. So adoption is not about making it *work*; it is about the handful of
things only a folder gets:

  * it is **in the repository**, so it is reviewed, diffed and deployed like
    everything else, and it survives the database;
  * it can have **hand-cut medal times** - `tools/set_medals.py` cuts those from
    a real board, and a derived set is only ever a guess at what the track asks;
  * it gets a **place in the order**, which is the switcher's difficulty ramp
    rather than "newest first";
  * and it can be *edited by hand* afterwards, which a row cannot be without
    going back through its author.

**How it is kept honest.** Emitting `build(b)` source means writing a second
implementation of what `moves.replay` already does, and a second implementation
is a thing that drifts. So the tool does not trust itself: it writes the folder,
imports it as the pool would, builds the ribbon, and compares
`moves.fingerprint` against the document's. Same road or the folder is deleted
and the tool says so. A drift in the generator is therefore caught on the very
track it would have broken, every time it is run.

    venv/bin/python tools/adopt_track.py foggy-ridge
    venv/bin/python tools/adopt_track.py foggy-ridge --order 145 --dry-run

The row is left alone. Nothing is deleted, and the track keeps working from the
database until the folder is deployed - at which point `tracks.BY_SLUG` wins,
because `tracks.get` checks the pool before it asks the resolver. Take the row
down by hand afterwards if you want the board reset; leave it and the board is
kept, which is almost always what you want.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from tracks import moves as moves_mod                          # noqa: E402


# Fields carried on a move that are not geometry, and are handled separately.
_SKIP = ("t", "free")


def _num(v):
    """A number the way a source file should read it: `40` and not `40.0`."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return repr(v)


def _call(m):
    """One move as the Builder call that makes it.

    Deliberately positional where the Builder's own signature is positional -
    `b.arc(-42, 30)` and not `b.arc(deg=-42, rad=30)` - because the pool's
    thirteen hand-written tracks read that way and an adopted one should be
    indistinguishable from them.
    """
    t = m["t"]
    spec = moves_mod.SPEC[t]
    got = {k: v for k, v in m.items() if k not in _SKIP and k in spec}
    free = set(m.get("free") or ())

    def val(k):
        v = got.get(k, spec[k])
        s = _num(v) if not isinstance(v, str) else repr(v)
        return "FREE(%s)" % s if k in free else s

    if t == "start":
        return "b.start(run=%s)" % val("run")
    if t == "straight":
        args = [val("len")]
        if got.get("rise"):
            args.append("rise=%s" % val("rise"))
        if got.get("ease") is False:
            args.append("ease=False")
        return "b.straight(%s)" % ", ".join(args)
    if t == "arc":
        args = [val("deg"), val("rad")]
        for k in ("rise", "bank"):
            if got.get(k):
                args.append("%s=%s" % (k, val(k)))
        if got.get("ease") is False:
            args.append("ease=False")
        return "b.arc(%s)" % ", ".join(args)
    if t in ("crest", "hump"):
        return "b.%s(%s, %s)" % (t, val("rise"), val("len"))
    if t == "gap":
        args = [val("len")]
        for k in ("drop", "bow"):
            if got.get(k) is not None and got.get(k) != spec[k]:
                args.append("%s=%s" % (k, val(k)))
        return "b.gap(%s)" % ", ".join(args)
    if t == "jump":
        args = [val("rise"), val("gap")]
        for k in ("drop", "kick", "land"):
            if got.get(k) is not None and got.get(k) != spec[k]:
                args.append("%s=%s" % (k, val(k)))
        return "b.jump(%s)" % ", ".join(args)
    if t == "loop":
        args = []
        for k in ("rad", "shift", "dir"):
            if got.get(k) is not None and got.get(k) != spec[k]:
                args.append("%s=%s" % (k, val(k)))
        return "b.loop(%s)" % ", ".join(args)
    if t in ("boost", "bounce"):
        args = []
        if got.get("len") is not None and got["len"] != spec["len"]:
            args.append(val("len"))
        if got.get("rise"):
            args.append("rise=%s" % val("rise"))
        return "b.%s(%s)" % (t, ", ".join(args))
    if t == "pipe":
        args = ["%s=%s" % (k, val(k)) for k in ("depth", "floor", "side")
                if got.get(k) is not None and got.get(k) != spec[k]]
        return "b.pipe(%s)" % ", ".join(args)
    if t == "flat":
        return "b.flat()"
    if t == "cp":
        args = ["%s=%s" % (k, val(k)) for k in ("pre", "post")
                if got.get(k) is not None and got.get(k) != spec[k]]
        return "b.cp(%s)" % ", ".join(args)
    if t == "finish":
        args = ["%s=%s" % (k, val(k)) for k in ("pre", "post")
                if got.get(k) is not None and got.get(k) != spec[k]]
        return "b.finish(%s)" % ", ".join(args)
    if t == "finish_at_start":
        return "b.finish_at_start()"
    raise SystemExit("adopt: no idea how to write a %r move as source" % t)


def build_source(doc):
    """The body of `build(b)`, with the sticky calls put back in.

    The document carries width, barriers and bank on *every* move, because a
    list you can reorder cannot have sticky state. A source file is the opposite:
    `b.width(13.0)` reads perfectly there and repeating it on every line would
    be noise. So this converts back, emitting a sticky call only where the value
    changes - which is exactly what `moves.replay` does at runtime.
    """
    lines = []
    w = rail = bank = None
    for m in doc.get("moves") or ():
        if m["t"] in moves_mod.LAYS_ROAD:
            if m.get("w") is not None and m["w"] != w:
                w = m["w"]
                lines.append("b.width(%s)" % _num(w))
            if m.get("rail") is not None and m["rail"] != rail:
                rail = m["rail"]
                lines.append("b.rail(%s)" % repr(rail))
            if m.get("bank_state") is not None and m["bank_state"] != bank:
                bank = m["bank_state"]
                lines.append("b.bank(%s)" % _num(bank))
        lines.append(_call(m))
    return lines


def write_folder(slug, row_like, order, out_root=None):
    """Write `tracks/<slug>/`. Returns the directory it wrote."""
    doc = row_like["doc"]
    out = os.path.join(out_root or os.path.join(ROOT, "tracks"), slug)
    os.makedirs(out, exist_ok=True)

    free = any(m.get("free") for m in doc.get("moves") or ())
    body = build_source(doc)
    med = row_like.get("medals")

    src = ['"""%s' % row_like["name"], ""]
    src.append("Adopted from a community track by %s."
               % (row_like.get("author") or "somebody"))
    if doc.get("forked_from"):
        src.append("Their own fork of %s." % doc["forked_from"])
    src += ['"""', ""]
    if free:
        # Only imported when it is used: an unused import is a lint failure in a
        # file nobody was going to read again.
        src.append("from ..builder import FREE")
        src.append("")
    src.append("slug = %r" % slug)
    src.append("name = %r" % row_like["name"])
    src.append("difficulty = %d" % row_like["difficulty"])
    if med:
        src.append("# Derived from the ribbon when this was adopted, not cut "
                   "from a board.")
        src.append("# Re-cut with tools/set_medals.py once it has one worth "
                   "cutting from.")
        src.append("medals = (%s)" % ", ".join("%.1f" % v for v in med))
    src.append("ground = %s" % (_num(doc["ground"])
                                if doc.get("ground") is not None else "None"))
    if doc.get("closed"):
        src.append("closed = True")
    if doc.get("exposed"):
        src.append("exposed = True")
    src.append("order = %d" % order)
    src.append("width = %s" % _num(doc.get("width", 9.0)))
    if doc.get("scenery"):
        src.append("")
        src.append("# Placements, drawn by `placeAll` in trackmesh - the same "
                   "interpreter")
        src.append("# a community track goes through, so nothing here had to be "
                   "rewritten.")
        src.append("placed = " + json.dumps(doc["scenery"], indent=4))
    src.append("")
    src.append("")
    src.append("def build(b):")
    src.append('    """%s"""' % (row_like["name"]))
    for line in body:
        src.append("    " + line)
    src.append("")

    with open(os.path.join(out, "track.py"), "w") as f:
        f.write("\n".join(src))

    pal = doc.get("pal") or {}
    with open(os.path.join(out, "palette.py"), "w") as f:
        f.write('"""What %s looks like."""\n\nPALETTE = %s\n'
                % (row_like["name"], _fmt_palette(pal)))

    with open(os.path.join(out, "__init__.py"), "w") as f:
        f.write("")
    return out


def _fmt_palette(pal):
    """A palette as source, with the colours as hex.

    `0x4d5464` and not `5199204`: `tracks/look.py` is explicit that these are
    packed RGB written as hex, and a decimal integer in a palette file is a
    colour nobody can read or adjust.
    """
    def fmt(v, indent=4):
        pad = " " * indent
        if isinstance(v, bool):
            return repr(v)
        if isinstance(v, int):
            return "0x%06x" % v if 0 <= v <= 0xFFFFFF else repr(v)
        if isinstance(v, float):
            return _num(v)
        if isinstance(v, str):
            return repr(v)
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x, indent) for x in v) + "]"
        if isinstance(v, dict):
            inner = ",\n".join("%s%r: %s" % (pad + "    ", k,
                                             fmt(x, indent + 4))
                               for k, x in v.items())
            return "{\n%s,\n%s}" % (inner, pad)
        return repr(v)
    return fmt(pal)


def _row_like(slug):
    """Read the row, as plain data, so the rest of this file needs no database."""
    os.environ.setdefault("DRIVE_VERIFY", "0")
    import app
    import tracks as tracks_mod
    from models import DriveUserTrack
    with app.app.app_context():
        row = DriveUserTrack.query.filter_by(slug=slug).first()
        if row is None:
            raise SystemExit("adopt: there is no track called %r." % slug)
        if row.status != "live":
            raise SystemExit("adopt: %r is %s, not live. Approve it first - "
                             "adopting an unreviewed track puts it in the "
                             "repository without anybody having driven it."
                             % (slug, row.status))
        t = tracks_mod.from_document(slug, row.doc, timed=True)
        med = t.get("medals") or {}
        return {
            "doc": row.doc, "name": row.name,
            "difficulty": row.difficulty,
            "author": row.author.username if row.author else None,
            "medals": (med.get("gold"), med.get("silver"), med.get("bronze"))
                      if med else None,
            "want_hash": moves_mod.fingerprint(t, row.doc.get("scenery")),
        }


def verify(slug, want_hash, out_root=None):
    """Import the folder as the pool does, and check it is the same road.

    This is the load-bearing part of the tool. Generating `build(b)` source is a
    second implementation of `moves.replay`, and the way to keep a second
    implementation honest is not care - it is comparing them on the real input
    every time.
    """
    import importlib
    from tracks import solver as solver_mod
    from tracks.builder import Builder
    importlib.invalidate_caches()
    mod = importlib.import_module("tracks.%s.track" % slug)
    importlib.reload(mod)

    # Built exactly as `tracks._one` builds a pool folder: the Builder takes its
    # width and barriers, and a closed lap is re-solved. `ground` is not a
    # Builder argument at all - it is a plate height on the track dict - so it
    # cannot affect the ribbon and does not belong here.
    def fresh():
        return Builder(width=getattr(mod, "width", 9.0),
                       rails=bool(getattr(mod, "rails", False)))
    b = fresh()
    mod.build(b)
    if getattr(mod, "closed", False):
        built, _closure = solver_mod.close(b, fresh())
    else:
        built = b.build()
    got = moves_mod.fingerprint(built, getattr(mod, "placed", None))
    return got, want_hash


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if len(args) != 1:
        print(__doc__.strip().split("\n\n")[0])
        print("\nusage: adopt_track.py <slug> [--order N] [--dry-run]")
        return 1
    slug = args[0]
    order = None
    if "--order" in argv:
        order = int(argv[argv.index("--order") + 1])
    dry = "--dry-run" in argv

    row = _row_like(slug)
    import tracks as tracks_mod
    if slug in tracks_mod.BY_SLUG:
        raise SystemExit("adopt: the pool already has a %r." % slug)
    if order is None:
        order = max(t.get("order", 0) for t in tracks_mod.TRACKS) + 5

    lines = build_source(row["doc"])
    if dry:
        print("would write tracks/%s/{track.py,palette.py,__init__.py}" % slug)
        print("  %d moves -> %d Builder calls, order %d"
              % (len(row["doc"].get("moves") or ()), len(lines), order))
        for ln in lines:
            print("    " + ln)
        return 0

    out = write_folder(slug, row, order)
    got, want = verify(slug, row["want_hash"])
    if got != want:
        shutil.rmtree(out)
        print("adopt: the folder built a DIFFERENT road from the row, so it has\n"
              "been deleted rather than committed. This is a bug in this tool's\n"
              "source generator, not in the track.\n"
              "  row:    %s\n  folder: %s" % (want, got))
        return 1
    print("wrote %s" % os.path.relpath(out, ROOT))
    print("  %d moves, order %d, verified identical to the row"
          % (len(row["doc"].get("moves") or ()), order))
    print("\nNext: run the suite, shoot its picture, and commit the folder.")
    print("  scripts/tests.sh drive")
    print("  venv/bin/python tools/shoot_tracks.py %s" % slug)
    print("\nThe row is untouched, so the track keeps working until this ships."
          "\nThe pool wins once it does: `tracks.get` checks BY_SLUG before it "
          "asks\nthe resolver.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
