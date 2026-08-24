#!/usr/bin/env bash
# Reclaim disk from worktree build caches.
#
# .next is the offender: a Next build cache grows to 2-3G per worktree and
# never shrinks, so 20 idle worktrees quietly cost 40G+. It is fully
# regenerable, so it should never outlive the work it was built for.
#
#   ./scripts/worktree-gc.sh              # dry run - show what would go
#   ./scripts/worktree-gc.sh --apply      # delete .next in idle worktrees
#   ./scripts/worktree-gc.sh --apply --deep    # also node_modules + venv
#   ./scripts/worktree-gc.sh --apply --merged  # also remove clean worktrees
#                                              # whose HEAD is in origin/main
#
# A worktree running `next dev` is SKIPPED, never touched. This script never
# kills a process and never deletes a worktree with uncommitted changes or
# unpushed commits.
set -uo pipefail

# The PRIMARY checkout, not merely the current one: --show-toplevel resolves to
# whichever worktree invoked us, and this script must never sweep the primary.
ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
APPLY=0; DEEP=0; MERGED=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --deep) DEEP=1 ;;
    --merged) MERGED=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done
(( APPLY )) || echo "DRY RUN - pass --apply to actually delete"

# Directories that are the cwd of a live `next dev`, so we leave them alone.
busy=""
for p in $(pgrep -f '[n]ext dev' 2>/dev/null); do
  c=$(lsof -a -p "$p" -d cwd 2>/dev/null | tail -1 | awk '{print $NF}')
  [ -n "$c" ] && busy="$busy $c"
done

freed=0
rm_path() {  # $1 = path to remove
  [ -d "$1" ] || return 0
  local mb; mb=$(du -sm "$1" 2>/dev/null | cut -f1)
  freed=$(( freed + ${mb:-0} ))
  if (( APPLY )); then rm -rf "$1"; echo "  removed ${mb}MB  $1"
  else echo "  would remove ${mb}MB  $1"; fi
}

git worktree list --porcelain | grep '^worktree ' | cut -d' ' -f2- | while read -r wt; do
  [ "$wt" = "$ROOT" ] && continue   # never touch the primary checkout
  fe="$wt/sorento_crm_frontend"
  case "$busy" in *"$fe"*) echo "SKIP (dev server live)  $wt"; continue ;; esac

  echo "$wt"
  rm_path "$fe/.next"
  if (( DEEP )); then
    rm_path "$fe/node_modules"
    rm_path "$wt/sorento_crm_backend/venv"
  fi

  if (( MERGED )); then
    dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    inmain=$(git -C "$wt" branch -r --contains HEAD 2>/dev/null | grep -c 'origin/main')
    if [ "$dirty" = "0" ] && [ "$inmain" -gt 0 ]; then
      if (( APPLY )); then git worktree remove "$wt" && echo "  worktree removed (merged, clean)"
      else echo "  would remove worktree (merged into origin/main, clean)"; fi
    fi
  fi
done

echo
echo "Run 'git worktree prune' afterwards to clear stale registrations."
