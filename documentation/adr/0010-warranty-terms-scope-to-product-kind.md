# Warranty Terms scope to a Warranty Product Kind, not to `product_categories`

Warranty cover is defined against a **Warranty Product Kind** - a new mapped layer - and never
directly against `products.category_id` or `products.id`. `products.warranty_months` is abandoned.

A future reader will find `products.category_id` populated on 100% of 11,415 rows, sitting right
there, and wonder why warranty did not just use it.

## Why the existing columns cannot carry this

`products.warranty_months` is a single integer per product. Sorento's actual Warranty Policy
(Version 15, March 2026) is nothing of the kind. One Water Closet carries three simultaneous
promises:

| part | period | qualification |
|---|---|---|
| Ceramic Body | Lifetime, on crack line and leaking ONLY | external force excluded; installation **included** |
| Flushing Fittings | 5 years from date of purchase | installation **excluded** |
| Seat Cover Soft Close | 2 years from date of purchase | installation **excluded** |

Four dimensions an integer cannot hold:

- Cover attaches to a **part**, not a product, and the parts expire on different dates.
- "Lifetime" is not a number of months.
- Cover is **defect-scoped**: a lifetime ceramic body covers cracking and leaking and nothing else,
  so the reported defect type decides entitlement alongside the date.
- **Installation included / excluded** is part of the promise and is what decides who pays for the
  visit. Clause 15: *"Where fault is found to be something other than a warranty issue or the
  product is not our product, Sorento will be entitled to impose a callout charge."*

`warranty_months` is also empty: 0 of 11,415 rows populated. Nothing is lost by abandoning it.

## Why not `product_categories`

The categories are AutoCount merchandise codes, brand-split, with `category_name` equal to
`category_code` and no description: `SRT-FT` 1857, `SRT-BA` 995, `CB-FT` 950, `SRT-WB` 599,
`SRT-SH` 565, `SRT-WC` 484, `M-FT` 413, `BRT-WC` 127, and so on. `SRT-WC`, `CB-WC`, `M-WC` and
`BRT-WC` are four brands of the same physical thing, while the policy enumerates 31 kinds
(Water Closet, Urinal Bowl, Squatting Pan, Electronic Seat Cover, Intelligent Water Closet,
Tankless Water Closet, Wash Basin, LED Mirror, Mirror Cabinet, Stop Valve, Sensor Taps, ...) and
covers the Sorento brand only. Selling categories split by brand and buying pattern; the policy
splits by what a thing is and what can go wrong with it. They are different questions and one
column cannot answer both.

Scope is also not uniformly category-level. Some terms name a specific model list
(`SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB5060-BL, SRTMCB5061-BL`) and some name a series
(*Honeycomb Series*). A Kind is therefore mapped from category plus model-code rules, not from a
single FK.

## The payoff that justifies the extra layer

Deciding cover at Kind level means cover can be decided **before the exact model is known**. The
model codes people actually report do not resolve cleanly: `SRTWC8152` matches
`SRTWC8152-RL-RG`, `SRTWC8152-SH` and `SRTWC8152-300-RL`; `WC189-G2` matches nothing because the
reporter dropped the `SRT` prefix; `SRTWC8517-200mm` matches nothing because they appended the size
as text. All three `SRTWC8152` variants are Water Closets, so entitlement resolves with full
confidence while the variant stays open for Customer Service to pin down. A SKU-scoped warranty
model would stall on ambiguity that a Kind-scoped one absorbs.

It is also the level a Consumer recognises, which is what makes a picture-based chooser possible
instead of asking a homeowner to identify `SRTWC8152-RL-RG`.

## Consequences

- A Kind-to-product mapping must be maintained, seeded from category plus model-code rules, and it
  will need review when new categories appear. This is real ongoing cost, accepted.
- Terms are versioned and dated. A Complaint is judged against the terms in force on its **date of
  purchase**, so republishing the policy never changes what someone already bought. Clause 16
  reserves the right to amend without notice, which makes this non-optional.
- Replacing a part under warranty transfers the **remaining** cover, never a fresh term
  (clause 6 note).
- Cover is auto-activated from the purchase date and registration is optional, following the BRD.
  This is a deliberate departure from policy clause 3(b), which states a product must be registered
  before a claim may be processed. Sorento's business decision overrides the document. Clause 26's
  registration bonus (Automatic Water Booster Pump, "2 + 1 year extended warranty with online
  registration") is still modelled, so registration lengthens cover where the policy says it does.
- **Unresolved and referred to Sorento:** clause 17 restricts cover to residential installations and
  excludes commercial or industrial use, yet 23 of the 50 existing complaints are
  `customer_type='Project'` (hotels, commercial fitouts). Read literally, none of those are covered.
  The engine models the restriction but does not enforce it until Sorento rules on it.
