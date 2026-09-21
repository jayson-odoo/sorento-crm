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
