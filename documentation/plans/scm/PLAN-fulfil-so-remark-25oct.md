# PLAN: per-SO remark on the Confirm split page, carried into the purchasing email (FULFIL-SO-REMARK)

**Status:** Plan. Step 1 investigation done; behaviour card filed to the owner (crew `--ask`); no code
until the answers come back. Track: M by the brief; becomes L if slice 2 (AutoCount pull of new fields)
goes ahead, because it needs a shared-service change and CRM columns (migration).

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

## Slices (pending owner answers)

1. Remark field + email (CRM only). Default from data the CRM already holds (Note -> `MOCKUP`).
2. AutoCount pull: shared service sends `ShipInfo`, `RefDocNo`, line `FurtherDescription`; CRM stores
   them; default rules use them (PR / Sponsorship / PO no / mixed-SO line labels).

## Open questions

Filed as the behaviour card; answers recorded here when crew relays them.
