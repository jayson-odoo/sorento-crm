# UAC: the tail keeps the ideate lane's draft pointer

Plan: `PLAN-chatbot-ideation-pointer-tail-25sep.md`

- AC-1 Dry run keeps the pointer. A console (dry-run) `ideate` turn whose intake tool
  answers a `session_vars.ideation` pointer returns that exact pointer in
  `session_patch["ideation"]`.
- AC-2 Live turn keeps the pointer. A live `ideate` turn leaves
  `respond_contacts.session_vars["ideation"]` equal to the pointer the intake tool
  answered; the tail's write does not replace it with the turn-start value.
- AC-3 Other lanes untouched. A non-ideate turn on a contact that already holds a pointer
  leaves that pointer exactly as it was.
- AC-4 The draft continues. A second dry-run ideate turn, given the first turn's
  `session_patch` as `previous_conversation_state`, sends the first turn's `draft_id` to
  the intake tool, so the shared service updates the same draft instead of minting a
  new one.
- AC-5 Journey on stack A (owner). "i have an idea" then a problem sentence then
  "boleh": one `app_ideation.ideas` row on `fx_shared_local`, the recent-files menu is
  listed once and a reply of "all" attaches, and "yeah" after "Is this right?" stays in
  the ideate lane.
