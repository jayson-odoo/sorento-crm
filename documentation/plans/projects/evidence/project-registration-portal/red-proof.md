# Red proof (retroactive) for PROJECT-REG-PORTAL

Evidence only: each lane test file was run on the commit BEFORE the code it tests, in a throwaway
`git worktree` (not the shared tree), against the Postgres sandbox. A worktree was removed after use.
Backend command shape (from the worktree's `sorento_crm_backend`):
`SORENTO_ENV_FILE=.env.ci-tests <shared venv>/bin/python -m pytest tests/<file>.py -q -p no:warnings --tb=line`.
Frontend: `npx vitest run <files>` with the shared `node_modules` linked in.

## (a) Backend lane tests on origin/main (537a9df3)

Test files copied from head 37421af5: the portal, review, duplicates, round1 suites, the support
module, `test_numbering_mm_token.py` and the migration test.

| File | Result on main | Representative failure |
|---|---|---|
| test_project_registration_portal.py | 34 failed, 1 passed | `Unsupported submission type: 'project_registration'.` (400) in 24 tests; `Unknown form_key: portal.project_registration` in 2 |
| test_project_registration_review.py | 26 failed, 1 passed | `Unsupported submission type` (via the portal helper) in 22; `register_project() got an unexpected keyword argument 'skip_clash_check'` |
| test_project_registration_duplicates.py | 20 failed | `ModuleNotFoundError: No module named 'app.services.project_registration_service'` |
| test_project_registration_round1.py | collection error | `ImportError: cannot import name 'project_registration_service' from 'app.services'` |
| test_numbering_mm_token.py | 4 failed, 2 passed | `KeyError: 'mm'` at `numbering_service.py:78`; seed rule `assert 'PRJ-' == 'PPF{yy}{mm}'` (the 2 passes are the unchanged-token and never-overwrite guards) |
| test_migration_prreg_0001_project_registrations.py | 11 failed | `FileNotFoundError: .../alembic/versions/prreg_0001_project_registrations.py`; `No module named 'app.models.project_registration'` |

(A first attempt hit `Connection refused` because the sandbox Postgres had stopped; it was restarted
and the table above is the clean second run.)

## (b) Phase 1 front end: tests (3bab9386) on the commit before the code (959b2817)

Code commit e81a5a51 landed before its tests, so the four FE test files from 3bab9386 were copied onto
959b2817 and run:
`npx vitest run services/projectRegistrationService.test.ts "app/(auth)/portal/components/SubmissionForm.projectRegistration.test.tsx" "app/(protected)/project-sales/registrations/components/ProjectRegistrationsList.test.tsx" "app/(protected)/project-sales/_shared/components/ProjectForm.review.test.tsx"`

Result: 4 files failed, 7 tests failed.
- `projectRegistrationService.test.ts`: `Failed to resolve import "./projectRegistrationService"`.
- `ProjectRegistrationsList.test.tsx`: `Failed to resolve import "./ProjectRegistrationsList"`.
- `ProjectForm.review.test.tsx`: `Failed to resolve import "../../registrations/components/ProjectRegistrationReview"`.
- `SubmissionForm.projectRegistration.test.tsx`: 7 of 7 fail, `TypeError: Cannot read properties of undefined (reading 'filter')` (no field list for the kind).

## (c) Round 2 tests on their parent (c8df57c6)

Backend, 26881941 (`test_r2_an_ineligible_applicant_falls_back_to_the_approver_without_manage`, file taken from 26881941):
`pytest tests/test_project_registration_round1.py::test_r2_an_ineligible_applicant_falls_back_to_the_approver_without_manage`
-> 1 failed: `assert 422 == 200`, body `{"code":"project_registration_owner_invalid","message":"That salesperson cannot own a project of this company."}`.

Front end, 4288f37b test files on c8df57c6 (3 files): 6 failed, 28 passed.
- landing-fields.projectRegistration.test.ts: "reads Rejected although it is still editable" red, "a real draft still reads Draft" red (`isShownAsDraft` is not exported), "the landing fields carry ppf_no and read the value" red.
- SubmissionForm.projectRegistration.round1.test.tsx: "badges a rejected registration Rejected, not Draft" red; "does not offer to delete a rejected registration, the server refuses it" red.
- ProjectDetailClient.test.tsx: "shows State and Mukim as facts of the development" red.

## (d) Round 1 tests on their parent (c3f78c24)

Backend (43ba4597 `test_project_registration_round1.py` + support on c3f78c24): 21 failed, 5 passed, 3 errors.
Failure lines include: `module ... has no attribute 'MAX_LOT_NUMBERS'`, `... no attribute 'clear_embedding_cache'`
(4 tests, 3 of them setup errors), `assert 3 == 2`, `assert 2 == 1` (embed calls per list), `RuntimeError: bad row`
(unguarded lot parse), and the named tests: title over 2000, long title on submit, zero-padded lot, lot pattern cap,
failing lot read, lead/project rule shape, embed failure not retried per row, ownership checks building duplicates
(`AssertionError: the duplicates were computed for an ownership check`), no comments, no attachments, row lock on
approve/reject, mukim stop words, listener churn (2), owner needs the manage grant, owner without company access,
inactive owner, party type or template of another company, customer checked under the registration's company, and
`status=all` leaving unsent drafts out.

Front end (5775adf4 files on c3f78c24: SubmissionForm.projectRegistration.round1, ProjectForm.review.round1,
ProjectForm.review): 7 failed, 19 passed:
a 409 exact duplicate shows its message (the one-surface change), a submitted registration shows no Comments tab,
no Attachments card on a draft, AI Extract is told it cannot attach, the owner select is disabled without
projects.projects.manage, a refused approval is toasted by the hook and not repeated inline, the PPF code in the
meta line is a link to the project.

## Kill proof

The reviewer's kill-test tables (mutation, test that must fail, observed) are not in this repository; they
were reported in the review thread. This section is a placeholder until the coordinator supplies them.
