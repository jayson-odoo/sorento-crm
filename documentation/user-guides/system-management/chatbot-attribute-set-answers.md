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

The first line always states the count, and how many products are shown in this reply:

> 908 taps have certificates. Showing 5.

Below that first line, the reply looks exactly like asking about one product - one block per
product, files attached - repeated for the first five qualifying products. If every qualifying
product already fits in the reply, the "Showing" sentence is left off (e.g. "3 taps have
certificates.").

### Getting the next five

Reply **more** (also **next**, or the Malay **lagi**) - on its own, or as a short phrase like
"more please" or "show more" - and the bot sends the next five products with an updated header:

> 908 taps have certificates. Showing 6 to 10.

Keep replying "more" to keep paging. Once every qualifying product has been shown, the bot says:

> That was all 908 taps.

The bot only carries the first 200 qualifying product ids forward for paging. If a set is bigger
than that and you keep asking for more past the 200th, it will ask you to narrow the question
instead of paging further (e.g. "narrow the ask - a brand, or a more specific type - and I can
show you the right ones") rather than silently stopping.

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
  > I don't know 'water tap' as a product type. Did you mean tap?
* An unrecognised **document type** (something you're asking to see, like a photo, before an
  admin has taught the bot that word) clarifies and lists the document types it does know:
  > I don't know 'photo' as a document type. Types I know: Certification, Product Photos, Product
  > Videos, Technical Specifications.

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
