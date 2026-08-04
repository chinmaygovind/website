#!/usr/bin/env bash
#
# Print the modules a set of changed files touches, one per line.
#
# This is the single place that maps a path to a test suite. Both the local
# runner (scripts/tests.sh) and the deploy workflow call it, so they can never
# disagree about what "changed" means.
#
# Usage:
#   scripts/changed-modules.sh                 # uncommitted work + commits not on origin/main
#   scripts/changed-modules.sh <base>          # everything since <base>
#   scripts/changed-modules.sh <base> <head>   # a specific range
#   scripts/changed-modules.sh --stdin         # read the paths from stdin instead
#   scripts/changed-modules.sh --json ...      # a JSON array, for the Actions matrix
#
set -uo pipefail

JSON=0
STDIN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --json)  JSON=1; shift ;;
    --stdin) STDIN=1; shift ;;
    *) break ;;
  esac
done

cd "$(dirname "$0")/.."

# --- collect the changed paths -------------------------------------------

paths=""

if [ "$STDIN" = 1 ]; then
  # CI takes this branch: it asks GitHub which files the push touched, so it
  # never has to clone the history to find out.
  paths="$(cat)"
elif [ $# -eq 0 ]; then
  # Local default: whatever is not committed, plus whatever is committed here
  # but not on origin/main yet.
  paths="$(git status --porcelain=v1 | cut -c4- | tr '\n' '\n')"
  base=""
  if git rev-parse --verify --quiet origin/main >/dev/null; then
    base="$(git merge-base HEAD origin/main 2>/dev/null || true)"
  fi
  if [ -n "$base" ]; then
    paths="$paths
$(git diff --name-only "$base" HEAD)"
  fi
else
  base="$1"
  head="${2:-HEAD}"
  # A first push, a force push or a shallow clone can leave the base
  # unreachable; fall back to the head commit on its own.
  if ! git rev-parse --verify --quiet "$base^{commit}" >/dev/null \
    || [ "$base" = "0000000000000000000000000000000000000000" ]; then
    paths="$(git diff-tree --no-commit-id --name-only -r "$head")"
  else
    paths="$(git diff --name-only "$base" "$head")"
  fi
fi

# A rename shows up as "old -> new"; keep the new name.
paths="$(printf '%s\n' "$paths" | sed 's/.* -> //' | sed 's/^"//; s/"$//' | grep -v '^$' || true)"

# --- map paths to modules ------------------------------------------------

want_site=0 want_drive=0 want_ers=0 want_kot=0

all() { want_site=1; want_drive=1; want_ers=1; want_kot=1; }

while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$p" in
    drive/*) want_drive=1 ;;
    ers/*)   want_ers=1 ;;
    kot/*)   want_kot=1 ;;

    # ttr is a submodule with its own repo and its own CI.
    ttr|ttr/*|.gitmodules) ;;

    # Changing the test plumbing itself means we do not know what is safe to
    # skip, so run the lot.
    scripts/*|.github/workflows/*) all ;;

    # Docs, deploy plumbing and editor config affect no test suite.
    *.md|.gitignore|deploy/*|.claude/*|.github/*) ;;

    # app.py, requirements.txt, accounts/, tests/, site/ and anything
    # unrecognised: the root app. Its suite is the accounts tests plus the
    # import check the deploy used to be - a couple of seconds either way, so
    # an unknown path landing here costs almost nothing.
    #
    # `accounts/` deliberately is not a module of its own: it is not a service,
    # it is part of the website app, installed from the root requirements.txt
    # into the root venv and served by the same gunicorn.
    *) want_site=1 ;;
  esac
done <<EOF
$paths
EOF

# --- emit ----------------------------------------------------------------

# Canonical order: cheapest first.
mods=""
[ $want_site  = 1 ] && mods="$mods site"
[ $want_drive = 1 ] && mods="$mods drive"
[ $want_ers   = 1 ] && mods="$mods ers"
[ $want_kot   = 1 ] && mods="$mods kot"

if [ "$JSON" = 1 ]; then
  out="["
  sep=""
  for m in $mods; do
    out="$out$sep\"$m\""
    sep=","
  done
  echo "$out]"
else
  for m in $mods; do echo "$m"; done
fi
