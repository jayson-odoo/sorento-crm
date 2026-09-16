"""SORENTO_ENV_FILE lets a test point at a private dotenv instead of the
backend's real .env, which a running dev server also reads (see
app.main._load_env_file). This test never touches the real .env: it writes
its own temp dotenv, points SORENTO_ENV_FILE at it, and restores the
environment afterwards.
"""
import os

from app.main import _load_env_file


def test_sorento_env_file_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text("DATABASE_URL=postgresql://x:y@localhost/zzz_env_switch\n")

    original_database_url = os.environ.get("DATABASE_URL")
    monkeypatch.setenv("SORENTO_ENV_FILE", str(env_file))
    try:
        _load_env_file()
        assert os.environ["DATABASE_URL"].endswith("zzz_env_switch")
    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
