# PLAN: release sweep red on main 6e6657e2 (RELEASE-FIX-11NOV, 11 Nov 2026)

Status: done (PR #2325). Small fix track (tests only, no migration, no RBAC change).

## Failing on origin/main 6e6657e261 (passing at prod e731f224)

- tests/test_migration_354_projects_schema_move.py (3 tests): census of `projects`-schema tables
  - test_the_mapping_covers_exactly_the_models_that_declare_the_projects_schema
  - test_upgrade_moves_and_renames_when_the_tables_are_in_the_default_schema
  - test_the_index_rename_map_is_the_one_the_models_derive
- tests/test_migration_lec_0004_prompt_synonyms.py (3 tests): global `lookup_options` counts
  - test_a_type_matched_by_name_and_existing_option_and_keyword_are_reused_case_aside
  - test_a_label_with_no_attachment_type_is_skipped_and_no_type_is_created
  - test_with_no_types_at_all_no_option_is_created
- tests/chatbot/test_closed_lists_validate.py (1 test, found in review, same cause as lec_0004)
  - test_a_word_two_items_share_names_neither

## Approach

Reproduce on a throwaway DB, name the merge that broke each, fix the test side if the merged app
behaviour is right (code only if it is a real bug). No merged migration is changed.

## Findings

- 354: #2303 QUOTE-AUTOSAVE added `projects.quotation_document_drafts` and
  `projects.quotation_document_snapshots` (migration `qas_0001_quote_form_drafts`, born straight into
  `projects`). They are not in the test's `BORN_AFTER_THE_MOVE` set, so the census expects 354 to know
  them. Fix: add both to the set (same shape as #2263).
- lec_0004: #2300 PROJECT-PARTY-ROLES added an `after_create` listener in `tests/conftest.py` that seeds
  the `project_party_role` lookup set and its 8 options into every `create_all` schema, the blank scratch
  schema included. lec_0004 counted ALL `lookup_options` rows, so 0 became 8 and 1 became 9. The
  migration and the seed are both right. Fix: count only the options of the `attachment_type_alias` set.
- closed lists (review round 1): `query(LookupOption).one()` on the blank schema raised
  MultipleResultsFound for the same seed. It now picks its fixture option by value. lec_0004 also asserts
  the global option count moves only by the alias options, so a write into another set still fails.

## Evidence

- main 6e6657e261: the 3 files give 7 failed, 41 passed. Branch: 48 passed. Kill test (main's copies of the
  3 files put back on the branch): the same 7 fail.
- Migration pool as the sweep runs it (`tests/test_migration_*.py`, 135 files, `-p no:xdist`, bootstrapped
  throwaway DB): 354 and lec_0004 pass. 13 others fail on local-role limits only (a non-superuser cannot
  touch `pg_index` or `session_replication_role`, `audit_logs` is append-only, the local password's `%`
  breaks alembic config interpolation). None of those files is touched here.

## Round 2 (crew, 11 Nov: more items from the same sweep on 6e6657e2)

- #2303 guards: `QuotationDocumentDraft` / `QuotationDocumentSnapshot` were missing from `PURGE_ORDER`
  (`app/modules/projects/purge.py`). That is an APP gap: an uninstall-with-purge would have left both tables
  behind. Fix: add them, snapshots before drafts before the document; frontend manifest
  `sorento_crm_frontend/modules/projects/purge_tables.json` in the same order; the audit entity-type census
  (`tests/test_projects_audit_entity_types.py`) learns both as born after the move.
- #2301: the backend MCP catalog copy drifted. Fix: `cp sorento_crm_mcp/sorento_crm_mcp/catalog.py
  sorento_crm_backend/app/services/mcp_catalog_copy.py` (the step the test and the pre-push hook name).
- #2305: `tests/test_quotation_form_save.py` fake terms template gains `payment_term_id`, `validity_value`,
  `validity_unit` (read at `app/services/project_quotation_document_service.py:640-647`).
- #2305: `PaymentTerm.company_id` NOT NULL in the model to match `qts_0001` (`company_id UUID NOT NULL`), the
  override `sample_request.py:63` and `new_product_application.py:61` already carry. No migration change.
  Pinned by a new test in `tests/test_quote_terms_select.py`.
- #2304: vitest exited 1 on 2 unhandled `target.getClientRects is not a function` errors (ProseMirror's
  `scrollToSelection` measures a Range; jsdom has no layout). Fix: guarded `Range.prototype` stubs in
  `sorento_crm_frontend/vitest.setup.ts`.
- Evidence: main's copies of the 6 backend files give 6 failed (the listed tests); branch green. The
  vitest file exits 1 on main and 0 on the branch; the 42 test files that mount tiptap or measure rects
  give 617 passed, exit 0.
