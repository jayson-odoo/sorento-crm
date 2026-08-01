# ADR 0008 - One viewer-resolved price, not a price per surface

**Status:** Accepted, 2026-08-01. Governs slice S7.2 and everything that displays money in the Dealer Kit.
**Context:** `PLAN-flyer-seeding.md` D5/D6, and UAC group C.

## The decision

There is exactly ONE function that answers "what does this viewer pay for this product",
and every surface calls it. No surface reads `products.list_price` and formats it, and no
surface does money arithmetic of its own.

```
resolve_prices(db, products, viewer, promotion_id=None) -> {product_id: PriceView}

PriceView:
  currency        str
  list_price      Decimal | None      what it costs without an offer
  offer_price     Decimal | None      the promotion's price, when one applies to THIS viewer
  invoice_price   Decimal | None      staff only, and only when the document asks
  promotion_id    str | None          which offer produced offer_price, for support questions
```

## Why now, before S7.2 is built

The Dealer Kit already turns a price into something a reader sees in **four** places, and
none of them knows promotions exist:

| Where | What it produces |
|---|---|
| `dealer_kit/collection_service.py:266` | the price on a catalogue tile |
| `dealer_kit/selection_service.py:190-209` | quote lines, line totals and the subtotal |
| `dealer_kit/bundle_service.py:120` | a bundle's component prices |
| `dealer_kit/bundle_pricing.py:73` | a bundle's saving against list |

Adding "a dealer sees the promo price while the promotion is live" one surface at a time
means four implementations of the same commercial rule, drifting independently, each with
its own idea of what happens when the promotion expires mid-session. The failure is not
hypothetical: this codebase has already lived through two SLA systems sharing one table and
discriminated only by a nullable column, and the cost was months of subtle wrong answers.

The Kit is also about to grow more surfaces that show money: the seeded catalogue (S7.4),
the design summary, and eventually an order. Every one of them is a chance to add a fifth.

## Rules this locks in

1. **The document never stores a price.** Already true (AC-G1) and restated because it is
   what makes one published page serve staff, dealers and consumers correctly.
2. **A FIGURE a viewer may not see never reaches them.** Not sent and hidden by the
   frontend, not sent and styled away: the number is not in the response. The same is true
   of the promotion's id, which would otherwise say "there is an offer here you are not
   being given".

   *Corrected 2026-08-01.* This rule first read "absent from the payload", which overstated
   what the codebase does and what matters. The precedent set by `invoice_price` (AC-G6,
   AC-G7) is that the KEY is present with a null value and the FIGURE is unrecoverable, and
   `offer_price` follows it exactly. A null key carries no information about the price, so
   the protection is identical, while a genuinely absent key would mean
   `response_model_exclude_none` and a breaking change for every reader. The wording is
   fixed here rather than the code being churned to match a doc that was wrong.
3. **Money is `Decimal` end to end.** Formatting happens at the edge, once. No float
   arithmetic, no summing in TypeScript. The frontend receives numbers it renders, never
   numbers it computes, which is why `quote_selection` sums server-side today.
4. **The brochure decides WHICH promotion, the viewer decides WHETHER.** A page carries at
   most one `promotion_id` (an explicit editorial choice, PLAN D5). Whether that promotion
   applies to the reader in front of us is `access_levels` plus the date window, resolved
   here, once.
5. **No applicable offer is the list price with no offer styling.** Never a hidden product,
   never a stale figure. An expired promotion is simply a promotion with no applicable rows.

## What this costs

Four call sites move to the new function as part of S7.2 rather than one. That is the price
of not having four commercial rules. It is paid once.

`resolve_prices` takes a LIST of products for the same reason `primary_image_urls` does: a
per-tile lookup turns a forty product catalogue into forty round trips, which is the
difference between a page that opens and a page a dealer gives up on.

## Alternatives rejected

**Resolve in each surface.** Cheapest today, and the reason the four readers above exist.
Rejected: the rule is commercial, not presentational, and a customer quoted two different
prices by two screens of the same product is the failure that costs trust.

**Put the promo price on the product row, refreshed by a job.** Fast reads, no join. Rejected:
one product has different prices for different audiences at the same instant, so a single
column cannot hold the answer, and a job means the paper and the screen disagree for as long
as the job is late.

**Resolve on the client from a promotions payload.** Rejected outright: it ships every
audience's pricing to every browser, which is the leak rule 2 exists to prevent.
