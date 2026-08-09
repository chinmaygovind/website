#!/usr/bin/env bash
#
# Run the tests for the parts of the site that changed.
#
# The full suite is about three minutes (drive ~1:35, kot ~1:10), and almost
# every change touches one game, so running all of it is nearly always waste.
#
# Each suite is split across cores where that helps - see parallel_for.
#
# Usage:
#   scripts/tests.sh                  # only what changed (see changed-modules.sh)
#   scripts/tests.sh drive            # a specific module (site, drive, ers, kot)
#   scripts/tests.sh drive kot        # several
#   scripts/tests.sh --all            # everything
#   scripts/tests.sh --list           # print what would run, run nothing
#   scripts/tests.sh drive -- -k ghost -x     # anything after -- goes to pytest
#
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

ALL_MODULES="site drive ers kot"

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
# The two suites that cost real time are CPU bound and their tests are
# independent, so this is most of the speed here: drive goes 5:40 -> 1:35 and
# kot 2:25 -> 1:10.
#
# **drive splits by file, not by test.** The original reason was test_sim.py,
# which drove each track once and kept the lap for seven tests to ask questions
# about - split by test and each worker re-drove it, which was slower than not
# parallelising at all. That file is gone, but the shape of the reason is not:
# half of drive's suite builds a QuickJS runtime in a module-scoped fixture, and
# a module scattered across four workers builds it four times. Everything else
# splits by test, which packs better.
#
# Four workers rather than every core, deliberately. Past four the critical
# path is one long file either way, so there is nothing left to win - and on a
# 16 core laptop kot's self-play tests contend badly enough that the suite
# stops finishing at all.
parallel_for() {
  m="$1"; py="$2"

  # 18 tests in a twentieth of a second. Starting workers costs more.
  [ "$m" = ers ] && return 0

  # Optional, like quickjs: without it the suite runs serially rather than
  # refusing to run.
  "$py" -c "import xdist" >/dev/null 2>&1 || return 0

  # An explicit -n after `--` is the caller overriding this.
  case " $pytest_args " in *" -n "*|*" -p no:xdist "*) return 0 ;; esac

  n="$(nproc 2>/dev/null || echo 4)"
  [ "$n" -gt 4 ] && n=4
  [ "$m" = drive ] && echo "-n $n --dist loadfile" || echo "-n $n --dist load"
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
  [ "$run_all" = 1 ] && return 0
  # An explicit -m from the caller is the caller's business, not ours.
  case " $pytest_args " in *" -m "*) return 1 ;; esac
  for ref in HEAD --cached; do
    if git -C "$ROOT" diff --name-only $ref -- kot/bot.py kot/cards.py 2>/dev/null \
         | grep -q .; then return 0; fi
  done
  return 1
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

  if [ "$m" = site ]; then
    # Two things, cheapest first. "Does it still import" is what the deploy
    # checks before it ships and catches a broken root app on its own; the
    # accounts suite is the real one. Both, because the import check is the
    # only thing that runs when there is no pytest to be had.
    ( cd "$ROOT" && "$py" -c "import app; print('app imports OK')" ) || return 1
    if [ -d "$ROOT/tests" ]; then
      ( cd "$ROOT" && "$py" -m pytest tests/ $par $pytest_args )
    fi
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
