# Behaviour card: per-SO Remark after Confirm also when the Confirm carries changes (FULFIL-SO-REMARK-CHANGES)

Status: card, waiting on owner answers (Q1-Q5). No code until answered. Track: TBD (expected M,
no migration). Follows FULFIL-SO-REMARK (#1847, `CARD-fulfil-so-remark-25oct.md`) and
OI-EMAIL-PURCHASING-FOCUS (#1871, merged 242cb0d554).

Owner, 26 Oct 2026 ~19:25 (verbatim): "remark is needed when there is change for fulfilment
planning (meaning except new order), remark is needed after i click confirm at fulfilment
planning".

FE = `sorento_crm_frontend/app/(protected)/project-sales/`, BE = `sorento_crm_backend/app/`.

## Today's behaviour (file:line)

1. **The board's Confirm already shows a Remark on change pages.**
   - Confirm (`FE fulfilment-planning/components/FulfilmentBoardPanel.tsx:2955`) opens the
     Confirm guide, with one page per order that has a line in the press
     (`FulfilmentBoardPanel.tsx:2237-2280`, via `confirmLinesByOrder`,
     `FE _shared/lib/fulfilmentBoard.ts:1124`).
   - Counted roles: `post` (Approve / Amend of a saved line, changes included), `withdraw`,
     `cancel_so`, `split_edit` (`fulfilmentBoard.ts:917-924`).
   - Every page shows the Remark field (`FE fulfilment-planning/components/ConfirmGuideDialog.tsx:334-360`),
     for new and changed lines alike.
2. **The default is the same for new and changed lines:** `Sponsorship` / `Purchase Request` /
   `Mockup` / blank (`BE services/so_remark_rules.py:29-43`, mirrored in
   `FE _shared/lib/soRemark.ts`). It is always optional, and nothing in it says "change".
3. **It prints only in the email:**
   - It goes in `so_remark` on `confirm-all` only (`BE schemas/project_supply.py:618-620`).
   - It is stamped on the order's queued lines (`BE api/v1/projects/fulfilment_planning.py:546-551`,
     `services/project_order_inquiry_service.py` `stamp_so_remark`).
   - It prints in the REMARK column of the email's SO table (`_so_remark_of`; template
     `alembic/versions/oihr_0010_so_remark_column.py`).
   - It is NOT in the OI Excel; the Excel's REMARK is the line's.
4. **Two change Confirms get NO Remark step today:**
   - (a) **An AutoCount-change-only press.** Lines the pending batch retires (role `cancelled`)
     are not counted (`fulfilmentBoard.ts:914-916`), so such an order gets no guide page, only the
     AutoCount note (`FulfilmentBoardPanel.tsx:3714`).
   - (b) **The planning sheet's own Confirm**
     (`FE fulfilment-planning/components/SupplyCompositionSection.tsx:165-172`, in
     `FulfilmentPlanningSheet`). It posts the per-order `POST /sales-orders/{id}/confirm`, whose
     body has no `so_remark` (`BE api/v1/projects/fulfilment_planning.py:1549`), and it has no guide.

## Proposed rules

1. **An order "with a change"** is one whose press carries anything other than a brand-new line's
   first decision:
   - a re-decided confirmed line (CHANGED),
   - a take-back on a first Confirm (an imported raised order),
   - a Reject / withdraw,
   - a Transfer to Cancel SO,
   - a split edit,
   - an AutoCount planning change.
2. **Required on change pages (Q1).** On such an order's guide page the Remark is required:
   Confirm stays disabled until it is non-blank. On a new-order-only page it stays optional, as
   today.
3. **Default text on a change page:** Q2.
4. **Other Confirm paths.** The AutoCount-change-only press gets a guide page with the Remark (Q3),
   and the planning sheet's Confirm gets the same step (Q4).
5. **Where it prints.** Unchanged: the email's SO-table REMARK (Q5).

## Real dev SOs (sorento_prod_1020, from crew's answers; masked)

| SO | Press | Today | Proposed |
| --- | --- | --- | --- |
| SO426939 | new only (Buy / Use own / Use BRW) | guide page, Remark optional, blank | unchanged (optional) |
| SO423386 L96 | change only: confirmed Buy 10 -> Use own 10 | page, optional, blank | page, Remark **required** |
| SO413460 L16 | new + change: first Confirm over an imported raised ORDER 52 -> Use own 48 + Buy 4 | page, optional | required |
| SO406398 L16/L32 | Transfer to Cancel SO | page, optional | required |
| SO394881 | AutoCount planning change only (book-cancelled lines) | **no page, no Remark** | page with required Remark |

## Edge cases

- **Mixed press.** New AND changed lines in one press make a change order: the Remark is required,
  per SO.
- **Prefilled words.** A Sponsorship / Purchase Request / Mockup prefill still prefills. Q2 says
  whether that counts as filled.
- **Confirm-all over several SOs.** Each change SO's page must be filled before "Next: Confirm". A
  new-only SO in the same press stays optional.
- **Simulate Confirm** writes nothing and asks for nothing.
- **"Send to purchasing" (resend)** is not a Confirm, so it is left as is.
- **Per-line remarks** (the planner's own REMARK per line, OI-SPLIT-GUIDE F25) are untouched; this
  card is the per-SO Remark only.

## Questions

**Q1. What does "remark is needed ... except new order" mean?**
- (a) Required (cannot Confirm blank) on every SO page with a change; optional for new-only.
- (b) Shown on change pages as today, only prefilled with a change word.
- (c) Required on every page, new included.

Recommendation: (a), because "needed" reads as must-fill and "except new order" exempts new-only.

**Q2. Default text on a change page?**
- (a) Blank, so staff write the reason. Sponsorship / Purchase Request / Mockup still prefill and
  count as filled.
- (b) Prefilled `CHANGE`, editable.
- (c) Prefilled from what changed (`CANCEL` / `ORDER BACK` / `CHANGED`).

Recommendation: (a), because a required field pre-filled with a generic word gets clicked through,
and the owner wants the reason.

**Q3. The AutoCount-change-only press, which today has no page and no Remark?**
- (a) Give it a guide page with the required Remark.
- (b) Leave it without.

Recommendation: (a), because it is a change purchasing is told about.

**Q4. The planning sheet's own Confirm (no guide, no remark)?**
- (a) Add the same Remark step there.
- (b) Route it through the board's guide.
- (c) Leave it.

Recommendation: (a), the smallest change: `/sales-orders/{id}/confirm` gains `so_remark` like
confirm-all.

**Q5. Where does the Remark print?**
- (a) The email's SO table only (today).
- (b) Also a new `SO REMARK` column in the OI Excel.

Recommendation: (a), because the Excel keeps #1871's short column list and the email already
carries it.
