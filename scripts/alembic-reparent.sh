#!/usr/bin/env bash
# Re-parent a lane branch's new alembic migrations onto origin/main's current
# head, before the lane's PR is marked ready.
#
# Today that re-parenting is done by hand: find main's head, open the lane's
# first new migration, flip its down_revision, hope nobody transposed a
# character. Two lanes landing close together each get a green PR alone and
# main ends up with two heads anyway, because "main's head" moved between the
# lane branching off and the lane's author doing the hand-edit. This script
# does the same edit mechanically, computed fresh against origin/main at run
# time, so `check-migration-heads` (.github/workflows/deploy.yml) never has to
# catch it.
#
# Usage (from anywhere inside any worktree of this repo):
#   ./scripts/alembic-reparent.sh              # fetch origin/main, then reparent
#   ./scripts/alembic-reparent.sh --no-fetch   # use whatever origin/main already is locally
#
# Only touches the ROOT of the lane's new migration chain (the one file whose
# down_revision does not point at another new migration). Every other new
# migration in the lane is left alone - the chain still hangs off the root,
# the root now hangs off main's head instead of whatever main's head was when
# the lane branched.
#
# No file renaming: revision ids in this repo are a mix of hashes, numeric
# prefixes and short names, and renaming one is out of scope for a mechanical
# tool - it would need to also update every other file's down_revision that
# points at it, which is exactly the kind of edit this script exists to avoid
# doing by hand.
set -euo pipefail

DO_FETCH=1
for arg in "$@"; do
  case "$arg" in
    --no-fetch) DO_FETCH=0 ;;
    *)
      echo "usage: $0 [--no-fetch]" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ "$DO_FETCH" = "1" ]; then
  git fetch origin main
fi

VERSIONS_REL="sorento_crm_backend/alembic/versions" python3 - <<'PY'
import ast
import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path.cwd()
VERSIONS_REL = os.environ["VERSIONS_REL"]
VERSIONS_DIR = REPO_ROOT / VERSIONS_REL


def parse_versions(sources):
    """sources: iterable of (label, text). Returns {revision: down_revision}.

    down_revision is None, a str, or a tuple of str (merge revision). Mirrors
    the ast-based parsing in the check-migration-heads job of
    .github/workflows/deploy.yml, including the explicit utf-8 note: several
    migrations hold non-ASCII literals, and a bare read decodes with the
    runner's locale, which is ASCII whenever LANG is unset.
    """
    graph = {}
    for label, text in sources:
        tree = ast.parse(text, filename=label)
        revision = None
        down_revision = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) \
                    and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            else:
                continue
            if name == "revision":
                revision = ast.literal_eval(value)
            elif name == "down_revision":
                down_revision = ast.literal_eval(value)
        if revision is None:
            print(f"warning: {label} has no `revision` assignment, skipping", file=sys.stderr)
            continue
        graph[revision] = down_revision
    return graph


def down_parents(down_revision):
    if down_revision is None:
        return []
    if isinstance(down_revision, str):
        return [down_revision]
    return list(down_revision)


def heads_of(graph):
    revs = set(graph.keys())
    downs = set()
    for down in graph.values():
        downs.update(down_parents(down))
    return sorted(revs - downs)


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=False,
    ).stdout.decode("utf-8")


# --- 1. main's migration graph, read straight from origin/main (not the
# working tree - the working tree is the lane's branch). ------------------
ls_tree = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", "origin/main", "--", VERSIONS_REL],
    cwd=REPO_ROOT, check=True, capture_output=True, text=True,
).stdout
main_paths = [
    line for line in ls_tree.splitlines()
    if line.endswith(".py") and "__pycache__" not in line
]
main_sources = [(path, git("show", f"origin/main:{path}")) for path in main_paths]
main_graph = parse_versions(main_sources)

main_heads = heads_of(main_graph)
if len(main_heads) != 1:
    sys.exit(
        "error: origin/main itself has "
        f"{len(main_heads)} alembic head(s): {main_heads}\n"
        "main is broken (two migration heads landed) - fix main first, this "
        "script only reparents a lane onto a single main head."
    )
main_head = main_heads[0]

# --- 2. the lane's working-tree migration graph, and which revisions on it
# are NEW (not already on origin/main). ------------------------------------
local_files = sorted(
    p for p in VERSIONS_DIR.glob("*.py") if "__pycache__" not in p.parts
)
local_sources = [(str(p), p.read_text(encoding="utf-8")) for p in local_files]
local_graph = parse_versions(local_sources)
local_paths = {}
for path, text in local_sources:
    tree = ast.parse(text, filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "revision":
            local_paths[ast.literal_eval(node.value)] = pathlib.Path(path)

lane_new = set(local_graph) - set(main_graph)
if not lane_new:
    print("nothing to reparent: no local migration files are new relative to origin/main")
    sys.exit(0)

# --- 3. root(s) of the lane's new chain: a new revision whose down_revision
# does not point at another new revision. ----------------------------------
roots = sorted(
    r for r in lane_new
    if not any(p in lane_new for p in down_parents(local_graph[r]))
)
if len(roots) != 1:
    sys.exit(
        f"error: found {len(roots)} root(s) among the lane's new migrations: {roots}\n"
        "expected exactly one - linearize the lane's migrations manually first "
        "(one down_revision chain, one root)."
    )
root = roots[0]
root_path = local_paths[root]
root_down = local_graph[root]

print(f"main head: {main_head}")
print(f"lane's {len(lane_new)} new migration(s): {sorted(lane_new)}")
print(f"lane chain root: {root} ({root_path.relative_to(REPO_ROOT)})")

if root_down == main_head:
    print(f"already parented on main head {main_head}: nothing to do")
    sys.exit(0)

if isinstance(root_down, (tuple, list)):
    sys.exit(
        f"error: root {root}'s down_revision is a merge revision {root_down} - "
        "refuse to auto-rewrite a merge revision, handle it manually."
    )

# --- 4. rewrite the root file's down_revision (and its docstring `Revises:`
# line, if present) to point at main's head. --------------------------------
text = root_path.read_text(encoding="utf-8")
assign_pattern = re.compile(
    r'^(down_revision\s*=\s*)(None|\'[^\']*\'|"[^"]*")(.*)$', re.MULTILINE,
)
m = assign_pattern.search(text)
if not m:
    sys.exit(
        f"error: could not find a simple `down_revision = ...` assignment line "
        f"in {root_path} to rewrite"
    )
old_literal = m.group(2)
quote = old_literal[0] if old_literal != "None" else '"'
new_text = (
    text[: m.start()]
    + m.group(1) + f"{quote}{main_head}{quote}" + m.group(3)
    + text[m.end():]
)

revises_pattern = re.compile(r'^(Revises:\s*)(\S+)(.*)$', re.MULTILINE)
new_text, n = revises_pattern.subn(
    lambda mm: mm.group(1) + main_head + mm.group(3), new_text, count=1,
)

root_path.write_text(new_text, encoding="utf-8")
old_display = old_literal if old_literal == "None" else old_literal[1:-1]
print(f"rewrote {root_path.relative_to(REPO_ROOT)}: down_revision {old_display} -> {main_head}"
      + (" (docstring Revises: line updated too)" if n else ""))

# --- 5. verify: main's graph plus the lane's new revisions (root now
# rewritten) has exactly one head. ------------------------------------------
local_graph[root] = main_head
combined = dict(main_graph)
combined.update({r: local_graph[r] for r in lane_new})
final_heads = heads_of(combined)
if len(final_heads) != 1:
    sys.exit(
        f"error: after rewriting, the combined graph still has "
        f"{len(final_heads)} head(s): {final_heads} - inspect the lane's "
        "migrations manually."
    )
print(f"single head after reparent: {final_heads[0]}")
PY
