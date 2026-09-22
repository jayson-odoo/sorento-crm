# PLAN: conversation SLA ticket keeps assignee, agent, team set code and message after resolve

Status: small fix track, review READY after fix round 1, awaiting PR (lane `fix/sla-keep-assignee-on-resolve`, worktree `sorento_crm-sla-keep-assignee`)
UAC: `keep-assignee-on-resolve-22sep-acceptance-criteria.md`
Owner ruling (22 Sep 2026, R5): keep the fields for audit; resolved tickets must not reappear in My Pending / My Team / inbox tabs.

## Journey

Manager opens a resolved Conversation SLA Tracking record. Today Assigned To, Agent Code, Team Set Code and Message all read `-`. After: they show the values the ticket had when it was resolved, as Form-SLA rows already do.

## Defect (`sorento_crm_backend/`)

`app/services/sla_service.py` `ConversationSLATrackingService.update_tracking`:

- `:4760-4776` on resolve of a non-form tracker sets `assigned_to`, `assigned_to_id`, `agent_id`, `team_set_code`, `message_id` to None.
- `:4831-4845` raw-SQL `update(...).values(message_id=None, team_set_code=None, agent_id=None)` re-nulls three of them after commit.

Both blocks go together. `agent_code` in the response derives from `agent_id` (`app/schemas/sla.py:634-636`), so keeping `agent_id` restores it.

## Why it is safe (measured)

Every live worklist gates on `is_resolved` independently of the assignee: `list_my_pending` `sla_service.py:1280-1284` and `list_team_pending` `:1571-1577` via `open_tracker_scope()` (`sla_scope.py:26-35`); inbox Mine/Unassigned `conversation_inbox_service.py:110-125`; WhatsApp daily summary `user_sla_daily_summary_service.py:87-96`. `get_dashboard_metrics` never filters by assignee. KPI leaderboard (`sla_kpi_service.py:266-284`) currently under-counts resolved conversation tickets because of the null; keeping the field corrects it. `can_user_act_on_tracking` (`sla_service.py:1443-1465`) keeps its `resolved_by` fallback; the comment at `:1454-1457` becomes stale and is reworded.

Fix round 1: the audit above missed `/external/next-assignee` (`_tracking_is_assigned` read `assigned_to_id` with no `is_resolved` gate, so a returning contact's resolved ticket read as already assigned and the escalation lane skipped `assign_conversation`); gated on `is_resolved`, AC-KA-11/12. Same shape still exists at `GET /external/conversation-sla-tracking` (returns `is_resolved`, n8n must gate; confirm with n8n owner).

## Fix

1. Remove the five `update_data[...] = None` lines and the `close_team_label` lookup if it only served them (check its other uses first). Keep the form-tracker branch structure if anything else lives in it.
2. Remove the raw-SQL re-null block at `:4831-4845`.
3. Reword comments: `sla_service.py:4759-4763`, `:1454-1457`; model comments `app/models/sla.py:130`, `:137` ("cleared on resolve"); schema comment `app/schemas/sla.py:118`.
4. Reopen (`is_resolved=False` path, `tests/test_conversation_sla_reopen_override.py`): nothing to restore now; assert fields survive a resolve → reopen round trip.

## Tests (write first)

Flip the four that assert the null as correct: `tests/test_conversation_sla_list_history_filters.py:197-213`, `tests/test_ticket_thread_read_scope.py:306-329`, `tests/test_conversation_ticket_integration_response.py:120-156`, `tests/test_conversation_multi_open_consumer_audit.py:395-420`. Add AC-KA-1..7 below. Run the SLA test family touched: `pytest tests/test_conversation_sla_*.py tests/test_ticket_*.py tests/test_sla_*.py tests/test_conversation_ticket_*.py tests/test_conversation_multi_open_consumer_audit.py tests/test_conversation_inbox*.py -q` against the private DB.

## Known follow-ups

- S4: FE `slaHandler.ts` "Resolved by" swap - pending owner ruling, not applied in this lane.
- S5: the KPI leaderboard now counts resolved conversation tickets per assignee (previously under-counted, see "Why it is safe" above). Rows resolved before this deploy stay NULL on `assigned_to_id` / `agent_id` / `team_set_code` / `message_id` forever - no backfill is possible, since the pre-fix resolve genuinely discarded that data rather than merely hiding it.

## Out of scope

Frontend (renders whatever the API returns; no change). Chat panel layout and chatbot routing are separate lanes.
