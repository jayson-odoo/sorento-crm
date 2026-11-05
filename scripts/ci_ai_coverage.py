#!/usr/bin/env python3
"""AI-GATE: a new paged list route must be readable by the assistant, or say why not.

Plan: documentation/plans/chatbot/PLAN-ai-tools-standard-5nov.md section 2.5 (DoD line 6) and
PLAN-ai-gate-5nov.md. In one sentence: if a change ADDS a list screen's API (a GET route taking
`page` or `limit`) and neither registers it for the assistant (its "GET /api/v1/..." path is in some
`EntityDef(routes=...)` under app/services/assistant_registry/) nor marks it with

    # ai: not-for-assistant <reason>

on a comment line directly above its decorators, this check fails.

Diff-based, so there is no baseline file: a route counts as added when its method + full path is
served at HEAD and was not served at the base (the merge base with origin/main by default). An edit
to an existing route's body, signature or file therefore never triggers it.

Stdlib only and no import of the backend: full paths are worked out from the source by AST
(`APIRouter(prefix=...)`, `include_router(..., prefix=...)` chains up to `app.include_router` in
app/main.py), so it runs in the PR gate before any dependency install. A route whose mount chain
cannot be resolved statically is reported with what is known and must use the opt-out or be
registered by its file-local path.

Usage: python3 scripts/ci_ai_coverage.py [--base REF] [--head REF]
  --base  ref to diff against (default: merge base of HEAD and origin/main)
  --head  ref to check (default: the working tree)
Exit 0 = pass, 1 = uncovered routes, 2 = usage / git error.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = "sorento_crm_backend"
APP_DIR = f"{BACKEND}/app"
REGISTRY_DIR = f"{APP_DIR}/services/assistant_registry"
ROOT_MODULE = "app.main"
OPT_OUT_RE = re.compile(r"#\s*ai:\s*not-for-assistant\b(.*)$")
PAGED_PARAMS = {"page", "limit"}
ROUTE_STRING_RE = re.compile(r"^\s*GET\s+(/\S*)\s*$")


# --------------------------------------------------------------------------- source readers


class Tree:
    """Read .py files under app/ from the working tree or from a git ref."""

    def __init__(self, repo: Path, ref: str | None):
        self.repo = repo
        self.ref = ref
        self._files: dict[str, str] | None = None

    def files(self) -> dict[str, str]:
        if self._files is not None:
            return self._files
        out: dict[str, str] = {}
        if self.ref is None:
            base = self.repo / APP_DIR
            for p in base.rglob("*.py"):
                rel = p.relative_to(self.repo).as_posix()
                try:
                    out[rel] = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        else:
            listing = _git(self.repo, "ls-tree", "-r", "--name-only", self.ref, "--", APP_DIR)
            paths = [p for p in listing.splitlines() if p.endswith(".py")]
            out = _git_cat_many(self.repo, self.ref, paths)
        self._files = out
        return out


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if res.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def _git_cat_many(repo: Path, ref: str, paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    req = "".join(f"{ref}:{p}\n" for p in paths).encode()
    res = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input=req, capture_output=True)
    if res.returncode != 0:
        raise GitError(f"git cat-file: {res.stderr.decode(errors='replace').strip()}")
    data = res.stdout
    out: dict[str, str] = {}
    pos = 0
    for p in paths:
        nl = data.index(b"\n", pos)
        header = data[pos:nl].decode()
        pos = nl + 1
        if header.endswith(" missing"):
            continue
        size = int(header.split()[2])
        out[p] = data[pos : pos + size].decode("utf-8", errors="replace")
        pos += size + 1
    return out


class GitError(Exception):
    pass


# --------------------------------------------------------------------------- route graph


def module_name(rel_path: str) -> str:
    """sorento_crm_backend/app/api/v1/scm/__init__.py -> app.api.v1.scm"""
    p = rel_path[len(BACKEND) + 1 :] if rel_path.startswith(BACKEND + "/") else rel_path
    p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _eval_str(node: ast.AST | None, consts: dict[str, str]) -> str | None:
    """A string literal, a module constant, `+` of those, or an f-string over them; else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _eval_str(node.left, consts), _eval_str(node.right, consts)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                if v.format_spec is not None or v.conversion != -1:
                    return None
                v = v.value
            text = _eval_str(v, consts)
            if text is None:
                return None
            parts.append(text)
        return "".join(parts)
    return None


def _str_kw(call: ast.Call, name: str, consts: dict[str, str] | None = None) -> str | None:
    """A keyword's string value; "" when the keyword is absent, None when it cannot be worked out."""
    for kw in call.keywords:
        if kw.arg == name:
            return _eval_str(kw.value, consts or {})
    return ""


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


@dataclass
class Route:
    file: str
    line: int
    func: str
    router: tuple[str, str]  # (module, variable)
    path: str | None  # decorator path, router prefix not included; None = not worked out
    paged: bool
    opt_out: str | None  # None = no comment; "" = comment without a reason


@dataclass
class Graph:
    modules: set[str] = field(default_factory=set)
    # (module, var) -> APIRouter(prefix=...) ; None when the prefix is not a literal
    routers: dict[tuple[str, str], str | None] = field(default_factory=dict)
    # child (module, var) -> list of (parent (module, var), include prefix)
    mounts: dict[tuple[str, str], list[tuple[tuple[str, str], str | None]]] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)

    def full_paths(self, key: tuple[str, str], _seen: frozenset = frozenset()) -> set[str] | None:
        """Every full path prefix a router is served under, or None when unresolvable."""
        if key in _seen:
            return None
        own = self.routers.get(key, "")
        if own is None:
            return None
        if key == (ROOT_MODULE, "app"):
            return {""}
        result: set[str] = set()
        for parent, prefix in self.mounts.get(key, []):
            if prefix is None:
                continue
            parents = self.full_paths(parent, _seen | {key})
            if parents is None:
                continue
            result |= {pp + prefix + own for pp in parents}
        return result or None


def _resolve_import(graph_modules: set[str], current: str, is_pkg: bool, node: ast.ImportFrom) -> str | None:
    if node.level:
        parts = current.split(".")
        if not is_pkg:
            parts = parts[:-1]
        if node.level > 1:
            parts = parts[: len(parts) - (node.level - 1)]
        base = ".".join(parts)
        return f"{base}.{node.module}" if node.module else base
    return node.module


def _module_stmts(body: list[ast.stmt], into_defs: bool = False):
    """Statements through if / try / with blocks; into def and class bodies only with `into_defs`.

    Statement level only: walking every expression node of every file (ast.walk) took most of the
    gate's run time. Imports, routers and mounts sit at module level; route functions also sit in
    route factories (`def register_x_routes(router): @router.get(...)`), hence `into_defs`.
    """
    for node in body:
        yield node
        blocks = (ast.If, ast.Try, ast.With, ast.For)
        if into_defs:
            blocks = blocks + (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        if isinstance(node, blocks):
            for name in ("body", "orelse", "finalbody"):
                inner = getattr(node, name, None)
                if isinstance(inner, list):
                    yield from _module_stmts(inner, into_defs)
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                yield from _module_stmts(handler.body, into_defs)


def build_graph(files: dict[str, str]) -> Graph:
    g = Graph()
    g.modules = {module_name(p) for p in files}
    parsed: dict[str, tuple[str, ast.Module, list[str]]] = {}
    for rel, src in files.items():
        # Only files that can declare, mount, re-export or decorate with a router: parsing all
        # ~1.5k backend files twice took most of a minute.
        if "router" not in src.lower() and "FastAPI" not in src:
            continue
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError:
            continue
        parsed[rel] = (module_name(rel), tree, src.splitlines())

    # pass 0: module-level string constants (`BASE = "/stock-debt/snapshots"`, `PO = BASE + "/{id}"`)
    consts: dict[str, dict[str, str]] = {}
    for rel, (mod, tree, _lines) in parsed.items():
        table: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                value = _eval_str(node.value, table)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        if value is None:
                            table.pop(t.id, None)
                        else:
                            table[t.id] = value
        consts[mod] = table

    # pass 1: routers declared at module level
    for rel, (mod, tree, _lines) in parsed.items():
        for node in _module_stmts(tree.body):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                fn = _call_name(node.value.func)
                if fn not in ("APIRouter", "FastAPI"):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                prefix = _str_kw(node.value, "prefix", consts[mod]) if fn == "APIRouter" else ""
                for t in targets:
                    if isinstance(t, ast.Name):
                        g.routers[(mod, t.id)] = prefix
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # a router factory's own router, keyed "<function>()": every file must see it
                # before pass 3 resolves `include_router(build_x_router(...))` anywhere
                for inner in _module_stmts(node.body):
                    if (
                        isinstance(inner, ast.Assign)
                        and isinstance(inner.value, ast.Call)
                        and _call_name(inner.value.func) == "APIRouter"
                    ):
                        g.routers[(mod, f"{node.name}()")] = _str_kw(inner.value, "prefix", consts[mod])

    # pass 2: every file's import map, and re-exports (`from .x import router` in a package)
    imports: dict[str, dict[str, tuple]] = {}
    aliases: dict[tuple[str, str], tuple[str, str]] = {}
    for rel, (mod, tree, _lines) in parsed.items():
        is_pkg = rel.endswith("/__init__.py")
        # local name -> ("module", dotted) | ("attr", module, attr)
        names: dict[str, tuple] = {}
        for node in _module_stmts(tree.body):
            if isinstance(node, ast.ImportFrom):
                src_mod = _resolve_import(g.modules, mod, is_pkg, node)
                if not src_mod:
                    continue
                for a in node.names:
                    local = a.asname or a.name
                    sub = f"{src_mod}.{a.name}"
                    if sub in g.modules:
                        names[local] = ("module", sub)
                    else:
                        names[local] = ("attr", src_mod, a.name)
                        aliases[(mod, local)] = (src_mod, a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        names[a.asname] = ("module", a.name)
        imports[rel] = names

    def canon(key: tuple[str, str]) -> tuple[str, str]:
        for _ in range(8):
            if key in g.routers or key not in aliases:
                return key
            key = aliases[key]
        return key

    # Module-level functions and their parameter names, for route factories:
    # `def register_x_routes(router, ...): @router.get(...)` called as `register_x_routes(some_router)`,
    # and `def build_x_router(): router = APIRouter(); @router.get(...); return router`.
    params: dict[tuple[str, str], list[str]] = {}
    for rel, (mod, tree, _lines) in parsed.items():
        for node in _module_stmts(tree.body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                params[(mod, node.name)] = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]

    def func_key(names: dict[str, tuple], mod: str, expr: ast.AST) -> tuple[str, str] | None:
        key: tuple[str, str] | None = None
        if isinstance(expr, ast.Name):
            if (mod, expr.id) in params:
                return (mod, expr.id)
            ref = names.get(expr.id)
            if ref and ref[0] == "attr":
                key = (ref[1], ref[2])
        elif isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            ref = names.get(expr.value.id)
            if ref and ref[0] == "module":
                key = (ref[1], expr.attr)
        for _ in range(8):
            if key is None or key in params or key not in aliases:
                break
            key = aliases[key]
        return key if key in params else None

    # factory (module, function) -> [(parameter name, Route without its router)]
    factory_routes: dict[tuple[str, str], list[tuple[str, Route]]] = {}
    # factory -> [(its parameter name, inner factory, inner parameter name)]
    factory_calls: dict[tuple[str, str], list[tuple[str, tuple[str, str], str]]] = {}
    # (factory, parameter name, router key the caller passed)
    applications: list[tuple[tuple[str, str], str, tuple[str, str]]] = []

    def call_bindings(fkey: tuple[str, str], call: ast.Call) -> list[tuple[str, ast.AST]]:
        names_ = params[fkey]
        out = [(names_[i], arg) for i, arg in enumerate(call.args) if i < len(names_)]
        out += [(kw.arg, kw.value) for kw in call.keywords if kw.arg]
        return out

    # pass 3: include_router calls, factory calls and GET routes
    for rel, (mod, tree, lines) in parsed.items():
        names = imports[rel]
        call_assigns: dict[str, ast.Call] = {}
        for node in _module_stmts(tree.body):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                for t in node.targets:
                    if isinstance(t, ast.Name) and (mod, t.id) not in g.routers:
                        call_assigns[t.id] = node.value

        def router_key(expr: ast.AST, depth: int = 0) -> tuple[str, str] | None:
            if isinstance(expr, ast.Call):
                fkey = func_key(names, mod, expr.func)
                if fkey and (fkey[0], f"{fkey[1]}()") in g.routers:
                    return (fkey[0], f"{fkey[1]}()")
                return None
            if isinstance(expr, ast.Name):
                if (mod, expr.id) in g.routers:
                    return (mod, expr.id)
                if expr.id in call_assigns and depth < 4:
                    return router_key(call_assigns[expr.id], depth + 1)
                ref = names.get(expr.id)
                if ref and ref[0] == "attr":
                    return canon((ref[1], ref[2]))
                return None
            if isinstance(expr, ast.Attribute):
                # pkg.sub.router: walk down to the Name, then up through sub-modules
                chain: list[str] = []
                cur: ast.AST = expr
                while isinstance(cur, ast.Attribute):
                    chain.append(cur.attr)
                    cur = cur.value
                if not isinstance(cur, ast.Name):
                    return None
                ref = names.get(cur.id)
                if not ref or ref[0] != "module":
                    return None
                chain.reverse()
                target = ref[1]
                for part in chain[:-1]:
                    target = f"{target}.{part}"
                return canon((target, chain[-1]))
            return None

        # routers built inside a factory: `def build_x(): router = APIRouter(...)`
        local_routers: dict[str, dict[str, tuple[str, str]]] = {}
        for fn in _module_stmts(tree.body):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in _module_stmts(fn.body):
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and _call_name(node.value.func) == "APIRouter"
                ):
                    key = (mod, f"{fn.name}()")
                    g.routers[key] = _str_kw(node.value, "prefix", consts[mod])
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            local_routers.setdefault(fn.name, {})[t.id] = key

        for stmt in _module_stmts(tree.body):
            node = stmt.value if isinstance(stmt, ast.Expr) else None
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "include_router" and node.args:
                parent = router_key(node.func.value)
                child = router_key(node.args[0])
                if parent and child:
                    g.mounts.setdefault(child, []).append((parent, _str_kw(node, "prefix", consts[mod])))
                continue
            fkey = func_key(names, mod, node.func)
            if fkey:
                for pname, arg in call_bindings(fkey, node):
                    rkey = router_key(arg)
                    if rkey and rkey in g.routers:
                        applications.append((fkey, pname, rkey))

        def walk_defs(body: list[ast.stmt], enclosing: ast.AST | None):
            for node in _module_stmts(body):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield node, enclosing
                    yield from walk_defs(node.body, node if enclosing is None else enclosing)
                elif isinstance(node, ast.ClassDef):
                    yield from walk_defs(node.body, enclosing)

        for node, factory in walk_defs(tree.body, None):
            fparams = params.get((mod, factory.name), []) if factory is not None else []
            local = local_routers.get(factory.name, {}) if factory is not None else {}
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "get"
                ):
                    continue
                base = dec.func.value
                if dec.args:
                    path = _eval_str(dec.args[0], consts[mod])
                else:
                    path = _str_kw(dec, "path", consts[mod])
                all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                first_line = min([d.lineno for d in node.decorator_list] + [node.lineno])
                route = Route(
                    file=rel,
                    line=dec.lineno,
                    func=node.name,
                    router=("", ""),
                    path=path,
                    paged=any(a.arg in PAGED_PARAMS for a in all_args),
                    opt_out=_opt_out_above(lines, first_line),
                )
                if isinstance(base, ast.Name) and base.id in local:
                    route.router = local[base.id]
                elif isinstance(base, ast.Name) and base.id in fparams:
                    factory_routes.setdefault((mod, factory.name), []).append((base.id, route))
                    continue
                else:
                    rkey = router_key(base)
                    if rkey is None or rkey not in g.routers:
                        continue  # not an APIRouter / FastAPI object declared under app/
                    route.router = rkey
                g.routes.append(route)

        # factories that pass their router parameter to another factory
        for fn in _module_stmts(tree.body):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fparams = params.get((mod, fn.name), [])
            for stmt in _module_stmts(fn.body):
                node = stmt.value if isinstance(stmt, ast.Expr) else None
                if not isinstance(node, ast.Call):
                    continue
                inner = func_key(names, mod, node.func)
                if not inner:
                    continue
                for pname, arg in call_bindings(inner, node):
                    if isinstance(arg, ast.Name) and arg.id in fparams:
                        factory_calls.setdefault((mod, fn.name), []).append((arg.id, inner, pname))

    # pass 4: instantiate factory routes on the routers their callers passed
    def apply(fkey: tuple[str, str], pname: str, rkey: tuple[str, str], depth: int = 0) -> None:
        if depth > 6:
            return
        for p, route in factory_routes.get(fkey, []):
            if p == pname:
                g.routes.append(Route(**{**route.__dict__, "router": rkey}))
        for p, inner, inner_p in factory_calls.get(fkey, []):
            if p == pname:
                apply(inner, inner_p, rkey, depth + 1)

    for fkey, pname, rkey in applications:
        apply(fkey, pname, rkey)
    return g


def _opt_out_above(lines: list[str], first_line: int) -> str | None:
    """The opt-out reason from the comment block directly above the decorators (1-based line)."""
    i = first_line - 2
    while i >= 0:
        text = lines[i].strip()
        if not text.startswith("#"):
            break
        m = OPT_OUT_RE.search(text)
        if m:
            return m.group(1).strip(" :-")
        i -= 1
    return None


def normalize(path: str) -> str:
    path = re.sub(r"\{[^}]*\}", "{}", path.strip())
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def route_keys(g: Graph, r: Route) -> set[str]:
    if r.path is None:
        # a path the AST cannot evaluate: keyed by function, so an edit still matches the base
        return {f"?{module_name(r.file)}.{r.func}"}
    full = g.full_paths(r.router)
    if full is None:
        prefix = g.routers.get(r.router) or ""
        return {f"?{r.router[0]}:{normalize(prefix + r.path)}"}
    return {normalize(p + r.path) for p in full}


# --------------------------------------------------------------------------- registry


def registered_routes(files: dict[str, str]) -> set[str]:
    """Every "GET /api/v1/..." string inside an EntityDef(...) call, path normalized."""
    out: set[str] = set()
    for rel, src in files.items():
        if not rel.startswith(REGISTRY_DIR + "/"):
            continue
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node.func) == "EntityDef":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        m = ROUTE_STRING_RE.match(sub.value)
                        if m:
                            out.add(normalize(m.group(1)))
    return out


# --------------------------------------------------------------------------- the check


@dataclass
class Finding:
    route: Route
    keys: set[str]
    problem: str


def check(head_files: dict[str, str], base_files: dict[str, str]) -> tuple[list[Finding], int]:
    head = build_graph(head_files)
    base = build_graph(base_files)
    base_keys: set[str] = set()
    for r in base.routes:
        base_keys |= route_keys(base, r)
    registry = registered_routes(head_files)

    findings: list[Finding] = []
    added = 0
    for r in head.routes:
        if not r.paged:
            continue
        keys = route_keys(head, r)
        if keys & base_keys:
            continue  # served before this change: an edit, a move or a re-mount, not a new list
        added += 1
        if r.opt_out is not None:
            if not r.opt_out:
                findings.append(Finding(r, keys, "opt-out comment has no reason"))
            continue
        if keys & registry:
            continue
        findings.append(Finding(r, keys, "not registered for the assistant"))
    return findings, added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="ref to diff against (default: merge base of HEAD and origin/main)")
    ap.add_argument("--head", help="ref to check (default: the working tree)")
    ap.add_argument("--repo", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    repo = Path(args.repo or os.getcwd())
    try:
        repo = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
        base_ref = args.base or _git(repo, "merge-base", "HEAD", "origin/main").strip()
        base_ref = _git(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}").strip()
        findings, added = check(Tree(repo, args.head).files(), Tree(repo, base_ref).files())
    except GitError as exc:
        print(f"ai-coverage: {exc}", file=sys.stderr)
        return 2

    if not findings:
        print(f"ai-coverage: ok ({added} new paged list route(s) since {base_ref[:12]}, all covered)")
        return 0
    print(f"ai-coverage: {len(findings)} new paged list route(s) the assistant cannot read:")
    for f in findings:
        shown = ", ".join(sorted(f.keys))
        print(f"  {f.route.file}:{f.route.line} {f.route.func}  GET {shown}  ({f.problem})")
        print(
            f"::error file={f.route.file},line={f.route.line},title=AI coverage::"
            f"GET {shown}: {f.problem}"
        )
    print(
        "\nFix one of two ways (PRINCIPLES.md DoD line 6):\n"
        "  1. register the entity in sorento_crm_backend/app/services/assistant_registry/<module>.py\n"
        '     with routes=("GET /api/v1/<full path>",), fields = what the screen shows; or\n'
        "  2. put this comment line directly above the route's decorators:\n"
        "     # ai: not-for-assistant <why the assistant should not read this list>"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
