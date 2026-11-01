# The agent on WhatsApp

Use this to let a WhatsApp contact be answered by the agent (the assistant behind the Chatbot
Console's Agent mode) instead of the normal bot, one contact at a time.

## Steps

1. Open **Respond.io Contacts** and the contact (**Contact Details**, **Chatbot** card).
2. Make sure **AI replies allowed** is on.
3. Switch on **Agent mode (auto)**. It is off by default. You need permission to edit contacts.
4. Optional: set **Agent turns per day** for the contact (empty uses the global value).

From the contact's next WhatsApp message, every text message goes to the same router as the
Chatbot Console. It picks the agent or the bot per message. Photos, voice notes, a reply to a
question the bot just asked (its offer to pass a question to a team included), and any message
after the daily cap still go to the bot. A reply to a request the agent is waiting on (see below)
goes to the agent. Switching **Agent mode (auto)** off returns the contact to the bot.

## What the agent can do for a contact

* **A contact with no linked CRM user** (most dealers and end users) is answered as that contact.
  It reads only what the bot already gives the same contact:
  * product lookups and product lists for the contact's brands;
  * incoming stock;
  * stock, purchase order, last cost and sales figures, each only when the contact holds that
    field reveal on its page, as for the bot;
  * uploaded documents the contact may read (see
    [Let the AI answer from uploaded documents](./ai-reads-uploaded-documents.md)), answered with
    a citation such as *(Warranty Policy, p.1)*.

  It does not read the CRM user guides. The only changes it makes are the requests listed under
  [Requests a dealer can make over WhatsApp](#requests-a-dealer-can-make-over-whatsapp).
* **A contact linked to an active CRM user** (staff) is answered as that user, with that user's
  permissions, exactly like Agent mode in the Chatbot Console.

## Requests a dealer can make over WhatsApp

A contact with no linked CRM user can ask the agent for these. They are the same requests the
contact makes on its portal, and they follow the contact's portal forms: a form switched off
for the contact on its page is not offered over WhatsApp either.

| The dealer asks | What happens | Undo |
| --- | --- | --- |
| "Please send a stock inquiry for 40 pcs of SRT5733, needed by mid December." (A plain "can I get 40 pcs?" is a stock check: the bot answers it.) | A **Stock Inquiry** goes to the project sales team, requested by the contact itself, with the product, quantity and any date, project or note the dealer gave. | "undo" within 10 minutes withdraws (deletes) it, as long as nobody on the team has responded to it, taken it, commented on it or moved it on. After that the agent replies *"It is with the team now, so I can't withdraw it. I can add a note to it instead."* |
| "For my inquiry last week, the customer can only take delivery on Tuesday" | A note on one of the dealer's own submitted requests (stock inquiry, complaint, purchase request or sponsorship form). The team sees it on the form's comments. | The dealer can ask to remove their own note. |
| "What did I send you?" | A list of the dealer's own submitted requests with their numbers and statuses. | - |

Every request is shown first and needs a yes:

> I will make these changes when you confirm:
> 1. Send a stock inquiry to the project sales team: SRT5733 (product name), 40 pcs, needed by 15 Dec 2026, requested by you.
>
> Reply yes to go ahead, or tell me what to change.

After the yes the reply gives the request number, for example *"Stock inquiry SI-26-0001 is with
the project sales team. Reply undo within 10 minutes to withdraw it."* An unanswered request
expires after 10 minutes and nothing is sent. The project sales team is told about a new stock
inquiry as when it comes from the portal. An email it was already sent stays sent after a
withdraw, and its link then opens no record.

Not over WhatsApp (yet): warranty claims and complaints, purchase requests, sponsorship forms,
sample and price tag requests, orders, and changes to the contact's own details. The agent says
it cannot do these here and suggests the dealer's salesman. For complaints the bot still sends the
portal link.

In the Chatbot Console these requests are a test: the yes shows what would happen and the reply
ends with *"Test turn: nothing was sent."* Nothing is created, changed or deleted.

## Ideas sent by staff over WhatsApp

A linked staff contact can log an idea through the agent. The agent shows the idea and asks for a
yes first. On a WhatsApp message the confirmed idea is a real idea on the Ideas board. An idea
made from a Chatbot Console turn stays a test idea and does not appear on the board.

## When the agent cannot answer

* No answer in the documents: *"I couldn't find that in our product documents."* followed by
  *"Would you like me to pass this to our marketing product team?"* (**Chatbot hands over to support teams** on) or
  *"Please refer to your salesman."* (that switch off for the contact).
* The agent could not finish: *"I couldn't finish this one just now. Please send your question
  again in a minute."* The bot does not answer that message instead.
* A contact sending many messages in a short time is limited to 30 agent answers per 10 minutes.

## What's captured

Each WhatsApp message the agent answers is recorded on the contact's Chat History with the route
the router chose, and counts once in chatbot analytics. The audit log records a dealer request the
agent made as made by the contact, through the agent.

## See also

* [Chatbot Console and Agent mode](./chatbot-console-agent-mode.md)
* [Let the AI answer from uploaded documents](./ai-reads-uploaded-documents.md)
* [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md)
