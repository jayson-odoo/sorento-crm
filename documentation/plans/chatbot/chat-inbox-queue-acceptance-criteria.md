# UAC: CHAT-INBOX-QUEUE - the CRM owns each contact's message queue

Plan: `PLAN-chat-inbox-queue.md`. Owner GO 25 Oct 2026 05:50 (option 2, drains on the API
pool, re-send rule (a) behind one function) and 05:55 (zero downtime on deploy).

Words: **covered contact** = a contact the existing switch `system_settings.chatbot_direct_ingress_mode`
covers (`contacts` = the ids in `chatbot_direct_ingress_contacts`, `all` = everyone; `off` =
nobody; `direct_ingress.covers`). **Injector** = anything that delivers a customer message to
the CRM: the respond.io webhook (`POST /api/v1/public/respond/webhook`), n8n's
`POST /api/v1/external/chat/turn` (the spine, the failover `sorento-main-INJECT`, and Retry's
re-inject all arrive here). **Sender** = the workspace's thin n8n chatbot sender
(`direct_ingress.send`). **Send time** = respond.io's send time (`send_order.send_key_ms`).

## Switch

- **IQ-1** Mode `off`: nothing changes. `/chat/turn` runs the turn synchronously and returns
  its reply and actions; the webhook starts no turn; no sender POST. The existing chatbot
  suites stay green.
- **IQ-2** Mode `contacts` queues only the listed contacts; everyone else keeps the sync path.
  Mode `all` queues every contact.
- **IQ-3** `is_test` and console turns are never queued, whatever the mode.

## Enqueue (every injector, answered once)

- **IQ-4** A covered message creates at most ONE queued turn row, whichever injectors deliver
  it and in whatever order (webhook, n8n, INJECT, Retry re-inject, and repeats of each).
- **IQ-5** No injector waits for the turn. The webhook answers respond.io as today. `/chat/turn`
  for a covered contact answers at once with no actions, in the shape the spine already treats
  as nothing to send (`duplicate: true`, `actions: []`).
- **IQ-6** A covered photo or voice note is queued too (direct ingress's text-only skip does not
  apply in queue mode); it is read inside its own turn on the drain.
- **IQ-7** The webhook's existing gates still apply to its copy: bad signature 401, unsigned,
  not incoming, not WhatsApp, staff sender, rate limit, stale. A message an injector skipped
  can still be queued by another injector's copy.

## Order (per contact, send time, no clamp)

- **IQ-8** At most one turn of a contact runs at a time, across all API processes.
- **IQ-9** A contact's queued rows are answered in send-time order, whatever their arrival
  order, with no time limit that lets a later message overtake: a burst of 12 messages from one
  contact, arriving shuffled, gives 12 sender POSTs in send order, one each.
- **IQ-10** The next row of a contact starts only after the previous row's sender POST has
  returned.
- **IQ-11** A contact under human takeover when its row comes up: no sender POST for it (as
  direct ingress today); its later rows are handled the same way.

## Global burst

- **IQ-12** 40 contacts x 3 messages enqueued at once: all 120 answered exactly once, each
  contact in send order; turns running at once in one process never exceed the direct-turn pool
  size; a row that cannot start yet stays queued (never dropped, never left to n8n).

## Late earlier-sent photo

- **IQ-13** A text T (sent second) is running when a photo P (sent first) is queued. T's turn is
  abandoned before it writes any conversation state or posts anything; P is answered; then T
  runs again and sees what P left (its products). The sender gets P's actions, then T's. Each
  once.
- **IQ-14** When nothing earlier is queued, a finished turn posts at once: no added wait.

## Failures and crashes

- **IQ-15** A turn that fails in the engine posts the engine's error reply once (as a failed
  sync turn answers today); the contact's next rows continue.
- **IQ-16** Sender POST failed: logged as failed. Whether the row is sent again is decided by
  ONE function (`should_resend`): it re-sends only when the log proves the POST never left
  (connection refused before sending); a timeout or an error answer after sending is NOT
  re-sent and the row is flagged for staff on the turn trace. The contact's next rows continue.
- **IQ-17** A process dies with rows queued: the next live process answers them, in send order,
  each once (a sweeper at start-up and at least every 2 s re-arms a drain for every contact
  with queued rows and no live drain).
- **IQ-18** A row left running by a dead process: if no sender POST was attempted for it, it
  runs again and is answered once; if a POST was attempted, `should_resend` decides (IQ-16).

## Deploy (zero downtime)

- **IQ-19** On shutdown (SIGTERM), a process's drains stop taking new rows, finish the turn they
  are in (including its sender POST and its done mark) within the grace period, then exit. Test:
  shutdown mid-turn gives exactly one sender POST for that row, the row done, and the contact's
  later rows still queued and untouched.
- **IQ-20** A message that arrives while a process is shutting down is queued and answered by
  the next process, in send order.
- **IQ-21** The grace period covers the longest turn (photo read up to `media_sync_wait_seconds`,
  30 s, plus parser and lane); the deploy keeps ingress reachable through the switch (values and
  any deploy change: plan section "Zero-downtime deploy").

- **IQ-24** In queue mode a photo or voice read that is not finished within
  `media_sync_wait_seconds` (for example while the worker restarts) does not produce a "could
  not read it in time" reply: the drain keeps waiting (heartbeat kept, hard cap 10 minutes)
  and the contact's later rows wait behind it. A read job the worker abandoned is read again
  once.
- **IQ-25** The app's shutdown handler returns only after every running drain has finished its
  current row (POST and done mark), so the process never exits mid-turn on a deploy; the
  gunicorn grace (`graceful_timeout`) and the deploy script's stop timeout are both above the
  longest turn.

## Review round 1 additions (reviewer + security-reviewer, 25 Oct)

- **IQ-26** Every lane answers in queue mode exactly as in sync mode: casual / low-signal,
  out of scope, escalation offer and escalation accept included (they close through the
  delegated path today). No generic error reply because a row was queued.
- **IQ-27** A turn gives way BEFORE any lane side effect it cannot undo (escalation's SLA row
  and round-robin draw): a re-run after giving way writes them once.
- **IQ-28** Shutdown starts at the signal: on SIGTERM drains stop taking rows at once, even
  while long-lived connections (staff event streams) are still open; a drain waiting on a
  photo read parks the row (back to queued, nothing written) instead of waiting, so the next
  process continues it. Total shutdown stays inside gunicorn's grace.
- **IQ-29** One answer per row even if the drain's Redis mutex is lost mid-turn (Redis restart,
  key evicted): each claim is fenced on the row, the `sending` stamp and the done mark only
  apply to the claim that owns the row, and a drain whose stamp matches nothing does not POST.
- **IQ-30** Fairness: a contact with a long backlog does not hold a pool thread for it; each
  drain step runs one row then yields, so other contacts' rows are answered in between. A
  photo read not finished within `media_sync_wait_seconds` parks the row and frees the thread
  (the contact's later rows still wait behind it; overall cap 10 minutes from the first read).
  The sender POST's connect timeout is short (5 s); the read timeout stays 60 s.
- **IQ-31** A failed respond.io contact lookup (takeover check) never answers: the row goes
  back to queued and the contact backs off (growing delay, no hot loop).
- **IQ-32** `/chat/turn` applies the structural gates before queueing: incoming messages only,
  not from a staff / bot sender, WhatsApp only. (It stays authenticated by its API key; no
  stale cut, so failover copies still queue.)
- **IQ-33** A contact cannot pile up more than 200 queued rows: a further copy is not queued
  and is logged as an error (a loop guard far above any human rate).
- **IQ-34** A recovered row whose logged sender outcome is `ok` is marked done, not flagged.
- **IQ-35** A photo read whose job row has made no progress for longer than its expected run
  is treated as abandoned and read again once, without waiting for RQ's registry cleanup.
- **IQ-36** The sweeper's query is served by an index (partial on queued / processing rows),
  built without blocking writes; with mode off it costs nothing measurable.

## Retry and rollback

- **IQ-22** Retry on a failed queued turn answers it once, even if the Retry copy arrives twice.
- **IQ-23** Mode switched to `off` with rows still queued: those rows are still answered, once;
  new messages take the sync path.
