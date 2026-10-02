# PLAN: combo (product set) stock in the chatbot stock answer (COMBO-STOCK)

Status: Plan (scout done; behaviour card asked on PR #1443, awaiting owner). Track: small fix
expected (no migration, no RBAC, no new ingest surface), confirmed once the card is answered.

## Journey

Owner, 2 Oct 2026 (dev, business_query v43):
- "chck stock SRTWC8608" lists only SRTWC8608-SC (Total 1074) and SRTWC8608-SC-UF (Total 0,
  PO placed). No set, no pedestal, no cistern.
- "chck stock SRTWC8608-RL" answers "That would search every stock we have - I need at least
  one filter ... Give me a product code" although it WAS a code.

## Scout findings (file:line on main 6864cd0b)

### a) How combos are modelled

Explicit-link tables that exist, and which one the chatbot reads:

| Table | What it is | Qty per set | Chatbot reads it? |
|---|---|---|---|
| `product_sets` + `product_set_members` (`app/models/product_set.py:47`, `:93`) | A CODE (e.g. `SRTWC8608-RL`) naming an assembly sold as one thing, stocked as its members. Not a product, never stocked. Created by hand or via reviewed proposals (`product_set_proposal_service.py`, prefix guesses are only PROPOSALS a person confirms). | `ProductSetMember.quantity` NUMERIC (`product_set.py:113`) | Resolver yes (`entity_resolver.py:861` `_probe_product_set`, exact set_code, already computes `complete_sets` + `limiting_member` at `:937-946`). Stock answer NO (see c). |
| `item_packages` / `item_package_lines` (AutoCount PackageDTL mirror) | Read by raw SQL in `project_so_draft_service.py:957-990`; its model/migration "ships on the AutoCount branch" and is NOT on main (no alembic file creates it). | `qty` | No |
| `product_combos` / `product_combo_parts` (`app/models/product_combo.py`) | Price-tag packages ("3 in 1"), no code, choice groups. | n/a | Deliberately invisible to the chatbot (owner ruling 1, AC-S1-8, docstring `product_combo.py:9-11`) |
| `product_companion_rules` (`app/models/product_companion.py`) | Supplier "ships with" rule for PO lines | ratio | No (procurement only) |

So the explicit link the chatbot should use is `product_sets`. No code-prefix guessing.

SRTWC8608 family (repo evidence; this sandbox has no dev DB by contract):
- Members of the flyer set `SRTWC8608-RL`: `SRTWCX8608-RL` pedestal, `SRTWCY8608` cistern,
  `SRTWC8608-SC` seat cover (`product_set.py:3-5`, quotation fixture
  `sorento_crm_frontend/e2e/fixtures/project-cs/quotation-qt-004188.lines.json:33-52`).
- `SRTWC8608-P-RL` is a set in prod too (22 Sep hotfix evidence, contact 423729104 turn 59).
- Dev proof that `SRTWC8608-RL` IS a `product_sets` row there: the owner got the
  scope-needed sentence, which only a PLACED-but-inventory-incompatible entity produces; an
  unknown code gets "could not find" instead (repro below).
- There is NO set coded `SRTWC8608` (the base code): it resolved via the product prefix tier.

### b) What the stock ask does today

- Combo base code "SRTWC8608": not a product, not a set code, so tier 2
  `_prefix_probe_product` (`entity_resolver.py:1864`) prefix-matches product codes
  `SRTWC8608%` -> `SRTWC8608-SC`, `SRTWC8608-SC-UF`. The pedestal `SRTWCX8608-RL` and cistern
  `SRTWCY8608` do not start with (or contain) "SRTWC8608", so they never appear. No set
  expansion happens on this path at all.
- Set code "SRTWC8608-RL": see c.

### c) Why "SRTWC8608-RL" was refused as filterless (bug)

1. `_probe_product_set` places the token as `entity_type="product_set"` (tier 1, so the
   product prefix tier never runs).
2. `gate.ALLOWED["inventory"]` (`lanes/business/gate.py:83`) is
   `["product","warehouse","category","brand"]`: `product_set` is dropped from
   `compatible_entities`.
3. `turn_runtime.make_tool_runner.runner`: the inventory fetch has no entity with a uuid, so
   the 22 Sep no-subject guard (`no_subject_gate`, `turn_runtime.py:~2905-2918`) refuses it
   and stamps the `needs_scope` sentence. Reproduced end to end in the test harness: reply
   "That would search every stock we have - ..." and zero tool calls.

Fix (no ask needed): an inventory ask whose subject placed as a product set is answered over
the set's MEMBERS (explicit `product_set_members` link), never refused as filterless.
The resolver's own docstring already names this as the design (`entity_resolver.py:931-938`:
"For n8n's fan-out ... this is what feeds them").

## Behaviour card

Posted as `crew-ask` on PR #1443. Answers recorded here when they arrive.
