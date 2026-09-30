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
- AC-5 (grill Q6): the detail reply (one code's customers and months) longer than one message is
  split the same way: parts <= 3900 chars, "(k/m)" markers, no line broken, every customer once.

## Grill (feature skill Step 2, run late on 30 Sep 2026 after the owner's process audit)

The grill ran AFTER the code, which was built to the recommendation on each question below.
Asked as one `crew-ask` on PR #1407. Owner answer, 30 Sep 2026 (verbatim): "all as recommended
(over 1000 -> top 1000 with a note; buttons on last part only; split detail reply here; API >1000
-> error; sales analysis tool stays 100)".

| # | Decision | Options | Recommendation | Owner answer |
|---|----------|---------|----------------|--------------|
| Q1 | Safety ceiling | (a) 1000 (b) 500 (c) none | (a): 1000 rows is ~12 WhatsApp messages; no ceiling lets "top 50000" flood the chat | (a) as recommended |
| Q2 | Named N above the ceiling | (a) answer the top 1000 under "I can list at most the top 1,000 in one reply." (b) ask for a number 1 to 1000 | (a): answers at once, never a silent cut | (a) as recommended |
| Q3 | Long list delivery | (a) CRM splits into messages <= 3900 chars, never breaking a row (b) one message, rely on n8n chunking | (a): n8n chunking is unverified, WhatsApp limit is 4096 | (a) as recommended |
| Q4 | Part marker | (a) "(1/3)" own line at the top (b) "Part 1 of 3" (c) marker at the end | (a): short, reads first; a reply that fits one message has none | (a) as recommended |
| Q5 | Quick replies and the rank pick | (a) last part only (b) every part | (a): the question is asked at the end; a rank typed after any part still picks from the whole list | (a) as recommended |
| Q6 | Detail reply (customers and months) splitting | (a) backlog (b) split the same way in this PR | (b): same WhatsApp limit, ~3 lines plus a test | (b) as recommended: split here |
| Q7 | Direct API/MCP n above 1000 | (a) 422 "n must be between 1 and 1000" (b) silent clamp | (a): the lane clamps and says so; a raw caller gets a clear error | (a) as recommended |
| Q8 | "How many?" offered range | (a) 1 to min(count, 1000) (b) 1 to count | (a): consistent with Q1 | (a) as recommended |
| Q9 | `crm_sales_analysis` n (1 to 100) | (a) leave, a different tool (b) uncap too | (a): not in the ruling; a new ask if wanted | (a) as recommended |
