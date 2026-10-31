# Behaviour card: a stock ask for a set answers SET availability first (CHATBOT-SET-STOCK)

## v4 (30 Oct ~22:30): owner hand test = CHANGE REQUEST. ANSWERED 30 Oct ~22:40, built at 8d994dbcc0.

Owner answers (verbatim): Q1 "a"; Q2 "it should behave like product search in resolver, in this case it is
like prefix search right just like product code, the resolver should behave similarly for product and set
from entity perspective"; Q3 "hmm should we ask set? should we just show the product in the set?"; Q4 "a";
Complete sets line: "I don't need the complete set answer".
Built: R1 only (every domain that takes products expands a set; the domain list is gone). R2 (set quantity
question) is DROPPED: no "How many sets?", no set maths, today's product quantity questions stay. In the
ETA / photos branch, where the gate decides a picker, a set's parts always resolve and a set is never a
choice; only products outside every matched set can still make today's picker. The resolver already matches
a set like a product code (v3).

Owner, hand test #2013, verbatim: "shouldn't apply to stock only, any ask like eta, photos, delivery also
should be included; how it works is basically expand the set to multiple product codes under the set and
pass to behind." And: "if I ask like this should it be 1 for each, just thinking will this break our
general rule, make our code too customized logic, too hard to maintain."

His screenshots (prompt v148):
- "srtwc8826 eta" answered `SRTWC8826-SC: ETA 03/11/2026, 08/11/2026 / Please refer to your salesman.`,
  the seat cover only.
- "check stock stock srtwc8826" asked `How many units for each? 1. SRTWC8826-SC 2. SRTWCX8826-P
  3. SRTWCY8826 4. SRTWCX8826-S`. He typed `1`. The reply was `SRTWC8826-SC x 1: Got stock.`: the `1` was
  read as line 1, not as one set.

### What the code does today (head 5235f08e77)

1. The expansion step he describes ALREADY EXISTS, and it is generic: `run_gate` replaces a visible set
   with its member products, each carrying `set_code` (`lanes/business/gate.py:441-462`). Every handler
   after it sees plain product codes.
2. It runs for two domains only: `_SET_MEMBER_DOMAINS = {"master_products", "inventory"}`
   (`gate.py:75`). For any other domain the set entity is not a kind that domain accepts, so it is
   dropped, and only the product codes that contain the typed code survive (SRTWC8826-SC). That is why the
   ETA reply named the seat cover only.
3. Ten domains accept product entities (`ALLOWED`, `gate.py:77-140`): master_products,
   product_attachment (photos, drawings, certificates), promotion, inventory, order, sales (delivery,
   orders), incoming (ETA), spo_allocation, purchase_cost, purchase_order.
4. The reply groups member rows under "Set <code>" by the row's `Product Code` field
   (`lanes/business/fetch.py:1875-1902`, called at `:3338`). The stock, incoming, attachment, promotion
   and order presenters all print that field (`sorento_crm_mcp/presenters.py`, `Product Code` at :503,
   :534, :589, :640, :910, :947, :1089, :1122, :1165, :1418, :1478).
5. The quantity question is ONE function: one numbered line per product slot under "How many units for
   each?" (`turn/task.py:381-405`); slots come from `with_owed` (`turn/task.py:1059-1075`). A set's
   members become four product slots, so the bot asks per part, and a bare `1` reads as a line pick.

### The rule (proposed)

- R1. One step, already there: a set code resolves to its member products (code and quantity per set)
  at the gate, for EVERY domain that accepts products. The domain list goes; the matrix decides. Every
  intent (stock, ETA, photos, delivery and orders, price, promotion, SPO, last cost) runs on the expanded
  codes through its existing handler. The reply groups them under "Set <code>" (exists).
- R2. Quantity for a set ask: one question, "How many sets of SRTWC8826-S?", one number, no numbered
  list. Each part is checked at sets x quantity per set (all 1 today). The verdict line names the set:
  `SRTWC8826-S x 6 sets: Got stock.`, or the short part when one is short.
- R3. Nothing is per intent. The set is known in three places, all keyed by `product_sets` data: the gate
  (expand), the reply (group), the quantity question (sets). No word lists, no code shapes.

### Answer to "too customized, too hard to maintain?"

No. This REMOVES a special case: today expansion is limited to a hand-kept list of two domains (`gate.py:75`);
R1 deletes that list. Handlers stay set-blind; they receive product codes as for any multi-code ask. Set
knowledge stays in three places, all reading the same `product_sets` rows. A new intent tomorrow gets
sets for free if it accepts products. The one genuinely new behaviour is the quantity question (R2), which
lives in the existing quantity task.

### Real examples (dev rows, prod copy 20 Oct; crew copy figures differ slightly)

1. "srtwc8826 eta": both sets, under Set SRTWC8826-P and Set SRTWC8826-S, with the ETA of SRTWCX8826-P,
   SRTWCX8826-S, SRTWCY8826 and SRTWC8826-SC (today: SC only, 03/11 and 08/11).
2. "photo srtwc8826-s": the photos of SRTWCX8826-S, SRTWCY8826 and SRTWC8826-SC under one heading.
3. "check stock srtwc8826-s" (availability contact): "How many sets of SRTWC8826-S?", then `6`: each part
   checked at 6 (on hand SRTWCX8826-S 343, SRTWCY8826 422, SRTWC8826-SC 671), reply
   `SRTWC8826-S x 6 sets: Got stock.`
4. "srtwc7405-rl-s-pj x 6 sets" (availability): one number already given, no question; checks
   SRTWCX7405-RL-S-PJ (1456), SRTWCY7405-PJ (1482), SRTWC7405-SC (2132) at 6 each.
5. "delivery srtwc8608-rl" (staff): the open sales-order lines of SRTWCX8608-RL, SRTWCY8608 and
   SRTWC8608-SC under Set SRTWC8608-RL.

### Edge cases

- A member hidden from the contact (not chat-searchable, brand scope) or discontinued: the set is not
  expanded (visibility rule, `head/candidates.py:298-315`); the code answers as products. A member can
  never be missing from the catalogue: `product_set_members.product_id` is a RESTRICT foreign key
  (`app/models/product_set.py:99-106`).
- Set plus loose items in one ask ("srtwc8826-s and srtwt6201"): the set's parts under its heading, the
  loose product on its own; quantity per Q3.
- A catalogue code naming several sets (srtwc8826 = -P and -S) when a quantity must be judged: per Q2.
- "Complete sets: N (limited by <part>)" line: still the owner's yes/no from v3 (crew recommendation yes).
  For an availability contact R2's verdict already says it in words, no number.
- Price: a set member's price stays dropped in a set reply (today's rule, `fetch.py:1869-1893`); the set
  price is the product-sets screen's (derived) and is not part of this lane.

### Questions (4, with recommendations)

Q1. Which asks expand a set. (a) every domain that accepts products (the matrix, 10 domains: stock,
ETA, photos and files, promotion, orders and delivery, SPO, last cost, PO, product info); (b) only stock,
ETA, photos, delivery. Recommendation: (a), one rule with no list to keep; (b) is the hand-kept list that
caused this.

Q2. A catalogue code that names several sets, when a quantity is needed ("check stock srtwc8826" for an
availability contact): (a) ask which set first ("Which set: SRTWC8826-P (P-trap) or SRTWC8826-S
(S-trap)?"), then "How many sets?"; (b) one number for all of them. Recommendation: (a), the two sets share
the bowl and seat cover, so one number for both checks the shared parts once at the wrong quantity. Staff
asks with numbers visible need no quantity and show both sets, as today.

Q3. Set plus loose items with no quantity given: (a) one line per subject, named, not numbered
("SRTWC8826-S: how many sets?" / "SRTWT6201: how many units?"); (b) ask the set first, then the loose
items. Recommendation: (a), one reply, and a named line cannot be read as a line pick.

Q4. Numbered quantity lists for plain products (today's "1. CODE -" list, outside sets): (a) leave as
is in this lane; (b) also drop the numbers there so "1" is never a pick. Recommendation: (a), it is the
general quantity rule and changing it touches every multi-product stock ask; file it as its own lane if
you want it.

Eval: parser gold rows for "srtwc8826 eta", "photo srtwc8826-s", "delivery srtwc8608-rl", "check stock
srtwc8826-s" then "6", Malay variants; engine tests per domain (one per handler family) asserting the
member ids reach each tool; red first.

---

(v3 and earlier below)

Status: ANSWERED (owner, 30 Oct ~17:35): Q1 resolver change (not the prompt), Q2 the existing product
logic, Q3 show every product under its set (no set maths), Q4 today's long-answer behaviour, Q5 no
prompt change. The "S" rules below that add a set block or set counts are NOT built; the build follows
`chatbot-set-stock-acceptance-criteria.md`. Correction to item 4: the chatbot resolves in AND mode,
whose probe list had no set probe; that, not only the prompt gate, is why 7405 showed only the SC.
Plan: `PLAN-chatbot-set-stock-30oct.md`.

## What the owner asked

- Text, 30 Oct ~17:10: a 2-piece WC set = CX + CY + SC. CX 100, CY 50, SC 25 means 25 sets.
- Voice 14:29: customers type the catalogue code (SRTWC8826) and do not know X (tank + lid) and Y
  (bowl) exist. "Show everything at once": tank, bowl, seat cover stock, like the cabinet SRTBF11705.
- Voice 17:03: "AI stock check on 7405 only showed the SC; it did not show the bowl and the water
  tank. That's wrong."
- WhatsApp 17:02, salesperson: "Pls check stock srtwc7405 x 6 sets". Reply: SRTWC7405-SC and
  SRTWC7405-SC-UOA per location, no set, no count of full sets.

## What exists (main 97c56256 code, dev rows)

1. **Sets are seeded.** `product_sets` + `product_set_members` (`app/models/product_set.py:46,96`).
   Dev copy: 93 sets, all active, all Sorento. 7405 has NINE sets (SRTWC7405-P, -S, -P-PJ, -S-PJ,
   -RL-P-PJ, -RL-S-PJ, -300-RL-PJ, -S-289UF-PJ, -S-UOA), 8826 has two (-P, -S), 8608 has six. Every
   member: quantity 1, active, not discontinued, chat-searchable. No set and no product carries the
   bare code SRTWC7405, SRTWC8826 or SRTWC8608.
2. **A complete-sets figure exists, TOTAL only, in two copies, never in a chat reply.**
   `entity_resolver.py:886-1001` (`complete_sets` `:978-981`, limiting member `:993`) and
   `product_set_service.py:439-469` (admin grid). Both: on hand minus reserved, summed over every
   warehouse (`entity_resolver.py:938-941`). Reserved is 0 on every dev stock row, so today that is
   on hand. No per-location figure, no O/S.
3. **Chat reads a set as its members, behind a prompt gate.** CHAT-CODE-LOOKUP R2:
   - set codes join the code shortlist (`head/candidates.py:414`, `_set_rows` `:328-346`),
   - the gate swaps a picked set for its member products (`lanes/business/gate.py:441-462`),
   - the reply groups members under "Set <code>", price dropped (`lanes/business/fetch.py:1875-1902`).
   All three run only when the turn's parser prompt version carries BOTH the CLOSED LISTS and the
   CODE LOOKUP sections (`head/parser.py:1095`, `head/code_lookup_prompt.py:56-58`; the section is
   published unlabelled and the owner moves the production label, `code_lookup_prompt.py:3-7`).
4. **Root cause of the 7405 reply.** Two steps, both measured:
   - With the gate on, "srtwc7405" ranks (exact, prefix, contains, similarity; `candidates.py:349-361`,
     cap 5 `:30`): set SRTWC7405-P 0.75, set SRTWC7405-S 0.75, product SRTWC7405-SC 0.69, set
     SRTWC7405-P-PJ 0.64, set SRTWC7405-S-PJ 0.64. SRTWC7405-SC-UOA is 9th, so it CANNOT be in the
     list. It was in the reply, so the turn ran with the gate OFF: no set codes, only the product
     codes that hold the word (SRTWC7405-SC, -SC-UOA; the X and Y parts hold "srtwcx7405..." /
     "srtwcy7405...", not "srtwc7405", and only score 0.37 / 0.44). UNVERIFIED which prompt version
     carries the production label: crew check below.
   - With the gate on, the stem still does not answer: five candidates, four of them sets, and the
     CODE LOOKUP prompt says "When two or more are equally plausible ... pick none: the assistant
     asks which code" (`code_lookup_prompt.py:21-22`). So "srtwc8826" would get "which code?", not
     the tank, bowl and seat cover the owner wants.
   - Even a set picked by its full code prints only the member rows: the set count is never said
     (item 2).
5. **O/S.** Staff stock answers print O/S = open sales-order quantity per location
   (`app/api/v1/inventory/stock.py:76-95`). Dealer verdicts judge on hand only (owner ruling 6 Oct,
   `inventory_service.py:1666-1674`). On dev, O/S dwarfs on hand for every WC member: SRTWC7405-SC
   on hand 2,132, O/S 7,411 (BRW-BB alone 5,371 O/S against 2 on hand).
6. **The cabinet SRTBF11705 is not a set.** No `product_sets` row touches 11705. SRTBF11705 is one
   product, "6 IN 1 BATHROOM FURNITURE SET", discontinued; SRTBF11705-NEW is the active one. Its only
   links are a mirror (SRTMR11404-BL) and a shelf (SRTSV11404-BL) in `product_compatibility`, shown
   only when the ask names a mirror or shelf (`lanes/business/find.py:1-25`). So no "cabinet, tap
   and one more part" answer exists in code or data; the WC answer is new work, not a reuse.

## The rule (proposed)

- **S1. Set from data.** A typed code is a set ask when it resolves to visible `product_sets` rows
  (item 3). No code-shape rule in chat.
- **S2. A catalogue stem names its sets.** "srtwc8826" answers every visible set whose code holds the
  stem (8826: -P and -S). Mechanism per Q1.
- **S3. Set block first, then every component once.** Per set: complete sets (Q2 for the basis),
  limiting component named, the locations that hold at least one full set. Then each distinct
  component's stock rows once (tank, bowl, seat cover), including a component at 0, so a missing
  bowl shows, never silently absent.
- **S4. "x N sets".** Staff: "Asked: 6 sets", and "Short by" with the limiting component when the
  count is under N. Dealers: the existing got-stock verdict judged on sets at their allowed locations,
  no numbers.
- **S5. Variants** (-SC vs -SC-UOA): only the members a set row lists count. SRTWC7405-S-UOA is its
  own set with the -UOA parts; nothing else is guessed.
- **S6. One formula.** Chat, resolver and admin grid read one function (today's two copies merge).
- Unchanged: component row format, price dropped in set replies, no IDs, one fact per line.

## Real examples (dev copy, on hand, staff)

Formula: complete sets = min over members of the member's total on hand. "Locations" = each
location's own min, listed when 1 or more.

1. "stock srtwc8826" (the owner's code). Two sets:
   ```
   Set SRTWC8826-S
   *Complete Sets:* 343
   *Limited By:* SRTWCX8826-S
   *MWH-BB:* 181 sets
   *DC1-BB:* 125 sets
   *CON:* 11 sets
   *BRW-BB:* 2 sets
   *JB SHOWR:* 1 set
   *SHOWROOM:* 1 set

   Set SRTWC8826-P
   *Complete Sets:* 19
   *Limited By:* SRTWCX8826-P
   *BRW:* 9 sets
   *CON:* 1 set
   *PJ-SR:* 1 set

   then the rows of SRTWCX8826-S, SRTWCX8826-P, SRTWCY8826, SRTWC8826-SC, each once
   ```
   Note 343 vs 321: 22 sets need a transfer (parts in different locations). That gap is Q3.
   Note shared parts: SRTWCY8826 (422) and SRTWC8826-SC (671) serve both sets; each set's count
   reads "if you sell only this one".
2. "Pls check stock srtwc7405 x 6 sets": nine sets. Example of one, SRTWC7405-RL-S-PJ: complete
   1,456, limited by SRTWCX7405-RL-S-PJ (Y 1,482, SC 2,132); 971 of them in one location
   (DC1-BB 673, DC1-IB 159, MWH-BB 92, CON 25, MWH-IR 20, BRW-BB 1, BRW-VAR 1). Asked 6: no short line.
   SRTWC7405-S reads 0, limited by SRTWCX7405-S (no stock row with on hand; its cistern SRTWCY7405
   has 1 at BRW-VAR).
3. SRTWC8608-RL: complete 1,090, limited by SRTWCX8608-RL (Y 1,417, SC 1,397); 982 in one location.
4. SRTWC8840-S-RL: complete 1,488, limited by SRTWCX8840-S-RL (Y 1,534, SC 1,796); 1,278 in one
   location across 18 locations.
5. Dealer on "Availability only", "srtwc8826 x 6 sets": "Got stock" for each set that has 6 at the
   dealer's allowed locations, the existing short reply otherwise. No numbers.

## Edge cases

- A discontinued member: the set reads 0, limited by it (resolver behaviour today).
- A member hidden from the contact: the set stays hidden (`candidates.py:298-315`), the code answers
  as products. Safe side.
- Member quantity above 1: floor(on hand / quantity). None on dev today.
- Locations such as REJ100%, BRW-DFCT, SHOWROOM count today (`counts_as_available` true on dev); the
  set figure follows the same location policy as the stock answer, so the two agree.
- A product code typed in full that is also a member (SRTWC7405-SC): product answer, no set block.
- Follow-up "how about 10 sets": the carried subject is the set(s).

## Eval

- Parser gold `scripts/chatbot_eval/gold/parser_set_stock.jsonl`: "stock srtwc8826", "srtwc7405 x 6
  sets", "srtwc8826 p trap", "ada stok srtwc8608 3 set", a full set code, a member code; expect the
  set codes (or the one spec-matched set) and quantity N.
- Engine tests (deterministic): set block before components, min and limiting member, per-location
  lines, short-by, dealer verdict on sets, shared parts, hidden member, discontinued member.
- Q1 (a) changes the CODE LOOKUP prompt: md5-pinned, published unlabelled, the owner moves the label.
  Q1 (b) needs no prompt change.

## Questions (5, with recommendations)

Q1. How a stem like "srtwc8826" reaches all its sets. (a) prompt: the parser picks EVERY listed set
code that holds the typed code when no spec word narrows it (today it picks none and asks); (b)
engine: a typed code word that no product carries exactly, with set codes holding it in the
shortlist, answers all of those sets, no prompt change.
Recommendation: (a), the parser already decides between sets ("P-trap" picks one), so one place keeps
deciding meaning; (b) is a code-containment rule outside the parser.

Q2. O/S in the set count. (a) on hand only (your 6 Oct basis); O/S stays on the component rows;
(b) also print "After O/S" = sets once open sales orders are taken off.
Recommendation: (a). On dev, O/S is bigger than on hand for every WC part (SRTWC7405-SC: 2,132 on
hand, 7,411 O/S), so "After O/S: 0" would print on every set, which is noise.

Q3. Complete sets when parts are in different locations. (a) min over each part's TOTAL (your
formula; SRTWC8826-S 343), with the locations that hold full sets listed (321 of them); (b) only sets
complete in one location (321).
Recommendation: (a), your formula; the location lines already show where the full sets sit.

Q4. Nine 7405 sets is long (about 9 blocks plus about 13 part rows). (a) print every set block, no
cap; (b) print the set lines only ("SRTWC7405-RL-S-PJ: 1,456 sets, limited by ...") and the part rows
only when one set is picked or asked by spec ("srtwc7405 s trap").
Recommendation: (b) when more than 3 sets match, (a) otherwise; "srtwc8826" (2 sets) shows everything.

Q5. Production prompt. The 7405 reply proves the turn ran without the CODE LOOKUP section, so even
today's set grouping never ran in prod. (a) this lane ships the set answer plus the Q1 prompt change
and you move the production label to the new pinned version after the eval; (b) you move the label to
today's CODE LOOKUP version first, as a separate step, and this lane builds on it.
Recommendation: (a), one label move, one eval run, and the 7405 ask is the gold case that proves it.

## Crew check needed

- Which parser prompt version carries the production label for staff contacts today, and does its
  text contain `== CODE LOOKUP ==` and `== CLOSED LISTS ==`? (item 4, root cause step 1.)
