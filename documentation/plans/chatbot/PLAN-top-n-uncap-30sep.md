# PLAN - Top selling: a named N is no longer capped at 100 (TOP-N-UNCAP)

Status: in review on PR #1407 (small fix track: no migration, no auth/RBAC change, no UI).

Owner, 30 Sep 2026: "top 100 selling ... remove the cap, there is a use case of 100, 200".
Supersedes the 26 Sep ruling "a named N is 1 to 100" in
`PLAN-chatbot-top-x-hot-selling-24sep.md`.

## Change

1. One technical safety ceiling, `TOP_SELLING_N_CEILING = 1000`, replaces the three 100 caps:
   - backend engine (`lanes/business/fetch.py`): a named N above the ceiling is sent as the
     ceiling and flagged (`n_capped_from`) so the reply says so; never a silent clamp.
   - API (`orders.py` `_TOP_SELLING_N_MAX`): 422 only above the ceiling.
   - MCP presenter (`presenters.py`): renders every row up to the ceiling; when the named N
     was above it, the reply states the ceiling.
   The MCP package cannot import the backend, so it carries its own copy of the constant with
   a comment naming the backend one; a test pins the two equal.
2. Long lists: the presenter splits its text into WhatsApp-safe messages (each <= 3900 chars,
   never breaking a row, "(1/3)" markers) so delivery does not depend on n8n chunking.
3. Wording: the MCP tool description and the route docstring say "1 to 1000".

## UAC

- AC-1: N=200 returns 200 rows end to end (fetch -> API -> presenter), split into ordered
  chunks each <= 3900 chars, markers "(k/m)", no row split across chunks.
- AC-2: N=5 reply is unchanged (one message, no marker).
- AC-3: N above 1000 answers with 1000 rows under the line "I can list at most the top 1,000 in one reply."
- AC-4: API 422 `invalid_n` only for n < 1 or n > 1000.
