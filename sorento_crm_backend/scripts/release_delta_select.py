"""Pick the tests a release delta runs: only the affected ones (RELEASE-DELTA-AFFECTED, 5 Nov 2026).

Owner ruling, 5 Nov 2026: "the key is to run only the tests that are affected, dependent, or
depended by". Run by scripts/release-delta.sh on the diff between the last green nightly and the
release head; documented in documentation/agents/cloud-lanes.md "Nightly sweep + release delta".

BACKEND IMPORT GRAPH. Nodes are the `.py` files under the backend's `app/`, `scripts/` and
`tests/`. A file's edges are the modules it loads, of two kinds:
  - module-level: an `import` / `from ... import` statement that runs when the file is imported
    (at the top, or inside a module-level `if` / `try` / class body);
  - lazy: an import inside a function, and, in files under `tests/` only, a dotted
    `app.x.y` / `scripts.x` / `tests.x` in a string literal (a `mock.patch` /
    `monkeypatch.setattr` target).
Resolution: relative imports against the file's package; `from pkg import name` points at
`pkg.name` when that is a module, else at the module `pkg/__init__.py` re-exports `name` from
(`from app.models import User` -> app/models/user.py), else at `pkg`; any other dotted name at
its longest prefix that is a module. Importing `a.b.c` adds no edge to the packages `a`, `a.b`.

Why two kinds (measured on 42d1a56c..019770c1, 5 Nov 2026): the full transitive closure of
every import reaches ~95% of the test files from almost any change, because function-local
imports (there to break cycles) tie the services into one component (po_link_history.py <-
document_ingest_service <- procurement_service <- form_actions <- task_scheduler <-
user_service <- every test of a user). Following lazy edges one hop only, that diff selects
1,499 test files, 1,319 of them because app/main.py imports the ingest router at module level
and document_ingest_service imports po_link_history inside a function.

SELECTION. A changed path selects (backend-relative; all rules together):
  1. itself, when it is a test file (`tests/**/test_*.py`);
  2. dependents: let R be the changed modules closed under module-level importers
     (transitively: B imports A at module level and A is in R, so B is in R), plus every module
     with a lazy edge into R (one hop, not propagated further); select every test file that is
     in R or has an edge of either kind into R. A lazy import is what one function needs when it
     is called, so its importer's own tests cover it; following it on through every
     module-level importer reaches app/main.py and with it every API test (measured below);
  3. depended-by, "the tests of what the change calls": for a changed non-test module M and each
     module D that M imports directly (either kind), the test files named `test_<D>.py` or
     `test_<D>_*.py` (D's last dotted name) that import D directly. Applied to every direct
     import, not only those whose call the diff touches: a call-contract change cannot be told
     apart statically, and the named tests of a direct callee are few;
  4. a changed file that is not a module (alembic revision, template, json, shell script,
     workflow, frontend file): every test file whose text names it (its basename; a frontend file
     by its path under sorento_crm_frontend/) is selected and counts as changed; a non-test module
     that names a changed file under sorento_crm_backend/app/ (a template, a data file) counts as
     changed too. A non-test module naming a frontend, workflow or root file is a parity comment,
     not a load, and does not count;
  5. a module the head deleted: every test file whose text names its dotted path;
  6. `tests/test_migration_*.py` (all of them) only when `alembic/`, `alembic.ini` or
     `app/models/` changed; any one the graph selects runs too;
  7. `tests/test_lessons_learnt_regressions.py` (the source-scanning regression guards) whenever
     any backend path changed.
A test file counts as importing, at module level, every conftest.py in its directory and above
(pytest imports them first), so a module a conftest loads reaches the tests under it. A changed
package `__init__.py` counts as a change to every module of that package (Python runs it before
any of them). `tests/scm/` is selected only through these rules, like any other directory.
`tests/ci_excluded.txt` entries never run, nor do `tests/nightly_only.txt` entries (the
reorder-planning tests; the nightly full sweep runs them, CI-PARALLEL-ACTIONS 5 Nov 2026).

FULL backend suite (every test file) instead, with the reason printed, when the diff changes:
any conftest.py; test infrastructure (`tests/__init__.py`, `tests/_xdist_crash_guard.py`,
`tests/ci_excluded.txt`); pytest / dependency config (`pytest.ini`, `pyproject.toml`,
`setup.cfg`, `requirements*.txt`); env bootstrap (`scripts/bootstrap_env.py` of the backend,
`scripts/cloud-env-setup.sh` of the repo); or when the graph cannot be built (a file does not
parse).

FRONTEND. `vitest related --run <changed frontend files that exist at head, and the test files
that still name a deleted one>` plus the
source-scanning guards (sorento_crm_frontend/scripts/source-guard-tests.sh) when a frontend file
changed. FULL `vitest run` when shared config or test setup changed: `package.json`,
`package-lock.json`, `vitest.config.*`, `vitest.setup.*`, `tsconfig*.json`, `test-mocks/`,
`__mocks__/`.

The graph is cached as JSON per backend tree sha (`--cache-dir`); a parse is ~25 s.

CLI:
  release_delta_select.py --base <sha> --head <sha> --out <dir> [--backend <dir>] [--cache-dir <dir>]
  release_delta_select.py --changed-from - --out <dir>      (changed repo paths on stdin)
Writes <out>/selected.txt (backend test files, backend-relative), <out>/selected_why.txt (each
with the rule that picked it) and <out>/vitest_related.txt (frontend-relative paths), and prints
key=value lines: backend=full|selected|none, backend_reason, backend_selected, backend_total,
backend_scm, migrations=true|false, vitest=full|related|none, vitest_reason, graph=built|cache.
Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_PREFIX = "sorento_crm_backend/"
FRONTEND_PREFIX = "sorento_crm_frontend/"
SOURCE_DIRS = ("app", "scripts", "tests")
# Bump when the edge rules in file_edges change: the cache key is the tree sha only.
GRAPH_VERSION = 4
SAFE_TEST_RE = re.compile(r"^tests/([A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]*\.py$")
DOTTED_RE = re.compile(r"(?<![\w.])((?:app|scripts|tests)(?:\.[A-Za-z_]\w*)+)")
MIGRATION_TEST_RE = re.compile(r"^tests/test_migration_[A-Za-z0-9_.-]*\.py$")
REGRESSION_GUARDS = "tests/test_lessons_learnt_regressions.py"

# Repo paths whose change runs the whole backend suite, with the reason printed.
BACKEND_FULL = [
    (re.compile(r"^sorento_crm_backend/(.+/)?conftest\.py$"), "a conftest.py changed"),
    (re.compile(r"^sorento_crm_backend/tests/(__init__\.py|_xdist_crash_guard\.py|ci_excluded\.txt)$"),
     "test infrastructure changed"),
    (re.compile(r"^sorento_crm_backend/(pytest\.ini|pyproject\.toml|setup\.cfg|requirements[^/]*\.txt)$"),
     "pytest / dependency config changed"),
    (re.compile(r"^(sorento_crm_backend/scripts/bootstrap_env\.py|scripts/cloud-env-setup\.sh)$"),
     "env bootstrap changed"),
]
FRONTEND_FULL = re.compile(
    r"^sorento_crm_frontend/(package\.json|package-lock\.json|vitest\.config\.[a-z]+|vitest\.setup\.[a-z]+"
    r"|tsconfig[^/]*\.json|test-mocks/.*|(.+/)?__mocks__/.*)$"
)
MIGRATION_TRIGGER = re.compile(r"^sorento_crm_backend/(alembic/|alembic\.ini$|app/models/)")


class GraphError(Exception):
    pass


# --- graph ---------------------------------------------------------------------------------

def module_name(rel: str) -> str | None:
    """`app/services/foo.py` -> `app.services.foo`; a package's __init__ -> the package."""
    if not rel.endswith(".py"):
        return None
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return ".".join(parts)


def is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") and Path(rel).name.startswith("test_") and rel.endswith(".py")


def source_files(root: Path) -> dict[str, str]:
    """backend-relative path -> text, for every .py under app/, scripts/, tests/."""
    out: dict[str, str] = {}
    for top in SOURCE_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if "/__pycache__/" in rel or module_name(rel) is None:
                continue
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _resolve(name: str, modules: dict[str, str]) -> str | None:
    """The longest prefix of `name` that is a module of the tree, as its path."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        rel = modules.get(".".join(parts[:i]))
        if rel:
            return rel
    return None


def _imports(tree: ast.Module) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Every import node with True when it runs at module import time."""
    out: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def visit(node: ast.AST, top: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                out.append((child, top))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                visit(child, False)
            else:
                visit(child, top)

    visit(tree, True)
    return out


def _parse(rel: str, text: str) -> ast.Module:
    try:
        return ast.parse(text, filename=rel)
    except SyntaxError as exc:
        raise GraphError(f"{rel} does not parse: {exc.msg} (line {exc.lineno})") from exc


def _package(rel: str) -> list[str]:
    package = (module_name(rel) or "").split(".")
    return package if rel.endswith("__init__.py") else package[:-1]


def _from_base(node: ast.ImportFrom, package: list[str]) -> str:
    if not node.level:
        return node.module or ""
    keep = len(package) - (node.level - 1)
    if keep < 0:
        return ""
    return ".".join(package[:keep] + ([node.module] if node.module else []))


def reexports(sources: dict[str, str], modules: dict[str, str]) -> dict[str, dict[str, str]]:
    """package __init__ path -> {name it re-exports: path of the module the name comes from}."""
    out: dict[str, dict[str, str]] = {}
    for rel, text in sources.items():
        if not rel.endswith("__init__.py"):
            continue
        names: dict[str, str] = {}
        for node, top in _imports(_parse(rel, text)):
            if not top or not isinstance(node, ast.ImportFrom):
                continue
            base = _from_base(node, _package(rel))
            for alias in node.names:
                if alias.name == "*" or not base:
                    continue
                target = modules.get(f"{base}.{alias.name}") or _resolve(base, modules)
                if target and target != rel:
                    names[alias.asname or alias.name] = target
        out[rel] = names
    return out


def file_edges(rel: str, text: str, modules: dict[str, str],
               exports: dict[str, dict[str, str]] | None = None) -> tuple[set[str], set[str]]:
    """(module-level edges, lazy edges) of `rel`, as paths (see the module docstring)."""
    exports = exports or {}
    tree = _parse(rel, text)
    package = _package(rel)
    top: set[str] = set()
    lazy: set[str] = set()

    def add(name: str, at_top: bool) -> None:
        target = _resolve(name, modules)
        if target and target != rel:
            (top if at_top else lazy).add(target)

    for node, at_top in _imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, at_top)
            continue
        base = _from_base(node, package)
        if not base:
            continue
        for alias in node.names:
            if alias.name != "*" and f"{base}.{alias.name}" in modules:
                add(f"{base}.{alias.name}", at_top)
                continue
            pkg = modules.get(base)
            via = exports.get(pkg, {}).get(alias.name) if pkg else None
            if via and via != rel:
                (top if at_top else lazy).add(via)
            else:
                add(base, at_top)
    if rel.startswith("tests/"):
        # String literals only: the regex over the raw text would also read the import lines.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for name in DOTTED_RE.findall(node.value):
                    add(name, False)
    return top, lazy - top


def build_graph(sources: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    modules = {module_name(rel): rel for rel in sources}
    exports = reexports(sources, modules)
    graph: dict[str, dict[str, list[str]]] = {}
    for rel, text in sources.items():
        top, lazy = file_edges(rel, text, modules, exports)
        graph[rel] = {"top": sorted(top), "lazy": sorted(lazy)}
    return graph


def tree_sha(repo: Path, head: str | None, backend_rel: str) -> str | None:
    if not head:
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", f"{head}:{backend_rel.rstrip('/')}"],
            text=True, stderr=subprocess.DEVNULL).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def load_graph(sources: dict[str, str], cache_dir: Path | None, key: str | None
               ) -> tuple[dict[str, dict[str, list[str]]], str]:
    """The graph and where it came from ("cache" or "built")."""
    cache = cache_dir / f"graph-v{GRAPH_VERSION}-{key}.json" if cache_dir and key else None
    if cache and cache.is_file():
        try:
            graph = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(graph, dict) and set(graph) == set(sources):
                return graph, "cache"
        except (OSError, ValueError):
            pass
    graph = build_graph(sources)
    if cache:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(graph), encoding="utf-8")
            tmp.replace(cache)
        except OSError:
            pass
    return graph, "built"


# --- selection -----------------------------------------------------------------------------

@dataclass
class Result:
    backend: str = "none"  # full | selected | none
    backend_reason: str = "no backend change"
    tests: list[str] = field(default_factory=list)  # backend-relative
    total: int = 0
    migrations: bool = False
    vitest: str = "none"  # full | related | none
    vitest_reason: str = "no frontend change"
    vitest_files: list[str] = field(default_factory=list)  # frontend-relative
    why: dict[str, str] = field(default_factory=dict)  # test -> the rule that picked it
    graph_source: str = ""


def _path_list(root: Path, name: str) -> set[str]:
    try:
        lines = (root / "tests" / name).read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def _excluded(root: Path) -> set[str]:
    return _path_list(root, "ci_excluded.txt")


def nightly_only(root: Path) -> set[str]:
    """tests/nightly_only.txt: the nightly full sweep runs these, a release delta never does."""
    return _path_list(root, "nightly_only.txt")


def _frontend(changed: list[str], fe_root: Path, res: Result) -> None:
    fe_changed = [p for p in changed if p.startswith(FRONTEND_PREFIX)]
    if not fe_changed:
        return
    full_hit = next((p for p in fe_changed if FRONTEND_FULL.match(p)), None)
    if full_hit:
        res.vitest, res.vitest_reason = "full", f"shared config / test setup changed: {full_hit}"
        return
    rels = [p[len(FRONTEND_PREFIX):] for p in fe_changed]
    present = [r for r in rels if (fe_root / r).is_file()]
    deleted = [r for r in rels if r not in present]
    # `vitest related` cannot follow a deleted file: the test files that still name it (an import
    # path ending in its name without the extension) run directly.
    importers: list[str] = []
    stems = {Path(r).with_suffix("").name for r in deleted if re.search(r"\.[cm]?[jt]sx?$", r)}
    if stems:
        rx = re.compile(r"""[/'"](%s)['"]""" % "|".join(re.escape(x) for x in sorted(stems)))
        for dirpath, dirnames, filenames in os.walk(fe_root):
            # Pruned, not filtered: node_modules alone is tens of thousands of directories.
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".next", "e2e", ".git")]
            for name in filenames:
                if ".test." not in name:
                    continue
                path = Path(dirpath) / name
                if rx.search(path.read_text(encoding="utf-8", errors="replace")):
                    importers.append(path.relative_to(fe_root).as_posix())
    res.vitest_files = sorted(set(present) | set(importers))
    res.vitest = "related"
    res.vitest_reason = (f"vitest related on {len(present)} changed frontend files, "
                         f"{len(deleted)} deleted ({len(importers)} tests still name one) + source guards")


def select(changed: list[str], root: Path, *, frontend: Path | None = None, cache_dir: Path | None = None,
           cache_key: str | None = None) -> Result:
    """`changed` are repo-relative paths; `root` is the backend directory at the head."""
    res = Result()
    changed = sorted({p.strip() for p in changed if p.strip()})
    _frontend(changed, frontend or root.parent / FRONTEND_PREFIX.rstrip("/"), res)

    # A nightly-only test (CI-PARALLEL-ACTIONS) is never selected, even on a full fallback.
    excluded = _excluded(root) | nightly_only(root)
    sources = source_files(root)
    all_tests = sorted(r for r in sources if SAFE_TEST_RE.match(r) and r not in excluded)
    res.total = len(all_tests)
    be_changed = [p[len(BACKEND_PREFIX):] for p in changed if p.startswith(BACKEND_PREFIX)]
    res.migrations = any(MIGRATION_TRIGGER.match(p) for p in changed)
    full_reason = next((f"{why}: {p}" for p in changed for rx, why in BACKEND_FULL if rx.match(p)), None)
    graph: dict[str, dict[str, list[str]]] = {}
    if not full_reason:
        try:
            graph, res.graph_source = load_graph(sources, cache_dir, cache_key)
        except GraphError as exc:
            full_reason = f"import graph build failed: {exc}"
    if full_reason:
        res.backend, res.backend_reason, res.tests = "full", full_reason, list(all_tests)
        res.why = {t: "full" for t in all_tests}
        res.migrations = True
        return res

    picked: dict[str, str] = {}

    def pick(test: str, why: str) -> None:
        if SAFE_TEST_RE.match(test) and test not in excluded and test in sources:
            picked.setdefault(test, why)

    changed_mods: set[str] = set()
    for rel in be_changed:
        if rel in sources:
            if is_test_file(rel):
                pick(rel, "changed")
            changed_mods.add(rel)
            if rel.endswith("/__init__.py"):
                # Importing any module of a package runs its __init__ first, and the graph has
                # no parent-package edges: a changed __init__ counts as a change to every module
                # of the package.
                pkg_dir = rel[: -len("__init__.py")]
                changed_mods.update(r for r in sources if r.startswith(pkg_dir))
        elif rel.endswith(".py") and rel.split("/", 1)[0] in SOURCE_DIRS and module_name(rel):
            # Rule 5: a deleted module; a test may still name it in a patch target.
            dotted = re.compile(rf"(?<![\w.]){re.escape(module_name(rel) or '')}(?!\w)")
            for t in all_tests:
                if dotted.search(sources[t]):
                    pick(t, f"names deleted {rel}")

    # Rule 4: changed non-module files. A substring test first (one regex alternation over every
    # file took minutes, measured), then the boundary check on the hits only.
    names: dict[str, str] = {}
    for p in changed:
        if p.startswith(BACKEND_PREFIX) and p[len(BACKEND_PREFIX):] in sources:
            continue
        if p.startswith(FRONTEND_PREFIX):
            names[p[len(FRONTEND_PREFIX):]] = p
        elif not p.endswith(".md"):
            names[Path(p).name] = p
    bounded = {n: re.compile(rf"(?<![\w.-]){re.escape(n)}(?![\w-])") for n in names}
    for rel, text in sources.items():
        own = is_test_file(rel)
        hit = next((n for n, rx in bounded.items()
                    if (own or names[n].startswith(BACKEND_PREFIX + "app/")) and n in text and rx.search(text)),
                   None)
        if hit:
            changed_mods.add(rel)
            if own:
                pick(rel, f"names {names[hit]}")

    # Rule 2: dependents.
    importers_top: dict[str, set[str]] = {}
    importers_any: dict[str, set[str]] = {}
    for src, edges in graph.items():
        for t in edges["top"]:
            importers_top.setdefault(t, set()).add(src)
            importers_any.setdefault(t, set()).add(src)
        for t in edges["lazy"]:
            importers_any.setdefault(t, set()).add(src)
    # pytest imports every conftest.py above a test file before the test: a module-level edge.
    for t in all_tests:
        parts = t.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            conftest = "/".join(parts[:i]) + "/conftest.py"
            if conftest in sources:
                importers_top.setdefault(conftest, set()).add(t)
                importers_any.setdefault(conftest, set()).add(t)
    # Module-level importers first, transitively; then one lazy hop, which does not propagate.
    origin: dict[str, str] = {m: m for m in sorted(changed_mods)}
    queue = deque(sorted(origin))
    while queue:
        cur = queue.popleft()
        for imp in sorted(importers_top.get(cur, ())):
            if imp not in origin:
                origin[imp] = origin[cur]
                queue.append(imp)
    for mod in sorted(origin):
        for imp in sorted(importers_any.get(mod, ())):
            origin.setdefault(imp, origin[mod])
    for mod in sorted(origin):
        for t in [mod, *sorted(importers_any.get(mod, ()))]:
            if is_test_file(t):
                pick(t, "changed" if t in changed_mods else f"imports {origin[mod]}")

    # Rule 3: depended-by, the tests of each direct import of a changed non-test module.
    tests_by_stem: dict[str, list[str]] = {}
    for t in all_tests:
        tests_by_stem.setdefault(Path(t).stem[len("test_"):], []).append(t)
    for rel in sorted(changed_mods):
        if is_test_file(rel) or rel not in graph:
            continue
        for dep in graph[rel]["top"] + graph[rel]["lazy"]:
            if is_test_file(dep):
                continue
            last = (module_name(dep) or "").rsplit(".", 1)[-1]
            for stem, tests in tests_by_stem.items():
                if stem == last or stem.startswith(last + "_"):
                    for t in tests:
                        edges = graph.get(t, {"top": [], "lazy": []})
                        if dep in edges["top"] or dep in edges["lazy"]:
                            pick(t, f"tests {dep}, called by {rel}")

    # Rules 6 and 7.
    if res.migrations:
        for t in all_tests:
            if MIGRATION_TEST_RE.match(t):
                pick(t, "migration test (alembic/ or app/models/ changed)")
    if be_changed:
        pick(REGRESSION_GUARDS, "regression guards (backend changed)")

    res.tests = sorted(picked)
    res.why = picked
    if res.tests:
        res.backend = "selected"
        res.backend_reason = (f"affected by {len(changed_mods)} changed modules "
                              f"({len(be_changed)} changed backend paths)" if changed_mods else
                              f"no test file reaches the {len(be_changed)} changed backend paths; regression guards only")
    elif be_changed:
        res.backend_reason = "no test file reaches the change"
    return res


# --- CLI -----------------------------------------------------------------------------------

def git_changed(repo: Path, base: str, head: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--name-only", "--no-renames", base, head], text=True)
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--changed-from", help="'-' reads the changed repo paths from stdin")
    parser.add_argument("--backend", default=None, help="backend dir (default: next to this script)")
    parser.add_argument("--cache-dir", default=os.environ.get(
        "RELEASE_DELTA_GRAPH_CACHE", str(Path.home() / ".cache" / "sorento-release-delta")))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.backend) if args.backend else Path(__file__).resolve().parents[1]
    repo = root.resolve().parent
    if args.changed_from:
        changed = [line.strip() for line in sys.stdin if line.strip()]
    elif args.base and args.head:
        changed = git_changed(repo, args.base, args.head)
    else:
        parser.error("give --base and --head, or --changed-from -")
    key = tree_sha(repo, args.head, BACKEND_PREFIX)
    res = select(changed, root, cache_dir=Path(args.cache_dir) if args.cache_dir else None, cache_key=key)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "selected.txt").write_text("".join(f"{t}\n" for t in res.tests), encoding="utf-8")
    (out / "selected_why.txt").write_text("".join(f"{t}\t{res.why[t]}\n" for t in res.tests), encoding="utf-8")
    (out / "vitest_related.txt").write_text("".join(f"{f}\n" for f in res.vitest_files), encoding="utf-8")
    print(f"backend={res.backend}")
    print(f"backend_reason={res.backend_reason}")
    print(f"backend_selected={len(res.tests)}")
    print(f"backend_total={res.total}")
    print(f"backend_scm={sum(1 for t in res.tests if t.startswith('tests/scm/'))}")
    print(f"migrations={'true' if res.migrations else 'false'}")
    print(f"vitest={res.vitest}")
    print(f"vitest_reason={res.vitest_reason}")
    print(f"graph={res.graph_source or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
