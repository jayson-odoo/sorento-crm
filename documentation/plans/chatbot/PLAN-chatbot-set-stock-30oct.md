# PLAN: CHATBOT-SET-STOCK - a stock ask for a set code answers SET availability first

Status: Waiting on owner (card v4 after the hand-test change request, 30 Oct ~22:30). Before: Build (owner answered card v3, 30 Oct ~17:35: resolver change, show every part under its set, today's
format, no prompt change). Red tests bb03573e, fix fa9fdcbe. Track: small fix (backend only, no migration, no
auth or ingest change). Size M, owner-visible chatbot change.

## Why

Owner, 30 Oct 2026 ~17:10: "I want to relook at our set to check for set instead of product, cause
recently got user raise back so i want to handle that". A salesperson asked "Pls check stock
srtwc7405 x 6 sets" and the bot answered per component code only, never how many full sets exist.

Behaviour card: `CARD-chatbot-set-stock-30oct.md` (same folder), filed as one crew ask.

## Root cause (verified in code, reproduced by test)

The chatbot resolves product tokens in AND mode (`match_mode: "and"`, `lanes/business/services.py:142`
into `references.resolve_reference_post`, then `entity_resolver.resolve_references_intersection`).
`_AND_PROBES` had no set probe, so "srtwc7405" matched only the product codes that contain it
(SRTWC7405-SC, SRTWC7405-SC-UOA); the tank and bowl carry SRTWCX / SRTWCY. The set expansion in the
gate was also tied to the CODE LOOKUP prompt flag, which the production parser version lacks.

## Change

1. `entity_resolver._and_probe_product_set` (AND mode) and `_prefix_probe_product_set` (OR tier 2),
   one shared builder `_product_set_entities`.
2. `lanes/business/gate.py` and `resolve_gate.py`: set members expand whatever the parser version.
3. `engine._exact_codes_only`: a set member belongs to the catalogue code its set starts with
   (availability contacts).

UAC: `chatbot-set-stock-acceptance-criteria.md`.
