# UAC: Customer amendment requests on the quotation link (QUOTE-CUSTOMER-AMEND)

Plan: `PLAN-quote-customer-amend-29oct.md`. Mock: `documentation/mockups/QUOTE-CUSTOMER-AMEND/index.html` (v3, owner "ok" 30 Oct 10:28).
Contract: the plan's "API contract" section. Every value in tests is fake.

## Customer: suggesting (sign page, public link)

- **AC-QCA-01** On a valid, unaccepted, latest issue the customer can suggest a new quantity and/or unit price per line and submit them in ONE request, with an optional note and an optional name. The request is stored per line and per field (`quantity`, `unit_price`), holding the issued value and the suggested value.
- **AC-QCA-02** Quantity: at least 1, at most 9,999,999.99, two decimals. 0, a negative, more than two decimals or a non-number is refused (422 `quotation_amendment_qty_invalid`), and nothing is stored.
- **AC-QCA-03** Unit price: above 0, at most 9,999,999,999.99, two decimals. Otherwise 422 `quotation_amendment_price_invalid`. A price on a zero-priced line that is not rate-only (a set companion) is refused with the same code.
- **AC-QCA-04** Removal: a line may be marked `remove: true`. It is stored as one `remove` row. Remove together with a quantity or price on the same line is refused (422 `quotation_amendment_remove_conflict`).
- **AC-QCA-05** A value equal to the issued one is not a change and is not stored. A request with no change and no note is refused (422 `quotation_amendment_empty`). A note alone is a valid request.
- **AC-QCA-06** Only lines of the versions this issue carried may be named. Any other line id (another issue, another project, made up) is refused (422 `quotation_amendment_line_unknown`) without saying which ids exist, and nothing is stored.
- **AC-QCA-07** The payload has no field for description, code, brand, spec or any other line field; unknown keys are ignored and nothing but the request rows is written. The issued lines are never modified by a request.
- **AC-QCA-08** One open request per issue. A second submit while one is open is refused (409 `quotation_amendment_open`); two concurrent submits leave exactly one request.
- **AC-QCA-09** An expired or unknown link answers the existing 404 `quotation_sign_link_invalid` for the request route too.
- **AC-QCA-10** An accepted issue refuses a request (409 `quotation_already_accepted`).
- **AC-QCA-11** A superseded issue (a later issue exists on the same document) refuses a request AND a signature (409 `quotation_superseded`), and its sign page says `superseded_by_ref` = the later issue's `our_ref_text`.
- **AC-QCA-12** The public request route is rate-limited per client IP and per token through `app/services/rate_limit.py` (bucket `quotation_amendment`); over the limit answers 429 and stores nothing.

## Customer: waiting and answered

- **AC-QCA-13** While a request is open the customer cannot sign: `accept` answers 409 `quotation_amendment_open` and writes no signature. The sign page carries `can_sign: false` and `sign_blocked_reason: "amendment_open"`.
- **AC-QCA-14** The sign page payload carries every line's `id` and an `amendment_request` block (`null` when none): `status`, `submitted_at`, `requester_name`, `note`, `rows[]` (`id`, `line_id`, `field`, `value_from`, `value_to`, `decision`, `decision_reason`).
- **AC-QCA-15** Once applied, the request's rows carry their decisions and reasons on the same link, and the issue can no longer be signed (`sign_blocked_reason: "amendment_applied"`); the revised quotation goes out with its own link.

## Salesperson: told

- **AC-QCA-16** A submitted request sends ONE notice to the project owner (management when the project has no owner) through `project_notify_service`, type `project_quotation_amendment_requested`, with `send_whatsapp=True` (in-app and email are already on), naming the issue's reference and the number of lines.
- **AC-QCA-17** A request is written to the project activity feed (template `quotation_amendment_requested`). A failing notifier or feed does not fail the customer's request.

## Salesperson: deciding (Lines tab, staff routes)

- **AC-QCA-18** Staff with edit rights on the project read the open (or latest) request of the document's latest issue, and set each row's decision to `accepted`, `rejected` or back to `pending`, with an optional reason (at most 500 characters) on a rejection. Deciding a row of another document's request is 404.
- **AC-QCA-19** A suggested unit price below the line's floor is reported on its row (`below_floor: true`, `floor_value`), judged with the same floor resolution the line writer uses.
- **AC-QCA-20** Apply is refused while any row is `pending` (422 `quotation_amendment_undecided`).
- **AC-QCA-21** Apply revises ONLY the scopes with at least one accepted row (`project_quotation_service.revise`), writes each accepted value onto the copied line in the new version, deletes the copied line for an accepted removal, and leaves rejected rows and untouched lines exactly as issued. Each line's floor flags (`is_below_floor`, `floor_value_applied`) recompute as for a hand edit, and the version total recomputes.
- **AC-QCA-22** The new version is a DRAFT: no issue is created. Issuing it with an accepted below-floor price is refused by the existing gate (422 `quotation_below_floor_pending_approval`) until a manager approves.
- **AC-QCA-23** Apply is refused (409 `quotation_amendment_draft_open`) for a document where a touched scope already has a version later than the issued one, and with the existing lock (422 `quotation_locked_for_approval`) while the document is pending approval or approved. Nothing is written on a refusal.
- **AC-QCA-24** Apply marks the request `applied` with who and when; a second Apply is 409 `quotation_amendment_not_open`. A request with only rejected rows applies without revising anything.
- **AC-QCA-25** Issuing a newer revision while a request is still open closes it as `superseded`.

## Staff UI (QuotationLinesGrid review mode)

- **AC-QCA-26** The Lines grid keeps its own columns (#, Photo, Drawing, Product, Description, Brand, Qty, UOM, Rate (RM), Total (RM)); no Decision column and no new tab.
- **AC-QCA-27** A quantity suggestion renders in that line's Qty cell, a price suggestion in its Rate cell: the issued value struck through, the suggested value, and an Accept and a Reject button in the same cell, labelled "Accept suggested quantity on {line}" / "Reject suggested quantity on {line}" (and "... unit price ..."). A removal renders in the row-actions cell with "Accept removal of {line}" / "Reject removal of {line}".
- **AC-QCA-28** A below-floor price suggestion shows "Minimum price RM {floor}" in its Rate cell.
- **AC-QCA-29** Clicking Accept calls the decide handler with `accepted`; Reject reveals a reason input in the same cell, and the decision `rejected` is sent with the typed reason.

## Customer UI (sign page) - written after QUOTE-SIGN-PAGE (#1987) merges

- **AC-QCA-30** The sign page's own columns stay; Qty and Unit rate become inputs in suggest mode, a narrow last column holds the Trash2 "Remove line {n}" / Undo2 "Restore line {n}" icons; qty below 1 cannot be sent; Sign shows exactly one disabled reason; at 375 the table scrolls inside its card.
