# PLAN: PROMPT-DIET-V66 (the PROMPT-RULES-DIET edits on the production v66 parser text)

Status: Build (crew brief PROMPT-DIET-V66, size S, small fix track: under 300 lines, no migration, no schema, no
auth/RBAC, no ingest surface). Follow-up of #1867.

## Scope change (owner via crew, 26 Oct ~21:55)
The owner pastes the diet text into prod himself as a new version, so the deliverable is the TEXT
(`crew/state/outbox/diet-v66/diet_v66.txt` + md5 + char count + change summary) and the gate result. NO new migration:
step 2 of the fix below is dropped. The edit-list change stays as a small PR so the text is reproducible from the repo.

## Why
`diet_0001_parser_prompt_diet` (#1867, deployed 26 Oct 17:01) skipped on prod: the production label of
`chatbot_semantic_parser` there is v66 (129,639 chars, md5 fb7b4283), and v66 does not take the edits.

## Measured (dry run of `chatbot_prompt_diet_edits.build` on the exact v66 text, 26 Oct)
- v66 already carries the `== LOOKUP LISTS ==` line, so `build` goes straight to `apply` (no list-free step).
- 112 edits; 111 find their anchor once. ONE misses: edit #36 (`chatbot_prompt_diet_edits.py:96`, the ENTITY
  CONFIDENCE + ENTITY OPERATIONS block), found 0 times.
- v66 vs v185 (= prod v65, the diet's measured base, 129,651 chars, md5 3f1e2d27): exactly 3 lines differ (v185 lines
  427, 434, 435), each the owner's removal of `one ` before `<customer name>` (3 x 4 = 12 chars). All three sit inside
  edit #36's anchor. Nothing else differs.

## Fix
1. `chatbot_prompt_diet_edits.py`: split edit #36 into three anchored edits whose anchors stop right before, and start
   right after, the `one ` token, so the token (present on v65, absent on v66) is carried through untouched. Same
   payload text: on the v185 base the output is byte-identical to today (md5 94fccf45, 102,402 chars); on v66 it keeps
   the owner's edit (no `one `). No new rule, no wording change beyond #1867's.
2. DROPPED (scope change): new migration `diet_0002_parser_diet_v66` (down_revision = main's single head `bca_0001_brand_dealer_company`): the
   diet_0001 publish logic with its own message. Builds the diet text from the production-labelled version, inserts it
   UNLABELLED, never moves a label, logs a warning and publishes nothing when the base does not take the edits.
   - prod (label on v66): publishes the v66 diet text as the next version.
   - dev (label on v63): `build(v63)` gives the same text diet_0001 already published, so it logs "already published"
     and inserts nothing (both bases handled; no duplicate).
3. Tests, red first: `tests/chatbot/test_prompt_diet_v66.py` (the confidence block in its v65 and v66 shapes takes
   the real edits; the v65 output is unchanged).
4. Side effect, stated: `diet_0001` now also takes a v66 base, but only on a DB whose alembic is still before it; prod
   is already past diet_0001, so nothing publishes there from this PR.

## Proof owed (PR body)
md5 + length of the diet text built from v66; section diff summary vs v66; md5 of the v185 build unchanged.

## Eval
Parser-level gold gate, arm A = v66 (md5 fb7b4283), arm B = the v66 diet text, crew harness
`crew/state/eval/prompt-diet`. Spend cap USD 3, estimate reported before the run, no hidden-set run without crew OK.

## Not in scope
No new edits, no re-measure of the other 111 edits (they apply unchanged), no label move (promotion stays one label move
in the Chatbot Console).
