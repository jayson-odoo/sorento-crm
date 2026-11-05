#!/usr/bin/env python3
"""LOCAL STAGING ONLY: make a local CRM copy talk to a local Shared Service bound to AutoCount db3.

Lane AC-TEST-COMPANY (owner, 5 Nov 2026): the test company lives on a local staging copy on the
owner's Mac, not in the prod CRM. This script creates or updates, idempotently:

1. The CRM company whose code the Shared Service (SS) maps to the db3 book (default `SRT_DB3`).
   The CRM names the SS company only by `companies.code` (`foundryx_autocount_client.py:173,236`;
   ingest resolves `companyCode` the same way, `api/v1/external/company_anchor.py:135-161`).
2. The `foundryx-esb` integration row: `config_json.base_url` -> the local SS, the outbound key
   (CRM -> SS) in its encrypted credentials, active, and no `company_code` binding pinned to
   another company (a binding would refuse SRT_DB3 pushes as COMPANY_ANCHOR_AMBIGUOUS).
3. The inbound key SS pushes with (SS -> CRM `/api/v1/external/ingest/*`), as a hashed
   `integration_api_keys` row on `foundryx-esb`. Pass one to keep SS's config stable across
   resets; without one, a key is minted on first run and printed once.
4. Every AutoCount write switch ON (columns missing on this branch are reported, not invented).
5. A staging admin login granted the test company, which becomes its active company.

Refuses unless the database the app would write to is on this machine AND its name carries a
dev/staging token AND no prod token. Default is a dry run; `--apply` commits.

Run from sorento_crm_backend/:
    STAGING_SS_API_KEY=... STAGING_ADMIN_PASSWORD=... \\
      venv/bin/python -m scripts.staging.seed_db3_staging --ss-base-url http://localhost:8100 --apply

Runbook: documentation/plans/autocount/RUNBOOK-db3-local-staging.md
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

#: Hosts that mean "this machine". Anything else is refused: staging is local by definition.
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
#: At least one of these must be a token of the database name (split on _ - .).
STAGING_TOKENS = frozenset({"dev", "staging", "stg", "local"})
#: None of these may be a token of the database name.
PROD_TOKENS = frozenset({"prod", "production", "live", "main"})

#: Every AutoCount write switch on `system_settings`. #2168 is on main; #2173's column lands
#: with that PR (branch claude/ac-qtso-crm-phase-2-1n1ffk) and is reported missing until then.
AUTOCOUNT_SWITCHES = (
    "stock_debt_po_link_enabled",  # #2168 Stock Debt PO line link/unlink (app/models/user.py:465)
    "project_autocount_write_enabled",  # #2173 project QT/SO create/update/cancel
)

INTEGRATION_NAME = "foundryx-esb"
DEFAULT_COMPANY_CODE = "SRT_DB3"
DEFAULT_COMPANY_NAME = "TEST - AutoCount db3"
DEFAULT_ADMIN_EMAIL = "staging-admin@example.com"


class RefusedTarget(Exception):
    """The database is not a local staging database."""


def check_target(url) -> str:
    """Return the database name if `url` is a local staging database, else raise RefusedTarget.

    `url` is a SQLAlchemy URL or a string. Checked against the URL the app's engine really uses,
    not an env var a caller could have set differently.
    """
    from sqlalchemy.engine import make_url

    parsed = make_url(str(url)) if not hasattr(url, "database") else url
    host = (parsed.host or "").lower()
    name = (parsed.database or "").lower()
    if host not in LOCAL_HOSTS:
        raise RefusedTarget(f"database host {host!r} is not this machine; staging is local only")
    tokens = {t for t in re.split(r"[_\-.]+", name) if t}
    prod_hit = tokens & PROD_TOKENS
    if prod_hit:
        raise RefusedTarget(f"database name {name!r} carries a prod token {sorted(prod_hit)}")
    if not tokens & STAGING_TOKENS:
        raise RefusedTarget(
            f"database name {name!r} has no staging token (one of {sorted(STAGING_TOKENS)}); "
            "copy the dev DB to e.g. sorento_staging first"
        )
    return name


@dataclass
class SeedConfig:
    ss_base_url: str
    ss_api_key: str
    admin_password: str
    push_key: Optional[str] = None
    company_code: str = DEFAULT_COMPANY_CODE
    company_name: str = DEFAULT_COMPANY_NAME
    admin_email: str = DEFAULT_ADMIN_EMAIL


@dataclass
class SeedReport:
    lines: list[str] = field(default_factory=list)
    minted_push_key: Optional[str] = None
    missing_switches: list[str] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.lines.append(line)


def _ensure_company(db, cfg: SeedConfig, report: SeedReport):
    from app.models.company import Company

    company = db.query(Company).filter(Company.code == cfg.company_code).first()
    if company is None:
        company = Company(name=cfg.company_name, code=cfg.company_code, is_active=True)
        db.add(company)
        db.flush()
        report.add(f"company {cfg.company_code}: created")
    else:
        company.name = cfg.company_name
        company.is_active = True
        db.flush()
        report.add(f"company {cfg.company_code}: exists, kept")
    return company


def _ensure_integration(db, cfg: SeedConfig, report: SeedReport):
    from app.models.integration import Integration
    from app.services.integration_admin_service import IntegrationAdminService
    from app.services.integration_seed import seed_integrations

    row = db.query(Integration).filter(Integration.name == INTEGRATION_NAME).first()
    if row is None:
        # The standard seed (principal + admin-parity role + row); idempotent, no env key.
        seed_integrations(db, None)
        row = db.query(Integration).filter(Integration.name == INTEGRATION_NAME).first()
        report.add(f"integration {INTEGRATION_NAME}: seeded")

    service = IntegrationAdminService(db)
    config = dict(row.config_json or {})
    config["base_url"] = cfg.ss_base_url.rstrip("/")
    binding = config.get("company_code")
    if binding and str(binding).strip() != cfg.company_code:
        # A binding names one company for every push; SRT_DB3 pushes would be refused.
        config.pop("company_code")
        report.add(f"integration {INTEGRATION_NAME}: dropped company_code binding {binding!r}")
    credentials = dict(service.decrypt_credentials(row) or {})
    credentials["api_key"] = cfg.ss_api_key
    service.update(row, config_json=config, credentials_json=credentials, is_active=True)
    report.add(f"integration {INTEGRATION_NAME}: base_url={config['base_url']}, outbound key set, active")
    return row


def _ensure_push_key(db, row, cfg: SeedConfig, report: SeedReport) -> None:
    from app.models.integration import IntegrationApiKey
    from app.services.integration_key_crypto import hash_api_key, key_prefix
    from app.services.integration_key_service import IntegrationKeyService

    if cfg.push_key:
        digest = hash_api_key(cfg.push_key)
        existing = db.query(IntegrationApiKey).filter(IntegrationApiKey.key_hash == digest).first()
        if existing is not None and existing.integration_id != row.id:
            raise RefusedTarget("the given push key already belongs to another integration")
        if existing is None:
            db.add(
                IntegrationApiKey(
                    integration_id=row.id, key_hash=digest, key_prefix=key_prefix(cfg.push_key)
                )
            )
            db.flush()
            report.add("push key (SS -> CRM): registered")
        else:
            existing.revoked_at = None
            existing.expires_at = None
            db.flush()
            report.add("push key (SS -> CRM): already registered")
        return

    live = (
        db.query(IntegrationApiKey)
        .filter(
            IntegrationApiKey.integration_id == row.id,
            IntegrationApiKey.revoked_at.is_(None),
            IntegrationApiKey.expires_at.is_(None),
        )
        .first()
    )
    if live is not None:
        report.add(f"push key (SS -> CRM): {live.key_prefix}... exists; set STAGING_SS_PUSH_KEY to pin one")
        return
    report.minted_push_key = IntegrationKeyService(db).issue_key(row)
    report.add("push key (SS -> CRM): minted (printed below, once)")


def _switches_on(db, report: SeedReport) -> None:
    from app.models.user import SystemSetting

    settings_row = db.query(SystemSetting).first()
    if settings_row is None:
        raise RefusedTarget("no system_settings row; bootstrap the database first")
    for name in AUTOCOUNT_SWITCHES:
        if hasattr(SystemSetting, name):
            setattr(settings_row, name, True)
            report.add(f"switch {name}: ON")
        else:
            report.missing_switches.append(name)
            report.add(f"switch {name}: not on this branch, skipped")
    db.flush()


def _ensure_admin(db, cfg: SeedConfig, company, report: SeedReport) -> None:
    import bcrypt

    from app.models.company import UserCompany
    from app.models.user import User, UserRole, UserRoleAssignment

    role = None
    for slug in ("superadmin", "admin"):
        role = db.query(UserRole).filter(UserRole.slug == slug).first()
        if role is not None:
            break
    if role is None:
        raise RefusedTarget("no superadmin/admin role; bootstrap the database first")

    hashed = bcrypt.hashpw(cfg.admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = db.query(User).filter(User.email == cfg.admin_email.lower()).first()
    if user is None:
        user = User(
            email=cfg.admin_email.lower(),
            name="Staging Admin",
            password=hashed,
            status="ACTIVE",
            email_verified_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(user)
        db.flush()
        report.add(f"admin {cfg.admin_email}: created ({role.slug})")
    else:
        user.password = hashed
        user.status = "ACTIVE"
        user.is_trashed = False
        report.add(f"admin {cfg.admin_email}: exists, password reset ({role.slug})")

    if not db.query(UserRoleAssignment).filter_by(user_id=user.id, role_id=role.id).first():
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    if not db.query(UserCompany).filter_by(user_id=user.id, company_id=company.id).first():
        db.add(UserCompany(user_id=user.id, company_id=company.id))
    user.last_active_company_id = company.id
    db.flush()
    report.add(f"admin {cfg.admin_email}: granted {company.code}, active company set")


def seed(db, cfg: SeedConfig) -> SeedReport:
    """Apply every step on `db` without committing (the caller commits or rolls back)."""
    from app.models.base import company_scope

    report = SeedReport()
    # The seed spans companies (a company row, a global integration, a global settings row);
    # run it under the all-companies scope, as the bootstrap and migrations do.
    with company_scope(db, None):
        company = _ensure_company(db, cfg, report)
        row = _ensure_integration(db, cfg, report)
        _ensure_push_key(db, row, cfg, report)
        _switches_on(db, report)
        _ensure_admin(db, cfg, company, report)
    return report


def _parse(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Seed a LOCAL staging CRM copy for the db3 test book.")
    ap.add_argument("--ss-base-url", default=os.environ.get("STAGING_SS_BASE_URL"))
    ap.add_argument("--company-code", default=DEFAULT_COMPANY_CODE)
    ap.add_argument("--company-name", default=DEFAULT_COMPANY_NAME)
    ap.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL)
    ap.add_argument("--apply", action="store_true", help="commit; without it nothing is written")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    from app.database import SessionLocal, engine

    try:
        name = check_target(engine.url)
    except RefusedTarget as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    missing = [
        label
        for label, value in (
            ("--ss-base-url / STAGING_SS_BASE_URL", args.ss_base_url),
            ("STAGING_SS_API_KEY", os.environ.get("STAGING_SS_API_KEY")),
            ("STAGING_ADMIN_PASSWORD", os.environ.get("STAGING_ADMIN_PASSWORD")),
        )
        if not (value or "").strip()
    ]
    if missing:
        print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
        return 2

    cfg = SeedConfig(
        ss_base_url=args.ss_base_url.strip(),
        ss_api_key=os.environ["STAGING_SS_API_KEY"].strip(),
        admin_password=os.environ["STAGING_ADMIN_PASSWORD"],
        push_key=(os.environ.get("STAGING_SS_PUSH_KEY") or "").strip() or None,
        company_code=args.company_code,
        company_name=args.company_name,
        admin_email=args.admin_email,
    )
    db = SessionLocal()
    try:
        report = seed(db, cfg)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    except RefusedTarget as exc:
        db.rollback()
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()

    print(f"database: {name} ({'APPLIED' if args.apply else 'DRY RUN, rolled back; add --apply'})")
    for line in report.lines:
        print(f"  - {line}")
    if report.minted_push_key and args.apply:
        print(f"\nSS push key (X-API-Key for SS -> CRM ingest), shown once:\n  {report.minted_push_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
