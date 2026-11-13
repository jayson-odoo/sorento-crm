# PLAN: standard History tab, wave 5: price tags (STANDARD-HISTORY-W5)

Status: Build (track M, lane STANDARD-HISTORY-W5, PR #2390). Card answered 13 Nov (all five
recommendations). LEAD pattern: tester (red) -> coder -> reviewer -> browser pass.

Parent plan: `PLAN-standard-history-10nov.md` (waves). UAC: `standard-history-w5-acceptance-criteria.md`.

## Journey

Owner 13 Nov ~11:00: is price tag request history "in system view"? Today the CRM price tag
request detail has Request / Lines / Files only, while the portal request page has a History
tab. This wave adds the standard History tab (shared `AuditTrail`, entries mode) to the CRM
price tag request detail. Templates stay out (Q4, trigger in the UAC).

## Reuse (discovery, file:line)

| Piece | Existing function | Use |
|---|---|---|
| History list UI | `components/audit/AuditTrail.tsx:100` entries mode | reuse as is |
| Entry type | `types/recordHistory.types.ts:14` | reuse as is |
| Tab wrapper pattern | `components/audit/SalesOrderHistory.tsx` | copy the 20-line pattern for the request (own hook/service) |
| Response schema | `OrderInquiryHistoryResponse` (wave 1) | reuse as is |
| Actor names | `history_common.audit_actor` (`history_common.py:19`) | EXTEND: contact actors (Q2) |
| Times | `history_common.iso` | reuse |
| Revision lineage + diff | `PortalRevisionService.list_revisions` (`portal_revision_service.py:1221`), `_diff` `:1470`, `_diff_lines` `:2249` | reuse as is, untouched (Q5, #2386 owns `_diff_lines`) |
| Design versions | the `page_version` read in `GET /{id}/versions` (`price_tag_requests.py:823`) | same query, one shared helper if both need it |
| Review comments | `price_tag_review_service.list_comments` | reuse |
| Request lookup + scope | `PriceTagRequestService.get_request` (as `GET /{id}`, `price_tag_requests.py:266`) | reuse |
| Status labels | `lib/price-tag-status.ts:21` | the backend title uses the same words (one backend map in the history service) |

## Standing rules that apply

History tab via shared component (who, on behalf of, when, plain action, old -> new); dates
dd/mm/yyyy; no internal ids or raw codes; plain business words; person by name; nothing hangs
(error + Try again); reuse functions; 375 / 1280 px usable; one main button per page (unchanged).
