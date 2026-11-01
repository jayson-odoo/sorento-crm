# Let the AI answer from uploaded documents

Use this when you want staff or WhatsApp contacts to ask the AI about a document you uploaded in
Resources (an employee handbook, a warranty policy, a product guide, a technical specification).
The AI answers only from the document and cites it, for example *(Warranty Policy, p.1)*.

## Steps

1. Open **Resource Management > Attachment Types** (`/resource-management/attachment-types`).
2. Edit the type the document belongs to.
3. Set **AI can read**:

   | Option | Who the AI answers from these documents |
   |---|---|
   | **Off** (default) | Nobody. The AI never reads the type. |
   | **Staff only** | Staff in the Console agent and the AI side panel, if they may open the file in Resources. |
   | **Dealers** | Staff, plus WhatsApp contacts with a dealer or office access code that the file's access levels include. |
   | **Everyone** | Staff, plus every WhatsApp contact whose access code the file's access levels include (end users too). |

4. Optional: set **Escalate to** to the team staff should ask when a staff question is not in the
   documents. WhatsApp contacts are handed over differently, see "When the document has no
   answer" below.
5. Save. Every file of that type is read in the background.

## What's captured

Each file shows a **Read by AI** row on its detail page and in the Files modal:

* **Queued** or **Processing**: the read is running (the row refreshes by itself).
* **Done**: with the number of pages read, and how many were scanned pages read by OCR with an
  estimated cost.
* **Failed**: with the reason. **Read again** appears for a failed file if you may upload files.
* **Not supported**: the file type cannot be read (PDF and DOCX are read).

Limits: 300 pages, 100 scanned pages, per file. A longer file fails with a readable reason.

## Who sees what

* A document of a **Staff only** type never reaches a WhatsApp contact, whatever its access levels.
* A WhatsApp contact reads a file only when the file's **access levels** share a code with the
  contact's access codes. For a **Dealers** type the contact's end user code does not count.
* A contact with no access code reads no document.
* A file of another company is not read for a contact outside that company; a shared type is read
  for every company.
* Switching a type back to **Off**, deleting a file or moving it to another company takes effect
  on the next question.

## When the document has no answer

The AI never fills a gap from general knowledge.

* Staff: the reply says the answer is not in the documents and names the **Escalate to** team.
* WhatsApp contacts: the reply is *"I couldn't find that in our product documents."* followed by
  * *"Would you like me to pass this to our marketing product team?"* when **Chatbot hands over to support teams** is
    on for the contact. If they answer yes, the usual hand-off to the marketing product team runs.
  * *"Please refer to your salesman."* when that switch is off for the contact.

## How you'll be notified

Nothing is sent when a file is read. Check the **Read by AI** row.

## See also

* [The agent on WhatsApp](./chatbot-agent-on-whatsapp.md)
* [Chatbot Console and Agent mode](./chatbot-console-agent-mode.md)
* [Upload flow](../_shared/upload-flow.md)
