#!/usr/bin/env python3
"""Run one module's tests as several pytest processes, one test file at a time.

**This is not `pytest-xdist`, and the difference is the whole point.** xdist
splits a run inside one controller that talks to its workers over pipes, using
OS threads it creates at start-up. `drive/app.py` calls `eventlet.monkey_patch()`
on its second line - it has to, since one eventlet worker serves every live race
- and that greens `threading` *after* execnet has already made those threads. A
real thread signalling a green primitive does not wake eventlet's hub, so the
worker's main thread goes to sleep waiting for something that can never arrive:
the run reaches 93-98%, every test passes, and then the controller sits in
`futex_do_wait` while its workers sit in `hrtimer_nanosleep` until somebody
kills the job. That is the stall `drive/docs/testing.md` recorded at 246s, 739s
and 901s and could not explain, and it reproduces here in about two runs out of
three at `-n 16`.

Separate processes have no such problem. Each one is an ordinary `pytest`
invocation - exactly the thing that is known to exit cleanly - and the shell is
the only thing coordinating them. What is given up is work-stealing *within* a
file, so the wall clock cannot go below the slowest single file.

**Files are ordered longest-first, from times this script recorded last run.**
A greedy queue with the big files started first packs about as well as bin
packing and needs no estimate of anything: whatever is left at the end is small.
The table is written to `<module>/.pytest-file-times`, gitignored, and a file
missing from it sorts first - so a newly added file is treated as expensive
until it has been timed once, which is the safe way round.
"""

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

TIMES = ".pytest-file-times"


# What one pytest process costs before it runs a single test: a fresh
# interpreter, Flask, SQLAlchemy and the track pool. Used to take the extra
# start-ups back out of a split file's recorded cost, so the table says roughly
# what the file would cost whole. Only the *order* of the table is read (see
# SPLIT_TOP), so this needs to be about right rather than exact.
OVERHEAD_MS = 1300


def load_times(root):
    out = {}
    try:
        with open(os.path.join(root, TIMES)) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    out[parts[1]] = int(parts[0])
    except (OSError, ValueError):
        pass
    return out


def save_times(root, times):
    try:
        with open(os.path.join(root, TIMES), "w") as f:
            for name, ms in sorted(times.items(), key=lambda kv: -kv[1]):
                f.write("%d %s\n" % (ms, name))
    except OSError:
        pass                      # a timing hint is not worth failing a run over


# **How many files get cut up, and into how many pieces - by rank, not by
# clock.** The wall clock cannot go below the slowest single unit, so the two or
# three files that set it have to stop being one unit each.
#
# Deciding that from the recorded milliseconds does not work, and the way it
# fails is worth writing down: the times are recorded *during a parallel run*,
# where sixteen processes share sixteen logical CPUs and every unit takes two to
# three times what it would alone. Feed that back in and a file looks more
# expensive than it is, gets split further, adds processes, deepens the
# contention, and looks more expensive again. Three runs took it from 43 units
# at 28.8s to 67 units at 29.3s, with `test_verify.py` "costing" 54s.
#
# So only the *order* of the table is used, and the order is stable under
# contention because everything inflates together. The top few files are split a
# fixed number of ways, and nothing else is.
SPLIT_TOP = 3
SPLIT_PIECES = 3

# **The totals are printed, and that is not decoration.** Splitting a file means
# handing pytest a list of node ids, and the failure mode with no symptom is a
# unit that runs *fewer* tests than it was meant to - a mistyped id selects
# nothing, and pytest exits 0 having run nothing at all. Summing what every unit
# reported and printing it means a run that quietly stopped covering a third of
# `test_verify.py` says so, instead of going green faster than before.
COUNT = re.compile(r"(\d+) (passed|failed|skipped|error|errors|xfailed|xpassed)")


def split(root, py, name, rank, extra):
    """One file as one or more `(file, label, [pytest targets])` units.

    `rank` is its place in the timing table, 0 being the most expensive.
    """
    path = os.path.join("tests", name)
    pieces = SPLIT_PIECES if rank < SPLIT_TOP else 1
    if pieces < 2:
        return [(name, name, [path])]

    p = subprocess.run([py, "-m", "pytest", path, "-q", "--collect-only",
                        "-p", "no:cacheprovider"] + extra,
                       cwd=root, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    ids = [ln.strip() for ln in p.stdout.decode("utf-8", "replace").splitlines()
           if ln.strip().startswith(path + "::")]
    if p.returncode != 0 or len(ids) < pieces * 2:
        # Collection said something unexpected - a collect error, or too few
        # tests to be worth cutting. Run the file whole rather than run part of
        # it: a unit that silently covers half a file is the one failure mode
        # this must not have.
        return [(name, name, [path])]

    # Round robin rather than contiguous blocks. Cost within a file is lumpy -
    # `test_verify.py` has one 7s test among twenty short ones - and dealing
    # them out spreads the lumps instead of putting them all in one pile.
    out = [[] for _ in range(pieces)]
    for i, node in enumerate(ids):
        out[i % pieces].append(node)
    return [(name, "%s [%d/%d]" % (name, i + 1, pieces), chunk)
            for i, chunk in enumerate(out) if chunk]


def main():
    root, py, jobs = sys.argv[1], sys.argv[2], int(sys.argv[3])
    # Each pytest runs with `cwd=root`, so a caller's relative interpreter path
    # ("drive/venv/bin/python") would be resolved from inside the module and not
    # found. Pin both before anything changes directory.
    root = os.path.abspath(root)
    if os.sep in py:
        py = os.path.abspath(py)
    extra = sys.argv[4:]

    tests = os.path.join(root, "tests")
    files = sorted(f for f in os.listdir(tests)
                   if f.startswith("test_") and f.endswith(".py"))
    if not files:
        print("no test files in %s" % tests, file=sys.stderr)
        return 1

    # Files that mutate something the whole module shares. They get the machine
    # to themselves, first, before anything else is started. See tests/EXCLUSIVE.
    exclusive = []
    try:
        with open(os.path.join(tests, "EXCLUSIVE")) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line in files:
                    exclusive.append(line)
    except OSError:
        pass
    files = [f for f in files if f not in exclusive]

    known = load_times(root)
    # Unknown sorts first: a file nobody has timed might be the slow one, and
    # starting it last is the only ordering that can hurt.
    files.sort(key=lambda f: -known.get(f, 10 ** 9))

    total = 0
    fresh, pieces, units, tally, failed = {}, {}, {}, {}, []
    lock = __import__("threading").Lock()
    done = [0]

    def run(unit):
        name, label, targets = unit
        started = time.time()
        p = subprocess.run(
            [py, "-m", "pytest"] + targets + ["-q", "-p", "no:cacheprovider"]
            + extra,
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ms = int((time.time() - started) * 1000)
        with lock:
            # Two different numbers. `units` is what actually sets the wall
            # clock - the slowest single process - and `fresh` is what the file
            # is estimated to cost unsplit, which is what next run splits on.
            units[label] = ms
            for n, word in COUNT.findall(
                    p.stdout.decode("utf-8", "replace")):
                tally[word] = tally.get(word, 0) + int(n)
            fresh[name] = fresh.get(name, 0) + ms
            pieces[name] = pieces.get(name, 0) + 1
            done[0] += 1
            if p.returncode != 0:
                failed.append((name, p.stdout.decode("utf-8", "replace")))
            if sys.stdout.isatty():
                sys.stdout.write("\r  %d/%d units" % (done[0], total))
                sys.stdout.flush()
        return p.returncode

    # `files` is already sorted most-expensive first, so position is rank. A
    # file with no recorded time sorts to the front and is treated as expensive.
    order = {name: i for i, name in enumerate(files)}
    queue = []
    for name in files:
        queue.extend(split(root, py, name, order.get(name, 0), extra))

    started = time.time()
    total = len(queue) + len(exclusive)
    for name in exclusive:              # alone, and before the rest
        run((name, name, [os.path.join("tests", name)]))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        list(pool.map(run, queue))
    if sys.stdout.isatty():
        sys.stdout.write("\r")

    work = {n: max(1, ms - (pieces.get(n, 1) - 1) * OVERHEAD_MS)
            for n, ms in fresh.items()}
    save_times(root, work)

    for name, output in failed:
        print("=" * 70)
        print("FAILED  tests/%s" % name)
        print("=" * 70)
        print(output.rstrip())

    summary = ", ".join("%d %s" % (n, w) for w, n in sorted(tally.items())
                        if n)
    slow = sorted(units.items(), key=lambda kv: -kv[1])[:3]
    print("  %s" % (summary or "no tests reported"))
    print("  %d units on %d processes in %.1fs (slowest: %s)"
          % (total, jobs, time.time() - started,
             ", ".join("%s %.1fs" % (n, ms / 1000.0) for n, ms in slow)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
