# PLAN: SPEC-VARIANT-OR - a spec that narrows one code to 2+ variants ORs them

Status: in review (small fix track: backend only, no migration, no auth change), PR #1833

## Problem

Owner hand test, 23 Oct 2026, turn c4cffa1a "SRTWC8354 s trap 250MM". The parser and the
index were right (trap_type=s_trap, trap_length=250). `_narrowed_payload`
(`sorento_crm_backend/app/api/v1/system/references.py`) narrowed the one code to the two
variants that carry it, SRTWC8354-SH and SRTWC8354-SH-UF, but the request kept
`match_mode "and"`, so the resolver intersected the two codes' prefix families and the reply
listed the -SH-UF* rows, P trap ones included. The two-product-codes-means-OR rule
(`lanes/business/resolve_gate.py`, `resolve_entity_body`) runs before the narrowing and never
sees the variants.

## Fix (all in `references.py`)

1. `_picked_variants`: the variant codes a narrowing picked are the tokens it added, minus a
   bare code that is a typed token cut short (`narrow_code_tokens`'s fallback for a folded
   "Srtwc7604ptrap" whose words picked nothing; that is the typed family, not a variant).
2. `_variants_or`, at the end of `_narrowed_payload`: when the narrowing picked a variant and
   every token left is a product (a code the narrowing put in, or a token the caller typed as
   a product), `match_mode` goes to "or". The gate's own rule: several product codes name
   that many products. A token of another kind (a customer) keeps AND, as the gate does.
3. `_keep_exact_variants`, in `resolve_reference_post` after `_resolve_input`, OR mode only:
   each picked variant's token keeps its exact-code product match. OR alone answers each
   token's prefix family (the -SH token finds every -SH-* row). A token with no exact match
   is left as answered; two exact rows (one code in two companies) stay ambiguous.

Pins were not used for the exact match: a pin outside the resolver's company scope is a 400.

## Tests (red first, `tests/chatbot/test_trap_spec_search.py`)

- one code + grounded S trap 250 -> exactly the two 250 variants through the route, both
  resolved (code word in the message, and the carried-product shape)
- a spec narrowing to 1 code keeps the mode
- a spec matching no variant leaves the request unchanged
- a spec narrowing beside a customer keeps AND
- two typed codes still OR (gate regression pin)
- a bare code the narrowing falls back to keeps its family (reviewer's scenario)

## Out of scope

- Glued tokens ("SRTWC8354-250MM"), dim_length vs trap_length pick (INDEX-HYBRID scout).
- "SRTWC8354 s trap 250 for HANLIM": with a customer beside the code the request stays AND,
  so the two variants still intersect there. Follow-up if it shows up in a real turn.
