"""Measure what each bot level is actually worth, and solve for its pace.

A level is supposed to mean something - easy is a bronze lap, max is the record -
and one pace multiplier cannot deliver that across the pool, because the same
multiplier is a silver on one track and worse than bronze on another. So it is
solved per track per level, here, and the answers go in `bots_pace.json`.

    python tools/calibrate_bots.py                     # everything, then write
    python tools/calibrate_bots.py --tracks sunrise    # a subset
    python tools/calibrate_bots.py --levels hard max
    python tools/calibrate_bots.py --report            # drive as configured, no solving
    python tools/calibrate_bots.py --sweep             # grid over the driver's gains

**Re-run it when the car is retuned, when a track's geometry moves, or when
`tools/hotlap.py` picks up a new record** - all three change what a lap is worth.
Nothing detects a stale table automatically, exactly like the track previews;
what a stale one costs is a level being a second or so off the medal it is named
for, which is a disappointment rather than a failure.

`--sweep` is the other half. The driver's gains in `bot.js` are not matters of
taste - the wrong lookahead runs the car wide out of corners and lands it on the
grass after every jump - so when one of them changes, this is how the change is
judged: drive the pool, add up the gap to each record, print it.
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
sys.path.insert(0, DRIVE)

import bots                                              # noqa: E402
import botsim                                            # noqa: E402
import tracks as tracks_mod                              # noqa: E402

# Close enough. Half a percent of a lap is well inside the spread a bot shows
# race to race from its own mistakes, so solving tighter is solving noise.
TOL = 0.005
MAX_ROUNDS = 5
# A pace this far outside 1.0 is not a driver being asked to try harder, it is
# one being asked to do something the line does not support - past the top of
# this it simply crashes, and under the bottom it is not really driving.
PACE_MIN, PACE_MAX = 0.45, 1.18
# **A level driving a recorded lap may not be asked to beat it by much.** Its
# reference speeds are a real lap a person actually held on this geometry, so
# anything over 1.0 there is a demand for a corner nobody has taken - the car
# runs wide, and the search "converges" on a pace that crashes. The relaxed line
# is a conservative estimate rather than a record and has genuine headroom, so
# it keeps the wider ceiling.
HOTLAP_PACE_MAX = 1.02
# What a DNF costs when a round hits one: back off and try again.
DNF_BACKOFF = 0.92


def _ceiling(level, line):
    """The most pace this level may be given on this line.

    Per level and not just per line, because hard and max are both aimed at
    times the driver cannot quite reach - so a single ceiling pins both at the
    top and the two come out identical. See `paceMax` in bots.py.
    """
    if line != "hotlap":
        return PACE_MAX
    return bots.PROFILES[level].get("paceMax", HOTLAP_PACE_MAX)


def drive(slug, level, pace=None, tune=None, seed=1, line=None):
    """One lap, with an optional gain override for `--sweep`."""
    if tune is None:
        return botsim.solo_lap(slug, level, pace=pace, seed=seed, line=line)
    # The sweep path needs to put `tune` inside the profile, which `solo_lap`
    # builds itself - so it is done here rather than widening that signature for
    # a case only this tool has.
    rt = botsim.runtime()
    lin, source = bots.line_for(slug, level, force=line)
    prof = bots.profile(slug, level, seed=seed, pace=pace)
    prof["tune"] = tune
    botsim.build(rt, slug)
    try:
        rt.ctx.set_time_limit(180)
        out = rt.call("botLap(TRACKS.find(t => t.slug === %s), T, %s, %s, %s)"
                      % (json.dumps(slug), json.dumps(lin), json.dumps(prof),
                         json.dumps({"fps": 60, "maxT": 180})))
    finally:
        rt.ctx.set_time_limit(botsim.EVAL_LIMIT_S)
    out["source"] = source
    out["pace"] = prof["pace"]
    return out


def solve(slug, level, verbose=True):
    """Find the pace that puts this level on its target time, on a line it can drive.

    Two attempts. First on the line the level asks for - the recorded fast lap
    for the quick levels - and then, only if that could not be got round at any
    pace, on the relaxed one.

    **The fallback is a measurement and it is written down**, because a level
    that cannot complete a track is far worse than one that is a second slow: a
    bot that goes off at the same jump every lap spends the race respawning and
    is no use to anybody racing it. Where the fallback fires, `bots_pace.json`
    records `relaxed` and the room drives the safe line there until the driver
    is good enough that a re-run takes it away again.
    """
    target = bots.target_ms(slug, level)
    if not target:
        return None
    want = bots.PROFILES[level]["line"]
    best = _solve_on(slug, level, target, want, verbose)
    # **Getting round is not the bar; landing near the target is.** Gauntlet's
    # quick line technically completed - in 51.88s against a target of 36.23,
    # which is a car crawling home after falling off - so "did it finish" would
    # have kept it. A lap this far out, or one with a crash in it, means the
    # driver cannot hold this line here, so the other one is tried and whichever
    # lands closer wins.
    poor = best is None or abs(best["err"]) > 0.05 or best["respawns"] > 1
    if poor and want != "relaxed":
        if verbose:
            print("      that line is not working here; trying the safe one")
        alt = _solve_on(slug, level, target, "relaxed", verbose)
        if alt and (best is None or abs(alt["err"]) < abs(best["err"])):
            best = alt
    return best


def _solve_on(slug, level, target, line, verbose):
    """The pace search on one particular line, or None if it never got round.

    Newton in one variable, and it converges in two or three rounds because lap
    time is very nearly inversely proportional to pace over the range that
    matters. The interesting part is the failures: a DNF means the pace asked
    for something the car could not hold, so back off and try again rather than
    treating the timeout as a lap time.
    """
    pace = bots.PROFILES[level]["pace"]
    ceiling = _ceiling(level, line)
    best = None
    for rnd in range(MAX_ROUNDS):
        out = drive(slug, level, pace=pace, line=line)
        if not out["finished"]:
            if verbose:
                print("      round %d  pace %.3f  DNF at %.0f%%"
                      % (rnd, pace, 100 * out["progress"]))
            pace = round(pace * DNF_BACKOFF, 4)
            if pace < PACE_MIN:
                break
            continue
        ms = out["time"]
        err = (ms - target) / float(target)
        if best is None or abs(err) < abs(best["err"]):
            best = {"pace": pace, "ms": ms, "err": err, "line": out["source"],
                    "respawns": out["respawns"]}
        if verbose:
            print("      round %d  pace %.3f  %.2fs vs %.2fs  (%+.1f%%)"
                  % (rnd, pace, ms / 1000.0, target / 1000.0, 100 * err))
        if abs(err) <= TOL:
            break
        nxt = round(min(ceiling, max(PACE_MIN, pace * (1 + err * 0.9))), 4)
        if abs(nxt - pace) < 1e-4:
            break                      # pinned at a limit; no more to be had
        pace = nxt
    # Newton assumes lap time falls as pace rises. Past the driver's competence
    # that is false: the extra speed is carried into corners the car cannot hold,
    # and the lap gets *slower* - measured at 3.3s worse on Chicane between pace
    # 1.02 and 1.50, with Eight and Mount Joy ceasing to finish at all. So a
    # level that is still short of its target has been pushed to the ceiling by
    # the search and left there, which is very often not its quickest pace. Scan
    # back down and keep the best lap actually driven. Only saturated levels pay
    # for this, which in practice means `hard` and `max`.
    if best is not None and best["err"] > TOL:
        best = _fastest_below(slug, level, line, ceiling, target, best, verbose)
    return best


# How far below the ceiling to look for the real optimum, and in what steps.
_SCAN = (1.0, 0.96, 0.92, 0.88, 0.84, 0.80)


def _fastest_below(slug, level, line, ceiling, target, best, verbose):
    """The quickest clean lap over a scan of paces, not the highest pace.

    A lap with a respawn in it is only accepted if nothing clean was found: a
    respawn is a second and a half of standing still that the bot's *rivals*
    watch it take, so a level whose calibration depends on one is not calibrated.
    """
    for f in _SCAN:
        pace = round(ceiling * f, 4)
        if pace < PACE_MIN:
            break
        out = drive(slug, level, pace=pace, line=line)
        if not out["finished"]:
            continue
        cand = {"pace": pace, "ms": out["time"], "line": out["source"],
                "respawns": out["respawns"],
                "err": (out["time"] - target) / float(target)}
        if verbose:
            print("      scan   pace %.3f  %.2fs%s"
                  % (pace, cand["ms"] / 1000.0,
                     "  (%d respawns)" % cand["respawns"] if cand["respawns"] else ""))
        # Clean first, then quickest. `False < True`, so the flag sorts a lap
        # with no respawn in it ahead of one with, whatever the times are.
        if (bool(cand["respawns"]), cand["ms"]) < (bool(best["respawns"]), best["ms"]):
            best = cand
    return best


def enforce_order(slug, solved, verbose=True):
    """Make sure the levels come out in the order their names promise.

    Nothing in the pace solve guarantees it. Each level is fitted to its own
    target independently, and where a quick level cannot drive the recorded line
    it falls back to the safe one and is fitted to a target that line cannot
    reach - so it lands wherever the search happened to stop. Measured over the
    pool that produced Sunrise with `max` at 18.50 against `hard` at 17.88, and
    Cloudbreak with `hard` five seconds slower than its own `medium`.

    A Max that loses to a Medium is the single most obvious way for this whole
    feature to look broken, so it is a constraint rather than a hope: walk up
    the levels, and any that is not quicker than the one below it gets more pace
    until it is - or, failing that, inherits the configuration of the level
    below, which at least ties rather than inverting.
    """
    order = [lv for lv in bots.LEVELS if lv in solved and solved[lv]]
    for a, b in zip(order, order[1:]):
        lo, hi = solved[a], solved[b]
        tries = 0
        while hi["ms"] >= lo["ms"] - 100 and tries < 3:
            tries += 1
            ceiling = _ceiling(b, hi["line"])
            nxt = round(min(ceiling, hi["pace"] * 1.05), 4)
            if abs(nxt - hi["pace"]) < 1e-4:
                break
            out = drive(slug, b, pace=nxt, line=hi["line"])
            if out["finished"] and out["time"] < hi["ms"]:
                hi = {"pace": nxt, "ms": out["time"], "line": out["source"],
                      "err": hi["err"], "respawns": out["respawns"]}
                solved[b] = hi
            else:
                break
        if hi["ms"] >= lo["ms"] - 100:
            # Still not quicker. Take the level below's whole configuration -
            # a tie reads as "these two are much the same", where an inversion
            # reads as broken.
            if verbose:
                print("   %-7s could not be made quicker than %s here; "
                      "taking its settings" % (b, a))
            solved[b] = dict(lo)
    return solved


def report(slugs, levels):
    """Drive as currently configured and say how far off each level lands."""
    print("%-10s %-7s %8s %8s %7s  %-8s" %
          ("track", "level", "lap", "target", "diff", "line"))
    worst = 0.0
    for slug in slugs:
        for level in levels:
            target = bots.target_ms(slug, level)
            out = drive(slug, level)
            if not out["finished"]:
                print("%-10s %-7s %8s %8.2f %7s  %-8s  <-- DNF at %.0f%%"
                      % (slug, level, "DNF", target / 1000.0, "", out["source"],
                         100 * out["progress"]))
                worst = max(worst, 99)
                continue
            d = (out["time"] - target) / 1000.0
            worst = max(worst, abs(d))
            print("%-10s %-7s %8.2f %8.2f %+7.2f  %-8s%s"
                  % (slug, level, out["time"] / 1000.0, target / 1000.0, d,
                     out["source"], "  (%d respawns)" % out["respawns"]
                     if out["respawns"] else ""))
    print("\nworst miss: %.2fs" % worst)


def sweep(slugs):
    """Grid over the driver's gains, scored against the records.

    Scored on `max` only and against the record itself, because that is the
    level the gains actually bind on: the slower levels have pace in hand and
    will hit their target whatever the steering is doing.
    """
    import itertools
    rec = {s: (bots.hotlap(s) or {}).get("time_ms") for s in slugs}
    slugs = [s for s in slugs if rec.get(s)]
    grid = list(itertools.product([0.5, 0.9, 1.6], [1.0, 2.5, 5.0],
                                  [0.06, 0.12, 0.20]))
    print("sweeping %d combinations of head/cross/turnLead over %s\n"
          % (len(grid), ", ".join(slugs)))
    rows = []
    for head, cross, lead in grid:
        tune = {"head": head, "cross": cross, "turnLead": lead}
        cells, score = [], 0.0
        for s in slugs:
            out = drive(s, "hard", tune=tune)
            if out["finished"] and out["respawns"] == 0:
                secs = out["time"] / 1000.0
                cells.append("%6.2f" % secs)
                score += secs - rec[s] / 1000.0
            else:
                cells.append("   DNF")
                score += 40.0
        rows.append((score, tune))
        print("head %.1f  cross %.1f  lead %.2f   %s   score %+7.2f"
              % (head, cross, lead, " ".join(cells), score))
    rows.sort(key=lambda r: r[0])
    print("\nbest: %s  score %+.2f" % (json.dumps(rows[0][1]), rows[0][0]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tracks", nargs="*", default=None)
    ap.add_argument("--levels", nargs="*", default=list(bots.LEVELS))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    slugs = args.tracks or [t["slug"] for t in tracks_mod.TRACKS]
    if not botsim.available():
        print("quickjs is not installed, or DRIVE_BOTS is off")
        return 1

    t0 = time.time()
    if args.sweep:
        sweep(slugs)
        print("\n%.0fs" % (time.time() - t0))
        return 0
    if args.report:
        report(slugs, args.levels)
        print("%.0fs" % (time.time() - t0))
        return 0

    table = dict(bots.paces())
    for slug in slugs:
        print("%s" % slug)
        solved = {}
        for level in args.levels:
            best = solve(slug, level)
            if not best:
                print("   %-7s no target" % level)
                continue
            solved[level] = best
            fell = best["line"] != bots.PROFILES[level]["line"]
            print("   %-7s pace %.3f -> %.2fs (%+.1f%%) on the %s line%s%s"
                  % (level, best["pace"], best["ms"] / 1000.0, 100 * best["err"],
                     best["line"], "  <-- FELL BACK" if fell else "",
                     "  MISSED" if abs(best["err"]) > 0.02 else ""))
        # A Max that loses to a Medium is the most visible way this can be
        # wrong, and nothing above prevents it. See `enforce_order`.
        if len(solved) > 1:
            solved = enforce_order(slug, solved)
            print("   order: " + "  ".join(
                "%s %.2f" % (lv, solved[lv]["ms"] / 1000.0)
                for lv in bots.LEVELS if lv in solved))
        for level, best in solved.items():
            table.setdefault(slug, {})[level] = {"pace": best["pace"],
                                                 "line": best["line"]}
    if args.dry_run:
        print("\n(dry run; %s not written)" % bots.PACE_FILE)
        return 0
    with open(bots.PACE_FILE, "w") as f:
        json.dump(table, f, indent=1, sort_keys=True)
    print("\nwrote %s in %.0fs" % (bots.PACE_FILE, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
