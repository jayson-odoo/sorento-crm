# PLAN - From a lodged retail complaint to a technician at the door

**Status:** Drafted, not started. Supersedes nothing; extends S6 (Service Jobs).

## Journey (Phase 0)

The actor is **Agnes**, CS. A retail complaint has just landed from the consumer portal.

1. She opens the complaint. The products are listed as the consumer described them, with
   whatever the extractor matched.
2. She sets **root cause** and **resolution**. Some resolutions mean somebody has to go to
   the site; most do not. She should not have to remember which.
3. Where a visit is needed, a **service job already exists** by the time she looks - raised
   by the resolution she picked, carrying the site the complaint reported.
4. She needs a **date**. The consumer is a person with a job, so this is a phone call, not
   a form. She triggers the call from the complaint, speaks to them, and the call is
   recorded against the job so the next person knows it happened.
5. She types the date they discussed and presses **Propose**. The consumer gets a WhatsApp
   message: this date, **Confirm** or **Reject**.
6. The consumer taps Confirm - the job becomes Confirmed with no further typing by anyone.
   Or they reject, and we ask for a time that suits them, and capture the reply.
7. **Only then** is a technician assigned. Sending one before the customer has agreed a
   date is the wasted van this whole slice exists to prevent.
8. The dispatcher sees the month at a glance and knows who has capacity.

Every step above is a decision Agnes makes. Nothing here asks her for something the system
already knows: the site comes from the complaint, the contact from the token, the date from
the conversation.

## What already exists (verified, not assumed)

| Piece | State |
|---|---|
| Service job entity, 7-state graph, assignments, costs | Built (S6) |
| `confirm_job` refusing a date without an agreement (AC-F5) | Built |
| Respond.io send + template send + outbox logging | Built (`_send_and_log`) |
| WhatsApp **template** sends with variables | Built (SLA notifications use them) |
| Inbound Respond webhook -> CRM | Built (message ingest) |
| Complaint root cause / resolution master data + pickers | Built |
| Warranty policy engine (kinds, terms, assessments) | Built, **no admin UI** |

## The one unknown that changes a design

**Does Respond.io expose call history through its API?**

The client in `integration_service.py` uses `v2/contact/*` for contacts, messages,
conversation status/assignee, channels and templates. There is **no call endpoint in use,
and I have not confirmed one exists.** Respond.io is a messaging platform; calls may be
absent entirely, or may appear as events inside `v2/contact/{id}/message/list`.

This must be settled by probing the live workspace before slice S8 is designed, because the
two outcomes are different features:

- **Calls appear in the message list** -> we can link a real call record to the job.
- **They do not** -> "trigger call" becomes: open the Respond conversation for the contact
  (a deep link we already build) and have Agnes record the outcome on the job herself. That
  is still worth building - it keeps the date and the fact of the call on the record - but
  it is a logged action, not an integration, and it must not be described as one.

Building the optimistic version without checking would produce a call log that silently
stays empty.

## Slices

### S7a - Resolution decides whether a visit is needed
Add `requires_service_job` (bool) to `complaint_resolutions`. Setting a resolution that
requires one raises the job automatically, copying the complaint's site, exactly as the
manual "Raise service job" button does today - same service, no second path. Idempotent:
a complaint that already has an open job gets no second one (a duplicate reads as a revisit
in every report that counts them). Admin edits the flag on the existing Resolutions master
data screen.

**Why config and not a hardcoded list:** the resolutions are Sorento's vocabulary and they
add to it. A code change per new resolution is a change nobody will make in time.

### S7b - Warranty policy configuration (the "is it within policy" gap)
The engine is complete and answers per part per line. What is missing is the ability to
maintain what it reads: 31 kinds, 41 terms, **2 kind rules**. Two rules for thirty-one
kinds is why most reported products reach no Kind and therefore get no verdict - the
feature looks broken and is actually unconfigured.

CRUD for Policies (versioned, dated), Terms (per kind per part), Kinds, and Kind Rules
(category / model prefix / model list / series, with priority). Backend routers + admin UI.
This is the largest slice and it is worth its own review.

### S8 - Propose a date, and let the customer answer
1. `proposed_scheduled_from` on the job, distinct from `scheduled_from`: a date we
   suggested is not a date anyone agreed to, and collapsing them recreates the
   "Service Date: TBA wearing a Confirmed badge" failure S6 exists to prevent.
2. **Propose** sends a WhatsApp template with Confirm / Reject buttons, through the same
   template path SLA notifications use.
3. Inbound webhook maps the reply back to the job:
   - Confirm -> `confirm_job` with `customer_agreed_by = "Consumer on WhatsApp"`, no typing.
   - Reject -> ask for a preferred slot, capture the reply, park the job as waiting on the
     customer (S4a's vocabulary, already wired).
4. **Assignment gated on Confirmed.** Today the graph allows assigning a proposed job; that
   is the wasted van. Gate it in `assign_technician`, not only in the UI.

Open question for you: a rejected date with a counter-proposal in free text needs parsing.
Structured buttons for a few slots is more reliable than reading "can ah, but after 5pm
lah" - worth deciding before building.

### S9 - Calendar dispatch board
Month view by default, each day a block showing its jobs; click a day for a time-of-day
view per technician; click a job for a popup with a link to its page and inline edit.
Replaces the current single-day columns, which cannot answer "who has capacity next week" -
the question a dispatcher actually asks.

Keep the stall list: it is the one thing a calendar hides, because a job with no date
appears on no day.

## Order

S7a (small, unblocks the journey) -> S7b (largest, independent) -> S8 (needs the unknown
settled) -> S9 (pure UI, can run in parallel with S7b).
