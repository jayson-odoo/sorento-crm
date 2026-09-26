# Chatbot - "which products have X" (asking for a set)

Use this when a WhatsApp customer asks a broad question about a whole group of products - "which
tap has cert", "which basin got stock" - instead of naming one product code. It also covers the
two lookup sets an admin fills in to teach the bot the words customers actually use.

## What counts as "asking for a set"

A customer asking a question shaped like "which &lt;product type&gt; has/got &lt;something&gt;"
(cert, stock, incoming, a promotion) is asking for a set, not one record. Examples the bot
understands this way: "which tap has cert", "which basin got stock", "which sink has incoming",
"which item has PPS cert", "any shower set on promo", "basin ada gambar" (Malay for "has a
photo"). A brand narrows the set the same way ("which sorento bidet has cert").

**A product code or a code prefix still answers the old way, with no set header** - "check stock
srtwc286" replies as it always has, one product's stock, no count line in front of it.

## The reply

The reply opens with what the bot searched for, one filter per line with the label in bold,
then the count:

> **Brand:** Sorento
> **Product type:** Wash basin
> 7 wash basins have stock.

**Up to 50 qualifying products:** every one is listed below, two lines each at most: the
product name with its code, then the one or two facts the question was about (the stock total,
the certificate number and expiry, or the incoming quantity and arrival date):

> 1. Sorento Close Couple WC (SRTWC286-SH-NEW-P)
> **Total:** 34

For a product's full details, ask for it by its code.

**More than 50:** nothing is listed, because the list would not fit in one WhatsApp message.
The bot states the count and asks:

> 908 taps have certificates. That is too many to list in one message. How many should I show
> (up to 50)? Or ask again naming a brand or size.

Reply with a number ("10") and the bot lists that many from the start of the set:

> 908 taps have certificates. Here are the first 10.

Or narrow the question instead ("which sorento tap has cert") and the bot answers the smaller
set. Naming a number in the question itself works the same way ("show 20 taps with cert").

Another number after a list continues the same set from where it stopped ("10" after the
first 30 lists 31 to 40, "Here are 31 to 40."), and once every product has been listed the bot
says "That is all 62." The bot never offers "more" or "next" itself. A new product type or a
new question ("which basin has cert" after a water closet list) starts a new set.

### Which brand comes first (brand weights)

Each brand has a **Chatbot brand weight** on **Master Data > Brands** (shown in the list, set
on the brand's own page with **Edit**, or in the create and edit dialog). When the question
names no brand, the bot answers the highest weighted brand that has products in the set, and
the last line names the other brands in weight order, with their counts (here Cabana 0.5, Mocha
0.1, Bravat 0):

> Other brands with stock: Cabana 57, Mocha 25, Bravat 79. Name one to see them.

A weight of 0 means no preference. Sorento starts at 1.5 and every other brand at 0, so the
reply stays as before until you weight another brand; for example Sorento 1.5, Cabana 0.5,
Mocha 0.1 lists Cabana before Mocha. If no weighted brand has products in the set, the answer
covers every brand. A question that names a brand always answers that brand only.

### When nothing matches

The bot says what it searched for and what the set holds in other values, before it offers to
escalate:

> No gunmetal wash basins with incoming stock (I looked for Finish or colour: Gunmetal among
> wash basins). 12 wash basins have incoming stock in another finish or colour: Chrome 5, Matt
> black 4, White 3. Would you like me to escalate to purchasing team?

Every value is said in plain words ("Cold only", "S trap", "Free standing"). To change how a
value reads, edit its display label on the spec key in Product Specifications.

A dealer on an **Availability only** stock visibility policy asking "which tap got stock" is
counted over the locations their policy allows only, and is never shown a quantity: each product
is listed by its code, followed by the usual "How many units do you need?" question.

The owner's everyday words are understood as their product types: "water tap" is a tap and
"water basin" is a wash basin ("which water tap got stock", "which water basin got stock").

## What "has cert" checks

"Has cert" (and "has certificate", "has PPS cert", etc.) is checked against the **Certificates**
register, not against a product's uploaded files. A certificate that has expired still counts as
the product "having" one - it is included in the set, and flagged as expired in that product's
block, the same way an expired certificate is flagged today when you ask about one product by
code.

A certificate word that names a scheme (e.g. "PPS") narrows the set to that scheme only, and the
header names it: "940 products have PPS certificates."

## When the bot doesn't recognise a word

The bot never silently answers "none" for a word it didn't understand - it always says so and
asks you to try a word it knows.

* An unrecognised **product type** clarifies and suggests the closest match it does know:
  > I don't know 'aqua tap' as a product type. Did you mean tap?
* An unrecognised **document type** (something you're asking to see, like a photo, before an
  admin has taught the bot that word) clarifies and lists the document types it does know:
  > I don't know 'photo' as a document type. Types I know: Certification, Product Photos, Product
  > Videos, Technical Specifications.

* An unrecognised **value** of something the bot does know (a trap type, a finish) is said back
  with the values it knows, never swapped for the nearest one:
  > I don't know 't trap' as a trap. I know P trap and S trap.

Answer the question with one of the offered words ("tap", "p trap") and the bot runs your
original question again with that word, for example "2 taps have stock." with the list.

Once an admin adds the missing word to the matching lookup set (see below), the same question
answers with a set instead of clarifying.

Asking for a promotion set ("any shower set on promo") still goes through the existing
access-level flow first, exactly as a single-product promotion question does today.

## Admin: teaching the bot new words

Two lookup sets exist for this so an admin can add the exact words their customers use, without
any code change. Both start out **empty** - a word only resolves once someone has added it as a
keyword.

Open **System Management → Configuration → [Lookup Sets](/master-data-management/lookup-sets)**:

* **Certificate Scheme** (`certificate_scheme`) - maps a customer's word for a certificate scheme
  (e.g. "watermark") to the scheme spelling that actually appears in the certificate register
  (e.g. "PPS", "SPAN", "WCM"). **A scheme word that already matches the register's own spelling
  works without adding an option at all** - this set is only needed for words the register
  doesn't already recognise.
* **Attachment Type Alias** (`attachment_type_alias`) - maps a customer's word for a document
  (e.g. "photo", "picture", "gambar") to the actual attachment type name on the product (e.g.
  "Product Photos").

To add a word to either set:

1. Click the set's row to open it, then click **Add option**.
2. Fill in **Value (canonical)** - the real spelling the system should resolve to (a scheme
   spelling for Certificate Scheme, an attachment type name for Attachment Type Alias) - and
   **Label (display)**.
3. Under **Keywords (synonyms for n8n / resolve)**, add every word or phrase a customer might
   type for it (e.g. "watermark" for a scheme, or "photo" / "picture" / "gambar" for a document
   type).
4. Click **Add**.

Use the **Test resolve** card on the same page to try a raw word and confirm it resolves to the
value you expect before relying on it.

## See also

* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md) - to
  see exactly what the bot understood and looked up for one WhatsApp message, including a
  set-answer turn.
* [System Management - Data reference for admins](data-analysis.md) - the Lookup Sets table
  reference.
