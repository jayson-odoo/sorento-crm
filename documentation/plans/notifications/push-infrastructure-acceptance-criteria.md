# Push notification infrastructure - acceptance criteria

Status: DRAFT
Plan: `documentation/plans/notifications/PLAN-push-infrastructure.md`
Blocks: `documentation/plans/notifications/PLAN-message-push.md` (the first NEW event
rides on this infrastructure; SLA assignment/escalation already does)

## Journey

A salesperson opens Sorento on her phone browser. A bar appears once: **"Install Sorento
on your phone - get SLA alerts even when the app is closed."** She taps it. On Android
the browser's install prompt fires. On iOS she is shown the two steps Safari requires
(Share -> Add to Home Screen), because iOS has no programmatic install.

The app opens from her home screen like an app. On first launch inside the installed app
she is asked once whether to allow notifications. She allows.

That evening a form SLA escalates to her. Her phone buzzes with the title and reason and
a link. She taps, lands on the form, and claims it.

She was never sent to a settings page to find a toggle, and she was never asked twice.

## Phase A - make the existing path reliable  [BE] [T]

**AC-P1** [BE] Given the RQ worker starts with no `WORKER_QUEUES` override, when it
reports its queue list, then `notifications` is in it. Today's default
(`imports,respond_io,catalogue_render,media,project_docs,flyer_read`) omits it, so every
`send_notification_deliveries` job enqueues and is never drained - 86 deliveries sat
`pending`, 32 of them in August 2026.

**AC-P2** [T] A test asserts `notifications` is present in the default queue list, so the
next queue added cannot silently drop it again.

**AC-P3** [BE] Given deliveries are sitting `pending` older than a threshold, when a
recovery command is run, then they are re-enqueued and their outcome recorded. This is a
one-shot reconciler for the existing backlog, not a scheduled sweeper.

**AC-P4** [BE] Given the worker process starts without `VAPID_PRIVATE_KEY`, when it
boots, then it logs a clear WARNING naming the missing variable. 158 deliveries failed
with "VAPID not configured" between 27 May and 13 Aug 2026 and nothing surfaced it.

**AC-P5** [BE] Given a notification whose `data` blob would push the payload over the
4096-byte web-push limit, when the push is built, then the payload is trimmed to
`title`, `body` and `data.link` (plus `tag` where present) so it always fits. 13 SLA
pushes failed on this in Jun-Jul 2026 because `whatsapp_context_vars` is carried in the
same `data`.

**AC-P6** [T] A test builds a notification with an oversized `data` blob and asserts the
resulting payload is under 4096 bytes and still carries a usable `link`.

**AC-P7** [BE] Given a push fails for any reason, when the delivery row is written, then
`error_message` records the reason (already true) AND the failure is logged at WARNING
with the user id, so a silent org-wide outage is visible without a SQL query.

## Phase B - adoption: install and enable  [FE]

**AC-P8** [FE] Given I am signed in on a mobile browser and the app is not installed,
when I open any page, then a dismissible install prompt appears once, saying what
installing gets me (alerts when the app is closed). Dismissing it does not show it again
on that device.

**AC-P9** [FE] Given the browser supports `beforeinstallprompt` (Android Chrome, desktop
Chrome/Edge), when I tap Install, then the native install prompt fires.

**AC-P10** [FE] Given I am on iOS Safari, where `beforeinstallprompt` does not exist,
when I tap Install, then I am shown the Share -> Add to Home Screen steps, because iOS
offers no programmatic path. iOS also requires the installed app for web push at all
(16.4+), which is why this cannot be skipped there.

**AC-P11** [FE] Given the app is running installed (`display-mode: standalone`) and
notification permission is `default`, when I open it, then I am asked once to enable
notifications, in place, without being sent to My Account.

**AC-P12** [FE] Given I decline, when I open the app again, then I am not asked again;
the toggle in My Account remains the way to change my mind.

**AC-P13** [FE] Given permission is already granted and a subscription exists, then
neither prompt appears.

**AC-P14** [FE] Given I am on a desktop browser with the app not installed, then the
install prompt is not shown - the pitch is a phone in a pocket, and a desktop nag reads
as noise.

**AC-P15** [FE] The app icon and tab icon are served from our own origin. `app/layout.tsx`
currently points `icons.icon` and `icons.shortcut` at an `encrypted-tbn0.gstatic.com`
thumbnail URL - a hotlinked Google image, which is wrong for an app we are asking people
to install and dies whenever that URL does. The manifest's own icons are already local
and correct.

**AC-P16** [FE] Both prompts render correctly at 375px and 1280px and never cover the
primary action of the page beneath.

## Phase C - prove it  [E2E]

**AC-P17** [E2E] A recorded agent-browser evidence run: sign in, enable notifications,
trigger a real form-SLA assignment for that user, and show the delivery row reaching
`sent` plus the notification the worker produced. Written into the plan and the commit so
it can be re-walked.

**AC-P18** [BE] Given the evidence run completes, then a short operational note records
which queues the PRODUCTION worker actually drains (the compose file on the server is
hand-edited and gitignored, so this cannot be read from the repo) and whether the
production worker has the VAPID variables.

## Out of scope

Per-event push preferences, an admin event registry, quiet hours, notification
templates. The message-arrival event is its own plan and rides on this one.
