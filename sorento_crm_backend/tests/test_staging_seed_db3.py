"""AC-TEST-COMPANY: the local db3 staging seed (scripts/staging/seed_db3_staging.py).

Two halves: the target guard (pure, no database) and the seed itself on a rolled-back Postgres
session, run twice to prove it is idempotent.
"""
from __future__ import annotations

import bcrypt
import pytest

from scripts.staging.seed_db3_staging import (
    AUTOCOUNT_SWITCHES,
    INTEGRATION_NAME,
    RefusedTarget,
    SeedConfig,
    check_target,
    seed,
)

from ._pg_fixture import pg_session, unique_code

#: Long enough for the 32-character minimum on its own.
PUSH = "ss-push-key-for-local-staging-tests-"


# ---------------------------------------------------------------------------- guard


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost:5432/sorento_staging",
        "postgresql+psycopg2://u@localhost/crm-stg",
        "postgresql://u:p@127.0.0.1/Sorento_Staging",
        "postgresql:///sorento_staging",  # unix socket, no host
    ],
)
def test_guard_accepts_local_staging_databases(url):
    assert check_target(url, environ={})


@pytest.mark.parametrize(
    "url, why",
    [
        ("postgresql://u:p@db.example.com/sorento_staging", "not this machine"),
        ("postgresql://u:p@10.0.0.5/sorento_dev", "not this machine"),
        ("postgresql://u:p@localhost/sorento", "no staging token"),
        ("postgresql://u:p@localhost/sorento_ci", "no staging token"),
        ("postgresql://u:p@localhost/sorento_prod_staging", "prod token"),
        ("postgresql://u:p@localhost/production_dev", "prod token"),
        ("postgresql://u:p@localhost/staging_live", "prod token"),
        ("postgresql://u:p@localhost/stagingonly", "no staging token"),  # a token, not a substring
        # The shared prod-copy dev database must never be re-pointed (security review).
        ("postgresql://u:p@localhost/sorento_dev", "no staging token"),
        ("postgresql://u:p@localhost/sorento_local", "no staging token"),
        # libpq rerouting a local-looking URL to another server.
        ("postgresql://u:p@/sorento_staging?host=db.prod.internal", "another server"),
        ("postgresql://u:p@localhost/sorento_staging?hostaddr=10.0.0.5", "another server"),
        ("postgresql://u:p@localhost/sorento_staging?service=prod", "another server"),
    ],
)
def test_guard_refuses_anything_else(url, why):
    with pytest.raises(RefusedTarget, match=why):
        check_target(url, environ={})


@pytest.mark.parametrize("var", ["PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_guard_refuses_when_libpq_env_can_reroute(var):
    with pytest.raises(RefusedTarget, match="another server"):
        check_target("postgresql:///sorento_staging", environ={var: "db.prod.internal"})


def test_apply_needs_the_database_name_typed_out(monkeypatch, capsys):
    from scripts.staging import seed_db3_staging as mod

    # The refusal must come before anything else, so no seed input may be present to proceed with.
    for var in ("STAGING_SS_API_KEY", "STAGING_ADMIN_PASSWORD", "STAGING_SS_PUSH_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(mod, "SessionLocal", None, raising=False)
    monkeypatch.setattr(mod, "check_target", lambda url: "sorento_staging")
    assert mod.main(["--ss-base-url", "http://x", "--apply"]) == 2
    assert "--confirm-db sorento_staging" in capsys.readouterr().err
    assert mod.main(["--ss-base-url", "http://x", "--apply", "--confirm-db", "sorento_dev"]) == 2


# ---------------------------------------------------------------------------- seed


def _cfg(code: str, **over) -> SeedConfig:
    base = dict(
        ss_base_url="http://localhost:8100/",
        ss_api_key="ss-outbound-key",
        admin_password="staging-pass-1",
        company_code=code,
        company_name="TEST - AutoCount db3",
        admin_email=f"{code.lower()}@example.com",
    )
    base.update(over)
    return SeedConfig(**base)


def _ensure_prereqs(db):
    """CI's database is reference data only: make sure a settings row and an admin role exist."""
    from app.models.user import SystemSetting, UserRole

    if db.query(SystemSetting).first() is None:
        db.add(SystemSetting())
    if db.query(UserRole).filter(UserRole.slug.in_(["superadmin", "admin"])).first() is None:
        db.add(UserRole(slug="admin", name="Admin"))
    db.flush()


def test_seed_creates_everything_and_is_idempotent():
    from app.models.base import company_scope
    from app.models.company import Company, UserCompany
    from app.models.integration import Integration, IntegrationApiKey
    from app.models.user import SystemSetting, User
    from app.services.integration_admin_service import IntegrationAdminService
    from app.services.integration_key_crypto import hash_api_key

    code = unique_code("DB3")
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        cfg = _cfg(code, push_key=PUSH + "a" + code)

        first = seed(db, cfg)
        second = seed(db, _cfg(code, push_key=PUSH + "a" + code, admin_password="staging-pass-2"))

        companies = db.query(Company).filter(Company.code == code).all()
        assert len(companies) == 1 and companies[0].is_active

        row = db.query(Integration).filter(Integration.name == INTEGRATION_NAME).one()
        assert row.is_active
        assert row.config_json["base_url"] == "http://localhost:8100"
        assert IntegrationAdminService(db).decrypt_credentials(row)["api_key"] == "ss-outbound-key"

        keys = db.query(IntegrationApiKey).filter(
            IntegrationApiKey.key_hash == hash_api_key(PUSH + "a" + code)
        ).all()
        assert len(keys) == 1 and keys[0].integration_id == row.id

        settings_row = db.query(SystemSetting).first()
        for name in AUTOCOUNT_SWITCHES:
            if hasattr(SystemSetting, name):
                assert getattr(settings_row, name) is True
            else:
                assert name in second.missing_switches

        user = db.query(User).filter(User.email == cfg.admin_email).one()
        assert user.status == "ACTIVE"
        assert user.last_active_company_id == companies[0].id
        assert bcrypt.checkpw(b"staging-pass-2", user.password.encode("utf-8"))  # second run's
        grants = db.query(UserCompany).filter_by(user_id=user.id, company_id=companies[0].id).all()
        assert len(grants) == 1

        assert first.minted_push_key is None and second.minted_push_key is None


def test_seed_drops_a_binding_to_another_company():
    from app.models.base import company_scope
    from app.models.integration import Integration

    code = unique_code("DB3")
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        seed(db, _cfg(code, push_key=PUSH + "b" + code))
        row = db.query(Integration).filter(Integration.name == INTEGRATION_NAME).one()
        row.config_json = {**(row.config_json or {}), "company_code": "SRT"}
        db.flush()

        report = seed(db, _cfg(code, push_key=PUSH + "b" + code))

        db.refresh(row)
        assert "company_code" not in (row.config_json or {})
        assert any("dropped company_code binding" in line for line in report.lines)


def test_seed_mints_a_push_key_once_when_none_given():
    from app.models.base import company_scope
    from app.models.integration import Integration, IntegrationApiKey

    code = unique_code("DB3")
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        # Start from no live key on the integration, whatever the shared DB holds.
        seed(db, _cfg(code, push_key=PUSH + "c" + code))
        row = db.query(Integration).filter(Integration.name == INTEGRATION_NAME).one()
        db.query(IntegrationApiKey).filter(IntegrationApiKey.integration_id == row.id).delete()
        db.flush()

        minted = seed(db, _cfg(code)).minted_push_key
        again = seed(db, _cfg(code)).minted_push_key

        assert minted and minted.strip()
        assert again is None


def test_seed_refuses_a_real_looking_admin_email():
    from app.models.base import company_scope

    code = unique_code("DB3")
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        with pytest.raises(RefusedTarget, match="reserved domain"):
            seed(db, _cfg(code, push_key=PUSH + "d" + code, admin_email="owner@sorento.com.my"))


def test_seed_refuses_a_short_push_key():
    from app.models.base import company_scope

    code = unique_code("DB3")
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        with pytest.raises(RefusedTarget, match="at least 32"):
            seed(db, _cfg(code, push_key="short"))


def test_seed_never_revives_a_revoked_push_key():
    from datetime import datetime

    from app.models.base import company_scope
    from app.models.integration import IntegrationApiKey
    from app.services.integration_key_crypto import hash_api_key

    code = unique_code("DB3")
    key = PUSH + "e" + code
    with pg_session(autoflush=False) as db, company_scope(db, None):
        _ensure_prereqs(db)
        seed(db, _cfg(code, push_key=key))
        row = db.query(IntegrationApiKey).filter(IntegrationApiKey.key_hash == hash_api_key(key)).one()
        row.revoked_at = datetime(2026, 1, 1)
        db.flush()

        with pytest.raises(RefusedTarget, match="revoked"):
            seed(db, _cfg(code, push_key=key))
        assert row.revoked_at is not None
