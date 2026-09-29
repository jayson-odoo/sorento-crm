# UAC: ideation testable on test turns

Plan: `PLAN-ideation-is-test-turns.md`. Issue #1179, sorento side. All ACs are pytest; no
live run.

## handle_turn payload (`tests/test_ideation_turn.py`, `wired` fixture)

- **AC-1 [BE][T] test turn carries `is_test: true`.** Given a configured workspace and a
  stubbed `create_idea`, when `handle_turn(..., is_test=True)` runs, then the create-idea
  payload has `is_test is True`.
- **AC-2 [BE][T] live turn carries `is_test: false`.** Given the same, when `handle_turn`
  runs without `is_test` (the default), then the payload has `is_test is False` (the key is
  present, not omitted).
- **AC-3 [BE][T] a test turn never persists the pointer.** Given a `collecting` reply from
  `create_idea`, when `handle_turn(..., is_test=True)` runs, then `overwrite_for_contact` is
  not called, the contact's stored `session_vars` is unchanged, and the returned
  `session_vars.ideation` still carries the new `draft_id` (the caller carries it).
- **AC-4 [BE][T] the endpoint forwards the flag.** Given `POST /api/v1/external/ideation/turn`
  with `is_test: true`, then `handle_turn` receives `is_test=True`; a body without the field
  gives `is_test=False`.

## Ideate lane (`tests/chatbot/test_s3_canned_and_ideate.py`)

- **AC-5 [BE][T] a dry run calls the tool as a test turn.** Given an `is_test` envelope
  routed to `ideate` with the tool seam recording its calls, when `run_turn` runs, then the
  seam was called exactly once and the call carries `is_test is True`, plus the same
  arguments a live turn sends.
- **AC-6 [BE][T] a live turn calls the tool with `is_test: false`.** Existing
  `test_ideate_branch_calls_mcp_tool` also asserts `is_test is False` on the call.
- **AC-7 [BE][T] the action carries the tool's real reply, no placeholder.** Given AC-5,
  then `result.reply["text"]` equals the tool's `reply_text`, `result.actions` is exactly
  one `send_message` with that text and `dry_run: True`, and the action has NO `preview`
  key. `PREVIEW_IDEATE_REPLY` no longer exists in `contracts`.
- **AC-8 [BE][T] the rest of the dry run stays a dry run.** Given AC-5, then
  `respond_contacts.session_vars` is unchanged before/after, `result.session_patch` is
  present, `result.is_test` is True, and every action carries `dry_run: True`.

## MCP tool (`sorento_crm_mcp/tests/test_ideation_tool.py`)

- **AC-9 [BE][T] `is_test` travels as a boolean** when passed, and is omitted from the body
  (never null) when not passed.

## Docs

- **AC-10 [T]** `PLAN-ideation-capture-n8n.md` section 1 request body and
  `PLAN-ideation-ideate-intent.md` section 4 (the section 5.1 snapshot) each name `is_test`.
