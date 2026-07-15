# PLAN — Per-event, per-channel SLA notify (assignment vs escalation)

Status: **Done** — migration applied, BE gating + tests green, both FE forms verified in browser.

## Goal
Replace the coarse "notify" flags with a matrix. A notification on a form-SLA
event (assignment / escalation) sends on a channel ONLY when BOTH are true:
- the STAGE allows that event, and
- the USER opted into that channel for that event.

### Stage config (form_sla_configs)
- `notify_assignee` (existing) → "Notify on **assignment**".
- `notify_on_escalation` (NEW, default true) → escalation now respects it (today it always notifies).

### User toggles (users)
Replace the single `notify_whatsapp` (assign+escalate) with per-event × per-channel:
- `notify_email_on_assignment` (default **true** — preserves today's always-email)
- `notify_email_on_escalation` (default **true**)
- `notify_whatsapp_on_assignment` (default = old `notify_whatsapp`)
- `notify_whatsapp_on_escalation` (default = old `notify_whatsapp`)
Keep `notify_whatsapp_summary` (separate). Keep `notify_whatsapp` column (unused for
assign/escalate now; left to avoid a destructive drop).
In-app stays always-on when the stage allows the event (not user-gated).

### Send matrix (`_notify_assignee(kind)`)
| kind | gate (stage) | email sends if | whatsapp sends if |
|---|---|---|---|
| assigned | `notify_assignee` | user `notify_email_on_assignment` | user `notify_whatsapp_on_assignment` + contact |
| escalated | `notify_on_escalation` | user `notify_email_on_escalation` | user `notify_whatsapp_on_escalation` + contact |

## BE
1. **Migration** (from head 932195fa2398): add `form_sla_configs.notify_on_escalation` (bool, server_default true); add the 4 user bool columns (email defaults true, whatsapp backfilled from `notify_whatsapp`).
2. **Models**: `FormSLAConfig.notify_on_escalation`; `User` 4 new columns.
3. **notification_service.create_with_channel_preferences**: add `email_pref_attr: Optional[str]=None` — when set, gate `send_email` on `getattr(user, email_pref_attr)`. Mirrors the existing `whatsapp_pref_attr` gate. Default None ⇒ email unchanged for other callers.
4. **_notify_assignee(kind)**: pass per-event pref attrs:
   - assigned → email `notify_email_on_assignment`, whatsapp `notify_whatsapp_on_assignment`.
   - escalated → email `notify_email_on_escalation`, whatsapp `notify_whatsapp_on_escalation`.
5. **_escalate_tracker**: before `_notify_assignee(kind="escalated")`, look up the stage config by `(source_entity_type, team_set_code)`; skip notify if `notify_on_escalation` is false (default true / notify when no config found).
6. **Schemas/API**: extend `_ChannelPrefsUpdate` + `_channel_prefs` + user profile schemas with the 4 fields; FormSLAConfig schema + create/update with `notify_on_escalation`.

## FE
7. `user-profile-edit-dialog.tsx` + `notification-channels-preference.tsx`: replace the single "WhatsApp escalation & assignment alerts" with 4 toggles (Email/WhatsApp × Assignment/Escalation). Update `user-profile-schema.ts` + `app/models/user.ts`.
8. `FormSLAConfigDialog.tsx`: add "Notify on escalation" toggle.

## Tests
pytest: matrix gating in `_notify_assignee` (each cell), escalation respects `notify_on_escalation`, `create_with_channel_preferences` email gate. Migration up/down.
