# PLAN: multi-turn carry for report asks (2 Nov 2026)

**Status:** Build. Crew ruled Q1-Q3 (a) on 2 Nov from the owner's 14 turns. Track: full (M, chatbot
behaviour, LEAD pattern). Branch `crew/sales-account-type-carry` from main 55875e05ac. No migration, no route change.

## Why

Owner, #2074 hand test, 2 Nov: "it can get the answer I want but it kind of cannot survive multi turn". In a 14-turn
conversation (agent, account type, period, company, basis, breakdown named one at a time), turns 6 to 14 dropped slots set
earlier or asked again for them.

## Causes (read from the turn traces at 4b206b7407)

1. The held frame only carries when the parser marks the follow-up `modify` / `reuse` or a customer is held
   (`report_ask.py` `_follows_up` ~1247-1253, `with_held` ~1294, a ranking frame refused ~1297). A `replace_combine` follow-up
   ("for sales agent agent b") is a fresh ask: `_settle` keeps no filters (~2232), no basis or measure (~2276), no period
   (~2349) and no company, so it asks again.
2. An answer to an open question that the parser also tags as a report kind, or with a stray entity, replaces the open ask
   (`names_its_own_ask` ~830-834, `engine.py` ~6120-6123), and `with_held` refuses the ranking frame before reading it.
3. A company pick the parser declared itself is not counted as the company pick (`engine.py` ~6113).
4. A type word drops the held company (`_settle` ~2255-2257, AT-35 rule of #2074).

## Rules (crew ruling 2 Nov: Q1 a, Q2 a, Q3 a)

- R1 Every sales / outstanding follow-up starts from the held frame (the open question's ask, else the last answer), whatever
  the entity_op, until the parser marks a new topic, another report kind is asked, or the frame is stale.
- R2 A follow-up that names a slot changes only that slot (agent, account type, brand, category, customer, product, period,
  company, basis, breakdown); "all X" widens it (#2070, unchanged).
- R3 A slot set earlier in the conversation is never asked again: basis, period, company, brand-or-account when the user
  said which.
- R4 An answer fills its question's slot and keeps the rest of the open ask.
- Q1 A follow-up naming a new agent, type or brand keeps the held company when that subject exists in it; it drops the
  company (and asks) only when the subject exists only in the other company. Replaces #2070 Fix 6 and #2074's AT-35 type-word rule.
- Q2 A slot named again replaces it ("for sales agent agent b" after AGENT A is AGENT B alone).
- Q3 The carry ends on another report kind, a reset the parser marks, or the existing stale-frame rule.

## ARCHITECTURE

1. **Layer.** Report ask lane only (`lanes/business/report_ask.py` `with_held` / `_settle` / `_refine`), plus the engine
   seam that decides an answer is a new ask. No parser prompt change, no route change.
2. **Shared mechanism.** ONE held frame and ONE merge: the follow-up's own args over the held args, slot by slot. `_settle`
   and `_refine` both read it. The stamp stops depending on entity_op.
3. **Classes fixed.** Every slot (not one shape): filters, period, basis, measure, company, breakdown; every follow-up kind
   (fresh-looking, refine, answer to an open question).
4. **Removes.** The entity_op gate in `_follows_up` for sales frames; the ranking-frame refusal in `with_held`.
5. **Not built.** No word list, no new question type, no prompt edit.

## Owner rulings checked

Basis ask 27 Oct (kept: only a conversation's first ask asks it; a carried basis is the user's own and the header names it).
Outstanding summary 29 Oct (kept). #2070 held customer + step 19 (kept). Conflict: #2070 Fix 6 company rule, resolved by Q1.

## Tests

Red first, from the owner's 14 turns as a scripted lane conversation (fake parser verdicts copied from the traces, fake
route), one assertion per turn; plus the #2070 and #2074 suites unchanged. Console pass of the 14 turns on a copy after.
