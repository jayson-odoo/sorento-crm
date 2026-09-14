# Chatbot - product spec visibility

Use this to control which product spec keys (Thickness, Material, and so on) the WhatsApp
chatbot is allowed to quote to a contact when it answers a product question. The card is called
**Spec visibility** and sits directly under **Stock visibility**, in the same shape, in three
places: on a contact's record, on a market segment, and as the site-wide default.

## Where to find it

* **[User Management → Internal Users](/user-management/contact-access-agents)** (or **System
  Management → Respond Contacts**, which lists every contact) → open a contact → **Profile** tab
  (the tab you land on) → **Spec visibility** card, directly under **Stock visibility**.
* **[User Management → Market Segments](/user-management/market-segments)** → the **Spec
  visibility** icon action on a segment's row opens a dialog titled **Spec visibility -
  \<segment name\>** (e.g. **Spec visibility - Project**).
* **[User Management → Settings → Spec Visibility](/user-management/settings/spec-visibility)**
  - a tab beside **Stock Visibility** in Settings' tab bar.

## The three tiers, and who wins

Each of the three placements above writes one policy row: a contact override, a market-segment
row, or the site-wide default. The card's badge names which one is in force for the record you
have open: **Contact override**, **Market segment: \<name\>** (e.g. *Market segment: Retail*),
or **Default**.

A contact override wins outright. Otherwise, the contact's market segments are merged (most
restrictive of the two combined, if a contact carries more than one). Otherwise the site-wide
default applies. A contact with no market segment, or whose segments carry no policy of their
own, follows the default.

## The two rules

The card offers exactly one rule at a time, toggled between:

* **Show only** - pick the keys that stay visible. An empty pick means no key is visible at all;
  leaving the picker on **All specs** (nothing ticked, placeholder showing) means every key is
  visible.
* **Hide these** - pick the keys to withhold. An empty pick here means the opposite of an empty
  **Show only** pick - nothing is hidden, every key is visible.

Switching the rule carries whatever is ticked across to the other list rather than clearing the
picker.

Under either rule, the card prints the net effect as **Hidden today:** followed by the hidden
keys' labels, or **Nothing hidden** when none are hidden at that tier.

## Remove override

**Remove override** (on a contact) or **Remove policy** (on a market segment) only appears once
that tier has a row of its own to remove - it is not offered on an inherited card, and never on
the site-wide default. Clicking it starts a countdown with **Cancel** next to it; the removal
only commits once the countdown lapses, even if you close the tab. Once it commits, the card
falls back to whatever the record would otherwise inherit (its market segment, or the default).

## The shipped default

Out of the box:

* The site-wide default hides **Thickness** and **Drainer board / countertop thickness**.
* The **Project** market segment hides nothing (an empty **Hide these** list - everything
  visible).
* **Retail** and untagged contacts inherit the site-wide default.

An admin can change any of these three rows at any time; they are not reset by anything running
in the background.

## What the customer sees

A hidden key is left out of the "Specs:" summary line the chatbot gives on a product question,
and out of the vocabulary the chatbot matches asked words against - so a hidden spec cannot be
matched into a reply by naming it a different way either. If a contact asks about a hidden key
directly (e.g. "what's the thickness"), the reply names the key and says **not available**,
never "not recorded" (the wording used for a key that is visible but simply has no value on that
product).

## What this does NOT affect

Hiding a key only changes what the chatbot may say. Price tags, catalogue/dealer-kit PDFs, the
customer portal, and staff-facing screens in the CRM continue to show every spec on a product,
unfiltered, regardless of any contact's or segment's spec visibility policy.

## A retired spec key stays hidden

If a spec key is later removed from the product spec registry, any policy still naming it simply
ignores that key when working out what is hidden today - it does not error and does not need to
be cleaned up by hand.

## See also

* [Chatbot - "last purchase cost" answer](chatbot-last-purchase-cost.md) - a different,
  per-contact chatbot gate, on the same contact record's **Access** tab rather than **Profile**.
* [System Management - Data reference for admins](data-analysis.md)
