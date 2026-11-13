# UAC: WA-COMPLAINT-INTAKE (WhatsApp complaint filing, typed submissions)

Plan: `PLAN-wa-complaint-intake-13nov.md`. Owner answers 13 Nov ~19:05: Q1 (a) revive #2095, Q2 (a), Q3 (a)
staff can file too. Q4 and Q5 open: each built behind one switch (default OFF = today's behaviour) so the answer
is a one-line change.

#2095's criteria C-1..C-19 (`documentation/plans/resources/agentic-wa-s2-acceptance-criteria.md`, merged in with
its 45 tests) stay in force unchanged. New rows:

## T: one typed-submission seam

- T-1 Stock inquiry and the dealer complaint both submit through ONE shared function "submit a portal form as the
  contact" (draft -> optional attach step -> `submit_draft`; a refused submit deletes the draft and anything the
  attach step stored; a failure after the submit committed reports the record as sent). No second copy of
  draft/submit/cleanup logic remains in `portal_writes.py`.
- T-2 The complaint fields, their checks (DO, product lines on the DO, lookup values only as the customer said
  them with `data.ask_customer` options, within warranty never defaulted, required-field list) and the confirm
  summary come from ONE complaint type definition, used by both the dealer tool and the staff tool. The two
  differ only in: whose orders a DO may be (T-3 / S-2), who the defaults name, and how the record is created.
- T-3 Behaviour of the dealer tools is unchanged by the refactor (all #2095 + W2 tests green, no assertion
  edited except where this UAC changes the wording).

## S: linked staff file for a customer (Q3 a)

- S-1 A linked staff user holding `complaint_management.complaints.add` is offered the staff complaint tool on
  WhatsApp and in the console; without the slug it is not offered and a direct call is refused (no write).
- S-2 The DO must be the EXACT number of an order the staff user can see (their company scope, and when they
  hold only `view_own`-style customer scope, one of their own customers' orders). Anything else: "Delivery order
  <no> not found." and nothing about another customer.
- S-3 Same questions as the dealer: products on that DO, what is wrong in their words, within warranty asked,
  the other three dropdowns asked with the real options unless said.
- S-4 Defaults: customer name from the DO's debtor; contact person / number = what the staff member gave
  (the site or dealer contact), else the staff member's own name and WhatsApp number; salesperson = the staff
  member's name; complaint date = business day (Asia/Kuala_Lumpur).
- S-5 Confirm first ("yes" on a later turn), then the record is created through the staff create
  (`ComplaintService.create_complaint`), status Submitted with a complaint number (the same numbering the portal
  submit uses), the WhatsApp conversation link set (`respond_inbox_url` from the staff member's contact), and the
  same CS notice as a portal complaint (`notify_team_complaint_external_created`). Audit actor = the staff user,
  via the agent.
- S-6 Photos: the staff member's own chat photos (same read and rules as the dealer's) can be attached; they land
  on the complaint as complaint documents.
- S-7 Console turn = test: proposal shown, "yes" writes nothing, "Test turn: nothing was sent."
- S-8 Reply after filing: "Complaint <number> is with the team." (no undo line for staff: staff edit or void it in
  the CRM).

## P: photo caption routing (Q4, switch, default OFF)

- P-1 Switch OFF: a turn with media goes to the bot exactly as today (`router.py` `has_media`).
- P-2 Switch ON: a turn with an image AND caption text from an agent-eligible contact is classified like a text
  turn (the caption is the text); an image with no caption still goes to the bot. The photo is stored as today
  so the complaint tools can offer it.

## L: confirm card language (Q5, switch, default OFF)

- L-1 Switch OFF: the complaint confirm reads in English as built by code.
- L-2 Every complaint confirm (dealer and staff) shows one fact per line as "Label: value", product code on its
  own line, no ";" chains (standing rule "Label: value").
- L-3 Switch ON: the complaint confirm labels, the "Reply yes ..." line and the after-filing line are in the
  customer's language (en / ms / zh, read the way the bot already reads it); the customer's own words stay
  verbatim; numbers, codes and dates unchanged (dd/mm/yyyy).
