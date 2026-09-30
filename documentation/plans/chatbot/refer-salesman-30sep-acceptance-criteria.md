# UAC: REFER-SALESMAN (one wording, every refer reply is a Customer ask)

Plan: `PLAN-refer-salesman-30sep.md`.

## Wording

- **AC-RS01 [MCP]** The `availability` stock answer's three fixed lines read
  `<code> x <Q>: yes, we have stock. Please refer to your salesman.`,
  `<code> x <Q>: the quantity is more than what I can confirm here. Please refer to your salesman.`,
  `<code> x <Q>: no stock and no incoming at the moment. Please refer to your salesman.`
  The `incoming` line (`no stock at the moment, ETA <date>.`) is unchanged.
- **AC-RS02 [MCP]** A dealer's incoming reply closes with exactly `Please refer to your salesman.`
  whether or not the contact's customer has a sales agent; no name is printed.
- **AC-RS03 [BE]** No customer-facing text anywhere in the backend or MCP contains
  `salesperson` in a refer line, or `refer to your salesman to proceed`; the only refer sentence
  is `Please refer to your salesman.` (asserted by a grep-shaped test over the source).
- **AC-RS04 [BE]** The end-to-end dealer incoming turn (real engine, real routes, real
  presenter) prints `<code>` / `ETA: <dates>` and then `Please refer to your salesman.`

## Customer asks rows

- **AC-RS10 [BE]** A dealer incoming ask answered with ETAs writes one `stock_asks` row per
  product line: `branch = incoming_eta`, `quantity` null, `product_code` = the line's code,
  `product_id` resolved by code within the ask's company, `answer_summary` =
  `ETA: <dates>. Please refer to your salesman.`, state open, `notified_agent` false,
  `notify_skip_reason = not_notified_branch`.
- **AC-RS11 [BE]** A dealer incoming miss ("But no incoming matched these." + the refer line)
  writes one row per resolved product entity, `branch = referred`, `quantity` null,
  `answer_summary` = the reply text as sent.
- **AC-RS12 [BE]** A dealer stock miss ("I couldn't find X." + the refer line) writes one row,
  `branch = referred`, `product_code` = the typed code.
- **AC-RS13 [BE]** A dealer's "no" to a did-you-mean writes one row, `branch = referred`,
  `product_code` = the typed code, `quantity` = the carried quantity, `answer_summary` =
  `Please refer to your salesman.`
- **AC-RS13b [BE]** A refer reply that names no product at all writes one `referred` row whose
  `product_code` is the dealer's message text (capped at 100), per the crew-ask recommendation.
- **AC-RS14 [BE]** A stock ask answered with a `stock_availability` entry writes exactly the rows
  it writes today (no duplicate `referred` row for a product that already has a branch row).
- **AC-RS15 [BE]** A staff (non-dealer) turn never writes a `referred` or `incoming_eta` row; a
  dry run that is not the chat console writes nothing.
- **AC-RS16 [BE]** Neither new branch enqueues the salesman WhatsApp job.
- **AC-RS17 [BE]** The migration makes `quantity` nullable and the branch CHECK accept
  `incoming_eta` and `referred`; it is re-runnable.

## Readers

- **AC-RS20 [BE]** `GET /sales/customer-asks/...`, the CRM customer Asks tab endpoint and the
  portal `customer-asks` endpoint return the new rows with `quantity: null` and the new branch;
  the response schema does not drop them.
- **AC-RS21 [FE]** The portal Customer asks list, the CRM Asks tab and the to-do print the ask
  as `<code>` when quantity is null (never `<code> x null`), and label the branches
  `Incoming ETA` and `Referred`.
- **AC-RS22 [FE]** The to-do's "Answered" text for a `referred` / `incoming_eta` row is the
  `answer_summary` as stored (no `<code> x <Q>:` prefix to strip).
