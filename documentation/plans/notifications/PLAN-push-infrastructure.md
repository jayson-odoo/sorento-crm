# PLAN - push notification infrastructure and adoption

Status: IN PROGRESS - I0 and I1 landed (commit d363c51e5); I2 in build

| Slice | State |
| --- | --- |
| I0 queue + VAPID boot warning | DONE - `notifications` in `DEFAULT_QUEUES`, `resolve_queue_names()` seam, tests pin each queue |
| I1 payload under 4096 bytes | DONE - `build_push_payload()`, byte-measured truncation, link outranks body |
| I2 install + enable prompts | in build (#253) |
| I3 evidence + production audit | not started (#254) |

Production compose check (23 Aug 2026): the `worker` service does **not** pin
`WORKER_QUEUES`, so the new default reaches it on the next deploy. Two places could still
override it and neither has been read: `env_file: ./sorento_crm_backend/.env` on the
server, and the `*backend-env` anchor. The worker inherits that same `.env`, so the VAPID
half of AC-P18 is answered by the same grep - and failing that, by the new boot warning on
the next restart.
UAC: `documentation/plans/notifications/push-infrastructure-acceptance-criteria.md`
Domain: notifications

## Why this plan exists

The ask was "push SLA assignment and escalation to phones, then advertise it so people
install the app". Investigation found the feature is **already built and already firing** -
and is being quietly lost at four points. So this is not a build; it is a repair plus an
adoption surface, and it must land before any new event is added on top.

### What the production database says (23 Aug 2026)

| Measurement | Value |
| --- | --- |
| `push_subscriptions` rows | 1 (one user, one device) |
| `notification_deliveries` where `channel='web_push'` | 740 |
| - sent | 483 |
| - failed | 171 |
| - pending, never dispatched | 86 (32 of them in August) |
| Last successful push | 2026-08-22 10:49 |
| Failure reason: "VAPID not configured" | 158, 27 May to 13 Aug |
| Failure reason: payload over 4096 bytes | 13, 21 Jun to 2 Jul |

### SLA assignment and escalation already push

`form_sla_service._notify_assignee` (line 1375) calls
`create_with_channel_preferences(..., send_web_push=False, ...)`. That `False` is not the
final word: `notification_service.py:273-284` upgrades it to `True` whenever the user has
a row in `push_subscriptions`. The browser subscription IS the opt-in - there is no
separate preference column, by design (TCK-33).

So nothing needs building for the most important event. It needs to stop being dropped,
and it needs users who have installed the app.

## The four defects

### 1. The `notifications` queue has one drainer and no backstop

**Corrected 23 Aug 2026.** An earlier draft of this plan said the queue was never drained
at all. That was wrong, and it was wrong because the claim was written without reading
`queue_service.py`. What is actually the case:

| Path | State |
| --- | --- |
| In-process daemon drain on enqueue (`_IMMEDIATE_DRAIN_QUEUES = {"notifications": 5}`) | works, capped at 5 jobs per enqueue |
| Scheduler backstop `notification_delivery_processor` (drains 20 per tick) | **disabled** in `scheduled_tasks`, last ran 14 Aug 2026 |
| RQ worker draining the queue | absent from the default `WORKER_QUEUES` |

So deliveries are processed by a daemon thread inside whichever API process handled the
request, and both backstops are off. A burst larger than five, or a process recycled
mid-drain by a deploy or a restart, leaves rows `pending` with nothing to recover them.

The fix is therefore **resilience, not an outage repair**: a dedicated worker survives API
restarts and deploys where a daemon thread does not, and the five-job cap stops being
load-bearing. Re-enabling `notification_delivery_processor` would restore the safety net
independently; that is a production data flag rather than a code change, and with a worker
draining the queue it may simply be unnecessary.

Fix: add `notifications` to the default list, and pin it with a test so the next queue
added cannot drop it again (AC-P1, AC-P2).

**This must be checked on the server, not in the repo.** The production compose file is
hand-edited and gitignored (`documentation/.../project_compose_manual_not_in_ci`), so if
it pins `WORKER_QUEUES` explicitly, changing the default here does nothing (AC-P18).

### 2. The worker can start without VAPID and say nothing

`notification_tasks._send_web_push_for_notification` reads
`os.environ.get("VAPID_PRIVATE_KEY")` directly. Absent, it writes
`status='failed', error_message='VAPID not configured'` per delivery and moves on. 158
deliveries died that way over eleven weeks with no operator signal.

Fix: warn loudly at worker boot when the variable is missing (AC-P4). Not a hard failure -
a worker that refuses to start over one optional channel is worse.

### 3. Payloads exceed the 4096-byte web-push limit

The sender serialises `notification.data` verbatim into the push body. SLA notifications
carry `whatsapp_context_vars` (contact name, entity number, reason, two due dates, base
url, form url, portal url, the full message) in that same dict, for the WhatsApp channel's
benefit. Thirteen pushes were rejected with
`binary data passed in the request must be less than 4096 bytes`.

Fix: build the push payload explicitly rather than passing `data` through - `title`,
`body`, `data.link`, and `data.tag` where present (AC-P5). The service worker only ever
reads `title`, `body`, `data.link`, so nothing else was being used anyway. The push is a
poke with a link; everything else is one fetch away, which is the same argument
`conversation_event_bus` already makes for its own payload shape.

### 4. One person has installed it

483 successful pushes all went to a single device. No surface anywhere invites anyone to
install the app or turn notifications on; the only control is a button in My Account that
you have to already know exists.

Fix: Phase B below.

## Phase B - the adoption surface

Two prompts, each shown at most once per device, each dismissible.

**Install prompt** (AC-P8 to AC-P10, AC-P14). Mobile browsers only, not desktop - the
pitch is a phone in a pocket and a desktop nag reads as noise. Capture
`beforeinstallprompt` where it exists (Android Chrome, desktop Chrome/Edge) and fire the
native prompt on tap. iOS Safari has no such event and no programmatic install, so there
it shows the Share -> Add to Home Screen steps instead. That is not a nicety on iOS: web
push does not work at all in a plain Safari tab, only in the installed app (16.4+), so
without this step iOS users see `subscribeToPush()` return false and conclude the feature
is broken.

**Enable prompt** (AC-P11 to AC-P13). Only when running installed
(`display-mode: standalone`) and permission is still `default`. Asks once, in place. A
decline is remembered and My Account stays the way to change your mind. Nothing appears
when permission is already granted.

Both use `localStorage` for the once-per-device memory. It can come back empty (private
window, cleared data) and the cost of that is one repeated prompt, which is the right
failure for a preference this small.

While here: `app/layout.tsx` points `icons.icon` and `icons.shortcut` at an
`encrypted-tbn0.gstatic.com` thumbnail. Hotlinking a Google image as the icon of an app
we are asking people to install onto their home screen is wrong, and it breaks whenever
that URL does. The manifest's own icons are already local and correct (AC-P15).

## What is deliberately NOT in this plan

No per-event push preferences, no admin event registry, no templates, no quiet hours. The
existing design - the browser subscription is the opt-in, and every notification mirrors
to push - is doing the job. Adding a configuration layer before anyone has installed the
app is machinery for a problem nobody has yet.

The one preference that is planned is the message-scope select in
`PLAN-message-push.md`, and it exists because chat volume is genuinely different from
event volume, not because configuration is good in itself.

## Slices

Tickets: [#250](https://github.com/jayson-odoo/sorento-crm/issues/250) I0,
[#251](https://github.com/jayson-odoo/sorento-crm/issues/251) I1,
[#253](https://github.com/jayson-odoo/sorento-crm/issues/253) I2 (install + enable),
[#254](https://github.com/jayson-odoo/sorento-crm/issues/254) I3 (evidence).
[#252](https://github.com/jayson-odoo/sorento-crm/issues/252) closed - see below.

**I0 - queue and boot correctness.** `notifications` in the default queue list, a test
pinning it, the VAPID boot warning, failure logging at WARNING. Covers AC-P1, AC-P2,
AC-P4, AC-P7.

**I1 - payload builder.** Explicit push payload under 4096 bytes with a test at the
boundary. Covers AC-P5, AC-P6. Lands directly in
`notification_tasks._send_web_push_for_notification` - no new module.

**I2 - install and enable prompts.** Covers AC-P8 to AC-P16, including the icon fix.

**I3 - evidence and operational note.** Covers AC-P17, AC-P18.

I0 and I1 are independent of I2. I3 is last.

**There is no reconciler slice.** The 86 stuck deliveries are between one and three
months old. Re-enqueuing them would deliver a stale SLA alert to a phone long after the
form was handled, which is worse than the silence. Once I0 lands they stop accumulating;
the existing rows are left where they are, and that is the whole decision. A one-shot
command to re-send them was drafted and cut - it is machinery for a backlog nobody wants
delivered.

## Ordering against the message event

`PLAN-message-push.md` slice S0 (the FE mock of the scope select) is independent and can
proceed. Its S3 (the send path) should land after I0 and I1, or the first thing the new
event does is reproduce all three defects.

## Risks

- **The production worker's real queue list is unknown from here.** If compose pins
  `WORKER_QUEUES`, I0 changes nothing until that file is edited on the server. AC-P18
  exists to force that check rather than assume the fix took.
- **Advertising a feature that is being dropped is worse than not advertising it.** I0
  and I1 must be verified in production before I3 ships, or the first wave of installs
  meets the same 9 percent silent loss August shows.
- **iOS remains best-effort.** Installed-only, throttled when the device is idle. The
  install prompt copy must not promise parity with a native app.
- **One repeated prompt** where `localStorage` is unavailable. Accepted.

## Definition of Done

1. `notifications` drained by the worker, asserted by test AND confirmed on the server.
2. A push with an oversized `data` blob delivers rather than failing.
3. An install and an enable prompt, verified at 375px and 1280px by real sidebar
   navigation.
4. A real SLA escalation observed arriving on a phone, recorded.
