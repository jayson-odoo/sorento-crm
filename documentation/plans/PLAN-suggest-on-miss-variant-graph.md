# Suggest-on-Miss - CRM backend + variant graph (resolver / MCP side)

**Status:** BUILT + verified (2026-07-04). All waves landed; migration `260_variant_graph_trgm`
applied, 11k backfilled (2093 variants). Reviewer + tester passed; 2 should-fix + 1 latent bug
fixed. UAC: AC-D1/D2, AC-N1 - N4, AC-R1/R2, AC-V1 - V5, M4, M5 all PASS (AC-V5 browser-verified via
Playwright). MCP passthrough verified end-to-end (raw + render). n8n render/UX half (counterpart
plan) still to build. NOT yet committed.
**Owner:** CRM backend + FE.
**Counterpart:** n8n render/UX side lives in `sorento_crm_n8n/n8n-workflows-init/plans/suggest-on-miss-plan.md`.
This doc is the **CRM half** that plan's §7 assigns to us, plus a new **persisted variant
graph** the n8n plan does not cover. One feature, dependency-ordered.

**Goal:** kill dead-end "no data / not found" replies at the source:
1. **Resolve better** - dash/whitespace-insensitive exact matching (`srtkt71-ss` ≡ `SRTKT71SS`).
2. **Suggest better** - on a miss, return real neighbours. Prefer curated **variants**
   (stored FK graph); fall back to **trigram** neighbours. Rank variants above
   digit-neighbours.
3. **Domain-honest get-results** - a neighbour is only suggested if it **actually has data
   in the asked domain** (stock / eta / cert / delivery). If the nearest data-bearing
   neighbour is **too far**, return **none** → n8n says "no similar products with stock".
4. **Visualize + backfill** the variant graph so staff see which product is a variant of which.

---

## 0. Why the grill changed the original plan

Findings that reshaped `suggest-on-miss-plan.md` §3/§4 (verified against the live DB, 11,413 product codes):

- **DO dash-normalization claim was false.** `_probe_customer_order` uses `_strip_all_ws`
  (whitespace only). `2026-06-3640` ≢ `202606-3640` today. The §3a dash-strip fixes it (M1[37886]).
- **pg_trgm was not installed** (only `vector`+`plpgsql`); the trigram tier (`_trgm_lookup`,
  entity_resolver.py:2266, wired at :3572) **silently returned `[]`** via `try/except`. So every
  "did you mean" (M2) dead-ended. **Extension now installed** (manually, superuser). **GIN indexes
  still missing** → seq scan until the migration lands.
- **First-dash stem split is garbage** for this catalog - first dash is often a category/brand
  prefix: `ACC`(140 products), `IDCI`(76), `OX`(39), `M`(23). Rejected.
- **Raw `similarity()` does not rank variants above digit-neighbours** - Jaccard dilutes longer
  codes, so `SRTWT8517-NEW` can rank *below* `SRTWT8518`. Fixed by an `is_variant` prefix-boost as
  the primary sort key.
- **The `%` operator gate (GUC 0.3) shadows the code's `TRGM_THRESHOLD=0.25`** - the 0.25 is dead
  until we `SET LOCAL pg_trgm.similarity_threshold = 0.25`.
- **`WC 8609`→`MWCY8609` = 0.23 trigram** - below any sane floor. Accepted out-of-reach → escalate.

---

## 1. The variant graph (new)

### 1.1 Model
Add a self-referential FK to `products`:

```python
variant_of_id = Column(
    UUID(as_uuid=False),
    ForeignKey("products.id", ondelete="SET NULL"),   # deleting a parent NEVER blocks
    nullable=True,
)
variant_of = relationship("Product", remote_side=[id], backref="variants")
```

Precedent: `ProductCategory.parent_category_id`, `UnitOfMeasure.base_uom_id` (same self-FK + `remote_side` pattern).

- `is_variant` (the FE field) = `variant_of_id IS NOT NULL`. Not stored - derived in the serializer.
- **A base** = product with `variant_of_id IS NULL`. **A variant** = points at its parent product.

### 1.2 Derivation - longest EXISTING boundary-prefix
On write, a product's parent is:

> the **longest existing product** `P'` such that `my_code` starts with `P'.code`, `P'` is
> strictly shorter, and the character right after the prefix is a **`-` or a letter** (never a
> continued digit). Longest wins (most specific parent).

Boundary-char rule is what separates variants from digit-neighbours:

| my code | candidate parent | next char | verdict |
|---|---|---|---|
| `SRTKT71SS-BL` | `SRTKT71SS` | `-` | ✅ variant |
| `M-FH08SS` | `M-FH08` | `S` (letter) | ✅ variant |
| `SRTWC8517-200` | `SRTWC8517` | `-` | ✅ variant (size) |
| `SRTWT8517` | `SRTWT85` | `1` (digit) | ❌ different product |
| `ACC-4001` | `ACC` (not a product) | - | ❌ no parent → **is a base** |

**Existence-anchoring** (parent must be a real row) is why there is no vocab to maintain and why
`ACC`/`OX`/`IDCI` never form 140-member garbage families - those prefixes aren't products.

Prefix comparison is done on the **dash/ws-normalized** form (so `srtkt71-ss` matches
`SRTKT71SS`); the boundary char is read from the **original** child code (so a stripped dash
doesn't erase the boundary signal).

### 1.3 `reconcile_variant_links` - one idempotent function, three triggers
Set-to-correct-value (idempotent JOIN pattern), never update-where-null:

- **create / edit** a product → derive *my* parent **and** adopt any existing orphans whose
  longest-existing-boundary-prefix is now me.
- **delete** a product → DB `ondelete=SET NULL` nulls children (never blocks); then re-derive those
  ex-children so they re-anchor to the **next** existing ancestor (or stay NULL if none). Without
  this, deleting a mid-tier code silently orphans a whole sub-tree.

`reconcile_variant_links(code_or_id)` is called from `product_service.create_product` /
`update_product` / delete, and by the backfill.

### 1.4 Backfill (11,413 existing products)
`scripts/backfill_variant_links.py` - idempotent, re-runnable, corrects prior wrong values (not
"where NULL"). Sort codes by length ascending, derive each against the full existing set, or run
one self-join SQL pass. Log a summary: #variants linked, #bases, #largest families. Re-run safe.

### 1.5 Visualization (FE, keep it straightforward)
Product detail (`master-data-management/products/[id]/components/ProductDetail.tsx`) - one new
**"Variants" section**, no fancy tree:

- **When this product is a variant** → a **"Variant of"** row: badge + link to the parent
  (human-readable code, resolves to `/master-data-management/products/{parentId}`). Never show the UUID.
- **When this product is a base (or mid-tier)** → a **"Variants (N)"** list: each child code as a
  chip/row linking to its detail page, with its distinguishing suffix highlighted and a compact
  data hint (e.g. on-hand qty) where cheap.
- **Empty state** (base with no variants, per ADR): "No variants of this product." + no CTA needed.
- **List page**: an `is_variant` badge column (or a "Base / Variant" pill) so families are scannable.

Contract: `GET /api/v1/master-data/products/{id}` gains `variant_of` (`{id, product_code}` or null)
and `variants` (`[{id, product_code, ...}]`). Add both to the manual `ProductResponse` dict
builders (do NOT rely on schema inheritance - same trap as `get_user` dropping fields).

---

## 2. §3a - dash/whitespace exact normalization

Extend the two shared normalizers to strip `[-\s]+` (was `\s+`), symmetric python + SQL:

- `_strip_all_ws` (entity_resolver.py:640) → `re.sub(r"[-\s]+", "", value)`.
- `_ws_insensitive_lower` (entity_resolver.py:647) → `lower(regexp_replace(col, '[-\s]+', '', 'g'))`.

Applies to **every code field** (product, order/DO, customer, transporter, shipment, supplier) - 
one change, all types. Only `[-\s]`; `/ . _` stay significant (no transcript evidence, unknown risk).

**Collision rule (free).** Two real codes that flatten to the same normalized value (`SRTKT71SS` +
`SRTKT71-SS`) both land in `per_token[tok]` from the exact probe → the existing multi-row guard
(entity_resolver.py:3143) flags **ambiguous** → "did you mean X, Y?". Never silently returns the
wrong SKU. R2 codes (`cwc7601-rl`, `cwc7606-sh`) each still flatten to exactly one distinct code →
stay exact.

---

## 3. Resolver + get-results neighbour logic

### 3.1 Two miss types, one concept
- **Resolution miss (§3)** - token matched no product. → **trigram** neighbours as `matches[]`
  ("did you mean"). No has-data gate (nothing resolved to have data). Be generous.
- **Data miss (§4)** - token resolved to a real product, but the asked domain has **0 rows**. →
  **variant graph first**, then trigram top-up, then **has-data gate**, then **distance floor**.

### 3.2 Trigram ranking - `is_variant` prefix-boost
`_trgm_lookup` product probe rewritten; run with `SET LOCAL pg_trgm.similarity_threshold = 0.25`:

```sql
SELECT id, product_code, product_name,
       similarity(product_code, :p) AS sim,
       (lower(regexp_replace(product_code,'[-\s]','','g'))
          LIKE lower(regexp_replace(:p,'[-\s]','','g')) || '%') AS is_variant
FROM products
WHERE product_code % :p
  AND lower(regexp_replace(product_code,'[-\s]','','g'))
      <> lower(regexp_replace(:p,'[-\s]','','g'))      -- exclude self
ORDER BY is_variant DESC, sim DESC, product_code
LIMIT :n
```

`is_variant` = candidate (normalized) starts with input (normalized). Booleans sort true-first under
`DESC`, so **variants beat digit-neighbours even when raw similarity ties** (proven: `SRTKT71`
→ `SRTKT71SS`,`-BL/GM/GY` above `SRTKT72SS/73SS` despite the 0.500 tie).

### 3.3 Data-miss algorithm (get-results empty path, per domain)
```
input product P resolved, domain query returned 0 rows:
  candidates =  P.variants (stored graph children)            # curated, is_variant=true
             ∪  siblings sharing P.variant_of_id               # curated, is_variant=true
             ∪  trgm_neighbours(P.code)                        # recall, is_variant per §3.2
  rank: is_variant DESC, sim DESC
  candidates = [c for c in candidates if domain_has_data(c)]   # HAS-DATA GATE (per-domain)
  candidates = [c for c in candidates if sim(c, P.code) >= SUGGEST_FLOOR]   # DISTANCE FLOOR
  alternatives = candidates[:N]                                # cap (N=3)
  relaxed_axis = "entity"
  # alternatives == []  ->  n8n: "no similar products with stock"
```

- **Has-data gate is mandatory and per-domain** - enforced inside each tool (only the stock tool
  knows stock, only incoming knows eta). If `8517` has no stock **and** `8518` has no stock, `8518`
  is **not** returned; keep walking neighbours until one has stock.
- **Distance floor** (`SUGGEST_FLOOR`, e.g. 0.40 - higher than the 0.25 recall floor): if the
  nearest **data-bearing** neighbour is below it, return **none**. Suggesting a barely-related
  in-stock product is a business error; "no similar with stock" is the honest answer.
- Order matters: **has-data filter BEFORE cap** so in-stock variants keep their variant-first rank
  and out-of-stock ones don't consume the top-N slots.

### 3.4 Date axis (§4 M4 - in scope)
Entity axis = above. **Date axis** = separate nearest-row query in the order/delivery empty path
(no trigram):

```sql
SELECT actual_delivery_date, order_number
FROM orders
WHERE <debtor = resolved customer> AND deleted_at IS NULL AND actual_delivery_date IS NOT NULL
ORDER BY abs(actual_delivery_date - :asked_date) ASC     -- nearest either side
LIMIT :k
```
→ `alternatives[]` with `relaxed_axis:"date"`, each carrying the date value. Window = nearest ±,
capped `k`; document the constant.

### 3.5 Per-domain relaxation map
| Domain | Axis | Neighbour source | Has-data test |
|---|---|---|---|
| stock / eta (inventory, incoming) | entity | variant graph → trgm | on-hand>0 / has eta row |
| order / delivery | date → other open DOs | nearest-date | DO exists on/near date |
| promotion | entity → date/active | variant graph → trgm | active promo in window |
| product_attachment / cert | entity → type | variant graph → trgm | has attachment of type |
| master_products (price/dimension) | entity | variant graph → trgm | field present |

---

## 4. MCP passthrough (2 strings)

Backend emits `alternatives[]` + `relaxed_axis` at the top level of the tool response on the empty
path. MCP presenters rebuild responses into a strict envelope, but already support a whitelist - 
add the two keys to `_PASSTHROUGH_KEYS` (presenters.py:86):

```python
_PASSTHROUGH_KEYS = ("suggested_escalation", "escalate_team", "escalated_agent",
                     "fallback_used", "alternatives", "relaxed_axis")
```

Survives both the render envelope and the non-render `{**data}` path. **§5 escalation is already
built** - `escalation_hint.attach_suggested_escalation` injects `suggested_escalation` into empty
responses at the MCP layer (server.py:1498). Compose: an empty response carries escalation +
alternatives; n8n renders one combined quick-reply message.

---

## 5. Prerequisites / infra

1. `CREATE EXTENSION pg_trgm` - **done** (superuser, manual).
2. **GIN trigram indexes** (migration; plain `CREATE INDEX` - 11k rows, trivial lock, fully
   transactional in Alembic; `CONCURRENTLY` not needed at this size):
   ```sql
   CREATE INDEX IF NOT EXISTS idx_products_code_trgm ON products USING gin (product_code gin_trgm_ops);
   CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (product_name gin_trgm_ops);
   -- + orders.debtor_name / debtor_code for the customer trgm probe
   ```
3. `SET LOCAL pg_trgm.similarity_threshold = 0.25` in the trgm query (make the 0.25 floor real).
4. Constants documented: `TRGM_THRESHOLD` (recall, 0.25), `SUGGEST_FLOOR` (substitution, ~0.40),
   `N` (cap, 3), date window `k`.

---

## 6. Build order (one feature, dependency-ordered)

1. Schema: `variant_of_id` self-FK + GIN trgm indexes (one migration).
2. `reconcile_variant_links` + wire into create/edit/delete + **backfill 11k**.
3. §3a dash-strip in the two normalizers.
4. Rewrite `_trgm_lookup` product probe (is_variant rank + `SET LOCAL` 0.25).
5. Data-miss neighbour logic (graph → trgm → has-data gate → distance floor) per domain endpoint;
   date-axis nearest-date. Emit `alternatives[]` + `relaxed_axis`.
6. MCP `_PASSTHROUGH_KEYS` += 2.
7. FE: `variant_of`/`variants` in ProductResponse; Variants section + list badge.
8. n8n render/UX - counterpart plan (already grilled).

Three-phase loop per CLAUDE.md within each FE-touching slice (§1.5, FE prototype → BE+tests → review).

---

## 7. UAC - acceptance, mapped to the original plan's test cases

Source rows = `suggest-on-miss-plan.md` §9 (`chat_histories`, exported 2026-07-04). Each line is a
pass/fail gate. Verify: **pytest** (resolver/endpoint), **vitest** (FE variant section),
**playwright** (product detail + a chat round-trip where feasible), **golden-master replay** (R5).

### 7.1 Resolve better - dash elimination (§3a) → M1
| id | input | must resolve to | test |
|---|---|---|---|
| 37925/37930 | `srtkt71-ss` | exact `SRTKT71SS`, normal stock answer | pytest: `resolve` returns single exact, `match_tier=exact` |
| 37886 | `d/o 2026-06-3640` | exact `202606-3640`, DO status | pytest: order probe exact after dash-strip |
| 38117/38165 | `SRTWT7438GM` | exact `SRTWT7438-GM` | pytest: product probe exact |
- **AC-D1** dash/ws variants of a real code resolve **exact** (not fuzzy, not ambiguous).
- **AC-D2** two real codes colliding under dash-strip → **ambiguous** with both in `matches[]`
  (never silent wrong SKU).

### 7.2 Suggest better - variants first, then neighbour (§1+§3) → M2, M3
| id | input | expected | test |
|---|---|---|---|
| 38031 | `cwc605-rl` (miss) | did-you-mean `CWCX605-RL` (trgm) | pytest: `matches[]` non-empty, tier=trgm |
| 38506 | `WC 8609` | **no candidate** (0.23 < floor) → escalate only | pytest: `matches==[]`; accepted limit |
| 38157/38163 | `Srtwc8517-250` | did-you-mean `SRTWC8517-SH-UF-200` | pytest: variant/neighbour surfaced |
| 38239 | `srtwt2206` no stock | **variants with stock** first; else neighbour with stock; else none | pytest: graph children queried before trgm |
| 38533 | `SRTJC3305` no stock | sibling-with-stock or none | pytest |
| 38105/38278 | `SRTBF11705` no eta | variant `SRTBF11705-NEW` (has data) | pytest: graph child preferred |
- **AC-N1** resolution miss returns trgm neighbours ranked **is_variant DESC, sim DESC** (variants
  above digit-neighbours).
- **AC-N2** data miss prefers **stored variants** (graph) over trigram digit-neighbours.
- **AC-N3** (**the 8518 rule**) if `8517` has no stock **and** `8518` has no stock → `8518` is
  **not** returned. The next neighbour **with stock** is found instead.
- **AC-N4** (**too-far rule**) if no data-bearing neighbour clears `SUGGEST_FLOOR` → `alternatives==[]`
  → n8n says "no similar products with stock". No barely-related in-stock product is suggested.

### 7.3 Date + attachment axes → M4, M5
| id | input | expected | test |
|---|---|---|---|
| 38519/38521/38103/38167 | delivery today, none | nearest date w/ DO + escalate CS | pytest: date-axis alternatives, `relaxed_axis=date` |
| 38183 | `SRTWT2207` image, none | sibling `SRTWT2207-NL` w/ image | pytest: attachment has-data gate |
| 38513/38517 | cert, none | sibling product w/ cert or none + escalate | pytest |
| 38487 | escalate + add sibling-with-cert | escalation kept, sibling added same message | pytest + n8n |

### 7.4 Must-NOT-regress (§9.2/§9.3) → R1 - R5
- **AC-R1 has-data ⇒ identical.** Any query with ≥1 row today → byte-identical reply; the
  alternatives/neighbour path is entered **only** on empty results.
- **AC-R2 exact stays exact.** `srtwb1610`, `cwc7601-rl`, `srtmcb6083`, `SRTSS8750`, `cwc7606-sh`
  still resolve to the **same single** code after dash-strip (collision guard).
- **AC-R3 non-business untouched.** `Hai`, sports, "thankyou" → casual, no suggestion/escalation.
- **AC-R4 escalation preserved.** Cert/attachment misses that escalate today still escalate
  (now possibly + siblings; escalation never removed).
- **AC-R5 golden-master replay.** Replay all 2,216 `n8n_test` turns: non-miss turns diff-clean;
  only miss turns diff, each reviewed (alternatives come live → re-capture, not pinned).

### 7.5 Variant graph correctness (new)
- **AC-V1** backfill idempotent - re-run produces zero changes on the second pass; corrects a
  deliberately-wrong seed (not "where NULL").
- **AC-V2** boundary rule - `SRTKT71SS-BL`→parent `SRTKT71SS`; `M-FH08SS`→`M-FH08`;
  `SRTWC8517-200`→`SRTWC8517`; `SRTWT8517` **not** a variant of `SRTWT85`; `ACC-4001` is a **base**.
- **AC-V3** delete never blocks - deleting a parent SET-NULLs children (no FK error); re-derive
  re-anchors them to the next existing ancestor (or NULL if none).
- **AC-V4** parent-added-later - create a child before its base exists (child = base), then create
  the base → child re-links to it (adopt-orphans path).
- **AC-V5** visualization - variant product shows "Variant of {code}" link; base shows
  "Variants (N)" list; empty base shows the empty state; **no UUIDs** rendered. (vitest + playwright)

### 7.6 Out of scope (do not claim) - §9.4
Cross-domain multi-intent (38097/38406), material lookups (38176), price-history (38148/38165),
DO-by-PO (38262/38476), lost-context multi-turn (`1`/`5`/`DO`). Unchanged by this plan.

---

## 8. Open / to confirm during build
- `SUGGEST_FLOOR` exact value (start 0.40, tune on replay).
- Date window `k` and ± span.
- Whether siblings-sharing-parent (not just direct children) are in the §3.3 candidate union for
  every domain, or children-only for some (start: children + same-parent siblings).
- GIN index list finalised against every column `_trgm_lookup` probes.
