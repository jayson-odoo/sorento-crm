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
| "SRT5733, I need 40 pcs, please ask your project sales team for the lead time." | A **Stock Inquiry** goes to the project sales team, requested by the contact itself, with the product, quantity and any date, project or note the dealer gave. | "undo" within 10 minutes withdraws (deletes) it, as long as nobody on the team has responded to it, taken it, commented on it or moved it on. After that the agent replies *"It is with the team now, so I can't withdraw it. I can add a note to it instead."* |
| "For my inquiry last week, the customer can only take delivery on Tuesday" | A note on one of the dealer's own submitted requests (stock inquiry, complaint, purchase request or sponsorship form). The team sees it on the form's comments. | The dealer can ask to remove their own note. |
| "ELP3754 from DO2026-01234 is leaking after 3 months, still under warranty, photos above" | A **Complaint** (warranty claim) goes to the team, filled the way the portal's complaint form fills it, with the photos the dealer sent in the chat. | "undo" within 10 minutes withdraws (deletes) it, with its photos, as long as nobody on the team has touched it. After that, the same sentence as for a stock inquiry. |
| "Here are 2 more photos for that complaint" | The newer chat photos are added to the dealer's own open complaint. | The dealer can ask to remove a photo they added. |
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

Each WhatsApp message is still routed one at a time, and today many ways of asking for a stock inquiry
are answered by the bot as a stock check, with no confirm block. If that happens, the dealer can submit
the inquiry from their portal; notes, undo and "what have I sent" questions do reach these requests.
A plain "can I get 40 pcs?" is always a stock check that the bot answers.

Not over WhatsApp (yet): purchase requests, sponsorship forms, sample and price tag requests,
orders, and changes to the contact's own details. The agent says it cannot do these here and
suggests the dealer's salesman.

## Warranty claims and complaints with photos

The agent files the same **Complaint** the dealer would file on its portal, with the same required
fields and the same checks. It needs four things from the dealer and asks for any that is missing:

* the **delivery order number**. It must be a delivery order of one of the customer accounts linked
  to the contact (**Contact Details**). Any other number gets *"Delivery order <number> not found."*;
* the **product code(s)**, each on that delivery order;
* **what is wrong**, kept in the dealer's own words and language;
* whether it is **within warranty**, as the dealer says it. The agent never fills this in itself.

Everything else is filled as the portal form fills it: today's date, the dealer as salesperson and
as contact person (unless the dealer names a site contact) and the customer from the delivery order.
Complaint type, defects discovered and customer type take the dealer's answer, chosen from the same
options the portal form shows; where the form has a default (set in the lookup admin) and the dealer
says nothing, the default is used. Without a default the agent asks, listing the real options, and
it never picks one for the dealer. An answer in Malay or Chinese is understood when the option has a
matching keyword in the lookup admin; otherwise the agent asks again.

**Photos.** The agent can attach photos the dealer sent in the WhatsApp chat in the last 24 hours
(up to 10 to choose from, and no more than the portal's own limit per complaint). It can only use
photos the bot kept: photo reading must be turned on for the contact's number and its monthly
allowance not used up (see [Chatbot - photos and voice notes](./chatbot-media-intake.md)). A
photo the bot tried but could not read is still kept and can be attached. Documents, videos and voice notes
are not attached; the dealer adds those on the portal.

The confirm block lists each value and each photo, with the time it was sent and what it shows,
so a photo that is not part of the claim can be spotted before the yes:

> I will make these changes when you confirm:
> 1. File a warranty / complaint claim: DO DO2026-01234; ELP3754 x1; "leaking after 3 months"; within warranty: Yes; complaint type: Product defect; ...; date 2026-11-02; salesperson Tan; photo 1 (2 Nov 10:02): ELP3754, water stain under the basin; photo 2 (2 Nov 10:04): could not be read.

After the yes the reply gives the number: *"Complaint CMP-... is with the team. Reply undo within
10 minutes to withdraw it."* The team is told as for a portal complaint.

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
