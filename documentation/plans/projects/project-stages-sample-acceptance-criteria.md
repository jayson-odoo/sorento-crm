# UAC: project stages follow the document, Sample Submission included

Plan: `PLAN-project-stages-sample-28oct.md`. Card: `CARD-project-stages-sample-28oct.md`.
Status: DRAFT on the card's recommended answers; final once the owner answers Q1-Q5.

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
- AC-PS-05 [Q5]: Final Negotiation gets win 85 % / stale 7 days and Sponsorship Form 90 % / 7 days only where
  the value is empty; a value an admin set is kept.
- AC-PS-06: Downgrade removes only the edges this migration added.

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

## Automatic move on sample request submit [Q1]

- AC-PS-20: Submitting the first sample request linked to a Spec In project moves the project to Sample
  Submission; staff form and portal both.
- AC-PS-21: The project history shows the stage change with the sample request number.
- AC-PS-22: A second submitted sample request does not move the project again.
- AC-PS-23: A project at Final Negotiation, Sponsorship Form or a terminal rung is not moved (never backwards).
- AC-PS-24: A project at Registered or Identified is not moved (no legal edge) and the sample request still
  submits.
- AC-PS-25: A sample request with no project submits as before.
- AC-PS-26: If the graph has no Sample Submission rung, the request submits and nothing moves.
- AC-PS-27: Saving or cancelling a draft never moves the project.
- AC-PS-28: After submitting from the project's Sample requests tab, the project header shows Sample Submission
  without a manual reload.

## First PO

- AC-PS-30: The first PO on a project at Final Negotiation or Sponsorship Form moves it to PO Received
  (`status_moved_to_po_received` true).
- AC-PS-31: The first-PO behaviour from every other rung is unchanged.

## Text surfaces

- AC-PS-40: The projects list `status_key` description (route, MCP `crm_projects_list`, analytics connector)
  names sample_submission, final_negotiation, sponsorship_form and no longer promises quoted / tendering.
