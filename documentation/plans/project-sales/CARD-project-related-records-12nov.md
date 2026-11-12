# CARD: project related records (lane PROJECT-RELATED-RECORDS)

Status: Q1-Q4 answered (a) by crew 12 Nov from owner rulings; D1-D3 with the owner; mock v2 filed. Track: L (migration: nullable `project_id` on SI and NPA).
Pointers read from origin/main aa82463745. BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend`.

## 1. The six types today

| Type | Project link today | Set by | On the project page today | Linked rows (12 Nov prod clone, counts only) |
|---|---|---|---|---|
| Stock Inquiry (SI) | none. Free text `project_name`, `project_customer` (`models/procurement.py:1063-1064`) | typed in the SI form (`StockInquiryFieldRows.tsx:103`) and the portal/WhatsApp form (`api/v1/external/stock_inquiries.py`) | nothing | 0 linked of 101 (94 have a typed project name) |
| Complaint | `complaints.project_id`, nullable FK, SET NULL (`models/complaints.py:43`, migration `318_complaint_project_link`) | complaint form picker (`ComplaintForm.tsx:905`), checked by `_assert_linkable_project` (`services/complaints_service.py:1845`) | nothing (the complaint shows its project code, `ComplaintDetail.tsx:1246`) | 0 linked of 448 |
| Purchase request (PR) | `purchase_requests.project_id`, nullable FK, SET NULL (`models/procurement.py:1144`, migration `315_sponsorship_link`) | PR form picker (`PurchaseRequestForm.tsx:784`), `assert_linkable_project` (`services/project_service.py:185`) | nothing (the sponsorship tab filters PRs out, `services/sponsorship_link_service.py:163`) | 0 linked of 81 (79 have a typed project title) |
| Sponsorship form (SF) | same table and column as PR, `request_type = 'sponsorship_form'` | SF form picker; portal contacts flagged `requires_registered_project` must pick one | **Sponsorship Form tab** (`SponsorshipsPanel.tsx`, `/projects/{id}/sponsorships`, `samples_pos.py:501`) with a spend rollup per year | 7 linked of 136 (128 unlinked have a typed title) |
| New Product Application (NPA) | none. Free text `project_name` (`models/new_product_application.py:79`) | NPA form; an NPA raised from an SI keeps `stock_inquiry_id` | nothing | 0 (table empty) |
| Order Change Notice (OCN) | does not exist yet (lane OCN-ORDER-CHANGE-NOTICE) | - | - | - |

What it should show: every one of these that is linked to the project, in one place on the project page, each row opening the record.

So today the project page could show at most 7 records across the 13 projects; everything else waits for a person to pick its project (Q5).

Migration size: `stock_inquiries` 101 rows / 248 kB, `new_product_applications` 0 rows. Adding a nullable column with no default plus a partial index is metadata-only and well under a second at this size (timed on a dev copy before merge).

## 2. Proposed display

- One tab **Related** (count badge = rows the viewer can see) replacing today's **Sponsorship Form** tab. Samples Request keeps its own tab (not in this list). Old links `?tab=sponsorships` open Related filtered to Sponsorship form.
- One standard grid, built from `components/common/PanelDataGrid.tsx` with the sponsorship panel as the template: Search, Filters (Type multi-select, Status multi-select), Columns, one line per row, long subject cut with "..." and full on hover.
- Columns (all sortable on the server, so the order holds on page 2): **Type**, **Number**, **Status** (status pill, `lib/status-pill.ts`; complaints use `lib/complaint-status.ts`), **Approval** (PR/SF only, else "-"), **Date** (dd/mm/yyyy via `formatDate`, `lib/helpers.ts:128`), **Raised by** (a name, never an id), **Subject** (SI item description, complaint defect, PR project title, SF what-for, NPA first line or remark), **Value** (PR/SF total, NPA cost when it has one, else "-").
- The sponsorship spend rollup (total and per year) stays as the one line above the grid, shown when the project has sponsorship forms. It is the same `sponsorship_rollup` call as today.
- Row click opens the record's own page (`/procurement-management/stock-inquiries/{id}`, `/complaint-management/complaints/{id}`, `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}`, `/procurement-management/new-product-applications/{id}`). No Open column, no row buttons.
- No Create button inside the tab (one main button per page, in the header).

## 3. Permissions (reuse, no new rule)

- The tab needs the project: `require_any_permission(READ)` (`api/v1/projects/projects.py:53-57`) plus the project own-scope guard (`api/v1/projects/_own_scope.py`). A project of another company is a 404 before anything is read (`get_project_or_404`, company scope).
- Per type, the existing request rule decides: `own_scope.request_access(perms, kind)` (`services/own_scope.py:216`).
  `None` -> that type is left out of the grid and of the Type filter; `"own"` -> only rows that are theirs (`request_clause`, NPA `npa_clause`); `"all"` -> every linked row. Admin and superadmin see all.
- Records are reached only through `project_id = <this project>`, so a record linked to another company's project never appears. Kill test: a record of company B linked to company B's project does not show on company A's project, and a user with only `view_own` sees only their own.

## 4. How an unlinked record gets linked (no name matching)

- SI and NPA get a nullable `project_id` (FK SET NULL, partial index, same as migrations 315/318) and the same project picker the PR form uses (`useProject` / `projectCodeLabel`, `PurchaseRequestForm.tsx:70-71`), checked by the same `assert_linkable_project`. The free-text `project_name` stays as it is (display fallback, like `project_title` on PR).
- Portal / WhatsApp forms offer only the contact's own company projects (`sponsorship_link_service.projects_for_contact`).
- An NPA raised from an SI starts with that SI's project already picked (an explicit id the person sees and can change).
- Existing rows: nothing is backfilled. They stay unlinked until a person picks the project on the record (Q5).

## 5. Plug-in shape for OCN (one registration)

- BE: `app/services/project_related_records.py` keeps `RELATED_TYPES: dict[kind, RelatedType]`. A `RelatedType` names the model, its access kind (for `request_access`), and how its columns map to the shared row (number, status, approval, date, raised by, subject, value). The endpoint `GET /api/v1/projects/{id}/related-records?type=&status=&query=&sort=&dir=&page=&limit=` builds one `UNION ALL` from the registered types the viewer may see, so sort and paging run in SQL.
- FE: `relatedRecordTypes.ts` keeps one entry per kind: label, href(id), status label/pill.
- OCN adds one BE entry and one FE entry. A test registers a fake sixth type and proves it shows without editing the endpoint or the grid.

## 6. Examples (fake names; shapes from the counts above)

- Project PS26-0001 "Fake Tower Phase 1": 2 SF (one approved, one pending), 1 PR, 1 complaint (in progress), 0 SI, 0 NPA linked.
- An SI with free text project "Fake Tower" and no link: does NOT appear until someone picks the project on the SI.
- An NPA raised from SI-000123 that is linked to PS26-0001: opens with PS26-0001 picked.

## 7. Questions

1. **SI and NPA have no project link.** (a) add a nullable `project_id` + the PR-style picker to both forms (staff and portal), existing rows stay unlinked; (b) show them only when reached through another record. Recommendation: (a), the same way PR and complaint were linked (migrations 315/318), and the only way an SI shows on a project without name matching.
2. **Tabs.** (a) one Related tab with a Type filter, replacing the Sponsorship Form tab (the rollup line moves with it), Samples Request stays; (b) one tab per type (five, six with OCN). Recommendation: (a), one grid and one filter instead of six near-identical tabs; the standing rule asks for a linked list in one view.
3. **PR and SF share one table.** (a) same grid, Type column tells them apart; (b) separate. Recommendation: (a). The spend rollup still counts sponsorship forms only.
4. **Columns.** (a) Type, Number, Status, Approval, Date, Raised by, Subject, Value as above; (b) fewer: Type, Number, Status, Date, Subject. Recommendation: (a), every column can be hidden with Columns.
5. **Linking an old or closed record.** Most existing SIs are already answered and may be locked for editing. (a) the Project field stays editable on the record's own page for anyone who can edit that record, even when the record is closed, and the change shows in its History; (b) only through the normal edit, so closed records stay unlinked; (c) a "Link records" picker on the project page. Recommendation: (a), linking is filing, not changing the request, and it stays on the record's page as today.

## 8. Why purchase requests and complaints have zero links (crew asked, 12 Nov)

- The link columns are not new: `315_sponsorship_project_link` (purchase_requests.project_id) and `318_complaint_project_link` (complaints.project_id) both landed 17 Aug 2026 (#155), with a "Registered project (optional)" picker on the STAFF purchase request / sponsorship form (`PurchaseRequestForm.tsx:779-800`) and complaint form (`ComplaintForm.tsx:900-915`).
- The PORTAL forms (what salespeople fill from the WhatsApp link) never got it for complaints and purchase requests: in `SubmissionForm.tsx` the complaint and purchase_request field lists hold only the typed `project_title`; only `sponsorship_form` has `project_id` (`:387-397`). That is why the 7 linked records are all sponsorship forms.
- Second cause: only 13 projects exist, and portal project registration arrived 26 Oct (#1849), so most of these records predate any project they could point to.
- Complaints do carry a free-text project name: `complaints.project_title` (`models/complaints.py:38`), like `purchase_requests.project_title`.
- Consequence for this lane: AC-C3 adds the portal picker to complaint and purchase request too (CRM forms = portal forms, owner 28 Oct).
