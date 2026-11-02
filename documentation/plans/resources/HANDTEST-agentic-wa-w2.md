# HANDTEST: AGENTIC-WA-W2 slice 1, dealer requests on WhatsApp

Revision 3 (2 Nov). Supersedes the crew-handtest comments on PR #2072 (revisions 1 and 2). Step 7 changed because the
published `chatbot_router` v1 sent the old English sentence to the bot on both console passes (Jev 0.14, then 0.02),
and WhatsApp has no Agent toggle. Every phrasing below is one that crew's router measure (PR #2072 comment
6562121453, single runs on v1, floor 0.70) saw reach the agent; scores drift between runs.

## URL
crew test copy

## Setup
- Branch head 46c97d94 or later. No migration. Worker running. Respond egress BLOCKED for the whole test.
- The test contact must have ALL of these:
  - **AI replies allowed** and **Agent mode (auto)** on;
  - no linked CRM user, one contact row only for its respond.io id;
  - at least one stored real inbound turn (the console borrows its envelope);
  - the Stock Inquiry portal form left on (the default).
- CODE below is one active product code in the contact's brands (SRT5733 on the dev copy; there its name equals its
  code, so the summary reads `SRT5733 (SRT5733)`).
- The console's Prompt version picker defaults to the newest `full` parser version (v148 on the dev copy), not the
  production one `/health` reports (189). That is by design and only affects bot replies; leave it.

## Steps
Console part (a console turn is a test, nothing is written):
1. Sign in, open **System > Messaging > Chatbot Console** from the sidebar, and pick the test contact.
2. Press **New conversation**, so no stale bot question holds the message on the bot (owner ruling W2-Q4 (a)).
3. Switch the **Agent** toggle on, then send: `can I get 40 pcs CODE by 15 Dec 2026 for project Test Tower?`
4. Read the reply.
5. Send: `yes`
6. Open **Stock Inquiries** from the sidebar and search for CODE.

WhatsApp part (test contact, egress blocked; there is no Agent toggle, the router decides):

7. Send: `CODE 我要40个，帮我问一下项目销售团队交期`
8. Open the contact's **Chat History** and read the reply and its route.
9. Send `yes`.
10. Open **Stock Inquiries** and open the new row.
11. Within 10 minutes, send: `undo that inquiry please`
12. Send `yes`.
13. Open **Stock Inquiries** again and search for CODE.
14. Send `CODE 我要5个，帮我问一下项目销售团队交期`, then `yes`. Wait 11 minutes, then send `undo that inquiry please`.
15. Send: `for my stock inquiry today, the customer can only take delivery on Tuesday, please add that`, then `yes`.
16. Open that stock inquiry's comments.
17. Send: `what requests have I sent you and what is their status?`
18. On the contact's page, switch the Stock Inquiry portal form off for the contact. Then send step 7's message again.

If the bot answers step 7 instead of the agent (route `chat` on the Chat History row; the reply is a stock, order or
"not under your account" answer and has no confirm block): send step 7 once more, since single router scores drift.
If the bot answers again, record step 7 as **NOT RUN: router (published v1)**, not as a FAIL, and go on with a stock
inquiry made another way: submit one for CODE from the test contact's portal (Stock Inquiry form), then do steps 11
to 13 within 10 minutes of that submit, and steps 15 to 17. Steps 11 and 15 to 17 were measured reaching the agent
on v1 (0.98, 0.98, 0.76).

## Expected
- 4: The reply contains (the agent may add its own paragraph above it):
  > I will make these changes when you confirm:
  > 1. Send a stock inquiry to the project sales team: CODE (product name), 40 pcs, needed by 15 Dec 2026, project Test Tower, requested by you.
  > Reply yes to go ahead, or tell me what to change.
- 5: The reply ends with "Test turn: nothing was sent."
- 6: No new stock inquiry (same row count as before step 3).
- 8: Route **agent** (router `classified`, Jev about 0.88 in the measure). The reply contains the confirm block:
  "1. Send a stock inquiry to the project sales team: CODE (product name), 40 pcs, requested by you." (no date or
  project: this message gives none). The words "agent mode" never appear.
- 9: The reply contains "Stock inquiry <number> is with the project sales team. Reply undo within 10 minutes to withdraw it."
- 10: Status Pending project sales; requested by the test contact; quantity 40.
- 11: Route agent. The reply proposes "Withdraw stock inquiry <number> (sent N minutes ago). It is deleted and the project sales team no longer sees it."
- 12: Done. In 13 the row from step 10 is gone.
- 14: After 11 minutes: "It is with the team now, so I can't withdraw it. I can add a note to it instead."
- 15: Route agent. A confirm block 'Add this note to your stock inquiry <number>: "the customer can only take delivery on Tuesday"' (the agent may word the note from the dealer's message). After the yes, step 16 shows that note from the contact.
- 17: Route agent. A list of the contact's own submitted requests with their numbers and statuses.
- 18: No stock inquiry confirm block. With the form off the contact has no stock inquiry tool, so the bot answers it or the agent says it cannot do this here and suggests the salesman.
- Throughout: nothing is sent to Respond beyond the blocked egress.

## Known limit (owner to read)

On the published router v1 most English and Malay stock inquiry phrasings go to the bot (crew's measure: 1 of 9
stock-inquiry rows reached the agent; notes, undo and the request list did). The wording fix (variant B) failed its
gate and is not published (`documentation/plans/chatbot/PROPOSAL-router-dealer-requests-01nov.md`). A follow-up lane
takes it up after #2072, shaped by the owner's si-1 answer.
