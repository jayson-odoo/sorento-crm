# PLAN: PROMPT-RULES-DIET (parser prompt 130k -> under 90k chars, measured round by round)

Status: Build (size M, prompt-only). Behaviour card answered by crew a74970758 (26 Oct): Q1 (a) pay a round-0 baseline on
v185; Q2 TRAIN x3 while it fits, x2 from the round that would pass USD 30, stop and report before any spend past 30; Q3 harness
runs the slim-index worktree read-only until #1865 merges, product module + migration on a branch from main after; Q4 (a);
Q5 hand test = diet version alone. Track: M (crew brief), not the small fix track: the text change is large and gated on
paid evals. Base: the list-free parser text of PR #1865 (CHAT-SLIM-INDEX), not yet merged.

## Owner ruling (26 Oct ~08:15 MYT, verbatim)
"yeah take the prompt from 130k to 90k yes, measured round by round"

## Journey
A customer or salesperson types into the chat. The parser reads the system prompt plus the turn. Today the list-free text
(v185 on the crew dev DB, `chatbot_lookup_edits.apply(v63)`, 129,651 chars, md5 3f1e2d27) is 92 % rule prose that repeats
itself: the same rule restated in several sections, long example runs, multi-paragraph justifications. A shorter text costs
less per turn and leaves the model fewer contradictory restatements. The parse must come out the same or better.

## Measured start (recomputed 26 Oct on 3f1e2d27, sections split on `== ... ==` and the boxed ALL-CAPS headings)
89 sections, 129,652 chars. Largest: ESCALATION CONFIRMATION + policy blocks 8,855 (L1645); DECISIVE DOMAIN TERMS 6,912
(L104); SALES RANKING 5,789 (L1040); REQUESTED ATTRIBUTES 5,032 (L241); BROADEN AXIS 3,851 (L454); THE OPEN QUESTION 3,744
(L1279); LOW STOCK REPORT FILTERS 3,639 (L989); OPEN NUMBERED QUESTION 3,633 (L842); MESSAGE TYPE 3,491 (L312); ENTITY
CONFIDENCE 3,399 (L419); ENTITY OPERATIONS 3,235 (L366); COMPANY-NAME REPLY 3,120 (L600); THE specification ENTITY 3,030
(L1388); OUTPUT 3,018 (L738); NARROWING A TOP SELLING ASK 2,979 (L1567). Matches the crew audit within a few chars.

## ARCHITECTURE
- Layer: prompt TEXT only (the parser head's system template). No engine, lane, schema or code-path change. Parser-first
  stands: no regex / word rule moves into code to make up for removed text.
- Shared mechanism, reused not copied: the anchored-edit shape of `app/services/chatbot_lookup_edits.py` (`Edit(op, anchor,
  payload)`, `apply(text) -> str | None`, every anchor exactly once or nothing changes, `replace_line` by sha256 for a line
  that must not be quoted in the public repo). New module `app/services/chatbot_prompt_diet_edits.py` holds this lane's
  EDITS and applies them ON TOP of the list-free text.
- Migration `diet_0001_parser_prompt_diet`: publishes ONE new UNLABELLED version = diet edits on the list-free text built from
  the production-labelled text (lookup edits first unless the production text already carries `== LOOKUP LISTS ==`).
  Idempotent; any anchor missing or doubled publishes nothing and logs why; the label never moves.
- Classes fixed, not one shape: every cut is one of (1) a rule restated in another section collapsed to its one home,
  (2) an example run cut to the examples that each show a different case, (3) a justification paragraph cut to its rule
  sentence. Never: a new instruction section, a deleted output key, a changed output value spelling.
- Invariants checked dry on every round (free): every parser gate read off the raw template is unchanged
  (`parser.resolve_config`: closed_lists / lookup_lists / code_lookup gate_on, chat-state HEADING, TEMPLATE_MARKER,
  "compare_to", "by_words", SALES_CHANNELS_LINE, `extract_tokens`; `chatbot_prompt_vars.py:941` "CUSTOMER ACCOUNT NUMBER"),
  the `<<<CHATBOT POLICY BLOCKS>>>` region byte-identical (L1720-1751 of v185, ~3.7k chars: it is re-rendered from the
  domain / entity-kind / spec tables at publish, `chatbot_prompt_vars.py:918-925`, so an edit there would be lost and drift
  from the tables), every `== ... ==` heading line kept, the SALES-TARGET-CHAT anchor
  `== SALES REPORT: order_status "sales_report", domain_hint "order" ==` kept exactly once, every OUTPUT key kept.

## Rounds (each: one coherent edit set ~8-12k chars, dry identity checks, then the paid gate)
- Harness: copy of the CHAT-SLIM-INDEX phase-1 lookup harness (crew/state/eval/slim-index/phase1, `P1_ARM_B=lookup`,
  real `engine._lookup_lines`, date pinned) in crew/state/eval/prompt-diet; B text = round edits on the list-free text.
- Gate: R5 62 x3, TRAIN 118 x3 (x2 if the cap needs it), category set 196 x1, hard rows. Arm A = previous accepted text
  (round 0 = v185 itself, paid once: no paid rows exist on 3f1e2d27, the final CHAT-SLIM-INDEX check ran on c10a9a6f).
- Bar: B majority >= A on R5 end-to-end (or5-c-02 / c-04 / 5-03 counted per RANK-REFINE-ROUTE #1863) and on TRAIN; hard
  rows majority-right ("dealer only" -> sales_channel dealer; "srt a3 flyer" -> promotion_kind a3_flyer); wrong-category
  messages at most A + 1. Early stop on a missed bar, then shrink the round or drop the edit that caused it (targeted rows).
- Spend: OpenAI dev eval key (..bG4A, gpt-5.4-mini) only, never the Gemini org key; cap USD 5 per round, USD 30 total;
  LEDGER at crew/state/eval/prompt-diet/LEDGER.md.
- Planned order (largest, least ranking-coupled first; ranking sections get their own round so R5 flips are attributable):
  R1 escalation + policy blocks, decisive domain terms, requested attributes, message type, entity confidence/operations.
  R2 broaden axis, open question + numbered answers, company-name reply, specification entity, low stock filters.
  R3 order_status / outstanding / document / date / routing / positional / output comment strings.
  R4 sales ranking, top selling (+ narrowing, answering), sales report / channel / analysis.
  R5 whatever remains to pass 90k.

## Ship
- `chatbot_prompt_diet_edits.py` (accepted round edits) + `diet_0001` migration + red-first tests (tester first):
  every anchor once on the list-free fixture, apply twice is None, size of apply(list-free) under 90,000 on the pinned text
  (crew-only check; the repo test uses a fixture), gates unchanged, SALES REPORT anchor kept once, SALES-TARGET insert
  still applies after the diet. Migration test like `tests/test_lkp_0001_migration.py`.
- Crew SQL `crew/state/migrations/PROMPT-RULES-DIET.sql` (INSERT the accepted version only, never alembic_version).
- PR (crew-lane: PROMPT-RULES-DIET), reviewer, owner hand test on a crew copy (crew moves the copy label for the window).
  The prod label moves only by the owner after release. No customer data in the repo: placeholders.

## Round log (crew eval, gpt-5.4-mini, dev key ..bG4A; rows + LEDGER in crew/state/eval/prompt-diet)
| round | sections | chars after | R5 e2e maj B vs A | TRAIN maj B vs A | hard rows B | cat wrong msgs B vs A | USD | verdict |
|---|---|---|---|---|---|---|---|---|
| 0 (A = v185) | none | 129,651 | 22/22/23 per run | 95/93/96 per run | dealer 3/3, a3 3/3 | 22 | 3.73 | baseline |
| 1 | escalation, decisive terms, requested attrs, message type, entity conf/ops, superseded dups | 120,208 | 22 vs 22 | 97 vs 96 | 3/3, 3/3 | 20 vs 22 | 3.62 | PASS |
| 2 (r02) | continuations, broaden, numbered answers, open question, spec entity, low stock | 114,053 | 20 vs 22 | - | - | - | 0.83 | EARLY STOP (or5-c-03, or5-m-03 -> top_selling) |
| 2b (r02 minus numbered answers) | | 114,876 | ok | 93 vs 97 | | | 2.55 | EARLY STOP (spec asks -> intent attachments) |
| 2c (2b minus open question + spec) | | 115,794 | 21 vs 22 | - | | | 0.55 | EARLY STOP (coin-flip rows) |
Crew a83045112 (b): from here A = v185 fixed, the rest gated in two steps (S1 = r01..r04, S2 = full chain), one retry.
| S1 (r01, r02c, r03a, r03b, r04) | + order / output / PO / quantity / access; ranking set | 100,080 | 20 vs 22 | - | | | 0.53 | EARLY STOP (or5-5-01, or5-c-01) |
| diags (7 variants, 3-6 rows x3) | | | | | | | 0.62 | or5-5-01 <- NARROWING A TOP SELLING ASK edit; top_selling flips <- ORDER_STATUS FILTER / TOPIC RESET / OUTPUT / GROUP_BY / TOP_N group |
| S1 retry s1c (r01, r02c, r03c, r03b, r04b) | both culprits dropped | 102,402 | 22 vs 22 | 95 vs 96 (per-run means 94.67 = 94.67) | 3/3, 3/3 | not run | 2.52 | EARLY STOP by one TRAIN item; decision with crew |
Full chain on the s1c base (r05d, r06c, r07): 91,663, not gated; the last ~4k sits in the sections the diags tied to flips.

## Trigger to stop early
A round that cannot pass the bar after one shrink: stop, report the accepted size and the section that resists.
