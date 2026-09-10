"""Red tests for S1: sorento_crm_backend/gunicorn.conf.py (does not exist yet).

UAC-2: preload_app True by default / False on GUNICORN_PRELOAD=0.
UAC-3: post_fork disposes app.database.engine with close=False, once per worker fork.
UAC-1: workers/worker_class/bind/timeout/keepalive/logging defaults match start.sh's
       current inline gunicorn flags (WORKERS, GUNICORN_KEEP_ALIVE, API_HOST, API_PORT).

The module lives at sorento_crm_backend/gunicorn.conf.py -- repo-root-of-backend, next to
start.sh, not under app/. It is loaded by path (not `import gunicorn.conf`) because the
filename has a dot in it. The env var reads happen at *import* time, so every test that
needs a particular env combination loads a FRESH module object via importlib rather than
reusing a cached one -- reusing would just replay whatever env was active on the first load.
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

CONF_PATH = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"


def _load_conf_module():
    """Import a fresh instance of gunicorn.conf.py from disk, uncached.

    A dotted module name with a literal '.' in the filename can't go through the normal
    `import` statement, and reusing sys.modules would hide the fact that the env var is
    read once, at import time -- so this gives every caller a brand new module object.
    """
    spec = importlib.util.spec_from_file_location("gunicorn_conf_under_test", CONF_PATH)
    assert spec is not None and spec.loader is not None, f"could not build a spec for {CONF_PATH}"
    module = importlib.util.module_from_spec(spec)
    # Registering under a fixed name lets `from app.database import engine` inside the
    # module (if it does that at import time) resolve normally; the module content itself
    # is fresh every call because spec_from_file_location + exec_module reruns the file.
    sys.modules["gunicorn_conf_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_preload_on_by_default(monkeypatch):
    """UAC-2: with GUNICORN_PRELOAD unset, preload_app defaults True."""
    monkeypatch.delenv("GUNICORN_PRELOAD", raising=False)
    module = _load_conf_module()
    assert module.preload_app is True


def test_preload_off_with_env_zero(monkeypatch):
    """UAC-2: GUNICORN_PRELOAD=0 turns preload off; GUNICORN_PRELOAD=1 turns it on."""
    monkeypatch.setenv("GUNICORN_PRELOAD", "0")
    module_off = _load_conf_module()
    assert module_off.preload_app is False

    monkeypatch.setenv("GUNICORN_PRELOAD", "1")
    module_on = _load_conf_module()
    assert module_on.preload_app is True


def test_defaults_match_start_sh(monkeypatch):
    """UAC-1: gunicorn.conf.py reproduces start.sh's current inline flags and defaults.

    start.sh today: --workers ${WORKERS:-4}, --worker-class uvicorn.workers.UvicornWorker,
    --bind "${API_HOST:-0.0.0.0}:${API_PORT:-8000}", --timeout 120,
    --keep-alive "${GUNICORN_KEEP_ALIVE:-75}", --access-logfile -, --error-logfile -,
    --log-level info.
    """
    # workers: default 4
    monkeypatch.delenv("WORKERS", raising=False)
    module = _load_conf_module()
    assert module.workers == 4

    # workers: overridden
    monkeypatch.setenv("WORKERS", "2")
    module = _load_conf_module()
    assert module.workers == 2
    monkeypatch.delenv("WORKERS", raising=False)

    module = _load_conf_module()
    assert module.worker_class == "uvicorn.workers.UvicornWorker"
    assert module.timeout == 120

    # keepalive: default 75
    monkeypatch.delenv("GUNICORN_KEEP_ALIVE", raising=False)
    module = _load_conf_module()
    assert module.keepalive == 75

    # keepalive: overridden
    monkeypatch.setenv("GUNICORN_KEEP_ALIVE", "30")
    module = _load_conf_module()
    assert module.keepalive == 30
    monkeypatch.delenv("GUNICORN_KEEP_ALIVE", raising=False)

    # bind: default host/port
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)
    module = _load_conf_module()
    assert module.bind == "0.0.0.0:8000"

    # bind: overridden host/port
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "9000")
    module = _load_conf_module()
    assert module.bind == "127.0.0.1:9000"
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)

    module = _load_conf_module()
    assert module.accesslog == "-"
    assert module.errorlog == "-"
    assert module.loglevel == "info"


def test_post_fork_disposes_engine_without_closing_parent(monkeypatch):
    """UAC-3: post_fork calls app.database.engine.dispose(close=False) exactly once.

    post_fork must import `engine` lazily *inside* the function (the plan's documented
    SQLAlchemy fork recipe: `from app.database import engine; engine.dispose(close=False)`),
    so patching the attribute on the already-imported app.database module before calling
    post_fork is what the mock is picked up by.
    """
    module = _load_conf_module()

    import app.database as database_module

    fake_engine = MagicMock()
    monkeypatch.setattr(database_module, "engine", fake_engine)

    module.post_fork(server=MagicMock(), worker=MagicMock())

    fake_engine.dispose.assert_called_once_with(close=False)


def test_post_fork_is_idempotent_per_call(monkeypatch):
    """UAC-3: each worker fork gets its own dispose call -- two forks, two disposes, never zero."""
    module = _load_conf_module()

    import app.database as database_module

    fake_engine = MagicMock()
    monkeypatch.setattr(database_module, "engine", fake_engine)

    module.post_fork(server=MagicMock(), worker=MagicMock())
    module.post_fork(server=MagicMock(), worker=MagicMock())

    assert fake_engine.dispose.call_count == 2
    for call in fake_engine.dispose.call_args_list:
        assert call.kwargs.get("close") is False
