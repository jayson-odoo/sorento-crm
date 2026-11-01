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
question the bot just asked, and any message after the daily cap still go to the bot. Switching
**Agent mode (auto)** off returns the contact to the bot.

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

  It makes no changes and does not read the CRM user guides.
* **A contact linked to an active CRM user** (staff) is answered as that user, with that user's
  permissions, exactly like Agent mode in the Chatbot Console.

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
the router chose, and counts once in chatbot analytics.

## See also

* [Chatbot Console and Agent mode](./chatbot-console-agent-mode.md)
* [Let the AI answer from uploaded documents](./ai-reads-uploaded-documents.md)
* [Escalate a task or enquiry](../_shared/escalate-a-task-or-enquiry.md)
