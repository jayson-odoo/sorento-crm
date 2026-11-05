"""AI-GATE: scripts/ci_ai_coverage.py (PLAN-ai-gate-5nov.md, PLAN-ai-tools-standard-5nov.md 2.5).

A PR that ADDS a paged list GET (takes `page` or `limit`) fails unless the route's full
"GET /api/v1/..." path is in an `EntityDef(routes=...)` under app/services/assistant_registry/, or
a `# ai: not-for-assistant <reason>` comment sits directly above its decorators. UAC AC-7.

The script lives at repo-root `scripts/`; it is loaded by path. Each test builds a throwaway git
repo with a tiny fake backend tree, commits a base, changes it, and runs the gate against the base.
No database, no network.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "ci_ai_coverage.py"
_MOD_NAME = "ci_ai_coverage_test"


def _load():
    if _MOD_NAME in sys.modules:
        return sys.modules[_MOD_NAME]
    spec = importlib.util.spec_from_file_location(_MOD_NAME, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MOD_NAME] = module  # before exec, so @dataclass resolves __module__
    spec.loader.exec_module(module)
    return module


BASE_FILES = {
    "sorento_crm_backend/app/__init__.py": "",
    "sorento_crm_backend/app/main.py": """
        from fastapi import FastAPI
        from app.api.v1 import api_router

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
    """,
    "sorento_crm_backend/app/api/__init__.py": "",
    "sorento_crm_backend/app/api/v1/__init__.py": """
        from fastapi import APIRouter
        from app.api.v1 import widgets

        api_router = APIRouter()
        api_router.include_router(widgets.router, prefix="/widgets")
    """,
    # a package that re-exports its router, like app/api/v1/downloads/__init__.py
    "sorento_crm_backend/app/api/v1/widgets/__init__.py": """
        from fastapi import APIRouter
        from app.api.v1.widgets import parts

        router = APIRouter()
        router.include_router(parts.router)
    """,
    "sorento_crm_backend/app/api/v1/widgets/parts.py": """
        from fastapi import APIRouter

        router = APIRouter(prefix="/parts")


        @router.get("")
        def list_parts(page: int = 1, limit: int = 20):
            return []


        @router.get("/{part_id}")
        def get_part(part_id: str):
            return {}
    """,
}

NEW_PAGED_ROUTE = """

    @router.get("/archived")
    def list_archived_parts(page: int = 1, limit: int = 20):
        return []
"""

REGISTRY = "sorento_crm_backend/app/services/assistant_registry/widgets.py"


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, src in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(src).lstrip("\n"), encoding="utf-8")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    _write(tmp_path, BASE_FILES)
    return tmp_path, _commit(tmp_path, "base")


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.write_text(path.read_text(encoding="utf-8") + textwrap.dedent(text), encoding="utf-8")


def _run(repo: Path, base: str, capsys, head: str | None = "HEAD") -> tuple[int, str]:
    args = ["--repo", str(repo), "--base", base]
    if head:
        args += ["--head", head]
    code = _load().main(args)
    return code, capsys.readouterr().out


PARTS = "sorento_crm_backend/app/api/v1/widgets/parts.py"


def test_added_paged_get_without_registration_fails(repo, capsys):
    root, base = repo
    _append(root, PARTS, NEW_PAGED_ROUTE)
    _commit(root, "add route")
    code, out = _run(root, base, capsys)
    assert code == 1
    # the full path is resolved through api_router -> widgets package re-export -> parts prefix
    assert "GET /api/v1/widgets/parts/archived" in out
    assert "not registered for the assistant" in out
    assert "list_archived_parts" in out


def test_working_tree_mode_sees_uncommitted_route(repo, capsys):
    root, base = repo
    _append(root, PARTS, NEW_PAGED_ROUTE)
    code, out = _run(root, base, capsys, head=None)
    assert code == 1
    assert "/api/v1/widgets/parts/archived" in out


def test_opt_out_comment_with_reason_passes(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        # The archive is an admin cleanup screen.
        # ai: not-for-assistant admin cleanup only, nobody asks for it in words
        @router.get("/archived")
        def list_archived_parts(page: int = 1):
            return []
        """,
    )
    _commit(root, "add opted-out route")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_opt_out_comment_without_reason_fails(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        # ai: not-for-assistant
        @router.get("/archived")
        def list_archived_parts(limit: int = 20):
            return []
        """,
    )
    _commit(root, "add opted-out route, no reason")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "opt-out comment has no reason" in out


def test_opt_out_comment_not_directly_above_does_not_count(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        # ai: not-for-assistant belongs to something else

        @router.get("/archived")
        def list_archived_parts(page: int = 1):
            return []
        """,
    )
    _commit(root, "comment separated by a blank line")
    code, _out = _run(root, base, capsys)
    assert code == 1


def test_registered_entity_route_passes(repo, capsys):
    root, base = repo
    _append(root, PARTS, NEW_PAGED_ROUTE)
    _write(
        root,
        {
            REGISTRY: """
                from app.services.assistant_registry.types import EntityDef

                ARCHIVED_PART = EntityDef(
                    key="archived_part",
                    label="Archived parts",
                    routes=("GET /api/v1/widgets/parts/archived",),
                )
            """
        },
    )
    _commit(root, "add route + registration")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_registration_of_a_different_route_does_not_cover(repo, capsys):
    root, base = repo
    _append(root, PARTS, NEW_PAGED_ROUTE)
    _write(
        root,
        {REGISTRY: 'X = EntityDef(key="part", routes=("GET /api/v1/widgets/parts",))\n'},
    )
    _commit(root, "registration names the old route only")
    code, _out = _run(root, base, capsys)
    assert code == 1


def test_route_string_outside_entitydef_does_not_count(repo, capsys):
    root, base = repo
    _append(root, PARTS, NEW_PAGED_ROUTE)
    _write(
        root,
        {
            REGISTRY: 'NOTE = "GET /api/v1/widgets/parts/archived"\n'
            'OTHER = Other(routes=("GET /api/v1/widgets/parts/archived",))\n'
        },
    )
    _commit(root, "string but no EntityDef")
    code, _out = _run(root, base, capsys)
    assert code == 1


def test_registered_route_with_path_param_matches_any_param_name(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        @router.get("/{part_id}/versions")
        def list_part_versions(part_id: str, page: int = 1):
            return []
        """,
    )
    _write(
        root,
        {REGISTRY: 'X = EntityDef(key="v", routes=("GET /api/v1/widgets/parts/{id}/versions/",))\n'},
    )
    _commit(root, "nested list")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_edit_to_existing_route_does_not_trigger(repo, capsys):
    root, base = repo
    path = root / PARTS
    src = path.read_text(encoding="utf-8")
    src = src.replace(
        "def list_parts(page: int = 1, limit: int = 20):\n    return []",
        "def list_parts(page: int = 1, limit: int = 50, query: str | None = None):\n    return [query]",
    )
    path.write_text(src, encoding="utf-8")
    _commit(root, "edit existing list")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_moving_a_route_to_another_file_does_not_trigger(repo, capsys):
    root, base = repo
    # the same served path, now declared in a new module mounted at the same place
    (root / PARTS).unlink()
    _write(
        root,
        {
            "sorento_crm_backend/app/api/v1/widgets/parts_v2.py": BASE_FILES[PARTS],
            "sorento_crm_backend/app/api/v1/widgets/__init__.py": """
                from fastapi import APIRouter
                from app.api.v1.widgets import parts_v2

                router = APIRouter()
                router.include_router(parts_v2.router)
            """,
        },
    )
    _commit(root, "move")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_non_paged_get_is_ignored(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        @router.get("/summary")
        async def parts_summary(part_type: str | None = None):
            return {}
        """,
    )
    _commit(root, "non-paged GET")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_api_route_with_get_counts_and_without_get_does_not(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        @router.api_route("/search", methods=["POST"])
        def search_parts(page: int = 1):
            return []


        @router.api_route("/browse", methods=["GET", "HEAD"])
        def browse_parts(page: int = 1):
            return []
        """,
    )
    _commit(root, "api_route")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "/api/v1/widgets/parts/browse" in out and "/search" not in out


@pytest.mark.parametrize(
    "signature",
    [
        'page_number: int = Query(1, alias="page")',
        'size: Annotated[int, Query(alias="limit")] = 20',
    ],
)
def test_paging_parameter_under_an_alias_counts(repo, capsys, signature):
    root, base = repo
    _append(
        root,
        PARTS,
        f"""

        @router.get("/aliased")
        def list_aliased({signature}):
            return []
        """,
    )
    _commit(root, "aliased paging")
    code, out = _run(root, base, capsys)
    assert code == 1, out
    assert "/api/v1/widgets/parts/aliased" in out


def test_added_post_with_page_is_ignored(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        @router.post("/search")
        def search_parts(page: int = 1):
            return []
        """,
    )
    _commit(root, "POST")
    code, out = _run(root, base, capsys)
    assert code == 0, out


def test_new_router_file_mounted_with_prefix_resolves_full_path(repo, capsys):
    root, base = repo
    _write(
        root,
        {
            "sorento_crm_backend/app/api/v1/gadgets.py": """
                from fastapi import APIRouter

                router = APIRouter(tags=["gadgets"])


                @router.get("/")
                def list_gadgets(limit: int = 20):
                    return []
            """,
            "sorento_crm_backend/app/api/v1/__init__.py": """
                from fastapi import APIRouter
                from app.api.v1 import gadgets, widgets

                api_router = APIRouter()
                api_router.include_router(widgets.router, prefix="/widgets")
                api_router.include_router(gadgets.router, prefix="/gadgets")
            """,
        },
    )
    _commit(root, "new module")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "GET /api/v1/gadgets " in out  # trailing slash normalized away


def test_route_factory_with_router_parameter_resolves_on_each_caller(repo, capsys):
    """`def register_x_routes(router): @router.get(...)` mounted by two callers, like portal/my-requests."""
    root, base = repo
    _write(
        root,
        {
            "sorento_crm_backend/app/api/v1/shared_routes.py": """
                from fastapi import APIRouter

                BASE = "/requests"


                def register_request_routes(router: APIRouter, dep=None) -> None:
                    @router.get(f"{BASE}/mine")
                    def list_my_requests(page: int = 1):
                        return []


                def register_outer(router):
                    register_request_routes(router)
            """,
            "sorento_crm_backend/app/api/v1/portal.py": """
                from fastapi import APIRouter
                from app.api.v1.shared_routes import register_outer, register_request_routes

                router = APIRouter()
                staff_router = APIRouter()
                register_request_routes(router, dep=None)
                register_outer(router=staff_router)
            """,
            "sorento_crm_backend/app/api/v1/__init__.py": """
                from fastapi import APIRouter
                from app.api.v1 import portal, widgets

                api_router = APIRouter()
                api_router.include_router(widgets.router, prefix="/widgets")
                api_router.include_router(portal.router, prefix="/portal")
                api_router.include_router(portal.staff_router, prefix="/my")
            """,
        },
    )
    _commit(root, "factory")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "/api/v1/portal/requests/mine" in out and "/api/v1/my/requests/mine" in out


def test_router_built_by_a_factory_function_resolves(repo, capsys):
    """`def build_x_router(): router = APIRouter(); ...; return router` then include_router(build_x_router())."""
    root, base = repo
    _write(
        root,
        {
            "sorento_crm_backend/app/api/v1/chat_routes.py": """
                from fastapi import APIRouter


                def build_chat_router(kind: str):
                    router = APIRouter()

                    @router.get("/{entity_id}/messages")
                    def list_messages(entity_id: str, limit: int = 50):
                        return []

                    return router
            """,
        },
    )
    _append(
        root,
        PARTS,
        """

        from app.api.v1.chat_routes import build_chat_router

        router.include_router(build_chat_router("part"))
        """,
    )
    _commit(root, "factory router")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "/api/v1/widgets/parts/{}/messages" in out


def test_route_path_from_module_constants_resolves(repo, capsys):
    root, base = repo
    _append(
        root,
        PARTS,
        """

        BASE = "/bins"
        LINES = BASE + "/{bin_id}/lines"


        @router.get(LINES)
        def list_bin_lines(bin_id: str, page: int = 1):
            return []
        """,
    )
    _commit(root, "constant path")
    code, out = _run(root, base, capsys)
    assert code == 1
    assert "/api/v1/widgets/parts/bins/{}/lines" in out


def test_real_tree_every_get_route_resolves_to_a_full_path():
    """Guards the static resolver against the live backend: no GET route is left unmounted."""
    mod = _load()
    graph = mod.build_graph(mod.Tree(_REPO_ROOT, None).files())
    assert len(graph.routes) > 500
    unresolved = [
        f"{r.file}:{r.line}"
        for r in graph.routes
        if r.path is None or graph.full_paths(r.router) is None
    ]
    assert unresolved == []


def test_static_paths_equal_the_apps_live_get_routes():
    """The AST resolver serves exactly the GET paths FastAPI registers: nothing missed, nothing invented.

    A new mounting pattern the resolver does not follow turns this red, before it lets a list route
    slip past the gate.
    """
    from fastapi.routing import APIRoute

    from app.main import app

    mod = _load()
    live = {
        mod.normalize(r.path) for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods
    }
    graph = mod.build_graph(mod.Tree(_REPO_ROOT, None).files())
    static: set[str] = set()
    for r in graph.routes:
        static |= mod.route_keys(graph, r)
    assert sorted(static - live) == []
    assert sorted(live - static) == []
