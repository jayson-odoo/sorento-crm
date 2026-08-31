# UAC - Flyer reading: adopt an unmatched printed code as an existing product

**Companion to:** `PLAN-flyer-code-adopt.md`
**Status:** S1 built (adopt + undo, Groups A and B). S2 (proposals follow, Group C) pending
- see `#422`. Undo revised to a deferred action, not an `AlertDialog`, in the S1 review pass
(31 Aug 2026) - see AC-B.3. Approved in session 31 Aug 2026 (captain rulings R1-R5 in the plan).
**Legend:** `[BE]` backend/pytest · `[FE]` frontend/vitest · `[E2E]` real FE->BE->DB via agent-browser · `[MIG]` migration · `[T]` CI guard.

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the
real stack for the side marked.

---

## Journey

**Actor:** a reviewer holding the printed flyer, with `master_data.products.edit`
(the same slug that already gates Apply sizes and Propose specs on this screen).

1. They open a finished flyer reading from Dealer Kit > Flyer readings and scroll to
   **Codes the product master does not have**. 34 rows. Each row shows the printed code,
   its pages, and the nearest existing code with a % alike badge. Nothing was applied
   for them (PLAN-flyer-seeding D8 still holds).
2. On the row `SRTBT1835` they press **This is...**. A small dialog opens with a product
   picker already set to the nearest code `SRTBT1835-16`. They can search for any other
   product instead; the search is served by the server, never a capped list. One
   **Confirm** button, no other decision.
3. The row flips in place to **Adopted as `SRTBT1835-16` · Undo**. The report has been
   recomputed: the code now counts as matched everywhere the report is read from, so the
   brochure seed places it, its printed size becomes a dimension candidate, and the spec
   propose pass will read its card.
4. The **Product specifications** section, if a proposal batch already exists, shows one
   line: *Codes were adopted or undone after this proposal. Propose again to reflect
   them.* Nothing in the current batch was touched. When they press **Propose again**, rows
   for `SRTBT1835-16` appear, badged `Flyer`, with values read from the card printed under
   `SRTBT1835`.
5. **Undo** on an adopted row starts a countdown (no confirmation dialog - see AC-B.3); the
   button carries a Cancel, and when the window lapses the row returns to unmatched. Specs
   already applied to the product are not reverted (applying was its own deliberate act).

A viewer without the edit permission sees adopted rows and the badge, and no buttons.

Decisions the reviewer makes: which product (one), and whether to undo (one). Everything
else is derived.

---

## Group A - Adopting (S1)

### AC-A.1 [BE] Adopt puts the code in `matched` and out of `unmatched`
Given a done reading whose printed code `X` is unmatched, and an active product `P` in
the same company that no printed code on this reading resolves to,
When `PUT /api/v1/dealer-kit/flyer-readings/{id}/code-overrides/X` with `{"productId": P}`,
Then 200 with the full reading detail; `report.matched` contains an entry with
`code == "X"`, `productId == P`, `productCode == P.product_code`, `adopted == true`,
`pages` == the pages `X` was printed on; `report.unmatched` no longer lists `X`;
`codeOverridesChangedAt` is set.

### AC-A.2 [BE] Adopted product is a product for every reader of the report
Given AC-A.1,
When the report is recomputed (`report_for`),
Then a card under `X` that prints a size yields a `dimensionCandidates` entry for `P`;
`flyer_seed_service` resolves `X` to `P` (seed places the product);
`notPromoted` reports `P` when the linked promotion lacks it.

### AC-A.3 [BE] Nearest code is prefilled, any product is allowed
Given an unmatched code with suggestion `S` and another product `Q` (same company),
When adopted with `productId == Q`,
Then 200 and `matched` names `Q`. The suggestion is a default in the UI only; the server
does not prefer it.

### AC-A.4 [BE] Re-adopting replaces
Given `X` already adopted as `P`,
When `PUT` again with `Q`,
Then 200, `X` is matched as `Q`, `P` is free again.

### AC-A.5 [BE] Refusals, in words the reviewer can act on
- `X` is not printed on this reading -> 404 `flyer_code_not_printed`.
- `X` resolves in the master by itself -> 409 `flyer_code_already_matched`
  ("`X` is already a product; nothing to adopt").
- `P` is not found in the company scope (other company, deleted) -> 404
  `flyer_adopt_product_not_found`.
- `P` is already what another printed code `Y` on this reading resolves to, either by
  itself or by an earlier adoption -> 409 `flyer_adopt_target_taken`, message names `Y`
  and its page(s). (R1: two cards never point at one product.)
- Reading not `done` -> 409 in the same words the seed and sizes apply use.
- Caller lacks `master_data.products.edit` -> 403. `dealer_kit.page.view` alone reads
  the report and cannot write.

### AC-A.6 [BE] A stale override is ignored, not an error
Given `X` adopted as `P`, and `P` later deleted,
When the reading is read,
Then `X` is back in `unmatched` with its suggestion, the response is 200, and the
override key is left as-is (no write on a GET).

### AC-A.7 [MIG] Column
Migration adds `code_overrides JSONB NOT NULL DEFAULT '{}'` and
`code_overrides_changed_at TIMESTAMP NULL` to the flyer reading table; existing rows
read back `{}` / `NULL`; downgrade drops both. Head id <= 32 chars, chained on
`448_merge_s6b_ptag`.

### AC-A.8 [T] `response_model` carries the new fields
A test asserts `adopted` on a matched entry and `codeOverridesChangedAt` on the detail
are present in the serialised response (lesson: undeclared fields are dropped silently).

### AC-A.9 [FE] The row, before and after
Given the unmatched section with permission,
Then each unmatched row shows a **This is...** button; an adopted row (a `matched` entry
with `adopted`) is listed in the SAME grid, in page order, showing
"Adopted as `CODE` name" and an **Undo** button; the section header counts
"N codes, M adopted"; the subtitle reads "These will not be in the brochure until
adopted. Suggestions are never applied for you."
Without permission: no buttons, adopted state still visible.

### AC-A.10 [FE] The dialog
When **This is...** is pressed,
Then a dialog opens titled "`X` is which product?", with a `SearchableSelect` in server
mode (`fetchOptions` over `listPickerProducts`, page size 50) preselected to the
suggestion when there is one, a `clearable` value, and a single Confirm reading
"Use `CODE` for `X`" disabled until a product is chosen. Loading, empty search and
error states render. Usable at 375px and 1280px.

**Every product is reachable (R5):** typing any code or name fragment that exists
anywhere in the 10k+ master returns it, because the search runs on the server; the list
pages with load-more and is never truncated to a client-side cap. A vitest asserts the
select is in `fetchOptions` mode and that a query is forwarded to `listPickerProducts`.

### AC-A.11 [FE] Success and failure
On 200 the reading query is replaced with the response (no refetch flash), a toast
"`X` adopted as `CODE`" shows, the dialog closes and the row flips.
On error the extracted message toasts (the 409 target-taken text is what the reviewer
reads) and the dialog stays open.

### AC-A.12 [E2E] Adopt round trip
Navigate by sidebar from `/` to the reading. Adopt one unmatched code to its suggestion.
Then: row shows adopted; `dealer_kit.flyer_reading.code_overrides` in the DB holds the
key; a reload of the page shows the same state; the matched count went up by one and the
unmatched count down by one.

---

## Group B - Undo (S1)

### AC-B.1 [BE] Undo
Given `X` adopted,
When `DELETE .../code-overrides/X`,
Then 200 with the detail; `X` is in `unmatched` with its suggestion; `matched` does not
name `P` for `X`; `codeOverridesChangedAt` updated. Deleting a key that is not set -> 404
`flyer_code_not_adopted`. Same permission and status rules as adopt.

### AC-B.2 [BE] Undo does not touch the product
Given specs were applied to `P` from a proposal batch,
When `X` is undone,
Then `product_specifications` for `P` is unchanged and the batch rows are unchanged.

### AC-B.3 [FE] Undo is a deferred action, not a confirmation dialog
Captain ruling, S1 review (31 Aug): PRINCIPLES.md "Design mandates" / ADR-PRODUCT-STANDARDS
govern over this plan's original `AlertDialog` text - a detach action is a
server-deferred pending action with a countdown, never a confirm dialog. Pressing
**Undo** parks `flyer_reading.undo_code_adopt` (`useDeferredRowAction` /
`DeferredActionButton`, the same mechanism every other detach in the app uses) and the
button becomes a countdown with Cancel; nothing is asked up front. When the window
lapses the server runs the same `unadopt_code` the DELETE route always did (R2 holds:
specs already applied to `CODE` are never touched, either way the window resolves).
Cancel aborts before it commits. The control is disabled while its own action is
counting down.

Permission narrowing, reviewed and accepted: the direct DELETE route enforces
`dealer_kit.page.view` AND `master_data.products.edit`; the generic
`/pending-actions` route checks exactly one slug, so the deferred path is registered
against `master_data.products.edit` only - the permission that actually authorises
the write. `dealer_kit.page.view` still gates reaching the screen the button is on.

### AC-B.4 [E2E] Undo round trip
Continue from AC-A.12: undo the same code. Row is back to unmatched with the suggestion;
DB key removed; counts back to the starting values.

---

## Group C - Spec proposals follow the adoption (S2)

### AC-C.1 [BE] Propose reads the printed card, writes to the adopted product
Given `X` adopted as `P`, and the card printed under `X` states specs the rules catch,
When a proposal pass runs,
Then rows exist with `product_id == P`, `product_code == P.product_code`,
`pages == X's pages`, the same source/evidence as any matched card (`Flyer`, not
`manual`), and the values come from `X`'s card text.

### AC-C.2 [BE] Undo before a pass, no rows
Given `X` adopted then undone,
When a pass runs,
Then no rows name `P` because of `X`.

### AC-C.3 [BE] Batch is never touched by adopt or undo
Given a settled batch with an edited row and a dismissed row,
When a code is adopted or undone,
Then the batch, its rows, their edits and dismissals are unchanged.

### AC-C.4 [FE] Hint line
Given a settled batch and `reading.codeOverridesChangedAt > batch.createdAt`,
Then the Product specifications section shows one line above the grid: "Codes were
adopted or undone after this proposal. Propose again to reflect them." Not shown when
there is no batch, when the batch is proposing, or when the timestamps say nothing
changed since. It is a status line, not an explanation of the feature.

### AC-C.5 [E2E] Adopt, propose again, rows appear
Adopt a code, press Propose again, wait for settle: the adopted product appears in the
proposal groups with `Flyer` badges; the hint line is gone.

---

## Out of scope (recorded, not built)

- Master-level alias (`products.alternate_codes`). Trigger: the same printed code is
  adopted on a second flyer. Backlog.
- Bulk "adopt every suggestion above N%". D8 forbids the silent version; the per-row
  click is the feature.
