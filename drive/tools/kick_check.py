"""Where does the road throw the car? Drive a bot lap and list every unplanned hop.

    venv/bin/python tools/kick_check.py sahara
    venv/bin/python tools/kick_check.py sahara --level hard --min 3
    venv/bin/python tools/kick_check.py sahara --sweep    # the whole road, not one line

`test_hills_are_eased_but_kickers_are_not` checks every crest against a car doing
40 u/s, and a car on a straight does 50 - 65 off a pad - so a crest the test
passes can still put a driver in the air, which is what Sahara's first ramps
did. Nothing in a still render shows it either. This drives the real `Car.step`
round the lap (`botLap` in QuickJS, the same runtime the bots race in) and
reports every stretch where the wheels left the road somewhere the ribbon has no
gap: a **KICK**. The track's own jumps are listed too, as **JUMP**, so you can
see the tool is looking.

**`--sweep` drives the whole lap again at offsets across the road** - the bot's
line moved to 0, +-0.25, +-0.55, +-0.85 and +-0.95 of the half-width everywhere.
A bot keeps to one line and a person does not: on Sahara the line was clean
while a driver off-centre was being thrown up the ramps by a support pier's top
and off the right kerb by a berm the ground query could not see. Contact with a
solid gate post at +-0.95 shows as a short slow blip and is not a kick.

A kick wants fixing at its cause, which is nearly always a crest too sharp for
the speed: an eased rise of `rise` over `length` crests at a radius of
`length^2 / (6 * rise)`, and the car stays down while `v^2 / radius` is under
gravity (30) - about 85 flat out and 140 on a pad. Lengthen the hill, lower it,
or take the pad away from in front of it. A gate splitting a climb in two makes
two short hills out of one long one.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts, it = {}, iter(argv[1:])
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it, "")
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("\nusage: kick_check.py <slug> [--level max] [--min 3] [--sweep]")
        return 1
    slug, level = args[0], opts.get("level") or "max"
    sweep = "sweep" in opts or "--sweep" in argv
    least = int(opts.get("min") or 3)

    import botsim
    import bots
    import tracks
    track = tracks.get(slug)
    if not track:
        print("no such track: %s" % slug)
        return 1
    rt = botsim.runtime()
    botsim.build(rt, slug)
    line, _ = bots.line_for(slug, level)
    prof = bots.profile(slug, level, seed=1)
    # One frame in 60, so the trace's 6000-frame cap covers 100 seconds of lap.
    rt.ctx.set_time_limit(400)
    L, n = track["line"], len(track["line"])
    offsets = [0.0, -0.25, 0.25, -0.55, 0.55, -0.85, 0.85, -0.95, 0.95] if sweep else [None]
    total = 0
    for off in offsets:
        ln = line
        if off is not None:
            ln = dict(line, p=[
                ([e["p"][0] + e["lat"][0] * off * e["hw"], e["p"][1] + e["lat"][1] * off * e["hw"],
                  e["p"][2] + e["lat"][2] * off * e["hw"]] if not e.get("air") else line["p"][i])
                for i, e in enumerate(L)])
            print("-- offset %+.2f of the half-width" % off)
        total += _one(rt, slug, level, ln, prof, L, n, least)
    print("%d kick(s)%s" % (total, " across the sweep" if sweep else ""))
    return 1 if total else 0


def _one(rt, slug, level, line, prof, L, n, least):
    out = rt.call("botLap(TRACKS.find(t => t.slug === %s), T, %s, %s, %s)" % (
        json.dumps(slug), json.dumps(line), json.dumps(prof),
        json.dumps({"fps": 60, "maxT": 300, "trace": True})))
    print("%s, %s bot: %s in %.2fs, %d respawn(s)" % (
        slug, level, "finished" if out["finished"] else "DID NOT FINISH",
        out["time"] / 1000.0, out["respawns"]))
    for f in out["fell"]:
        print("  fell at station %d (%.3f): %s" % (f["i"], f["i"] / float(n), f["why"]))

    runs, cur = [], None
    for k, (i, v, want, grounded, y, d, ly) in enumerate(out["trace"] or []):
        if not grounded:
            if cur is None:
                cur = [k, k, i, i, 0.0, v]
            cur[1], cur[3] = k, i
            cur[4] = max(cur[4], y - ly)
        elif cur:
            runs.append(cur)
            cur = None
    kicks = 0
    for a, b, i0, i1, h, v in runs:
        frames = b - a + 1
        if frames < least:
            continue
        air = any(L[j].get("air") for j in range(max(0, i0 - 2), min(n, i1 + 3)))
        kicks += 0 if air else 1
        p = L[i0]["p"]
        print("  %s  %3d frames  stations %4d-%-4d (%.3f)  %.1f up  at %.0f u/s  [%.0f, %.0f, %.0f]"
              % ("JUMP" if air else "KICK", frames, i0, i1, i0 / float(n), h, v, p[0], p[1], p[2]))
    if out["trace"] and len(out["trace"]) >= 6000:
        print("  (trace capped at 6000 frames - the end of a long lap is not covered)")
    return kicks


if __name__ == "__main__":
    sys.exit(main(sys.argv))
