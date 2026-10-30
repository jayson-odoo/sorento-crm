# PLAN: PS-REGISTER-CHECK-FIRST (29 Oct 2026)

Status: Build. Mock v4 approved 30 Oct 10:27 (Spec In hidden at 0 documents), V1-V3 = (a); red tests being amended
to the final UAC; crew said build now (30 Oct), so merge origin/main and resolve once #1953 (PORTAL-P4-REQUESTS)
lands (it edits ProjectForm.tsx, projects.py, project_service.py). Track M (feature track, local lane; no schema).

Card: `CARD-ps-register-check-first-29oct.md`. UAC: `ps-register-check-first-acceptance-criteria.md` (written after
the owner answers the card). Mock: `documentation/mockups/PS-REGISTER-CHECK-FIRST/index.html`.

## Journey

Owner team meeting 29 Oct (Project Sales):

1. A salesperson registers a project themselves; the registration admin only approves or rejects.
2. The duplicate Check runs FIRST, before any other detail is typed (a wizard). A match collapses the form to one
   action: "Register as secondary lead" (today's "Register interest", renamed: owner Q1, no new concept, no second
   lead row). Management reviews competing secondary leads on the project.
3. A requirements document is part of the project record for the audit trail. Not required at register; required
   to move the project out of Registered (owner Q5: "it is required after registering, so the state moves one by
   one").

## Scope

1. Wizard on the register form: step 1 = title (+ AI extract) and a mandatory Check; step 2 opens only after a
   Check with no blocking match; a match collapses the form to "Register as secondary lead".
2. Rename "interest" to "secondary lead" everywhere it shows (form, dialog, Access panel, Reassign dialog,
   notifications).
3. "Requirements" document kind on the project; server guard: Registered -> next stage refused without one, plain
   message, upload shortcut on the stage action.

Out of scope: required-vs-optional registration fields (management confirms Mon 2 Nov; keep today's, keep the
step-2 field list easy to change); lead-name uniqueness (card Q-A).

## Architecture

- Layer: service. The gate lives in `change_status` (`BE/services/project_service.py:1380`), the one entry for manual
  stage moves, so API and any future caller get it; the first-PO automatic move (`project_po_service.py:209`) writes
  the status itself and stays ungated by design (Q-B a). One helper `has_requirements_document(db, project_id)` reads
  `entity_attachment_links` + `attachments` + `attachment_types.code`.
- Gate input: any live document linked to the project (owner, mock v3 note 3); no attachment type, no seed.
- Clash: one helper `assert_no_blocking_clash(...)` lifted from `register_project` (`project_service.py:283-303`) and
  called by `register_project`, `crm_register(submit=True)` and `crm_submit`. Same 409 and message for every caller
  (class: every path that turns a registration into a submitted one).
- Rename: strings only; stored `kind` and notification type keys unchanged.
- FE wizard: create-mode step state inside `ProjectForm` (no new form), `WizardSteps` + Create-lead footer pattern;
  step-2 sections stay today's JSX so Monday's required-field ruling stays a local change.
- FE gate: the header reads the document count from the Documents tab's query `['project-documents', id]` (shared
  cache): 0 documents on a Registered project -> "Upload Requirement" CTA, Spec In hidden; the upload invalidates the
  query and the header flips. The server 422 stays the backstop (toast). No new API field.
- Secondary leads table: `components/common/PanelDataGrid.tsx` (raw `components/ui/table` is barred by
  `components/ui/raw-table.inventory.test.ts`).

## Slices

1. BE gate + seed (AC-G1..G6, G9).
2. BE salesperson Check (AC-S1..S4).
3. Rename BE + FE (AC-R1..R5).
4. FE Upload Requirement CTA + dialog (AC-G7..G10).
5. FE wizard with Clash / No clash (AC-W1..W10).
6. FE secondary leads table (AC-R6) and tabs (AC-T1..T3).

## Test list

- BE (tester, red first): `tests/test_project_requirements_gate.py` (G1-G6, incl. first-PO move not gated),
  `tests/test_project_salesperson_submit_check.py` (S1-S4), notification wording (R1).
- Existing BE/FE tests that move Registered -> Spec In without a file will go red when the gate lands: the coder adds a
  Requirements file to their setup; assertions are not weakened.
- FE (vitest, red first, after v2): ProjectForm wizard (W1-W9), rename strings (R2-R5), stage action dialog (G7),
  upload kind (G8), tab order + legacy redirects (T1-T3).
- Global guards: none (no table, no list endpoint).
