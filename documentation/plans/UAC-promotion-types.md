# UAC — Maintainable promotion types with per-type expired-promo behaviour

**Status:** authoring → FE mock → BE + tests → self-verify (pytest + live MCP) → handoff
**Sources:** captain decision `promo-succession-design/captain-decision-2026-08-14.md`
(authoritative), design scout `promo-succession-design/report.md` (evidence base).
Where they conflict, the captain wins (his D1/D2 supersessions are folded in below).

**Problem in one line:** a customer asks "any promo for SRTWC286?", the bot answers with
the A3 flyer (active) and never mentions the July WC promo that just ended — because the
system has no idea the two are different *kinds* of promotion with different rules about
what happens after the end date.

---

## Journey

### J1 — The customer asking about a product (WhatsApp → n8n → CRM)

**Who:** an end user / dealer chatting on WhatsApp. **Arrives from:** a Respond.io thread.

- **What the system already knows:** their contact, their access level (already asked and
  confirmed earlier in the spine), and — from their message — the product they named. They
  are asked for nothing new by this feature.
- **Step 1 (no decision):** they type "any promo for SRTWC286?". The reformulator sets
  `domain_hint=promotion`; the spine POSTs `/api/v1/system/references/resolve`.
- **Step 2 (no decision):** the resolver walks `promotion_products` back to the promotions
  containing that SKU, and now applies the **per-type serving policy** before answering:
  live promos win; where a type has no live promo and the type's config allows it, the
  latest expired promo of that type comes back marked expired-but-usable; a *special*
  promo never comes back after its end date.
- **Step 3 (no decision):** the agent calls `crm_marketing_promotions_list`, which honours
  the same policy, so the second hop cannot re-introduce what the first hop excluded.
- **What they hold at the end:** either the live promos, or "the JULY SORENTO WC PROMO
  ended on 31/07 but still applies until the end of the year", or — when only an expired
  *special* exists — no promotion at all (correct: it genuinely cannot be honoured).

### J2 — n8n uploading a promotion file (external create)

**Who:** the n8n promo-intake workflow. **Arrives from:** a marketing PDF dropped into the
intake channel.

- **What the system already knows:** the uploaded file's name, which n8n posts as
  `promotions.description` (this is the only "name" a promotion has).
- **Step 1 (no decision):** `POST /api/v1/external/promotions/` creates the promotion. The
  backend **derives** the promotion type from the file name's markers — "special" → Special,
  "PP" → PP, focus wording → Focus Item, A3 signals → A3 Flyer, no marker → Standard. Nobody
  is asked to pick a type.
- **What they hold at the end:** a promotion row carrying its type and
  `promotion_type_source = "auto"`; the response echoes both so n8n can log the verdict.

### J3 — Marketing fixing a misclassification

**Who:** marketing / CS staff. **Arrives from:** the sidebar, Marketing Management →
Promotions.

- **What the system already knows:** the promotion and its auto-assigned type.
- **Step 1 (one decision):** they see the **Type** column on the list, spot a wrong value,
  open the promotion's edit form (or the detail page's Edit) and pick the right type from a
  clearable select.
- **What they hold at the end:** the corrected type, stamped `promotion_type_source =
  "manual"` so a later re-upload of the same file does not silently undo the correction.
  Serving behaviour changes on the next bot question — no redeploy. A special that became a
  standard is exactly this edit (captain D3: no succession lineage in v1).

### J4 — Admin tuning what a type does after expiry

**Who:** an admin. **Arrives from:** Marketing Management → Promotion Types.

- **What the system already knows:** the five seeded types and their current config.
- **Step 1 (one decision per row):** open a type in a modal, toggle **Show when expired**
  and set its bound (usable to end of year / max age in days).
- **What they hold at the end:** the MCP tools and the resolver honour it on the very next
  call. No code change, no deploy — this is the captain's "maybe I can control this promo
  type if expired still want to show in MCP so it is configurable".

---

## Decisions (bound to the captain's, with the builder's calls flagged)

- **D1 — Types are DATA.** A `promotion_types` table, admin-CRUD-able, not a Python enum.
  Seeded with the five known types. `promotions.promotion_type_id` is a nullable FK
  (`ON DELETE SET NULL`), so deleting a type degrades rows to "unclassified", never to a
  broken FK.
- **D2 — Per-type expiry config.** `show_expired` (does an expired promo of this type still
  surface at all) plus two optional bounds, ANDed when both are set:
  `expired_valid_until_year_end` (usable only while the calendar year it ended in is still
  running — the captain's "till end of year") and `expired_max_age_days` (a hard recency
  cap). *Builder's call, per captain D2: bounds stay configurable; the seeds below are the
  starting values, not a hardcoded rule.*
- **D3 — Unclassified rows follow the default type.** The type flagged `is_default` (Standard)
  supplies the policy for any promotion with no type. Legacy rows therefore behave exactly as
  "standard" (even expired can be used), which is what they are.
- **D4 — Per-type suppression, not global.** A live promo suppresses expired promos **of its
  own type**, within the candidate set of the question being answered. A live A3 flyer does
  NOT suppress an expired standard promo — that suppression is precisely the SRTWC286 bug.
- **D5 — Classification markers live on the type row** (`match_markers` JSONB + `match_priority`),
  so a new marker is a data edit, not a deploy. Special is evaluated first: when a name
  carries two markers, the more conservative type (the one that cannot be used after expiry)
  wins.
- **D6 — No succession lineage** (captain D3 stands).

### Seeded types

| code | name | show_expired | year-end bound | max age (days) | markers | priority |
|---|---|---|---|---|---|---|
| `special` | Special Promo | **false** | – | – | `special` | 10 |
| `pp` | PP Promo | true | true | – | `pp` | 20 |
| `focus_item` | Focus Item | true | true | – | `focus`, `focus item` | 30 |
| `a3_flyer` | A3 Flyer | true | false | 180 | `a3`, `a3 flyer` | 40 |
| `standard` | Standard Promo | true | true | – | (none — `is_default`) | 99 |

---

## Acceptance criteria

### Type entity + admin CRUD

**T1 — Table + seeds.** A migration creates `promotion_types` and seeds exactly the five rows
above, with `standard` as the single `is_default` row. Re-running the migration's upgrade on a
DB that already has them does not duplicate. *BE + pytest.*

**T2 — Promotion carries a type.** `promotions.promotion_type_id` (nullable FK, ON DELETE SET
NULL) and `promotions.promotion_type_source` (`auto` | `manual`, nullable). Existing rows are
backfilled by running the classifier over their description. *BE + pytest.*

**T3 — Admin list.** Marketing Management → **Promotion Types** renders a DataGrid of types
(code, name, show-expired, bounds, markers, promotions using it), with an "Add" toolbar
button, per ADR-PRODUCT-STANDARDS and the shared DataGrid rules. *FE + vitest.*

**T4 — Create/edit in a modal.** Add and Edit open a modal (not a page); required code + name;
`show_expired` toggle; the two bounds; markers as a token list; priority; default flag. *FE +
vitest.*

**T5 — Delete is a hard delete behind a confirmation.** `AlertDialog` / `ConfirmDeleteDialog`,
copy "Confirm delete" / "This action cannot be undone"; the backend `DELETE` really deletes and
promotions pointing at it fall back to NULL (→ default-type policy). Deleting the `is_default`
row is refused with a 409 explaining why. *FE + BE + pytest.*

**T6 — Unique code.** Creating a second type with an existing `type_code` returns 409, not a
500. *BE + pytest.*

### Auto-classification

**C1 — Marker match at external create.** `POST /api/v1/external/promotions/` with
`description = "SORENTO SPECIAL PROMO_22052026 DEALER.pdf"` creates a promotion whose type is
`special` and whose `promotion_type_source` is `auto`. *BE + pytest.*

**C2 — All five markers.** `"... PP PROMO COMBINE ..."` → `pp`; `"... FOCUS ITEM ..."` →
`focus_item`; `"_SORENTO A3 FLYER 2025-2026_compressed"` → `a3_flyer`; a name with no marker
(`"CABANA SHELF PROMO 31032026 (DEALER USE)"`) → `standard`. *BE + pytest.*

**C3 — Word-boundary matching, not substring.** `"SUPPLY PROMO"` does NOT match the `pp`
marker; `"SPECIALIST TOOLS PROMO"` does NOT match `special`. *BE + pytest.*

**C4 — Conservative on collision.** A name carrying two markers resolves to the
lowest-`match_priority` type (special before pp/focus/a3). *BE + pytest.*

**C5 — Manual wins over auto.** When n8n re-sends a promotion that a human has already
retyped (`promotion_type_source = "manual"`), the update-in-place path leaves the type alone.
An `auto` row is re-classified normally. *BE + pytest.*

**C6 — Markers come from the DB.** Adding a marker to a type row changes classification with
no code change (the classifier reads `promotion_types.match_markers`). *BE + pytest.*

### Type visible and editable

**V1 — List column.** The promotions DataGrid shows a **Type** column (explicit `size`,
truncate + title), rendering the type name — never a UUID. *FE + vitest.*

**V2 — Detail shows it.** The promotion detail page shows Type in the same position its edit
form does (view and edit are the same layout), with an explicit empty state
("Unclassified — treated as Standard") when NULL. *FE + vitest.*

**V3 — Edit changes it.** The promotion edit form has a clearable `SearchableSelect` of types;
saving stamps `promotion_type_source = "manual"`. *FE + BE + vitest.*

**V4 — Special → standard is one edit.** Changing a promotion's type from Special to Standard
immediately changes its post-expiry behaviour (covered end-to-end by S5). *BE + pytest.*

### Per-type serving semantics (the shared policy)

Notation: "candidate set" = the promotions a given question already narrowed to (e.g. the
promotions containing product P that overlap the contact's access levels).

**S1 — Live always wins.** Any live promotion in the candidate set is returned. *BE + pytest.*

**S2 — Per-type expired fallback.** For a type with no live promotion in the candidate set and
`show_expired = true`, the latest expired promotion of that type (by `end_date` desc, then
`created_at` desc) is returned, flagged `is_expired = true` **and** `expired_but_usable = true`.
Exact `end_date` ties return both, capped at 2 per type. *BE + pytest.*

**S3 — Special never serves after expiry.** An expired `special` promotion is absent from the
served rows entirely, even when it is the only candidate. *BE + pytest.*

**S4 — Bounds are honoured.** A `pp` promotion that ended last calendar year is not served
(year-end bound); an `a3_flyer` that ended more than 180 days ago is not served (max-age
bound). Editing the type's config flips both outcomes with no deploy. *BE + pytest.*

**S5 — Per-type suppression only.** With a live A3 flyer and an expired standard promo both
containing product P, BOTH are served — the flyer live, the standard flagged
expired-but-usable. This is the SRTWC286 regression, pinned. *BE + pytest.*

**S6 — Unclassified follows the default type.** A promotion with `promotion_type_id = NULL`
is served under the `is_default` type's config. *BE + pytest.*

### END GOAL — both surfaces react to the configuration

**E1 — `/api/v1/marketing/promotions` honours it.** A new `serving_policy=true` query param
replaces the active-first/fallback gate with the per-type policy; each row carries
`promotion_type_code`, `promotion_type_name`, `is_expired`, `expired_but_usable`, and the
payload carries `serving_policy_applied: true`. Without the param the FE DataGrid behaviour is
byte-identical to today. *BE + pytest.*

**E2 — MCP hard-pins it.** `crm_marketing_promotions_list` sends `serving_policy=true` on every
call (pinned default, not an agent-visible param, mirroring the catalogue hard-pin), and its
description tells the agent to say the promotion **has expired but still applies** when
`expired_but_usable` is true. The two other promo-serving tools
(`crm_marketing_promotion_products_list`, `crm_marketing_promotion_attachments_list`) pin the
same policy against their parent promotion. *MCP + pytest (mcp suite).*

**E3 — `/api/v1/system/references` resolve honours it.** The promotion-domain reverse walk
(`_build_promotions_for_products`) applies the same shared helper, so an expired special is not
even resolved, and an expired-but-usable row is. Its `display` gains `start_date`, `end_date`,
`is_expired` (live definition, fixing today's raw-flag read), `promotion_type_code` and
`expired_but_usable`. Existing keys keep their shape. *BE + pytest.*

**E4 — One definition, two surfaces.** Both call the same helper module; a test asserts the two
surfaces agree on the same fixture set (no drift). *BE + pytest.*

**E5 — Live MCP proof (mandatory before done).** Against the running MCP server on :8765 with
the backend on :8000: a call proving an expired-but-usable type IS served with
`expired_but_usable: true`, and a call proving an expired `special` is NOT. Transcript pasted
into the verification log below. *Live check.*

### Non-regression

**N1 — FE listing unchanged.** Without `serving_policy`, `/api/v1/marketing/promotions` returns
the same rows, order, pagination and `fallback_used` as before. *BE + pytest.*

**N2 — Existing promo tests stay green.** `tests/test_promotion_*.py` and the MCP promotion
tests pass unchanged. *BE + MCP.*

---

## Verification log

### Automated suites

```
pytest tests/test_external_promotion_type_classification.py \
       tests/test_promotion_classifier.py \
       tests/test_promotion_serving_policy.py \
       tests/test_promotion_types_crud.py \
       tests/test_references_promotion_serving.py
46 passed

sorento_crm_mcp: pytest tests/            243 passed  (incl. test_promotion_serving_policy_pin.py)

vitest: PromotionTypesList.test.tsx        6 passed
        PromotionTypeFormModal.test.tsx    4 passed
        PromotionsList.typeColumn.test.tsx 3 passed
```

### Live check (E5) — MCP :8747 → API :8047 → local prod-copy DB

Fixtures are this feature's own rows (`ZZT-PROMOTYPE` prefix) on one product: a live
A3 flyer, an expired PP promo, an expired special.

`crm_marketing_promotions_list(product_ids=<SRTWC INLET>)` — the tool pins
`serving_policy=true`, the agent cannot switch it off:

```
MCP tools registered: 36
serving_policy_applied: True
rows returned: 2
 - ZZT-PROMOTYPE SORENTO A3 FLYER 2026 | type: A3 Flyer | is_expired: False | expired_but_usable: False | end_date: 2026-10-13
 - ZZT-PROMOTYPE SORENTO PP PROMO 2026 | type: PP Promo | is_expired: True  | expired_but_usable: True  | end_date: 2026-07-25
PASS: expired-but-usable served, expired special withheld
```

**The config actually drives it.** Flipping `special.show_expired` to true (no
restart of the MCP or the API) and re-running the same call:

```
rows returned: 3
 - ZZT-PROMOTYPE SORENTO SPECIAL PROMO 2026 | type: Special Promo | is_expired: True | expired_but_usable: True | end_date: 2026-08-04
 - ZZT-PROMOTYPE SORENTO A3 FLYER 2026      | type: A3 Flyer      | is_expired: False
 - ZZT-PROMOTYPE SORENTO PP PROMO 2026      | type: PP Promo      | is_expired: True | expired_but_usable: True
```

Reverting the toggle returns the 2-row answer above. That round trip is the END
GOAL: the MCP reacts to the promotion-type configuration, live.

### Live check (E3) — `POST /api/v1/system/references/resolve`

Same product, `domain=promotion`, dealer access:

```
- ZZT-PROMOTYPE SORENTO A3 FLYER 2026 | type: A3 Flyer | is_expired: False | expired_but_usable: False | end: 2026-10-13
- ZZT-PROMOTYPE SORENTO PP PROMO 2026 | type: PP Promo | is_expired: True  | expired_but_usable: True  | end: 2026-07-25
```

Byte-for-byte the same verdict as the MCP surface (E4), and the expired special is
absent from both.

### Migration / seed state

`alembic heads` → single head `361_promotion_types`, chained onto
`357_merge_grn_spo_fm_heads` (which already rejoined the container-status,
human-source-boost and GRN lanes). Applied to the local DB: the
five types seeded, and all 29 existing promotions classified from their file names
(28 standard, 1 A3 flyer, 0 unclassified).

### Live check rerun (2026-08-15, post machine reboot)

Both surfaces re-proven against a freshly restarted stack in one scripted pass
(`live_check.py`): 9/9 checks PASS — MCP serves the live A3 flyer and the expired PP
as expired-but-usable, hides the expired special; resolve returns the identical
verdict; flipping `special.show_expired` on makes BOTH surfaces serve the special
with no process restart, and reverting hides it again.

### Browser verification (agent-browser headless, prod build on :3047)

Full sidebar walk, logged in as the E2E user:

- **Nav**: Marketing Management → Promotions → **Promotion Types** entry renders and
  navigates to `/marketing-management/promotion-types` (screenshot `pt-list.png`).
- **List**: the five seeded types with When-expired pills (Special "Not served" red,
  others "Still served" green), plain-language rules ("Not served once expired",
  "Still applies until end of year", "Still applies within 180 days"), file-name
  markers, per-type promotion counts, and the Default tag on Standard Promo.
- **Create**: Add Promotion Type modal (Code, Name, Description, Show-when-expired
  switch, File-name markers, Match priority, Sort order, Default switch). Created a
  throwaway `zzt_test` type; row appeared with rule "Still applies, no time limit".
- **Delete**: trash icon → dialog titled "Confirm delete" with copy
  `Delete promotion type "ZZT Test Type"? This action cannot be undone.`, destructive
  red Delete; confirmed → backend `DELETE ... 200`, row gone (screenshot
  `pt-delete-dialog.png`).
- **Promotions list**: Type column renders per-row type names.
- **Promotion detail**: "Promotion Type" field always rendered; auto-classified rows
  read e.g. "Special Promo (from the file name)".
- **Retype round trip**: edit form's clearable Promotion Type select, Special →
  Standard saved (`PUT 200`, detail shows "Standard Promo" with the file-name hint
  dropped, i.e. the manual stamp), then reverted to Special.
- **Console**: zero page errors. The one warning (missing dialog description) was
  fixed by adding an `sr-only` `DialogDescription` to the form modal.

Environment note for future lanes: the CRM fires cross-origin API calls from the
browser, so the backend's `CORS_ORIGINS` must include the FE port. With :3047
missing, every preflight 400'd and react-query's retries pinned the renderer at
100% CPU - it presents as a hung browser, not as a CORS error.
