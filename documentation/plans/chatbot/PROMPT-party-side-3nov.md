# Parser prompt change: party side of a both-sides company (PR #2120)

Owner on prod, 3 Nov 2026 (parser v71, after #2066): "it keeps asking me to choose fullshun customer or supplier, it
is so clear that sales is talking about customer ... quite annoying". Crew review of the first cut (head 833b0d28):
code word lists broke the owner rule of 28 Oct (#1947), so the side is the parser's semantic call. Code reads no word
of the message for it.

The first line of the section is the marker (`parser.PARTY_SIDE_LINE`). It turns on the `party_side` schema key
(`parser.with_party_side`: "customer" | "supplier" | "unclear" | null, required and nullable). A text without the line
keeps today's schema, and a both-sides name is asked, as on main.

Update 5 Nov 2026: the section is LIVE in production text. The owner published parser v202 (md5
`d29c19830b22aa47403a88ddcb8e817d`, production label v71, `PROMPT-chatbot-totals-filters-d29c1983.md`), which carries
this Edit 1 verbatim, while this PR's code was not on main, so prod still asked "hanlim (customer) / hanlim
(supplier)" on "delivery to hanlim". Merging this PR turns the side logic on in production at the next deploy, with
no further label move. The paragraph below is the original 3 Nov plan: crew applies the edit,
runs the eval gate and pins the md5; the owner moves the production label. Section rules are abstract (owner rule kept:
no gold-message examples, no word lists).

## Base and order with SALES-ACCOUNT-TYPE (#2105)

Update 4 Nov: #2105 is merged (3a05967c). Base for this edit: #2105's candidate text md5 `e4aa6d43fedd996579b8c1caa2c54556`
(its REPORT_ASK section applied), or whatever parser version crew publishes #2105 as. Section bytes to insert (the code
block below, from `== PARTY_SIDE` through the last line's newline): 1315 bytes, md5 `9fcfa92c8b6045279b8889734c0fe4d8`.
The resulting full-text md5 is crew's to compute on publish (the full parser text is not in this repo) and to pin.

#2105 inserts its `== REPORT_ASK ... ==` section before the same banner (`PROMPT-report-semantic-carry-e4aa6d43.md`, base
`99b5fc65`, result `e4aa6d43`). Recommended: **one parser version carrying both sections**. Apply #2105's Edit 1 to the
base, then Edit 1 below (it lands after the REPORT_ASK section, right before the banner). The owner then moves one
label, and the eval gate runs once on the combined md5. The two markers are independent flags, so either PR's code
works with the combined text whichever merges first. On merge order, #2105 goes first (reviewed, READY); #2120 then
rebases its `parser.py` hunks, which sit next to #2105's in `ParserConfig`, `resolve_config` and `_base_schema`, a
textual conflict only.

## Edit 1, a section inserted immediately before the banner line that precedes `TOP SELLING` (the line of `━` characters, then `TOP SELLING`)

```text
== PARTY_SIDE: whether the company the user names is our customer or our supplier ==
A NEW output key on every object, party_side: "customer", "supplier", "unclear" or null.
One company can be both our customer (we sell to it) and our supplier (we buy from it) under the same name. party_side is the side the user means in this turn, read from the whole turn and the assistant's open question, never from one word alone:
  - The user says what the company is to us (our customer or dealer, or our supplier or vendor) -> that side, whatever else the message asks.
  - Otherwise the question decides. A question about what we sell to the company (its sales, invoices, deliveries to it, its orders with us, quotations to it) -> "customer". A question about what we buy from the company (our purchase orders to it, goods incoming from it, goods received from it) -> "supplier".
  - A reply that answers the assistant's open question keeps the side of the ask it answers, unless the reply says another.
  - "unclear" only when neither the message nor the open question tells which side: the company named with nothing else, or a question both sides share in the same words.
  - null when the message names no company.
party_side never changes an entity's hint or canonical_code; they are read as their own sections say.
```

## Gate (crew)

- Eval gate per `documentation/agents/chatbot-verification.md` ("Per-step gate"): the hidden cases of the topics this
  touches (sales report, outstanding, purchase order) plus the 30-case smoke, on the candidate md5, against the
  base's baseline.
- Console pin of the candidate (dry run), then the owner's hand test: `laneboard/scripts/2120.md`.
- Owner step, after the gate: move the parser production label to the candidate.
