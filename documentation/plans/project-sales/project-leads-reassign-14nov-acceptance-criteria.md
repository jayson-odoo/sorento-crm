# UAC: Project leads list + reassign back (PROJECT-LEADS-REASSIGN)

Status: DRAFT, provisional on the behaviour card answers (PR #2407). Items tagged [Qn] change if the
answer to question n differs from the recommendation.

## A. One reassign path (backend)

- A1. Approving a secondary lead and the plain owner change (`PUT /projects/{id}` with a new
  `owner_user_id`) both run ONE shared function. Each one moves the owner, keeps the outgoing owner
  as a collaborator [Q3], records one `owner_reassigned` Activity row ("Reassigned from A to B")
  with the actor, and notifies the new and the previous owner [Q5].
- A2. Reassign back: owner S1 -> S2 by approving S2's secondary lead, then S2 -> S1 by the owner
  change. This gives two Activity rows (S1->S2 and S2->S1) and two notification sends, and BOTH
  arrive (the second one is not swallowed by the first one's dedup key). S1 ends as owner and S2
  as collaborator.
- A3. Only `projects.projects.manage` may reassign, on both paths: anyone else gets 403 and
  nothing changes (unchanged rule).
- A4. Same owner as today = no-op: no Activity row, no notification, no collaborator row.
- A5. The project payload carries the primary lead: `primary_owner_user_id` +
  `primary_owner_name` [Q1]. The primary is the first owner at registration. It never changes on
  reassign.
- A6. Backfill [Q1]: for an existing project, the primary is the `from_user_id` of its earliest
  `owner_reassigned` Activity row, else its current owner.

## B. Access card leads list (frontend)

- B1. One list (the shared PanelDataGrid). It holds the primary, then every secondary lead
  (pending, reassigned, dismissed), plus the current owner if the owner is neither [Q4].
- B2. Columns: Salesperson | Lead (Primary / Secondary) | Date | How they found it | Owner (Yes or
  blank) | Status (Pending / Dismissed / blank). Each cell holds one value. Every row is one line
  with truncate + title.
- B3. Primary row: Date = the lead raised date when the project came from a lead, else the
  registration date [Q2]. "How they found it" = the lead source label.
- B4. At 1280px and at 375px the card has no horizontal scrollbar at the default column set.
- B5. A manager right-clicks a non-owner row: "Reassign to <name>" opens the existing
  ReassignProjectDialog with that person preselected. Submitting it moves the owner. A pending row
  also offers "Dismiss". The owner row has no Reassign item. A non-manager gets no Reassign or
  Dismiss items. No action buttons on rows.
- B6. After the primary is reassigned away, the primary row still says Lead "Primary" and Owner
  is blank. Reassigning back to it makes Owner "Yes" again.
- B7. Activity tab shows "Reassigned from A to B" for every reassignment, both directions.
- B8. An inactive primary shows "(inactive)" after the name and offers no Reassign item.

## C. Overview one column

- C1. The Overview tab stacks the cards in one column, full width, at every width, in this order:
  The development, Customer, Value and timing, Parties, Where this came from, Access, Critical.
- C2. Same cards, same fields, same order inside each card as before.
