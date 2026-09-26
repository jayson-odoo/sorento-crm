# PLAN - Ideation chat reply format (issue #1277)

**Status:** in progress (branch `fix/ideation-chat-reply-format`). Track: small fix, with one
data-only migration (publishes two prompt versions, no schema change); no auth/RBAC change, no
new external ingest surface.
**UAC:** `ideation-chat-reply-format-acceptance-criteria.md` (alongside).
**Evidence:** the owner's console test of 26 Sep 2026 quoted in #1277 (prompt v27).
**Rulings in force:** everything in `PLAN-ideation-intake-redesign-24sep.md` (R1 to R18) except
where #1277 amends it: R10 as amended by R16 put the title on line 1 of every recap; #1277 finding
3 drops it from the recaps and keeps it only in the final (`complete`) message. That amendment is
ASSUMED (the issue says "ruling assumed unless the owner overrules") and is flagged in the PR.

## What is wrong today (verified)

1. Labels are plain. `_ideate_reply_fallback` tells the model `'Problem: ...'`, and the
   shared-service template fallback is plain too. Nothing in sorento bolds them.
2. The Problem value is the user's raw words. `_ideate_extractor_fallback` never asks for a clean
   statement, and the context block the extractor reads joins the captured fields with `"; "`
   (`ideation_extractor.py`, `captured_lines = "; ".join(...)`), which is the same glue the owner
   saw inside the Problem line.
3. The recap's line 1 is the quoted title (R10/R16 as written), so it shows on every recap with no
   label.
4. The media offer is text only: `build_menu_text` lists file names; nothing sends the images.

## Design (the simplest thing that covers both reply paths)

- **W1 + W3, one deterministic pass.** `compose_ideate_reply` runs every reply, the LLM's or the
  shared-service template it falls back to, through `_format_ideate_reply(text, facts)`:
  - a line whose label (ignoring `*`, `_` and spaces around it) is `Problem`, `Solution`,
    `Impact` or `Department` followed by `:` is rewritten `*Label:* value` (idempotent);
  - for every status except `complete`, a line that is only the draft title (quotes, `*` and an
    optional `Title:` prefix ignored, case and spacing ignored) is dropped. `complete` keeps the
    title on line 1 with the idea number and the link. `duplicate_candidate`'s
    `Similar idea exists: <candidate title>` line is not the draft title and stays.
  - `_passes_reply_checks` reads a field line through the same label parser, so a composed reply
    that already bolds its labels is accepted instead of falling back.
  - `_ideate_reply_fallback` is reworded to match (bold labels, no title line in a recap).
- **W2, prompt only.** `_ideate_extractor_fallback` gains a CLEAN VALUES rule for problem,
  proposed_solution and impact (strip conversational preamble such as "i have an idea", "i think
  the problem is", "i guess"; correct spelling; when extending, rewrite the old value and the new
  detail as one readable sentence, never a semicolon join; keep the user's meaning, add nothing).
  The captured context is listed one field per line instead of `"; "`-joined. `raw_text` is
  untouched: `raw_transcript` is still the user's own words, turn by turn.
- **Prompt versions.** Migration `ideation_reply_fmt_prompts` calls `seed_prompt_registry` then
  `bump_prompt_to_fallback` for `ideate_extractor` and `ideate_reply` (the 272 precedent for an
  ideation prompt): each publishes the new text as the next version and moves `production` to it,
  a no-op when production already carries it.
- **W4, the existing outbound media path.** `handle_turn` returns `offered_media`
  (`[{position, kind, url, filename}]`, the menu's own numbering) on the turn that builds a media
  menu, `[]` otherwise; `IdeationTurnResponse` declares it (response_model drops undeclared
  fields). The ideate lane (`lanes/ideate.py::run`) turns the images among them into
  `reply_extras["attachments_src"]`, one entry per image, `{url, filename, mimeType,
  attachmentType: "image", caption: "<position>"}`, `None` when there are none. The engine's
  existing `_send_actions` already emits `send_attachments` after `send_message` (flagged
  `dry_run` on a console turn) and n8n's `sub-send-attachments` does the Respond.io send. No new
  mechanism.
  - 24h window: same rule as every other chatbot `send_attachments`: the reply answers an inbound
    message that just arrived, so the window is open by construction; the CRM does not send on
    the turn path (D9).
  - Console: `TurnAttachments` shows an image entry as a thumbnail with its caption; bot bubbles
    render WhatsApp `*bold*` as bold (`components/chatbot/WhatsAppText.tsx`).

## Not in this change

- n8n's `sub-send-attachments` lives outside this repo. Whether it forwards the entry's
  `caption` to Respond.io's `attachment.caption` cannot be checked here; flagged in the PR.
  Trigger to change n8n: the first live turn whose images arrive without their number.
- Videos, audio and files in the menu are still listed only; the issue asks for images.

## Tests

Tester first (red), then the fix (green), each kill-tested:

- W1, W3: `tests/test_ideation_reply.py` and `tests/test_ideation_turn.py` (turn harness, stubbed
  create_idea and provider).
- W2: `tests/test_ideation_extractor.py` (prompt carries the rule; context one field per line) +
  `scripts/replay_ideate_extractor.py` (live replay of the #1277 transcript, needs an LLM key).
- W4: `tests/test_ideation_turn.py` (`offered_media`), `tests/chatbot/test_ideation_offered_media.py`
  (engine `run_turn` with the tool stubbed: actions, captions, dry run), vitest for
  `TurnAttachments` and `WhatsAppText`.
