# PLAN - Container Status workbook, per company

Status: complete (pending review)
UAC: `documentation/plans/purchasing/container-status-per-company-acceptance-criteria.md`
Classification: CORE (procurement base + resource library). No new module, no new schema.
`attachments.company_id` already exists; the one migration is a data backfill
(`323_cs_company_backfill`), not DDL.
Supersedes the "exactly one live row, globally" rule in
`documentation/plans/purchasing/PLAN-container-status-tracking.md`.

## The defect

`app/services/container_status_document.py:103 enforce_single_current` trashes every live
Container Status attachment except the single newest **across all companies**. Its UPDATE has
no company predicate, and being raw `text()` it is not reached by the global
`do_orm_execute` scope filter either. So a Mocha import soft-deletes Sorento's current
workbook out of the library, the MCP document tool, and entity resolution.

Publication is already company-correct: `publish_import_source` stamps `company_id` from the
import job's company snapshot (`app/models/job.py:47`). The bug is entirely in what happens
immediately afterwards.

`latest_document` (same file, line 256) has the same shape of bug for reads: raw SQL, no
company predicate, so `GET /procurement/packing-lists/container-status/latest` serves whichever
workbook is newest globally.

## What already works, and must not be rebuilt

Established by reading the code, not assumed:

- **Contact -> company is an explicit admin-managed M2M**: `respond_contact_companies`
  (`app/models/company.py:57-73`). A contact can belong to Sorento, Mocha or both.
- **Request-entry resolution already exists**: `app/services/company_scope_resolver.py`,
  attached to every `/api/v1/*` route at `app/main.py:213-214`. A JWT user resolves to
  `frozenset({active_company})`; an `X-API-Key` call carrying `contact_id` + `space_id`
  resolves to `frozenset(contact's companies)`; no contact params means `None` (all
  companies, backward compat); no principal means `UNSET` (fail-closed).
- **ORM SELECTs are auto-filtered** by `do_orm_execute` (`app/services/company_scope.py`).
  `Attachment` is `CompanyScopedMixin` with `__company_shared__ = True`, so the predicate is
  `company_id IS NULL OR company_id IN (scope)`.
- **Raw SQL has a sanctioned escape hatch**: `company_sql_predicate`
  (`app/services/company_scope_sql.py`), already used by the resolver's trigram tiers.
- **Entity resolution already attributes attachments to a company**: `attachment` is in
  `_company_scoped_models()` (`app/services/entity_resolver.py:3664-3696`), and
  `_attach_company_info` stamps `company_id` / `company_name` on every match and drops
  out-of-scope ones. Pattern pinned by `tests/test_resolve_entity_company_attribution.py`.

So AC-C1 is mostly a consequence of fixing AC-A1: today only one row survives globally, so
resolve has only one row to find. There is one genuine gap on that path (see change 3).

`access_levels` is a separate axis (contact access types) and is NOT touched by this work.

## Changes

### 1. `enforce_single_current` becomes per-company - `app/services/container_status_document.py`

Rank within each company and keep rank 1:

```sql
UPDATE attachments
SET is_deleted = true, deleted_at = :now
WHERE id IN (
    SELECT id FROM (
        SELECT a.id,
               ROW_NUMBER() OVER (
                   PARTITION BY a.company_id
                   ORDER BY a.uploaded_at DESC, a.id DESC
               ) AS rn
        FROM attachments a
        JOIN attachment_types t ON t.id = a.attachment_type_id
        WHERE (t.code = :code OR t.type_name = :name)
          AND a.is_deleted = false
    ) ranked
    WHERE ranked.rn > 1
)
```

Properties kept deliberately:

- **Newest-survives, not caller-names-the-keeper.** Re-publishing an older job must never
  promote a stale sheet. Unchanged.
- **`a.id DESC` tie-breaker.** Two workbooks committed in the same transaction share
  `uploaded_at` to the microsecond; without the tie-breaker the survivor is whichever the
  planner emits first.
- **Idempotent**, now per company: after one run every company has exactly one live row, so
  a second run trashes nothing and returns 0.
- **Soft delete only.** Rows and bytes stay recoverable; import jobs untouched.

**No session-scope filter here, on purpose.** This is a global invariant sweep, not a read.
It runs post-commit in the RQ worker under the single importing company's scope, and it has to
hold as a global invariant whoever runs it. Partitioning gives the right answer under every
scope, and a scope-filtered variant would silently stop being idempotent for the other
companies. `company_sql_predicate` is for reads that must respect the caller; this is not one.

`PARTITION BY company_id` groups all `NULL`s together, so a NULL-company workbook is ranked
only against other NULLs: one of them stays live and a company's upload never trashes it
(AC-A5). After change 1b that is defensive leftover rather than an expected steady state -
publication cannot write a NULL and the migration stamped the existing ones - but the
partition stays so a stray NULL is contained instead of colliding with a real company's
current sheet.

**Rewrite the docstring** and the module docstring paragraph at
`container_status_document.py:22-27`: both currently state the single-global-workbook design
being removed here.

### 1b. A published workbook can never have a NULL company - same file, plus a migration

Per-company ranking is only sound if every live row actually names a company.
`Attachment.__company_shared__ = True`, so the scope predicate is
`company_id IS NULL OR company_id IN (scope)`: a live NULL-company workbook is visible to
EVERY company at once, and because `PARTITION BY company_id` ranks NULLs only against each
other, no company's future import can supersede it. A single-company caller then resolves TWO
workbooks, one labelled Sorento and one labelled nothing - verbatim the ambiguity this change
exists to remove. It is reachable in production two ways:
`JobService.active_company_id_from_scope` (`app/services/job_service.py:38-43`) snapshots NULL
for an import enqueued under a `None`/`UNSET` scope (the n8n / X-API-Key path), and migration
302's attachment backfill only stamped rows with a directory or a product/promotion/shipment
link, which a published container status row has none of.

Fixed at the source rather than ordered around:

- **`publish_import_source` COALESCEs onto `DEFAULT_COMPANY_ID`** (imported from
  `app.services.company_scope`) instead of inserting the import job's raw `company_id`
  snapshot. A container status workbook is an OWNED operational document, not a shared form
  attachment, so NULL is never the right answer for it; the codebase already says a
  `None`-scope owned write belongs to the incumbent company (`resolve_write_company_id`, and
  migration 306's DB DEFAULT on the owned tables), and this follows that same rule.
- **Migration `323_cs_company_backfill`** stamps `company_id = Sorento` on every existing
  `attachments` row of the Container Status type (joined via `attachment_types` on
  `code='container_status' OR type_name='Container Status'`) that is still NULL. Idempotent;
  a row already attributed to another company is left alone; `is_deleted` is untouched, so
  rows the old global rule trashed stay trashed and merely get attributed. `downgrade()` is an
  explicit no-op - nulling the column back would re-create the defect on real data and there
  is no way to tell a row this stamped from one a Sorento import stamped legitimately.

Two consequences of stamping a real company that the NULL partition had been hiding:

- **The "already published" probe must match trashed rows.** It carried
  `AND is_deleted = false`, so once `enforce_single_current` had trashed a published row, a
  re-run of that job matched nothing, fell through to the INSERT, and wrote a SECOND row for
  the same storage key with `uploaded_at = now()`. That stale sheet then ranked newest in its
  partition and trashed the company's genuine current workbook - the exact inversion
  `enforce_single_current`'s docstring claims is impossible. While unstamped rows landed in
  the inert NULL partition this was invisible; stamping the incumbent aims it at real data.
  The live filter is dropped so the probe matches whatever the row's state, and a trashed
  match is returned as-is. It is deliberately NOT restored: it was trashed because a newer
  workbook superseded it, or because someone trashed it on purpose, and an old job re-running
  must not undo either.
- **The incumbent fallback is logged.** `JobService.active_company_id_from_scope`
  (`app/services/job_service.py:22-43`) snapshots NULL for FOUR scopes - `None`, `UNSET`,
  empty frozenset and multi-company - plus a bare `except Exception: return None`, whereas
  `resolve_write_company_id` returns the incumbent only for `None` and raises for the rest.
  So a Mocha-only user with no `last_active_company_id` resolves to `UNSET` and their workbook
  publishes as Sorento's. The proper fix belongs at enqueue and is out of scope here; what is
  in scope is making it diagnosable, so the publish warns when the job carried no company
  snapshot and the success log now names the company. **Follow-up worth a ticket:** narrow
  `active_company_id_from_scope` so an ambiguous scope fails the enqueue rather than
  snapshotting NULL.

### 2. `latest_document` becomes company-aware - same file, and the route

- Splice `company_sql_predicate(db, "a.company_id", shared=True)` into the WHERE.
- `LEFT JOIN companies c ON c.id = a.company_id`; return `company_id` and `company_name` in
  the dict.
- `ORDER BY (a.company_id IS NULL) ASC, a.uploaded_at DESC, a.id DESC` - a workbook actually
  owned by the caller's company beats a legacy unstamped one regardless of age (AC-B4).
  Without this the shared-NULL branch of the predicate lets a legacy sheet outrank the
  company's own.
- `GET /procurement/packing-lists/container-status/latest`
  (`app/api/v1/procurement/packing_lists.py:81`) needs **no signature change**: the
  router-level `apply_company_scope` dependency has already pinned the session to the caller's
  active company, which is exactly how the rest of procurement scopes requests (e.g.
  `suppliers.py` issues a bare `db.query(Supplier)` and relies on the same mechanism).
  Add `company_id` + `company_name` to the response body (AC-B2). Keep the 404 copy as-is.

### 3. Company attribution on the domain-hint resolve path - `app/api/v1/system/references.py`

`_resolve_with_domain_hint` (~line 105-195) is the short-circuit a document request
actually takes (`domain_hint="container status"`), and it builds its own match dicts with no
company on them. Its ORM query is already scope-filtered, so it returns both companies' rows
once change 1 lands - they are just indistinguishable.

Add `Attachment.company_id` to the select, `LEFT JOIN Company`, and emit `company_id` +
`company_name` **at the match level** (mirroring `entity_resolver.py:3502-3542`, not a new
shape) as well as inside `display` for renderers that only read `display`.

Nothing else on the resolve path changes. `_attach_company_info` already covers the main
probes (`_probe_attachment`, `_prefix_probe_attachment`, `_and_probe_attachment`).

### 4. The document surface shows which company - backend + MCP

- `AttachmentResponse` (`app/schemas/resources.py:302`) gains `company_id` and
  `company_name`. Per the DoD gate, add the fields to **every manual dict builder** in
  `resources_service.py` that constructs an attachment payload, not just the schema -
  inheritance alone silently drops them.
- MCP presenter `_resource_attachments`
  (`sorento_crm_mcp/sorento_crm_mcp/presenters.py:711`) adds a `Company` line to each item,
  emitted only when present so a shared/company-less file renders no empty line (AC-D3). This
  is the fix for "two files with identical names": the render deliberately withholds the UUID
  from the customer-facing answer, so the company name is the only handle left. Coder must
  confirm the field survives `_sanitize_tool_response` / any field allowlist in
  `server.py`.
- **The frontend file library gets no company column, deliberately.** A staff session always
  resolves to exactly ONE active company (`_resolve_user_scope`), so the library can never
  show two companies' currents side by side; a column would be a constant. The confusing case
  is the multi-company CONTACT going through MCP, which is what the presenter change covers.

## Tests (Postgres only, `tests/_pg_fixture.blank_session`)

Extend `tests/test_container_status_document.py` (its `_workbook` helper takes a
`company_id`; existing company-less cases keep working as the NULL partition):

- Mocha import leaves Sorento's current live - both rows live afterwards (AC-A1).
- Three workbooks in one company collapse to the newest; the other company's row untouched
  (AC-A2).
- Identical `uploaded_at` within one company - higher `id` survives, other company unaffected
  (AC-A3).
- Second run trashes 0 (AC-A4).
- Legacy NULL rows rank only against each other and survive a company upload (AC-A5).
- `latest_document` under `frozenset({mocha})` returns Mocha's; owned beats legacy NULL
  (AC-B1/B4); returns None when neither exists (AC-B3).

New `tests/test_container_status_resolve_two_companies.py`:

- Seed Mocha + a contact granted both companies via `respond_contact_companies`, one current
  workbook per company, session scope `frozenset({sorento, mocha})` -> resolve returns TWO
  attachment matches with distinct `company_id` / `company_name` (AC-C1/C2), through the
  domain-hint short-circuit path as well (AC-C3).
- Single-company contact gets exactly one match, its own (AC-C4).

Route test for `GET .../container-status/latest` returning the active company's workbook.

`tests/test_container_status_parser.py` is not modified: parsing, including the joint
"Arrived - Joint Mocha Container" tabs, is out of scope for this change.

## Operational note for the PR / support

**A no-contact `X-API-Key` caller now gets one workbook PER COMPANY.** Passing no `contact_id`
/ `space_id` resolves to scope `None` (all companies), which used to see exactly one workbook
globally because only one existed. Per-company currents means that caller now sees N, so
`resolved` flips `true` -> `false` and `ambiguous` `false` -> `true` on that path. That is
intended, not a regression: an all-companies caller must pass contact identity to get a single
answer. JWT sessions are unaffected - they are always pinned to one active company.

Any Container Status workbook that the OLD global rule already soft-deleted stays in the
trash. This change does not resurrect it and deliberately does not try to guess which company
it belonged to. **A company whose workbook was trashed by another company's upload must
re-upload its workbook once**; from then on each company keeps its own current and the two
can never collide again. The trashed rows remain recoverable from Resource Management ->
Trash if support prefers to restore rather than re-upload.
