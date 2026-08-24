# PLAN - Product Sets

> The design that fulfils `product-sets-acceptance-criteria.md`. That file is the contract;
> where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `product-sets` · **Domain:** master-data
**Status:** IMPLEMENTED - all six slices S0 to S5 are built, tested and browser-verified as of
2026-08-24, and migration `414_product_set_grant_sweep` mirrors the `master_data.products.*` grants
onto `master_data.product_sets.*`, which closes DoD item 3 (before it, the four permissions existed
and no role held them, so every non-admin was locked out of a finished feature). The
`PRODUCT_SET_RESOLVE_ENABLED` flag has been removed: S3 now resolves `product_set` unconditionally,
with no runtime switch. That does not remove the coordination obligation with `sorento-crm-n8n-60`,
it changes its nature - it is no longer enforced by code, so it is now a human coordination step
required BEFORE this change merges to `main` and deploys, not a switch flipped afterwards. What
remains outside the code: `sorento-crm-n8n-60` must hold the `product_set` contract in writing and
confirm before this merges, S2 still owes the promotion-payload evidence run its own-PR carve-out
was for, and the seeding backfill has not been applied - and note that the proposal pass offers
materially more than the UAC's sizing, 98 candidates for Sorento alone against 47 families and
roughly 94 rows across both companies, after the discontinued-member and accessory-token fixes;
that is a number to confirm against the catalogue before the backfill runs, not a defect.
Sign-off history: APPROVED - captain sign-off 2026-08-23 via Lavish review, verdict "Approved, start
S0". All five flagged calls confirmed: rename `product_set_service.py` in the same PR; S2 ships as
its own PR; S3 ships inert pending n8n confirmation; `linked_via_set_id` added; "Product Set" is the
term and goes into `documentation/CONTEXT.md`.

## Shape

A **Product Set** is a code that names an assembly Sorento sells as one thing and stocks as
several. It is not a product, is never stocked or costed, and is never ordered. It exists so
that a code printed on a flyer is answerable.

Two tables and one derived number. Everything else is plumbing that connects them to surfaces
that already exist.

## 1. Data

```
product_sets                       CompanyScopedMixin
  id                UUID pk
  set_code          VARCHAR(100)   NOT NULL
  name              VARCHAR(255)   NOT NULL
  list_price_override NUMERIC(15,2) NULL     -- wins when set; null means computed
  override_set_by   UUID           NULL      -- who, so the badge can name them
  override_set_at   TIMESTAMP      NULL
  is_active         BOOLEAN        NOT NULL DEFAULT true
  created_at / updated_at / created_by
  UNIQUE (company_id, set_code)

product_set_members
  id                UUID pk
  product_set_id    UUID  FK product_sets ON DELETE CASCADE   NOT NULL
  product_id        UUID  FK products     ON DELETE RESTRICT  NOT NULL
  quantity          NUMERIC(15,4) NOT NULL DEFAULT 1
  contributes_to_price BOOLEAN   NOT NULL DEFAULT false
  sort_order        INTEGER       NOT NULL DEFAULT 0
  created_at / updated_at
  UNIQUE (product_set_id, product_id)
```

Notes that are decisions, not detail:

- **No role column** (UAC D4). It was proposed and dropped because nothing depended on it.
- `RESTRICT` on `product_id` so a set can never hold a dangling member; `CASCADE` on the set
  so deleting a set never orphans rows.
- `quantity` is `NUMERIC`, never `Integer`. The repo has a standing lesson about integer
  quantity columns truncating fractional values.
- Uniqueness is `(company_id, set_code)`. Global uniqueness would make SRT and MOCHA fight over
  identical codes, which they legitimately both carry.
- `product_sets` is company-scoped; `product_set_members` reaches its scope through its parent,
  the same way `certificate_products` reaches scope through `Certificate`.

**Migration.** One `op.create_table` per table, explicitly. New tables are absent on databases
built by `create_all`, so autogenerate-only is not enough. Chain `down_revision` onto the
committed head and re-run `alembic heads` immediately before merging; a second head kills the
CI stamp step before any test runs.

## 2. Price

```python
def resolve_set_price(product_set) -> SetPrice:
    computed = sum(m.product.list_price * m.quantity
                   for m in product_set.members if m.contributes_to_price)
    ...
```

Computed at read time, never stored, so it follows a member's price without a backfill. The
override is a separate field and both travel in the response, because the FE shows the override
badge next to the figure it replaced.

No member ticked means the price is **absent**, not zero. The repo already learned this on
dealer-kit pricing: a list price of zero is missing data, not a free product.

`SetPrice` is a small dataclass, not a dict, so `response_model` cannot silently drop a field.
Every field gets an explicit assertion in the tests regardless (AC-D.6).

## 3. Stock and the complete-sets figure

Stock lives in `stock`, one row per product per warehouse, with `quantity_available` a
generated column (`quantity_on_hand - quantity_reserved`).

```
member_available  = SUM(stock.quantity_available) for that product across warehouses
complete_sets     = MIN over members of FLOOR(member_available / quantity)
limiting_member   = the member that produced the MIN
```

Per-member figures are the primary answer and `complete_sets` rides alongside with the limiting
member named. A bare zero while forty pedestals sit in a warehouse reads as a bug to whoever
asked, which is the failure mode this whole feature exists to remove.

A discontinued member does not remove itself from the set. It is flagged, it contributes 0, and
the reason names it.

## 4. Resolver

A set resolves to **one** entity, never a fan-out:

```json
{
  "entity_type": "product_set",
  "canonical_code": "SRTWC8608-RL",
  "uuid": "...",
  "match_field": "set_code",
  "display": {
    "name": "...",
    "complete_sets": 0,
    "limiting_member": "SRTWC8608-SC",
    "members": [
      {"product_code": "SRTWCX8608-RL", "description": "...", "quantity": 1, "available": 40},
      {"product_code": "SRTWCY8608",    "description": "...", "quantity": 1, "available": 12},
      {"product_code": "SRTWC8608-SC",  "description": "...", "quantity": 1, "available": 0}
    ]
  }
}
```

Wiring:

- `_probe_product_set` registered in `_TIER1_PROBES` producing `frozenset({"product_set"})`,
  exact match on `set_code`, whitespace and dash insensitive on both sides via the existing
  `_strip_all_ws` / `_ws_insensitive_lower` helpers, so `srtwc 8608-rl` resolves.
- `_ENTITY_TYPE_ALIASES` gains `product_set`, `product_sets`, `set`, `kit` as identity or alias
  entries, so a caller naming any of them scopes to the set probe.
- **ORM only.** The set leg goes through the ORM so the `do_orm_execute` listener injects
  company isolation. A raw `text()` query bypasses the listener entirely, which is how a
  cross-company leak gets shipped looking like a performance optimisation.
- **No price in the response** (UAC D7). A stock question gets stock. The price path answers
  price questions and does not fan out.

**Ambiguity.** A set code and a product code should never collide, since a set code exists
precisely because no product carries it. If both probes hit the same token, that is a data
defect: report it as ambiguous rather than silently preferring one. The multi-row guard already
does this for products; the set probe joins the same mechanism.

**Contract.** `entity_type: "product_set"` is a new value on the frozen `/references/resolve`
contract, and it resolves unconditionally - there is no runtime flag gating it. A set code
resolves to nothing today because no product carries it, so removing the gate cannot break a
lookup that currently works; it only turns a failure into an answer. The one real exposure is a
token that matches both a real product and a set, which now returns an extra entry in
`matches[]` - the product itself stays `confident_match` (`_TIER1_PROBES` runs `_probe_product`
before `_probe_product_set`), so a caller reading `matches[0]` is unaffected and only a caller
iterating the array sees one more entry. `sorento-crm-n8n-60` must have the contract in writing
and confirm BEFORE this merges to `main` and deploys - that obligation is no longer enforced by
code, so it is now purely a human coordination step ahead of the merge, not a switch someone
flips afterwards. From the moment this merges, `entity_type: "product_set"` can appear on any
`/references/resolve` response with no switch; n8n's renderer needs to tolerate an unknown
entity type gracefully if it is not ready for it. See
`documentation/plans/master-data/n8n-contract-product-set-entity.md` for the surface-by-surface
detail.

## 5. The shared code-resolution helper

Today two external paths resolve a product code differently:

- `product_attachments._resolve_product_codes` treats the code as a **substring** and returns
  every match, deliberately: "a code is a SUBSTRING, not a key".
- `promotions._resolve_product_codes` does **exact** match with a `+`-split fallback.

So a flyer code can link an attachment and fail to create a promotion, today, with no set
involved. One helper replaces both:

```
resolve_codes_to_products(db, codes) -> (matched, unmatched)
  1. exact product code
  2. product set code -> its members
  3. substring product code
```

Set expansion sits between exact and substring so a set code cannot be shadowed by an
accidental substring hit.

**This is a behaviour change to promotions** for codes that have nothing to do with sets, since
they gain substring matching. It is a live defect being fixed, but it ships as its own PR with
its own evidence run rather than hiding inside a set feature.

**Decided: the substring tier also applies to packing list create, on the user's explicit
call.** Packing list create never had substring matching before this change; it went through
its own exact-match-only lookup. Routing it through the same shared helper means it now gains
tier 3 (substring) along with tier 2 (set expansion). The user was asked whether packing list
should get a carve-out that keeps it on exact-plus-set-expansion only, without the substring
tier the other two surfaces already carried. They chose to keep the helper's behaviour
identical across every surface: one helper, one behaviour, which is what UAC decision D11
asked for. The trade-off they accepted, stated plainly: on a product attachment or a
promotion, a wrong substring match is a bad link. On a packing list it creates a receiving
line, so it inflates on-hand stock for the wrong SKU. A partial code such as `WC7601` matches
5 real sibling SKUs in the live catalogue and now creates a receiving line for each, every one
carrying the full submitted quantity. This was flagged as risky rather than built silently, and
the user ruled on it: consistency across surfaces over a packing-list-specific carve-out. See
`documentation/plans/master-data/n8n-contract-product-set-entity.md` Surface 5 for how this
reaches n8n.

**Provenance.** `product_attachments` gains `linked_via_set_id UUID NULL`, and the promotion
link table gains the same. Without it, nothing can answer "why is this flyer on a seat cover"
and nothing can clean up when membership changes. Null means a human or an exact code made the
link.

## 6. Surfaces

**Master Data Management > Product Sets.** DataGrid listing with fixed layout, resizable
columns, explicit sizes and truncation with `title`. Detail page at `/{module}/{id}` rendering
every section: header (code, name, company, status, price with override badge), members, linked
attachments, linked promotions. View and edit share one layout. Prev/next record navigation.
Usable at 375px and 1280px. Every destructive or detach action confirms first.

**Product detail** gains a **Sets** section listing every set the product belongs to, each a
link addressed by set code. `SRTWCY8608` belongs to two, so it is a list, never a single field.
Products in no set get an explicit empty state, not a hidden section.

**Not** in the products DataGrid, and **no** new MCP tool. Sets are not products, and mixing
them invites downstream code to treat a set id as a product id.

**Permissions.** `master_data.product_sets.view` / `.edit` / `.delete` registered in
`PERMISSION_REGISTRY`, a `menu.config.tsx` entry gated on view, and a grant sweep for
provisioned roles as part of the DoD gate.

## 7. Seeding

Roughly 47 families across two companies. The proposal pass groups the catalogue by
role-infix families and proposes one set per trap variant, writing nothing. Review reuses the
flyer-spec proposal shape already in the repo: stored batches, grouped review, tick to apply.

Nothing runs unattended. The role labels in this very design came out inverted at the start,
and a regex that writes without review would have propagated that across 94 rows.

## 8. Slices

| id | slice | notes |
| --- | --- | --- |
| S0 | Tables, migration, company scope, computed price with override | Backend only. No surface yet. |
| S1 | Master-data CRUD, list and detail | Phase 1 mock first, then wired. |
| S2 | Shared code-resolution helper, replacing both divergent ones, plus `linked_via_set_id` | **Own PR.** Changes promotion behaviour independently of sets. |
| S3 | Resolver `product_set` entity and the stock answer | **Coordinated release with n8n.** Resolves unconditionally, no runtime flag - the contract must be confirmed in writing BEFORE merge, not switched on after. |
| S4 | Sets section on product detail | |
| S5 | Proposal-and-review seeding over the 47 families | |

S0 and S1 are independent of S2. S3 depends on S0. S4 depends on S0. S5 depends on S1.

## 9. Testing seams

Agreed before Phase 2 starts, so the tests have somewhere to attach:

- `resolve_set_price(product_set)` - pure over loaded members, no session. Table-driven.
- `derive_complete_sets(members, stock_by_product)` - pure. Every quantity and discontinued
  case is a row in a table, not a fixture.
- `resolve_codes_to_products(db, codes)` - one function, both external callers, so one test
  file proves both paths agree.
- `_probe_product_set(db, tokens)` - the probe alone, including the two-company cross-bleed
  case per leg, the way the certificate leg is already tested.

Backend tests run on **Postgres only**, via `tests/_pg_fixture.py`. CI's database has no data,
so every test seeds its own chain and never reads an existing row.

## 10. Risks

- **The n8n contract is the long pole.** S3 cannot land unilaterally. Everything except S3 is
  useful without it: authoring, linking and the product-detail surface all ship first.
- **The promotions behaviour change (S2)** touches a live path that has nothing to do with
  sets. It needs its own evidence run and its own PR so a rollback is surgical.
- **Two writers on `product_attachments`.** The certificate service is already the only writer
  for cert-bearing attachments (COV-1). The set fan-out must respect that carve-out rather than
  writing alongside it.
- **Seeding correctness.** 47 families is small enough to review by hand and large enough that
  nobody will. The review screen has to make discarding as cheap as accepting.

## 11. Deliberately not doing

- Ordering, quoting or exploding a set onto an order line.
- Touching `item_packages`. It stays the read-only AutoCount mirror it is, and Project Sales
  keeps it as the authority for PO set explosion (its D10).
- `FT` membership. The model permits it; no set ships with one.
- A second glossary term. `Product Set` goes into `documentation/CONTEXT.md` alongside Bundle,
  with the distinction stated: a Bundle has no code and *is* an authored price, a set is a code
  first and its price is derived.

## 12. Housekeeping in the same PR

`app/services/product_set_service.py` currently holds the spec backward-search predicate
filter, which is not a product set in this sense. It is renamed to free the name, and the two
call sites plus the plan docs that reference it are updated.
