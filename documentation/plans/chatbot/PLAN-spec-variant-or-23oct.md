# PLAN: SPEC-VARIANT-OR - a spec that narrows one code to 2+ variants ORs them

Status: in progress (small fix track: backend only, no migration, no auth change)

## Problem

Owner hand test, 23 Oct 2026, turn c4cffa1a "SRTWC8354 s trap 250MM". The parser and the
index were right (trap_type=s_trap, trap_length=250). `_narrowed_payload`
(`sorento_crm_backend/app/api/v1/system/references.py`) narrowed the one code to the two
variants that carry it, SRTWC8354-SH and SRTWC8354-SH-UF, but the request kept
`match_mode "and"`, so the resolver intersected the two codes' prefix families and the reply
listed the -SH-UF* rows, P trap ones included. The two-product-codes-means-OR rule
(`lanes/business/resolve_gate.py`, `resolve_entity_body`) runs before the narrowing and never
sees the variants.

## Fix

In `_narrowed_payload`, after both narrowings: when one typed code was replaced by 2+ variant
codes and every token left is a product (a narrowing output, or an original token the caller
typed as a product), switch `match_mode` to "or". The same rule as the gate's: several
product codes name that many products, one product cannot be several codes. A token of
another kind (a customer) keeps AND, as the gate does.

## Tests (red first, `tests/chatbot/test_trap_spec_search.py`)

- one code + grounded S trap 250 -> exactly the two 250 variants through the route
- a spec narrowing to 1 code unchanged
- a spec matching no variant unchanged
- two typed codes still OR

Out of scope: glued tokens ("SRTWC8354-250MM"), dim_length vs trap_length pick.
