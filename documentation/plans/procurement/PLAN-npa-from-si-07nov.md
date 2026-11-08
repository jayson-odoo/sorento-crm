# PLAN - NPA from Stock Inquiry with product code lineage (NPA-FROM-SI)

Lane NPA-FROM-SI, size L, issue #2200. Status: PR ready (#2233; reviewer READY, security CLEAN; crew browser pass + owner hand test next). Owner OK on mock v3 7 Nov ("ok to start", Brand removed); Q1' and Q2-Q5 = the recommended (a) answers drawn on the approved mock.
Track: full (additive migration, portal surface, security-reviewer for portal access).

Builds on NEW-PRODUCT-APP (#1769, `PLAN-new-product-application-17oct.md`).
- Behaviour card (the rules; not restated here): `CARD-npa-from-si-07nov.md`.
- Mock: `mockups/npa-from-si-v3.html` (v1, v2 kept).
- UAC: `npa-from-si-acceptance-criteria.md` (written once Q1-Q5 are answered).

## Design (v3, owner mock notes 7 Nov)

One application = PRODUCT CODES (current catalogue codes, one multi-select under STOCK INQUIRY) -> ONE NEW PRODUCT
CODE (under REMARK, purchasing links it). The product table is today's form, unchanged.

### Data (migration `npasi_0001_lineage`, additive, `IF NOT EXISTS`, parent `slb_0001_leaderboard_perm`)
- `stock_inquiries`: `npa_requested` (default false), `npa_requested_by` -> users SET NULL, `npa_requested_at`.
- `new_product_applications`: `new_product_id` -> products RESTRICT, `new_code_closed_reason`, `new_code_by` ->
  users SET NULL, `new_code_at`; CHECK not both product and reason.
- `new_product_application_sources`: `id`, `application_id` CASCADE, `product_id` RESTRICT, `position`;
  UNIQUE (application_id, product_id).

## API contract (as built, BE green)

Staff, base `/api/v1/procurement/new-product-applications`:

| Method + path | Who | Answer |
|---|---|---|
| GET `/products?q=` | create or open_code | `[{id, product_code, product_name, brand_name}]` (empty q = []) |
| GET `/reuse-suggestions?product_ids=a,b` | any NPA slug | `Suggestion[]` (newest first, max 3) |
| GET `/lineage?product_id=` | NPA view/approve/open_code or `master_data.products.view` | `{created_from: Row[], made_from_this: Row[]}` |
| GET `/prefill?stock_inquiry_id=` | create | as before + `remark` from the SI, header `current_product_ids` + `current_products` |
| POST `/{id}/new-code/link` `{product_id}` | open_code, Approved | Detail; Completed |
| POST `/{id}/new-code/close` `{reason}` | open_code, Approved | Detail; Completed |
| POST `/{id}/new-code/undo` | open_code, Approved/Completed | Detail; back to Approved |

- Write HEADER gains `current_product_ids?: string[]` (left out keeps, `[]` clears; 422 "<code> is already one of the
  product codes." / "A chosen product code does not exist."). Lines keep today's fields only.
- Detail gains `current_products: [{id, product_code, product_name, is_active}]`, `suggestions: Suggestion[]`
  (itself excluded), `new_product_id, new_product_code, new_product_name, new_product_active,
  new_code_closed_reason, new_code_by_name, new_code_at`, `stock_inquiry: {id, inquiry_number, product_code, status,
  item_description, purchasing_response, quantity} | null`.
- Summary (list + detail) gains `created_codes: [{product_code, current_codes: string[], created_at}]` (0 or 1).
- Suggestion (staff) = `{product_id, product_code, product_name, is_active, description, created_at, application_id,
  application_no}`; portal drops `application_id`, `application_no`. `description` = the product types joined "; ".
- Lineage Row = `{application_no, product_id, product_code, product_name, is_active, current_products[],
  description, created_at}` + `application_id, customer_name, project_name, expected_qty` for NPA view-all only.
- Detail gains `new_product_facts` (item group, base UOM, list price, supplier of the new code; portal: supplier only).
- Portal `GET /submissions/stock_inquiry/{id}` also answers `npa_form_visible` (the contact holds the NPA form);
  `new_product_applications` is `[]` without it.
- The per-row link / close / undo routes stay for an application worked line by line before v3; the screens use
  the header new code only (removal is a follow-up once the owner confirms Q1').
- Stock inquiry: `PUT /stock-inquiries/{id}` and `POST /{id}/update-and-reply` accept `npa_requested: bool` (a
  response write, 422 outside pending_purchasing / responded; an unchanged echo is fine); the server stamps
  `npa_requested_by/at`. Detail answers `npa_requested, npa_requested_at, npa_requested_by_name`. The reply adds
  "Next step: please create a New Product Application for this inquiry." while asked and no live NPA exists.

Portal, base `/api/v1/public/portal`: GET `/new-product-application/products?q=`,
GET `/new-product-application/reuse-suggestions?product_ids=` (portal Suggestion); NPA write/detail as staff (portal
Suggestion shape); prefill scoped to the contact's company; `GET /submissions/stock_inquiry/{id}` gains
`npa_requested` and `new_product_applications: [{id, application_no, status, status_label, created_at,
created_codes}]` (the contact's OWN applications from that inquiry only).

## Test list
pytest (green): `tests/test_npa_from_si.py` (current codes, reuse exact set / order / subset / superset / closed /
undo / newest-first-3 / not itself, lineage + 403, prefill exact + remark + labels, SI ask stamp / clear / gate /
echo, reply sentence vs live NPA, summary created_codes, detail stock_inquiry) and `tests/test_npa_from_si_portal.py`
(product search company-only, round trip, foreign 422, suggestion without application / customer, detail
suggestions portal-shaped, SI ask + own applications only, created codes, prefill exact).
vitest (FE slice): multi-select product code cell sends `current_product_ids`, read-only chips, "Inquiry asked"
hint, suggestion row text per surface, "Use <code>" fills the link picker without linking, SI checkbox sends
`npa_requested`, portal SI banner + CTA only while asked and no live NPA, tabs + empty states, product Lineage tab.

## Decisions after the mock OK (7 Nov)

- Owner: mock v3 approved ("ok to start"), Brand column removed from the product table (screens only; the BE still
  accepts `brand_id`, the column stays).
- Crew B (a): SI attachments on the NPA are OUT of scope, follow-up lane (link-only copy, own security pass).
- Crew C (a): the per-row link / close / undo routes stay; pre-v3 applications show their per-row result read-only
  (staff keep Undo); removal follows a production count.
- A (Excel BRAND row): owner (a) "NPA can keep": the row stays, empty on new applications, filled on older ones.
- Exemption: the two embedded read-only lists (SI "New product applications", product Lineage) are plain bordered
  tables like `SampleRequestLines`, not DataGrids (a few rows, no search / sort / pagination).

## Owner hand-test round 3 (8 Nov 09:30 + 12:50)

- Customer = the stock inquiry's customer dropdown: one shared `components/common/CustomerDebtorCombobox.tsx`, the
  same `/public/portal/lookups/debtors` call (no kind: every company of the contact). Owner 12:50, option (a)
  "just behave like how stock inquiry behaves now": a pick of the application's own company links by id; a pick of
  the contact's other company is kept as text "<code> - <name>" with no id (the SI keeps every customer as text);
  the application stays in its company; never a 422 for that (`portal_new_product_application._keep_other_company_customer_as_text`).
- No "Waiting for approval / Locked" banner on Submitted / Resubmitted.
- Not opening became Reject: `POST /{id}/purchasing-reject` (open_code, Approved, reason) -> Rejected, the applicant
  resubmits; the shared `RejectOutlineButton` (the SI's style); older Not opening results read Rejected
  (`display_status`), and no longer answer the SI's ask.
- Crew took the recommendations: Excel BRAND row kept; SI attachments -> follow-up lane; old per-row routes kept until
  production shows none.

## Owner hand-test round 4 (8 Nov 15:10): the SI's Edit purchasing response

- One shared `components/common/PurchasingResponseDialog.tsx`, extracted from the SI's inline dialog, used by the SI
  and the NPA: "Purchasing response" text, then the form's own fields (NPA: Link / New product code, Lead time, Cost),
  then Cancel / Save only / Update & Reply. The NPA gains `purchasing_response` (additive, same unmerged migration).
- Update & Reply (`POST /{id}/purchasing-response/reply`) saves, then replies to the salesperson through the linked
  stock inquiry's conversation with the SI's own chat send (`enqueue_chat_send`, use case stock_inquiry_chat). The
  send's precheck runs before the commit, so a reply that cannot go saves nothing. A standalone NPA cannot reply.
- "No answer yet" is gone (the SI has no equivalent); a recorded outcome is not cleared back to Approved from the UI,
  as on the SI (the API still accepts `outcome: null`).
- Accepted (security round 6, nit 1): staff can link any existing SI, and Update & Reply then reaches that SI's
  requester. It adds no reach (any procurement user can already message an SI's contact) and the reply's purpose is
  the SI's requester, so the contact-match rule was not added.

## Crew pass on 62534a9c25 (8 Nov): the same reply, long project names

- Update & Reply now sends the SI's OWN reply, not a chat message: `StockInquiryService.enqueue_update_reply`
  (extracted from `update_inquiry_and_reply`, which calls it too, so the two cannot drift) queues
  `send_stock_inquiry_respond_message` (use case stock_inquiry, template stock_inquiry_update_with_button out of the
  window) with `update` = "NPA-xxxxxx: <response>" + "New product code: <code>" + "Lead time: <lead time>". Its View
  button keeps opening the SI portal page. The SI's refusal (no Respond.io conversation) runs before the commit, so
  nothing is saved; there is no separate chat precheck any more (the SI has none). The `enqueue_chat_send`
  extraction is reverted to main.
- The dialog's description line is the SI's on every caller (the prop is gone).
- The bell "NPA-xxxxxx is done: the codes are open" on Save only is main's lifecycle notice (#1769, every
  Approved -> Completed move), not a reply; it stays. Save only sends no message.
- `new_product_applications.project_name` is TEXT, as the SI's (SI26-0139 is 586 characters): one widening statement
  in the unmerged `npasi_0001_lineage`, never narrowed on downgrade. The detail's PROJECT clamps to two lines with
  the full name behind the eye button (`TruncatedTextCell`).
- Crew answer on a36de9009 (same component as the SI): the NPA reply refuses outside the SI's response stage with
  the SI's own guard (`response_gate.assert_response_write_allowed("stock_inquiry", ...)`, same sentence), before the
  save, so nothing is saved or queued; `can_reply` follows the SI page's rule (inbox AND response stage), so the
  button is not drawn on a closed SI. Save only stays allowed, as on the SI.
