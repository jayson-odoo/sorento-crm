# UAC: WA-COMPLAINT-INTAKE (issue reports on the ideation path, typed submissions)

Plan: `PLAN-wa-complaint-intake-13nov.md` (card v2). Q1 answered (a) real ss `type`; Q2 (who), Q3 (dealers) pending with the owner: rows marked [Q2] follow the
recommendation and change in one place if the answer differs.

## T: one typed seam
- T-1 A submission has a type, `idea` or `issue`, from ONE type table (label, required field, ask-back, reply
  copy). Unknown or missing type = `idea` (today's behaviour unchanged for every existing caller).
- T-2 The bot lane (`handle_capture_turn`) and the agent tool (`crm_idea_create`) both build the ss create through
  `build_create_payload`, which writes the type through ONE mapping function. Q1 (a), crew 13 Nov: a real ss
  `type` field (lane SS-IDEA-TYPE). `issue` -> `"type": "issue"`; `idea` sends no `type` (today's payload
  byte-identical). Reading back: one function maps an ss idea's `type` to the CRM type (missing/unknown = idea).
  No `department` bridge. The staff embed create forwards `type`; the list forwards `type=` to ss.
- T-3 The type is read from meaning: the extractor's JSON schema has `type` (enum idea|issue); the agent tool has a
  `type` argument (enum). No keyword lists, no post-parse word guards. Tests: an EN bug report, a Malay bug report
  with a typo, a feature request, a greeting-prefixed report (model scripted in unit tests; live set separately).
- T-4 Parser routing: a report of something wrong with the CRM or the assistant routes to `ideate`; a complaint
  about a product or an order still routes to `portal_link` (`parser_template.py`).

## I: issue behaviour
- I-1 An issue message with what is wrong creates the item at once (bot lane) / after "yes" (agent), exactly like
  an idea; required field = `problem` (what is wrong).
- I-2 An issue with no description ("I want to report a problem") asks once: "What went wrong? Tell me what you
  saw and where." (en/ms/zh); a second empty answer ends with the give-up line (as ideas).
- I-3 Reply after filing (bot lane), one fact per line, in the user's language:
  `Logged as issue IDEA-0xxx` / title line / `Photos: N` (only when N > 0) / link. An idea keeps today's reply.
- I-4 Agent proposal summary reads "Log issue ..." for an issue, "Log idea ..." unchanged for an idea.
- I-5 Console / dry run: test item as today (`is_test`), no photo upload.

## P: photos
- P-1 Images the same contact sent in the 30 minutes before filing, stored by the media lane (attachments linked
  to `chatbot_turn`, uploaded by that contact) and newer than the contact's previous successful submission, are
  uploaded to the new item as the submitting user through the same function the staff upload route uses.
  At most 10, newest first. Non-images are not sent.
- P-2 A photo upload failure never fails the filing: the item is reported as logged, `Photos: N` counts only the
  ones that landed, and the failure is logged.
- P-3 Photos already attached to an earlier submission are not attached again.

## B: /ideas board
- B-1 /ideas list has a Type column (Idea / Issue), sortable, hideable, one line.
- B-2 A Type multi-select filter: tick Issue -> only issues; tick both -> all; combines with the other filters;
  kept in the address bar like the other filters.
- B-3 The idea detail page shows Type in its metadata.
- B-4 Type is read through ONE frontend helper; an idea with no type data reads Idea.

## A: access (Q2 / Q3 pending)
- A-1 Unchanged gate: linked active CRM user holding `ideation.board.view`; no one else can file (dealers get
  today's answer). [Q2 a] adds a migration granting the slug to the sales roles crew names.

## D: dealers file as their own CRM user (owner 13 Nov 23:03: D1 (a), D2 (b))

- D-1 New permission `ideation.ideas.submit` ("Submit ideas and issues") in the permission registry. A migration
  grants it to role `portal_user`, and grants `ideation.board.view` to role `salesperson` (Q2 a; crew data: the
  31 linked `portal_user` users all also hold `salesperson`). Idempotent, single alembic head.
- D-2 The capture gate (`_access_user`) accepts a linked active user holding `ideation.board.view` OR
  `ideation.ideas.submit`. `ideation.ideas.submit` opens nothing else: every `/api/v1/ideation/*` route still
  needs `ideation.board.view` (a submit-only user gets 403 there).
- D-3 A WhatsApp contact with NO linked user, that is eligible for the assistant (AI access on, exactly one
  contact row for its respond.io id, the same rule the agent uses), filing a real idea or issue (a live turn whose
  extraction has the required field): the bot creates the contact's own CRM user through the existing
  `UserService.create_user` (role `portal_user` only, name and phone from the contact, no password, linked by
  `respond_contact_id`), then files as that user. Audit names the WhatsApp assistant as the creator. Reply as for
  staff.
- D-4 No user is created for: an ask-back with no idea yet, a held similar-list answer, a read failure, an
  unconfigured workspace, a test (console) turn, an ineligible contact (AI access off, duplicate contact rows),
  or a contact whose respond.io id is unknown. A test turn by an unlinked dealer answers "Test turn: nothing was
  sent." and writes nothing.
- D-5 Two messages at once never create two users (unique `respond_contact_id`): the second filing reuses the
  first user.
- D-6 A dealer's second filing reuses its user (no second create); its earlier items are "mine" in ss.
- D-7 No CRM sign-in for a user whose roles are all non-staff (`portal_user`, `guest`): phone OTP and the
  portal-link session exchange refuse it (`phone_signin_service._eligible_user_clauses` /
  `eligible_user_for_contact`). Users holding any staff role (e.g. `salesperson` + `portal_user`) sign in as today.
- D-8 The dealer keeps its dealer bot: a contact whose linked user's roles are all non-staff stays a CONTACT
  principal in the agent (`agent/access.py` `linked_active_user` / `build_context`), with today's dealer tools,
  knowledge audience and scope. Users with any staff role are unchanged (user principal).
