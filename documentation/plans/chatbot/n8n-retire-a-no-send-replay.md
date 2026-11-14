# N8N-RETIRE-A: no-send replay of past n8n sender runs

Owner, 12 Nov about 16:15: "yeah you can do no-send replay to verify, just don't send any messages
to user". Crew runs it on the Mac against real past n8n executions (read-only) and posts aggregates
only. The repo holds the tool, synthetic fixtures and tests; never a real execution.

## Run

```
cd sorento_crm_backend
SORENTO_ENV_FILE=<local env> venv/bin/python scripts/crm_sender_replay.py --in <folder of execution JSON> [--out report.md] [--json]
```

## Input: one JSON file per n8n sender execution

```
{
  "id": "<any label, not a customer value>",
  "sender_input": { "turn_id": "...", "contact_id": "...", "actions": [...], "ctx": {...}, "is_test": false },
  "respond_requests": [ { "method": "POST", "url": "https://api.respond.io/v2/contact/id:X/message", "body": {...} }, ... ]
}
```

`sender_input` is the body the n8n `chatbot-sender` webhook received. `respond_requests` are the
respond.io calls n8n made for it, in order, gathered from the sender execution and its sub-workflow
executions (sendmsg, send-attachments). Assembling these from n8n's execution store is crew's
step; the tool reads only this shape.

## What it does

1. Refuses to start (non-zero exit, nothing run) unless the database host in the settings is
   loopback.
2. Blocks Python sockets for the whole run: any `socket.connect` / `create_connection` raises
   `ReplayNetworkBlocked`. (The database driver's own C connection is not a Python socket; the
   run's database writes are rolled back, see 4.)
3. For each file, runs `crm_sender.send` on `sender_input` with a FAKE respond.io client that
   records every call and answers success with an invented message id, and a fake presign that
   returns a marked URL. Nothing leaves the process.
4. All database writes (log rows) happen inside one transaction that is rolled back at the end.
5. Normalises both sides into request descriptors and compares them in order.

## Descriptor per request (no text, names or phones)

`kind` (text / quick_reply / attachment / assign / comment / contact_update / other), `bytes`
(UTF-8 length of the text or title; 0 otherwise), `units` (UTF-16 length), `buttons` (count),
`attachment_type`, `has_file_name` (bool), `presigned` (bool: the url was a presigned one).

## Output

Per execution: `SAME` when both sides have the same number of requests and every descriptor
matches in order; else `DIFF` with, per index, the fields that differ (values are kinds, counts,
lengths, booleans only). Totals: executions, SAME, DIFF, ERROR (input unreadable or the CRM side
raised), and per field how many requests differed. `--json` prints the same as JSON. No message
text, contact id, url, name or phone is ever printed: a test greps the output for every string
value of the input.
