# n8n contract changes — handoff for the sorento-crm-n8n session

**Do not apply directly to live.** This is the spec for the n8n-side session to implement
and test in its own environment before promotion.

Belongs to slice S4 of `PLAN-monitoring-enhancement.md`. The CRM side can ship first —
every new ingest field is **optional**, and the ingest schema uses Pydantic's default
`extra="ignore"`, so today's payloads keep validating unchanged. Until n8n lands these,
the latency metric simply has no data; nothing breaks.

## Why

We are measuring the WhatsApp round trip — user presses send → our reply is accepted by
Respond — against a **p99 ≤ 10s** SLA, with alerting on from day one.

Three facts make the current payload unusable for that:

1. `sent_at` is `new Date().getTime()` — n8n's clock at save time, not when the user
   actually sent. Measured on real rows, outgoing `sent_at` sometimes **precedes** the
   incoming message it answers, so naive `t1 - t0` yields negative latency.
2. `message_id` is populated on **4 of 1519 rows**. The field exists in the ingest schema;
   n8n just isn't sending it. Without it the CRM cannot resolve the authoritative
   Respond-side timestamp via `GET /v2/message/{id}`.
3. Nothing links an outgoing message to the incoming one that triggered it. Temporal
   guessing breaks on message bursts and on proactive sends.

Both timestamps must come from **Respond's clock** so there is no skew between them.

## Workflows

| Workflow | Id |
|---|---|
| Main | `9qVyfUxmRQqrpGRMDLRuz` |
| Save-incoming subworkflow | `UrETd-jm46tFj3Xw7w8vL` (`sub-respond-save-message-redis`) |
| Send subworkflow | `aoydkG1dbItXR5jXFEQsP` (`sorento-sub-respond-sendmsg-respond`) |

## Change 1 — incoming save: pass the raw Respond timestamp

Node `Call 'sub-respond-save-message-redis'2`.

```diff
- "sent_at": "={{ new Date().getTime() }}"
+ "sent_at": "={{ $('tf-message').first().json.message.message.timestamp }}"
```

Verbatim epoch ms from the webhook — no arithmetic, no re-parsing. This is the
`message.timestamp` field (e.g. `1784519974000`) already present in the payload.

Apply the same change inside the `data` JSON blob, which repeats `"sent_at": new Date().getTime()`.

## Change 2 — populate `message_id` on both directions

Incoming: `messageId` from the webhook payload.

```
"message_id": "={{ $('tf-message').first().json.message.message.messageId }}"
```

Outgoing: the id returned by the Respond send call, which the send subworkflow already
receives. Pass it through to the chat-history ingest.

```
"message_id": "={{ $json.messageId }}"      // adjust to the send node's actual output path
```

This is the load-bearing change: the CRM's resolver selects rows
`WHERE message_id IS NOT NULL AND respond_ts IS NULL` and calls
`GET /v2/message/{id}`. Rows without a `message_id` are invisible to it forever.

## Change 3 — `turn_id` on both saves

Add to **both** the incoming and the outgoing ingest calls:

```
"turn_id": "={{ $execution.id }}"
```

Same execution = same turn, so pairing is exact regardless of bursts or ordering.
It doubles as the n8n execution id, so the CRM UI can deep-link straight to the
failing execution for triage.

Proactive sends (SLA notices, campaigns) have no incoming message and should simply have
**no `turn_id`** — the CRM excludes those from the SLA denominator rather than guessing.

## Resulting ingest payload

`POST /api/v1/external/chat-history/messages` — new fields marked, all optional:

```jsonc
{
  "channel": "whatsapp",
  "contact_id": "445239409",
  "phone_number": "+60165622487",
  "message": "SRTKS2405 stock level",
  "sent_at": 1784519974000,     // CHANGED: raw respond message.timestamp
  "type": "incoming",
  "message_id": "1784519974000000",  // NEW (was effectively never sent)
  "turn_id": "48213",                // NEW: {{ $execution.id }}
  "first_name": "Johnson",
  "last_name": null,
  "reply_to_message_id": null,
  "reply_to_message": null
}
```

## Acceptance

Keyed to the UAC (`monitoring-enhancement-acceptance-criteria.md`, S4 section):

- **OBS-S4-01** — incoming `sent_at` equals the webhook's `message.timestamp` exactly.
- **OBS-S4-02** — `message_id` present on 100% of new rows, both directions.
- **OBS-S4-03** — incoming and outgoing rows of one turn share a `turn_id`.
- **OBS-S4-04** — a proactive send produces a row with no `turn_id`.

## Test scenarios to simulate

The CRM-side p99 work needs these exercised end to end:

| Scenario | Expected |
|---|---|
| Normal turn, reply within target | paired row, latency < 10s, no alert |
| Slow turn (inject delay > 30s) | `stalled turn` alert (hard ceiling = 3× target) |
| Incoming with no reply at all | `no reply` alert after 5 min |
| Burst: 3 incoming rapidly, 1 reply | each turn pairs by `turn_id`, no phantom breaches |
| Proactive outbound only | excluded from the SLA denominator entirely |
| Failover-sourced incoming (`event_id` prefixed `failover-`) | ingests normally; webhook lag visible as `respond_ts` vs `ingest_at` |

## Sequencing

Independent of the CRM work. Recommended order: CRM migration + resolver ship first
(inert without n8n data), then n8n lands, then the alert thresholds are switched on once
real paired data confirms the p99 curve.
