# Chatbot settings

Use this to change the WhatsApp chatbot's overall switches, how it remembers past conversations,
which pricing tier it tries first, and the default order it climbs through related topics when
an answer comes back empty.

## Where to find it

**Settings > Chatbot** (`/user-management/settings`, **Chatbot** tab).

## Switches

Three on/off switches:

* **Stock denial lanes** - whether the bot is allowed to tell a customer outright that their
  stock question is refused. Off by default. While it's off, that kind of question is not
  reachable at all - the bot never gets the chance to send that reply (whether any one *contact*
  is allowed to ask about stock at all is a separate, per-contact setting - see
  **[Contact chatbot card](contact-chatbot-card.md)**).
* **Business lane** - whether the bot answers ordinary business questions (stock, orders,
  promotions and so on) itself.
* **Ordering** - whether the bot finishes every kind of question itself, end to end. Turning
  this **on** is confirmed first: a dialog titled *"Let the CRM finish every turn?"* warns that
  every lane still switched off elsewhere will then have nobody left to answer it. Turning it off
  needs no confirmation.

Below the switches, a card explains that the list of domains the bot refuses to answer has moved:
it is no longer typed here, it lives on each domain's own **Supported** switch on
**[Chatbot Domains](../system-management/chatbot-domains.md)**.

## Bot replies sent by

Chooses who delivers the bot's replies to the customer on WhatsApp:

* **n8n** (the default) - replies go out through the n8n automation, as before.
* **CRM for listed contacts** - the CRM sends the replies itself, for the contacts typed in the
  **Reply sender contacts** box (one respond.io contact per line). Everyone else stays on n8n. Use
  this to try the change on your own number first.
* **CRM for all** - the CRM sends every bot reply itself.

The change applies to the next reply, with no restart. To undo it, choose **n8n** again and save.
A reply that is already going out finishes the way it started.

When the CRM sends a reply and WhatsApp does not accept it, the turn shows as failed with the
reason, and **Retry turn** on that turn sends the parts the customer has not received yet (see
[Read a chatbot turn trace, and retry a failed one](../system-management/troubleshoot-chatbot-turn-failures.md)).

## Memory

* **Episode recall** - the default, for every contact, for whether the bot is allowed to pull
  details back in from an earlier closed topic in the same conversation when a customer refers
  back to it (e.g. "same report as yesterday"). Overridable per contact - see
  **[Contact chatbot card](contact-chatbot-card.md)**.
* **Keep episodes for** - how long a closed topic is kept before it's no longer available to
  recall (30, 90, 180 or 365 days).
* **Profile fields** - which facts about a contact (Tier, Language, Default ledgers) the bot is
  allowed to use as a hint.
* **Focus reset on** - which events clear what the bot is currently tracking about a conversation
  (Topic switch, Conversation close).

## Tier order

One orderable list (Dealer, Office, End user) - the order the bot tries pricing tiers in when it
has to guess which tier's pricing applies and nothing else says otherwise. Drag to reorder.

## Cross-domain ladder

The default order the **stock** topic climbs through related topics when its own answer comes
back with nothing, or very little - for example, checking incoming stock next when a product
shows zero on hand. Reorder the list, remove a step, or **Add a rung...** to add another domain.
This is the *same* list as the **inventory** domain's own Ladder tab on
**[Chatbot Domains](../system-management/chatbot-domains.md)** - editing it here is a shortcut,
not a second setting.

**This card has its own Save button**, separate from the rest of the page - saving the ladder
does not require saving the switches, memory or tier order, and vice versa.

## Saving

**Switches**, **Memory** and **Tier order** share **one Save** button at the bottom of the page,
plus a **Reset** button that discards unsaved edits on all three. A toast confirms each part that
saved.

## Who may edit this

Editing any of these cards needs the same admin **Settings** access as the rest of this page -
if Save does nothing, ask an admin to check your permissions.

## See also

* [Chatbot Domains](../system-management/chatbot-domains.md)
* [Entity kinds](../system-management/chatbot-entity-kinds.md)
* [Contact chatbot card](contact-chatbot-card.md)
* [Read a chatbot turn trace, and retry a failed one](../system-management/troubleshoot-chatbot-turn-failures.md)
