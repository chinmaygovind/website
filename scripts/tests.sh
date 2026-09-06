#!/usr/bin/env bash
#
# Run the tests for the parts of the site that changed.
#
# The full suite is about two and a half minutes (drive ~1:10, kot ~1:10), and
# almost every change touches one game, so running all of it is nearly always
# waste.
#
# Each suite is split across cores where that helps - see parallel_for.
#
# Usage:
#   scripts/tests.sh                  # only what changed (see changed-modules.sh)
#   scripts/tests.sh drive            # a specific module (site, gto, drive, ers, kot)
#   scripts/tests.sh drive kot        # several
#   scripts/tests.sh --all            # everything
#   scripts/tests.sh --list           # print what would run, run nothing
#   scripts/tests.sh drive -- -k ghost -x     # anything after -- goes to pytest
#
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

ALL_MODULES="site gto drive ers kot"

modules=""
pytest_args=""
list_only=0
run_all=0

while [ $# -gt 0 ]; do
  case "$1" in
    --all|-a)  modules="$ALL_MODULES"; run_all=1 ;;
    --list|-l) list_only=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --) shift; pytest_args="$*"; break ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *)
      case " $ALL_MODULES " in
        *" $1 "*) modules="$modules $1" ;;
        *) echo "unknown module: $1 (want one of: $ALL_MODULES)" >&2; exit 2 ;;
      esac
      ;;
  esac
  shift
done

if [ -z "$modules" ]; then
  modules="$(scripts/changed-modules.sh | tr '\n' ' ')"
  if [ -z "${modules// /}" ]; then
    echo "Nothing changed that has tests."
    exit 0
  fi
  echo "Changed: $(echo $modules)"
fi

if [ "$list_only" = 1 ]; then
  for m in $modules; do echo "$m"; done
  exit 0
fi

# Prefer the module's own venv, since that is where its deps live locally. In
# CI there is none and everything is on the ambient interpreter.
py_for() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"
  elif [ -x "$ROOT/$1/venv/bin/python" ]; then echo "$ROOT/$1/venv/bin/python"
  elif [ "$1" = site ] && [ -x "$ROOT/venv/bin/python" ]; then echo "$ROOT/venv/bin/python"
  else command -v python3 || command -v python
  fi
}

# The venvs are gitignored and hand made, so a module you have never run tests
# for locally has none. Build it rather than reporting "No module named pytest",
# which is not a test result. CI installs its own deps, so it opts out.
ensure_venv() {
  m="$1"
  if [ -n "${CI:-}" ] || [ -n "${PYTHON:-}" ]; then
    return 0
  fi

  # The root app's venv is at the top rather than under a module directory,
  # since it is the one gunicorn runs in production.
  if [ "$m" = site ]; then
    dir="$ROOT/venv"; reqs="$ROOT/requirements.txt"; test_reqs="$ROOT/requirements-test.txt"
  else
    dir="$ROOT/$m/venv"; reqs="$ROOT/$m/requirements.txt"; test_reqs="$ROOT/$m/requirements-test.txt"
  fi
  if [ ! -x "$dir/bin/python" ]; then
    echo "no venv for $m yet, creating one"
    python3 -m venv "$dir" || return 1
  fi

  # Reinstall when the requirements have actually moved, and not otherwise.
  # The venvs are long lived and gitignored, so without this a dependency
  # added to requirements-test.txt reaches CI and a fresh clone but never the
  # venv you have been running tests in for months - and a missing test-only
  # dependency does not fail, it quietly stops doing whatever it was for.
  stamp="$dir/.requirements-stamp"
  want="$(cat "$reqs" "$test_reqs" 2>/dev/null | cksum)"
  [ "$(cat "$stamp" 2>/dev/null)" = "$want" ] && return 0

  "$dir/bin/pip" install -q -r "$reqs" || return 1
  # Optional test-only deps: pytest for the root app, drive's QuickJS, xdist.
  if [ -f "$test_reqs" ]; then
    "$dir/bin/pip" install -q -r "$test_reqs" || return 1
  fi
  echo "$want" >"$stamp"
}

# How many workers to split a suite across, and how to divide it between them.
# kot is CPU bound with independent tests, so this is most of the speed there:
# 2:25 -> 1:10.
#
# **drive does not come through here at all any more - see `run_parallel`.** It
# runs as separate pytest processes rather than under xdist, because the stall
# that `drive/docs/testing.md` recorded as "not understood" turned out to be
# xdist plus `eventlet.monkey_patch()`, and it is not fixable by tuning `-n`.
#
# **The stall, since it was open for months:** `app.py` monkey-patches on its
# second line, which greens `threading`. xdist's workers talk to the controller
# over pipes using OS threads execnet creates at start-up, *before* any test
# imports `app` - so from the first import onward the worker has real threads
# holding green primitives, and a real thread signalling one does not wake
# eventlet's hub. The worker's main thread goes to sleep waiting for something
# that cannot arrive. Every test has passed; the session just never ends. It is
# visible in `/proc`: each worker's main thread in `hrtimer_nanosleep`, its pipe
# reader in `anon_pipe_read`, the controller in `futex_do_wait`. At `-n 16` it
# reproduced in two runs out of three.
#
# **`kot` monkey-patches too and still runs under xdist below, so it still has
# this.** That is the 3-in-34 CI stall, and the fix is to move it to
# `run_parallel` as well - not done here because it wants its own measurement,
# the way drive's did.
#
# Four workers rather than every core for kot, deliberately: on a 16 core laptop
# its self-play tests contend badly enough that the suite stops finishing.
parallel_for() {
  m="$1"; py="$2"

  # 18 tests in a twentieth of a second. Starting workers costs more.
  [ "$m" = ers ] && return 0

  # **drive must never be handed to xdist, and this is the belt to
  # `run_parallel`'s braces.** It deadlocks there - `eventlet.monkey_patch()`
  # against the OS threads execnet already made, see the note above - and the
  # fallback path in `run_module` would otherwise hand it `-n 4` the moment
  # `run_parallel` was unavailable. That is not a slower run, it is a hung one.
  [ "$m" = drive ] && return 0

  # gto runs serially: 47s against 14s on four workers. It does not monkey-patch
  # and so does not have drive's deadlock, but it has never been measured under
  # `run_parallel` either. Moving it there is the obvious next win - 70% of its
  # runtime - and wants the same before-and-after drive got.
  [ "$m" = gto ] && return 0

  # Optional, like quickjs: without it the suite runs serially rather than
  # refusing to run.
  "$py" -c "import xdist" >/dev/null 2>&1 || return 0

  # An explicit -n after `--` is the caller overriding this.
  case " $pytest_args " in *" -n "*|*" -p no:xdist "*) return 0 ;; esac

  n="$(nproc 2>/dev/null || echo 4)"
  [ "$n" -gt 4 ] && n=4
  echo "-n $n --dist load"
}

# kot's three bot self-play tests are marked `strength` and deselected by
# `kot/pytest.ini`, because they were 24s of kot's 31s. They come back on when the
# thing they measure could actually have changed.
#
# **The limit, said out loud rather than discovered later:** this reads the working
# tree, so it covers the real local loop - edit `bot.py`, run the suite, get the
# strength tests. It does **not** fire in CI, where the checkout is clean and one
# commit deep, so there is nothing to diff against. In CI they run only on the
# manual "run every module's tests" dispatch, whose box is ticked by default.
# Closing that properly means the `pick` job passing its changed-file list through
# to here, which is a change to `.github/workflows/` - and the token cannot push
# workflow files, so it is not done.
strength_wanted() {
  gated_wanted kot/bot.py kot/cards.py
}

# gto gates two suites the same way and for the same reasons. `exhaustive` is
# the evaluator's proof over all 2,598,960 five-card hands (~90s); `calibration`
# deals thousands of hands and checks each bot's *measured* VPIP and PFR against
# the numbers written on its profile (~100s). Each is the reason the thing it
# covers can be trusted, and each is longer than the rest of the suite, so they
# run when what they prove could actually have changed.
#
# **The same CI gap applies, and it is the same one line to close**: this reads
# the working tree, and CI's checkout is clean, so there they run only on the
# manual "every module" dispatch.
gated_wanted() {
  [ "$run_all" = 1 ] && return 0
  # An explicit -m from the caller is the caller's business, not ours.
  case " $pytest_args " in *" -m "*) return 1 ;; esac
  for ref in HEAD --cached; do
    if git -C "$ROOT" diff --name-only $ref -- "$@" 2>/dev/null \
         | grep -q .; then return 0; fi
  done
  # A file git has never seen is not in any diff, so a module whose first
  # commit has not happened yet would silently never run its gated proofs -
  # which is the one time you most want them.
  if git -C "$ROOT" ls-files --others --exclude-standard -- "$@" 2>/dev/null \
       | grep -q .; then return 0; fi
  return 1
}

# Run a module's tests as one process per test file, several at a time.
#
# Used for drive, which cannot use xdist (see above). One process per file is
# also why `drive/tests/EXCLUSIVE` exists: `test_track_folders.py` writes real
# folders into `tracks/`, and anything importing the pool while one is there
# picks it up as a track.
#
# Falls back to a plain serial pytest when the caller asked for something whose
# meaning a split run would change: `-x` should stop the run, not stop each of
# fifty runs, and an explicit `-n` is the caller asking for xdist by name.
# 99 means "I did not run anything, use the fallback". Anything else is the
# result of a real run. **They have to be different numbers**: with both as 1, a
# drive suite with one failing test looked like a decline, and the fallback then
# ran the whole suite again - under xdist, where it hangs. A red test became a
# hang, which is the worst way round.
run_parallel() {
  m="$1"; py="$2"
  case " $pytest_args " in
    *" -x "*|*" -n "*|*" --exitfirst "*|*" -p no:xdist "*) return 99 ;;
  esac
  [ -f "$ROOT/scripts/parallel_pytest.py" ] || return 99

  # **Physical cores, not `nproc`.** These processes are CPU bound, so the two
  # hyperthreads on a core do not give two cores' worth of work - on this laptop
  # 16 processes over 8 cores measured 26.5s against 27.6s for 8, which is a
  # second for twice the contention. And contention is not free elsewhere: it is
  # what the per-test time budget in `drive/tests/conftest.py` has to tolerate.
  n="$(lscpu -p=core 2>/dev/null | grep -cv '^#')"
  [ -n "$n" ] && [ "$n" -gt 0 ] 2>/dev/null || n=0
  if [ "$n" -gt 0 ]; then
    n="$(lscpu -p=core 2>/dev/null | grep -v '^#' | sort -u | wc -l)"
  else
    n="$(nproc 2>/dev/null || echo 4)"
  fi
  [ "$n" -lt 1 ] && n=1
  [ "$n" -gt 16 ] && n=16
  "$py" "$ROOT/scripts/parallel_pytest.py" "$ROOT/$m" "$py" "$n" $pytest_args
}

run_module() {
  m="$1"
  ensure_venv "$m" || { echo "could not set up $m/venv" >&2; return 1; }
  py="$(py_for "$m")"
  par="$(parallel_for "$m" "$py")"
  sel=""
  if [ "$m" = kot ]; then
    if strength_wanted; then
      # Wipes `addopts` (which is only ever the `-m "not strength"` default), so
      # everything is selected again. A single token with no spaces on purpose:
      # this script passes these through unquoted word splitting, and there is no
      # way to spell an empty `-m ""` that survives that.
      sel='--override-ini=addopts='
      echo "  (kot: including the bot strength tests)"
    else
      # A skipped test reads as a pass, so say it. Silence here is the trap.
      echo "  (kot: bot strength tests left out - pass --all, or change bot.py/cards.py)"
    fi
  fi

  if [ "$m" = gto ]; then
    # Two gated suites rather than kot's one, so wiping `addopts` is not enough:
    # leaving out only one of them needs `-m "not exhaustive"`, which has a
    # space in it and cannot survive this script's unquoted word splitting.
    # `PYTEST_ADDOPTS` is read and shlex-parsed by pytest itself, so the space
    # is safe there, and it lands after `pytest.ini`'s `addopts` - where, as
    # that file says, a later `-m` wins.
    marks=""
    left=""
    gated_wanted gto/evaluator.py gto/cards.py \
      || { marks="not exhaustive"; left="the evaluator proof"; }
    gated_wanted gto/bots.py gto/profiles.py \
      || { marks="${marks:+$marks and }not calibration"
           left="${left:+$left, }the bot calibration"; }
    # The third gate is not about time - the whole validation suite is four
    # seconds. It is the only suite here that needs `eval7`, which is a test-only
    # dependency, and it is the only one that compares this code against anybody
    # else's, so it runs whenever a file it could contradict has moved.
    gated_wanted gto/equity.py gto/evaluator.py gto/ranges.py gto/validate.py \
      || { marks="${marks:+$marks and }not validation"
           left="${left:+$left, }the outside-reference checks"; }

    # A skipped test reads as a pass, so always say which proof did not run.
    if [ -z "$left" ]; then
      echo "  (gto: including the evaluator proof, the bot calibration and the outside-reference checks)"
    else
      echo "  (gto: $left left out - pass --all, or change the files they cover)"
    fi

    if [ -z "$marks" ]; then
      export PYTEST_ADDOPTS="-m ''"
    else
      export PYTEST_ADDOPTS="-m \"$marks\""
    fi
  fi

  if [ "$m" = site ]; then
    # Two things, cheapest first. "Does it still import" is what the deploy
    # checks before it ships and catches a broken root app on its own; the
    # accounts suite is the real one. Both, because the import check is the
    # only thing that runs when there is no pytest to be had.
    ( cd "$ROOT" && "$py" -c "import app; print('app imports OK')" ) || return 1
    if [ -d "$ROOT/tests" ]; then
      ( cd "$ROOT" && "$py" -m pytest tests/ $par $pytest_args )
    fi
  elif [ "$m" = drive ]; then
    run_parallel "$m" "$py"
    rc=$?
    if [ "$rc" != 99 ]; then
      return "$rc"                     # it ran; that is the answer
    fi
    # It declined (an -x, an explicit -n) or is missing. Serial, never xdist -
    # `parallel_for` returns nothing for drive, so `$par` is empty here.
    ( cd "$ROOT/$m" && "$py" -m pytest tests/ $par $sel $pytest_args )
  else
    ( cd "$ROOT/$m" && "$py" -m pytest tests/ $par $sel $pytest_args )
  fi
}

failed=""
summary=""

for m in $modules; do
  echo
  echo "=============================== $m ==============================="
  start=$(date +%s)
  if run_module "$m"; then
    status="ok  "
  else
    status="FAIL"
    failed="$failed $m"
  fi
  summary="$summary
  $status  $m  ($(( $(date +%s) - start ))s)"
done

echo
echo "----------------------------------------------------------------"
printf '%s\n' "$summary"

[ -z "$failed" ] || { echo; echo "failed:$failed"; exit 1; }
