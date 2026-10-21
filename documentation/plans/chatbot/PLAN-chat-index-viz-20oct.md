# PLAN: Chatbot console "Index match" view (CHAT-INDEX-VIZ)

Status: Review READY (Opus reviewer, round 2 + nit); browser pass round 2 PASS 1280 + 375; awaiting owner hand test. Track: M, LEAD pattern.

Owner ask (21 Oct): see, for one console turn, how the closed-list index connects to the parser:
message tokens -> matched index entries (with source table/row/synonym) -> lines injected into the
parser input -> parser output -> grounding kept/dropped -> tool call.

Artifacts (step 1 + 2 of the LEAD pattern):
- Behaviour card: `chat-index-viz-20oct-behaviour-card.md` (what the view shows, 5 example turns,
  edge cases, new trace fields, 5 questions with recommendations).
- Mockup: `chat-index-viz-20oct-mock.html` (static, app tokens, purple labels map each element to
  the component it reuses).

Build (after owner approval only), expected slices:
1. BE: `closed_lists_index.block` and `candidates` return provenance beside the lines; engine
   `_candidate_lines` adds a `closed_lists_index` trace event; `compose_trace_detail` maps it plus
   the existing `grounding` event (`index_match`, `grounding` keys). pytest first.
2. FE: `IndexMatchSection` in `chat-history/components/TurnDetailDrawer.tsx` after Parse, types in
   `chatbotTurn.types.ts`. vitest first; agent-browser pass at 375 + 1280.
No migration (trace is JSONB). Depends on index mode reaching main (explore build c899b3ec5d today).
