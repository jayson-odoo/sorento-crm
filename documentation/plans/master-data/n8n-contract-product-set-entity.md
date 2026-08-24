# Contract change: `entity_type: "product_set"` on `/references/resolve`

**For:** `sorento-crm-n8n-60`
**From:** the CRM side, branch `feat/product-sets`
**Status:** DRAFT, awaiting n8n confirmation. **The CRM ships this OFF.**

## Why

A two-piece water closet is sold as one thing and stocked as three. The flyer
prints `SRTWC8608-RL`. The catalogue holds only the parts:

```
SRTWCX8608-RL   SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)   1180.00
SRTWCY8608      SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)        0.00
SRTWC8608-SC    SORENTO SRTWC8608-SC SEAT COVER ONLY               85.00
```

No product carries `SRTWC8608-RL`. `_probe_product` is an exact match on
`product_code`, so a customer asking `check stock SRTWC8608-RL` is told the
product does not exist. Measured on the live catalogue: **47 two-piece families,
23 with no bare code at all**, across roughly 338 role-bearing SKUs.

## The change

One new `entity_type` value. Nothing existing changes shape.

```json
{
  "entity_type": "product_set",
  "canonical_code": "SRTWC8608-RL",
  "uuid": "...",
  "match_field": "set_code",
  "display": {
    "name": "Washdown with rimless flushing, S-trap",
    "member_count": 3,
    "complete_sets": 0,
    "limiting_member": "SRTWC8608-SC",
    "members": [
      {"product_code": "SRTWCX8608-RL", "description": "...", "quantity": 1.0,
       "available": 40, "is_discontinued": false},
      {"product_code": "SRTWCY8608",    "description": "...", "quantity": 1.0,
       "available": 12, "is_discontinued": false},
      {"product_code": "SRTWC8608-SC",  "description": "...", "quantity": 1.0,
       "available": 0,  "is_discontinued": false}
    ]
  }
}
```

Also accepted as `domain_hint` / entity-type aliases, all canonicalising to
`product_set`: `product_set`, `product_sets`, `set`, `kit`.

## What the renderer needs to know

- **It is ONE entity, not three.** A set does not fan out into member products.
  The customer named the assembly, and the reply should name it back.
- **`complete_sets` is the shippable count**, `min(floor(available / quantity))`
  across members. `limiting_member` names the part that produced it.
- **Never render a bare `0`.** "0 complete sets, short on SRTWC8608-SC" is the
  intended shape. A bare zero reads as a bug to a dealer who knows there are 40
  pedestals on the shelf, and per-member `available` is the primary answer.
- **A discontinued member does not remove the set.** It is flagged, it supplies
  0, and it becomes the limiting member. The flyer code is still asked about.
- **No price is present, deliberately.** A stock question gets stock. Price goes
  through the price path, which has its own entitlement gates.
- **Asking for a MEMBER code alone does not mention its parent sets.** A dealer
  asking about a cistern wants the cistern.

## Rollout

The CRM side is behind `PRODUCT_SET_RESOLVE_ENABLED`, default **off**. So:

1. n8n reviews this document and says what, if anything, needs to change.
2. CRM merges and deploys with the flag off. Nothing changes for any caller.
3. n8n ships the renderer for `product_set`.
4. The flag is turned on, coordinated, and the behaviour appears.
5. The flag is deleted once it has been on for a while.

There is a standing obligation to ping this workflow **before any deploy touching
`/references/resolve`** so a no-change byte-parity snapshot can be taken. Step 2
is that deploy: the flag being off is what makes the snapshot match.

## Open question for n8n

Which turn shapes should carry the set answer? The CRM cannot tell from here
whether the existing stock renderer can take a nested `members` array or whether
this wants its own node. Say which and the CRM will match it.
