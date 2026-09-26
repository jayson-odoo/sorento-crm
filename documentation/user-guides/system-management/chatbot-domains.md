# Chatbot Domains

Use this to see or change what topics ("domains") the WhatsApp chatbot can answer, what it needs
to ask about before it answers, and which team it hands a question to when it can't answer at
all. This is where a topic like "stock", "incoming" or "promotions" is configured - not code, a
row on this page.

## Where to find it

**System Management > Chatbot Domains** (`/system-management/chatbot-domains`).

## The list

A DataGrid with **Domain**, **Label**, **Tools**, **Escalation team**, **Switch words**,
**Narrowing**, **Date filter**, **Supported** and **Updated**. Search box on top; **Filters**
narrows by **Supported** (on/off) and **Team**. Click any row to open it.

* **Domain** is the internal name the bot's language model refers to (e.g. `incoming`).
* **Label** is the word shown back to the customer for that topic (e.g. "Incoming").
* **Supported** shows **on** or **off** as a badge - a domain switched off is a topic the bot
  cannot answer at all.

## Add or edit a domain

Click **Add domain**, or click an existing row. The same modal opens either way, with four tabs:

### General

* **Name** - the internal key (e.g. `incoming`).
* **Label (customer sees)** - what shows up in the customer's reply.
* **Intents** - the phrasings/keywords this topic answers to, added as chips.
* **Tools (from the MCP tools list)** - which lookups this domain is allowed to run, picked from
  the same MCP tools catalogue the rest of the CRM's integrations use.
* **Primary tool** - which of the picked tools is the main one for this domain.
* **Escalation team** - which team a question in this domain gets routed to when the bot can't
  answer it and offers to escalate.
* **Switch words** - the words that make the bot switch into this topic mid-conversation.
* **Takes a date filter** / **Supported** - two on/off switches. Turning **Supported** off makes
  this whole topic unreachable to customers; use it instead of deleting a domain you just want to
  pause.

### Narrowing

One row per entity kind (see **[Entity kinds](chatbot-entity-kinds.md)**), each with a dropdown
choosing how this domain narrows down that kind of thing before it answers:

* **Must narrow to one** - the bot needs to settle on one specific match (one customer, one
  product) before it can answer. If the message names something that could mean more than one
  thing, it lists the candidates and asks which one. This does not mean the customer's *answer*
  is limited to one pick either - replying "1, 3 and 5" or "all" to that list still works, and
  gets an answer for each one at once.
* **Narrow to a code** - this domain always asks for the exact code before it will answer (for
  example, checking on incoming stock needs the precise product code, not a description).
* **Narrow by type** - the bot asks what type or category is meant, unless the customer's message
  already named it.
* **Narrow by tier** - the bot asks which pricing tier applies, unless the contact's tier is
  already known (see **[Contact chatbot card](../user-management/contact-chatbot-card.md)**).
* **Optional filter** - if the customer named something specific, the bot narrows to it; if not,
  it answers broadly without asking.
* **List all variants** - the bot lists every match, no follow-up question.
* **Not applicable** - this domain never needs to narrow on this kind of thing.

### Ladder

An ordered list of *other* domains this one climbs through when its own answer comes back with
nothing, or very little - for example, a stock answer of zero climbing on to check incoming
stock next. Reorder the list, remove a rung, or pick **Add a rung...** to add another domain.
(The same ladder for the stock/inventory domain can also be edited from **Settings > Chatbot >
Cross-domain ladder** - it's the same list, just a shortcut to it.)

### Prompt block

Read-only. Shows the paragraph this domain renders into the bot's own instructions, exactly as
it will read once published. A brand-new, unsaved domain says "Save the domain to see its
block."; a saved one that hasn't rendered yet says "No block rendered yet."

## Publishing a change

Saving a domain here does **not** change what the bot does on the very next message - it changes
the *policy*, and the bot's instructions have to be republished before they pick it up. After a
save, **[Prompts](/system-management/ai-assistant/prompts)** (System Management > AI Assistant >
Prompts) shows a banner: *"Domain block out of date - a Chatbot Domain or Entity kind changed
since v&lt;n&gt; went live. Publish a new chatbot_semantic_parser version to pick it up."* An
owner publishes a new version from that page to make the change live, with no deploy needed.

## Deleting a domain

Open the row and click **Delete**. It counts down for a few seconds in a toast with a **Cancel**
button before it actually deletes - there is no confirmation dialog to answer, and closing the
tab does not stop the countdown. **The last remaining domain cannot be deleted** - add another
domain first; trying anyway is refused with a message naming the domain.

## Who may edit this

Viewing this page needs the same permission as Chat History. Adding, editing or deleting a
domain needs the **Manage Chatbot Configuration** permission - without it, the page still shows
every field but **Add domain**, **Save** and **Delete** are not available (a "Close" button
replaces "Cancel").

## See also

* [Entity kinds](chatbot-entity-kinds.md) - the kinds of things (product, customer, ...) a
  domain's Narrowing tab narrows on.
* [Chatbot settings](../user-management/chatbot-settings.md) - the Switches, Memory, Tier order
  and Cross-domain ladder that sit alongside domains.
* [Contact chatbot card](../user-management/contact-chatbot-card.md) - the per-contact stock,
  recall, tier and language settings a domain's narrowing reads.
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md) - see
  a domain's narrowing and tools actually being used on a real conversation.
