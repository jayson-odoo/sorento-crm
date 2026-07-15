# Email Guardrail Stress Test

Run timestamp: 2026-05-16T14:35:20.677729Z

## Executive summary

The incident scenario (S1) — 50 attachment-linkage callbacks for one recipient — now produces **1 outgoing email(s)** instead of 50. The producer-side coalesce window collapses the burst into a single outbox row that lists every attachment, and the hard rate-limit guardrail backstops any future code path that re-introduces a per-record sender.

## Results

| Scenario | Pass | Enqueued | SMTP sends | Coalesce ratio | Final statuses |
|---|---|---|---|---|---|
| **S1** Burst of 50 attachment-linkage callbacks to same recipient (incident reproduction) | PASS | 50 | 1 | 50.0x | {"sent": 1} |
| **S2** Burst of 500 mixed events / 60s | PASS | 500 | 132 | 1.0x | {"pending": 379, "sent": 121} |
| **S4** 100 events to single recipient with per-recipient cap=10/hour | PASS | 100 | 10 | 1.0x | {"pending": 90, "sent": 10} |
| **S5** Simulated SMTP outage for 4s then recovery | PASS | 20 | 15 | 1.0x | {"pending": 5, "sent": 15} |

## Pass criteria detail

### S1
- PASS — Enqueued = count (50 == 50)
- PASS — Coalesce ratio >= 10x (proves burst collapsed) (ratio=50.0x)
- PASS — SMTP sends <= 2 (smtp=1)
- PASS — No terminal failures ({'sent': 1})

### S2
- PASS — Enqueued = 500 (500)
- PASS — SMTP rate inside 60s window <= cap (first-60s sends=60 cap≈90)

### S4
- PASS — Sent <= per-recipient cap (sent=10 cap=10)
- PASS — Non-sent stay pending (not lost) ({'pending': 90, 'sent': 10})

### S5
- PASS — No rows stuck in 'sending' ({'pending': 5, 'sent': 15})

## Operator runbook

- **Silence a noisy event**: System Management -> Email Event Configs -> toggle `enabled` off for the offending event_key. Existing pending rows auto-cancel at drain.
- **Drain a backlog faster**: System Management -> Settings -> bump `email_outbox_drain_batch_size` and reduce `email_outbox_drain_interval_seconds` (stay under provider connect rate).
- **Investigate a failed row**: open `/system-management/email-outbox/{id}` for full body, error_message, and attempt history. 'Retry' re-arms the row immediately.
