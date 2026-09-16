"""SORENTO_ENV_FILE lets a test suite point Settings at a private dotenv
instead of the backend's real .env, which a running dev server also reads
(see app.main._load_env_file). The wiring that matters lives in
app.config._resolve_settings_env_file, which runs at MODULE IMPORT time -
before `settings = Settings()` - because conftest imports app.database ->
app.config long before app.main is ever imported, so app.main's own
os.environ loader runs too late to affect Settings().

Both cases here spawn a real subprocess: the override has to be set BEFORE
`import app.config` for it to matter, which an in-process monkeypatch (the
previous version of this test) cannot exercise since app.config is already
imported by the time a test function runs.
"""
import os
import subprocess
import sys


def _run_probe(env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # A real DATABASE_URL/JWT_SECRET already sitting in THIS process's os.environ
    # (this suite is itself usually run as `SORENTO_ENV_FILE=... pytest ...`, and
    # app.main's own _load_env_file - imported by something collection touches -
    # writes the dotenv's values into REAL os.environ, not just into pydantic-
    # settings) would otherwise win inside the subprocess too: pydantic-settings
    # prefers a real environment variable over anything in its own env_file, no
    # matter which env_file SORENTO_ENV_FILE points the subprocess at. Dropped so
    # the subprocess is forced to read only the dotenv this test controls.
    env.pop("DATABASE_URL", None)
    env.pop("DIRECT_URL", None)
    env.pop("JWT_SECRET", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "from app.config import settings; print(settings.database_url)"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_sorento_env_file_overrides_settings_dotenv(tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "DATABASE_URL=postgresql://x:y@localhost:5432/zzz_env_switch\n"
        "JWT_SECRET=test-secret-for-env-file-switch-test\n"
    )

    result = _run_probe({"SORENTO_ENV_FILE": str(env_file)})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("zzz_env_switch")


def test_sorento_env_file_missing_raises(tmp_path):
    missing_path = tmp_path / "does-not-exist.env"

    result = _run_probe({"SORENTO_ENV_FILE": str(missing_path)})

    assert result.returncode != 0
    assert "SORENTO_ENV_FILE" in result.stderr
    assert "does not resolve to an existing file" in result.stderr
