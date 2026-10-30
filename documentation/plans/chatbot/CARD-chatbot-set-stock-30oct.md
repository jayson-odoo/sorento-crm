# Behaviour card: a stock ask for a set answers SET availability first (CHATBOT-SET-STOCK)

Status: FILED for the owner's answers (30 Oct 2026, v2 after the owner's voice notes). No code until
answered. Size M, owner-visible.
Plan: `PLAN-chatbot-set-stock-30oct.md` (same folder).

Owner, 30 Oct ~17:10: "I want to relook at our set to check for set instead of product, cause
recently got user raise back so i want to handle that". His rule: a 2-piece WC set = CX + CY + SC;
CX 100, CY 50, SC 25 means 25 sets. Salesperson's ask (30 Oct 17:02): "Pls check stock srtwc7405 x
6 sets"; the bot listed SRTWC7405-SC and SRTWC7405-SC-UOA per location and never said how many full
sets exist.

Owner voice notes (crew's English, 30 Oct):
- 14:29: the catalogue says SRTWC8826; inside it is SRTWCX8826 (tank + lid) and SRTWCY8826 (bowl),
  the seat cover keyed separately. Customers do not know X and Y, they always type SRTWC8826.
  "Show everything at once": tank, bowl, seat cover stock. "Like the cabinet SRTBF11705, where you
  already show the cabinet, the tap and one more part."
- 17:03: "AI stock check on 7405 only showed the SC; it did not show the bowl and the water tank.
  That's wrong."

## What exists today (main 97c56256, every line read)

1. **Sets are modelled, as data.** `product_sets` + `product_set_members`
   (`sorento_crm_backend/app/models/product_set.py:46`, members `:96`): a set code with its member
   products and a per-member `quantity` (Numeric, `:116`). Per company (`:86-90`). Not a product,
   never stocked. Admin screen: Master Data > Product Sets
   (`app/api/v1/master_data/product_sets.py`). This is the "previous PR" the staff member remembers
   (archived plan `documentation/plans/_archive/master-data/PLAN-product-sets.md`).
2. **Candidate sets are proposed from code shapes, never written by themselves.**
   `app/services/product_set_proposal_service.py:1-20`: a person ticks proposals. The archived plan
   (`PLAN-product-sets.md:17-21`) says the seeding backfill "has not been applied" (98 Sorento
   candidates). Whether prod and dev hold a SRTWC7405 set row today is UNVERIFIED: data request below.
3. **A complete-sets figure exists, TOTAL only, in two copies, never in a chat reply.**
   - `entity_resolver._probe_product_set` (`app/services/entity_resolver.py:886-1001`):
     `complete_sets` = min over members of floor(available / quantity) (`:978-981`), limiting member
     named (`:993`), a discontinued member supplies 0 (`:976-978`).
   - `ProductSetService._decorate` (`app/services/product_set_service.py:439-469`), the admin grid's
     Complete sets column.
   - Both read `quantity_available` summed over EVERY warehouse (`entity_resolver.py:938-941`,
     `product_set_service.py:432`) = on hand minus reserved (`app/models/inventory.py:132`). No
     per-location figure, no open-SO (O/S) netting, no dealer location scope.
4. **The chatbot reads a set code as its members, and stops there.** CHAT-CODE-LOOKUP R2:
   - Shortlist: set codes holding the typed word or spelt near it are candidates
     (`app/services/chatbot/head/candidates.py:328-346`), only if every member is visible to the
     contact (`:298-315`).
   - Gate: a visible `product_set` match is replaced by its member products, each carrying
     `set_code` (`app/services/chatbot/lanes/business/gate.py:441-462`, domains
     `master_products`/`inventory` `:75`).
   - Reply: member rows are grouped under a "Set <code>" heading with price dropped
     (`lanes/business/fetch.py:1875-1902`, called `:3337-3338`; trigger built
     `lanes/business/__init__.py:2361-2369`). The `complete_sets` / `limiting_member` the resolver
     already computed are dropped on the floor: no line prints them.
5. **Root cause of the 7405 reply (only the SC, no bowl, no tank).** The 7405 family in the
   catalogue is SRTWCX7405-RL-S-PJ, SRTWCY7405-PJ and SRTWC7405-SC
   (`documentation/plans/scm/PLAN-scm-friday-uat-journey.md:61-62`).
   - The code shortlist for a typed code word (`head/candidates.py:396-421`) ranks codes that HOLD
     the word first (`norm.contains(word)`, `:398-402`). Folded, "srtwc7405" is inside
     "srtwc7405sc" and "srtwc7405scuoa", and NOT inside "srtwcx7405rlspj" or "srtwcy7405pj": the role
     letter X / Y sits in the middle. Measured with the module's own trigram similarity
     (`:94-107`): -SC 0.69, -SC-UOA 0.56, the Y part 0.44, the X part 0.37. So the X and Y parts
     reach the parser at best as "spelt near" typo alternatives (`:405-415`, floor 0.30) and the
     parser takes the two codes that hold the word. Same for 8826 (X and Y 0.62, both "near").
   - A visible set row would have fixed it: "srtwc7405" IS inside a set code such as
     "SRTWC7405-RL-S-PJ", so the set would rank as a holding candidate (`:336-345`, `_ranked`
     `:349-361`) and the gate would answer its members (item 4). The reply had no "Set" heading, so
     there is no visible 7405 set in prod: either no row, or a member hidden from chat
     (`:298-315` hides the whole set then). Data request decides which.
   - So the fix is data (a set row per WC family) plus the reply (set figure). No code-shape
     matching in the chat path: the X / Y rule lives only in the proposal pass a person ticks
     (item 2).
6. **The cabinet SRTBF11705 in code.** It is ONE product, description "SORENTO 6 IN 1 BATHROOM
   FURNITURE SET" (`tests/fixtures/spec_derivation_golden_sample.json:108024-108025`), with a
   mirror and a shelf linked as compatible products (`scripts/oneoff/link_mirror_shelf_flyer.py:60,67`,
   table `product_compatibility`). The chat stock reply adds linked products only when the parser
   asks for the linked kind ("mirror for SRTBF11705", `lanes/business/find.py:1-25`). Nothing in
   code shows the cabinet's parts on a plain stock ask, so what you saw is either a `product_sets`
   row for it in prod or the -NEW variant rows (`SRTBF11705-NEW`). Data request item 5 checks;
   if it is a set row, the WC answer reuses exactly that path.
7. **O/S today.** The staff stock answer's O/S is the open sales-order quantity
   (`app/api/v1/inventory/stock.py:76-95`, `open_so_qty`, per location and per product). The dealer
   availability verdict judges ON HAND only, O/S not netted (owner ruling AVAIL-ONHAND-BASIS, 6 Oct,
   `app/services/inventory_service.py:1666-1674`).

## The rule (proposed)

- **S1. Recognise a set from data only.** A code is a set when the code lookup resolves it to a
  visible `product_sets` row (today's path, item 4). No code-shape, prefix or word rule in the chat
  path. A family with no set row answers as products, as today (fix = tick the set in Master Data).
- **S2. Set first, then EVERY component, in one reply.** When the subject is a set, the reply
  opens with the set block, then each member's stock rows (tank X, bowl Y, seat cover SC) under
  "Set <code>" (today's grouping). A component with no stock still gets its row, so a missing bowl
  is visible, never silently absent (your 17:03 note).
- **S3. Set block, staff (number-seeing) contacts.** Per location: sets = min over members of
  floor(member on hand at that location / member quantity). Total: see Q1. The limiting component
  is named. O/S: see Q2. Locations follow the contact's existing location scope and hide-zero policy.
- **S4. "x N sets".** The asked quantity is a number of SETS. Staff: one line "Asked: 6 sets" and,
  when short, "Short by: 2 sets (limited by SRTWC7405-SC)". Availability-only contacts (dealers):
  the existing verdict, judged on sets in their allowed locations ("Got stock" / short), no numbers.
- **S5. Variants of a component** (-SC vs -SC-UOA): counted only if the set row lists them; see Q3.
- **S6. A short code naming several sets** (e.g. S-trap and P-trap of one family): see Q4.
- **S7. One formula, one place.** The chat set block, the resolver's `complete_sets` and the admin
  grid read one function (today's two copies, item 3, become one). Basis per Q1/Q2.
- Unchanged: component row format, price dropped in a set reply, staff Gemini / customers OpenAI,
  no IDs, one fact per line `Label: value`.

## Examples

Real dev rows are pending the data request (this sandbox has no dev DB). Shapes below use the
owner's own numbers; the PR will replace them with 3-5 real sets from dev.

Example 1, staff, owner's rule: "stock srtwc8826" (CX 100, CY 50, SC 25, all at BRW):
```
Set SRTWC8826
*Complete Sets:* 25
*Limited By:* SRTWC8826-SC
*BRW:* 25 sets

1. *Product Code:* SRTWCX8826 ... (component rows as today)
```

Example 2, staff, parts split across locations (CX 10 at BRW, CY 10 at MWH, SC 10 at BRW):
```
Set <code>
*Complete Sets:* 10        <- Q1 (a); Q1 (b) prints 0
*Limited By:* (none short in total; no single location holds all three)
*BRW:* 0 sets (missing <cistern code>)
*MWH:* 0 sets (missing <pedestal code>, <seat cover code>)
```

Example 3, staff, the salesperson's ask "Pls check stock srtwc7405 x 6 sets", once a 7405 set row
is visible:
```
Set SRTWC7405-RL-S-PJ
*Asked:* 6 sets
*Complete Sets:* n         (O/S line per Q2)
*Limited By:* <member>
*Short By:* ...            (only when n < 6)
then the three component rows
```

Example 4, dealer on "Availability only", same ask: "✅ Got stock for 6 sets." or the existing short
reply, judged on sets at the dealer's allowed locations. No number.

Example 5, a family with no set row (today's 7405 reply): unchanged product answer. Nothing in the
chat path guesses a set from the code.

## Edge cases

- Discontinued member: the set shows 0, limited by that member (as the resolver does today).
- Member quantity 2 (e.g. two brackets): floor(on hand / 2).
- A member with no stock row at a location counts 0 there.
- A member hidden from the contact (not chat-searchable, brand scope): the set stays hidden and the
  code answers as products (`candidates.py:298-315`, unchanged). Hiding a set number is the safe side.
- The same set code in two companies: one set block per company (sets are per company).
- A product code that is BOTH a member and typed directly: product answer, no set block.
- Follow-up "how about 10 sets" after a set reply: the carried subject is the set.

## Eval

- Parser gold (`scripts/chatbot_eval/gold/`, new `parser_set_stock.jsonl`): set code asks, "x N
  sets", "N set", Malay "set" wording, stem codes; expect the code lookup canonical and quantity N.
- Answer tests (engine, deterministic): set block first, per-location min, limiting member, short-by,
  dealer verdict on sets, hidden member, discontinued member, no set row.
- Aim: no parser prompt change (the set is recognised from data and the quantity slot already
  exists). If gold shows the parser drops "x 6 sets", the prompt change goes through the md5 pin and
  the owner publishes it.

## Questions (5, with recommendations)

Q1. Total sets when parts sit in different locations. (a) total = min over each component's TOTAL
(your WC8826 formula), with each location's own sets listed under it; (b) total = sum of the
per-location complete sets (only sets shippable from one place).
Recommendation: (a), it is your formula and the per-location lines show where the sets really are.

Q2. O/S. (a) sets from ON HAND (your 6 Oct basis), plus one staff line "After O/S: n" = sets left
once open sales orders are taken off each member; dealers judged on on hand as today; (b) on hand
only, O/S shown only on the component rows.
Recommendation: (a), a salesperson asking "x 6 sets" needs to know what is not already promised.

Q3. Component variants (-SC vs -SC-UOA). (a) only the members the set row lists count; a variant
counts only if listed (or as its own set row); (b) treat look-alike sibling codes as alternates.
Recommendation: (a), (b) is a code-shape rule (standing rule: semantic, no word lists) and the set
row already says what the set is.

Q4. A short code that names several sets ("srtwc7405" matching an S-trap and a P-trap set).
(a) answer each matching set's block (up to 5), then components; (b) ask which set first.
Recommendation: (a), staff type short codes and want the answer in one reply.

Q5. Set rows missing in prod (item 5: 7405 has no visible set today). (a) the bot change ships
alone and the team ticks the missing WC sets in Master Data > Product Sets from the existing
proposal list; (b) this lane also produces that proposal list for every 2-piece WC family (set code
as the catalogue prints it, X tank / Y bowl / SC seat cover) as a sheet you tick before merge, and
the ticked rows go in with the PR.
Recommendation: (b), otherwise "srtwc7405" still answers only the seat cover after the fix. Nothing
is written without your tick, and the X / Y reading stays in the proposal pass, never in the chat.

Also changed by the rule, no question: the admin grid's Complete sets column moves to the same basis
as the chat (on hand, not on hand minus reserved) so the two never disagree (S7). Say so if the grid
must keep its current basis.

## Data request (read-only, dev copy)

1. `product_sets` per company: count, active count.
2. Every set with its members (set_code, company, member product_code, quantity, is_discontinued,
   member chat-searchable flag), for set codes like `%7405%`, `%8826%`, `%8608%`.
3. For those members: stock per warehouse code (on hand, reserved) and open SO qty per warehouse.
4. 3-5 active sets whose members sit in two or more locations, with the same columns as 3.
5. The cabinet: `product_sets` rows whose code or members match `%11705%`, `product_compatibility`
   rows for SRTBF11705, and products `%11705%` (code, description, chat-searchable).
6. Products `SRTWC%7405%`, `SRTWC%8826%`, `SRTWC%8608%` with their chat-searchable flag (a hidden
   X / Y part hides its set from chat).
