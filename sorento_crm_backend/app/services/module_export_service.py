"""
Module export service: assembles a portable zip from an installed module so it can
be dropped into another Sorento CRM deployment via the App Store upload flow.

Walks `EXPORT_FILES_BACKEND` and `EXPORT_FILES_FRONTEND` declared in each module's
manifest.py — supports the pragmatic "manifest with file refs" layout where module
code still lives in shared backend dirs (app/api/v1, app/models, app/services).

Stream the result via FastAPI's `StreamingResponse`.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


class ModuleExportError(Exception):
    """Raised on validation failures (e.g. base module export)."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]  # sorento_crm_backend/


def _frontend_root() -> Optional[Path]:
    candidate = _backend_root().parent / "sorento_crm_frontend"
    return candidate if candidate.is_dir() else None


def _module_dir(module_key: str) -> Path:
    return _backend_root() / "app" / "modules" / module_key


def _load_manifest(module_key: str) -> Dict[str, Any]:
    manifest_path = _module_dir(module_key) / "manifest.py"
    if not manifest_path.is_file():
        raise ModuleExportError(
            f"Module '{module_key}' has no manifest.py — not yet migrated to per-module package."
        )
    spec = importlib.util.spec_from_file_location(
        f"_export_manifest_{module_key}", manifest_path
    )
    if spec is None or spec.loader is None:
        raise ModuleExportError(f"Cannot load manifest at {manifest_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return {
        "MODULE_KEY": getattr(mod, "MODULE_KEY", module_key),
        "DISPLAY_NAME": getattr(mod, "DISPLAY_NAME", module_key),
        "DESCRIPTION": getattr(mod, "DESCRIPTION", ""),
        "DEPENDENCIES": list(getattr(mod, "DEPENDENCIES", []) or []),
        "VERSION": str(getattr(mod, "VERSION", "0.0.0")),
        "EXPORT_FILES_BACKEND": list(getattr(mod, "EXPORT_FILES_BACKEND", []) or []),
        "EXPORT_FILES_FRONTEND": list(getattr(mod, "EXPORT_FILES_FRONTEND", []) or []),
        "EXPORT_PURGE_FN": getattr(mod, "EXPORT_PURGE_FN", None),
    }


def _iter_files(root: Path, target: Path) -> Iterable[Path]:
    """Yield every file under target (a path relative to root)."""
    p = root / target
    if not p.exists():
        logger.warning("Export ref missing: %s", p)
        return
    if p.is_file():
        yield p
        return
    for f in p.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and not f.name.endswith(".pyc"):
            yield f


def _add_file(zf: zipfile.ZipFile, src: Path, arcname: str, hasher) -> None:
    data = src.read_bytes()
    hasher.update(arcname.encode("utf-8"))
    hasher.update(data)
    zf.writestr(arcname, data)


def build_export_zip(module_key: str) -> tuple[bytes, str]:
    """
    Build the export zip for `module_key`. Returns (zip_bytes, suggested_filename).

    Raises ModuleExportError for refusals (base module, missing manifest).
    """
    if module_key == "base":
        raise ModuleExportError("Refusing to export the platform 'base' module.")
    info = _load_manifest(module_key)
    backend_root = _backend_root()
    frontend_root = _frontend_root()

    buf = io.BytesIO()
    hasher = hashlib.sha256()
    file_list_backend: list[str] = []
    file_list_frontend: list[str] = []
    caveats: list[str] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) The module's own manifest + frontend metadata + mcp slice (under app/modules/<key>/).
        module_dir = _module_dir(module_key)
        if module_dir.is_dir():
            for f in module_dir.rglob("*"):
                if not f.is_file():
                    continue
                if "__pycache__" in f.parts or f.name.endswith(".pyc"):
                    continue
                rel = f.relative_to(module_dir)
                # manifest + python module bits → backend/
                # frontend/ subtree → frontend/
                # mcp/ subtree → mcp/
                first = rel.parts[0]
                if first == "frontend":
                    arc = "frontend/" + "/".join(rel.parts[1:])
                    _add_file(zf, f, arc, hasher)
                    file_list_frontend.append(arc)
                elif first == "mcp":
                    arc = "mcp/" + "/".join(rel.parts[1:])
                    _add_file(zf, f, arc, hasher)
                    file_list_backend.append(arc)
                else:
                    arc = f"backend/{rel.as_posix()}"
                    _add_file(zf, f, arc, hasher)
                    file_list_backend.append(arc)

        # 2) Backend file refs (legacy in shared dirs).
        for ref in info["EXPORT_FILES_BACKEND"]:
            files = list(_iter_files(backend_root, Path(ref)))
            if not files:
                caveats.append(f"missing backend ref: {ref}")
                continue
            for f in files:
                rel = f.relative_to(backend_root)
                arc = f"backend/{rel.as_posix()}"
                if arc in file_list_backend:
                    continue
                _add_file(zf, f, arc, hasher)
                file_list_backend.append(arc)

        # 3) Frontend file refs.
        if frontend_root is not None:
            for ref in info["EXPORT_FILES_FRONTEND"]:
                files = list(_iter_files(frontend_root, Path(ref)))
                if not files:
                    caveats.append(f"missing frontend ref: {ref}")
                    continue
                for f in files:
                    rel = f.relative_to(frontend_root)
                    # Normalize app/(protected)/<slug>/ → frontend/pages/<slug>/
                    parts = rel.parts
                    if len(parts) >= 3 and parts[0] == "app" and parts[1] == "(protected)":
                        slug = parts[2]
                        arc = "frontend/pages/" + slug + "/" + "/".join(parts[3:])
                    else:
                        arc = "frontend/" + rel.as_posix()
                    if arc in file_list_frontend:
                        continue
                    _add_file(zf, f, arc, hasher)
                    file_list_frontend.append(arc)
        else:
            caveats.append("frontend repo not found alongside backend; FE files skipped")

        # 4) EXPORT_INFO.json
        export_info = {
            "module_key": info["MODULE_KEY"],
            "display_name": info["DISPLAY_NAME"],
            "description": info["DESCRIPTION"],
            "version": info["VERSION"],
            "dependencies": info["DEPENDENCIES"],
            "purge_fn_ref": info["EXPORT_PURGE_FN"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "backend_files": sorted(file_list_backend),
            "frontend_files": sorted(file_list_frontend),
            "caveats": caveats,
            "checksum_sha256": hasher.hexdigest(),
        }
        zf.writestr("EXPORT_INFO.json", json.dumps(export_info, indent=2))

    filename = f"{info['MODULE_KEY']}-{info['VERSION']}.zip"
    return buf.getvalue(), filename
