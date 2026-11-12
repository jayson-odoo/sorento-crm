# Data retention - what the CRM clears and when

The CRM keeps business records (orders, customers, products, quotations, audit history) for
good. Some working data only matters for a while: logs of messages sent to other systems,
step-by-step chat traces, scheduler history, old planning snapshots. Nightly clean-up tasks
clear that working data so the database does not keep growing.

## Where to find it

**System > Scheduled Tasks** (`/system-management/scheduled-tasks`). Each clean-up is its own
task, runs once a day around 2:00 am Malaysia time, and shows its last run, last error and
**Run now**. Open a task's run to see what it removed (the counts).

## What each clean-up does

| Task | Clears | Keeps |
| --- | --- | --- |
| Plan exceptions clean-up | undecided plan exceptions from batches a newer batch has replaced (after one day) | the newest batch of every planning run, and every exception someone decided, with its batch |
| Integration log clean-up | message bodies and headers after 30 days; the whole log row after 180 days | calls still pending or processing |
| API call log prune | request and response bodies after 30 days; the row after 180 days | the same as before |
| Chat turn trace clean-up | the step-by-step trace of chat turns older than 90 days | the turn itself and the chat messages |
| Scheduled task history clean-up | run history older than 90 days | the latest run of every task |
| Old planning runs clean-up | replaced planning runs older than 90 days, with their recommendations | the current run, and any run someone changed or decided on |
| Old AI search data clean-up | AI search text replaced more than 90 days ago | current AI search data |
| Import row detail clean-up | per-row import detail older than 90 days | each import's totals and summary |

Audit history is never cleared.

## What you will notice

* An integration log entry older than 30 days shows no message body; older than 180 days it is
  gone.
* A chat turn older than 90 days has no trace to open.
* An import older than 90 days still shows its totals, but not the row-by-row detail.
* Planning exceptions show the newest batch, as before.

## Common questions

* **"A clean-up shows a run that did not finish."** Each run stops after about 30 minutes and the
  next run carries on where it stopped. The first night after this change can need several
  runs; **Run now** speeds it up.
* **"Can I get a cleared message body back?"** No. Clearing is permanent.
