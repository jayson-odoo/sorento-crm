# Message push notifications - acceptance criteria

Status: REVIEWED (plan markup applied 2026-08-23)
Plan: `documentation/plans/notifications/PLAN-message-push.md`

## Journey

A salesperson has Sorento added to her phone's home screen and has tapped
"Enable notifications" once, in My Account. Her phone is locked and in her pocket.

A customer she owns sends a WhatsApp message. Within seconds the phone buzzes:

> **Ah Meng (Sorento Kitchen)**
> Can I get the price for the 900mm hood?

She taps it. The phone opens straight to that conversation's ticket page, where the
message is already on screen. She replies from the drawer she already knows.

She made exactly one decision: reply, or not. She was never asked which contact,
which channel, or which notification type - the system knows the contact is assigned
to her, knows her coverage, and knows her scope choice from a single dropdown she set
once. If the customer fires off five more messages while she is walking to her desk,
the same notification updates in place ("Ah Meng - 6 new messages") instead of buzzing
six times. If she already has that thread open on her laptop, her laptop stays silent.

Nobody else is told anything: this is a personal alert, not a workflow event. It writes
no bell entry, sends no email, and changes no SLA clock.

## Scope of this slice

IN: one event (inbound WhatsApp message on a conversation), delivered to web push only,
governed by one per-user scope dropdown.

OUT (backlog): admin-configurable event registry, per-event templates, quiet hours,
mention notifications (`ticket_comments.mentioned_user_ids` exists and is the obvious
second event), call notifications, sound settings, retro-governing the ~40 existing
notification events that already fan out to web push blind.

---

## Phase 1 - frontend, mocked  [FE]

**AC-M1** [FE] Given I am on My Account -> Notification settings, when the page renders,
then a "Message notifications" select appears below the existing Browser Notifications
card, with exactly four options: "Contacts assigned to me and my coverage" (default),
"Contacts assigned to me only", "All contacts", "Off".

**AC-M2** [FE] Given the select renders, when I have not enabled browser push on this
device, then the select is still readable and settable (it is a server-side preference,
independent of this device's subscription), and a hint states that pushes only arrive on
devices where notifications are enabled.

**AC-M3** [FE] Given I change the select, when the save succeeds, then a success toast
shows and the new value survives a reload.

**AC-M4** [FE] Given the save fails, when the error returns, then the select reverts to
its previous value and an error toast shows the extracted API message
(`extractApiError`, never a hand-rolled `.catch(() => ({}))`).

**AC-M5** [FE] Given the browser does not support push at all, when the card renders,
then the existing unsupported copy still shows and the scope select is still offered
(the preference governs every device, not this one).

**AC-M6** [FE] The card renders correctly at 375px and at 1280px with no horizontal
overflow.

## Phase 2 - backend + service worker  [BE] [T]

### Recipient resolution

**AC-M7** [BE] Given an inbound message lands for a contact whose open conversation SLA
tracking is assigned to user A, when recipients are resolved, then A is a recipient if
A's scope is `assigned_only`, `assigned_and_coverage`, or `all_contacts`, and is not a
recipient if A's scope is `off`.

**AC-M8** [BE] Given user B holds an active, unexpired coverage subscription for user A
(`notification_subscriptions.target_user_id = A`, `is_active = true`), when the message
is assigned to A, then B is a recipient if B's scope is `assigned_and_coverage` or
`all_contacts`, and is not a recipient if B's scope is `assigned_only` or `off`.

**AC-M9** [BE] Given user C has scope `all_contacts`, when any inbound message lands -
including on a contact assigned to nobody - then C is a recipient.

**AC-M10** [BE] Given a contact holds SEVERAL open conversation trackings at once
(multi-open is live - `sla_service.py` AC-F1), when a message lands, then EVERY open
tracking's assignee is a recipient, each scoped by their own preference, and each
receives a link to their OWN ticket.

**AC-M10a** [BE] Given one of those tickets is resolved, when a later message lands, then
that ticket's assignee is NOT a recipient while the remaining open tickets' assignees
still are.

**AC-M10b** [BE] Given the contact has NO open tracking at all, or the open trackings
have no assignee, then only `all_contacts` users are recipients; nobody is pushed by
fallback to a team or a tier.

**AC-M11** [BE] Given the message row is not inbound (`type != 'inbound'` - an agent
reply, a bot reply, a template send), then no push is sent to anyone.

**AC-M12** [BE] Recipients are de-duplicated: a user who qualifies as both assignee and
coverer, or as assignee of two of the contact's open tickets, receives exactly one push
(with the link to the ticket assigned to them, or the most recent when both are).

**AC-M13** [BE] The resolution filters conversation trackings with
`conversation_tracking_scope()` - a form-SLA row must never be mistaken for the
conversation tracking (CLAUDE.md: two SLA systems share `conversation_sla_tracking`).

### Delivery

**AC-M14** [BE] The payload carries `title` = the contact's display name and
`body` = the message text truncated to 120 characters with an ellipsis. Nothing else -
no channel prefix, no ticket number.

**AC-M14a** [BE] `data.link` is per recipient: an assignee gets
`/sla-management/conversation-sla-tracking/<their own tracking_id>`. A recipient who
qualifies only through `all_contacts` gets the most recently updated open tracking's id,
or `/sla-management/conversation-sla-tracking?contact=<respond_io_id>` when none is
open.

**AC-M15** [BE] The payload carries `data.tag = "contact-<respond_io_id>"` so the service
worker can collapse consecutive messages from one contact.

**AC-M16** [BE] A message push writes a `notifications` row so the in-app bell shows
exactly what the phone showed. Channels are `in_app` + `web_push` only - no email
delivery row is created for this event.

**AC-M16a** [BE] Given the same Respond message reaches the ingest endpoint twice (the
dual-lane mirror the endpoint already dedupes on `message_id`), when the second lane
lands, then NO second bell entry and NO second push are produced. The notification's
idempotency key is the Respond `message_id`.

**AC-M16b** [BE] Given a message carries no `message_id` (nothing to dedupe on), when it
is ingested, then it notifies exactly once per ingest, as the row insert does.

**AC-M17** [BE] Given a recipient has no rows in `push_subscriptions`, when the push is
attempted, then nothing is sent and nothing raises.

**AC-M18** [BE] Given a push endpoint answers 404 or 410, when the send fails, then that
`push_subscriptions` row is deleted (dead-endpoint pruning, matching the existing
`_send_web_push_for_notification` behaviour).

**AC-M19** [BE] Given VAPID is not configured, when a message lands, then the ingest
still returns its normal 201 and the failure is logged, not raised.

**AC-M20** [BE] The push is dispatched from an RQ job on the `notifications` queue,
enqueued after the `chat_histories` row is committed. Given Redis is unreachable, when
enqueue fails, then `POST /api/v1/external/chat-history/messages` still returns its
normal 201 (post-commit side effects are best-effort - PRINCIPLES.md).

### Service worker

**AC-M21** [FE] Given a push arrives with a `tag` for which a notification is already
displayed, when the worker handles it, then it replaces that notification in place and
the body reads "<N> new messages", where N counts the collapsed messages.

**AC-M22** [FE] Given a push arrives and a visible window is already open on that
contact's thread, when the worker handles it, then no notification is shown.

**AC-M23** [FE] Given a push arrives and every open window is hidden, or none is on that
thread, when the worker handles it, then the notification is shown.

**AC-M24** [FE] Given the user taps a message notification, when the worker handles
`notificationclick`, then an existing window navigates to `data.link` and focuses, or a
new window opens at `data.link`.

### Preference plumbing

**AC-M25** [BE] `PUT /api/v1/user-management/users/me` (or the existing account
preference route) persists the scope, rejecting any value outside the four allowed with
422.

**AC-M26** [BE] The new column is returned by BOTH `get_user` and `get_me` manual dict
builders - CLAUDE.md: a new User column that is only added to the schema never reaches
the FE, and the toggle silently renders its default forever.

**AC-M27** [T] Existing users receive `assigned_and_coverage` via server default; no
backfill script is required, and this is asserted rather than assumed.

## Evidence (replaces a Playwright spec)

**AC-M28** [E2E] A recorded agent-browser run, written into the plan and the commit:
sign in, click through the sidebar to My Account, set the scope, ingest a message via
`POST /api/v1/external/chat-history/messages`, and show the push arriving - or, where
the headless browser cannot receive a real push, show the worker's `push` handler
producing the right notification for a synthesised event, plus the network evidence that
the send was attempted for the right recipients.

## Explicitly out of scope for the DoD

No new permission is introduced (My Account is self-service), so the permission grant
sweep is a no-op - stated here so the DoD gate can record it as checked, not skipped.
