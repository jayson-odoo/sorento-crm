# Chatbot - stock visibility (the dealer availability answer)

Use this to control what the WhatsApp chatbot is allowed to say about stock to a given contact:
the full breakdown, a shorter summary, or a plain yes/no/ask verdict with no quantity of ours
ever named. That last mode is what puts a dealer on the availability answer this guide is mostly
about. The card is called **Stock visibility** and sits directly above **Spec visibility**, in
three places: on a contact's record, on a contact access type, and as the site-wide default.

## Where to find it

* **[User Management → Internal Users](/user-management/contact-access-agents)** (or **System
  Management → Respond Contacts**, which lists every contact) → open a contact → **Profile** tab
  (the tab you land on) → **Stock visibility** card, directly above **Spec visibility**.
* **[User Management → Access → Contact Access Types](/user-management/contact-access-types)** →
  the **Stock visibility** icon action on an access type's row opens a dialog titled **Stock
  visibility - \<type name\>** (e.g. **Stock visibility - Dealer**).
* **[User Management → Settings → Stock Visibility](/user-management/settings/stock-visibility)**
  - a tab beside **Spec Visibility** in Settings' tab bar.

## The three tiers, and who wins

Each of the three placements above writes one policy row: a contact override, a contact access
type row, or the site-wide default. The card's badge names which one is in force for the record
you have open: **Contact override**, **Access type: \<name\>** (e.g. *Access type: Dealer*), or
**Default**. A contact override wins outright; otherwise the contact's own access type(s) apply
(merged strictest-first if a contact carries more than one); otherwise the site-wide default
applies.

## Mode

A **Mode** dropdown, one of three:

* **Detailed** - today's full reply: every location's quantity, named.
* **Compact** - a shorter summary, still built from real quantities.
* **Availability only** - the mode a dealer is put on. No quantity of ours is ever named; the bot
  only says whether it can supply the amount the dealer asked for, and if not, whether something
  is on the way. See **[Chatbot - dealer stock check
  (WhatsApp)](../project-sales-rep/whatsapp-stock-check.md)** for the exact wording a dealer sees.

## Locations

**Locations** (or **Excluded locations**, once you switch the **Include** / **Exclude** toggle
underneath the picker) is the warehouse set this record is allowed to be told about, and - for a
contact on **Availability only** - the exact set of warehouses its stock, incoming and purchase
figures are computed from. Leaving the picker on its placeholder means **All locations** under
Include, or nothing excluded under Exclude - either way, every active warehouse. A **Dealer
pool** button fills the picker with the standing dealer-pool location set in one click (always
under Include, even if you pressed it while on Exclude). **Hide zero-quantity locations** drops a
location from the reply once it holds none of the product; it only applies to **Detailed** and
**Compact** replies, since **Availability only** never lists locations to begin with.

## Saving and removing

**Save stock visibility** writes the row for the tier you have open. On an inheriting tier (no
row of its own yet) this creates one; on a tier that already has a row it updates it. **Remove
override** (on a contact) or **Remove policy** (on an access type) only appears once that tier
has a row to remove - never on the site-wide default. Clicking it starts a countdown with
**Cancel** next to it; the removal only commits once the countdown lapses, even if you close the
tab. Once it commits, the card falls back to whatever the record would otherwise inherit.

## Putting a dealer on the availability answer

Going live for dealers is three data rows, not code:

1. Open **Contact Access Types**, find **Dealer** (`dealer`), click its **Stock visibility**
   icon.
2. Set **Mode** to **Availability only**, set **Locations** to **BRW** and **MWH** (Include), and
   **Save stock visibility**.
3. Repeat for **Cabana Dealer** (`cabana_dealer`) and **Mocha Dealer** (`mocha_dealer`).

Any single contact can instead be put on (or taken off) the availability answer on its own, from
the contact record's own **Stock visibility** card - useful for a one-off dealer, or for testing
before rolling an access type over.

## Stock low threshold

**[Settings → Chatbot](../user-management/chatbot-settings.md)** carries a **Stock low
threshold** card, a single **Threshold (%)** input (1 to 100, default 50). It is the one number
the availability verdict uses everywhere it needs to judge "enough, but only just": a dealer's
ask counted against what's on hand marks the reply **running low** once the ask reaches this
percentage of what's available, and the same percentage decides whether an incoming or purchase
shortfall is called out as **limited**. It shares the page's one Save button with the rest of the
Chatbot switches.

## Lead time (the purchase ETA)

**Settings > General** (`/user-management/settings`, **General** tab) carries **Standard lead
time (days)**. When an availability reply names a purchase-order shortfall (no incoming, or
incoming isn't enough), the ETA it quotes is this number, worded as **ETA in N days** - never an
actual date, since no PO carries one dealers are shown. An incoming shortfall instead quotes the
earliest dated allocation it has (**ETA dd/mm/yyyy**), or **ETA to be confirmed** if none of the
counted allocations carry a date.

## Publishing the prompt (multi-product quantity capture)

A dealer who asks about several products in one message - "stock for A 5, B 60, C?" - only has
every product's quantity captured in one pass once the parser prompt version that reads it is
published. Until then, the bot falls back to asking one quantity at a time and only captures it
automatically when exactly one product in the message is missing a quantity.

1. Open **[Prompts](/system-management/ai-assistant/prompts)** (System Management > AI Assistant
   > Prompts).
2. Open **chatbot_semantic_parser**.
3. **Publish** the version that carries multi-product quantity capture, so it carries the
   **production** label.

No redeploy is needed either way. **Rollback** is moving the **production** label back to the
previous version.

## What this does NOT affect

Staff-facing screens in the CRM, the customer portal, price tags and catalogue/dealer-kit PDFs
continue to show real quantities, unfiltered, regardless of any contact's or access type's stock
visibility policy. Availability only changes what the chatbot may say on WhatsApp.

## See also

* [Chatbot - dealer stock check (WhatsApp)](../project-sales-rep/whatsapp-stock-check.md) - what
  a dealer actually sends and reads.
* [Chatbot - product spec visibility](chatbot-spec-visibility.md) - the same three-tier card
  shape, for product specs instead of stock.
* [Chatbot settings](../user-management/chatbot-settings.md) - the Stock low threshold card and
  the rest of the Chatbot settings page.
* [Chatbot Domains](chatbot-domains.md) - publishing a prompt change more generally.
* [System Management - Data reference for admins](data-analysis.md)
