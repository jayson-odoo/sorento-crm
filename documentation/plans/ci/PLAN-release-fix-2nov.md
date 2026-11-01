# PLAN: RELEASE-FIX-2NOV (release tests red on main 41ef8f1c0a)

Status: PR #2083 open, reviewer READY, red/kill proof posted; crew labels and merges. Small fix track (no migration, no auth/RBAC change, no new behaviour, diff well under 300 lines).

Release run 41357449170 (full suite) is red on main 41ef8f1c0a. Fix only the listed failures (brief items 1-3, plus crew's item 4 from the finished shards).

## 1. Staff AI panel turn raises NameError (#2073)

`app/services/chatbot/agent/access.py::eligible_contact`, staff-principal branch, queries `User` / `UserStatus`, but #2073
moved `from app.models.user import User, UserStatus` into `linked_active_user`. Put the import back in `eligible_contact`'s
local-import block (the file's existing style).

Red: `tests/chatbot/agent/test_agent_ideas_panel.py` (5 tests fail on main).

## 2. Import boundary guard flags three #2073 files

`tests/chatbot/test_import_boundary.py::test_no_module_outside_the_boundary_imports_the_chatbot_package` flags
`app/services/document_access_service.py`, `tests/test_doc_access_api.py`, `tests/test_doc_access_migration.py`.

The guard's own doorway for core is `app/modules/chatbot/` (ALLOWED_PREFIXES; `app/modules/chatbot/lane_vocabulary.py:1-9`
"the module publishes what core needs HERE, on its own surface"). So no ALLOWED entry: a new doorway
`app/modules/chatbot/contact_access.py` delegates, at call time and unchanged, to the four agent helpers the Document
Access preview needs (`_active_access_codes`, `_row_count`, `agent_switch_on`, `linked_active_user`). The service and the
two tests import through it. Same functions, so the page still cannot disagree with the bot; Document Access behaviour
does not change.

## 3. Stale test from #2078

`tests/scm/test_line_splits_confirm.py:876` unpacks three values from `OrderInquiryHandoverResend._plan`, which returns
`(sendable, skipped)` (`app/services/oi_handover_resend.py:281`). Fix to `sendable, _skipped = ...`. If the assertions it
feeds then fail, report, do not bend. Correct the stale docstring at `oi_handover_resend.py:261-262`.

## 4. Migration tests pinned their own revision as THE head (#2073, shard 9)

`tests/test_product_combo_fields.py::test_ac_0_1_the_revision_id_fits_and_alembic_has_one_head` asserted `ptc_0001` is the
single head; #2073's `das_0001` sits on top. Check the real claim instead: the id fits, the revision is in the graph, the repo
has one head. `tests/test_doc_access_migration.py` pinned `das_0001` the same way and gets the same fix. #2075 has no migration
test. Precedent: `tests/test_migration_453_shared_brand_attach.py::test_452_has_exactly_one_child`.

## Tests run locally (throwaway DB)

- `tests/chatbot/agent/test_agent_ideas_panel.py`, `tests/chatbot/test_import_boundary.py`,
  `tests/test_doc_access_api.py`, `tests/test_doc_access_migration.py`, `tests/scm/test_line_splits_confirm.py`
- `tests/chatbot/test_customer_asks_refer_only.py`
- `tests/scm` shard 1 `serial_ddl` tests (`.github/workflows/deploy.yml:1104-1110`)

Red first: test changes commit alone (`test(red):`), then the fix; kill test after green.
