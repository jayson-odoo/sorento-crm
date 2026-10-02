# PLAN: several attachment types in one ask + human labels in the attachment picker

Status: Plan (behaviour card filed as crew-ask on PR #1437; waiting on owner answers, no code yet).
Track: to be named once the answers fix the diff size (expected: small fix track, no migration).
Lane: ATTACHMENT-MULTI (owner, 2 Oct 2026).

## Owner ask

1. A contact cannot get several attachment types at once (e.g. photo AND technical drawing in
   one ask). Support multiple types in one ask / pick.
2. The attachment picker shows the raw key `product_attachment`. No snake_case in any
   customer-facing reply; use human labels. Sweep other replies / pickers for leaked
   snake_case keys and list them.

Coordination: ACCESS-MODEL adds a per-contact switch for attachment stamping. The stamp stays
in ONE place (`answer.build_suggest_offer`'s stamp suffix), so that switch gates one seam.

## What exists (measured in the cloud sandbox, real resolver + gate + miss lane, MCP stubbed)

Turn "photo and technical drawing for srtwc286", seeded: SRTWC286-SH has a Product Photos file
only, SRTWC286-SH-200 a Technical Drawing only, SRTWC286-SH-P both.

- Resolver: both types resolve (`photo` -> Product Photos, `technical drawing` -> Technical
  Drawing). The gate keeps both; the probe call carries both `attachment_type_ids`. The fetch
  side already handles two types.
- Picker (today):
  ```
  product_attachment search needs to be more specific. Multiple matches found. Please choose:
  1. SRTWC286-SH - has Technical Drawing      <- false: it has only a photo
  2. SRTWC286-SH-200 - has Technical Drawing
  3. SRTWC286-SH-P - has Technical Drawing
  ```
  With no files at all every line reads "- no Technical Drawing" (the photo is never named).
- Cause 1: `miss_suggest._scoping_type_name` (miss_suggest.py ~1080) returns ONE type name, the
  last scoping entity.
- Cause 2: `miss_suggest._annotate` `row_present_with_type` (~957-1030) counts a product as
  "has" when ANY typed row came back, whatever its type, so "has" is per product, not per type.
- Cause 3 (code reading, not yet measured): the product_attachment miss sentence joins the
  type raws with a space (`answer.py` ~3940, `" ".join(attach_raws)`), so it reads
  "But no photo technical drawing matched these".
- Cause 4 (code reading): the found answer attaches whatever files exist and says nothing about
  an asked type the product lacks.
- Leak: `gate.py:928` interpolates `parser.domain_hint` into the picker header.

## Snake_case sweep (customer-facing, confirmed by tracing to the reply field)

| file:line | text | leaked value |
|---|---|---|
| gate.py:928 | `{domain} search needs to be more specific...` | `product_attachment` |
| gate.py:1518 | `"raw" (hint)` in "Couldn't find: ..." | `attachment_type`, `customer_order`, `inbound_shipment`, `order_number`, `product_type` |
| answer.py:3544 | `• {entity_type}: {value}` ("Here's what you want:", found_summary) | `attachment_type`, `customer_order`, `inbound_shipment`, `order_number` |
| answer.py:3200 | `{'/'.join(resolved_types)} {token}` | same kinds |
| answer.py:3728/3749/3755 | `is that a {labels}?`, `e.g. {labels}` | `customer_order`, `inbound_shipment`, `attachment_type` |
| answer.py:3741 | `I understood {hint} {raw}` | parser hints |
| answer.py:3158 | `That would search every {scope_word}` | `purchase_cost`, `resource_attachment`, `product_attachment` |
| answer.py:4752/4823 | `"tok" ({type_label}) - did you mean` fallback | raw hint |
| turn/reconcile.py:97 | kind_pick option `{raw} ({kind})` | "water closet (attachment_type)" (owner transcript) |
| lanes/canned.py:71 + chatbot_reply_copy.py:104 | `not allowed to access {{team}}` | `incoming_stock_enquiries`, `order_enquiries`, ... |
| miss_suggest.py ~1102 | stamp noun = resolver `canonical_code` = `code or type_name` | any attachment type that carries a slug `code` |

Fallback-only (a domain without a label): `answer.py:265` `DOMAIN_LABELS` lacks `spo_allocation`,
`purchase_cost`, `resource_attachment`, `purchase_order`; `turn/compose.py:354/412`.
Already safe: `_plain_words`, `_prettify_type`, `_pretty_team`. Labels for every domain and
entity kind already exist in `turn/policy_rows.py`; that is the one source to reuse.

## Proposed rules (pending the crew-ask answers)

- R1 One ask naming N types answers all N for the settled product(s).
- R2 Picker stamp is per (product, type): `1. SRTWC286-SH - has Product Photos, no Technical Drawing`.
- R3 A settled product missing an asked type: send the files that exist plus one line naming the
  missing type.
- R4 Miss sentence names the types with "or": "But no Product Photos or Technical Drawing matched these."
- R5 No snake_case key reaches a customer; type nouns are `attachment_types.type_name`, never `code`.

## Work

Filled in once the answers land.
