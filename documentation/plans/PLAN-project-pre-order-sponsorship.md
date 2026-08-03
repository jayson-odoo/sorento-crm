# PLAN - Pre-order and sponsorship paths (slice P12, module `projects`)

**Status:** Decisions D26-D29 answered by the client 2026-08-03 (section 4). **Group J is out
of scope: no pre-order sales order.** Scope is now Group K only: AC-K4 pinned, AC-K5 built in
phase 1, AC-K1/K2/K3 are the build.
**Acceptance criteria:** `UAC-project-lead-to-so.md` Group K (AC-K1..K5). Group J (AC-J1..J5)
is WITHDRAWN, see D26.
**Slug:** project-pre-order-sponsorship
**Builds on:** P1-P11, all built. Phase 1's `sponsorship_link_service` already exists.

---

## 1. Why this is not "just two flags"

`is_pre_order` and `is_sponsorship` already exist on `project_sales_orders`, which makes the
slice look nearly done. It is not. Both columns are READ in exactly four places, and only one
of them is a rule:

| Site | What it does |
|---|---|
| `_credit_finding` (draft service ~1388) | early return, so neither kind consumes credit |
| `_pre_order_finding` (~1454) | informational overlap: this project already pre-ordered this product |
| `serialize_row` (~2092) | display only |
| `project_order_inquiry_service` (~374, ~808) | pre-order lines are a covering POOL for netting, and label the row |

Everything else Groups J and K ask for is absent. The structural problem is bigger than any
single AC: **there is no way to create either kind of sales order.** `ProjectSODraftService.build`
is the only entry point and it requires `(purchase_order_id, schedule_version_id)`, refusing
outright when the PO has no lines. A pre-order has no customer PO by definition, and a
sponsorship form is not a PO at all.

## 2. Verified state, per AC

Checked against the code, not against the plan's own claims.

| AC | State | Evidence |
|---|---|---|
| **AC-J1** flag + anchored on project | **DONE** | columns exist, `project_id` NOT NULL |
| **AC-J2** excluded from credit | **DONE** | `_credit_finding` early return |
| **AC-J2** excluded from customer analytics + category | **VACUOUS TODAY, not broken** | see the correction below |
| **AC-J3** quotation checks skipped, project requirement used | **NOT DONE** | `_price_findings` has no flag gate; and the path cannot be reached anyway (no PO) |
| **AC-J4** re-point moves quantity DATE BY DATE, cross-checks at that moment, records cancelled remainder | **NOT DONE** | `REPOINT_SO` exists in P11 but moves a WHOLE LINE between sales orders on the SAME purchase order (`line.project_sales_order_id = destination.id`). No partial quantity, no cross-check, no remainder |
| **AC-J5** demand counted once | **NOT DONE** | depends on J4 |
| **AC-K1** approved sponsorship form produces an SO draft at price zero | **NOT DONE** | nothing constructs an SO from a sponsorship form; `_trigger_sponsorship_form_approved` exists in `automation_triggers` but does not build one |
| **AC-K2** skip price/qty checks, keep product resolution + discontinued | **NOT DONE** | no flag gate on the findings |
| **AC-K3** costing empty, SO marked awaiting costing | **NOT DONE** | no `awaiting_costing` anywhere in the codebase |
| **AC-K4** sponsorship SO emits inquiry rows like a commercial one | **PROBABLY FREE** | `derive_for_sales_order` runs off publish and reads no flag. Needs a test to pin it, not new code |
| **AC-K5** sponsorship spend rolls up against the project | **DONE (phase 1)** | `sponsorship_rollup` + `sponsorship_conversion` in `sponsorship_link_service` |

So: two ACs done, one vacuous, one free-but-unpinned, six to build.

### Correction on AC-J2's second half

The first pass of this audit read "zero `is_pre_order` references in the forecast" as "a
pre-order is being counted as commercial value". That was wrong, and the way it was wrong is
worth recording: absence of a flag check is not evidence of a leak until you know what the
query actually sums.

`_committed_by_project` sums `project_purchase_orders` (lines when present, else the header
amount) - **customer POs, never sales orders**. A pre-order has no customer PO by definition,
so it cannot reach committed value. And no consumer of "customer analytics" or "customer
category" exists anywhere yet: `ProjectSalesOrder` is referenced only inside the sales-order,
allocation, inquiry, delta, ingest and divergence services.

So AC-J2 is satisfied where it can be (credit), and its analytics half has nothing to be
excluded from. It becomes real work the day customer analytics is built, and the honest thing
is a note ON that future work rather than a filter added now to a query that does not exist.
No code is warranted today.

## 3. Shape

```
SPONSORSHIP FORM (approved)                 PROJECT REQUIREMENT (no PO yet)
        │  AC-K1                                     │  AC-J1
        │  price 0, delivery month                   │  buy ahead of a win
        ▼                                            ▼
   SO DRAFT (is_sponsorship)                  SO DRAFT (is_pre_order)
   costing empty, awaiting costing            no quotation to check
        │                                            │
        │ publish (unchanged path)                   │ publish
        ▼                                            ▼
   ORDER INQUIRY rows (AC-K4, free)           stock arrives, sits against the project
                                                     │
                                       a real customer PO lands  ─── AC-J4
                                                     ▼
                                       RE-POINT: move quantity date by date onto the
                                       real SO, cross check against ITS quotation at
                                       that moment, cancel the remainder explicitly
                                                     │  AC-J5: quantity LEAVES the
                                                     ▼  pre-order as it lands
```

The one invariant that matters: **demand is counted once.** A pre-order line and the real
line it feeds must never both be open for the same quantity, or the reorder engine buys it
twice. That is why J4 moves quantity rather than copying it, and why the remainder is
cancelled rather than left dangling.

## 4. Decisions - ANSWERED by the client 2026-08-03

**D26 + D27: there is no pre-order sales order. Group J (AC-J1..J5) is OUT OF SCOPE.**
The client does not want pre-orders represented as sales orders in the CRM, which answers
the re-point question too: with nothing to re-point from, AC-J4/J5 do not arise.

Consequence worth stating, because it is not obvious. The pre-order covering pool in
`project_order_inquiry_service._pre_order_pools` reads ONLY
`project_sales_orders WHERE is_pre_order = true`. With none ever created that pool is always
empty and the `PRE_ORDERED_DO_NOT_ORDER` verb becomes unreachable. But the client's own file
(`(04).03.2026 MARYAM TUJU RESIDENCE.xlsx`) carries an ORDER row for 600 CB6633 that their
5,950 pre-order already covered - the row P10 exists to remove. That netting therefore has to
come from the INBOUND SPO pool (`_inbound_pools`, reading `SPOAllocation` on shipments that
have not landed), which is where a supplier-side pre-order actually lives.

**The pool code is kept, not deleted.** An empty pool emits nothing, so it is harmless; and
deleting it would be an irreversible bet that no CRM-side pre-order is ever wanted. The
`is_pre_order` column stays for the same reason. **To confirm with the client:** that their
pre-orders reach us as inbound SPOs, because if they do not, the 600 CB6633 row comes back.

**D28: `awaiting_costing` is a STATUS** on `project_sales_orders`, not a finding. It gates the
publish: Accounts has to cost a sponsorship before it goes to AutoCount.

**D29: a month becomes the LAST DAY of that month.** Chosen deliberately over the first:
netting is FIFO by delivery date (AC-I3a), and the last day is the latest date the commitment
can be honoured, so it never claims covering stock ahead of a dated commercial line in the
same month. Where a sponsorship form carries no delivery date at all, the line stays undated
and the netting engine already serves undated demand last.

---

## 4a. Superseded: the questions as originally asked

Kept for the record. Each changed what would get written, which is why they were asked.

**D26. How does a pre-order sales order get created?** There is no PO to build from.
Candidates: (a) a new "buy ahead" screen that takes product + qty + delivery date directly
against the project; (b) build from a quotation version instead of a PO, treating the
quotation as the requirement; (c) from the delivery schedule alone. This decides whether P12
needs a new intake screen or reuses one.

**D27. Can a re-point cross the customer boundary?** A pre-order is deliberately parked under
a convenience debtor (D18, the Hong Bee route). The real SO is under the real customer. If
re-point may cross debtors, the cross-check at re-point time has to be against the
DESTINATION's quotation, and the two AutoCount documents belong to different debtors, which
the existing whole-line `REPOINT_SO` never had to consider.

**D28. What is "awaiting costing" (AC-K3)?** A new value in `project_sales_orders.status`, a
`so_draft_findings` row, or a separate boolean? Status is the honest answer if it gates a
publish; a finding is right if it is only a note for Accounts. This also decides whether a
sponsorship SO can publish before Accounts has costed it.

**D29. "Delivery month" (AC-K1) with no day.** The line's `delivery_date` is a DATE. Sponsorship
forms give a month. Convention needed: first of the month, last of the month, or a separate
month column. Netting is FIFO by delivery date (AC-I3a), so the choice changes which demand a
covering pool serves first - it is not cosmetic.

## 5. What is safe to build before those answers

One piece does not depend on any of the four, and it is the AC-K4 pin: a test proving a
sponsorship sales order derives order-inquiry rows exactly as a commercial one does. The
derivation reads no flag, so it appears to work for free - which is precisely why it needs a
test. Unpinned, the next change to the netting or the verb table can silently stop sponsorship
stock from ever reaching purchasing, and nothing would fail.

It can be pinned before AC-K1 exists by constructing the order with `is_sponsorship=True`
directly, which is what the test would do regardless of how K1 eventually builds one.

Everything else waits for D26-D29. In particular, no filter is added for AC-J2 (see the
correction in section 2).

## 6. Test plan (Phase 2, test first)

- Re-point engine as a PURE function first, with golden cases: full quantity moves, partial
  moves date by date, a remainder that must be cancelled, a destination whose quotation
  disagrees, and the invariant that source qty + destination qty is conserved across the move.
- Forecast/analytics: a pre-order on a project does not appear in committed value.
- Sponsorship: an approved form produces a draft at price zero; product resolution and
  discontinued checks still fire; price and qty checks do not.
- Every test seeds its own chain and uses a marker prefix. CI's database is empty.

## 7. Risk

**The re-point is the only place in phase 2 where quantity moves between two committed
documents.** Getting it wrong double-counts demand, which is the exact failure the order
inquiry exists to prevent. It deserves the pure-engine-plus-golden-set treatment that P9's
ranking and P10's netting got, not an in-service loop.
