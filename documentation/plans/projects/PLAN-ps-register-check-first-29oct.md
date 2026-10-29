# PLAN: PS-REGISTER-CHECK-FIRST (29 Oct 2026)

Status: Build, BE red tests (owner answered Q-A..Q-E all (a) 30 Oct; mock v2 ask filed 30 Oct for the wizard + tabs
notes; FE slices W and T wait for v2 approval). Track M (feature
track, local lane; no schema: Requirements is an `attachment_types` row). Build waits for owner approval AND #1953
(PORTAL-P4-REQUESTS) merge. Merge origin/main again once #1978
(PS-WORDING) lands (both edit `ProjectForm.tsx`).

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
- Seed: `ensure_requirements_document_type` joins `project_seed_service.run` (startup, additive, idempotent), so the
  FE can resolve the kind by code before the first upload. Data, no schema.
- Clash: one helper `assert_no_blocking_clash(...)` lifted from `register_project` (`project_service.py:283-303`) and
  called by `register_project`, `crm_register(submit=True)` and `crm_submit`. Same 409 and message for every caller
  (class: every path that turns a registration into a submitted one).
- Rename: strings only; stored `kind` and notification type keys unchanged.
- FE wizard: create-mode step state inside `ProjectForm` (no new form), `WizardSteps` + Create-lead footer pattern;
  step-2 sections stay today's JSX so Monday's required-field ruling stays a local change.
- FE gate: the stage action catches 422 `project_requirements_missing` and opens the dialog; the server is the only
  judge (no new read field).

## Slices

1. BE gate + seed (AC-G1..G6, G9).
2. BE salesperson Check (AC-S1..S4).
3. Rename BE + FE (AC-R1..R5).
4. FE requirements dialog + upload kind (AC-G7, G8).
5. FE wizard (AC-W1..W10), after mock v2 approval.
6. FE tabs (AC-T1..T3), after mock v2 approval and V1-V3.

## Test list

- BE (tester, red first): `tests/test_project_requirements_gate.py` (G1-G6, incl. first-PO move not gated),
  `tests/test_project_salesperson_submit_check.py` (S1-S4), notification wording (R1).
- Existing BE/FE tests that move Registered -> Spec In without a file will go red when the gate lands: the coder adds a
  Requirements file to their setup; assertions are not weakened.
- FE (vitest, red first, after v2): ProjectForm wizard (W1-W9), rename strings (R2-R5), stage action dialog (G7),
  upload kind (G8), tab order + legacy redirects (T1-T3).
- Global guards: none (no table, no list endpoint).
