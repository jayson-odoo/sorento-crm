# Requirements inbox - 2026-08-01

Captured verbatim-in-substance from the review session, **before grilling**. Nothing here is designed.
Each item carries my first read and what has to be decided. Do not implement from this file.

The two flows these attach to (`adr/0011`):
- **Exchange / return request** - Dealer asks to return or exchange goods. Commercial.
- **Service complaint** - a fault needing attendance, spare parts or a plumber.

---

## Exchange / return request

**R1 - CS gates the request.** After a Dealer submits, Customer Service approves or rejects before
anything moves. *Read:* a status-engine transition guarded by a role, plus the Assess stage clock.
*Grill:* can CS partially approve (some lines yes, some no)? The discovery study says items can be added to
an existing RMA, which implies line-level granularity.

**R2 - A pending reason, so a request does not read as "stuck at CS".** The office may be unable to
proceed for reasons outside CS: awaiting maintenance, awaiting a plumber, awaiting the customer. Needs to be
visible as *why* it is waiting, not as CS inaction.
*Read:* a `pending_reason` on the case plus a distinct "waiting" state, so the SLA clock and the dashboard
both show the real owner. *Grill:* does a pending reason **pause the SLA clock** or merely annotate it?
This is the crux - pausing is what makes the metric fair, and it is also how SLA metrics get gamed. The
existing engine has `extension_count` / `extension_days_total`, which may already be the right mechanism.

**R3 - RMA is optional against a request.** A return or exchange may be settled without an RMA ever being
raised. *Read:* the RMA link is nullable and the case can close without one, which matches the study's
"nothing to collect, or cannot be collected back". *Grill:* what closure conditions are legitimate without
an RMA, and does closing without one need a reason?

**R4 - Collection notification with photo acknowledgement.** When collection is arranged, notify the
Dealer; the Dealer must acknowledge **and upload photos as proof**.
*Read:* an acknowledgement transition that requires attachments, reusing typed photos from after-sales S6.
*Grill:* is acknowledgement a hard gate (no collection until the Dealer acknowledges) or advisory? What
happens when they never acknowledge - the study's "the RMA stays open" is exactly this failure.

**R5 - Identify from the photos.** Identify (presumably the product, its condition, or that it matches the
claim) from the uploaded photos.
*Grill:* **this is underspecified and I will not guess.** Identify *what*, against *what*, and what happens
on a mismatch? Candidates: confirm the model matches the claimed SKU; confirm the defect is visible;
confirm the goods are the ones collected. Each is a different feature with different failure behaviour.

---

## Both flows

**R6 - Nothing submitted to CS gets missed.** The stated priority is the front of the funnel.
*Read:* already largely answered - the Acknowledge stage notifies the assigned CS member on creation and
escalates on breach (`AC-E3a`, `AC-E3b`). *Grill:* is there a "nobody is assignable" case, and what
happens then?

**R7 - Coloured pending tasks on the dashboard.** SLA risk visible at a glance.
*Read:* extend the existing pending-task surface with risk colouring. *Grill:* colour by what - time to
due, breach state, or pending reason? Colour must never be the only signal (accessibility, and the
code-review rule already forbids it).

**R8 - Overdue requires a reason.** Options named: pending maintenance, pending plumber, pending customer.
*Read:* configurable master data, not an enum in code - the study also asks for "dropdowns, not free text".
Same list plausibly serves R2. *Grill:* is the reason mandatory at breach time (blocking) or captured
after? And is R2's pending reason the same vocabulary as R8's overdue reason, or two lists?

**R9 - Track calls.** Record calls made to this customer about this case.
*Read:* a call log against the case - who called, when, outcome, next action. Phone calls are a real
intake and follow-up channel per the study ("end user by email, call or service group"), and today they
leave no trace. *Grill:* manual entry only, or is there any telephony to integrate? Manual is assumed.

**R10 - Google Maps pin on the consumer form.** The submitter pins their location rather than only typing
an address.
*Read:* store a lat/long alongside the address on the Site; the technician's job screen already shows a
maps link. The chat log already has people pasting `maps.app.goo.gl` links by hand, so this formalises
existing behaviour. *Grill:* which maps provider and whose API key; whether a pin is required or optional;
and what happens when the pin and the typed address disagree.

**R11 - Plumbers are outside the system, but their charges are recorded.** A plumber is not a user, not a
technician record, and gets no portal - but what Sorento pays them is tracked.
*Read:* a cost line on the case naming an external party, feeding the study's open costing question ("how
does Ms Tan know the cost of a complaint"). *Grill:* is the plumber a master record (so spend per plumber
is answerable) or free text per case? Master record is more useful and more work. Also: does this connect
to the chargeable-callout state, or are they independent - one is what we pay out, the other what we
charge in.

**R12 - The customer can reject the technician's visit, sending it back to scheduling.** *Read:* a
rejection transition on the Service Job returning it to *Proposed* with a reason, keeping the original
attempt in history rather than overwriting it. This is why the job has its own clocks (`adr/0009`).
*Grill:* does a customer rejection count against the technician's attend-time metric? It should not, and
that means rejections need to be excluded explicitly or the metric punishes the wrong person.

---

---

# Grill outcomes

## R2 / R7 / R8 / R12 - RESOLVED 2026-08-01: attribute, do not pause

**The complaint was attribution, not timing** - "so it doesn't say it is stuck at CS" means the dashboard
blames CS for a delay CS does not own. So the clock is left alone and a `waiting_on` dimension is added:

```
waiting_on_party    cs | maintenance | plumber | customer | supplier | warehouse
waiting_on_reason   FK to configurable master data (dropdowns, not free text)
waiting_since       timestamp
```

- **R2** the row reads "waiting on maintenance since 3 Aug", not "stuck at CS".
- **R7** colour driven by breach risk, **with the waiting party shown as a label** - colour is never the
  only signal (accessibility, and the code-review rule forbids it).
- **R8** `waiting_on` becomes **mandatory once overdue**.
- **R12** a customer rejecting a visit sets `waiting_on = customer` on the Schedule stage; the Service Job
  returns to *Proposed* with the rejected attempt kept in history, and rejected attempts are **excluded**
  from the technician's attend-time metric.
- **One shared reason vocabulary** for R2 and R8. "Pending plumber" is the same fact whether or not the
  clock has expired, and two lists would drift.

**The clock is never paused.** Pausing makes "how long did this take from the customer's point of view"
unanswerable - their toilet is broken whether or not our clock is running - and it is the classic gamed
metric, where a queue parked on "pending customer" reports perfect SLA. When a deadline genuinely must move,
that is **Extend** (`plans/PLAN-sla-extend-deadline.md`, already grilled 2026-06-24: resolution clock only,
reason required, soft limits, fully audited).

**Accepted consequence:** SLA numbers will look worse, because time waiting on a plumber still counts.
Mitigated by attribution - the report can say "of 40 breaches, 26 were waiting on an external party",
which is more useful than a clean number that hides them.

## R1 / R3 - RESOLVED 2026-08-01: the grain is the line, not the request

**Line-level state and disposition. An RMA is a cross-request collection container. The request's status is
derived from its lines.** Forced by the SOP: *"items can be added onto an existing RMA"*, and the
local/outstation rule (*"for local, REP can be done before RMA; for outstation, must RMA first"*) means one
request's lines do not all move together.

- The **six dispositions are per-line**: write-off, CN/cancellation, replacement same model, replacement
  equivalent value, replacement wrong model, repair, maintenance.
- CS may **approve some lines and reject others**. Whole-request approval breaks as soon as one of three
  items is written off and another replaced, which the disposition list guarantees.
- **Derived header status has precedent**: `complaint_fulfilment_service` already recomputes a header from
  its children including the reopen case (*"a `processed_by_cs` complaint becomes `fulfilled` once every
  non-cancelled linked DO is delivered; reopens if a non-delivered DO links"*). Same shape - the request
  closes when every line reaches a terminal disposition, and reopens if a line returns.

**R3 - RMA is optional because it is a line attribute.** A line settled by **CN alone** (customer cancelled,
money returned) never needs collection. A line where nothing can be collected takes an explicit
**"nothing to collect"** disposition that **requires a reason** - the study names this as the exact failure
where RMAs stay open forever and nobody closes them. A line's siblings are never blocked by it.

## R4 / R5 - RESOLVED 2026-08-01: readiness gate + a core attachment validator

**The photos are proof of readiness before dispatch, not proof of handover after it.** The failure the SOP
describes is a truck arriving and finding nothing collectable (*"Goods there and collectable? -> Not ready
-> Re-arrange collection"*).

**R4: acknowledgement gates collection scheduling.** No collection is scheduled until the Dealer
acknowledges with photos. Safe **only because of the R2 outcome** - an unacknowledged request sits at
`waiting_on = dealer` with `waiting_since`, so the delay is visibly theirs and CS is not blamed. CS may
override (*collect anyway*) **with a reason**.

**R5 is configuration, not a second AI feature.** The photo validator generalises out of `service_jobs`
into a **core attachment validator** living with attachments in the **`resources` module** (not literally
`base`: core is one module today, and `resources` owns attachments and is already a dependency of
`complaints`, `service_jobs`, `procurement` and `marketing`).

`attachment_types` is **already the per-type upload policy table** (`allowed_extensions`,
`max_file_size_mb`, `max_count_per_entity`, `supports_field_linkage`). Extend it - **no new tables**:

```sql
ALTER TABLE attachment_types
  ADD COLUMN validation_guidance text,   -- what "correct" MEANS for this type; the AI's input
  ADD COLUMN min_score numeric(3,2),
  ADD COLUMN validate_on_upload boolean NOT NULL DEFAULT false;
```

**`service_job_photo_types` and `service_job_photos` are deleted from the S6 design** - they were a special
case of a general thing. Photos become ordinary attachments whose type carries guidance, with `ai_score`,
`ai_suggestion`, `override_reason` and lat/long on the link row. This is a **simplification** of the earlier
plan. R5's three checks (model matches the claim, quantity matches, defect visible) become guidance text on
a new `rma_readiness` type.

## R11 - RESOLVED 2026-08-01: generic external provider, bookkeeping only

**A generic external-provider master with a `provider_type` discriminator** (plumber, contract technician,
courier, ...), not a plumber-specific table - the study already shows the role blurring (*"forward the
details to the plumber; can be an outstation technician"*).

- **Not `suppliers`.** That carries purchasing semantics (payment terms, lead times, SPO linkage) and would
  couple after-sales to `procurement` for no benefit.
- Cost lines carry case, provider, amount and **what it was for** (labour / parts / travel) - one number per
  complaint would not answer the study's costing question.
- **Money out is independent of money in.** A warranty job can be free to the consumer and still cost
  Sorento a plumber fee, so this is never part of the chargeability state.
- **Bookkeeping, no approval step.** Recording is free; reporting surfaces outliers. An approval queue for
  small amounts would add friction where CS already gates the case.

## R6 / R9 / R10 - RESOLVED 2026-08-01

**R6 - nobody assignable.** Route to a configured fallback (after-sales team lead) and flag the case
`assignment unresolved` on the dashboard. **Never silently unassigned** - an unassigned case with a running
clock is the exact failure this requirement exists to prevent. Machinery exists:
`resolve_team_with_tier_fallback`, and `AC-B10` already does this for an unresolved salesperson.

**R9 - call tracking. Manual-first; automatic attribution is deliberately not attempted.**

A call **cannot** be tied to a case automatically in the general case - a dealer can have five open cases at
once, and a wrong attribution puts false evidence into the record CS relies on. Note the existing system
makes the same compromise for messages: `entity_conversation_messages` is entity-keyed for internal notes,
while the Respond WhatsApp thread is **contact**-keyed and merely surfaced on the case via
`respond_inbox_url`. Nobody ties individual messages to cases either.

- A **`call` activity** in the existing `activities` module (per-entity feed alongside notes and the chat
  panel). **No new table.** Logged by whoever made or took the call: outcome + next action.
- **One safe automatic case:** if the contact has **exactly one open case**, auto-attach. More than one ->
  leave it in a per-contact call inbox for one-click attachment. Deterministic, and it mirrors the
  conversation-SLA rule of one open conversation per contact.
- **VERIFIED 2026-08-01: Respond.io exposes calls** via the n8n node's **`On Call ended`** trigger (one of
  11, beside message/conversation/contact events). **n8n owns the subscription** and calls a CRM write MCP
  tool `call_log_submit`, idempotent on the call id - same shape as `complaint_intake_submit`.
- **The attribution rule does not change.** The event is contact-keyed and carries no case reference, so
  auto-attach still applies only when the contact has exactly one open case. The webhook fills the same model
  automatically; it does not make attribution solvable.
- **Record the outcome, not the event.** `answered` / `missed` / `no_answer` plus duration - **a call that
  ended is not a call that connected**, and the whole point of R9 is evidence that contact was made
  (*"customer didn't receive any call from maintenance"*). Repeated unanswered calls are what legitimately
  justify `waiting_on = customer`.
- **Still unverified:** the `On Call ended` **payload shape** (direction, duration, outcome, handler,
  recording) needs one test call; and the installed node is **1.12.0 (Legacy)** with an update available, so
  confirm the trigger survives on the current package.

**R10 - Google Maps pin. Confirmed.** Store `latitude`, `longitude`, `place_id` **and** the typed address on
the Site. **Pin optional** - never blocks a submission. **No conflict reconciliation:** the pin is what the
technician navigates to, the address is what appears on documents, both kept. No pin -> geocode the address
at dispatch. The key must be **HTTP-referrer restricted**, since a public portal key is scrapable.

---

## Cross-cutting observation

R2, R7, R8 and R12 are all the same underlying gap: **the system currently cannot express "waiting on
someone who is not us"**, so every delay looks like internal inaction and every metric blames whoever
holds the record. That is worth designing once, coherently, rather than four times - and it is the most
valuable thing in this list.
