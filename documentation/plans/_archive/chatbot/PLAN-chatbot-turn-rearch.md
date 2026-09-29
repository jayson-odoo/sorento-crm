# PLAN - Chatbot turn engine re-architecture

Status: SHIPPED 22 Sep 2026 - PR #952 merged (0a335146e) + fresh-migration hotfix #1097 (c1412b1a0), prod deploy run 35660503056, parser prompt v42 promoted by migration chatbot_rearch_s12. Was: APPROVED by the owner 15 Sep 2026 23:40 MYT on `.lavish/chatbot-turn-rearch-plan.html`
("approved, slice into tickets"); UAC `chatbot-turn-rearch-acceptance-criteria.md` (AC-1501 to
AC-1594). Tickets: S0 #935, S1 #936, S2 #937, S3 #938, S4 #939, S5 #940, S6 #941. Lane branch
`feat/chatbot-turn-rearch` off main; tester branch `test/chatbot-turn-rearch-red`. S0 reds and S1
mocks started 15 Sep 23:50 MYT. `focus.document` is a LIST of document kinds (["DO"], ["SO","DO"])
so "both" needs no third value.

Owner decision: option C on `.lavish/chatbot-architecture-15sep.html`, 15 Sep 2026 21:40 MYT,
grill rounds 1 to 3 the same night. Mockups: `.lavish/chatbot-config-mockups.html`.

## Why

- The dialogue engine is 36,553 lines in 46 files. Thirty sites decide what a number, a yes,
  a no or "X only" means (13 apply the parser verdict, 13 override it, 4 patch a v1 prompt
  gap); 22 sites arm or resolve the open question; 18 decide the escalation team or offer.
- 4,566 tests and 1,791 replays were green; the owner's 20-minute hand pass found eight
  defects. Two were the same shape: the parser answered correctly and a downstream layer
  overruled it or read a second copy of the state (`X only` dropped the customer because fetch
  reads a rebuilt entities list, not focus; "is it discon?" printed "not recorded" because the
  composer's word list never learned the word).
- Every fix round on the old seams produced a regression on another seam; a day was spent
  on one lane's merge test. The owner's condition for the redesign: everything built must
  still work (129-line contract), and adding a domain must get cheaper.

## Measured (stack worktree at 0e93dcea5, 15 Sep 2026)

| what | value |
|---|---|
| `app/services/chatbot/` | 36,553 lines, 46 files |
| biggest files | engine.py 4,354; head/output_exchange.py 4,191; lanes/business/answer.py 4,163; tail/compile_state.py 3,293 |
| rule sites for number / yes / no / only | 30 (apply 13, override 13, v1 gap-patch 4) |
| pending arm / resolve sites | 22 (14 arm, 8 resolve) |
| team / offer decision sites | 18 plus about 20 print sites |
| LLM calls per turn | 1 to 4; parser 12k tokens, no timeout, no retry |
| config: page / DB-only / code constant | 25 / 3 / 28 |
| lines that go | about 9,000 (head, tail, dialogue, v1 schema, regexes) |
| lines that stay | about 27,000 (lanes, fetch, composers, escalation, contracts, console, trace) |

## What exists and is kept

Outer loop (n8n spine, `/external/chat/turn`, actions contract, retry ingress, media path);
`lanes/business` resolver, gate, fetch, MCP tools, composers; `lanes/escalation`, `lanes/casual`,
canned lanes; access (`head/access.py`); `chatbot.turns` + trace + chat-history viewer + console
+ shadow parse; prompt registry and labels; `conversation_frames` table and
`/memory/frames/search` (Phase 1, 2026, never wired); the console corpus and replay fixtures
for kept nodes; the five-key session shape.

## Design

### Turn order (seven stages)

```
A INTAKE   dedup, INSERT chatbot.turns, load state {focus, pending, profile, episodes-hint}
B PARSER   one call, one schema (v3 shape + document, status, backward_reference)
           hints in: Focus / Open question (frozen options) / Profile / Episodes (when recalled)
C APPLY    state' , plan = apply(state, verdict, policy)     pure, no text, no I/O
           resolves or clears pending, applies focus rules, narrower, reconciliation request
D ROUTE    from plan only: ask | business | escalation | casual | canned | denied
E FETCH    for d in plan.fetch: resolve (with reconciliation) -> gate -> tool(d) -> envelope
F COMPOSE  data first {sections, question, offer, canned, files}; text by the #930 grammar
G TAIL     pending' = composer.question; persist five keys FOR UPDATE; episode write on
           topic switch; trace apply + memory + prompt_text; actions out
```

Reconciliation lives in E because it needs the resolver (a lookup), but its RULE is declared
in C's policy and its outcome is written back into state' before F runs (one re-entry of
`apply` with `resolved_kinds`, still pure). Recall is a re-parse: when the verdict says
`backward_reference` and the contact's toggle is on, G's helper fetches frames, B runs once
more with the `Episodes:` block, C runs on the second verdict. Traced as `recall`.

### State: three shelves, one writer each

| shelf | where | writer | reader |
|---|---|---|---|
| focus + pending | `respond_contacts.session_vars` five keys (unchanged shape; `focus.document`, `focus.status` replace `order_status`) | APPLY (via TAIL persist) | parser hints, fetch (the only scope) |
| profile | `respond_contacts.chatbot_profile` JSONB + `chatbot_recall_enabled` | explicit picks (tier, ledgers) and the Contact page | parser hints, tier narrower |
| episodes | `conversation_frames` + embeddings | TAIL on `topic_reset` / conversation close | recall only |

### The policy: `chatbot_domains` and `chatbot_entity_kinds`

`DOMAIN_SPEC` becomes a table seeded from the constant (AC-1501). Per row: tools, primary
tool, team FK, switch words, intents, date filter, reveal key, supported, `narrowing` (entity
kind to one of `must_narrow_one | narrow_to_code | narrow_by_type | narrow_by_tier |
optional_filter | list_all | not_applicable`), `ladder`. `chatbot_entity_kinds` holds the 12
kinds with resolver source, did-you-mean flag, default narrowing, family grouping, base
property words (product), tier order. Loaded once per turn into a frozen `Policy` object
handed to APPLY and FETCH. Guardrail: until the constants are deleted (S6), a test asserts
table == constant.

The parser prompt's domain and entity blocks are rendered from these rows at publish time
(`ai_prompt_registry.render` gets a `blocks` provider). Saving a row never touches the live
prompt; the Prompts page shows "domain block out of date" (AC-1552).

### APPLY contract

```
apply(state: State, verdict: Verdict, policy: Policy, resolved: ResolvedKinds | None)
  -> (State, Plan)
State  = {focus: Focus(11 axes), pending: Pending | None, profile: Profile, turn_no: int}
Plan   = {domains, fetch: [FetchSpec], ask: Pending | None, denied: [...], trace: ApplyTrace}
```

Verdict is the parser's JSON as a plain dict (validated once by the parser schema, never
re-modelled). Keys APPLY reads: `entities[]` (raw, hint, canonical_code, current_message,
confident, hint_confident), `entity_op`, `scope_exclusive`, `reference_positions`,
`answers_open_question{resolved, picks, answer}`, `is_affirmative`, `escalation{...}`,
`domain_hint`, `intent_hint`, `message_type`, `asks[]` (each `{domain, intent}`, message
order: this is how a two-domain message travels; `focus.domains` = `asks[].domain` when
present, else `[domain_hint]`), `topic_reset`, `document`, `status`, `anaphora{backward_reference}`,
`date_*`. `turn_no` comes from intake (count of this contact's turns) and stamps
`pending.asked_at_turn` and every focus slot's `set_at_turn`.

Pending kinds (nine): the lane's eight `product_pick`, `customer_pick`, `tier_pick`,
`team_pick`, `company_pick`, `member_offer`, `outstanding_scope`, `outstanding_detail`, plus
`kind_pick` (reconciliation). Roster kinds `product_pick`, `customer_pick`, `kind_pick` stay
alive after their own pick (D19, contract 36) with `answered_positions` recorded; the other
six clear when answered. Main's older names map onto these (`disambiguation` = product_pick,
`escalation_offer` = team_pick with one option, `tier_ask` = tier_pick, `team_clarify` =
team_pick, `company_clarify` = company_pick).

Rules, in order, each a named function in `turn/apply.py` and each a replay case:

1. `answer_pending` - number / multi / all / yes / no / name against `pending` from
   `reference_positions`, `answers_open_question`, `is_affirmative`, `escalation.*`. A pick
   never changes domain. A roster survives its own pick. An answer never consumes a question
   this turn will ask (the composer decides asks; APPLY only resolves).
2. `focus_rules` - the seven existing rules, ported verbatim, with `document` / `status`.
3. `exclusive` - `scope_exclusive` replaces only the named axes.
4. `reconcile` - if `resolved` says a hinted kind missed and one other hit: rewrite kind,
   follow domain when no domain word; two hits: `ask = kind_pick`.
5. `narrow` - per (domain, kind) policy: proceed / roster ask / type ask / tier ask.
6. `plan` - domains in message order (fan-out), fetch specs from focus, denied from grants.

No function reads `message.text`. Grep guard in AC-1520.

### Fetch and compose (kept, tightened)

`run_fetch` loops `plan.fetch` (lane 2 design, contract 122 to 128). Composers return data
(`Answer`) and the renderer applies #930's grammar (contract 102 to 105). The composer's
`question` and `offer` fields are the ONLY way a question or an offer reaches the tail.

### Tail

Persists; writes the episode on topic switch; trace records `apply`, `memory`, `prompt_text`.
Deletes: `record_offer`, `team_from_reply`, `_spend_the_answer`, `with_offer`, `_re_armed`,
`_partial_dym_block`, `_picker_carry`, `_offer_carry`.

### Config pages (data only)

Chatbot Domains list + modal, Entity kinds list + modal, three cards on Settings > Chatbot,
Contact > Access "Chatbot" card, two panels in the turn drawer. Mockups M1 to M5. No rule
editor (growth-r1 D5).

### Turn replay (the gate)

`tests/chatbot/replay_turns/<group>/<case>.json` = `{envelope, verdict, expected}` recorded
by `scripts/chatbot_record_turn.py` from a `chatbot.turns` row (verdict = trace parser raw;
expected = data extracted from the stored response). `test_turn_replay.py` mocks the parser
with the verdict and compares structurally (AC-1591). `DIVERGENCES.md` holds signed entries.
Corpus: 129 contract lines, 91 console cases, 17 owner chains, #930 and #833 files, about 40
real turns per branch kind from the 0915 prod copy.

### Simplest thing that works, checked

- One new table pair (domains, entity kinds), one JSONB column, one bool column. No memory
  service; episodes reuse `conversation_frames`. No engine switch; rollback is a redeploy.
- No registry of rules: `apply` is six named functions called in order.
- No answer LLM. No shadow turn. Recall is one re-parse behind two flags.
- The composers, resolver, gate, fetch, escalation and outer loop are not rewritten.

## Slices

| slice | scope | ACs |
|---|---|---|
| S0 | Branch `feat/chatbot-turn-rearch` off main. Migrations: `chatbot_domains`, `chatbot_entity_kinds` (seeded), `respond_contacts.chatbot_profile` + `chatbot_recall_enabled`, `conversation_frames` columns as needed; `SessionVars` document / status; parser schema unification; external contract pin | AC-1501 to 1507 |
| S1 | Phase 1 FE, mocked: Domains, Entity kinds, Settings cards, turn drawer panels, Contact card | AC-1510 to 1517 |
| S2 | `app/services/chatbot/turn/` : `state.py`, `policy.py`, `apply.py`, `pending.py`, `narrow.py`, `reconcile.py`, `plan.py`; tests from the contract | AC-1520 to 1528 |
| S3 | Engine rewired A to G; fetch fan-out; composers return data; tail; episodes; recall; profile hints; trace records; deletions of head / dialogue / tail | AC-1530 to 1549 |
| S4 | Prompt: one lineage, generated blocks, #921 / #928 / #933 fixed, staleness banner | AC-1550 to 1552 |
| S5 | FE wired to real; CRUD routes + permission + grant sweep | AC-1560, 1561 |
| S6 | Turn replay corpus complete, test triage, deletions guard, owner hand pass twice, deploy | AC-1590 to 1594 |

Owner hand pass 1 after S3 (engine complete, FE still mocked); hand pass 2 after S6.

## Testing seams (agreed before Phase 2)

- `apply()` is pure: tests are tables of (state, verdict, policy) to (state', plan).
- `Policy` is built from rows: tests seed rows, never patch constants.
- Resolver returns `ResolvedKinds`; reconciliation tests stub it.
- Composer `Answer` data is asserted before text; text asserted only via #930 goldens.
- Turn replay is the integration seam; the parser is never live in CI.
- Prompt slice (S4) is the only live-LLM test file, paced, run by hand, verdicts recorded.

## Phase 1 (frontend, mocked)

Service files declare the contract at the top: `GET/POST/PUT/DELETE
/api/v1/system/chatbot/domains`, `/entity-kinds`, `GET /system/chatbot/turns/{id}` gains
`apply`, `memory`, `prompt_text`; `PUT /user-management/contacts/{id}/chatbot` for the profile
and recall toggle; settings gain `chatbot_tier_order`, `chatbot_memory` JSONB.

## Hazards

- The five-key session shape must stay byte-compatible for #930's parked lane and for live
  contacts mid-conversation at deploy: `order_status` is read once and mapped.
- `conversation_frames` was built for n8n Phase 2 and never exercised; its embedding path
  must be re-verified on the worker (DYLD, `OPENAI_API_KEY` in the worker env; see
  LESSONS-LEARNT).
- Recall re-parse doubles the parser cost on those turns; behind the per-contact toggle.
- Test triage volume: 22 lane-only modules plus every main module importing head / dialogue /
  tail. The tester's triage table is a deliverable, not a side note.
- The 0915 prod copy is the replay source; a turn recorded under v16 or v20 is replayed with
  its own verdict, so prompt drift never breaks the engine gate.
- Prod is frozen for chatbot changes except hotfixes and prompt-only fixes until S6 ships.

## Deferred (triggers)

| deferred | trigger |
|---|---|
| cross-contact recall (same company, another person) | owner asks after seeing same-contact recall in prod; privacy ruling needed |
| profile default-ledgers override | a contact asks to exclude a ledger class twice |
| answer LLM, agent strategy | never under this plan (growth-r1 D1) |
| rule editor / flow builder | never (growth-r1 D5) |
| shadow turn | if a future engine change is too large for a hand pass |
