# UAC: N8N-RETIRE-A, the CRM sends bot replies

Plan: `PLAN-n8n-retire-a-bot-reply-12nov.md` (same folder). Owns parent UAC lines 1, 2 and 7 of
`documentation/plans/infra/n8n-decom-ha-acceptance-criteria.md` for the reply-sending job.

## Switch

1. A fresh install and every existing install read "Bot replies sent by: n8n". With that value a
   customer turn goes out exactly as today: one POST to the workspace's chatbot sender, same body,
   same headers, same log row.
2. An admin sets "Bot replies sent by: CRM" on Settings > Chatbot and saves; the page shows CRM after
   a reload. Setting it back to n8n takes effect on the next reply, with no deploy and no restart.
3. Only a user who can edit the chatbot settings can change it.

## Sending with the switch on CRM

4. A customer asks the bot a question; the reply reaches the customer once, with the same text, the
   same quick-reply options and the same attachments the n8n sender would have sent, in the same
   order. No request goes to the n8n sender URL.
5. A long reply that the engine split into parts arrives as those parts, in order.
6. A turn that hands the customer to staff assigns the conversation and posts the internal comment
   (with the staff mentions) exactly as the n8n sender did.
7. Every respond.io call the sender makes leaves one integration log row, success or failure.
8. A contact whose outbound messages are switched off gets nothing; the turn shows the plain reason.
9. With no n8n sender URL on the workspace, a covered contact is still answered (the CRM sender
   counts as configured).

## Failures and Try again (owner 11 Nov)

10. respond.io refuses a part (or cannot be reached): that part is not marked sent; the drain tries
    again a bounded number of times; if it still fails the turn shows "Failed" with the plain reason
    and Try again.
11. A part times out: the CRM looks the message up in the conversation before doing anything else.
    Found: it counts as sent and is not sent again. Not found: it is sent again. Lookup fails: the
    turn shows "Not confirmed" with the plain reason and Try again.
12. Try again on that turn sends only the parts not yet confirmed; the customer never gets a part
    twice.
13. A part that respond.io confirmed is never sent again by any retry, recovery or restart.
14. A bot turn that fails before any reply is composed sends the customer the failure reply the n8n
    error workflow sent (wording per the behaviour card).

## Rollback

15. Switching back to n8n while a turn is mid-send finishes that turn on the path it started on;
    the next turn goes through n8n.
