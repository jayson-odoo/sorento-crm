# Contact chatbot card

Use this to control how the WhatsApp chatbot treats one specific contact - whether they can ask
about stock, whether the bot can recall earlier parts of the conversation with them, and their
known pricing tier and language.

## Where to find it

Open a contact under **[Contacts](/user-management/contacts)**, go to the **Access** tab, and
scroll to the **Chatbot** card.

## Fields

* **Stock checks** - on by default for every contact. Turn it off to stop the bot answering this
  contact's stock questions at all. (For the bot to actually reply with a refusal rather than
  just going quiet on that topic, **Stock denial lanes** on
  **[Chatbot settings](chatbot-settings.md)** also has to be switched on - that is a separate,
  system-wide switch.)
* **ETA buffer days** - on by default. When on, every arrival date the bot tells this contact
  is the shipment's date (its revised date, when one is set) plus the product's **ETA offset
  (days)** (set on the product, else on its category). When off, the contact is told the
  shipment's own date. A dealer asking for stock that is not there, and a dealer asking for the
  ETA, are told the same dates: every shipment still coming, earliest first, for example
  "No stock, ETA 03/11/2026, 06/11/2026." A date that has already passed while the shipment is
  still coming is shown with "(delayed)" after it.
  If the contact's ETA field is turned off for them (field access on the incoming stock agent),
  they are told no date on either question: "No ETA" when they ask for the ETA, and
  "No stock, No ETA." when they ask for stock that is still on its way.
* **Episode recall** - whether the bot may pull details back in from an earlier closed topic in
  this same conversation when the contact refers back to it (e.g. "same report as yesterday"),
  instead of asking everything over again. This overrides the system-wide default set on
  **[Chatbot settings](chatbot-settings.md) > Memory > Episode recall** for this one contact.
* **Language** - the language the bot assumes this contact writes in (English, Bahasa Malaysia or
  Chinese). Clearable - leave blank if unknown.
* **Tier** - this contact's pricing tier (Dealer, Office, End user). Clearable; the placeholder
  reads *"(none) - answered on the next pick"* - if left blank, the bot asks the next time it
  needs to know and remembers the answer automatically, so you don't have to set it by hand.

Every field saves itself as soon as you change it - there is no separate Save button on this
card.

## How you'll be notified

A toast reads "Chatbot settings saved" once a change is saved. If it fails to load in the first
place, the card shows "This contact's chatbot settings could not be loaded. Reload the page to
try again."

## See also

* [Chatbot settings](chatbot-settings.md) - the system-wide Episode recall default and Tier
  order this contact's own settings sit alongside.
* [Chatbot Domains](../system-management/chatbot-domains.md) - domains that narrow by tier read
  this contact's Tier before asking.
* [Read a chatbot turn trace, and retry a failed one](../system-management/troubleshoot-chatbot-turn-failures.md)
  - see this contact's Profile shelf (tier, language) on a real turn's Memory panel.
