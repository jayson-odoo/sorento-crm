# PLAN: a follow-up keeps the customer the user picked (CHATBOT-FOLLOWUP-CARRY, 1 Nov 2026)

**Status: fix committed, kill test and reviewer pending. Small fix track (no migration, no auth/RBAC change, no new ingest surface). Size S.**
UAC: `chatbot-followup-carry-acceptance-criteria.md`.

## Owner ruling (1 Nov ~16:25, "follow up yes")

A follow-up over a held customer (no new customer named, no topic reset) KEEPS that customer, all its picked ledgers
(company-scoped, as #2064) and the held period unless the message changes it. A new customer, an explicit "all customers"
or a topic reset replaces it. Picks are explicit, never auto name-matching; never default silently.

## Facts, measured on the crew copy (main 7896f3ae75, prompt v189, staff contact, agent switch off)

Dealer A's total after pick + basis: `sales_ranking_frame` holds 9 `customer_ids`, invoiced, 1 to 31 Oct, channel dealer.
Forked from that exact session, each message 3 times:

| Message | Parser (all 9 runs: `entity_op` reuse, `topic_reset` false, no customer as `current_message`) | Reply | Slot `customer_ids` |
|---|---|---|---|
| "how about ordered" | basis ordered | "Sorento or Mocha?" (3/3) | 0 |
| "and delivered?" | basis delivered | "Sorento or Mocha?" (3/3) | 0 |
| "what about last month" | 1 to 30 Sep, no basis | "Invoiced, delivered, ordered or outstanding?" (3/3) | 0 |

- The brief's "Which period?" run: the same words parsed `entity_op` **modify** (crew's run, turn trace), entities [], no
  dates. No code reads `modify`; `with_held` stamps only on `reuse` (`report_ask.py:1049`), so nothing is held.
- `replace_combine` reaches the same place: the parser's own table says "a set of a value -> replace_combine (a new product
  keeps the held customer)" (`parser_template.py:344`), and "total for all customers" came back `replace_combine`.
- A held RANKING loses the customer too. Top 5 products for one customer, then "how about ordered": `ranking_refine` null,
  axis null, "Sorento or Mocha?", slot `customer_ids` 0. `with_held` is off for any ranking frame (`report_ask.py:1052`).
- "by product" over the total: `reuse`, slot keeps channel but `customer_ids` 0.
- Replacing cases, as the parser reads them: "how about all customers" -> `broaden_axis` customer + `broaden_to` all (`reuse`
  or `replace_combine`); "start over ..." -> `entity_op` clear + `topic_reset` true; a new customer -> a customer entity
  `current_message` true, `replace_combine`, and its own `customer_ids`.

## Cause

Two gaps, both in `lanes/business/report_ask.py`. `_HELD_TOTAL_KEYS` (`:1008`) lists `customer_ids` as staying, so the stamp
carries them, but `_settle` reads only `brand_ids, category_ids, sales_agent_ids` off it (`:1813`). And `with_held`'s gate
(`:1047-1055`) stamps nothing on `modify`, `replace_combine` or under a held ranking. The comment at `:1374` is right about
`_fresh_args` (a carried ENTITY is not this ask's filter) and stays: the customer comes from the held REPORT's args, the
ids the report actually ran on, never from re-reading an entity or a name.

## ARCHITECTURE

- **Layer:** the report ask's engine seam (`with_held`) and the lane's hold (`_settle`). Not the parser, not the prompt, no word
  rules; nothing reads the typed text. Parser fields and engine-held state only.
- **Shared mechanism:** the R8/S6b hold that already carries period, product, channel, brand, category and sales agent.
  Customer joins it. No second path.
- **Classes fixed:** a follow-up with no new customer over a held report: total or ranking; `reuse`, `modify` or
  `replace_combine`; any change of basis, period or axis. Not one wording.
- **Explicit links only (owner rule):** the ids are the held report's own (`Focus.sales_ranking_frame`), so a pick's ledgers stay
  exactly the pick's. Nothing is looked up by code or name, so #2064's stranger cannot come back.
- **Prompt:** unchanged, so the prompt pinning gates do not apply.

## Fix

1. `with_held` (`_follows_up`): the stamp also turns on for `modify` naming no customer, and for `replace_combine` naming no
   customer while a customer is held. A ranking frame stays off (its own rules) unless it is filtered to a customer and not stale.
2. `_settle`: `customer_ids` joins the hold (`_customer_stays`), unless the message named a customer, `self_reference` is true, a
   pick answered this turn (`ranking_pick`), the parser widened customers to all, the new axis is customer, or customers were the
   ranked side on an "across all" read. `company` joins it too, or the follow-up asks "Sorento or Mocha?" again after the person
   already answered it (measured, brand total in one company).
3. `_widened`: `customer` joins `channel` and `product`, so `_refine` drops the held customer on "all customers" too.
4. The basis and any measure on screen stay **for a customer that stays** (`_HELD_CUSTOMER_KEYS`), so "what about last month" does
   not ask the basis again. Decided from S6c (`_settle`), the engine's R8 note and `_refine`, which all keep them; the reply's
   header names the basis, so it is not a silent default. A company total with no customer still asks (SALES-TOTAL-ASK, owner 27 Oct).
5. `lanes/business/__init__.py`: a sales analysis over a held customer skips the company total's own basis question. That question
   carries no customer (`sales_basis_ask.CARRIED`), and this is not a company total: the report ask's slot holds the customer across
   anything it still owes.

## Not changed, with reasons

- A follow-up over a ranking with no refine flag runs a total on the held customer and period, not the ranking again: that is the
  parser's reading (`ranking_refine` null, no axis, the sales label), and the ruling is about the customer and the period.
- "by customer" over a customer's total drops the customer: the axis's own filter is never held, as for every other axis.
- `warehouse_codes`, `spec` and `customer_agent_ids` are still not held. Not measured in this lane; the ruling is about the customer.

## Found, not fixed

- **A ranking asked with a customer loses the pick when the parser repeats `top_selling` on the pick turn.** "Dealer <customer> top 5
  products oct by amount delivered", then "1": "Sorento or Mocha?", slot with no customer, on the copy and in the engine harness. The
  same parse with `order_status` null keeps it. The plan row is gone before the lane: the trace's `narrowing` has no
  `sales.customer:just_picked`. Pick turn, not a follow-up, so not this fix. Cause past that point not traced.
- **A bare basis word can read as a document status.** "how about ordered" and "and delivered?" came back `order_status` null or
  `delivered` on 2 of 4 runs with the fix (0 of 6 before it, same prompt and session, so parser variance): an order list instead of a
  figure, on the same 9 ledgers. The customer is kept; the answer type is the parser's call (no post-parser domain override).
- **A total with no customer, "what about last month":** the company total's basis question carries only `sales_basis_ask.CARRIED`, so a
  brand filter on screen is not on the run that follows the answer (read in code, not run).

## Tests (red first)

`tests/chatbot/test_chat_followup_carry.py`, engine level (`test_new_ask_drops_sales_channel.chat`, real gate, parser and
resolver faked, fake customers): the owner's turns, then each follow-up with the parse measured above, plus the replacing cases
as guards. Unit guards on `with_held`. The R8 `OFF` table stays green unchanged.
