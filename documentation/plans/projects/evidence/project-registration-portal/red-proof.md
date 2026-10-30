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

Run by the `reviewer` agent in its own throwaway worktree (never the shared tree), each mutation reverted afterwards.
"Caught" names the test that went red; "SURVIVED" means no test failed.

### Phase 2 (head c3f78c24, before fix round 1; reviewer report 1)

| Mutation | Caught by |
|---|---|
| `skip_clash_check=True` -> `False` in approve | test_b6_a_blocking_spelling_clash_never_blocks_the_queue (+ b7) |
| IntegrityError mapping removed | test_b7_an_exact_same_developer_and_title_is_409_naming_the_project, test_b7_..._after_the_title_changes |
| SAVEPOINT removed | both b7 tests |
| Number drawn on submit | test_c4_submitted_and_rejected_registrations_draw_no_number |
| Not-pending guard removed | test_b8_approve_or_reject_a_non_pending_registration_is_409 |
| `require_form_visible` dropped from `_check_kind` | test_a1_no_grant_is_403..., test_a1_every_route_is_gated... |
| `contact_id` filter dropped from `_own` | test_a7_another_contacts_registration_is_404_everywhere |
| `_missing` returns `[]` | test_a8_submit_lists_the_missing_fields..., test_a8_only_the_blank_one_is_named |
| `>=` -> `>` on the semantic threshold | test_d5_a_cosine_at_or_above_the_bar_names_the_project |
| `{mm}` not zero-padded | 4 tests in test_numbering_mm_token.py |
| Migration `PRJ-` guard removed | test_c2_a_customised_rule_is_left_alone |
| All company filters removed | test_d6_another_companys_project_is_never_named |
| One redundant company filter removed | SURVIVED (redundant layers, not a gap) |
| FE: developer-required guard removed | "Approve with no developer shows the field error..." |
| FE: Check button shown in review | "has no Check button, no clash panel..." |
| FE: duplicate link uses the code, not the id | B3/G2 list link test; review "Possible duplicate line links every project..." |
| FE: `!isReview` removed on ClashWarningPanel | SURVIVED (equivalent mutation: the panel cannot appear without the Check button) |

(The lot / sibling / mukim mutations of that pass guarded rules that audit round 3 removed.)

### Fix rounds 1 and 2 (reviewer reports 2 and 3)

| Mutation | Caught by |
|---|---|
| Lead rule seeded back to `monthly` | test_b2_the_lead_rule_keeps_reset_none_and_the_project_rule_is_monthly |
| One embed call per row again | test_b3_a_list_of_pending_rows_makes_one_embed_call_at_three_seconds, test_b3_a_failing_embed_..._not_retried_per_row |
| Embed timeout 3 s -> 30 s | test_b3_a_list_..._at_three_seconds |
| Embedding cache disabled | three test_b3_* |
| Ownership check builds duplicates | test_b3_ownership_checks_never_build_the_duplicates |
| Comments accepted for the kind | test_s4_the_kind_has_no_comments |
| Attachments accepted for the kind | test_s5_attachments_are_refused_for_the_kind |
| Row lock dropped (approve; reject) | test_s6_..._with_a_row_lock (both) |
| Project / profile listener queues on every update | test_s8_only_a_title_or_developer_change_queues..., test_s8_the_profile_queues_the_parent_only... |
| Manage check removed from the owner rule | test_s9_another_owner_needs_the_manage_grant |
| Applicant made to need manage | test_s9_the_applicant_may_own_it_without_the_manage_grant |
| Owner eligibility removed | test_s9_an_owner_with_no_access_to_the_company_is_422, test_s9_an_inactive_owner_is_422 |
| `_check_company_refs` skipped | test_s10_a_party_type_or_template_of_another_company_is_422 |
| Customer lookup not limited to the registration's company | test_s11_the_customer_is_checked_under_the_registrations_company_only |
| Drafts back in `status=all` | test_n12_status_all_leaves_the_contacts_unsent_drafts_out |
| Title length bound removed | test_b1_a_title_over_2000_..., test_b1_submit_carrying_a_long_title_... |
| Owner fallback removed / widened | test_r2_an_ineligible_applicant_falls_back_to_the_approver_without_manage; test_s9_an_owner_with_no_access..., test_s9_an_inactive_owner_is_422 |
| FE: Comments tab / Attachments card / AI attach shown | "a submitted registration shows no Comments tab", "shows no Attachments card on a draft", "AI Extract is told it cannot attach" |
| FE: owner select always enabled | "is disabled without projects.projects.manage and keeps the applicant" |
| FE: PPF meta not a link | "the PPF code in the meta line is a link to the project" |
| FE: rejected labelled Draft / badge / delete for rejected / PPF on card / State+Mukim on overview | the five round-2 FE tests (landing-fields, detail badge, no delete, ppf_no, ProjectDetailClient) |

Nothing survived in these rounds.

### Audit round 3 (head 65e36bb7; reviewer report 4: 42 mutations, 41 caught)

| # | Mutation | Caught by |
|---|---|---|
| 1 | Spelling (trigram) fallback re-added | test_the_service_no_longer_reads_the_spelling_matcher; test_same_lot_and_mukim_without_a_meaning_match_is_not_named; test_a_spelling_near_title_without_a_meaning_match_is_not_named; test_a_title_equal_to_a_project_without_a_meaning_match_is_not_named; test_a_phase_sibling_without_a_meaning_match_is_not_named |
| 2 | Semantic threshold dropped | test_d5_a_cosine_below_the_bar_does_not |
| 3 | Company filter dropped from the meaning lookup | test_d6_another_companys_project_is_never_named |
| 4 | Strongest-first order reversed | test_d6_strongest_meaning_first_without_repeats; test_d6_the_cap_is_five_and_limit_is_honoured |
| 5 | Embedding back-off removed | test_b3_a_failing_embed_keeps_the_other_signals_and_is_not_retried_per_row |
| 6-8 | Debtor lookup ignores kind / agent filter / search text | test_the_debtor_lookup_for_this_kind_returns_only_the_agents_own_debtors; test_every_debtor_the_lookup_offers_is_accepted_by_the_save; test_the_debtor_lookup_for_this_kind_follows_the_search_text |
| 9-15 | Rate limits removed, mis-keyed, off by one, failing closed | test_the_31st_save_in_an_hour_is_429_rate_limited_and_every_verb_counts; test_a_submit_over_the_limit_is_refused_and_the_draft_stays_a_draft; test_reads_and_other_contacts_are_not_limited; test_the_11th_ai_extract_in_ten_minutes_is_429; test_the_ai_extract_limit_is_this_forms_only; test_the_ai_extract_limit_is_per_contact; test_the_save_limit_fails_open_when_redis_is_down |
| 16-17 | Submit notice emailed / decision notices not emailed | test_submit_notifies_approvers_in_app_only_never_by_email; test_approve_and_reject_still_notify_the_applicant_in_app_and_by_email; test_an_approve_notice_is_in_app_and_email_to_the_applicant |
| 18 | M1 text-type check removed | test_m1_a_non_string_value_is_422_naming_the_field_never_500 |
| 19 | portal-client drops `&kind=` from the debtor URL | SURVIVED (fixed in round 3b: a portal-client URL test) |
| 20 | M2 whitespace collapse removed | test_a_title_with_newlines_and_tabs_gives_a_one_line_notice_title; test_a_decision_notice_title_is_one_line_too |
| 21 | 409 without `details.existing_project` | test_the_exact_duplicate_409_carries_the_existing_project_as_data |
| 22-23 | Downgrade guard dropped / restores nothing | test_downgrade_leaves_a_customised_rule_alone; test_downgrade_leaves_a_ppf_rule_someone_changed_since; test_downgrade_restores_the_default_project_rule_where_it_is_still_the_ppf_shape |
| 24-26 | Approver-role grant ignored / old name match / every role | (then) test_the_permission_goes_to_the_admin_roles_and_the_one_named_approver_role; test_with_no_role_of_that_name_only_the_admin_roles_hold_the_permission. Renamed in 0fa8bc03 for the two-role ruling; re-checked by the captain: dropping Coordinator from APPROVER_ROLE_NAMES turns test_the_approver_roles_are_both_named_in_one_constant_of_the_migration red |
| 27-28 | FE: customer picker free text / blur reset removed | "the Customer name picker takes a pick only: typed free text is not kept" |
| 29 | FE: lookupKind not passed | "asks the lookup for this kind, so only the agent's own debtors are offered" |
| 30-31 | FE: Date unformatted / not shown | "shows a read-only Date, the submitted date as DD/MM/YYYY" |
| 32-34 | FE: review shows project type / company / brands again | the two review-trim tests |
| 35-36 | FE: existing-project link removed / not parsed | "shows "Already registered as <code> <title>" ... link"; the two existingProject service tests |

### Round 3b (head 6a0a9ed4; reviewer report 5: READY)

| Mutation | Caught by |
|---|---|
| Downgrade `next_value` uses LEAST instead of GREATEST | test_downgrade_keeps_the_counter_past_every_existing_prj_code |
| Downgrade max PRJ code without the +1 | test_downgrade_keeps_the_counter_past_every_existing_prj_code |
| Downgrade keeps `last_reset_key` | SURVIVED (equivalent: with reset `none` the key is never compared) |
| Downgrade `GREATEST(1, max+1)` instead of `GREATEST(next_value, max+1)` | SURVIVED (only reuses codes that no longer exist; no collision) |
| Portal Date cut from the UTC string | "a submission at 17:30 UTC on the 24th reads 25/10/2026" |
| Portal Date shown raw | same test + "shows a read-only Date, the submitted date as DD/MM/YYYY" |
| portal-client drops `&kind=` (the round-3 survivor) | "lookupDebtors > asks with kind=project_registration when the form passes it" (also checked by the captain) |
