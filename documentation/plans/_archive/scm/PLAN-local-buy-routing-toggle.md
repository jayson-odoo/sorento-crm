# PLAN: local-supplier Buy routing behind a system setting, off by default

Status: shipped (#1006 merged 18 Sep 2026, head reparent #1009, deployed run 35301663740)
UAC: `local-buy-routing-toggle-acceptance-criteria.md`
Domain: scm (touches system settings)
Supersedes in part: `PLAN-local-supplier-oi-routing.md` decision 4 and 5 (#814, merged 10 Sep 2026)

## Why

#814 made a Buy whose product is bought from a Malaysian supplier skip the Order Inquiry on
confirm (no OI row, no reorder demand) and marked it with a `Local` pill on the board. The
owner's finding on prod, 18 Sep 2026: a local supplier does NOT mean CS buys it themselves.
Purchasing still raises the buy, and once it reaches purchasing it is bought overseas anyway.
With the rule hard-wired, such a line never reaches purchasing at all, which breaks the
handoff. Screenshot: SO314594 line 13 (TPE-9204) and line 14, `Buy 280 Local`, nothing on
Order Inquiries.

Owner ruling (18 Sep 2026, verbatim intent): do not keep the pill either. Put the whole local
rule behind a toggle so it is suppressed now and can be switched back on later if it is ever
needed.

## Measured facts (primary checkout on `origin/main` 624dc9797, 18 Sep 2026)

| fact | where |
| --- | --- |
| Origin resolver, ONE SQL statement per call | `app/services/scm/supply_origin.py` `buy_origin_by_product` |
| Three callers, all default a missing key to `"overseas"` | `project_supply_service.py:1178` (sheet), `:5696` (confirm, checked + carried), `project_fulfilment_board_service.py:676` (board) |
| Header-mint gate reads `origin != "local"` | `project_order_inquiry_service.py:739` |
| Row-loop skip reads `origin == "local"` | `project_order_inquiry_service.py:792` |
| Schema field | `schemas/project_board.py:730`, `schemas/project_supply.py:226`: `Optional[Literal["local","overseas"]]` |
| FE pill, shown only when `buy_origin === 'local'` | `FulfilmentBoardListView.tsx:397,449`, `BoardLadderOptionsTable.tsx:93`, `BoardCellBreakdownDialog.tsx:795` |
| Existing tests pinning the ON behaviour | `tests/scm/test_confirm_local_buy_no_oi.py` (7), `tests/scm/test_supply_origin.py` (2) |
| Board statement-count bound | `tests/test_ladder_v5_edges.py::test_a_board_of_76_lines_does_not_scale_its_query_count_with_the_line_count`, bound 40 |
| Boolean system setting precedent | `system_settings.chatbot_stock_denial_enabled` (model `app/models/user.py:553`, GET dict `settings.py:403`, defaults dict `:684`, update schema `:159`) |
| General settings page already carries a planning field | `user-management/settings/page.tsx` saves `plan_grain` |
| Alembic head on main | `oicf_0001_board_rows_to_confirm` |
| User guide describing the ON behaviour | `documentation/user-guides/supply-chain/local-buy-and-borrow-source.md` |

## Decisions (owner, 18 Sep 2026)

1. One boolean system setting, `local_buy_routing_enabled`, default **false**. Off is the
   shipped state.
2. Off means the local rule does not exist anywhere: no `Local` pill, every Buy raises its
   Order Inquiry row, every Buy counts toward reorder demand. Nothing else on the board
   changes.
3. On means exactly today's behaviour (#814 decisions 4, 5 and 9). No code path is deleted,
   so the switch is reversible without a deploy.
4. Countries master, supplier country FK and the Borrow modal Location table (#814 S1, S2,
   S4) are untouched. They stand on their own.
5. Lines already confirmed as local Buys with no OI row are raised on their next re-confirm
   once the setting is off (carried entries go through the same loop). Accepted: that is
   the point. No backfill.

## Design

**One seam.** `buy_origin_by_product` reads the setting first. When it is off it returns
`{pid: None for pid in ids}` and runs no origin SQL. Every caller already does
`origin_by_product.get(product_id, "overseas")`, and `dict.get` returns the stored `None`
when the key is present, so:

- the sheet, board and confirm payloads carry `buy_origin: null`,
- the header gate `origin != "local"` is true, the row-loop skip `origin == "local"` is
  false, so every Buy raises,
- the FE pill condition `buy_origin === 'local'` is false, so no pill renders.

No caller changes, no OI-service change, no FE board change. The schemas already allow
`None`. The one extra statement per board build (the settings read) sits inside the bound
of 40.

The setting read: `db.query(SystemSettings.local_buy_routing_enabled).first()` inside the
resolver, no cache, no helper module. The resolver is called once per board build, once per
sheet, once per confirm (already pinned by `test_buy_origin_computed_once_per_board_build`).

### S1 Setting (BE)

- `app/models/user.py` SystemSettings: `local_buy_routing_enabled = Column(Boolean,
  nullable=False, server_default="false", default=False)`, with a two-line comment naming
  this plan.
- Migration `lbrt_0001_local_buy_toggle`, `down_revision = "oicf_0001_board_rows_to_confirm"`
  (re-parented by `./scripts/alembic-reparent.sh` at the pre-PR gate). `add_column` with
  `server_default=sa.false()`; downgrade drops it.
- `app/api/v1/user_management/settings.py`: field on `SystemSettingUpdate`
  (`Optional[bool] = None`), a line in the GET dict (`:403` block) and a line in the
  defaults dict (`:684` block). Both builders, per the lesson.

### S2 Resolver gate (BE)

`app/services/scm/supply_origin.py`: read the setting; off returns `None` for every id and
skips the SQL. Docstring updated to say the rule is a switch, default off, and why (owner
finding above).

### S3 Settings screen (FE)

General settings page (`user-management/settings/page.tsx`), beside the planning fields
(`planGrain`): one `Switch` labelled **Local supplier Buys skip Order Inquiries**, bound to
`local_buy_routing_enabled` in the schema, the form defaults and the save body. No
description text under it (no on-screen explanation rule). The label is the whole UI.

### S4 Docs

- User guide `local-buy-and-borrow-source.md`: "The Local pill" and "What happens on
  confirm" sections rewritten as: the rule is off unless an admin turns on the setting; with
  it off there is no pill and every Buy reaches Order Inquiries. Borrow-source section
  unchanged.
- `PLAN-local-supplier-oi-routing.md` Status line: it merged in #814 on 10 Sep and still
  reads "in review". Set it to `implemented (#814, 10 Sep 2026); decisions 4, 5, 9 gated
  off by PLAN-local-buy-routing-toggle (18 Sep 2026)` and move plan + UAC + evidence folder
  to `documentation/plans/_archive/scm/`.

## Slices and order

One slice. Phase 1 (FE against mocks) is folded into the coder slice: the whole FE change is
one Switch on an existing form, there is nothing to mock. Stated here so the PR can say so.

1. tester: reds from the UAC below (pytest + vitest).
2. coder: S1, S2, S3, S4, greens.
3. reviewer + security-reviewer + browser pass in parallel.
4. guide-writer folds S4 guide text if the coder left it.

## Testing seams (agreed before Phase 2)

- Resolver: `buy_origin_by_product(db, ids)` with the settings row flipped in the test
  session. Off: `{id: None}` for every id, zero SQL statements on the `product_suppliers`
  or `purchase_order_lines` tables (count via `event.listen(engine, "before_cursor_execute")`
  the way `test_ladder_v5_edges` counts). On: today's answers, reuse `test_supply_origin`'s
  `chain` fixture.
- Confirm: the real confirm path in `project_supply_service.py` (the seam
  `test_confirm_local_buy_no_oi.py::test_scm_demand_sees_no_local_buy` already uses), a
  product whose primary supplier's country is MY, setting off. One OI row raised, header
  minted, demand sees it.
- Existing ON tests keep their hand-built `origin` dicts and stay green untouched. The two
  that go through the resolver (`test_board_and_supply_carry_buy_origin`,
  `test_scm_demand_sees_no_local_buy`) gain a setting-on fixture line.
- Settings API: GET returns the field (both builders), POST general saves it. Assert the
  field is present in the response body, not just on the row (`response_model` lesson).
- FE: vitest on the general settings page, Switch present with the label, save body carries
  `local_buy_routing_enabled`. Vitest on the list view: `buy_origin: null` renders no pill
  (the existing `'overseas'` case already covers absence; the null case is the new shape).

## No-motion list

- No cache of the setting, no helper module, no per-request context. One read per resolver
  call; the resolver is already called once per build.
- No deletion of the OI-service local branches or the FE pill code. The toggle IS the
  reversal; deleting the code would make "enable later" a rebuild.
- No backfill of previously skipped lines. Re-confirm raises them (decision 5).
- No tenant or per-company scope on the setting. `system_settings` is the singleton.
- No countries / supplier country changes.

## Risks

- A prod SO whose local lines were confirmed under #814 gets fresh OI rows on its next
  re-confirm. Expected and wanted. Purchasing sees them as new rows under the existing
  header.
- Reorder demand rises by the local Buys the moment the setting is off. Wanted.

## After deploy (owner)

- Nothing to run. The column lands with `server_default false`, which is the wanted state.
- Re-confirm SO314594 (or let its next revision do it) so lines 13 and 14 reach purchasing.

## Captain's test list (Phase 2, tester writes these red BEFORE the coder)

pytest, file `tests/scm/test_local_buy_routing_toggle.py` (Postgres, `blank_session`):

1. `test_setting_column_defaults_false`: a fresh `SystemSettings` row reads
   `local_buy_routing_enabled is False`.
2. `test_resolver_off_returns_none_for_every_id_and_runs_no_origin_sql`: setting off (the
   default), three product ids, result `{id: None}` x3, and no statement touching
   `product_suppliers` / `purchase_order_lines` was executed.
3. `test_resolver_on_answers_local_for_my_supplier`: setting on, reuse the chain fixture,
   answer `local` for the MY primary link and `overseas` for the CN one (guards that ON is
   untouched).
4. `test_board_payload_buy_origin_is_null_when_off`: board build for a MY-supplier product,
   setting off, `contribution["buy_origin"] is None` (mirror of
   `test_board_and_supply_carry_buy_origin`, inverted).
5. `test_confirm_off_raises_oi_row_for_my_supplier_buy`: real confirm path, MY-supplier
   product, setting off: header minted, one `ORDER` row `raised`, `created == 1`.
6. `test_confirm_off_carried_line_previously_skipped_is_raised`: revision 1 confirmed with
   setting on (line skipped, no row), setting flipped off, revision 2 with the line carried:
   the line now has one raised row.
7. `test_scm_demand_sees_buy_when_off`: inverse of `test_scm_demand_sees_no_local_buy`.
8. `test_settings_api_get_and_post_carry_the_field`: GET general settings body has
   `local_buy_routing_enabled: false`; POST `{local_buy_routing_enabled: true}` then GET
   reads true. Both dict builders (`settings` present and `settings` None) covered.
9. Existing: `tests/scm/test_confirm_local_buy_no_oi.py::test_board_and_supply_carry_buy_origin`
   and `::test_scm_demand_sees_no_local_buy` get one line each setting the flag on. The
   other five need nothing.

vitest:

10. `user-management/settings/page.localBuyToggle.test.tsx`: the Switch renders with the
    accessible name `Local supplier Buys skip Order Inquiries`, unchecked when the GET says
    false; toggling it and pressing Save sends `local_buy_routing_enabled: true` in the
    body. Copy the harness from `page.deferredWindows.test.tsx`.
11. `FulfilmentBoardListView.test.tsx`: add one case to the existing `Local pill` describe:
    `buy_origin: undefined` on a Buy contribution renders zero `Local` badges.
