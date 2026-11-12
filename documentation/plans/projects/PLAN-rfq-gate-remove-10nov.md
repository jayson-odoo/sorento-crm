# PLAN: RFQ-GATE-REMOVE - drop the hard-coded Upload Requirement gate

Status: PR #2308 open, review READY, awaiting owner hand test (small fix track: under 300 lines, no migration, no auth/RBAC change)

## Why

Owner, 10 Nov 2026: "remove upload requirement gate", and earlier: "don't need upload requirement
step already, I thought we reusing the status graph?". This reverses the 29 Oct meeting rule
"RFQ upload mandatory" that PS-REGISTER-CHECK-FIRST (#1991, `PLAN-ps-register-check-first-29oct.md`)
built (now `_archive/projects/`). The status graph (`statuses` / `status_transitions`, admin at /system-management/status-graphs)
already drives every other header button through `ProjectStatusAction`; this rung goes back to it.

## Change

- FE `ProjectDetailClient.tsx`: remove `needsRequirement` / `gatedOnDocument` / `awaitingDocuments`,
  the "Upload Requirement" header button and its dialog wiring, and the registered-only documents
  read. The header always renders `ProjectStatusAction` with the graph's moves; the gear lists
  every secondary move.
- FE `ProjectDocumentsPanel.tsx`: drop the now-unused `requirement` prop on `UploadDialog`.
- BE `project_service.py`: remove `_assert_requirements_uploaded` and its call in the move path,
  and `project_has_live_document` (no other caller).
- Documents tab and its upload are unchanged.
- User guide `documentation/user-guides/project-sales-rep/register-a-project.md` stops saying the
  upload is required.

## Acceptance

- AC-1. A Registered project with 0 documents shows Spec In in the header (no Upload Requirement).
- AC-2. Clicking Spec In on it moves the project (the move mutation is called).
- AC-3. API: registered -> specified with no document returns 200 and the project is on specified.

## Tests

- vitest `ProjectDetailClient.requirements.test.tsx` rewritten to AC-1/AC-2.
- vitest `useChangeProjectStatus.requirements.test.tsx`: the code no longer exists; removed.
- pytest `test_project_requirements_gate.py` rewritten to AC-3; `test_project_outcome_single.py`
  docstring/setup that relied on the gate updated.
