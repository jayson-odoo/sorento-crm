# UAC: Resolver head-code retry

Every criterion is a pytest in `sorento_crm_backend/tests/test_resolve_head_code_retry.py`
(Postgres fixture, ZZT-prefixed scratch products seeded by the test - never rows from the
shared dev copy).

- **AC-1 head-code resolve.** POST /references/resolve with
  tokens=["ZZTWB8004BASINTAP"], raw_tokens=["ZZTWB8004 BASIN TAP"], product code ZZTWB8004
  seeded -> resolves to ZZTWB8004 with `match_tier: "head_code"`, `entity_type: "product"`,
  and the full row fields the n8n routing depends on: `company_id` present and
  `display.brand` present (seed the product with a brand + company).
- **AC-2 spaced codes still exact-hit.** Seed codes shaped like the -WALL HUNG family
  (`ZZTWB7299-WALL HUNG`) and `ZZT86CR-HEAD ONLY`; folded token
  ("ZZTWB7299WALLHUNG") + raw with spaces -> Tier-1 exact hit, `match_tier: "exact"` (NOT
  head_code), same row as today.
- **AC-3 split codes unchanged.** Seed `ZZB 6201`-shaped code; token "ZZB6201" exact-hits as
  today. And a raw "ZZB 6201" whose folded token misses (code not seeded) gains NO match from
  the retry (head "ZZB" has no digit -> pattern rejects).
- **AC-4 no code-like head unchanged.** tokens=["BASINTAPCHROME"],
  raw_tokens=["BASIN TAP CHROME"] -> no retry fires; response matches the no-raw_tokens
  response for the same token.
- **AC-5 inert without raw_tokens.** The same folded-token request WITHOUT raw_tokens returns
  no head_code match (byte-identical behaviour to today).
- **AC-6 retry beats spec-search.** Request with spec_fallback=true and a head-resolvable
  token -> `resolutions` carry the head_code product and no spec_candidates are produced for
  it (normal probes counted as resolved).
- **AC-7 head exact-miss is a clean miss.** raw "ZZTWB7299-WALL HUNG EXTRA" (head regex yields
  "ZZTWB7299-WALL", which is not a full code) -> no match added, no error; trgm alternatives
  behave as before.
- **AC-8 length-mismatch ignored.** raw_tokens shorter/longer than tokens -> field ignored,
  behaviour as AC-5.
