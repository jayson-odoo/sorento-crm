# PLAN: Register a CRM project in AutoCount (AC-PROJECT-REGISTER)

Status: Build - answers in (13 Nov); red tests next. Track: M (one additive
migration on `projects`; reuses the AC-QTSO-CRM write path, permission and dialog). Size from brief: M.

Owner, 13 Nov: "our project need to integrate with autocount to register a project in autocount,
the endpoint will be provided by autocount next week" ... "for autocount project registration ok"
(= build the CRM side now). UAT Wed 18 Nov shows the CRM flow with the AutoCount call pending.

## Reuse (discovery, file:line)

| Piece | Existing function | Use |
| --- | --- | --- |
| SS client, key, X-Request-ID + actor headers | `app/services/foundryx_autocount_client.py:259` `write()`, `:123` `trace_writes()` | reuse as is |
| Create that may land twice: write-ahead key, refusal releases, unknown keeps and re-sends the same key, row lock | `app/services/project_autocount_write_service.py:422` `_create()` | reuse as is (needs `autocount_pending_create` + `autocount_doc_key` on the record) |
| Every call logged + audit row with the person | `project_autocount_write_service.py:378` `_log_unlanded()` | reuse as is |
| SS answer -> plain words (refused / unreachable / pending / switched off) | `project_autocount_write_service.py:574` `_interpret()` | reuse as is |
| Capabilities read (op enabled or "Waiting for AutoCount") | `project_autocount_write_service.py:481` `_read_capabilities()` | extend: add `projects` kind to `_KINDS` |
| Book rule (no write without a book) | `project_autocount_write_service.py:519` `_no_book_answer()` | reuse |
| Route guard order: permission -> switch -> record -> SS | `app/api/v1/projects/project_autocount_write.py:69-91` | reuse `_assert_project_access`, `_guard`; add one route |
| Permission | `projects.autocount.write` (`app/rbac/permission_registry.py:743`) | reuse |
| FE hooks / button / result dialog | `project-sales/_shared/hooks/useProjectAutocountWrite`, `_shared/components/AutocountWriteButton`, `AutocountWriteDialog` | reuse; add one mutation hook |
| AutoCount number badge in a header | `QuotationDocumentPageHeader.tsx:113` | same Badge pattern |
| Project header gear menu | `ProjectDetailClient.tsx` `DetailActionsMenu` (~line 380) | add one item |

## Behaviour card

Posted as `crew-ask` on the PR; answers are folded back here before any code.

Answers (crew, 13 Nov, decided from owner rules): Q1 (a) send the CRM project code, store what
AutoCount answers; Q2 (a) approved and not lost only; Q3 (a) new switch "AutoCount project
registration", OFF; Q4 (a) gear-menu item + AutoCount number badge; Q5 (a) one-shot, no automatic
edits. UAC: `ac-project-register-acceptance-criteria.md` (R1-R18).

Changed from the card: no local length check on `projNo`. AutoCount's limit is not known until
the endpoint arrives; a too-long code comes back as AutoCount's own refusal (plain reason, Try
again), which the retry rule already covers. Add a local check only if the endpoint documents one.

## Design

### Backend
- Migration (one, additive, nullable, no backfill):
  - `projects.projects`: `autocount_doc_no` String(80), `autocount_doc_key` String(80),
    `autocount_book` String(40), `autocount_pending_create` JSONB, `autocount_registered_at`
    DateTime. Names match `ProjectQuotationDocument` so `_create()` works on a project as is.
  - `system_settings.project_autocount_register_enabled` Boolean NOT NULL default false.
- `app/services/project_autocount_register_service.py`: `ProjectAutocountRegisterService`
  subclasses `ProjectAutocountWriteService` (reuses `_create`, `_interpret`, `_log_unlanded`,
  `read_capabilities`, `_no_book_answer`, `_key_of`).
  - `PROJECTS_PATH = "documents/projects"` and `build_project_body()`, both marked
    `# STUB until the AutoCount endpoint (owner 13 Nov)`.
  - `_KINDS` gains `"projects": "projects"` (GUESS of the SS capability kind name; STUB).
  - `status(project_id)`, `register(project_id, actor)`.
  - Activity rows through `project_activity_service.record_project_event` (body_text, no new
    template mapping on the FE: `ProjectActivityPanel.describe` shows the saved sentence).
- Routes `app/api/v1/projects/project_autocount_register.py`, mounted beside
  `project_autocount_write`: `GET|POST /project-sales/{project_id}/autocount-register`. Guard
  order: permission `projects.autocount.write` -> switch -> project (404) -> write access ->
  eligibility (409) -> SS.
- Settings: the column in `SystemSettingUpdate`, the admin GET dict, `AppConfigResponse`, and the
  null->false list (`settings.py:139,297,492,637,1254`).
- Project detail: `autocount_project_no`, `autocount_registered_at` in the project dict
  (`project_service.py:~870`) and its response schema.

### Frontend
- Settings: one toggle beside "AutoCount quotations and sales orders from Project sales"
  (`user-management/settings/page.tsx`, `forms/general-settings-schema.ts`, `app/models/system.ts`).
- `_shared/services/projectAutocountWriteService.ts`: `getAutocountRegisterSwitch`,
  `getProjectAutocountRegister`, `registerProjectInAutocount`.
- `_shared/hooks/useProjectAutocountWrite.ts`: `useAutocountRegisterAccess`,
  `useProjectAutocountRegister`, `useRegisterProjectInAutocount` (same `useAutocountWrite`).
- `ProjectDetailClient.tsx`: gear item + Badge + `AutocountWriteDialog` for the answer.

## Standing rules that apply
- One main button per page (gear item, not primary).
- Failed ERP writes retryable: refusal releases, only success locks, unknown re-sends the same key.
- ERP writes behind an admin switch OFF by default; OFF = screen exactly as before; every call logged.
- Every tracked action shows in the record's history (Activity feed row).
- Plain words, no internal ids or codes; nothing hangs (dialog always ends in an answer).
- Reuse functions (table above).

## Assistant coverage
n/a: ERP writes are press-only behind an admin switch (owner rule); the AC-QTSO-CRM write actions
are not assistant actions either. The project's AutoCount number rides on project detail, which
the assistant already reads.

## Migration timing
Additive nullable columns + one boolean with a constant default: metadata-only on Postgres 11+.
Timed on a sandbox copy (result in the PR).
