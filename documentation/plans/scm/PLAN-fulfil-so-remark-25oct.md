# PLAN: per-SO remark on the Confirm split page, carried into the purchasing email (FULFIL-SO-REMARK)

**Status:** Build (size L, two repos). Owner approved mock v3 and the final card 25 Oct 05:39.
Rules: `documentation/plans/scm/CARD-fulfil-so-remark-25oct.md` (FINAL). UAC:
`documentation/plans/scm/fulfil-so-remark-25oct-acceptance-criteria.md`. PRs: shared service
`crew/fulfil-so-remark` (foundryx-shared-service) + CRM `crew/fulfil-so-remark` (sorento-crm).

## Requirement (owner, 25 Oct 2026, relayed by crew)

Fulfilment planning -> Confirm -> the split-delivery page (Review split, before the purchasing email
goes out). Today staff hand-write a remark beside special SOs in that email, e.g.
`SO427088  OTM / HUAZHI CONST. (MOCKUP)`.

1. Safe first: on that page, per SO, a Remark field prefilled with a default and editable. The remark
   prints in the purchasing email beside that SO (same Confirm email function and layout: SO facts in
   the top table, item lines below).
2. Auto default from AutoCount: Shipping Info normally holds the customer PO number, or
   `PURCHASE REQUEST` / `SPONSORSHIP`. Mockup = Note tab containing `***FOR MOCKUP` (whole SO) or an
   item line remarked mockup (SO mixes real and mockup units; say which lines).

## Step 1 findings (read-only; AutoCount AED_SORENTO via the Air tunnel, dev DB sorento_cagent_stack)

AutoCount columns (INFORMATION_SCHEMA, SO / SODTL):

| UI label | Column | Holds on project SOs |
| --- | --- | --- |
| Shipping Info | `SO.ShipInfo` nvarchar(40) | customer PO no (`OT06/2702`, `ET-PO0018661`), or `PURCHASE REQUEST`, `SPONSORSHIP`, or the PR number itself (`PR26-0375`) |
| Refer Document No | `SO.RefDocNo` nvarchar(50) | Sorento's own running number; the PREFIX is the type: `PS26-` normal, `PR26-` Purchase Request, `PSSF26-` Sponsorship |
| Note tab | `SO.Note` nvarchar(max), RTF | free text; whole-SO mockup is written here |
| line remark (rich text under an item) | `SODTL.FurtherDescription` nvarchar(max), RTF | `***FOR STH(100)-2 UNITS MOCK UP` on the mockup lines of a mixed SO |
| text-only line | `SODTL.Description` with empty ItemCode | section header such as `MOCKUP`, `MOCK UP - BLOCK 1`, `(2 UNITS MOCK UP)` |

Counts, last 90 days, project SOs (SalesLocation `BRW%`, RefDocNo `PS`/`PR`/`PSSF`, not cancelled): 810.

| RefDocNo prefix | SOs | Shipping Info | Note mockup | line remark mockup (SOs / lines) | header-line mockup |
| --- | --- | --- | --- | --- | --- |
| PS | 689 | 686 PO-like, 2 text, 1 blank | 10 | 11 / 20 | 8 |
| PR | 40 | 14 `PURCHASE REQUEST`, 26 a PR or PO number | 7 | 0 | 0 |
| PRR | 4 | PO-like | 0 | 0 | 0 |
| PSSF | 77 | 77 contain `SPON` (spellings: SPONSORSHIP, SPONSORHIP/LIN, SPONSORSHIP/LIN) | 8 | 1 / 1 | 0 |

3 SOs carry a Note mockup AND line mockups. Note wording varies: `***FOR MOCKUP`, `FOR MOCK UP`,
`(MOCKUP)`, `***( MOCK UP )`, `PRE-ORDER MOCKUP UNIT`, `FOR SHOW HOUSE & MOCK UP UNIT ONLY`,
`Only send 2 for mock up. Remaining ...` (prose about a PART of the SO).

What the CRM already has (ingest `app/services/document_ingest_service.py:236-241`, model
`app/models/order.py:684-705`): `sales_orders.internal_note` (Note, RTF stripped) and
`project_label` (from Note or `SO.Ref`); `po_ref` is AutoCount `UDF_Note` (blank on project SOs).
NOT synced for SOs: `ShipInfo`, `RefDocNo`, line `FurtherDescription` (only DO/GRN map ShipInfo,
`app/services/autocount_doc_ingest_service.py:383,400`).

Today's flow: Confirm (N) on `FulfilmentBoardPanel.tsx:3701` opens `ConfirmGuideDialog.tsx` (one
page per SO, section at :273-407); submit `runConfirmAll` (:1873) -> POST
`/project-sales/fulfilment-planning/confirm-all` (`fulfilment_planning.py:448`) ->
`ProjectSupplyService.confirm_many` (`project_supply_service.py:11509`). Email: `build_handover_email`
(`project_order_inquiry_service.py:14202`), SO facts from `_handover_order_facts` (:5237), template
`order_inquiry_handover_default` in `email_templates`, last layout `oihr_0009_split_rows`. No per-SO
remark exists in the payload, the schema (`ConfirmManyOrderBody`, `app/schemas/project_supply.py:596`)
or the email.

Dev check: `upper(internal_note) ~ 'MOCK'` is true for SO421287, SO423072, SO418626, SO422429 and
false for SO419417 / SO416732 (mixed SOs, flag only on the lines), so a Note-based default works on
today's data.

Shared service (`foundryx-shared-service` origin/main 5961bd3a, 22 Oct): SO is pulled from SQL, not
hapi; no hapi SO path exists (`modules/autocount/presets.py:1617-1626`,
`doc_lookup/registry.py:5-6`). The SO header query (`presets.py:185-203`) reads Note and Ref but not
ShipInfo or RefDocNo; the line query (`presets.py:204-214`) reads Description but not
FurtherDescription, and skips text-only lines (`ItemCode IS NOT NULL AND Qty IS NOT NULL`, :214). So
slice 2 needs a shared-service query + canonical payload change plus CRM columns.

## Architecture

One rule module per repo side, no new framework:

- **Shared service** sends three more AutoCount values on the SO it already pulls by SQL preset:
  header `ShipInfo` -> `ship_info`; line `FurtherDescription` (raw RTF, like `Note`) -> `line_remark`;
  line `SectionHeading` -> `section_heading`, computed in the line query by an OUTER APPLY: the
  Description of the nearest earlier text-only line (ItemCode or Qty NULL, text not blank) of the
  same DocKey. The item-line cut and the LineCount guard stay as they are. Existing tasks get the
  new query through the repo's backfill pattern (rewrite only a byte-identical previous preset; the
  hand-written prod query is a documented operator step). CRM drops unknown keys
  (`app/schemas/ingest_extras.py:23`), so the two PRs can deploy in either order.
- **CRM storage**: `sales_orders.ship_info` (precedent `orders.ship_info`, `app/models/order.py:484`),
  `sales_order_lines.line_remark` (RTF stripped by `app/utils/rtf.py:27`) and
  `sales_order_lines.section_heading`. One alembic revision. Ingest maps them like `po_ref`
  (`document_ingest_service.py:1050`).
- **CRM rules**: one pure module `app/services/so_remark_rules.py`: `is_mockup_line(note,
  line_remark, section_heading)`, `remark_type(ship_info)` (Sponsorship > Purchase Request),
  `default_remark(remark_type, chosen_flags)`, `label_lines(chosen_flags)` (mixed only). The board
  exposes `is_mockup` per line (`BoardContribution`, `project_board.py:574`) and `remark_type` per SO
  (`BoardOrderStanding`, :1239). The FE mirrors only the two-line default/label decision
  (`_shared/lib/soRemark.ts`) over those flags.
- **Confirm -> email**: `ConfirmManyOrderBody.so_remark` (`app/schemas/project_supply.py:596`,
  Optional, max 100; None = compute the default, "" = staff cleared it) -> `confirm` ->
  `record_saved_lines(so_remark=...)` (`project_order_inquiry_service.py:4587`) stamped on the queued
  items -> `_build_handover_context` `orders` rows (:14066) get `remark`; line items of an SO whose
  queued lines mix mockup and actual get `Mockup` / `Mockup, <text>` in `remark`. Resend
  (`oi_handover_resend.py:147`) passes no remark, so the default is recomputed from the resent lines.
- **Template**: `oihr_0010_so_remark_column` adds REMARK as the last SO-table column (HTML + text),
  copying `oihr_0009`'s pattern (`_load`, exact single replacements, `only_when` guard, downgrade).
- Not changed: the OI Excel attachment, the preview dry run (it never builds the email,
  `project_supply_service.py:11587`), RefDocNo (owner: not needed).

## Slices

CRM (this repo):
1. Migration + model + canonical schema + ingest mapping (`ship_info`, `line_remark`, `section_heading`).
2. `so_remark_rules.py` + board fields (`is_mockup`, `remark_type`).
3. Confirm payload `so_remark` + handover context (SO remark, line labels) + `oihr_0010` template.
4. FE: Remark input per SO page in `ConfirmGuideDialog.tsx`, Mockup badges, `so_remark` in
   `buildConfirmOrders` (`FulfilmentBoardPanel.tsx:1509`).

Shared service (`foundryx-shared-service`):
1. Preset header/line queries + mappings + canonical fields (SO line only) + catalog pin.
2. Backfill + module migration + bootstrap call + manifest bump + docs (operator step for the
   hand-written prod query).

## Test plan (red first, per repo)

CRM pytest (throwaway DB `sorento_fsr_throwaway`, `SORENTO_ENV_FILE=.env.ci-tests`):
`tests/test_so_remark_rules.py` (rules, every card case), `tests/test_so_remark_ingest.py` (columns
stored, RTF stripped, absent key keeps value like po_ref), `tests/test_so_remark_board.py`
(`is_mockup`, `remark_type` on the board), `tests/test_so_remark_email.py` (SO REMARK cell from the
payload, default when None, blank when "", line labels only when mixed, resend default),
`tests/test_email_layout_migrations.py` (oihr_0010 single head, guard, downgrade). Global guards:
`tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.
CRM vitest: `_shared/lib/soRemark.test.ts`, `FulfilmentBoardPanel.confirmGuide.test.tsx` (field,
default per case, clear, badges when mixed, payload carries so_remark).
Shared service pytest: preset query/mapping/payload/catalog/backfill tests next to
`tests/test_autocount_so_po_ref.py` and `test_autocount_so_transferable.py`.

## E2E (dev)

The dev SS source (`seed_autocount_shape_source.py`) has no ShipInfo/FurtherDescription and runs a
Postgres translation, so the end-to-end run reads real AutoCount read-only through the Air tunnel:
the SS branch's preset queries + mapping + sink payload for SO419417 / SO421287 / SO423741, posted to
the crew test copy's ingest, then the board and a Confirm on that copy. Never Confirm/Push to
AutoCount.

## Open questions

None. Owner rulings recorded in the card (FINAL).
