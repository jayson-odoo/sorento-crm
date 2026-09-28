# UAC: the Samantha case, slices 1 to 11 (issue #1262)

Plan: `PLAN-chatbot-samantha-slices-26sep.md`. Source: issue #1262 (scout report F1 to F8,
proposed slices 1 to 12, owner rulings 26 Sep ~06:40Z and ~11:05Z) and the round 2 explainer
`documentation/plans/chatbot/samantha-chat-diagnosis.html` (branch
`claude/samantha-chat-diagnosis-p4o3ao`). Round 3 section 6 (steps 1 to 3) is the brand feed.

## Journey

Actor: Samantha, a Mocha CS sales rep (staff, profile tier `office`), on WhatsApp.

1. She asks for outstanding orders for **brand Sorento** and dealer **Cheng Huat Sentul**.
   The bot runs the outstanding report filtered to that brand and that dealer. It never asks
   "which customer?" over ten SORENTO names, and it never asks "transporter or customer?".
2. If a pick is ever needed, the names she gave that resolved cleanly are kept, and only the
   ambiguous word is asked about. Her answer re-types the word; the printed option label is
   never stored as a customer.
3. She sends a photo of a product list with quantities (x3, x4). The bot answers for those
   products with each quantity shown next to its code, still for Cheng Huat Sentul. If a stored
   customer is unusable, the bot says so instead of printing "Customer: all".
4. She types "got eta". The bot lists the ETA rows for the carried products with no count
   header claiming "0", and the open outstanding question closes because she moved to another
   domain.
5. She sends photos captioned "X5" / "X4", each one product. Each photo is answered as its own
   question (its own domain, quantity 5 / 4 read by the parser, the code without the prefix).
   No tool error text ever reaches WhatsApp.
6. A one-letter Mocha code (M210-GM) is treated as a typed code: one product, one answer. No
   "5,857 products have stock. Showing 0.", no list of hundreds of codes.
7. When a lookup misses, a staff rep gets a plain "no record" or a clarifying question, never an
   offer to escalate to a team; nobody gets an escalation offer while a clarifying question is
   open.

## Acceptance criteria

Tags: `[BE]` backend, `[T]` test. Each AC names the slice (S) and the finding (F).

### Wrong or unsafe replies

- **AC-S1-1 [BE][T] (F2)** Given the MCP server answers a tool call with `isError: true`, when
  the chatbot calls the tool, then the call raises and the fetch takes its error arm; the reply
  is the neutral "I could not fetch ..." line and contains no "Error executing tool" text.
- **AC-S1-2 [BE][T] (F2)** Given the outstanding tool returns a bare string (not the envelope),
  when the output is structured, then it is not treated as a result (`has_result` false) and the
  string never becomes reply text.
- **AC-S1-3 [BE][T] (F2)** Given any lane text containing "Error executing tool", when the turn
  composes its reply, then that text is replaced by the neutral fetch-failure line.
- **AC-S1-4 [BE][T] (F2)** The in-app AI assistant's own tool loop behaves as before on a tool
  error (it still sees the error text), measured by its existing tests.
- **AC-S2-1 [BE][T] (F1c)** Given focus holds a customer whose `uuid` is missing and whose
  `canonical_code` is "Sorento (customer)", when the turn builds spec rows, candidates, offer
  filters, settles the question subject or builds the outstanding carry, then no non-UUID
  string lands in any `uuid` field, `customer_ids` filter or tool argument.
- **AC-S2-2 [BE][T] (F1c)** Given a session already holding `customer_ids: ["Sorento
  (customer)"]` on its open question, when the next turn runs, then the label is dropped at read
  and never reaches `crm_outstanding_report`.
- **AC-S2-3 [BE][T] (F1c)** Given the only stored customer is unusable (not a UUID), when the
  outstanding report runs, then the reply says the customer could not be used (or asks which
  customer) and never prints "Customer: all".
- **AC-S6-1 [BE][T] (F6a)** Given "got eta" over carried products (not a counted set), when the
  incoming answer is composed, then no "N products have incoming stock" header appears in the
  reply, and the incoming rows still do.
- **AC-S6-2 [BE][T] (F6a)** A counted-set header never appears in the reply text when
  `counted_set` is false, whichever carrier (`header_override` or baked `response`) held it.
- **AC-S7-1 [BE][T] (F1b)** Given a kind pick over "Sorento" (customer / transporter), when the
  options are built, then each option carries the raw token ("Sorento") and its kind, and the
  label is display only.
- **AC-S7-2 [BE][T] (F1b)** Given the pick is answered with position 2, when apply runs, then
  focus holds an entity with `raw` "Sorento" and hint `customer`, never "Sorento (customer)" in
  `raw`, `canonical_code` or `uuid`.
- **AC-S8-1 [BE][T] (F1b)** Given T3's verdict (Sorento ambiguous, Cheng Huat Sentul resolved to
  one customer), when apply runs, then the pick is asked AND `focus.customers` keeps Cheng Huat
  Sentul.
- **AC-S8-2 [BE][T] (F1b)** Given two ambiguous tokens in one message, then the first is asked,
  the second is not overwritten or lost, and it is asked once the first pick is answered.
- **AC-S11-1 [BE][T] (F8)** Given a contact whose profile tier is `office`, when every lookup
  misses (stock miss, outstanding miss, ladder rung), then the reply carries no "Would you like
  me to escalate" sentence and no escalation offer is armed.
- **AC-S11-2 [BE][T] (F8)** Given any contact and a turn that asks a clarifying question (a kind
  pick, a roster, a did-you-mean), then no escalation offer is added to that reply.
- **AC-S11-3 [BE][T] (F8)** Given a dealer or end-user contact and a stock miss with no open
  question, the warehouse offer is unchanged (R6 of 22 Sep stands).

### Recall

- **AC-S4-1 [BE][T] (F3)** Given an open outstanding offer (domain order) and a verdict with
  entities, no domain word, and `domain_hint` incoming, when decide runs, then the reading is
  NEW_ASK (not REFINE), the fetch domain is incoming, and `crm_outstanding_report` is not picked.
- **AC-S4-2 [BE][T] (F3)** Given the same offer and a verdict with no entities,
  `domain_in_message` true and `domain_hint` incoming ("got eta"), then the offer is closed
  (no pending after the turn) and the turn is answered as an incoming ask over the carried focus.
- **AC-S4-3 [BE][T] (F3)** An aside with no domain ("ok thanks") still leaves the offer open
  (owner hand pass 3 unchanged), and a verdict whose `domain_hint` equals the offer's domain
  still refines it.
- **AC-S5-1 [BE][T] (F4)** The parser schema carries an optional per-entity `quantity`; the
  prompt (new unlabelled version) says a leading or trailing "xN" / "N pcs" is that product's
  quantity and not part of its raw.
- **AC-S5-2 [BE][T] (F4)** Given a photo whose caption is "X5" and whose code is "M210-GM", the
  text handed to the parser keeps caption and codes apart (not "X5: M210-GM").
- **AC-S5-3 [BE][T] (F4)** Given a photo whose vision result carries per-line quantities
  (SRTBF 11502 x3, SRTBF 11503 x4), the text handed to the parser carries each quantity next to
  its code.
- **AC-S5-4 [BE][T] (F4)** Given a verdict entity `{raw: "M210-GM", quantity: 5}`, the reply
  names the product with its quantity ("M210-GM (x5)"). No code strips a quantity with a regex.
- **AC-S3-1 [BE][T] (F5)** `M210-GM` (one leading letter) counts as a typed code: a stock ask
  naming it withholds the catalogue `require` filter.
- **AC-S3-2 [BE][T] (F5)** `build_set_header` never appends "Showing N".
- **AC-S3-3 [BE][T] (F5)** The silent-company miss line names at most 5 codes; above that it
  says "the N products searched".
- **AC-S3-4 [T] (F5)** The owner's paging ban is written in `documentation/reference`.

### Brand

- **AC-S9-1 [BE][T] (F1a)** Given the brands table holds active brands for the contact's
  companies, when the parser user block is built (first parse and recall re-parse), then it
  carries one `Known brands:` line read live from the table (no cache, no hard-coded names).
- **AC-S9-2 [BE][T] (F1a)** The parser prompt (new unlabelled version) refers to the Known
  brands line instead of the hard-coded "Sorento, Mocha, or Cabana".
- **AC-S9-3 [BE][T] (F1a)** Given a verdict entity `{raw: "Sorento", hint: "brand"}` under the
  order domain and "Sorento" in the live brand list, then the token is resolved to that brand's
  ids, it is not re-typed to customer or transporter, and no customer or kind pick is asked.
- **AC-S9-4 [BE][T] (F1a)** `GET /order-management/outstanding-report` and
  `crm_outstanding_report` accept `brand_ids`; rows are limited to products of those brands; a
  brand alone is a valid subject; the header names the brand.
- **AC-S9-5 [BE][T] (F1a)** T2 + T3 end to end: "outstanding brand Sorento dealer Cheng Huat
  Sentul" calls `crm_outstanding_report` with `brand_ids` = Sorento's ids and `customer_ids` =
  [Cheng Huat Sentul's uuid], and the reply asks nothing.
- **AC-S9-6 [BE][T] (F1a)** The other order reports that take `product_ids`
  (orders list / summary tools) accept `brand_ids` the same way.

### Lane

- **AC-L-1 [T]** `tests/chatbot/test_turn_replay.py` and the rest of `tests/chatbot/` stay green
  (divergences, if any, signed in `replay_turns/DIVERGENCES.md` with a reason).
- **AC-L-2 [T]** Every slice has a kill test: reverting its implementing hunk turns its RED test
  red again.
