# Troubleshoot a failed notification (email or WhatsApp)

Use this when a user reports "I never got the email" / "the contact didn't get the WhatsApp message", or you need to confirm whether a notification actually went out. It walks the three delivery logs in order and tells you what each status means and what to check next.

This is an admin flow under **System Management**. There are no MCP tools for it — you work the list pages directly.

## First: which channel?

* **Email** → start at **Email Outbox** (the SMTP queue, richest detail), cross-check **Outgoing Mails** (the notification delivery record).
* **WhatsApp / Respond.io** → go to **Respond Outbox**, then **Integration Logs** for the raw response.

---

## Email failed to send

### Steps

1. Open **[Email Outbox](/system-management/email-outbox)**.
2. Set the **Status** filter to **Failed** (and check **Pending** too — a rate-deferred or backed-off email sits in **pending** with a future **Scheduled** time, it does *not* show as "deferred").
3. **Search** by the recipient email or the subject to find the row.
4. Read the row:
   * **Status = `failed`** with **Error** populated → the send hit its attempt cap. The row's **cancel reason** is `max_attempts_exceeded`; the **Error** column has the SMTP failure (bad address, auth, connection).
   * **Status = `cancelled`**, cancel reason `event_disabled` → the email event is switched **off**. Go to **[Email Event Configs](/system-management/email-event-configs)**, find the matching **Event**, and check **Enabled**. Turn it on if it should be sending.
   * **Status = `cancelled`**, cancel reason `cancelled_by_admin` → someone cancelled it manually.
   * **Status = `pending`** with **Scheduled** in the past and **Attempts** climbing → it's being retried/deferred; read **Error** for the rate-limit or transient reason.
5. To resend after fixing the cause, use the row's **Retry** action (re-queues it back to **pending**).
6. To confirm the *notification* side, open **[Outgoing Mails](/system-management/outgoing-mails)**, filter **Status = Failed**, search the same recipient. This is the per-notification delivery record; the drainer writes the outcome (`sent` / `failed`) back here, so it should agree with Email Outbox.

### What the statuses mean

* **Email Outbox** (`email_outbox`): `pending`, `sending`, `sent`, `failed`, `cancelled`. (`failed` = max attempts; `cancelled` = event disabled or admin.)
* **Outgoing Mails** (`notification_deliveries`): `pending`, `sent`, `failed`.

### What to check

* The email **event** is enabled (Email Event Configs) — a disabled event cancels every queued row.
* **Attempts vs max attempts** — repeated failures exhaust the budget and flip the row to `failed`.
* The **email drainer scheduled task** is alive: open **[Scheduled Tasks](/system-management/scheduled-tasks)** and confirm the drainer is **Enabled** with a recent **Last Run** and **Last Status = success**. If nothing in Email Outbox ever leaves `pending`, the drainer is likely down (it is the only process that sends SMTP).

---

## WhatsApp / Respond.io send failed

### Steps

1. Open **[Respond Outbox](/system-management/respond-outbox)**.
2. Set **Status** to **Failed**. (Every Respond send is logged on success **and** failure, so a failed/401'd send *will* be here — an empty list means nothing was attempted.)
3. **Search** by contact name/phone, or filter by **Linked** (`business_table`) for the related complaint / stock inquiry / purchase request.
4. Read the row:
   * **Type** = `text` or `template` — a closed 24h window falls back to a **template**; if it shows `template`, the window was closed.
   * **Status** with a status code — a **`401`** means the workspace API key is bad/placeholder.
   * **Error** / the **View** detail has the raw failure.
   * **Button URL** — inspect for a malformed double-host link if the contact's link is broken.
5. For the full request/response, open **[Integration Logs](/integration-management/integration-logs)**, filter **Channel = (Respond.io)** and **Status = Failed**, and read **response_payload** / **error_message**. If the row is `failed` and still has retries left (`retry_count < max_retry_allowed`), use the **Retry** action.

### What the statuses mean

* **Respond Outbox** / **Integration Logs** (`integration_log`): `success`, `failed`, `pending`, `processing`. A `failed` row often also carries an HTTP **status code** (e.g. `401` auth, `404`, `500`).

### What to check

* **The workspace API key.** Respond sends use the **workspace** key, not the env `RESPOND_API_KEY`. A `401` almost always means a bad key on **[Respond.io Workspaces](/system-management/respond-workspaces)** — verify the right workspace is **Active** / **Default** and its key is correct.
* **The contact resolves.** If contact name/phone is blank, the `respond_io_id` may not match a `respond_contacts` row.
* **Window vs template.** If sends fail only when out of the 24h window, an approved fallback template may be missing for that use case.

---

## Still not sure it ever fired?

If a notification appears in **none** of these logs, it was never attempted — look upstream at whatever should have triggered it (the SLA/complaint/automation flow), not at the delivery logs. For automation-driven emails, check **[Automation](/system-management/automation)** — the last run's **status** (`success` / `partial` / `failed`) and **error** tell you whether the send was even attempted.

## See also

* [System Management — Data reference for admins](data-analysis.md) — full field/status reference for every log.
</content>
