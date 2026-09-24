# PLAN: ideation testable on test turns (`is_test` through the real intake)

Status: small fix track, PR open (#1182)
Plan created: 2026-09-24T09:40:00Z
Domain: chatbot / ideation
Issue: #1179 (sorento side only; the shared-service side is a separate lane)
UAC: `ideation-is-test-turns-acceptance-criteria.md`

## Problem (measured against origin/main 028083e2)

The chatbot console and `chatbot_console_check.py --say` mark every turn `is_test`, and the
engine hands that flag to the ideate lane as `dry_run`. One line decides what the lane does
with it, `app/services/chatbot/lanes/ideate.py:184`:

```
result = preview_result(ctx) if dry_run else call_ideation_tool(**build_arguments(ctx))
```

On a test turn the tool is never called and the reply is the fixed placeholder
`PREVIEW_IDEATE_REPLY` ("[dry-run: ideation reply not generated]"), with `preview: true` on
the `send_message` action. D14 chose that because `crm_ideation_turn` mints a real idea row
in the shared service. Result: ideation cannot be exercised anywhere except live WhatsApp.

The payload chain the flag has to travel is already one straight line with no branching:
lane `call_ideation_tool` (MCP JSON-RPC) -> MCP tool `crm_ideation_turn`
(`sorento_crm_mcp/sorento_crm_mcp/ideation.py`) -> `POST /api/v1/external/ideation/turn`
(`IdeationTurnRequest`) -> `ideation_turn_service.handle_turn` -> `call_create_idea` ->
shared service `/ideation/intake/create-idea`. None of those hops carries `is_test` today.

## Fix (one seam, the flag rides the existing chain)

- **Lane** (`lanes/ideate.py`): a dry run calls the real tool, with `is_test=dry_run` beside
  `build_arguments(ctx)`. `preview_result` and the `preview` flag on the action go away:
  the reply text is the tool's own words on both kinds of turn, so nothing is stood in.
  `PREVIEW_IDEATE_REPLY` is deleted from `contracts.py` (dead). Everything else about the
  dry run is unchanged: `dry_run: true` on the action, no session write by the tail, the
  would-be `session_patch` returned (which is how the console carries the draft pointer
  between `--say` turns).
- **Engine** (`engine.py` `_complete_canned_lane`): drops the ideate-only `preview`
  plumbing; `_send_actions` keeps its `preview` parameter for the escalation lane.
- **MCP tool** (`sorento_crm_mcp/ideation.py`): optional `is_test: bool | None`, forwarded
  when set, omitted otherwise, like the other optionals. Catalog description gains the
  clause.
- **Endpoint** (`schemas/external/ideation.py`, `api/v1/external/ideation.py`):
  `is_test: bool = False` on `IdeationTurnRequest`, passed into `handle_turn`.
- **Service** (`ideation_turn_service.handle_turn`): `is_test: bool = False`; the create-idea
  payload always carries `"is_test": <bool>` (true on a test turn, false on a live turn). On
  a test turn the contact's `respond_contacts.session_vars` is NOT written: the updated blob
  is still returned for the caller to carry, but the DB copy stays as it was. Without that
  guard a test draft pointer written to the real contact row would be picked up by the
  contact's next LIVE turn through the endpoint's DB fallback (`handle_turn` reads
  `session_vars.ideation` from the row when the caller sends no pointer), which is exactly
  the cross-contamination D14 exists to prevent.

Not changed: the endpoint's `integration_log` row (an audit record; its payload now shows
`is_test`), the media lookback (a read), and the media snapshot on a selection turn.

## Chatbot rules honoured

General fix, not one scenario: every dry-run ideate turn goes through the real tool. The
head still honours the parser verdict (the lane is entered only when the parser routes
`ideate`); the flag is set after the parse, deterministically, from the envelope's
`is_test`. No keyword shortcut. pytest only, no live run.

## Files

- `sorento_crm_backend/app/services/chatbot/lanes/ideate.py`
- `sorento_crm_backend/app/services/chatbot/engine.py`
- `sorento_crm_backend/app/services/chatbot/contracts.py`
- `sorento_crm_backend/app/schemas/external/ideation.py`
- `sorento_crm_backend/app/api/v1/external/ideation.py`
- `sorento_crm_backend/app/services/ideation_turn_service.py`
- `sorento_crm_mcp/sorento_crm_mcp/ideation.py`, `catalog.py`
- tests: `tests/test_ideation_turn.py`, `tests/chatbot/test_s3_canned_and_ideate.py`,
  `sorento_crm_mcp/tests/test_ideation_tool.py`
- docs: `documentation/plans/ideation/PLAN-ideation-capture-n8n.md` section 1 (endpoint
  body), `PLAN-ideation-ideate-intent.md` section 4 (the section 5.1 create-idea snapshot)

## Track

Small fix track (PRINCIPLES.md): under 300 changed lines, no migration, no auth/RBAC change,
no new external ingest surface (one optional boolean on an existing external body). Tests
first, then the fix, one reviewer, no browser pass (no screen changed).
`security-reviewer`: not run, diff outside its surface.
