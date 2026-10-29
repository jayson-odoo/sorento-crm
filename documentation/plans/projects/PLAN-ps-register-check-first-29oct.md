# PLAN: PS-REGISTER-CHECK-FIRST (29 Oct 2026)

Status: Planning. Track M (feature track, local lane). Behaviour card + Lavish mock filed for owner approval;
build waits for owner approval AND #1953 (PORTAL-P4-REQUESTS) merge. Merge origin/main again once #1978
(PS-WORDING) lands (both edit `ProjectForm.tsx`).

Card: `CARD-ps-register-check-first-29oct.md`. UAC: `ps-register-check-first-acceptance-criteria.md` (written after
the owner answers the card). Mock: `documentation/mockups/PS-REGISTER-CHECK-FIRST/index.html`.

## Journey

Owner team meeting 29 Oct (Project Sales):

1. A salesperson registers a project themselves; the registration admin only approves or rejects.
2. The duplicate Check runs FIRST, before any other detail is typed (a wizard). A match collapses the form to one
   action: "Register as secondary lead" (today's "Register interest", renamed: owner Q1, no new concept, no second
   lead row). Management reviews competing secondary leads on the project.
3. A requirements document is part of the project record for the audit trail. Not required at register; required
   to move the project out of Registered (owner Q5: "it is required after registering, so the state moves one by
   one").

## Scope

1. Wizard on the register form: step 1 = title (+ AI extract) and a mandatory Check; step 2 opens only after a
   Check with no blocking match; a match collapses the form to "Register as secondary lead".
2. Rename "interest" to "secondary lead" everywhere it shows (form, dialog, Access panel, Reassign dialog,
   notifications).
3. "Requirements" document kind on the project; server guard: Registered -> next stage refused without one, plain
   message, upload shortcut on the stage action.

Out of scope: required-vs-optional registration fields (management confirms Mon 2 Nov; keep today's, keep the
step-2 field list easy to change); lead-name uniqueness (card Q-A).

## Architecture

(filled after the card is answered: layer, shared mechanism, classes fixed)

## Slices

(filled after the card is answered)

## Test list

(filled after the card is answered; red-first: BE stage guard, rename, Check-before-step-2)
