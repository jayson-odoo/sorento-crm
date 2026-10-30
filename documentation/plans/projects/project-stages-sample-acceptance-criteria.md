# UAC: project stages follow the document, Sample Submission included

Plan: `PLAN-project-stages-sample-28oct.md`. Card: `CARD-project-stages-sample-28oct.md`.
Status: FINAL - owner answers 28 Oct ~19:45 (card section "Owner answers").

Graph under test = the prod-shaped default project graph (rungs identified, registered, specified,
sample_submission, final_negotiation, sponsorship_form, po_received, lost, dormant with prod's 16 edges).
Tests build it themselves; CI's seed has quoted / tendering instead.

## Ladder (migration)

- AC-PS-01: After the migration, the default project graph has these manual edges, each exactly once:
  specified -> sample_submission "Sample submitted"; sample_submission -> final_negotiation "Final negotiation";
  final_negotiation -> sponsorship_form "Sponsorship"; sponsorship_form -> po_received "PO received";
  final_negotiation -> po_received "PO received"; sample_submission -> specified "Back to Spec In";
  final_negotiation -> sample_submission "Back to sample submission"; sponsorship_form -> final_negotiation
  "Back to final negotiation"; final_negotiation -> lost "Mark lost"; final_negotiation -> dormant "Mark dormant";
  sponsorship_form -> lost "Mark lost"; sponsorship_form -> dormant "Mark dormant".
- AC-PS-02: Running the migration twice adds nothing the second time; an edge an admin already made is kept
  as is (label untouched, no duplicate).
- AC-PS-03: On a graph without these rungs (fresh seed: quoted / tendering) the migration adds nothing and
  does not fail.
- AC-PS-04: The 16 existing edges and every rung's label, sort order and flags are unchanged.
- AC-PS-05 (Q5): win % and stale days of every rung are unchanged (Final Negotiation / Sponsorship Form stay empty).
- AC-PS-06: Downgrade removes every default-graph project edge matching one of the 12 exact (from, to, label)
  triples (so an admin edge with the same from, to AND label goes too; there is no marker column); every other
  edge, including an admin edge with the same from and to but another label, is kept.

## Header (manual moves)

- AC-PS-10: A project at Spec In shows one header button "Sample submitted"; "PO received", "Back to
  registered", "Mark lost", "Mark dormant" sit in the gear menu.
- AC-PS-11: At Sample Submission the button is "Final negotiation"; gear menu has PO received, Back to Spec In,
  Mark lost, Mark dormant.
- AC-PS-12: At Final Negotiation the button is "Sponsorship"; gear menu has PO received, Back to sample
  submission, Mark lost, Mark dormant.
- AC-PS-13: At Sponsorship Form the button is "PO received"; gear menu has Back to final negotiation, Mark
  lost, Mark dormant.
- AC-PS-14: Each click moves the project, the pill shows the new label, and the history shows a stage change.
- AC-PS-15 [Q2]: No move skips a rung forward except PO received, Mark lost, Mark dormant (the server refuses
  e.g. Spec In -> Final Negotiation with 422).
- AC-PS-16: The pills for Sample Submission, Final Negotiation and Sponsorship Form are coloured, not the grey
  fallback.

## The stage action opens the form (Q1, Q4: mirror Spec In -> quotation)

- AC-PS-20: Clicking "Sample submitted" on a Spec In project moves it to Sample Submission, then opens New
  Sample Request with this project already filled in.
- AC-PS-21: Clicking "Sponsorship" on a Final Negotiation project moves it to Sponsorship Form, then opens New
  Sponsorship Form with this project already filled in: the "Registered project" picker SHOWS the project as
  "<project code> - <title>" (not the search placeholder, never a UUID), and an empty "Project Title" field is
  filled with the project's title (a typed one is never overwritten).
- AC-PS-22: Clicking "Spec In" on a Registered project still moves it and opens the new quotation page (unchanged).
- AC-PS-23: Back moves (Back to Spec In, Back to sample submission, Back to final negotiation, Back to registered)
  and Final negotiation, PO received, Mark lost, Mark dormant move the project and open no form.
- AC-PS-24: A refused move shows the error and opens no form; the project stays where it was.
- AC-PS-25: Leaving the opened form without saving keeps the project at the new stage (same as Spec In today).
- AC-PS-26: The form opens only from the project page's stage action; dragging a card on the pipeline board moves
  the stage and opens nothing (as with Spec In today).
- AC-PS-27: Opening New Sponsorship Form with no project in the link (from the Sponsorship Forms list) works as
  before, project empty.
- AC-PS-28: A rung whose key is not one of the three form rungs (including an admin key such as "toString")
  opens no form.

## First PO

- AC-PS-30: The first PO on a project at Final Negotiation or Sponsorship Form moves it to PO Received
  (`status_moved_to_po_received` true).
- AC-PS-31: The first-PO behaviour from every other rung is unchanged.

## Text surfaces

- AC-PS-40: The projects list descriptions (route `status_key` Query, MCP `crm_projects_list`, analytics connector)
  name sample_submission, final_negotiation, sponsorship_form, and nowhere in those descriptions say quoted or
  tendering (examples included).
- AC-PS-41: The `only_critical` text describes the critical (management involved) flag as independent of the
  Final Negotiation stage (Q3), not "the Final Negotiation flag, not a stage".
