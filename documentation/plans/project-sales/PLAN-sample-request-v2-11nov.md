# PLAN: sample request v2 (lane SAMPLE-REQUEST-V2)

Status: Plan. Behaviour card + mock being written; no code until the owner approves. Track: full (size L).

Owner feedback 11 Nov 2026 ~16:20 MYT (prod Project Sales > Sample Requests > New): ship to is a project
party (not free text), customer stays mandatory from the AutoCount debtor, many sample requests per project,
contact person behaves like project registration, form restructured guided like the price tag request.

Behaviour card: `CARD-sample-request-v2-11nov.md` (this folder).

## Owner addition 11 Nov ~16:30 MYT (rule, no question)

"after i submit sample request, i should come back to my project right? depending on where I go into the
sample request from of course". Today Submit / Save draft push `/project-sales/sample-requests/<id>`
(`sample-requests/components/SampleRequestForm.tsx:249, :263`) and Cancel pushes the detail or the list (`:493`).

Rule: Submit, Save draft, Cancel and Back return to where the user started.
- Started from a project (Samples Request tab Create `[projectId]/components/SampleRequestsPanel.tsx:122`, or
  the sample_submission stage action `[projectId]/components/ProjectDetailClient.tsx:124`) -> back to
  `/project-sales/<projectId>?tab=sample-requests` with the success toast.
- Started from the Sample Requests list -> back to the list.
- Mechanism: the existing Project Sales origin pattern, `?from=<same-app relative path>` read with
  `useReviewOriginHref` (`project-sales/_shared/hooks/useReviewOrigin.ts:13`), guarded by
  `isSafeReviewOrigin` and built with `withReviewOrigin` (`project-sales/_shared/lib/reviewOrigin.ts:23, :33`),
  as the PO intake / SO review flows already do (`POIntakeConfirmClient.tsx:54, :125`). An unsafe or missing
  `from` falls back to the list. No new mechanism.
- The limited salesperson's portal-form path (`SampleRequestForm.tsx:107-119`) gets the same return.
