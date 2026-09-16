# PLAN: price tag text prices print a bare figure + `{{product.currency}}` token; AI extract prompt registered and hardened

Status: building (16 Sep 2026)
Owner ruling: 16 Sep 2026, "don't show the currency ... we should have a variable currency for flexibility" and "can I just fix at the prompt from the UI?" (answer: not registered today, so register it).
UAC: `price-tag-currency-token-extract-prompt-acceptance-criteria.md` (alongside).
Branch: `feat/price-tag-currency-token-extract-prompt-16sep`, worktree `.claude/worktrees/price-tag-currency-16sep`.

## Why

1. A TEXT layer bound to `list_price` / `sell_price`, and the `{{product.list_price}}` / `{{product.sell_price}}`
   merge fields, always print `RM 535`. `formatTagPrice` in `lib/dealer-kit/price-badge.ts:119` hardcodes the
   `RM ` prefix; the badge layer has a `showCurrency` toggle, the text path has none. The owner wants the figure
   bare and the currency as its own variable, composed by the designer.
2. The portal AI extract on `portal.price_tag_request` returned `{"products": []}` on 1 of 3 prod runs against a
   pasted list of 21 bare product codes (usage rows 11:40:17 / 11:42:13 / 11:42:20 on 16 Sep, 498 prompt tokens,
   completion 413 / 413 / 7). Local rerun 6/6 returned 21 lines. Cause: the prompt says the `products` array is
   "Optional ... when the document lists line items" and the form has `Fields: []`, so a bare code list sits on the
   boundary and the model sometimes decides "no line items". The system prompt is hardcoded in
   `app/services/ai_extract/extract_service.py::_build_messages` and not in `PROMPT_KEYS`, so it cannot be edited
   from System Management > AI Assistant.

## Measured facts (16 Sep 2026, local prod copy)

- `dealer_kit.tag_template`: 4 rows, 0 with a price text token or price slot; `tag_template_version`: 5 rows, 0.
  No data rewrite script is needed. The owner is composing the first such layer by hand today.
- `PriceView` (`app/services/dealer_kit/pricing.py`) already carries `currency`; `products.currency` is
  `String(3) NOT NULL default MYR`. The value never reaches the tag data payload today.
- Text prompt of the price tag extract = 328 tokens (tiktoken o200k). The 21-line paste = 170 tokens.

## Design (simplest thing that works)

### A. Text prices print bare; new `{{product.currency}}` merge field

FE only for rendering, BE adds one field to the payload.

- `lib/dealer-kit/product-block.ts::resolveSlotText` price branch calls `formatTagPrice(amount, false)`.
  `535`, `1,599`: grouping and whole-ringgit rounding unchanged. The BADGE path (`showCurrency`) is untouched.
- `lib/dealer-kit/merge-fields.ts`:
  - `FIELD_LABELS` gains `{ path: 'product.currency', label: 'Currency', group: 'Product' }` right after Sell price.
  - `resolvePath('product.currency', data, layer)` reads the subject (`subjectOf(data, layer)`, so a part-bound
    layer prints the PART's currency, D7) and returns `subject.<product|set|line|part>.currency ?? 'MYR'`.
    The fallback covers an older pinned/cached row that predates the field. It is NOT a slot binding: no
    `SlotBinding` union change, no Inspector option. `hasSubjectAwareToken` already treats `product.*` as
    subject-aware, nothing to do.
- FE types (`lib/dealer-kit/tag-template-types.ts`): `currency?: string` on `ProductTagData`,
  `ProductSetTagData`, `LineTagData`, `TagPartData`. Optional, because pinned data predates it.
- BE (`app/services/dealer_kit/tag_data_service.py`): every row builder that emits `list_price` also emits
  `currency`:
  - `product_tag_data`: `prices.currency if prices else DEFAULT_CURRENCY` (import from `pricing`).
  - set data: the first member's `PriceView.currency`, else `DEFAULT_CURRENCY`.
  - line tag rows, part rows, the resolved-line and subject builders: copy `data["currency"]`.
- BE schemas (`app/schemas/price_tag.py`): `currency: str = "MYR"` on `ProductTagData`, `ProductSetTagData`,
  `TagPartData`, `ResolvedLineData` and the line-tag response class that carries `list_price` / `sell_price`
  (`response_model` drops undeclared fields; the route test asserts the field, per LESSONS-LEARNT).
- No migration. No template rewrite. The designer types `{{product.currency}} {{product.sell_price}}`.

### B. AI extract system prompt registered PER FORM, price tag default hardened

Owner ruling 16 Sep (second): per form, and rule 8 only on the price tag request.

- `extract_service.extract_prompt_key(form_key) -> "ai_extract_" + form_key.replace(".", "_")`. Nine form
  keys exist: five `portal.*` in `form_schema_registry.py`, four `master.*` in
  `app/api/v1/master_data/ai_extract_field.py::_ENTITY_TO_FORM_KEY`.
- `app/services/ai_prompt_registry.py`: `_ai_extract_base_fallback()` returns today's system text (rules 1 to 7
  verbatim). `PROMPT_KEYS` gains one `PromptKeySpec` per form key (`active=True`, `activates_in=None`,
  `variables=[]`, role "AI extract - <form key> prefill (JSON)"). Only `ai_extract_portal_price_tag_request`'s
  fallback appends rule (8): "When the form has line items, `products` is REQUIRED whenever the document shows any
  product code: every product code line is one entry, even when no quantity, price or name is shown. Return an
  empty `products` array only when no product code appears anywhere." The other eight equal the base text.
- `_build_messages(form_key, ...)` takes the system text from `get_prompt(self.db, extract_prompt_key(form_key)).text`
  (call shape as `product_spec_understanding.py:552`). The per-form user message stays built in code. Its
  line-items clause loses "Optionally"; on the price tag form it says "(see rule 8)".
- A test walks every registered form key and asserts a prompt key exists, so a new form cannot ship without one.
- No retry loop. The prompt is the fix.

### C. Live red dot: designer and detail poll the diff; "Update all" removed

Measured 16 Sep on the local prod copy: `resolve_request_line_data` (the batched live resolve behind
`GET /{id}/data-changes`) costs 16 to 414 ms per request (18-tag request: 212 ms). Polling one open page every
30 s is under 1 percent of one worker. No push channel, no listener.

- New hook `useTagDataChanges(requestId, { enabled })` in `app/(protected)/dealer-kit/price-tag-requests/hooks/`
  wrapping `listTagDataChanges` with react-query: `refetchInterval: 30_000`, `refetchIntervalInBackground: false`
  (hidden tab does not poll), `refetchOnWindowFocus: true`, `enabled` false for a terminal request (a terminal
  request never carries the key). Precedent: `notifications-sheet.tsx` and the SLA thread already poll this way.
- `RequestTagDesigner.tsx` and `PriceTagRequestDetail.tsx` replace their `useState` + one-shot `useEffect` with
  the hook; `decideTagPin` / recheck call `refetch()` (or invalidate) instead of `loadDataChanges()`. The rail red
  dot (`RequestTagDesigner.tsx:2019`) and the header pill (`PriceTagRequestDetail.tsx:782`) are unchanged
  consumers, so a product edit shows within 30 s, or at once on tab focus, with no reload.
- Remove the `Update all` button (`PriceTagRequestDetail.tsx:786-796`), `updateAllPins`, and the FE service
  `updateAllTagPins` if nothing else imports it. The backend pin-all route and its tests stay (trigger to remove:
  the next lane that touches that route).

### D. List shows "Product data changed · N" from a stored count, refreshed only for touched rows

Computing the diff per list row would add up to 50 x 60 ms to every page load. Instead the count is cached on
the request and refreshed only when a cheap query says the request's products were touched after the last check.

- Migration `ptag_0012_data_change_cache` (parent `ptag_0011_line_promo`): `price_tag_requests` gains
  `data_changed_tag_count INTEGER NOT NULL DEFAULT 0` and `data_checked_at TIMESTAMP NULL`.
- `tag_data_service.store_data_change_count(db, request, rows)` writes `count(rows with data_changes)` and
  `now()` onto the request (0 for terminal). Called by every path that already runs the diff: the data-changes
  GET, recheck, pin (update / keep), and the detail response route, each followed by the commit those routes
  already do (the GET adds one). The print / PDF read path does NOT write (worker, read-only by design).
- `PriceTagRequestService.touched_request_ids(db, requests) -> set[str]`: one grouped SQL over the page's
  non-terminal requests: `max(greatest(updated_at, created_at))` across `products`, `product_specifications`,
  `promotions` (via the line's promotion), `product_sets` + `product_set_members`, `product_attachments`, joined
  through the request's lines and tags, compared with `data_checked_at` (null = touched). Named gap: a deleted
  image link leaves no timestamp, so that change shows on the next open of the record, not in the list.
- `list_page` route: for touched rows only, run `resolve_request_line_data` + `store_data_change_count`, then
  commit. Typical cost after one product edit: one or two resolves, once. `PriceTagRequestListItem` gains
  `data_changed_tag_count: int = 0` (response_model gate: route test asserts it).
- `PriceTagRequestsList.tsx`: a `Badge`-based pill `Product data changed · N` in a new column `Product data`
  (explicit `size`, `truncate`), hidden when 0; same amber style as the detail header pill. No "Update all"
  anywhere: the user clicks into the record to see what changed.

## Out of scope (named triggers)

- Exact-tier product resolver on `Srtkt1643ss BL` style codes (21/21 unresolved locally): separate ruling.
- Logging image pixel size / raw response on the usage row: separate lane if the owner wants it.
- Data rewrite of existing templates: trigger = a prod template row with a price text token that predates
  this deploy (today there are none).

## Tests (tester writes red first)

Vitest
- `lib/dealer-kit/product-block.test.ts`: text slot `sell_price` and `list_price` resolve to `535` / `1,599`,
  no `RM`.
- `lib/dealer-kit/price-badge.test.ts`: `formatTagPrice(760)` still `RM 760` (badge default unchanged).
- `lib/dealer-kit/merge-fields.test.tsx`: `{{product.currency}}` resolves to the subject's currency for a
  product, a line, a set, and a part-bound layer (D7); missing field falls back to `MYR`; `product.currency`
  appears in the field list under Product with label Currency; `{{product.sell_price}}` renders bare.

Pytest (Postgres fixture, seed own chain, never `LIMIT 1`)
- `tests/test_dealer_kit_tag_data.py`: `product_tag_data` row carries `currency == "MYR"` from the product;
  set data and line tag rows carry it; a part row carries its own product's currency.
- `tests/test_dealer_kit_tag_data_routes.py`: the tag data route response body includes `currency` on the
  product row and on a line tag row (response_model gate).
- `tests/test_ai_extract_service.py`: `_build_messages` system text equals
  `get_prompt(db, extract_prompt_key(form_key)).text`; every registered form key has a `PROMPT_KEYS` entry; only the
  price tag fallback carries rule (8) / "REQUIRED"; an override on the price tag key does not leak into another
  form; the price tag user-message clause no longer contains "Optionally".
- `tests/test_ai_prompt_registry*.py` (existing key-inventory test, if one enumerates keys): add the nine keys.

Slice C (vitest)
- `useTagDataChanges` hook: query options `refetchInterval === 30000`, `refetchIntervalInBackground === false`,
  `refetchOnWindowFocus === true`, disabled for a terminal status. Detail renders the pill from the hook's data and
  no `Update all` button exists at any count (`RequestDesignSection`/detail tests that asserted the button flip).
  Designer rail red dot appears when the hook's data changes without a remount (rerender with new query data).

Slice D (pytest + vitest)
- Migration test in the existing style (`tests/test_migration_*`): both columns exist after upgrade, defaults hold.
- `store_data_change_count` writes count + timestamp; 0 for a terminal request.
- `touched_request_ids`: a request whose product `updated_at` is after `data_checked_at` is touched; one checked
  after the last edit is not; `data_checked_at IS NULL` is touched; a terminal request is never touched; a spec row
  update, a promotion update, a set member update and a product attachment insert each count as touched.
- List route: a touched row comes back with the refreshed `data_changed_tag_count` and its `data_checked_at` set;
  an untouched row is served from the stored count (assert the resolver was not called for it, monkeypatch).
- vitest `PriceTagRequestsList`: the `Product data` column renders `Product data changed · 2` for a row with
  count 2 and nothing for 0.

## Verification

- agent-browser on the lane stack (:3080 / :8080, booted for the check, shut down after): sidebar to
  Dealer Kit > Tag templates, open a template, add a text layer with `{{product.currency}} {{product.sell_price}}`,
  canvas shows `MYR 535`-style text with the currency from the token and a bare figure from the price token;
  the Insert field dialog lists Currency under Product; a badge layer still shows `RM`.
- System Management > AI Assistant lists the `ai_extract` prompt with the rule (8) default text.
- Live extract on the 21-line paste from 16 Sep (scratchpad `pasted.txt`) returns 21 lines, 3 of 3 runs.

## Rollout

- No migration, no worker change, no env change. Owner: after deploy, open the prompt in the UI once to confirm
  it lists; compose the currency token on the live template.
