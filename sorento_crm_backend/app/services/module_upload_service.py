"""
Module upload service: receives a zip exported by `module_export_service`, validates it,
extracts backend + frontend payloads to disk, runs `alembic upgrade heads`, and seeds
the catalog row.

Zip layout (matches export_service):
  backend/
    manifest.py          (required)
    EXPORT_INFO.json
    <other backend files referenced by EXPORT_FILES_BACKEND>
    migrations/          (optional, branch-labeled)
  frontend/
    menu.json | routes.json | purge_tables.json (optional)
    pages/                (optional Next.js page tree)
  mcp/
    tools.json            (optional)
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    module_key: str
    version: str
    status: str
    needs_frontend_rebuild: bool
    restart_required: bool
    extracted_backend_files: list[str]
    extracted_frontend_files: list[str]


class ModuleUploadError(Exception):
    """Raised on validation or extraction failure."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]  # sorento_crm_backend/


def _frontend_root() -> Optional[Path]:
    candidate = _backend_root().parent / "sorento_crm_frontend"
    return candidate if candidate.is_dir() else None


def _safe_join(root: Path, member: str) -> Path:
    """Resolve a zip member path against root, refusing traversal."""
    target = (root / member).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise ModuleUploadError(f"Zip path traversal blocked: {member}") from exc
    return target


def _load_manifest_attrs(manifest_path: Path) -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        f"_uploaded_manifest_{manifest_path.parent.name}", manifest_path
    )
    if spec is None or spec.loader is None:
        raise ModuleUploadError(f"Cannot load manifest at {manifest_path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:  # noqa: BLE001
        raise ModuleUploadError(f"manifest.py raised on import: {exc}") from exc
    if not hasattr(mod, "MODULE_KEY"):
        raise ModuleUploadError("manifest.py must define MODULE_KEY")
    return {
        "MODULE_KEY": mod.MODULE_KEY,
        "DISPLAY_NAME": getattr(mod, "DISPLAY_NAME", mod.MODULE_KEY),
        "DESCRIPTION": getattr(mod, "DESCRIPTION", ""),
        "DEPENDENCIES": list(getattr(mod, "DEPENDENCIES", []) or []),
        "VERSION": str(getattr(mod, "VERSION", "0.0.0")),
    }


def _extract_zip_to_temp(zip_path: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="module_upload_"))
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            # Reject any absolute or traversal paths up front.
            if member.startswith("/") or ".." in Path(member).parts:
                raise ModuleUploadError(f"Unsafe zip member: {member}")
        zf.extractall(tmp)
    return tmp


def _copy_tree(src: Path, dest: Path) -> list[str]:
    """Copy src into dest (dest receives src's children). Returns relative file list."""
    copied: list[str] = []
    if not src.is_dir():
        return copied
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(str(rel))
    return copied


def _verify_module_mappers(module_key: str, backend_dest: Path) -> None:
    """Import the module's models and force SQLAlchemy mapper configuration.

    Raises ModuleUploadError if any relationship string fails to resolve. The caller
    rolls back the extracted files so the registry stays clean.
    """
    if not (backend_dest / "models.py").is_file() and not (backend_dest / "models").is_dir():
        return  # No ORM models to verify.

    import importlib
    from sqlalchemy.orm import configure_mappers

    module_path = f"app.modules.{module_key}.models"
    try:
        # Reload if already imported to pick up just-extracted code.
        if module_path in importlib.sys.modules:
            importlib.reload(importlib.sys.modules[module_path])
        else:
            importlib.import_module(module_path)
        # Apply any deferred inverse relationships the module queued via
        # ``register_inverse``. Without this, configure_mappers() would fail
        # when the module's models declare ``back_populates="..."`` against
        # platform classes that haven't yet received the reciprocal property.
        from app.database import Base
        from app.modules.runtime.relationship_registry import apply_pending
        apply_pending(Base.registry)
        configure_mappers()
    except Exception as exc:  # noqa: BLE001
        raise ModuleUploadError(
            f"Module '{module_key}' models failed mapper configuration: {exc}. "
            f"Likely a relationship() points to a class or property not present "
            f"in this deployment. Upload required upstream modules first."
        ) from exc


def _run_alembic_upgrade() -> None:
    """Programmatic `alembic upgrade heads`."""
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:  # noqa: BLE001
        raise ModuleUploadError("Alembic not installed") from exc
    cfg_path = _backend_root() / "alembic.ini"
    if not cfg_path.is_file():
        raise ModuleUploadError(f"alembic.ini not found at {cfg_path}")
    cfg = Config(str(cfg_path))
    command.upgrade(cfg, "heads")


def install_uploaded_zip(zip_path: Path, *, run_migrations: bool = True) -> UploadResult:
    """
    Validate zip, extract to app/modules/<key>/ + frontend/modules/<key>/, run migrations.

    Caller is responsible for activating the module (POST /{key}/activate).
    """
    if not zip_path.is_file():
        raise ModuleUploadError(f"Zip not found: {zip_path}")

    staging = _extract_zip_to_temp(zip_path)
    backend_src = staging / "backend"
    frontend_src = staging / "frontend"
    mcp_src = staging / "mcp"

    if not (backend_src / "manifest.py").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise ModuleUploadError("Zip missing backend/manifest.py")

    info = _load_manifest_attrs(backend_src / "manifest.py")
    module_key = info["MODULE_KEY"]
    if not module_key.replace("_", "").isalnum():
        shutil.rmtree(staging, ignore_errors=True)
        raise ModuleUploadError(f"Illegal module key: {module_key}")
    if module_key == "base":
        shutil.rmtree(staging, ignore_errors=True)
        raise ModuleUploadError("Refusing to overwrite the platform 'base' module")

    backend_root = _backend_root()

    # Block uploads whose declared DEPENDENCIES are not present on disk.
    # Without this guard, an importable module that references a missing class
    # poisons the SQLAlchemy mapper registry and 500s every ORM-backed route.
    declared_deps = [d for d in info.get("DEPENDENCIES", []) if d and d != module_key]
    if declared_deps:
        modules_dir = backend_root / "app" / "modules"
        missing = [
            dep
            for dep in declared_deps
            if dep != "base" and not (modules_dir / dep).is_dir()
        ]
        if missing:
            shutil.rmtree(staging, ignore_errors=True)
            raise ModuleUploadError(
                f"Module '{module_key}' depends on {missing} which "
                f"are not installed. Upload them first."
            )

    backend_dest = backend_root / "app" / "modules" / module_key
    extracted_backend: list[str] = []
    extracted_frontend: list[str] = []
    needs_frontend_rebuild = False

    try:
        # 1) backend/
        if backend_dest.exists():
            shutil.rmtree(backend_dest)
        extracted_backend = _copy_tree(backend_src, backend_dest)

        # 2) frontend assets
        fe_root = _frontend_root()
        if frontend_src.is_dir() and fe_root is not None:
            fe_dest = fe_root / "modules" / module_key
            if fe_dest.exists():
                shutil.rmtree(fe_dest)
            extracted_frontend = _copy_tree(frontend_src, fe_dest)
            # Copy frontend/pages into app/(protected)/
            pages_src = frontend_src / "pages"
            if pages_src.is_dir():
                slug_dirs = [p for p in pages_src.iterdir() if p.is_dir()]
                for slug_dir in slug_dirs:
                    target = fe_root / "app" / "(protected)" / slug_dir.name
                    if target.exists():
                        shutil.rmtree(target)
                    extracted_frontend.extend(
                        f"app/(protected)/{slug_dir.name}/{rel}"
                        for rel in _copy_tree(slug_dir, target)
                    )
                    needs_frontend_rebuild = True

        # 3) mcp tools.json (lives inside backend module dir already if present)
        if mcp_src.is_dir():
            mcp_dest = backend_dest / "mcp"
            mcp_dest.mkdir(parents=True, exist_ok=True)
            for f in mcp_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, mcp_dest / f.name)
                    extracted_backend.append(f"mcp/{f.name}")

        # 4) migrations
        if run_migrations:
            mig_dir = backend_dest / "migrations"
            if mig_dir.is_dir():
                _run_alembic_upgrade()

        # 5) verify the new module's mappers actually configure.
        # Without this, a string-based relationship() that resolves to a missing
        # class poisons SQLAlchemy's mapper registry — every ORM-backed route 500s.
        # Import the module's models, then call configure_mappers(); roll back on failure.
        _verify_module_mappers(module_key, backend_dest)

    except Exception:
        logger.exception("Upload failed; rolling back %s", module_key)
        if backend_dest.exists():
            shutil.rmtree(backend_dest, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return UploadResult(
        module_key=module_key,
        version=info["VERSION"],
        status="uploaded",
        needs_frontend_rebuild=needs_frontend_rebuild,
        restart_required=True,
        extracted_backend_files=extracted_backend,
        extracted_frontend_files=extracted_frontend,
    )


def remove_module_files(module_key: str) -> Dict[str, Any]:
    """Remove backend + frontend files for a module. Migrations are NOT removed."""
    if module_key == "base":
        raise ModuleUploadError("Cannot remove the 'base' module")
    removed: list[str] = []
    backend_dest = _backend_root() / "app" / "modules" / module_key
    if backend_dest.exists():
        shutil.rmtree(backend_dest)
        removed.append(str(backend_dest))
    fe_root = _frontend_root()
    if fe_root is not None:
        fe_dest = fe_root / "modules" / module_key
        if fe_dest.exists():
            shutil.rmtree(fe_dest)
            removed.append(str(fe_dest))
    return {"module_key": module_key, "removed_paths": removed}
