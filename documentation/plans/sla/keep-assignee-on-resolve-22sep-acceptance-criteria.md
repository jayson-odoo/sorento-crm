# UAC: conversation SLA ticket keeps assignee, agent, team set code and message after resolve

Plan: `PLAN-keep-assignee-on-resolve-22sep.md`

- AC-KA-1 Resolve a conversation tracker (UI route `POST /{id}/resolve`) that has `assigned_to_id`, `agent_id`, `team_set_code`, `message_id` set → after commit and a fresh read, all four are unchanged and `is_resolved` is true.
- AC-KA-2 Same via the n8n route `POST /integration/{id}` with `is_resolved=true` → same result.
- AC-KA-3 Detail response `GET /api/v1/sla-management/conversation-sla-tracking/{id}` for the resolved row carries non-null `assigned_to_id`, `agent_code`, `team_set_code`, `message_id`.
- AC-KA-4 `list_my_pending(user_id=<assignee>)` does NOT return the resolved tracker; it did return it before resolve.
- AC-KA-5 `list_team_pending` for the assignee's team does NOT return the resolved tracker.
- AC-KA-6 Inbox "Mine" tab clause (`conversation_inbox_service._open_conversation_ticket_clause`) excludes the resolved tracker for its assignee.
- AC-KA-7 Resolve then reopen (`is_resolved=False`) → the four fields are still populated and the tracker is back in `list_my_pending`.
- AC-KA-8 Form-SLA tracker resolve behaviour unchanged (existing test `test_form_row_resolve_is_never_gated_by_conversation_siblings` still green, reworded to say both paths now keep the fields).
- AC-KA-9 The resolver can still open the ticket drawer after resolving (`test_the_resolver_still_reads_the_ticket_they_just_resolved` green with the assertion on `assigned_to_id is None` removed).
- AC-KA-10 `list_tracking(is_resolved=True, assigned_to=<assignee>)` now returns the resolved row (history filter; flips `test_resolved_by_narrows_to_one_resolver`).
- AC-KA-11 (fix round 1) A contact whose only conversation tracker is resolved calls `POST /external/next-assignee` → `is_already_assigned` is `false`, `already_assigned` is not in `status_flags`, and a fresh assignee is drawn from round-robin.
- AC-KA-12 (fix round 1) Same contact/route with an OPEN, assigned tracker → `is_already_assigned` is `true` (pins the other direction, so AC-KA-11's fix cannot regress the still-open case).
- AC-KA-13 (fix round 1) `ConversationSLATrackingService.get_existing_assignee_for_contact_phone` returns `None` once the contact's only assigned tracker is resolved (it returned that resolver's info before this fix).
- AC-KA-14 (fix round 1) `POST /{id}/extend/preview` returns 422 "Cannot extend a resolved SLA task." for a resolved tracker, matching the real extend's `is_resolved` gate.
- AC-KA-15 (owner ruling S4, FE) A resolved conversation SLA row shows the ASSIGNEE in "Assigned To" - on the detail page header, the listing cell, and the collapsed tracking-info section - and "Resolved by <resolver>" remains visible in the detail header, alongside it, exactly where it already was.
