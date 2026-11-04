# PLAN: chatbot totals vs top-N, company vs brand, clearing a held filter, combined turn (4 Nov 2026)

Status: Plan (M track, LEAD pattern). Replay done; root-cause note and behaviour card next. No code before the
owner answers the card.

## Journey

A staff user asks the sales chatbot (Chatbot Console, staff contact) for sales totals and then refines them over
several turns: narrow to a company, split by channel, drop a filter. Owner test, 4 Nov ~09:20 MYT, prod console,
contact Mr Loo, parser prompt v70.

Failures reported (owner's words in the lane brief):
- F1 a TOTAL ask was treated as a RANKING ask ("How many? For example top 5" / "By quantity or by amount?").
- F2 "sorento company only" held BOTH Company: Sorento and Brand: SORENTO.
- F3 the held brand could not be cleared ("all brands", "brand is all brand"); "clear the brand filter" dropped
  everything and re-asked basis + period.
- F4 "sorento company only, show dealer and project" applied the filter but not the breakdown.
- F5 a fresh full question kept Company + Brand from earlier turns (brand should never have been added, F2).

## Replay (baseline, origin/main 240d6e8679; prod runs 24189427cb, same chatbot code)

Copy :8102 on sorento_prod_1020, parser pinned to version id 2247a9af (md5 57d7d412 = prod v70 per crew record),
contact Mr Loo with the agent switch off for the run (prod console replies were bot-path). Raw traces:
`crew/state/files/chatbot-trace-4nov/replay/baseline.jsonl` (crew state only; real names stay out of the repo).

Findings so far (x1, gemini-3.5-flash-lite):
- F2 reproduced: C4 "sorento company only, show dealer and project" -> Company: Sorento AND Brand: SORENTO.
- F4 reproduced: C4 kept the held channel split but added the brand; the split itself survived here.
- Carry loss not in the owner's list: B3 / E3 ("break down project and retail", "top 10 products") dropped the held
  period and basis and re-asked them; C3 (same text, same state as B3) kept them. Parser variance on one input.
- F1 not reproduced x1 on a clean thread (A1, E4 gave a total). The ranking asks fire when the verdict carries a
  ranking frame; root cause is in which field decides that (see root-cause note).

## Root-cause note

(next: file:line per failure)

## Behaviour card

(filed as one crew --ask before any code)

## Architecture

(after the card: layer, mechanism, classes)

## Tickets / tests

(after the card)
