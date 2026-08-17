# Lead to sales order: what to walk, and what to expect

Written 2026-08-02, overnight. Branch `feat/project-lead-to-so`, unpushed, unmerged.

## Before you start: TWO THINGS OR NOTHING WILL SHOW

**1. Switch the company to Sorento.** Your account opens on Mocha, and every screen below
will be correctly, silently empty until you switch. Top bar, company chip, pick "Sorento
SRT". This cost me twenty minutes last night; it will cost you the same.

**2. The stack is already running.** Frontend on `localhost:3010` as a production build,
backend on `:8010`, and an RQ worker draining the `project_docs` queue. If the worker is
not running, uploads will sit on "queued" forever and look broken:

```
cd sorento_crm_backend
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES WORKER_QUEUES=project_docs venv/bin/python worker.py
```

Extraction is a paid call to Gemini and takes roughly two minutes for a ten page scan.
That is normal, and the screen tells you where it is up to.

## What is already seeded

Project `PRJ-000001 TUJU RESIDENCE AT J`, filing reference `PS26-0143`, with quotation
`QT-004188` and all sixty of its real lines. Two leads: `LEAD-000001` waiting to be
accepted, and `LEAD-000002` with no buyer at all.

Re-seed or reset at any time:

```
cd sorento_crm_backend
venv/bin/python scripts/seed_project_cs_demo.py --reset
```

It deletes only what it creates, by natural key. There is no unscoped delete in it.

---

## 1. Lead generation

**Project Sales → Awaiting Acceptance.** One row: Residensi Bukit Raja Phase 2, waiting
"1 day", assigned to you, and under "Told us" the informant with their BCI reference.
Assignment is not ownership: the lead sits here until somebody accepts it.

Try: nudge, or hand it to somebody else.

**Project Sales → Leads.** `LEAD-000002` has NO buyer, deliberately. A lead now records
who told us separately from who will eventually buy, because those are usually different
people and requiring a buyer meant inventing a customer to get past the form.

Open it, accept it, or decline it with a reason. Declining returns it to the pool, and
whoever raised it can hand it on.

Then create your own lead with the wizard: development first, then who told us, then the
detail with the buyer optional, then who to hand it to.

## 2. Project management

**Project Sales → Pipeline → PRJ-000001.** Overview carries the filing reference. Tabs for
Quotations (QT-004188, sixty lines, 1,805,907.02), plus the three new ones below.

## 3. Upload the PO

**POs tab → "Upload a PO document"**, and give it
`sorento_crm_frontend/e2e/fixtures/project-cs/customer-po-buimaco-r1.pdf`.

You land on the confirm screen while it reads. About two minutes for ten pages.

What I saw when I ran it last night, live:

- 10 pages, 51 lines, every one of them passing `qty x unit price = amount`
- PO number `HQ/26/01/121`, term 60 days, sales person VALERIE, your ref
  `SLG/23/C/TUJU/LOA/2025/10`
- "Our sum of the lines matches the document total, RM 1,810,640.62"
- "14 of 51 lines need attention" (mostly products absent from the catalogue, see below)
- The pencil read verbatim: **"15/5/26 - Cancel item (7) due to Changed the price. Refer to
  New P/O HQ/26/05/087"**, and under it, in plain words: "Cancels line 7 (SRTFV100, 16 NOS,
  RM 4,733.60). The line stays on the record, marked cancelled, and drops out of our total."

**The number that matters.** 1,810,640.62 minus the cancelled 4,733.60 is 1,805,907.02,
which is the quotation's printed grand total to the cent. The PO proves itself against the
quotation, and neither number was typed by anybody.

Line 7 is NOT cancelled until you accept that card. That is deliberate: nothing the pencil
says changes a line until a person agrees with it.

Try: the "problems only" toggle above the lines, accept the cancellation card, and watch the
totals sentence change rather than stay red.

## 4. Upload the delivery schedule

**Delivery schedules tab → upload**
`e2e/fixtures/project-cs/delivery-schedule-buimaco-r1.pdf`, against the PO you just
confirmed.

Every product column shows three numbers: our total of the cells, the schedule's own printed
TOTAL QTY, and the PO quantity. Measured on this document, 35 of 37 columns reconcile on the
first pass; you fix the rest by editing cells, and a column flips as you type.

Both stragglers are explained rather than hidden: one column has no printed total at all
(the customer wrote it as prose), and one page carries a row its label column does not show.

## 5. Produce the sales orders

**Sales orders tab → Build**, choosing the schedule version. Sets explode into a priced
parent and its zero-priced companions, quantities spread across the delivery phases, and the
area split is proposed rather than imposed.

Five hard findings block a publish, all arithmetic. Everything else is a warning that
publishes once you type a reason, and the reason stays on the order forever.

## 6. The revision, and the delta

Upload `delivery-schedule-slg-r2.pdf` (note: issued by SLG, a different company from the PO,
which is why the issuer is asked and not assumed). Then **Sales orders → the draft →
Revisions**, pick the new version, and Compare.

One sentence answers the only question worth asking: "Dates only. 12 lines move; quantities,
prices and products are unchanged." Hide the date moves to see the exceptions. Anything that
could not be matched across the two versions gets its own section rather than vanishing.

Creating the amendment auto-drafts an order change notice from the same delta. Both wait for
review; nothing is applied until you publish it.

---

## What is NOT built, so you do not go looking

- Allocation, the order inquiry Excel and the SCM handoff, pre-order and sponsorship paths,
  the ESB swap and real AR figures, and divergence reconciliation. Publish stops at
  producing the AutoCount import file.
- Merging two drafts. Splitting and moving lines work; merge needs an endpoint.
- SLA escalation when a lead is ignored. The waiting time is visible; nothing chases it yet.

## Known rough edges, honestly

- **14 of 51 lines "need attention" is mostly the catalogue, not the reading.** Six of the
  sixty quotation lines resolve to no product: a connector and a bottle trap that are not in
  the item master, one truncated description, and a code that exists only with a suffix. I
  left them unresolved on purpose so the draft raises them.
- **`item_packages` has one row in this database**, so set explosion mostly exercises the
  quotation fallback rather than the AutoCount package authority.
- **Line count moved between runs**, 52 in the spike and 51 last night. The totals are
  identical to the cent, so nothing was lost; the model split two lines differently. Worth
  knowing before you count rows.
- **Two delivery-schedule columns share one product code** and currently merge. Fine for
  demand, wrong for reconciliation, and being fixed.
- **The lead endpoints reject the API-key principal** while the project endpoints accept it.
  Harmless in the browser, but the two routers guard themselves differently and one of them
  is wrong.
- The schedule slice has no route-level tests and its upload path is covered only by the
  live walk I did last night, not by an automated test.

## Where the work is

Fifteen commits on `feat/project-lead-to-so`. Nothing pushed, nothing merged, no deploy.
392 frontend tests and 147 new backend tests pass. The contract every slice was built
against, including every correction the screens forced, is
`documentation/plans/CONTRACT-project-lead-to-so.md`.
