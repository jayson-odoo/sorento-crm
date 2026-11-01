# Let the AI answer from uploaded documents

Use this when you want staff or WhatsApp contacts to ask the AI about a document you uploaded in
Resources (an employee handbook, a warranty policy, a product guide, a technical specification).
The AI answers only from the document and cites it, for example *(Warranty Policy, p.1)*.

## Steps

### Let the AI answer dealers from a document type

1. Open **Resource Management > Document Access** (`/resource-management/document-access`). There is one row per document type.
2. Find the type (use **Search types...**). On its row, tick **Staff** to let staff ask the AI about it, and tick one box under each access type whose WhatsApp contacts may read it (for example a dealer access type).
3. Each tick saves at once. A toast tells you how many documents that access type can now read, for example *Warranty Policy: Sorento Dealer can now read 12 documents.*
4. An amber figure such as **12/15** on a ticked box means 12 of the type's 15 readable documents carry that access type in their access levels. The other three are not read for it until you fix them (see "Fix one document's access levels" below).
5. Optional: open **Resource Management > Attachment Types**, edit the type and set **Escalate to**, the team staff should ask when a staff question is not in the documents. The Attachment Type dialog no longer has **AI can read**; the ticks on Document Access replace it.

Untick every box of a type to stop the AI reading it. The filter **AI reads** (On / Off) narrows the list to types that have a tick or none.

### Check what one contact can read

1. On **Document Access**, pick the contact in **Preview as**.
2. A strip shows **Runs as** (a staff user or the contact), **Agent on WhatsApp** (On or Off), the contact's **Access types** and **Companies**.
3. Each row now shows what that contact reads, for example *Reads 12 of 15*, followed by why the rest are not read:
   * *no shared access type*: the document's access levels do not include any of the contact's access types.
   * *other company*: the document belongs to a company the contact is not in.
   * **No access type**: the contact has no access type, so reads nothing.
   * **No company**: the contact has no company.
   * **Not ticked for ...**: none of the contact's access types is ticked on that type.
   * **Staff only**: only Staff is ticked.
   * **Off**: nothing is ticked.
   * *Reads N of N (as staff)*: the contact runs as a staff user, who reads every document of a type with Staff ticked.
   * **Agent on WhatsApp** showing **Off** means the contact gets no AI answers at all until the agent is switched on for them.
4. Clear **Preview as** to go back to the plain grid.

### Fix one document's access levels

1. Click a row to open its side panel.
2. The panel shows the same ticks under **Who can read**, then **Documents**: every readable document (PDF or DOCX) with its **Access levels** (editable there), **Company** or **Shared**, and, when you are previewing a contact, whether that contact reads it and why not.
3. Change the access levels of the document. It saves at once.
4. **Sent as a file** shows the **Direct access** switch and how many contacts it is granted to (for example *Granted to 3 contacts*). This is about sending the file itself, which has its own rule (below).

On a phone the rows are cards. Tap a card to open the same panel.

## What's captured

Each file shows a **Read by AI** row on its detail page and in the Files modal:

* **Queued** or **Processing**: the read is running (the row refreshes by itself).
* **Done**: with the number of pages read, and how many were scanned pages read by OCR with an
  estimated cost.
* **Failed**: with the reason. **Read again** appears for a failed file if you may upload files.
* **Not supported**: the file type cannot be read (PDF and DOCX are read).

Limits: 300 pages, 100 scanned pages, per file. A longer file fails with a readable reason.

## Who sees what

One rule decides it:

* A WhatsApp contact reads a document when **one of the contact's access types is ticked on the document's type AND is in the document's access levels**, and the document is in one of the contact's companies or is **Shared**.
* A contact with no access type reads nothing.
* Staff read every document of a type with **Staff** ticked, if they may view Resources.
* A type with only **Staff** ticked never reaches a WhatsApp contact, whatever the access levels.
* A file of another company is not read for a contact outside that company.
* Unticking a box, deleting a file or moving it to another company takes effect on the next question.

Settings from before this page were carried over unchanged: the old **Dealers** setting became Staff plus every access type except End User (so office access types show ticked), **Everyone** became Staff plus every access type, and **Staff only** became Staff alone.

Sending a file (**Direct access**, and each contact's **Document types**) follows its own rule and did not change.

## When the document has no answer

The AI never fills a gap from general knowledge.

* Staff: the reply says the answer is not in the documents and names the **Escalate to** team.
* WhatsApp contacts: the reply is *"I couldn't find that in our product documents."* followed by
  * *"Would you like me to pass this to our marketing product team?"* when **Chatbot hands over to support teams** is
    on for the contact. If they answer yes, the usual hand-off to the marketing product team runs.
  * *"Please refer to your salesman."* when that switch is off for the contact.

## How you'll be notified

Nothing is sent when a file is read. Check the **Read by AI** row. Ticking on **Document Access** shows a toast with the count of documents now readable.

## See also

* [The agent on WhatsApp](./chatbot-agent-on-whatsapp.md)
* [Chatbot Console and Agent mode](./chatbot-console-agent-mode.md)
* [Upload flow](../_shared/upload-flow.md)
