# Contract change: Product Sets, everything n8n touches

**For:** `sorento-crm-n8n-60`
**From:** the CRM side, branch `feat/product-sets`, HEAD `59dc69314`
**Status:** DRAFT, awaiting n8n confirmation.

**Nothing in this document is deployed yet.** The whole Product Sets feature, including the
parts marked "live" below, is still on the unmerged branch `feat/product-sets`. Nothing on this
branch exists on `main` or in production today. "Live" in this document means "ships
unconditionally, no feature flag, the moment this branch merges and deploys" - not "already
running." Only one piece is additionally gated behind a flag once deployed: the `product_set`
entity type on `/references/resolve` (section 1).

**UPDATE, same branch, later in this pass:** two findings below are now fixed, not open. Surface
1 finding 1 ("`product` does not auto-expand to include `product_set`") and Surface 5 ("packing
list create is UNTOUCHED") are both superseded - see
`documentation/plans/master-data/product-set-n8n-evidence.md` for the real curl evidence. The
surface sections below are left as-written (they are still an accurate account of what this
pass found and why), with a pointer added at each fixed spot.

## Why this feature exists

A two-piece water closet is sold as one thing and stocked as three. The flyer prints
`SRTWC8608-RL`. The catalogue holds only the parts:

```
SRTWCX8608-RL   SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)   1180.00
SRTWCY8608      SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)        0.00
SRTWC8608-SC    SORENTO SRTWC8608-SC SEAT COVER ONLY               85.00
```

No product carries `SRTWC8608-RL`. Before this feature, an exact-match code lookup told a
customer asking `check stock SRTWC8608-RL` that the product does not exist. Measured on the
live catalogue: 47 two-piece families, 23 with no bare code at all, across roughly 338
role-bearing SKUs. A **Product Set** row now names the assembly and its members; it is never
stocked, costed or ordered on its own.

As of today only 2 test sets exist in the database (`SRTWC8608-RL` and one duplicate-name
fixture, `SRTWC8608-RL-WEPLS`). The proposal-and-review seeding pass that would populate the
other ~46 families has not run yet - see the pre-launch checklist.

---

## Surface 1: `/references/resolve`, the `product_set` entity type

**Status: GATED.** Behind `PRODUCT_SET_RESOLVE_ENABLED`, an env var, default off. Confirmed off
in the running dev backend (unset in `.env`). Route: `POST /api/v1/system/references/resolve`
(also a `GET` variant), guarded per-request by `get_external_api_user` (X-API-Key or Bearer).

### With the flag off (today, and what a caller has always seen)

Curled directly against the running backend:

```
curl -s -X POST http://localhost:8050/api/v1/system/references/resolve \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"query": "SRTWC8608-RL"}'
```

```json
{
  "tokens": ["SRTWC8608-RL"],
  "elapsed_ms": 1088.5,
  "resolutions": [
    {
      "token": "SRTWC8608-RL",
      "resolved": true,
      "ambiguous": false,
      "matches": [
        {
          "entity_type": "attachment",
          "canonical_code": "SRTWC8608-RL_TD.jpg",
          "uuid": "1fee0d26-b2e4-40c3-9b5e-f2e5575fdc78",
          "match_field": "original_filename",
          "match_tier": "prefix",
          "display": {
            "filename": "SRTWC8608-RL_TD.jpg",
            "attachment_type": "Technical Specifications",
            "directory": "Marketing --> Sorento Technical Drawing --> Close Coupled Water Closet"
          }
        }
      ],
      "alternatives": []
    }
  ],
  "unresolved_tokens": []
}
```

No product, no set: only a technical-drawing attachment whose filename happens to start with
the code. This is the failure mode the feature fixes - not "nothing found" but "a customer
gets an unrelated PDF instead of a stock answer."

The `_probe_product_set` function is registered and runs on every call (it is not removed by
the flag), but returns nothing while `PRODUCT_SET_RESOLVE_ENABLED` is unset, so this response
is byte-identical to what n8n has always received. Nothing else about the endpoint's shape,
tiers or aliases changes with the flag off.

### With the flag on (traced through the code, not curled - restarting this dev backend to flip
the env var was out of scope for this pass; the trace below is checked line-for-line against
`app/services/entity_resolver.py` and the same DB row above)

The same call would add a `product_set` match to the SAME token's `matches` array, alongside
whatever already matched. Read from the live DB row for `SRTWC8608-RL` (3 members, all in
stock, none discontinued):

```json
{
  "token": "SRTWC8608-RL",
  "resolved": true,
  "ambiguous": false,
  "matches": [
    {
      "entity_type": "product_set",
      "canonical_code": "SRTWC8608-RL",
      "uuid": "608d64d6-93fe-4fa7-a84b-70879589b84c",
      "match_field": "set_code",
      "display": {
        "name": "Washdown with rimless flushing, S-trap",
        "member_count": 3,
        "complete_sets": 1629,
        "limiting_member": "SRTWCX8608-RL",
        "members": [
          {"product_code": "SRTWCX8608-RL", "description": "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL", "quantity": 1.0, "available": 1629, "is_discontinued": false},
          {"product_code": "SRTWCY8608",    "description": "SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP).  SRTWCY8608",    "quantity": 1.0, "available": 2051, "is_discontinued": false},
          {"product_code": "SRTWC8608-SC",  "description": "SORENTO SRTWC8608-SC SEAT COVER ONLY",                         "quantity": 1.0, "available": 2044, "is_discontinued": false}
        ]
      }
    },
    {
      "entity_type": "attachment",
      "canonical_code": "SRTWC8608-RL_TD.jpg",
      "uuid": "1fee0d26-b2e4-40c3-9b5e-f2e5575fdc78",
      "match_field": "original_filename",
      "match_tier": "prefix",
      "display": { "...": "unchanged from above" }
    }
  ],
  "alternatives": []
}
```

**Important correction to the earlier draft of this note: this is not an isolated new entity
type appearing in a vacuum.** For any token that already matches something else today (an
attachment filename, in this real example), turning the flag on makes `matches` grow to
carry BOTH. `resolved` stays `true` (its definition is `bool(matches) and not ambiguous`, not
"exactly one match" - see `TokenResolution.resolved`), and `ambiguous` is only set when two
rows of the SAME entity type collide, which product-vs-set is guarded against but
set-vs-attachment is not. **n8n's renderer has to handle a `matches` array that mixes
`product_set` with other types for one token, not assume `product_set` arrives alone.**

What else the resolver contract carries, unchanged from the earlier draft:

- Aliases: `product_set`, `product_sets`, `set`, `kit` all canonicalise to the entity type
  `product_set`, usable as `domain_hint`/`domain` or inside `allowed_entity_types`.
- No price in `display`, ever (a stock question gets stock; the price path is separate and has
  its own entitlement gates).
- `complete_sets` is `min(floor(available / quantity))` across members; `limiting_member` names
  the part that produced it. Never render a bare `0` - say which member is short.
- A discontinued member does not remove the set: it supplies 0 and becomes the limiting member.
- Asking for a bare MEMBER code does not mention its parent sets (that surfaces on the product
  detail page instead, see Surface 6).

**Two things this pass found that were not in the earlier draft:**

1. **FIXED, same branch.** `allowed_entity_types: ["product"]` now reaches the set probe too
   (`_expand_entity_types` in `app/services/entity_resolver.py`, additive - a `product` filter
   still gets ordinary products, plus the set probe becomes reachable). Gated behind the SAME
   `PRODUCT_SET_RESOLVE_ENABLED` flag as the rest of this surface, so this changes nothing while
   the flag stays off. Real evidence:
   `documentation/plans/master-data/product-set-n8n-evidence.md` command 1/2. What follows
   describes the bug this fixed, kept for context: `product_set` used to appear only when the
   caller's `allowed_entity_types` was either omitted (`None`, meaning "search everything") or
   explicitly included `product_set`/`set`/`kit`. n8n's stock-answer node passing
   `allowed_entity_types: ["product"]` to keep the resolve call narrow would have kept NOT seeing
   sets even after the flag flipped on - `product` did not auto-expand to include `product_set`
   the way `brand`/`category` auto-expand to `promotion`. It now does, for `product_set`
   specifically, gated the same way.
2. **AND-mode (`match_mode: "and"`) never returns a `product_set`, flag on or off.** There is no
   `product_set` probe registered in `_AND_PROBES` (`app/services/entity_resolver.py:3617`).
   Only OR-mode (the default, and what the `matches`-per-token examples above use) can surface
   one. If any n8n flow uses AND mode for compound stock queries, a set code inside it is
   invisible however the flag is set. Not fixed here (reported, not a defect in scope for this
   pass to change) - worth a decision on whether AND-mode needs it.

### Multi-company scope: read this before turning the flag on

`X-API-Key` calls resolve to **all-companies scope (`None`, no company filter at all)** unless
the request ALSO carries `contact_id` AND `space_id` query params
(`app/services/company_scope_resolver.py:_resolve_api_key_scope`, wired as a router-level
dependency on every `/api/v1/*` route, `app/main.py:238`). This is true for `/references/resolve`
exactly as it is true for every other route under `X-API-Key` - the fact that the `EXTERNAL_API_KEY_ACT_AS_USER_ID`
principal happens to belong to one company (Sorento, in this dev environment) does NOT scope the
query; that principal only supplies attribution (`created_by`), not the read filter.

Product codes already collide across companies today - 11,000+ codes exist in both Sorento and
Mocha - so an unscoped `/resolve` call already risks answering with the wrong company's product,
and that risk is unchanged by this feature. `product_set.set_code` has **zero** cross-company
collisions today (checked directly against the DB), but nothing stops one appearing once Mocha
starts using sets, and an unscoped call would then surface both companies' sets under the same
token with no way to tell them apart beyond an internal UUID.

**If n8n's resolve calls for the stock-answer flow already pass `contact_id` + `space_id`
(matching the practice the product probe already requires them to follow), no change is needed
here - this is a "confirm your existing practice already covers it" item, not new work.**

---

## Surface 2: The MCP server

**Status: UNCHANGED, confirmed by reading every tool.**

- No new MCP tool was added for sets (UAC D12 says so; the code confirms it - zero references
  to `product_set` or `ProductSet` anywhere under `sorento_crm_mcp/`).
- No MCP tool wraps `/references/resolve` at all (grepped for `system/references` and
  `references/resolve` in the MCP package - zero hits). That endpoint is called by n8n's AI
  orchestrator directly, not through MCP, so nothing in the MCP catalogue is affected by
  Surface 1 either.
- `crm_master_products_list` (the only product-related MCP tool that could plausibly be
  affected) calls `GET /api/v1/master-data/products` - the LIST route. The new "sets this
  product belongs to" field (Surface 6) is populated ONLY on the four DETAIL-shape methods
  (`get_product` and its siblings); list rows keep their original single query and gain nothing.
  There is no MCP tool that calls a product DETAIL-by-id route at all, so no existing MCP tool's
  response shape changes, checked, not assumed.

**n8n action: none.** If a new MCP tool for sets is wanted later, it must be seeded into
`agent_mcp_tools` in the same PR that adds it - standing rule in this repo, not optional, and
not needed for this launch since no such tool exists.

---

## Surface 3: External API, product attachments (`/api/v1/external/product-attachments`)

**Status: LIVE the moment this branch deploys.** No flag. `POST /` (single or bulk via
`payload.products`) and `POST /link-products` (bulk).

### What changed, concretely

The code path that matches `product_code` against the catalogue was replaced with one shared
resolver (`app.services.product_code_resolution.resolve_codes_to_products`), used by BOTH this
route and promotions (Surface 4) so the two can no longer disagree about what a code means.
Tiers, in order:

1. **exact** product code match
2. **product set** code, expanded to every member (NEW)
3. **`+`-split**, each half matched exactly
4. **substring**, every product carrying the code (this tier already existed here before sets -
   `product_attachments` has always done substring matching; what's NEW is tier 2 landing above
   it, and the shared helper itself)

For product attachments specifically, tiers 1, 3 and 4 are unchanged behaviour (substring
matching on a code was already how this route worked - `"WC7601"` already matched every SKU
containing it and linked the file to all of them). The only actual behaviour change here is
**tier 2, the set expansion**, plus one new response field.

### Before / after, for a set code

Take the real set `SRTWC8608-RL` (company Sorento, 3 members: `SRTWCX8608-RL`, `SRTWCY8608`,
`SRTWC8608-SC`).

- **Before this feature:** `product_code: "SRTWC8608-RL"` matches nothing (no product carries
  it as an exact code, prefix, or substring), so `create_product_attachment` returns
  `400 Invalid product_code`.
- **After (this branch):** the same call links the attachment to all 3 members. Each created
  `product_attachments` row carries `linked_via_set_id = 608d64d6-93fe-4fa7-a84b-70879589b84c`
  (the set's own id), where a link made by a person or by an exact code carries `NULL`.

### Response shape, by call shape

- **Single code, non-bulk `POST /`:** returns one `ProductAttachmentResponse` row (no
  `response_model` declared on that route, so nothing is stripped) - it now includes
  `linked_via_set_id` (`app/schemas/product.py:395`, inherited via `ProductAttachmentBase`), so
  n8n CAN see, per call, whether the link it just made came from set expansion.
- **Bulk (`POST /` with `products`, or `POST /link-products`):** returns
  `ProductAttachmentBulkLinkResponse { linked: [{product_id, product_code}], skipped_product_codes, already_linked }`.
  **`ProductAttachmentBulkLinkItem` does NOT carry `linked_via_set_id`** - checked against
  `app/schemas/external/attachments.py:158`. The bulk shape cannot tell n8n which of its linked
  codes came from a set; only the single-code response can. Reported, not changed here.

### Company scope

Pinned to the ATTACHMENT's own `company_id` before any product matching happens
(`scope_to_attachment_company`, `app/api/v1/external/utils.py:16`) - NOT the `X-API-Key`
all-companies default. This is the existing Group G isolation fix and it already covers sets:
a same-coded set in another company is invisible here regardless of the endpoint's default
scope. No change needed, already correct.

### The cleanup: removing a set member detaches its fan-out links

If a set's membership is edited (through the master-data set-edit flow) and a product is
dropped from it, `ProductSetService._detach_set_fanout_links`
(`app/services/product_set_service.py:339`) deletes any `product_attachments` row where
`linked_via_set_id` equals THAT set and the product is one that just left. A link a person made
by hand, or one made through an exact product code, is untouched (its `linked_via_set_id` is
`NULL`). Deleting the whole set instead of editing it does not run this cleanup - it relies on
an `ON DELETE SET NULL` foreign key (migration 412) so the document itself survives, only its
"why is this here" provenance is lost.

**n8n action: none required for this route.** The response shape addition is additive
(`linked_via_set_id` is a new optional field on the single-link response, nothing existing
removed or renamed). Worth knowing the bulk response can't show it, in case anyone downstream
wants to build a "was this a set link" check off the API response rather than the CRM UI.

---

## Surface 4: External API, promotions (`/api/v1/external/promotions`)

**Status: LIVE the moment this branch deploys.** No flag. `POST /`.

### What changed, concretely - this is the one with real risk, and you asked to run this
evidence yourselves, so here is exactly what to look for

Promotions used to match a code with **exact match, then a `+`-split fallback, and nothing
else**. It now goes through the SAME shared resolver as product attachments: exact, then
product-set expansion, then `+`-split, then **substring - which promotions never did before.**

This is a real, intentional behaviour change to a live path that has nothing to do with sets,
called out as such in the plan (`documentation/plans/master-data/PLAN-product-sets.md`, section
5): "This is a behaviour change to promotions for codes that have nothing to do with sets,
since they gain substring matching." It ships in the same commits as sets on this branch, not
split into its own PR the way the plan originally called for - see the pre-launch checklist.

### The two concrete input classes where old and new disagree

**Class A: a code that IS a set code.**
Old: `SRTWC8608-RL` matches nothing exactly, no `+` in it, so it lands in
`missing_codes`/`warnings`, and NO `PromotionProduct` row is created for it.
New: it expands to its 3 members, and a `PromotionProduct` row is created for EACH ONE,
`linked_via_set_id` stamped to the set's id on each.

**Class B: a code that is a SUBSTRING of one or more real codes, but not an exact code
itself and has no `+`.** Real example from the live catalogue:

```
select product_code, list_price from products
where replace(lower(product_code),' ','') like '%wc7601%' and company_id = '<Sorento>';

 CWC7601-P-RL     | 1225.00
 CWC7601-S        | 1225.00
 CWC7601-S-200-RL | 1450.00
 CWC7601-S-300-RL | 1450.00
 CWC7601-S-ECO    |    0.00
```

Old: `"WC7601"` (or any substring of these) matches nothing exactly, goes to `missing_codes`.
Nothing is created, no risk.
New: `"WC7601"` resolves to all 5 rows above. `create_promotion` creates 5 `PromotionProduct`
rows, ONE PER MATCH, and **each row's discount is computed from the payload's single
`selling_price` against THAT PRODUCT'S OWN `list_price`**
(`_promotion_product_values`, `app/api/v1/external/promotions.py:70`):
`discount_amount = list_price - selling_price`, `discount_percent = discount_amount / list_price * 100`.
If the operator meant one specific product at 1225.00 and typed a `selling_price` of, say,
980.00 (20% off), the SAME 980.00 now gets compared against 1225.00, 1225.00, 1450.00, 1450.00
AND 0.00 - the last one has `list_price = 0.00`, which the helper's own falsy check
(`lp = float(product.list_price) if product.list_price else None`) treats as "no list price," so
that row's discount is left exactly as the payload's raw `discount_amount`/`discount_percent`
rather than recomputed, which is its OWN separate surprise.

**What to look for in your evidence run:** any payload where `product_code` was written as a
short or partial code (a habit that was previously harmless because it just landed in
`missing_codes`) will now silently attach the promotion to every sibling SKU that contains it,
each with a discount computed off a price the operator never looked at.

### Response visibility: n8n cannot see provenance in the promotion response

Unlike product attachments, `linked_via_set_id` was added to the `PromotionProduct` MODEL and
its DB column (`app/models/marketing.py:194`) but **not to either promotion schema** -
`PromotionProductResponse` (`app/schemas/marketing.py:411`) and `PromotionResponse`
(`app/schemas/marketing.py:229`) both omit it. Checked against `response_model` on the create
route (`PromotionCreateResponse`, wraps `PromotionResponse`) - the field genuinely is not
serialized anywhere, not just dropped by `response_model`. Neither n8n's create-promotion
response nor the CRM's own promotion-detail screen can currently tell a person which lines came
from a set fan-out or a substring match versus an operator's exact code. Reported, not fixed
here - the plan's UAC didn't ask for this field to be surfaced on promotions, only for the
cleanup mechanism (Surface 3/4's detach behaviour) to have something to match against.

### A second, smaller finding: the warning message text is now stale

`create_promotion`'s `missing_codes` warning still reads `"Missing product codes (exact match,
then '+' split fallback)"` (`app/api/v1/external/promotions.py:188`) - it does not mention that
a code is now also tried as a product-set code and a substring before being called missing. Not
a functional bug (the field still correctly lists genuinely-unmatched codes), but if anything on
the n8n side parses or displays that message text, it undersells what was actually tried.

### Company scope

Pinned to the company_id(s) of the attachment(s) named in the payload
(`_attachment_ids_from_promotion_payload` -> `set_company_scope`,
`app/api/v1/external/promotions.py:150`) - same mechanism as product attachments, and it
already covers set expansion for the same reason. If a promotion payload carries NO
`attachment_id` at all, the request falls back to the `X-API-Key` default: all-companies scope
(same rule as Surface 1). Worth confirming n8n's promotion-create calls always carry at least
one `attachment_id`, which they appear to (the flow is built around a flyer PDF), but this is
the same trap as Surface 1 if that ever stops being true.

**n8n action: you already own this evidence run. Point it at Class A and Class B above with
real payloads, on a set code and on a short/partial code respectively, and confirm the
resulting `PromotionProduct` rows (queryable via `crm_marketing_promotion_products_list`, or
directly) are the ones actually intended.**

---

## Surface 5: Packing list create (`/api/v1/external/packing-lists`)

**Status: FIXED, same branch, superseding this section as originally written.** Real evidence:
`documentation/plans/master-data/product-set-n8n-evidence.md` command 5.

What follows is the ORIGINAL finding from earlier in this pass, kept for context on why the
change was made and what it does NOT do:

`create_packing_list` used to match `product_code` via `get_products_by_code`
(`app/api/v1/external/utils.py:92`) - a plain case-insensitive EXACT match
(`func.lower(Product.product_code).in_(...)`), nothing more, so a set code landed in
`skipped_product_codes`/`unknown_product_codes` and that line was dropped from the shipment.

Explicit product decision, from the person who owns this feature, directly overriding that
finding: a packing-list line naming a set code now fans out to the set's members through the
SAME shared resolver product attachments and promotions already use
(`resolve_codes_to_products`) - one helper, one behaviour (D11), rather than packing lists being
the one surface that still tells a customer/dealer "no such product." **This is NOT the same
thing `PLAN-product-sets.md` section 11 excludes** ("ordering, quoting or exploding a set onto an
**order** line") - that exclusion is about a customer's SALES order/quote line, an OUTBOUND
document. A packing list is INBOUND (what a supplier shipped), a different document with a
different question ("what physical goods just arrived"), and section 11 says nothing about it.

**The quantity decision, stated plainly:** the packing-list line's `quantity` is copied UNCHANGED
onto every member line - not split across members, not scaled by `ProductSetMember.quantity`
(how many of that part one assembled set needs). A physical packing slip has no field for "how
many complete sets" versus "how many of this one part," so scaling would invent a number nobody
on the slip actually wrote. See the evidence doc for the worked example and the full reasoning.

**n8n action: if a supplier's packing list ever prints a set/flyer code instead of a real SKU,
it now creates a line for every member at the code's own stated quantity - confirm that is the
receiving behaviour you want before this deploys.**

---

## Surface 6: Product detail, "sets this product belongs to"

**Status: LIVE the moment this branch deploys, if any n8n tool ever reads the product DETAIL
route (currently none do - see Surface 2).**

`GET /api/v1/master-data/products/{id}` (and the other three detail-shape read methods) now
returns a `product_sets` list, each entry naming a set by `set_code` that this product is a
member of. Always a list (a cistern can belong to more than one assembly). Populated by
`ProductService._populate_product_sets`, DETAIL-only - list rows (Surface 2's
`crm_master_products_list`) are untouched, confirmed in Surface 2 above. `ProductSetRef` is
declared on `ProductResponse`, so it survives `response_model` serialization rather than being
silently dropped.

**n8n action: none today, since no MCP tool or external route currently reads a product by id.**
If one is ever added, its response will additively include this field with no schema break.

---

## Open question, carried forward: which turn shape renders a set answer

The CRM cannot tell from here whether n8n's existing stock renderer can take a nested
`members[]` array (Surface 1's `display.members`) inline, or whether a `product_set` match
needs its own node/branch. This decides the shape of Surface 1's rollout - say which and the
CRM will match it. Two things sharpen this question versus the earlier draft:

1. Given `matches` can now legitimately carry MORE than one entity type for the same token (see
   the real attachment + product_set example above), does the renderer branch per-match on
   `entity_type`, or does it need the resolver to change so a set match suppresses co-occurring
   matches of other types? The CRM has NOT built that suppression - flagging it as a design
   choice for n8n to weigh in on, not something already decided.
2. Confirm whether your stock-answer node's `allowed_entity_types` (if it sends one) needs
   `product_set` added explicitly once the flag flips, per the finding in Surface 1.

## Rollout, updated

1. This document (plus the answer to the open question) goes to n8n for review.
2. This branch merges and deploys. `PRODUCT_SET_RESOLVE_ENABLED` stays unset, so Surface 1 is a
   no-op; Surfaces 3, 4, 5, 6 go live exactly as described above (Surface 5: no-op by design;
   Surfaces 3/4/6: live, no flag). This is the point at which n8n runs the Surface 4 evidence
   pass against production data.
3. n8n ships whatever the stock renderer needs for `product_set` (per the open question).
4. `PRODUCT_SET_RESOLVE_ENABLED` is turned on, coordinated, and Surface 1's behaviour appears.
5. The flag is deleted once it has been on for a while.

There remains a standing obligation to ping this workflow before any deploy touching
`/references/resolve`, so a no-change byte-parity snapshot can be taken. Step 2 above is
NOT that deploy for Surface 1 (the flag stays off through it) but IS the live deploy for
Surfaces 3, 4 and 6 - those have no such snapshot step today because they were never framed as
gated.
