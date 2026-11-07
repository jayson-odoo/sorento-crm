# PLAN: reserve email button opens that email's lines, in every state

Status: owner hand test OK except prev/next after reserve + park; fixed in round 2 (e600b89bb2, shared pager keeps its walk), reviewer READY; owner re-check (script steps 15-19) pending. Small fix track (size S after the owner's 3 Nov scope cut): no migration, no
auth/RBAC change, no new external ingest. One coder (tests first, `test(red):` commit alone),
one reviewer, hand test on the crew test copy.

crew-lane: OI-RESERVE-ROUND

Behaviour card: `oi-reserve-round-behaviour-card.md`. UAC: `oi-reserve-round-acceptance-criteria.md`.

## Architecture

- **Layer: backend email context.** `merged_context` (`order_inquiry_reserve_service.py:504`)
  is the one place every reserve email's `reserve.link` is decided. Each request context
  (`_build_context` `:344`, `_build_commit_context` `:405`) gains `reserve.request_id`;
  `merged_context` builds the link from the distinct request ids in context order:
  one OI -> `<OI link>?reserve=<id>[,<id>]`; two or more OIs ->
  `<list link>?display=lines&inquiry_no=<OIs>&reserve_request=<ids>`. The templates already
  render `{{ reserve.link }}` (`oisn_0002_full_table.py:59,91,211,218`), so no template change.
- **Layer: backend list filter.** `reserve_request` (comma-joined request ids, uncapped,
  UUID-validated in `_validate_worklist_filter_uuids` `order_inquiries.py:159`) joins
  `_worklist_filters` (`order_inquiries.py:193`) and the routes that take `inquiry_no`
  (list, summary, export, matrix). `OrderInquiryWorklistService._base`
  (`order_inquiry_worklist_service.py:1348`) keeps a row when an
  `OrderInquiryReserveRequestRow` with `request_id IN ids` names it (EXISTS, beside the
  `reserve` filter at `:1497`), whatever its answer.
- **Layer: FE OI page.** `OrderInquiryLinesTab` takes the OI's reserve requests (already
  fetched by `OrderInquiryDetail.tsx:124`) as a prop. A request id in `?reserve=` seeds a new
  `requestFilter` (string[] of request ids) instead of the State preselect; a line matches
  when any row it folds is named by a selected request's rows. A `SearchableMultiSelect`
  "Request" beside State, options `Request #<ordinal>`, shown when there is at least one
  request. List statuses in `?reserve=` keep today's code path.
- **Layer: FE OI list.** `OrderInquiriesClient` seeds `reserveRequestFilter` from
  `?reserve_request=`, syncs it to the URL, passes it through `orderInquiryService` to list /
  summary / export calls, shows a chip "Reserve requests: N" and clears it with Clear filters.
  `display=lines` already selects the Lines view (`OrderInquiryHeadersOrLinesView.tsx`).

No new class, table, registry or column.

## Slices

1. `test(red):` pytest for AC-1..AC-5, vitest for AC-6..AC-10, committed alone, red output posted.
2. Backend link + filter, then frontend, until green. Kill test.
3. Guide: `documentation/user-guides/supply-chain/order-inquiry-reserve-email.md` (what the button opens).
4. Reviewer, hand-test script, crew-done.
