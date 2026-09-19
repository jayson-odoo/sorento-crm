# Entity kinds

Use this to see or change the named "kinds" of things the WhatsApp chatbot recognises inside a
customer's message - a product, a customer, a location, a pricing tier, and so on - and how each
kind gets matched to an actual record.

## Where to find it

**System Management > Entity Kinds** (`/system-management/chatbot-entity-kinds`; the page itself
is titled **Entity kinds**).

## The list

A DataGrid with **Kind**, **Resolved against**, **Did-you-mean**, **Default narrowing**, **Family
grouping** and **Base property words**. Search narrows by kind or label. Click a row to open it.

* **Kind** is the internal code the bot's language model and the matching logic refer to (e.g.
  `product`).
* **Resolved against** says, in plain words, what a name of this kind gets matched against (for
  example "Master products (code, name, set members)").
* **Did-you-mean** - **on** means that when nothing matches closely enough, the bot offers its
  best guess instead of just giving up.
* **Default narrowing** - the narrowing behaviour this kind falls back to when a domain's own
  **[Chatbot Domains](chatbot-domains.md)** row doesn't set anything more specific for it. Same
  set of options as a domain's Narrowing tab (Must narrow to one, Narrow to a code, Narrow by
  type, Narrow by tier, Optional filter, List all variants, Not applicable).
* **Family grouping** - how matches of this kind are grouped into one "family" for a picker (for
  example, grouped by base code so several ledgers of the same customer count as one).
* **Base property words** - product only: a word the bot reads as asking about a property (like
  "discontinued") mapped to the actual field it should answer from, so the bot can answer "is it
  discon?" correctly instead of saying it doesn't know.

## Add or edit a kind

Click **Add kind**, or click an existing row:

* **Kind** - the internal code. Fixed once created (cannot be edited on an existing row).
* **Label** - the name shown on the list and elsewhere in the admin screens.
* **Resolved against** - free text describing what this kind matches against.
* **Did-you-mean** - on/off switch.
* **Default narrowing** - dropdown, same options as above.
* **Family grouping** - free text (leave blank if not applicable).
* **Base property words** - a small table of word -> field pairs. **Add word** adds a row; the
  trash icon removes one.

There is no delete for an existing entity kind from this screen - the twelve kinds the bot uses
are a fixed set; edit a row rather than remove it.

## Who may edit this

Viewing this page needs the same permission as Chat History. Adding or editing a kind needs the
**Manage Chatbot Configuration** permission - without it every field is read-only and there is
no **Save**.

## See also

* [Chatbot Domains](chatbot-domains.md) - each domain's Narrowing tab sets its own policy per
  entity kind, overriding the Default narrowing here.
* [Chatbot settings](../user-management/chatbot-settings.md) - the Tier order list orders the
  values of the `tier` kind.
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
