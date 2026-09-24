# Chatbot - dealer stock check (WhatsApp)

If your account is set up as a dealer, asking the Sorento WhatsApp number about stock gets you a
straight yes/no/ask answer for each product you name, never a warehouse quantity. This guide is
for that answer. If you don't recognise this reply shape, your account isn't on it - see your
[portal overview](portal-overview.md) instead.

## What to send

Name the product codes and, if you know it, how many units you need:

> stock for MWT5727SS-CR 5, MHS1028 60, MSK11A-QT and ABC123?

You can ask about one product or several in the same message.

## If you leave a quantity out

The bot notes what it already has and asks only for what's missing - it never guesses:

> Noted: MWT5727SS-CR x 5, MHS1028 x 60. How many units do you need for MSK11A-QT and ABC123?

Reply with just the missing quantities:

> MSK11A-QT 110, ABC123 20

Once every product you asked about has a quantity, you get the full answer for all of them.

## "Just proceed"

Don't want to give a quantity for one of them? Say so, and the bot answers the ones it has and
tells you which it skipped:

> just proceed

> MWT5727SS-CR x 5: Yes, available.
> MHS1028 x 60: Yes, available, but running low.
> Not checked: MSK11A-QT, ABC123.

## Changing a quantity

Send a new number for a product you already gave one for, and it replaces the old one - the
others you're still waiting on stay as they are:

> make MHS1028 80

## Asking something else and coming back

You can step away from the stock check mid-conversation - ask about a promotion, a delivery, or
anything else - and the bot answers that normally without mentioning the stock check at all.
Nothing is lost:

* Give it a quantity for one of the products you were asked about (even much later) and it picks
  the stock check straight back up.
* Say **"back to the stock check"** (or name the product again) and it re-asks only what's still
  missing.

Nothing about it expires on its own - there's no time limit to come back within.

## "Never mind the stock check"

Say this (or anything with the same meaning) and the whole check is dropped. Ask again from
scratch whenever you like.

## Reading the answer

One line per product, in the order you asked:

* **`CODE x N: Yes, available.`** - Sorento can supply the quantity you asked for from your
  allowed locations.
* **`CODE x N: Yes, available, but running low.`** - it can be supplied, but the amount left
  after your order is thin.
* **`CODE x N: Not available.`** - it can't be supplied right now, and nothing is on the way that
  would help.
* **`CODE x N: Not available, but there is [limited] incoming, ETA dd/mm/yyyy.`** - not available
  today, but a shipment already on its way covers it (or only partly covers it, if it says
  "limited"), landing on the date shown.
* **`CODE x N: Not available, but there is [limited] purchase, ETA in N days.`** - not available
  today, but a purchase order not yet shipped is expected to cover it (or only partly, if it says
  "limited"), in about that many days.
* Both an incoming shipment and a purchase order can be named together, joined by "and".

**No warehouse quantity of ours is ever shown** - not on hand, not incoming, not on order. The
only numbers in the reply are the quantity you asked for and the date or day count for anything
on the way.

## See also

* [Portal overview](portal-overview.md) - the separate portal used for complaints, stock
  inquiries, purchase requests and sponsorship forms.
* [Chatbot - stock visibility (the dealer availability answer)](../system-management/chatbot-stock-visibility.md)
  - how an admin puts an account on this answer.
