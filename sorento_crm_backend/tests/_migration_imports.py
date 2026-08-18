"""Which application modules a migration file imports, read from its syntax tree.

A migration describes a point in history, so it must not import live application code:
`from app.services.scm.demand import COMMITTED_V_SQL` is how the first from-zero replay of
the SCM chain died in production (see `340_scm_committed_reads_the_decision`). Reading the
tree rather than the text catches every spelling of that import - `from app.x import y`,
`import app.x`, `import app.x as z`, `importlib.import_module("app.x")` and
`__import__("app.x")` - and ignores the docstrings that talk about it.
"""
from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE = "app"


def _is_app_module(name: str | None) -> bool:
    return name is not None and (name == _PACKAGE or name.startswith(f"{_PACKAGE}."))


def _dynamic_import_target(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        is_importer = func.attr == "import_module"
    elif isinstance(func, ast.Name):
        is_importer = func.id in {"import_module", "__import__"}
    else:
        return None
    if not is_importer or not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def app_imports(path: Path) -> list[str]:
    """Every `app.*` module the file imports, statically or through the import machinery."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if _is_app_module(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and _is_app_module(node.module):
                found.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if _is_app_module(target):
                found.append(target)
    return found
