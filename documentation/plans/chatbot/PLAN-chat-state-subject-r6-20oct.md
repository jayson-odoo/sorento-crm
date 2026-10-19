# PLAN: CHAT-STATE round 6 - one typed Subject between parse and tools (F2 / M2)

**Status:** Build, S1 next. Track: L (cross-cutting; company scope + hidden keys move to one boundary, so
security-reviewer joins). LEAD pattern. Branch `crew/chat-state-r2`, PR #1772. Approved: crew a29999356 (20 Oct).
**UAC:** `chat-state-subject-r6-acceptance-criteria.md` (alongside). **Source:** crew/state/reports/
CHAT-ARCH-REVIEW-20oct.md section 2 F2 (M2); owner rule 20 Oct 00:55 (ARCHITECTURE section on every plan).

## Goal
`turn/chat_state.apply_changes` becomes the single writer of a typed Subject; every tool call on a state-led turn takes
the Subject; an unresolved Subject asks instead of fetching. Held-family, scheme-index and class decisions read the
State ops. All legacy text rewriters stand down on the state path. One `UserTurn` contract at ingress replaces the
seven first-line reads. State-off stays byte-identical.

## ARCHITECTURE
1. Layer: code between parse and tools (State applier -> Subject -> fetch / gate), plus the ingress contract. The prompt
   is not touched (head/chat_state_prompt.py now belongs to CHAT-CODE-LOOKUP).
2. Shared mechanism: a typed `Subject` in turn/state.py: `source` (ids / predicate over a scope / unresolved), explicit
   product ids or a predicate (brand / class / spec / family), company scope + hidden keys, provenance per axis
   (held / said / offer). Written only by apply_changes; one State-to-fetch function maps it to tool arguments.
3. Also fixes: F1 (setting one axis keeps the held others; the 10 xfail(strict) tests in
   tests/chatbot/test_chat_state_r5_set_axis_keeps_held.py are the red set), TYPE-ONLY-EMPTY-SET, #1755 R6-3 / R6-4
   semantics (moved here by crew), held-family narrowing on the state path, R4-A offer picks, R3-A held quantity,
   unscoped fetches (fetch.py:665-675, gate.py:172).
4. Removes on the state path: with_carried_entities' "names nothing" rule (turn_runtime.py ~4921), carry_onto_family,
   narrow_held_to_brands + with_brand_from_offer, the brand-as-string duplicate, names_own_class at task.py:735 /
   scheme_index.py:35 / held_family.py:152 / engine.py:4986, with_set_count_from_text / with_company_pick /
   with_new_set_words / the stock-ask regex, decide.py's refine-of-standing-subject branch, reconcile.py:110-121, and
   every `split("\n", 1)[0]` (moved into UserTurn). Each item is ported to an op semantic or deleted, with a test pin.

## Slices (each: tester red -> coder -> lead kill-proof -> reviewer; L1 gate per slice; ONE push at round end)
- S1 Subject type, written by apply_changes; no behaviour change; the trace shadow-logs the Subject beside today's
  fetch input.
- S2 State-to-fetch: the fetch on a state-led turn reads the Subject; the carry patches retire there; the F1 xfail(strict)
  marks come off.
- S3 held-family / scheme-index / class decisions read the ops; names_own_class deleted at its four seams.
- S4 an unresolved Subject asks (no unscoped fetch on the state path).
- S5 the port-or-delete list of legacy rewriters, each pinned.
- S6 UserTurn at ingress (own_text, quoted_text, media reads), used by both the webhook path and #1766's direct-ingress
  path; value-identical off the state path.

## Dependencies and budget
- Applier input today also reads entities, open_question_answer.mode, demand_qty and message domains besides
  state_changes (turn/chat_state.py:654-972). An op `value` field (CHAT-CODE-LOOKUP's prompt + schema, this lane's
  applier) is agreed through crew before either side builds it. Until then the applier keeps reading entities.
- Measurement: L1 replay gate per slice (base = the slice's parent); one paired TRAIN x1 at round end, cap 0.3 USD;
  combined4 is crew's.
- Lessons carried: fixtures carry the real data shape; never revert app files while a gate or live run reads the tree;
  a harness must prove the state path ran (apply_changes counter).
