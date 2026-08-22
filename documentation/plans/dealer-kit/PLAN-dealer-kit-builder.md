# PLAN — Dealer Kit: page builder, collections, PDF (S1–S3)

**Status:** Pre-code. Not started.
**UAC:** `dealer-kit-builder-acceptance-criteria.md` (companion — every AC below traces to it).
**Decisions:** ADR-0005 (own builder, amended: email becomes a third emitter) · ADR-0007 (a Dealer is a `customers` row) · vocabulary in `documentation/CONTEXT.md`.
**Scope:** S1 builder core · S2 collections + binding · S3 PDF export.
**Deferred out of this plan:** S2.5 Edition revision workflow (blocked — see Dependencies) · S3.5 AI spacing · S4+ dealer surface, Selection, AI design · the email emitter.

---

## 1. What is being built, in one paragraph

A page builder inside Sorento that produces the digital catalogue: a Designer arranges
**Sections** on a 12-column responsive grid, binds a **Collection** of products to a **Tile
Template**, publishes by moving a label to an immutable version, and exports the same document
to PDF through headless Chromium. The document is **viewer-agnostic** — it stores bindings, not
prices — so one published page serves staff, dealers and consumers with the price each is
allowed to see.

## 2. Dependencies and their state

| Dependency | State | Consequence |
|---|---|---|
| `app/rule_engine/` (evaluator, registry, prose) | **Exists** — used by promo-expiry automation | S2 registers a `product` fact source; no new evaluator |
| `attachments` + `storage_router` | **Exists** | Asset library stores rows in `attachments`, semantics in `dealer_kit.asset` |
| `UserDownload` + My Downloads drawer | **Exists** | S3 reuses it; note it has **no params column** (see §6) |
| `CompanyScopedMixin` + `do_orm_execute` filter | **Exists, but ONLY on `feat/promo-expiry-rule-engine` — NOT on `main`** | Branch point is forced: `feat/dealer-kit-builder` is cut from that branch, not main, or AC-A6/A7 are unsatisfiable. Dealer Kit cannot merge before multi-company does |
| `access_levels` / `is_direct_access` on products & attachments | **Exists** | Drives viewer-resolved pricing and badge gating |
| `ai_prompt_versions` / `ai_prompt_labels` | **Exists** | Copied as the shape for `page_version` / `page_label` |
| **Status engine (ADR-0001)** | **BUILT** — ported by project-sales; S2.5 rides it (2026-08-03) | No longer blocks anything here |
| `respond_contacts` ↔ `customers` link | **Does not exist** | Blocks S4, not this plan |

**The one blocker worth stating plainly:** ADR-0001 adopted the status engine as core, but no
`statuses` / `status_transitions` model exists yet. The Edition approval workflow
(draft → pending_approval → approved → done) must ride it rather than adding a seventh
hardcoded status vocabulary — which is the exact mistake ADR-0001 was written to prevent. So
S2.5 waits. Nothing in S1–S3 touches it.

## 3. Schema

All tables in schema `dealer_kit`, mirroring `scm`. FKs into core are **normal cross-schema
FKs**, unqualified (`ForeignKey("products.id")`); FKs within the module are schema-qualified
(`ForeignKey("dealer_kit.page.id")`). All PKs/FKs `UUID(as_uuid=False)` per the uuid-id
principle.

```
page               id · name · slug · print_profile JSONB · company_id · created_by · timestamps
page_version       id · page_id FK · version INT · doc JSONB · commit_message · created_by
                   UNIQUE(page_id, version)
page_label         id · page_id FK · label · version_id FK · updated_by · updated_at
                   UNIQUE(page_id, label)            -- labels: 'published' | 'staging'
tile_template      id · name · doc JSONB · company_id · timestamps
collection         id · scope ('library'|'page') · page_id FK NULL · name NULL
                   conditions_json JSONB · pinned_product_ids[] · excluded_product_ids[]
                   manual_order[] · company_id
asset              id · attachment_id FK -> public.attachments · name · kind · tags[] · company_id
bundle             id · name · price NUMERIC · company_id
bundle_component   id · bundle_id FK · product_id FK -> public.products · quantity · sort_order
```

Core migrations this plan owns (small, additive, nullable):

- `attachment_types.certification_logo_attachment_id` → `attachments` (AC-E2)
- `attachments.valid_until` DATE, **and appended to `Attachment.__audit_columns__`** (AC-E3) —
  without the audit line, expiry edits are silently unaudited

## 4. The document model

`page_version.doc` is the whole design. It stores **no prices and no access decisions** —
AC-G1 makes a price string in a saved doc a defect.

```jsonc
{
  "sections": [
    { "id": "s1", "background": {...}, "padding": {...},
      "blocks": [
        { "id": "b1", "type": "text" | "image" | "artboard" | "collection" | "bundle",
          "props": { "collectionId": "...", "tileTemplateId": "...", "columns": {...} } }
      ] }
  ],
  "layouts": {
    "desktop": { "b1": {"colStart":1,"colSpan":6,"rowStart":1,"rowSpan":2} },
    "tablet":  { ..., "isDerived": true },
    "mobile":  { ..., "isDerived": true }
  }
}
```

**Breakpoints** 12 / 8 / 4 columns at ≥1280 / ≥768 / <768. Smaller layouts are **derived** from
desktop (reading order top-left→bottom-right, full-width stack, spans clamped) and carry
`isDerived: true`. The moment a Designer edits a breakpoint, its flag flips false and desktop
edits stop re-deriving it — with an explicit "re-derive" action to go back (AC-C6–C8).

**Derivation is a pure function** and gets a golden-set test written **before** the
implementation (AC-K2, per the TDD rule for deterministic engines).

**`react-grid-layout` is edit-time only.** The runtime renderer emits plain CSS Grid, guarded
by an import test (AC-C9) — RGL in the public bundle is a regression.

## 5. Slices

### S1 — Builder core

1. `[MIG]` schema + `page`, `page_version`, `page_label`, `tile_template`, `asset` + the two core column adds
2. `[BE]` module catalog row, router guard, six permission slugs, **grant sweep** for existing roles (AC-A5)
3. `[BE]` version/label service — `max(version)+1` **per page_id**, never update in place, label move busts the render cache
4. `[FE]` editor: sections, 12-col grid, drag/resize/collide, three breakpoints, derived layouts
5. `[FE]` asset library + tile template editor
6. `[FE]` **paper mode** — canvas at true paper width with page-break lines; break lines are *never* drawn on the desktop canvas (AC-H6)
7. `[FE]` public renderer — server-rendered, plain CSS Grid

Gate: a Designer builds a static page, publishes it, rolls back, and the public URL follows the
label.

### S2 — Collections, binding, bundles

1. `[BE]` `collection` + `bundle` + `bundle_component`
2. `[BE]` register a **`product` fact source** in `app/rule_engine/registry.py` (category, brand, price band, `is_discontinued`, stock) — reuse `infer_facts` for column-derived facts, explicit `FactDef` for computed ones
3. `[BE]` resolution = **rule ∪ pins − exclusions**, ordered by `manual_order` then a documented fallback — golden-set test first (AC-K3)
4. `[BE]` bundle availability **derived at read time** from components; one discontinued component makes the bundle unavailable (AC-F10) — never a stored flag
5. `[BE]` price allocation: pro-rata by list price, remainder to the largest line, sums exactly (AC-F11) — golden-set test first
6. `[FE]` product picker → silent `scope=page` collection, with "save as reusable collection" promoting it to `library`
7. `[FE]` collection block, multi-image tile template (AC-E9 — composited, never generated)
8. `[BE]` viewer resolution: price and product visibility from `access_levels`; **invoice price = document toggle AND viewer access**, and when it fails, the field is absent from the *response*, not hidden in the DOM (AC-G6/G7)

Gate: one library collection bound to three pages; adding a product updates all three.

### S3 — PDF export

1. `[BE]` print profile on `page` + per-section `printMode` + per-block `hideInPrint` (buttons/CTAs/filters default to true)
2. `[BE]` a print route rendering the same React runtime at paper geometry — **Print Preview and the PDF worker use this same route**, which is the only reason preview break positions can be trusted (AC-H3/H5)
3. `[BE]` RQ task: headless Chromium print-to-PDF → storage router → `UserDownload`
4. `[FE]` Print Preview with live re-flow on page size / orientation change
5. `[DEPLOY]` Chromium + runtime deps in the worker image, documented in `DEPLOY.md`, **verified in a container** — not only on macOS (AC-I8)

Gate: the exported PDF matches the screen at desktop width, and a dealer-audience export and a
staff export of the same page carry different prices.

## 6. Two things that will bite, addressed up front

**Viewer context in the worker.** `UserDownload` has **no params/payload column** — only
`kind`, `source_entity_*`, `status`, `filename`, storage fields. The worker has no request
context, so principal, access levels, active company and page version must be snapshotted at
**enqueue** (AC-I3). Put them on a `dealer_kit.export_request` row referenced by
`source_entity_id`, rather than widening the core table. The worker must never fall back to a
system principal — that is how a consumer ends up holding a PDF of dealer net prices.

**Company scope on every owned table.** `dealer_kit` tables are Owned-bucket. Each registers
with `CompanyScopedMixin` and the CI new-table guard, and the leak test asserts `UNSET` scope →
0 rows (AC-A6/A7). A collection of Sorento products surfacing under Mocha is the failure this
prevents.

## 7. Test strategy

Phase 2 is **test-first** (red → green → refactor), not test-after. Written before their
implementations: breakpoint derivation, collection resolution, bundle price allocation — the
three deterministic engines here.

- **pytest** — Postgres only, no sqlite. Committing tests use a private `zzt_` scratch schema.
  All fixture cleanup **scoped to marker rows**, symmetric before+after — never an unscoped
  `DELETE FROM` against the local prod-copy DB.
- **vitest** — loading / empty / error / data for every new component; hook tests.
- **playwright** — one spec: sidebar → builder → create page → add section → bind collection →
  publish → public render → export PDF → My Downloads, asserting the `/api/v1/*` calls.
- **Browser verification** — reached by **clicking through the sidebar** from `/`, never a deep
  URL, at **375px and 1280px**, against a **prod build** before handoff.

## 8. Order of work

```
S1 ──► S2 ──► S3        (this plan, unblocked)
        │
        └──► S2.5 Edition revision workflow   [waits on the status engine port]
             S3.5 AI spacing Proposals        [after S3]
             email emitter                     [after S3, own ACs]
```
