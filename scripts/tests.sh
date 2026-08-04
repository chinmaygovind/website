#!/usr/bin/env bash
#
# Run the tests for the parts of the site that changed.
#
# The full suite is about five minutes (drive ~2:10, kot ~2:00), and almost
# every change touches one game, so running all of it is nearly always waste.
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

while [ $# -gt 0 ]; do
  case "$1" in
    --all|-a)  modules="$ALL_MODULES" ;;
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
  [ -x "$dir/bin/python" ] && return 0

  echo "no venv for $m yet, creating one"
  python3 -m venv "$dir" || return 1
  "$dir/bin/pip" install -q -r "$reqs" || return 1
  # Optional test-only deps: pytest for the root app, drive's QuickJS, ...
  if [ -f "$test_reqs" ]; then
    "$dir/bin/pip" install -q -r "$test_reqs" || return 1
  fi
}

run_module() {
  m="$1"
  ensure_venv "$m" || { echo "could not set up $m/venv" >&2; return 1; }
  py="$(py_for "$m")"

  if [ "$m" = site ]; then
    # Two things, cheapest first. "Does it still import" is what the deploy
    # checks before it ships and catches a broken root app on its own; the
    # accounts suite is the real one. Both, because the import check is the
    # only thing that runs when there is no pytest to be had.
    ( cd "$ROOT" && "$py" -c "import app; print('app imports OK')" ) || return 1
    if [ -d "$ROOT/tests" ]; then
      ( cd "$ROOT" && "$py" -m pytest tests/ $pytest_args )
    fi
  else
    ( cd "$ROOT/$m" && "$py" -m pytest tests/ $pytest_args )
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
