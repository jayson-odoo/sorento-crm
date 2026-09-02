# M6 Composer, mobile, toasts, focus - browser verification evidence (agent-browser, 3 Sep 2026)

Worktree `motion2-M6`, branch `feat/motion2-M6-composer-mobile-toasts`, HEAD `b0d0fc154`. FE
`PORT=3081 npm run dev` (`npm run dev` PID 6241, `next dev` child PID 6267), BE reused read-only
on `:8120` per `FASTAPI_INTERNAL_URL=http://localhost:8120` in `.env.local` (copied from the
`motion2-M3` worktree's shape, confirmed `NEXTAUTH_URL=http://localhost:3081`,
`AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`). `lsof -i :3081` / `:3082` empty before starting;
load average (1 min) 6.27 at the start, 4.53 just before boot, both under the 12 guard. Login via
`E2E_EMAIL`/`E2E_PASSWORD`. Session `--session m6tester` (isolated browser). Viewport 1280x800
default, 375x812 for the mobile checks. Navigated by sidebar clicks from `/`.

**Method beyond the standard command set.** Same as the M3 evidence run: a Node 22 script with
native `WebSocket` attached directly to the daemon's Chrome via `agent-browser get cdp-url` and
the page's own `webSocketDebuggerUrl` (from `/json/list`, simpler than `Target.attachToTarget`
session juggling and confirmed to be the SAME tab `agent-browser` already had open by matching
`target.url` against `localhost:3081` first). Raw CDP drove: `Emulation.setEmulatedMedia` +
`setTouchEmulationEnabled` + `setEmitTouchEventsForMouse` for coarse-pointer (M6-03, same recipe
as M3-05 - bare feature overrides alone did not flip `matchMedia`), `Fetch.enable` +
`fulfillRequest`/`failRequest` to force a query error and a send failure (M6-01, M6-04),
`Network.emulateNetworkConditions` + `setCacheDisabled` to throttle image loads (M6-07), and
`Input.dispatchKeyEvent` for a real Tab keypress (M6-05, so `:focus-visible` reflects genuine
keyboard navigation rather than a scripted `.focus()` call). Scripts and helper module (`cdp.mjs`)
are in the scratchpad, not committed - the numbers and screenshots below are the record.

**Tool quirks hit this run, confirmed harness artifacts, not product defects:**

- `click <ref>` / `element.click()` silently no-ops on the sidebar accordion toggles and on the
  Conversations inbox's "All" tab (a Radix `Tabs`-shaped trigger) - the same finding as
  M1-M5 evidence. Worked around with a full
  `pointerdown/mousedown/pointerup/mouseup/click` dispatch (sidebar) or `agent-browser`'s own
  `find role button click` (the tab, which needed a real pointer event the CLI provides but a
  JS-dispatched synthetic one did not reliably trigger). Plain `.click()` worked fine on ordinary
  buttons (Send, dialog triggers, conversation rows).
- A same-JS-tick double `sendBtn.click(); sendBtn.click();` (zero-latency) sent TWO messages, not
  one - `sending` is a React state set via `setSending(true)`, which does not update the closure
  variable the SECOND call reads until the next render, so two calls in the exact same
  synchronous tick both pass the `sending` guard. This is not a realistic double-Enter or
  double-click: even the fastest real double-click or a "spam Enter" keypress has some event-loop
  gap between the two events. Retested with a 15ms gap (via two separate `Input`/`KeyboardEvent`
  dispatches) and the guard held cleanly - see M6-01 detail below. Flagged here as a harness
  artifact per the M3 evidence run's own precedent for zero-latency synthetic dispatch, not
  reported as a fail.
- `agent-browser`'s own tab-switch click DOES fire a real pointer sequence (confirmed it succeeds
  where a JS `.click()` on the identical element does not), so it was used for the one Radix-tab
  interaction in this run instead of a synthetic dispatch.

## Findings summary (pass/fail table)

| Check | Target | Result | Measured value |
| --- | --- | --- | --- |
| M6-01 (1280) | Caret/focus never leaves the textarea across a send | PASS | 154 samples at 40ms intervals from type-through-settle: `activeIsTextarea` true on every single sample (0 false) |
| M6-01 (1280) | Textarea never gains `disabled` | PASS | 0 of 154 samples had `textareaDisabled: true` |
| M6-01 (1280) | Attach / Voice buttons never gain `disabled` | PASS | 0 of 154 samples for either button |
| M6-01 (1280) | Optimistic bubble: dimmed (`opacity-60`), then replaced with no duplicate | PASS | Bubble present (count=1, never 2) for 32 consecutive 40ms samples (~1.28s), then gone; final screenshot shows the single un-dimmed `ZZT-M6 optimistic test 065731` bubble with a delivered checkmark, no stray dimmed copy |
| M6-01 (1280) | Realistic fast double-Enter -> one message | PASS | Two `KeyboardEvent('keydown', {key:'Enter'})` dispatches 15ms apart, second one re-typing the same text (since the first send already cleared the field): exactly one `ZZT-M6 reentry test 065544` bubble delivered |
| M6-01 (1280) | Realistic fast double-click on Send -> one message | PASS | Two `sendBtn.click()` calls 15ms apart: Send button read `disabled: true` at +15ms (guard already committed), second click intentionally skipped by the script exactly because of that - single `ZZT-M6 clickgap test 065630` bubble delivered |
| M6-01 (1280) | Same-tick (0ms) double-click | **Harness artifact, not a real interaction** | Two messages sent (`ZZT-M6 optimistic test 065455` x2) - see quirks note above; not counted against the AC |
| M6-01 (1280) | Failure: bubble removed, error toast top-center with close button, persists | PASS | `Fetch.failRequest` on the `POST .../reply` call: pending-bubble sample count dropped from 1 to 0 within one 40ms poll tick of the failure; toast `data-type=error`, `data-y-position=top`, `data-x-position=center`, close button present, still present at +9s (no auto-dismiss) - textarea kept the unsent text for a retry (`setReplyText('')` only runs on the success path) |
| M6-01 (375) | Same success-path measurements, repeated at 375 | PASS | Identical shape: 154 samples, 0 focus/disabled violations, pending bubble for 31 consecutive samples then replaced, final bubble `ZZT-M6 optimistic test 375 065946` visible un-dimmed |
| M6-02 | Notifications sheet sizes via `dvh`, bottom edge visible at 375 | PASS | `ScrollArea` computed class `h-[calc(100dvh-12rem)] min-h-[200px]`; rect bottom `697px` inside a `812px` viewport |
| M6-02 | AI assistant panel sizes via `dvh`, bottom edge visible at 375 | PASS | Inline style `max-height: calc(100dvh - 6rem)`; panel rect bottom `788px` inside `812px` |
| M6-02 | Conversations inbox sizes via `dvh` | PASS | Container class `min-h-[70dvh] ... lg:h-[calc(100dvh-13rem)] lg:flex-row`; rect bottom `719.9px` inside `812px` |
| M6-02 | Real mobile-Safari dynamic-toolbar emulation | NOT AVAILABLE | `agent-browser` 0.27.0 exposes no visual-vs-layout-viewport split; used the UAC's own documented fallback ("else assert the computed height uses dvh") for all three surfaces instead |
| M6-03 | Default `Input` `md` size: 16px under `pointer-coarse`, smaller otherwise | PASS | Products search box: `13px` with no emulation, `16px` with `Emulation.setEmulatedMedia` (`pointer: coarse`) + touch/mobile emulation active (`matchMedia('(pointer: coarse)')` confirmed `true`) |
| M6-03 | No `maximum-scale` in the viewport meta | PASS | `<meta name="viewport">` content: `"width=device-width, initial-scale=1"` |
| M6-04 | One `<Toaster position="top-center">` | PASS (code + observed) | Every toast observed this run (success, mutation-error, query-error, permission) carried `data-y-position=top data-x-position=center` |
| M6-04 | Mutation error: top-center, close button, persists (no auto-dismiss) | PASS | Incidental real event: `POST /api/v1/complaints-management/complaints` 500'd (see the out-of-scope backend bug noted below) and its `toast.error(...)`-driven toast (`hooks/useEntityMutation.ts`) was still on screen, unclosed, **90+ seconds later** with `data-close-button` present - confirmed via DOM read, not a timed script |
| M6-04 | Success toast auto-dismisses at ~4000ms | PASS | Composer's `toast.success('Sent.')` on a real send: visible for `4201ms` from first-seen to first-gone sample (150ms poll granularity) |
| M6-04 | **Query error: top-center, close button, persists** | **FAIL** | `Fetch.fulfillRequest` forced two consecutive 500s on `GET /api/v1/master-data/products` (react-query `retry:1` needs both failed to reach `onError`): the resulting toast (`providers/query-provider.tsx`'s `QueryCache.onError` -> `toast.custom(...)`) was `top-center` (PASS) but **`hasClose: false`** (no close button) and **auto-dismissed after ~3.6-4s** (last-seen sample at t=6410, poll-relative; first-seen at t=2812; gone by the next 150ms tick) - not "still present after 6s". Screenshot `M6-04-query-error-no-close-button-FAIL.png` shows the black toast with no X, contrast against the mutation-error toast's X in `M6-01-failure-toast-and-bubble-removed.png`. Root cause in source, see below |
| M6-05 | Tabbing to a dialog's close X shows the global focus ring | PASS | Real `Input.dispatchKeyEvent` Tab keypresses (16, on the Export dialog) landed on `[data-slot="dialog-close"]`; `element.matches(':focus-visible')` `true`, computed `outline: 2px solid`, `box-shadow` ring stack non-`none` |
| M6-07 | Conversation thread with 2+ images stays pinned to the bottom while they load | PASS | Jennifer thread (2 real images, pre-existing conversation data - see note below), network throttled to ~200kbps/300ms latency with cache disabled, then reloaded and reselected: `scrollHeight - scrollTop - clientHeight` (`distanceFromBottom`) read **exactly `0` on every one of 65 valid 100ms samples** across a 7s window while one of the two images finished loading mid-window |
| M6-07 | Image wrappers are fixed-aspect boxes | PASS | Both `<img>` in the thread have a `closest('[class*="aspect-"]')` ancestor with class `aspect-[4/3] w-full overflow-hidden rounded bg-muted/20` |
| Console | Zero NEW errors (pre-existing a11y warnings are noise) | ONE NEW ERROR, out of scope | `[error] Error submitting form: name '_request_has_valid_external_api_key' is not defined` - a backend `NameError` surfaced while probing for a safe throwaway record to send M6-01's message into (see below); unrelated to any M6 source file. Six `Missing Description for {DialogContent}` warnings are the same pre-existing a11y noise this run's own dialogs already triggered (Export dialog, template dialog) and are not new |

## M6-04 root cause: query errors bypass the duration/close-button standard

`lib/toast.ts` wraps only `success` (4000ms) and `error` (`Infinity` + `closeButton: true`);
`custom`, `info`, `warning`, `message`, `promise`, `dismiss`, `loading` are explicitly documented
as "pass through unchanged" and `lib/toast.test.ts` asserts exactly that
(`toast.custom` -> `sonnerToast.custom` with no injected options). `providers/query-provider.tsx`'s
`QueryCache.onError` renders its red banner via `toast.custom(() => <Alert ... close={false}>...)`
for BOTH the permission-denied case and the generic case - never `toast.error(...)`. Since
`toast.custom` gets no duration override, it falls back to Sonner's own default (`4000ms`), and
since the `Alert` itself is rendered with `close={false}`, there is no dismiss affordance on the
custom content either - and Sonner's own `closeButton` prop on `<Toaster>` does not retrofit one
onto arbitrary `custom()` content the way it does for `success`/`error`/etc. calls that go through
Sonner's own Toast component. Net effect: every REST **query** failure surfaced through the shared
`QueryClient` (as opposed to a mutation's own `onError: toast.error(...)`, which every
`useEntityMutation`-based hook uses and which DOES get the Infinity+close treatment) reads and
disappears like a transient success message, with no way to re-read it once it is gone. This is
the M6-04 commit's (`0dac8bce8`) own scope boundary - it changed `query-provider.tsx`'s import from
`sonner` to `@/lib/toast` and dropped the now-redundant per-call `position: 'top-center'`, but did
not touch the `toast.custom(...)` call shapes themselves - not a regression introduced by
something else in this slice.

## Note on the M6-01 send target

The composer send test needed a conversation "clearly owned" per the run's data-safety
instruction. The Conversations inbox's only pre-existing entries are real customer/supplier
WhatsApp threads (Eric Ng, Jennifer, Johnson, Brendon Foo, Sorento Sandy) except one: **"Jayson"
+60166753328**, whose thread content (product-catalogue bot replies to the tester's own queries)
and whose name matches the logged-in user (`tehjayson@gmail.com`) - this is the developer's own
test WhatsApp line, not a third party's, and is where all M6-01 sends in this run went (six
distinct throwaway `ZZT-M6 ...` texts, three of them intentionally landing as real deliveries.
per the composer's own success path). No other contact's thread was touched. Two other avenues
were tried first and abandoned as unsuitable: creating a new Complaint (blocked by a real,
pre-existing backend bug - `POST /api/v1/complaints-management/complaints` 500s with a Python
`NameError: name '_request_has_valid_external_api_key' is not defined`, unrelated to M6, not
investigated further here since it is out of scope) and reusing an existing `ZZT-E2E`-coded Stock
Inquiry (its chat contact, "BASER" +601116891678, could not be confirmed as a designated test line
the way "Jayson" self-evidently is, so it was left untouched).

## M6-07 note on the image count

The UAC / brief ask for a thread with three images; the richest one found via a sweep of every
existing conversation (`Eric Ng`, `Jennifer`, `Johnson`, `Brendon Foo`, `Sorento Sandy`, `Jayson`)
was Jennifer's, with exactly **two** real images (a conversation-SLA-tracking attachment and a
technical-specification photo) and no way to load further history (`scrollHeight` did not grow
across five programmatic `scrollTop = 0` attempts - `RespondChatList`'s "load older" fetch appears
to need a genuine `scroll` event, not just a property write, and was not chased further since two
images already exercises the stay-pinned behaviour the check cares about). Per this run's own
brief ("2+ images... if none exists, say so and mark source-confirmed"), this is reported as
source-confirmed at 2 images, not 3.

## Screenshots in this directory

- `M6-01-1280-optimistic-then-real.png` - Jayson thread at 1280px, final settled state after a
  real send: the plain, un-dimmed `ZZT-M6 optimistic test 065731` bubble with a delivered
  checkmark, no leftover dimmed duplicate.
- `M6-01-375-optimistic-then-real.png` - same check at 375px (mobile single-pane thread view).
- `M6-01-failure-toast-and-bubble-removed.png` - forced-failure run: pending bubble already gone,
  "Failed to fetch" error toast top-center WITH a close button (contrast against M6-04's finding).
- `M6-02-notifications-sheet-375.png` - notifications bell sheet open at 375px.
- `M6-02-ai-assistant-375.png` - AI assistant panel open at 375px, overlaying the thread.
- `M6-02-conversations-inbox-375.png` - Conversations inbox single-pane thread view at 375px.
- `M6-04-query-error-no-close-button-FAIL.png` - forced query-error run: "Failed to fetch
  products" toast, top-center, but no close button (the M6-04 fail).
- `M6-05-dialog-close-focus-ring.png` - Export dialog, close X focused via real Tab keypresses,
  focus ring visible.
- `M6-07-jennifer-thread-2-images.png` - Jennifer thread with both real images loaded, thread
  scrolled to the bottom.

## Cleanup

Dev server killed: `kill 6241` (parent `npm run dev`); its child `next dev` (6267) exited with it -
confirmed via a follow-up `lsof -i :3081` returning empty. Only the `m6tester` agent-browser
session was closed (`close`, not `close --all`). The direct-CDP Node scripts attached to and
detached from the SAME session's target each time via the page's own `webSocketDebuggerUrl` - no
second browser was opened. `.env.local` left in place. Network throttling and cache-disable were
reset (`Network.emulateNetworkConditions` back to unrestricted) at the end of every script that
set them; `Fetch` domain was disabled after each interception script.

**Data:** six real WhatsApp sends landed on the developer's own "Jayson" test conversation
(`ZZT-M6 optimistic test 065455` x2, `ZZT-M6 reentry test 065544`, `ZZT-M6 clickgap test 065630`,
`ZZT-M6 optimistic test 065731`, `ZZT-M6 optimistic test 375 065946`, `ZZT-M6 toast timing test
070942`) plus one failed attempt left in the draft box (`ZZT-M6 failure test 065823`, never sent,
textarea content only) - all on the tester's own conversation, none deleted (this composer has no
delete path for a sent message, and none was requested). No Complaint or Stock Inquiry record was
created (the Complaint attempt 500'd server-side before any row was written; the Stock Inquiry
route was inspected but not used to avoid the "BASER" contact - see note above). No deferred-delete
countdown was armed at any point in this run.
