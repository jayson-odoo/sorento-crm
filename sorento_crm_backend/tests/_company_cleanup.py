"""Shared teardown for suites that hard-delete their own throwaway ``companies`` rows.

App startup runs ``project_seed_service.run`` for EVERY company (``app/main.py``), and its
per-company step seeds ``projects.types`` -> ``projects.templates`` -> ``projects.template_roles``.
Under xdist another worker can boot a TestClient while this suite's throwaway companies exist,
so those rows get seeded for companies the suite is about to delete, and the teardown's
``DELETE FROM companies`` dies on ``types_company_id_fkey`` (CI run 34795397584, shard 4).

Raw SQL naming a ``projects`` table MUST be schema-qualified: the default search path is
``public``, where a core table of the same bare name may live (module docstring in
``app/models/projects.py``).
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

# Children before parents: template_roles -> templates -> types. These are the only tables
# the seeder writes per company_id (``seed_types_and_templates``); everything else it seeds
# is company-independent.
_PROJECT_SEED_TABLES = (
    "projects.template_roles",
    "projects.templates",
    "projects.types",
)


def delete_project_seed_rows(db: Session, company_ids: Sequence[str]) -> None:
    """Clear the project-sales seed rows for ``company_ids``, so the companies can be deleted."""
    ids = [str(cid) for cid in company_ids if cid]
    for table in _PROJECT_SEED_TABLES:
        for company_id in ids:
            db.execute(
                sa_text(f"DELETE FROM {table} WHERE company_id = :company_id"),
                {"company_id": company_id},
            )
