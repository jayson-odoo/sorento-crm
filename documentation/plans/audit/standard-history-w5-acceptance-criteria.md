# UAC: STANDARD-HISTORY wave 5, price tag request History tab

Plan: `PLAN-standard-history-w5-pricetags-13nov.md`. Parent: `PLAN-standard-history-10nov.md`
(waves 1 and 2 merged as #2299 / #2355; their UAC is `standard-history-10nov-acceptance-criteria.md`).

Behaviour card (PR #2390 crew-ask, 13 Nov) answered by crew the same day from prior owner
rulings: Q1 (a) every tracked event, Q2 (a) contact's name via the one shared `audit_actor`,
Q3 (a) same access as opening the request, Q4 (a) request page only, Q5 (a) portal tab and
`_diff_lines` untouched (no overlap with #2386). Criteria name the question they answer.

## Backend

One read: `GET /api/v1/dealer-kit/price-tag-requests/{request_id}/history`, one service
`app/services/price_tag_request_history_service.py` on `app/services/history_common.py`.

- AC-W5-1: Answers `{events: [...]}` in the wave 1 shape (`OrderInquiryHistoryResponse`: `id`,
  `kind`, `at`, `actor`, `title`, `lines[{row_id, so_line_no, item_code, qty, change}]`),
  newest first. Change lines use "→".
- AC-W5-2 (Q3): Gate = the request page's own read (`dealer_kit.price_tag_requests.view` OR
  `.view_own`), staff session only (`require_any_permission`, never `_with_api_key`): an
  X-API-Key principal is refused (401/403). Unknown or malformed id, another company's request,
  or a request outside a `view_own` user's scope: 404, the same as `GET /{request_id}`.
  Read-only: the read writes no row anywhere (including no `data_changed_tag_count` refresh).
- AC-W5-3 (Q1): Events, each from data already recorded:
  - `submitted` "Submitted", `revised` "Edit N", `resubmitted` "Appealed" (each + ": <reason>"
    when one was given): one per `portal_form_revisions` row of this request (kinds original /
    revision / resubmission), actor = the submitting contact's name. "Edit N" and "Appealed" are
    `list_revisions`' own `label` (`_revision_label`, owner hand test 11 Nov: a salesperson's
    edit of their own request "is not a revision"), reused so the portal and CRM tabs name the
    event the same; this supersedes the card's "Revised, revision N" wording (review round 1).
    Lines = that version's `changes` from `PortalRevisionService.list_revisions`, one line per
    change, "<label>: <from> → <to>"; an added line reads "<label>: <to>", a removed one
    "<label>: <from>"; a field set from empty or cleared reads "-" on the empty side. A date
    value reads dd/mm/yyyy through the existing `_format_display_date`. An original has no
    lines. `list_revisions` and `_diff_lines` are reused, not copied or changed.
  - `status_changed` "Status: <old> → <new>" with the screen's labels (`lib/price-tag-status.ts`:
    New, Designing, Design Ready, Changes Requested, Approved, Ready for collection, Collected,
    Rejected, Void): `audit_logs` UPDATE rows on `price_tag_requests` of this request whose
    `new_values` hold `status`.
  - `assigned` "Assigned to <name>" / "Unassigned": the same rows holding `assigned_to_id`.
  - `print_by` "Printing: Office prints" / "Printing: Salesperson prints": rows holding
    `print_by`.
  - `line_price` "Line price changed" with one line per changed field of the line ("<item>:
    promotion <old> → <new>", "<item>: price <old> → <new>"): `audit_logs` UPDATE rows on
    `price_tag_request_lines` rooted at this request whose changed columns include
    `promotion_id`, `manual_sell_price` or `price_type`. A promotion reads by its name.
  - `design_saved` "Design saved, version N" (+ ": <message>"): `page_version` rows of the
    request's page, actor = `created_by`.
  - `changes_requested` "Changes requested: N comments": the salesperson's
    `price_tag_review_comments` of this request (`author_contact_id` set) grouped per `round`,
    at = the earliest comment of the round, actor = its author. A staff note written by a
    transition (D14, `author_user_id`) is not counted there; the status change it rode on is
    already its own event.
  - Any other column change (`updated_at`, counters, `data_checked_at`, draft timestamps) and
    line / tag / part INSERT or DELETE rows are NOT events.
- AC-W5-4 (Q2): Actor is a name. A portal write (`actor_type = contact`) reads the contact's
  name; the shared `history_common.audit_actor` gains this, so the OI and SO History reads keep
  their tests green unchanged. No IP, user agent, raw audit JSON, UUIDs or entity ids in any
  title or line.

## Frontend

- AC-W5-5: The CRM price tag request detail (`PriceTagRequestDetail.tsx`) gets a fourth tab,
  last after Files, labelled History with the History icon (as the SO / OI pages). It renders
  the shared `AuditTrail` entries mode titled History, exactly as the OI / SO tabs (AC-SH-B8 to
  B11: two-line entries, "Show N lines", search only past 10 entries, empty "No history yet",
  error "Could not load the history" + Retry). Request / Lines / Files are unchanged.
- AC-W5-6: Layering: service (`services/priceTagRequestHistoryService.ts` or the dealer-kit
  service) -> hook -> component, `extractApiError`; the History query loads only when the tab is
  opened and is refetched after a header action on the page (status change, claim).
- AC-W5-7: dd/mm/yyyy dates, one line per entry heading, no raw ids; usable at 375 px and
  1280 px.
- AC-W5-8 (Q5): The portal request page's History tab (`PriceTagRequestForm.tsx`) is unchanged.

## Out of scope (Q4)

Tag templates, tag sizes and accessory templates (the template editor keeps its Versions
sheet). Trigger: the owner asks for template edit history; then it joins the "rest" wave.
