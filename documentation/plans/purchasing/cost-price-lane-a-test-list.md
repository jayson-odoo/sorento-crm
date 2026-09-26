# Cost price Lane A (S1 + S2): the captain's test list

Status: Phase 2 input for the `tester`, 27 Sep 2026. One line per UAC id: the test name and the
assertion in words. The tester writes these red, BEFORE the coder, against
`cost-price-api-contract.md`; the coder makes them green without editing them (a test the coder
believes is wrong is reported to the captain).

## Seams the tests pin (the coder builds to these names)

- Models, `app/models/cost_price.py`: `ProductSupplierCost` (`product_supplier_costs`),
  `CostPriceChangeSet` (`cost_price_change_sets`), `CostPriceChangeLine`
  (`cost_price_change_lines`), `SupplierPriceLink` (`supplier_price_links`). Columns as plan
  section 4. `SystemSettings.cost_price_verification_enabled`.
- Migration `alembic/versions/cpc1_supplier_cost_lists.py`, `revision = "cpc1_supplier_cost_lists"`,
  chained on the current head. It also widens `audit_logs.action` to `String(40)` (the named
  events `SUPPLIER_COST_LIST_EDIT` and `COST_VERIFICATION_SETTING` do not fit the old 20).
- Reader, `app/services/procurement/supplier_price_list_reader.py`:
  `read_supplier_price_list(data: bytes, filename: str) -> PriceListRead` with `.sheets`
  (each: `name`, `header_row`, `skipped_reason`, `price_currency`, `rows`) and `.letterhead`;
  each row: `sheet`, `row_no`, `line_no`, `supplier_code_raw`, `supplier_code`, `code_note`,
  `configuration`, `price` (`Decimal | None`), `flags` (set of str). Also
  `clean_code(raw) -> tuple[str, str | None]` and `clean_price(value) -> Decimal | None`.
  Raises `AppException` 422 with codes `file_type`, `file_too_large`, `too_many_rows`.
- Cost lists, `app/services/procurement/supplier_cost_service.py`:
  `price_in_force(rows, day) -> row | None` (pure; rows carry `unit_cost`, `currency`,
  `start_date`, `end_date`, `created_at`), `cost_status(row, rows, day) -> str`,
  `refresh_link(db, link, day)` and `refresh_prices_in_force(db, day) -> int` (the daily tick;
  returns how many links changed).
- Change sets, `app/services/procurement/cost_price_change_service.py`: whatever the routes need;
  tests go through the HTTP routes of the contract, not this module, except AC-S1-08's spy.
- Fixture: `tests/fixtures/cost_price/taiyang_shapes.py` builds the synthetic TAIYANG workbook
  in memory (5 sheets named `19 series`, `12 series`, `22 series`, `28 series`, `25 series`;
  letterhead rows 1 to 5 merged across the width naming `XIAMEN TAIYANG TECHNOLOGY CO., LTD`;
  header row 6 `序号 型号 产品配置 价格`; 40, 24, 18, 58, 118 body rows; 产品配置 merged over rows
  7 to 9 of `19 series`; `CB2500SS-BL（彩盒）` in `25 series`; `SRTWT1900-BL-DIY` in `19 series`;
  every other code and price synthetic). The same builder writes
  `tests/fixtures/cost_price/taiyang_price_list.xlsx` for the browser run (committed). The
  owner's real file was never attached, so this fixture is synthetic, not anonymised.

Every test seeds its own company-scoped chain (supplier, products, links, users) with a marker
prefix (the CI database has no business rows). Postgres only, `tests/_pg_fixture.py` helpers or
the `tests/scm` route-test pattern (`as_company_user`, `_grant`).

## Files

`tests/test_cost_price_reader.py`, `tests/test_cost_price_cost_lists.py`,
`tests/test_cost_price_upload_routes.py`, `tests/test_cost_price_apply.py`,
`tests/test_cost_price_verification.py`, `tests/test_cost_price_permissions.py`,
`tests/test_cost_price_audit.py`; FE: `.../cost-price-uploads/**/*.test.tsx` and
`.../cost-price-uploads/dropdowns.inventory.test.ts`.

## S1

- **AC-S1-01** `test_fixture_parses_every_sheet_with_its_row_counts`: the fixture yields 5 sheets
  with 40, 24, 18, 58, 118 rows, each row carrying sheet, row_no (7 upward), supplier_code,
  configuration, price and the 序号 value.
- **AC-S1-02** `test_header_found_at_row_4_and_row_9` and
  `test_sheet_without_header_is_skipped_by_name`: header rows 4 and 9 are found;
  a sheet with none has `skipped_reason == "no_header"`, zero rows, and no exception.
- **AC-S1-03** `test_merged_configuration_fills_down_with_flag` and
  `test_merged_price_fills_down_with_flag`: rows 8 and 9 carry row 7's configuration with
  `configuration_from_merge`; a price merged over two rows gives both the price and
  `price_from_merge`; `item_code` is never filled down.
- **AC-S1-04** `test_code_cleaning_folds_nfkc_trims_and_splits_the_note`:
  `clean_code("CB2500SS-BL（彩盒）") == ("CB2500SS-BL", "彩盒")`,
  `clean_code(" SRTWT1900-BL-DIY ") == ("SRTWT1900-BL-DIY", None)`; the row keeps the verbatim
  raw; and (route level) the note is never sent to the matcher (spy on `resolve`).
- **AC-S1-05** `test_price_cleaning` (parametrised): `¥512`, `512.00元`, `"512"`, `512`,
  `RMB 1,512` give Decimal values; `面议`, blank, `-5` give None; a line with no price is
  `needs_attention` and Apply is refused 422 until it is skipped.
- **AC-S1-06** `test_probe_suggests_the_one_supplier_named_in_the_letterhead` and
  `test_probe_suggests_nothing_when_zero_or_two_suppliers_match`.
- **AC-S1-07** `test_currency_from_supplier_links`, `test_currency_header_token_wins`,
  `test_currency_null_when_unresolved_and_upload_requires_it` (422 `currency_required`).
- **AC-S1-08** `test_upload_binds_with_the_shared_engine_remember_false`: spy on
  `proforma_invoice_service._products_by_code` and `supplier_code_matcher.resolve`; both are
  called, `resolve` with `remember=False`; outcomes recorded as `exact`, `alias` (a seeded alias
  for this supplier), `ladder` with `match_rung == "separator"` (`CB2500SS GY` for
  `CB2500SS-GY`), `unmatched` otherwise; a code that binds a product SET is `unmatched`; no line
  has any other outcome value.
- **AC-S1-09** `test_line_records_price_in_force_new_price_and_change_pct` and
  `test_unlinked_product_is_new_link`: change_pct is `(new - current) / current * 100` rounded to
  1 decimal, null when there is no current price.
- **AC-S1-10** `test_two_lines_binding_one_product_are_both_duplicate` and apply refused 422 until
  one is skipped.
- **AC-S1-11** `test_apply_refused_while_unmatched_or_needs_attention_or_duplicate`: 422
  `unresolved_lines` naming the count.
- **AC-S1-12** `test_manual_map_is_stored_and_aliases_written_only_on_apply`: after PATCH
  `product_id`, the line is `manual`; no `SupplierProductCodeAlias` row exists until Apply; after
  Apply one `source=manual` alias for the manual map and one `auto` alias for the ladder bind;
  `test_discarded_set_teaches_nothing`: discard, zero new alias rows.
- **AC-S1-13** `test_equal_price_without_dates_is_unchanged_and_never_applied` and
  `test_equal_price_with_dates_is_changed`.
- **AC-S1-14** `test_second_upload_for_supplier_with_open_set_is_409_naming_it`.
- **AC-S1-15** `test_upload_refuses_big_wrong_type_or_too_many_rows` (patch the byte cap low for
  the size case; `.csv` and `.xlsm` refused; a 5,001 row sheet refused), nothing stored.
- **AC-S1-16** covered in permissions (below).
- **AC-S1-17** `test_multi_company_session_is_refused`: 422 `pick_one_company` on probe and
  upload.
- **AC-S1-18** `test_source_file_retained_and_downloadable`: GET source-file returns the same
  bytes and the original file name; the set records file name, sheet names, header rows.
- **AC-S1-23** `test_discard_hard_deletes_a_draft` and
  `test_pending_or_applied_set_cannot_be_deleted` (409); `test_discard_form_action_is_registered`
  (key `cost_price_change_set.discard`, destructive window, permission `.upload`).
- **AC-S1-26** `test_verification_off_uploader_applies_directly`: status `applied`,
  `verified == false`, `applied_by` is the uploader, no submit needed.
- **AC-S1-27** `test_apply_writes_one_cost_row_per_line_with_set_dates_and_source`: one
  `ProductSupplierCost` per changed or new-link line not skipped, carrying the set's currency,
  start, end and `source_change_line_id`; unchanged and skipped lines write nothing; the link's
  `unit_cost` equals the price in force.

## Cost lists

- **AC-CL-01** `test_price_in_force_rules` (pure, parametrised): always row alone; dated row
  inside its range wins over always; always again after the dated end; two covering rows, the
  later start wins; equal starts, the newest `created_at`; none when every row ended or not
  started; boundaries inclusive on both ends.
- **AC-CL-02** `test_cost_row_has_only_price_currency_and_dates`: the model's business columns
  are exactly `unit_cost`, `currency`, `start_date`, `end_date` (plus id, link, source, audit
  fields); no route schema carries basis, shipping, tax or terms.
- **AC-CL-03** `test_end_before_start_is_422` and `test_negative_price_is_422` on the hand-edit
  routes and on upload dates.
- **AC-CL-04** `test_apply_and_hand_edit_keep_unit_cost_equal_price_in_force`, including null
  when nothing is in force, and `test_link_without_cost_rows_is_never_written` (a link with
  `unit_cost` 10 and no cost rows keeps 10 after an unrelated apply and after the tick).
- **AC-CL-05** `test_daily_tick_updates_links_and_writes_one_audit_row` with a fixed day:
  a scheduled row whose start arrives becomes `unit_cost`; an ended row stops being it; one
  `SUPPLIER_COST_TICK` audit row lists the changed links; a second run the same day returns 0 and
  writes no audit row. `test_daily_tick_is_scheduled` (a scheduler job is registered for it).
- **AC-CL-06** `test_hand_edit_add_change_delete_audited_and_gated`: with `.edit` 201/200/200
  and a `SUPPLIER_COST_LIST_EDIT` row each; without `.edit` 403 on all three;
  `test_cost_delete_form_action_is_registered` (`product_supplier_cost.delete`, destructive).
- **Contract** `test_supplier_cost_lists_route_shape_and_statuses`: the 2.1 shape, statuses
  `in_force`, `scheduled`, `ended`, `always`, `overridden` computed for a fixed today, `query` and
  `status` filters; `test_product_suppliers_by_product_carries_costs`.

## S2

- **AC-S2-20** `test_setting_column_defaults_false_and_reaches_both_serialisers`: GET settings
  and the general update both carry `cost_price_verification_enabled`; editing needs the existing
  settings edit permission; a change writes `COST_VERIFICATION_SETTING`.
- **AC-S2-01** `test_verifier_decides_a_line_with_reason` and `test_decide_all`.
- **AC-S2-02** `test_apply_pending_refused_with_undecided_lines` (422 naming the count).
- **AC-S2-03** `test_uploader_cannot_decide_return_or_apply_own_set`, superadmin uploader
  included, 403 `SAME_PERSON_CANNOT_VERIFY` on all four; `test_second_user_with_verify_can`.
- **AC-S2-04** `test_verification_on_apply_draft_is_409_submit_first` and
  `test_submit_moves_to_pending_with_submitter`; `test_verification_off_submit_is_409`.
- **AC-S2-05** `test_new_link_lead_time_is_the_suppliers_most_common` and
  `test_new_link_without_default_needs_lead_time` (422 `lead_time_required` until PATCHed).
- **AC-S2-06** `test_stale_line_blocks_apply_and_writes_nothing`: change the link's price in force
  after upload; Apply is 409 `stale_lines` listing recorded and live; no cost row written; the
  line's `stale` field is filled on the next GET lines.
- **AC-S2-07** `test_second_apply_is_409`: two sequential applies, the second 409 (the
  conditional status update; a true concurrent test is optional).
- **AC-S2-08** `test_apply_pending_marks_verified_with_verifier`.
- **AC-S2-09** `test_return_needs_reason_clears_decisions_back_to_draft`.
- **AC-S2-10** `test_applied_set_is_frozen`: PATCH line, decision, submit, return all 409.
- **AC-S2-11** `test_supplier_channel_set_is_pending_with_setting_off`: a set seeded with
  channel `supplier_page` and status `pending_verification` cannot be applied by an `upload`-only
  user, can by a verifier; toggling the setting does not move it.
- **AC-S2-12** `test_submit_notifies_every_verifier_once` and
  `test_apply_and_return_notify_the_submitter` (notification rows).
- **AC-S2-13** `test_apply_leaves_product_prices_alone`: `products.cost_price`, `list_price`,
  `invoice_price` unchanged.
- **AC-S2-14** `test_product_supplier_crud_requires_permissions`: POST/PUT/DELETE
  `/procurement/product-suppliers` 403 without add/edit/delete; `test_migration_sweeps_product_supplier_writes`
  (roles holding `procurement.product_suppliers.view` get add/edit/delete; roles holding
  `scm.proforma_invoice.upload` get view/add/edit/delete, so purchasing can open the Prices tab;
  `integration_%` roles excluded; idempotent).
- **AC-S2-19** `test_migration_grants_verify_to_purchasing_roles_only` and
  `test_api_key_principal_cannot_decide_return_or_apply`.

## Permissions and audit

- **AC-S1-16** `test_routes_need_upload_or_view` (parametrised over probe, upload, PATCH line,
  discard, apply: 403 without `.upload`; list and detail: 403 without `.view`).
- **AC-S1-25** `test_migration_grants_upload_and_view_to_purchasing_roles`: run the migration's
  `upgrade()` in a rolled back transaction (the `test_autocount_pull_sr1` pattern); roles holding
  `scm.proforma_invoice.upload` and `admin`, `superadmin` get `.upload`, `.view`, `.verify`; no
  `integration_%` role gets any; a second run adds nothing.
- **AC-AU-01** `test_new_tables_and_product_suppliers_are_audit_tracked`.
- **AC-AU-02** `test_named_events_written` for upload, apply (with verified flag, dates and the
  change list), submit, return, hand edit.
- **AC-AU-03** `test_apply_audit_rows_share_one_trace_id`.

## FE (vitest)

- **AC-SR-05** `dropdowns.inventory.test.ts`: every new `.tsx` under the cost price screens, the
  supplier Prices tab and the product Suppliers tab cost section imports no
  `@/components/ui/select`, renders no raw `<select>`, and uses only
  `SearchableSelect` / `SearchableMultiSelect` for dropdowns.
- **AC-S1-21** `CostPriceLines.test.tsx`: each filter's empty state text renders; the zero-changed
  set shows "Nothing changed against current prices" with Discard.
- **AC-S2-15** `CostPriceReview.verification.test.tsx`: with `verification_enabled: false` no
  Submit, Decision column, Accept all or Return renders; with it on and `actions.can_submit` the
  bar shows Submit for verification; with `can_decide` the Decision column and Accept all render;
  a disabled Apply carries `apply_blocked_reason` as its tooltip.
- **AC-SR-02** `useCostPriceLineFilter.test.ts`: search by supplier code, configuration, product
  code or sheet combined with the stat filter and sheet tab; counts follow the search.
