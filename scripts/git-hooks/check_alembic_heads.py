"""Single-alembic-head check, shared by the repo pre-push hook and CI.

This is the exact ast-based logic `.github/workflows/deploy.yml`'s
`check-migration-heads` job runs, ported as-is (same encoding handling, same
ast walk) so the hook and CI can never quietly drift apart - only the INPUT
differs.

CI reads `sorento_crm_backend/alembic/versions/*.py` off a fresh checkout of
the branch under test. The hook can't do that (nothing has been pushed yet),
so it approximates "what CI will see after this merges" as the union of
origin/main's version files and the working tree's version files, with the
working tree winning for a path present in both - i.e. origin/main plus your
local edits/additions layered on top.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

VERSIONS_REL = "sorento_crm_backend/alembic/versions"


def _repo_root() -> pathlib.Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return pathlib.Path(out.stdout.strip())


def _origin_main_paths(repo_root: pathlib.Path) -> set[str]:
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "origin/main", "--", VERSIONS_REL],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return {p for p in out.stdout.splitlines() if p.endswith(".py")}


def _working_tree_paths(repo_root: pathlib.Path) -> set[str]:
    d = repo_root / VERSIONS_REL
    if not d.exists():
        return set()
    return {f"{VERSIONS_REL}/{p.name}" for p in d.glob("*.py")}


def _read_origin(repo_root: pathlib.Path, path: str) -> str:
    out = subprocess.run(
        ["git", "show", f"origin/main:{path}"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return out.stdout


def _read_working(repo_root: pathlib.Path, path: str) -> str:
    # encoding is explicit: ten migrations hold non-ASCII literals, and a
    # bare read_text() decodes with the runner's locale, which is ASCII
    # whenever LANG is unset. Mirrors the CI job's own comment verbatim.
    return (repo_root / path).read_text(encoding="utf-8")


def main() -> int:
    repo_root = _repo_root()
    origin_paths = _origin_main_paths(repo_root)
    wt_paths = _working_tree_paths(repo_root)
    all_paths = sorted(origin_paths | wt_paths)

    revs: set[str] = set()
    downs: set[str] = set()
    for path in all_paths:
        text = _read_working(repo_root, path) if path in wt_paths else _read_origin(repo_root, path)
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) \
                    and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            else:
                continue
            if name not in ("revision", "down_revision"):
                continue
            val = ast.literal_eval(value)
            if name == "revision":
                revs.add(val)
            elif val is not None:
                downs.update([val] if isinstance(val, str) else val)

    heads = sorted(revs - downs)
    print(f"{len(revs)} revisions, {len(heads)} head(s): {heads}")
    if len(heads) != 1:
        print(
            "the migration graph must have exactly one head: merge main "
            "and add a merge revision joining these heads",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
