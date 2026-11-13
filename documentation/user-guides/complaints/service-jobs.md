# Service jobs (send a technician to the site)

Use a service job when a complaint needs someone on site. You raise the job from the complaint, agree a date with the customer, send a technician, and record the visit until the work is verified. Service Jobs, Dispatch Board and Technicians are under **Complaint Management** in the sidebar.

## Steps

### 1. Fill in the complaint's Site

1. Open the complaint and press **Edit**.
2. In the **Site** section fill **Address line 1**, **Address line 2**, **Postcode**, **City**, **State**, **Country**, **Contact on site** and **Contact phone**, then save.
3. If the Site is still empty, **Address line 1** starts with the customer's delivery address. Nothing is saved until you save the complaint.

The complaint page shows the same fields in a **Site** card, in the same order. A field with no value shows "-". The job page shows this same Site, so fix an address on the complaint, not on the job.

### 2. Raise a service job

1. Open the complaint, open the gear menu at the top right and choose **Raise service job**.
2. The job appears in the complaint's **Service Jobs** section as a number such as SV26/11-0001 (SV, year, month, then a running number), with status **Proposed**.

Good to know:

* **Raise service job** is only offered while the complaint has no live job. A job is live until it is **Verified** or **Cancelled**. After that you can raise a new one (for example for a second visit months later).
* You can raise a job on a complaint in any status, including closed or rejected ones.
* A resolution marked **Requires service job** raises the job for you. When you set that resolution on a complaint and save, a job is raised automatically (if there is no live job already). Setting any other resolution, or clearing it, never creates or removes a job. To mark a resolution, go to Complaint Management, **Resolutions**, open it and tick **Requires service job** (the list has a column with the same name).
* Click the job's line in the **Service Jobs** section to open it. Each line shows the number, status, scheduled date and technician.

### 3. Move the job along

A job page has a header with the job number and status, two tabs (**Details** and **History**), a gear menu and one filled button, which is always the next step. Press it and the job moves on.

| Status | What it means | Main button | What moves it |
|---|---|---|---|
| **Proposed** | Raised, no date agreed yet | **Confirm date** | Confirming the date |
| **Confirmed** | Customer agreed a date | **Assign technician** (if none yet), then **On the way** | Assigning, then pressing On the way |
| **On the way** | Technician has left | **Arrived** | Pressing Arrived |
| **Arrived** | Technician is on site | **Complete** | Pressing Complete |
| **Completed** | Work done, not yet checked | **Verify** | Pressing Verify |
| **Verified** | Checked and accepted | none | Finished |
| **Cancelled** | Visit called off | none | Finished |

**Confirm date.** The **Confirm date** dialog asks for **Date**, **Time** (for example 10:00 am) and **Agreed by** (the name of the customer person who agreed). All three are needed. Pick the date from the calendar, written dd/mm/yyyy, for example 15/11/2026.

**Assign technician.** The **Assign technician** dialog has one **Technician** field. You can only pick an active technician. To swap technicians later, open the gear menu and choose **Change technician** (offered while the job is Proposed or Confirmed). History keeps the earlier technician.

**Gear menu moves.** Besides the main button, the gear menu offers what the status allows:

* **Cancel** (Proposed or Confirmed): asks for a **Reason**.
* **Customer rejected the visit** (Confirmed or On the way): the job goes back to **Proposed** and asks for a **Reason**. The agreed date and "Agreed by" are cleared, the technician stays, and the first try stays in History.
* **Revisit needed** (Arrived): same, back to **Proposed** with a **Reason**, for when the technician must come again.
* **Reopen: work not accepted** (Completed): the job goes back to **Arrived**.
* **Arrived** (Confirmed, with a technician): skips On the way.
* **Open complaint**: jumps to the complaint.

## Why can't I mark Arrived (or On the way)?

* The job has no technician yet. The main button on a Confirmed job reads **Assign technician** until you pick one. Assign first, then **On the way** and **Arrived** appear.
* The job is still **Proposed**. Confirm a date first. Moves only go in the order in the table above, so a Proposed job cannot jump to Arrived.
* The job is already **Completed**, **Verified** or **Cancelled**. For a Completed job use **Reopen: work not accepted**.
* You do not have the dispatch permission (see "Who can do what").

## How do I send a technician?

1. Make sure the technician exists under **Technicians** and is active.
2. Raise the job from the complaint (or let a "Requires service job" resolution do it).
3. Open the job, press **Confirm date**, fill the date, time and who agreed, and confirm.
4. Press **Assign technician** and pick the person.
5. On the day press **On the way**, **Arrived**, **Complete**, then **Verify** once the work is accepted.

## Where are jobs waiting for a date?

Open **Dispatch Board**. The **Waiting for a date** card on top lists every job still in **Proposed**, oldest raised first, whichever day you pick. Or open **Service Jobs** and filter **Status** to **Proposed**.

## Dispatch Board

* Pick a day with the date picker (dd/mm/yyyy), or use **Previous**, **Next** and **Today**.
* Below **Waiting for a date** you see one column per technician with a job that day, with the **Unassigned** column first. Jobs are listed by time.
* A card shows the job number, time, city and status. Click a card to open the job. Nothing is edited on the board itself.
* A Confirmed job is never in **Waiting for a date**, because it already has a date.

## Service Jobs list

* Columns: **Job no.**, **Complaint no.**, **Status**, **Scheduled**, **Technician**, **City**, **Customer**. Click a header to sort (ascending, descending, off).
* **Search service jobs...** looks at job number, complaint number, customer and city.
* Filters: **Status** (**All statuses**, pick several), **Technician** (**All technicians**, pick several), and **Scheduled from** / **Scheduled to** dates. Filters combine.
* Click a row to open the job. The previous and next buttons on the job follow the list's filters and sort.
* Right-click a row for **Open complaint**, the job's next step, **Change technician** and the gear moves that status allows.
* There is no Create button: a job is always raised from its complaint.

## Technicians

Open **Technicians**.

1. Press **Create**, fill **Name** (required), **Phone** and **Type** (**Employee** or **Contractor**), and save.
2. Right-click a technician and choose **Edit** to change them. It opens the same dialog.
3. **Archive** makes the technician inactive (the list shows **Inactive**). An inactive technician is not offered on **Assign technician**, but their old jobs keep their name. **Restore** makes them active again.
4. **Delete** is offered only for a technician who has never been on a job. It runs as a countdown with a Cancel, with no confirmation box. A technician who has been on any job cannot be deleted: archive instead.

## History tab

Open the job's **History** tab to see, newest first, who did what and when: the job being created, the date confirmed and who agreed it, technician changes (old to new), and every status change with its reason. After a rejected visit, the first date and technician are still here.

## What's captured

* On the job: job number, status, scheduled date and time, who agreed, technician, arrived, completed and verified times, and the reason for any rejection or cancellation.
* On the complaint: the Site.
* Times are shown as dd/mm/yyyy, h:mm am/pm (Malaysia time).

## Who can do what

* **Service jobs view**: see Service Jobs, Dispatch Board, the technician list and a complaint's Service Jobs section.
* **Service jobs dispatch**: raise a job, confirm a date, assign or change a technician, and make every status move.
* **Technicians manage**: create, edit, archive and delete technicians.

Roles that can already edit complaints get all three. If a menu item is missing or a button does nothing, ask your admin to check the role under User Management.

You only see jobs for complaints you are allowed to see.

## How you'll be notified

Nothing is sent to the customer or the technician yet. Share the date and time yourself (phone or WhatsApp). The result of each step shows on screen and in History.

## Bulk import

Not available.

## See also

* [Complaints data reference](./data-analysis.md)
* [Complaint lifecycle and next actions](../technical-team/complaint-lifecycle-and-next-actions.md)
* [Set root cause and resolution](../technical-team/set-root-cause-and-resolution.md)
