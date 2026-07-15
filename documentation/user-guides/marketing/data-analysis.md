# Marketing — Data analysis for the AI assistant

This guide is for **the AI assistant** (and for power users who want to know what it can answer). It maps natural-language questions about **promotions, promotion product lines, promotion documents, and campaigns** to the data the assistant can read, the filters it should use, and — most importantly — the **promotion date / activity rules** it must get right.

The assistant reads marketing data through **three** tools, all backed by the promotions tables:

| Tool | Use it for |
|----|----|
| `crm_marketing_promotions_list` | List / filter promotions (summary + linked attachments inline; no product lines). The default tool for "what promos do we have …". |
| `crm_marketing_promotion_products_list` | The **product lines** on promotions (per-SKU promo price / discount). Requires a `promotion_ids` **or** `product_ids` narrower. |
| `crm_marketing_promotion_attachments_list` | Promotion **documents** (flyers / brochures linked to a promotion). Requires a `promotion_ids` **or** `attachment_ids` narrower. |

> **Campaigns have NO assistant tool.** There is no MCP tool for marketing campaigns — the assistant **cannot** directly read campaign rows. The Campaign model is documented at the end so power users know what to ask for, but campaign questions must be answered from the **[Campaigns](/marketing-management/campaigns)** list page / export, not the assistant.

> **No UUIDs in answers.** Identify a promotion by its **description** (the promotion's human title — there is no separate name column), a product by **product code / name**, a document by its **filename**, a campaign by its **campaign code / name**.

> **Unfiltered calls are bounded.** `crm_marketing_promotions_list` called with no narrowing filter returns only the **latest 10** active promotions (newest first) so open questions like "what's our latest promo?" stay bounded. The **product** and **attachment** tools return an **empty page** with no narrower — always pass a `promotion_ids` / `product_ids` / `attachment_ids` filter for those two.

Menu paths (Marketing Management group):

* Promotions → [**All Promotions**](/marketing-management/promotions), [**Promotion Attachments**](/marketing-management/promotion-attachments)
* [**Promotion Products**](/marketing-management/promotion-products)
* [**Campaigns**](/marketing-management/campaigns)

---

## The single most important rule: ACTIVE vs EXPIRED, and which DATE the window tests

A promotion has a **flag** (`is_active`) **and** a **date window** (`start_date` → `end_date`). "Currently live" means **both**: `is_active = true` **AND** today is within `[start_date, end_date]`. Get this wrong and you will present an old or switched-off promotion as if it were running.

### 1. The `is_expired` flag — read it on every row

Every row from all three tools carries **`is_expired`**:

* `is_expired = false` → the promotion is **currently live**.
* `is_expired = true` → the row was **found but is NOT live** (flag off **or** today outside the start/end window).

**When `is_expired` is true, tell the user the promotion / line / document was FOUND but is EXPIRED. Never present an `is_expired` row as a live promotion.**

### 2. The `active` filter (default = active-first, with fallback)

| `active` value | Behaviour |
|----|----|
| omitted (default) / `true` | Return **active** promotions (flag on AND today in window). If a narrowing filter yields **zero** active matches, the tool **falls back** to inactive/historical rows and sets **`fallback_used = true`** on the response — surface those as "no live match; here's the closest expired one". |
| `false` | Return **inactive / expired / historical** promotions **only**. Use when the user explicitly asks for past / expired / ended promos. |

### 3. `date_mode` — which promotion date the `period_from` / `period_to` window tests

When the user gives a date window (`period_from` / `period_to`, `YYYY-MM-DD`), `date_mode` decides **which** promotion date that window is compared against. **This is the marketing equivalent of "which date column?":**

| `date_mode` | Tests | Use when the user says… |
|----|----|----|
| **`overlap`** (default) | The promotion's `[start_date, end_date]` **overlaps** the window | "valid / running / live **during** X", "promos active in March" |
| **`started`** | `start_date` falls **within** the window | "**released / launched / new / started** in the last N days", "new promos this month" |
| **`ended`** | `end_date` falls **within** the window | "**ended / expired / finished** in X", "which promos expired last week" |

> **`started` and `ended` automatically include BOTH active and historical rows** (they drop the active gate) — do **not** also pass `active` with them unless the user explicitly narrows to one state. `overlap` keeps the active-first behaviour above.

When in doubt about the window's meaning, use `overlap`. Dates are stored as Malaysia civil calendar days (`YYYY-MM-DD`); ranges are inclusive.

---

## Entity 1 — Promotion

**Tool:** `crm_marketing_promotions_list` (`GET /api/v1/marketing/promotions`)
**Table:** `promotions`

### Fields on each row
`description` (the promotion's title — **there is no separate `name` column**; the **All Promotions** grid shows this under **Description**), `start_date`, `end_date`, `is_active` (grid **Status** — Active / Inactive), `access_levels` (grid **Access**), `products_count` (grid **Products**), `attachments` (inline array of linked documents, grid **Attachments**), `created_at` (grid **Created At**), `created_by`, `updated_at`, and the computed **`is_expired`**.

### Filters
| Filter | Notes |
|----|----|
| `promotion_ids` | Canonical promotion UUIDs (csv / JSON / repeated). Resolve a promotion title to its UUID first. |
| `product_ids` | Promotions that contain any of these products. **OR-combines** with `promotion_ids` — a promotion is returned if it is in `promotion_ids` **OR** contains any product in `product_ids` (there is no AND option). |
| `active` | Active-first / fallback / historical-only — see the rule above. |
| `period_from` / `period_to` | Date window (`YYYY-MM-DD`). |
| `date_mode` | `overlap` (default) / `started` / `ended` — see the rule above. |
| `access_levels` | Filters promotions whose `access_levels` overlaps the supplied **names** (case-insensitive, translated name → code). Phrases like `sorento dealer`, `end user`, `mocha office` are **`access_levels` only — never `*_ids` values**. |
| `sort` / `dir` | See sortable fields. `dir` is `asc` / `desc` (default `desc`). |

> **Access levels** are a per-promotion audience tag (JSONB). The seeded default is `["dealer", "end_user"]`; the actual names are tenant-configured contact access types (e.g. "Sorento Dealer", "End User", "Mocha Office"). Use them to answer "which promos are visible to dealers / end users?".

### Sortable fields
`start_date`, `end_date`, `is_active`, `created_at`, `access_levels`, `products_count`. Default sort `created_at` (newest first for the assistant's bounded page).

### Example questions

1. **"What's Sorento's latest promotion?"**
   Call with no narrower → bounded to the 10 newest active promotions, newest first. Report the top row's `description` and window.

2. **"List active promotions running during March 2026."**
   `period_from=2026-03-01`, `period_to=2026-03-31`, `date_mode=overlap` (default). Report only `is_expired=false` rows as live.

3. **"Which promotions launched in the last 30 days?"**
   `date_mode=started`, `period_from=<today − 30d>`, `period_to=<today>` (includes active **and** historical — don't pass `active`).

4. **"Which promotions expired last month?"**
   `date_mode=ended`, `period_from=<first of last month>`, `period_to=<last of last month>`.

5. **"Show promotions available to dealers."**
   `access_levels=Sorento Dealer` (a name, not an ID). Pair with `active` if they want only live ones.

6. **"Is there a promotion on product <X> right now?"**
   Resolve product → `product_ids`. If the only match comes back with `is_expired=true` (or `fallback_used=true`), say it was found but is **expired**, not live.

7. **"List expired / historical promotions."**
   `active=false`. Sort `end_date desc` to surface the most recently ended first.

8. **"How many products are on promotion <Y>?"**
   Resolve → `promotion_ids`; read `products_count` (or list the lines with the product tool).

9. **"Promotions ending this week."**
   `date_mode=ended`, window = this week.

---

## Entity 2 — Promotion Product (line)

**Tool:** `crm_marketing_promotion_products_list` (`GET /api/v1/marketing/promotion-products`)
**Table:** `promotion_products`

A per-SKU line under a promotion: the product, its promo price, and the discount maths. **At least one of `promotion_ids` / `product_ids` is REQUIRED** — without a narrower the tool returns an empty page.

### Fields on each row
The linked **`product`** (code, name, `list_price`, dimensions, brand, category — grid **Product Code** / **Product Name** / **List Price**), **`promotion_price`** (grid **Promo Price**; stored as `promo_selling_price`), `discount_amount` (grid **Discount Amount**), `discount_percent` (grid **Discount %**), `dealer_discount_percent`, `dealer_cost`, `list_to_dealer_margin_amount`, the parent **`promotion`** reference (grid **Promotion** = the promotion's description), and the computed **`is_expired`** (true when the **parent** promotion is not live). Lines may belong to a **promotion group** (bundle / FOC rule) carrying `foc_tiers` (buy-N-paid, get-M-free combinations).

### Filters
| Filter | Notes |
|----|----|
| `promotion_ids` | Canonical promotion UUIDs. **(required path A)** |
| `product_ids` | Canonical product UUIDs — lines containing any of these. **(required path B)** |
| `active` | **Parent-promotion** activity (NOT product status). Default active-first with inactive fallback (`fallback_used`); `false` = inactive-promotion lines only. |
| `status` | **Product** status: `active` / `inactive` / `all`. (Distinct from `active`, which is about the promotion.) |
| `item_type` | Product `item_type` exact match. |
| `price_min` / `price_max` | Product `list_price` (MYR). |
| `length_min/max`, `width_min/max`, `height_min/max` | Product dimensions (mm). |
| `any_dimension_min` / `any_dimension_max` | Axis-agnostic — matches when ANY of L/W/H is in range. |
| `access_levels` | By parent-promotion access overlap (names). |
| `sort` / `dir` | Sortable: `created_at` only (default `created_at asc`). |

### Example questions

10. **"List the products on promotion <Y> with their promo prices."**
    Resolve → `promotion_ids`. Report each `product` code/name + `promotion_price` and `discount_percent`. Flag `is_expired` rows as expired.

11. **"What's the promo price for product <X>?"**
    Resolve → `product_ids`. If the parent promotion is `is_expired`, say the price was for an **expired** promotion.

12. **"Which promo SKUs are discounted more than 20%?"**
    `promotion_ids` (or `product_ids`), then read each line's `discount_percent` and keep > 20.

13. **"Show promotion lines for products priced between RM100 and RM300."**
    `promotion_ids` + `price_min=100`, `price_max=300`.

14. **"List the dealer cost / margin for SKUs on promotion <Y>."**
    `promotion_ids`; read `dealer_cost` and `list_to_dealer_margin_amount` per line (render MYR).

15. **"Are any 600 mm wide products on promotion?"**
    `width_min`/`width_max` around 600 (± tolerance) plus a `promotion_ids`/`product_ids` narrower.

16. **"List promo lines on expired promotions only."**
    `active=false` plus a narrower.

---

## Entity 3 — Promotion Attachment (document)

**Tool:** `crm_marketing_promotion_attachments_list` (`GET /api/v1/marketing/promotion-attachments`)
**Table:** `promotion_attachments`

The link between a promotion and a file (flyer / brochure). **At least one of `promotion_ids` / `attachment_ids` is REQUIRED** — without a narrower the tool returns an empty page.

### Fields on each row
The linked **`attachment`** (`original_filename` — grid **Attachment Filename**; `attachment_type.type_name` — grid **Attachment Type**; `stored_filename`, `mime_type`, `file_size_bytes`), `is_primary` (grid **Is Primary**), `sort_order` (grid **Sort Order**), the parent **`promotion`** reference (grid **Promotion** = description), `synced_to_excel` / `last_synced_to_excel`, and the computed **`is_expired`** (parent promotion not live).

### Filters
| Filter | Notes |
|----|----|
| `promotion_ids` | Canonical promotion UUIDs. **(required path A)** |
| `attachment_ids` | Canonical attachment UUIDs. **(required path B)** |
| `active` | Parent-promotion activity — default active-first with inactive fallback (`fallback_used`); `false` = inactive-promotion documents only. |
| `access_levels` | By parent-promotion access overlap (names). |
| `sort` / `dir` | Sortable: `created_at`, `sort_order` (default `created_at asc`). |

### Example questions

17. **"What documents are attached to promotion <Y>?"**
    Resolve → `promotion_ids`. List `original_filename` + `attachment_type.type_name`. Mark the `is_primary` one as the headline flyer.

18. **"Show the primary flyer for promotion <Y>."**
    `promotion_ids`, then pick the row with `is_primary = true`.

19. **"Which promotion does flyer <file> belong to?"**
    Resolve the attachment → `attachment_ids`; read the parent `promotion` description.

20. **"List promotion brochures for dealers."**
    `promotion_ids`/`attachment_ids` + `access_levels=Sorento Dealer`.

21. **"Any documents on expired promotions?"**
    `active=false` plus a narrower; every row will carry `is_expired=true`.

22. **"Order promotion <Y>'s attachments as they're displayed."**
    `promotion_ids`, `sort=sort_order`, `dir=asc`.

---

## Entity 4 — Campaign (NO assistant tool)

**The assistant cannot read campaigns** — there is no MCP tool. Answer campaign questions by pointing the user to the **[Campaigns](/marketing-management/campaigns)** list page (search / sort / export there). The data model below lets power users phrase precise list/filter questions for that page.

**Table:** `marketing_campaigns` (model class `MarketingCampaign`). Campaign types live in `campaign_types`.

### Fields
| Field | Meaning (grid label) |
|----|----|
| `campaign_code` | Unique human code (**Campaign Code**). |
| `campaign_name` | Title (**Campaign Name**). |
| `campaign_type_id` → `campaign_types.type_name` | Campaign type (**Type**). |
| `description` | Free text. |
| `start_date` | Start (**Start Date**) — **required**, stored as a datetime. |
| `end_date` | End (**End Date**) — optional datetime. |
| `budget` | Planned budget, MYR (**Budget**). |
| `target_audience` | Free text. |
| `status` | Lifecycle (**Status**) — see enum below. |
| `created_by`, `created_at`, `updated_at` | Audit. |

> The grid also shows a **Spent** column, but `spent` is a frontend-only derived figure — it is **not** a stored column on `marketing_campaigns`.

### Date columns
`start_date` (required), `end_date` (optional), `created_at`, `updated_at`.

### Status values (enum `CampaignStatus`)
`PLANNING`, `ACTIVE`, `COMPLETED`, `CANCELLED` (default `PLANNING`). *(Stored uppercase in the backend; see the audit note below — the frontend types use lowercase, so treat status case-insensitively.)*

### Example questions (answer via the Campaigns page / export)
* "List active campaigns." (`status = ACTIVE`)
* "Which campaigns start after <date>?" (`start_date`)
* "Show campaigns of type <type> with a budget over RM50,000."
* "How many campaigns are in PLANNING?"
* "List completed campaigns from last quarter." (`status = COMPLETED`, `end_date` in quarter)
* "Which campaigns have no end date set?"
* "Show cancelled campaigns." (`status = CANCELLED`)

---

## Things to remember

* **Live = flag on AND today in window.** Always read **`is_expired`**; never present an `is_expired=true` row as live. When `fallback_used=true`, there was **no** live match — say so.
* **`date_mode` picks the date:** `overlap` (running during) / `started` (launched in) / `ended` (expired in). `started` / `ended` include historical rows automatically.
* **Promotions have no `name` column** — the title is `description`. There are no UUIDs in answers: use description / product code / filename / campaign code.
* **Product and attachment tools require a narrower** (`promotion_ids` / `product_ids` / `attachment_ids`); the promotions tool auto-caps unfiltered calls to the 10 newest.
* **`access_levels` are names, never IDs** ("Sorento Dealer", "End User", "Mocha Office").
* **Campaigns are not assistant-readable** — redirect to the Campaigns page / export.

## See also

* [Upload a Promotion](upload-promotion.md)
* [Upload a Marketing Form](upload-marketing-form.md)
