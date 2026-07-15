# Complaints — Data analysis for the AI assistant

Reference for answering "list / filter / count / status" questions about customer **complaints** and their master data. Field names, statuses, and the SLA linkage below are taken verbatim from the backend (`app/models/complaints.py`, `app/models/complaint_master_data.py`, `app/services/complaints_service.py`, `app/services/complaint_master_data_service.py`) and the complaint frontend (`complaint-management/*`). UI labels are quoted verbatim from the React components.

The three entities and their backing tables: **Complaint** (`complaints`), **Complaint Root Cause** (`complaint_root_causes`), **Complaint Resolution** (`complaint_resolutions`). Complaint SLA timers live in the shared `conversation_sla_tracking` table under the **form** scope (`source_entity_type = 'complaint'`).

> **Reading notes for the assistant**
> * **There is NO complaint-list MCP tool.** The AI assistant cannot enumerate or filter complaint records directly — see [What the assistant can and can't read](#what-the-assistant-can-and-cant-read) below. Direct complaint listing/export is a power-user job on the [Complaints](/complaint-management/complaints) list page. The assistant answers complaint **status / SLA / breach** questions via the SLA tools (`crm_sla_conversation_tracking_list`, `crm_sla_conversation_event_logs_list`) filtered to the form scope, plus this data-model reference for grounding the vocabulary.
> * **Status drives everything.** The complaint lifecycle `status` string (not a separate "stage" table) drives the status pill on both the internal view and the customer portal. The exact codes + human labels are below — use them, don't invent "Open / Closed".
> * **No UUIDs in answers.** A complaint is identified to people by `complaint_number` (or its delivery-order number / customer name), never its internal id. Root causes and resolutions are identified by `name`.
> * **`contact_id` is the internal `respond_contacts.id` (UUID), not the Respond.io `respond_io_id`.** It scopes a complaint to a Respond.io contact for portal / chat resolution; never surface it and never treat it as the WhatsApp/Respond.io contact number.
> * **Timestamps are naive UTC.** `created_at`, `last_responded_at`, `rejected_at`, `resolved_at`, the `*_notified_at` columns and the SLA clocks are all stored naive UTC; `complaint_date` is a plain date. Be explicit about timezone when quoting times (the UI renders Malaysia time).

---

## Complaint — `complaints`

A single customer complaint about a delivered product / order, moving through a fixed status lifecycle. One or more affected products are captured as per-product line items.

**Key fields**

| Field | Meaning |
|-------|---------|
| `complaint_number` | Human-readable reference (UI **Complaint Number**). Nullable — externally created complaints may not have one yet. |
| `delivery_order_number` | The originating delivery-order number(s) (UI **DO Number**); free text, may be comma/semicolon/newline-separated and resolved against `orders.order_number`. |
| `complaint_date` | Date the complaint was raised (UI **Complaint Date**). A `date`, not a timestamp. |
| `customer_name` | Customer / debtor name (UI **Customer Name**). |
| `customer_type` | Who is complaining. Recommended values: `dealer`, `end_user`, `project`, `other` (with `customer_type_others` when `other`). Stored as free text. |
| `within_warranty` | Warranty status. Recommended values: `Yes`, `No`, `Not sure`. Stored as free text. |
| `product_type` | Generic product category, CSV-aligned with `product_code` (e.g. `bathtub`, `basin`, `faucet`). |
| `product_code` | Affected product code(s) (UI **Product Code**); CSV, index-aligned with `product_type` / `quantity` and mirrored from `product_lines`. |
| `quantity` | Affected unit count(s), CSV index-aligned. Free text ("5" or "5 boxes"). |
| `complaint_type` | Kind of issue (UI **Complaint Type**). Typical buckets: Broken, Damaged, Scratch, Wrong Item, Missing Parts, Defect, Other. Free text. |
| `defects_discovered` | When the defect was discovered (date or phrase like "on delivery"). |
| `defect_description` | One/two-line description of the defect. |
| `salesperson` | Sales rep (UI **Salesperson**). |
| `contact_person`, `contact_number`, `customer_address` | Customer-side contact + site/delivery address. |
| `project_title` | Project name when the complaint is for a project order (UI **Project Title**). |
| `required_on_site_support` | Boolean — whether on-site support was requested. Default `false`. |
| `status` | Lifecycle status (UI **Status**). Default `new`. See [Statuses](#complaint-statuses-enum). |
| `assigned_to` | Respond.io assignee user id (UI **Assigned To**); display name resolved via `User.respond_user_id`. For the list/detail page the *effective* assignee shown comes from the latest unresolved complaint SLA tracker's assignee, falling back to this column. |
| `root_cause_id` → `complaint_root_causes` | Selected root cause (optional). Serialized as `root_cause_name`. |
| `resolution_id` → `complaint_resolutions` | Selected resolution (optional). Serialized as `resolution_name`. |
| `technical_team_response` | The technical team's reply text sent to the customer. |
| `rejection_reason`, `rejected_at`, `rejected_by` | Set when a complaint is rejected (cleared again on a later approval). |
| `resolved_at`, `resolved_by` | Set when finalized (processed by CS / closed). |
| `root_cause_notified_at`, `resolution_notified_at` | When the root-cause / resolution was notified out. |
| `contact_id`, `space_id` | Respond.io contact (internal `respond_contacts.id` UUID) + workspace/space scope. Internal — never surfaced. |
| `last_responded_by`, `last_responded_at` | Who last replied + when (naive UTC). Serialized with `last_responded_by_name`. |
| `portal_draft_at` | Set while the contact is editing in the submission portal; cleared on Submit. |

**Per-product lines (`complaint_product_lines`):** the source of truth for affected products — `product_code` (required), `quantity` (free text), `product_type` (auto-derived from product master), `sort_order`. The `product_code` / `product_type` / `quantity` CSV columns on `complaints` are kept denormalized (index-aligned) from these for backward compat (n8n, public view).

**Date columns:** `complaint_date` (date; default sort, ascending), `created_at`, `last_responded_at`, `rejected_at`, `resolved_at`, `root_cause_notified_at`, `resolution_notified_at`. **For a bare time window** ("complaints between Jan and Mar") default to `complaint_date`; use `created_at` when the user says "created/raised in the system".

**List filters (Complaints list / `GET /api/v1/complaints-management/complaints/`):**
* `query` — free-text search across complaint number, DO number, customer name/type, contact person/number, address, product code/type, complaint type, defects, defect description, salesperson, project title, warranty, status, assignee (UI **Search complaints…**).
* `assigned_to` — exact Respond.io assignee id; the sentinel `__unassigned__` matches unassigned complaints (UI **All assignees**).
* `status` — exact status code (UI **All statuses**).
* `contact_id` / `space_id` — scope to one Respond.io contact/space (external callers only).
* `page`, `limit`, `sort`, `dir`.

**Sortable columns:** `complaint_date` (default, `asc`), `created_at`, `delivery_order_number`, `customer_name`, `product_code`, `salesperson`, `assigned_to`, `status`. (Unknown sort keys fall back to `complaint_date`; `complaints.id` is always the deterministic tie-breaker.)

**List columns (UI, verbatim):** **DO Number**, **Complaint Number**, **Complaint Date**, **Created at**, **Customer Name**, **Product Code**, **Complaint Type**, **Project Title**, **Salesperson**, **Status**, **Assigned To**, **Attachments**, **Print Count**.

**Example questions** (answerable by a power user on the Complaints list / export; the assistant answers the status/SLA-flavoured ones via the SLA tools — see below):

* "List complaints for customer {X} from January to March." (filter customer + `complaint_date` range)
* "Show complaints with status Responded assigned to {user}."
* "How many complaints came in this month?" (count by `complaint_date` / `created_at`)
* "List complaints for product code {SRT-100} between {A} and {B}."
* "Which complaints are unassigned?" (`assigned_to = __unassigned__`)
* "Show rejected complaints and their rejection reason."
* "List complaints for delivery order {DO-123}."
* "How many complaints by complaint type this quarter?" (group by `complaint_type`)

---

## Complaint Root Cause — `complaint_root_causes`

Master-data list of selectable root causes assigned to a complaint (UI: **[Root Causes](/complaint-management/complaint-root-causes)**).

**Fields:** `id`, `name` (unique, required; UI **Name**, e.g. "Manufacturing defect"), `description` (UI **Description**), `is_active` (UI **Active**), `created_by`, `created_at`, `updated_at`. The response also carries computed `complaint_count` (UI **Complaints**) — how many complaints reference this root cause.

**Date columns:** `created_at`, `updated_at`.

**List filters (`list_root_causes`):** `query` (matches `name` / `description`; UI **Search root causes…**), `is_active`, `page`, `limit`. Always sorted by `name` ascending. Delete is blocked while `complaint_count > 0` (FK `ondelete="RESTRICT"`).

**Example questions**

* "List active complaint root causes." (`is_active = true`)
* "Which root cause is used by the most complaints?" (sort/aggregate by `complaint_count`)
* "Is there a root cause called 'Manufacturing defect'?"
* "Show inactive root causes."
* "How many complaints have root cause {X}?" (`complaint_count`)
* "List root causes with no complaints attached." (`complaint_count = 0`)

---

## Complaint Resolution — `complaint_resolutions`

Master-data list of selectable resolutions assigned to a complaint (UI: **[Resolutions](/complaint-management/complaint-resolutions)**).

**Fields:** `id`, `name` (unique, required; UI **Name**, e.g. "Replacement issued"), `description` (UI **Description**), `is_active` (UI **Active**), `created_by`, `created_at`, `updated_at`. The response also carries computed `complaint_count` (UI **Complaints**).

**Date columns:** `created_at`, `updated_at`.

**List filters (`list_resolutions`):** `query` (matches `name` / `description`; UI **Search resolutions…**), `is_active`, `page`, `limit`. Always sorted by `name` ascending. Delete is blocked while `complaint_count > 0` (FK `ondelete="RESTRICT"`).

**Example questions**

* "List active complaint resolutions."
* "Which resolution is applied most often?" (sort/aggregate by `complaint_count`)
* "Is there a resolution called 'Replacement issued'?"
* "Show resolutions used by zero complaints."
* "How many complaints were resolved via {resolution}?" (`complaint_count`)
* "List inactive resolutions."

---

## Complaint statuses (enum)

`complaints.status` is a free-text column with a **fixed working set** of codes driven by the lifecycle in `complaints_service.py`. Default on create is `new`. Human labels come from `lib/complaint-status.ts` (`complaintStatusLabel`) — most are title-cased; `processed_by_cs` has an explicit label.

| Code | Human label | Meaning |
|------|-------------|---------|
| `new` | New | Just created (default). |
| `draft` | Draft | Portal draft (contact still editing in the submission portal). |
| `submitted` | Submitted | Submitted by the contact (portal) / externally created, awaiting review. |
| `updated` | Updated | Edited while still in the response stage. |
| `responded` | Responded | Technical-team reply sent to the customer. |
| `approved` | Approved | Approved after the reply (decision stage). |
| `rejected` | Rejected | Rejected after the reply; `rejection_reason` required. |
| `processed_by_cs` | Processed by CS | Customer service handled the case (normal CS completion). |
| `closed` | Closed | Approved complaint that could not be resolved; CS stage closed. |

> `resolved` appears in the status-pill colour maps (`lib/complaint-status.ts`, `lib/status-pill.ts`) but the CS-completion lifecycle finalizes to `processed_by_cs` or `closed`, not a literal `resolved` status — treat "resolved/closed/processed by CS" as the terminal set.

**Lifecycle (response → decision → CS close):**

```
new / submitted / updated  →  responded  →  approved | rejected
approved  →  processed_by_cs | closed
```

* `responded` is only reachable from a response-stage status (`new`, `submitted`, `updated`, `responded`); re-replying on a decided complaint delivers the message but never regresses the status.
* Approve / reject is allowed only from `responded`. Rejecting requires a `rejection_reason`; approving clears any prior rejection metadata.
* `processed_by_cs` / `closed` are allowed only from `approved`, and both close the customer-service SLA stage.

**Example questions**

* "How many complaints are awaiting a technical response?" (status in `new`/`submitted`/`updated`)
* "List complaints approved but not yet closed by CS." (`status = approved`)
* "Show complaints processed by CS this month." (`status = processed_by_cs`)
* "How many complaints were rejected vs approved this quarter?" (group terminal-ish statuses)

---

## SLA linkage (complaint = form SLA, scope `complaint`)

Complaint SLA timers are **Form SLA** rows in the shared `conversation_sla_tracking` table, discriminated by `source_entity_type = 'complaint'` (one of `FORM_SLA_TYPES`). They are **per-entity and multi-active**: a single complaint can have multiple open SLA rows, one per active stage (e.g. the technical-response stage vs the customer-service stage). Never assume one timer per complaint.

How they connect to the lifecycle: complaint actions emit form-SLA events via `emit_form_event(..., "complaint", ...)` — `submit` on create, `technical_team_response` on reply, `approved` / `rejected` on decision, and the CS finalize closes the stage with a resolve event. The complaint's effective **Assigned To** (list + detail) is read from the **latest unresolved** complaint SLA tracker's assignee (`is_resolved = false`, ordered by `initiated_at` desc), falling back to `complaints.assigned_to`.

For analytical SLA questions the assistant reads these timers through the SLA tools at the **form scope**, filtering `source_entity_type = 'complaint'`:

* `crm_sla_conversation_tracking_list` — the complaint timer rows (clocks, tier, assignee, resolved flags).
* `crm_sla_conversation_event_logs_list` — escalations / responses / resolutions / reassignments per timer (join via `tracking_id`).

Compute met / breach **per clock** (response vs resolution) exactly as defined in [../sla/data-analysis.md](../sla/data-analysis.md) — that doc is the source of truth for the SLA fields and the met/breach maths. The complaint `reference` shown by the SLA layer is the complaint number.

**Example SLA questions** (answerable via the SLA tools):

* "Which complaints breached resolution and are still unresolved?" — scope=form, `source_entity_type='complaint'`, `NOT is_resolved AND due_at_resolution < now`; show the complaint `reference`.
* "How many complaint SLA timers opened this month, and how many are resolved?" — scope=form, `source_entity_type='complaint'`, bucket by `initiated_at`.
* "Average complaint resolution time this quarter." — scope=form, `source_entity_type='complaint'`, `avg(resolution_duration)` (hours).
* "Which complaint timers escalated to tier 2+ last week?" — event logs, `event_type='escalation' AND to_tier >= 2`.
* "Who has the most open complaint SLA tasks?" — scope=form, `source_entity_type='complaint'`, group open rows by `assigned_to_id`.

---

## What the assistant can and can't read

* **Can:** complaint **SLA** state and history (open/overdue/breach, escalations, assignees, durations) via `crm_sla_conversation_tracking_list` / `crm_sla_conversation_event_logs_list` at the form scope (`source_entity_type='complaint'`); and this page's data model to ground complaint/root-cause/resolution vocabulary and statuses.
* **Cannot:** enumerate, filter, or export the complaint records themselves — there is **no** `crm_complaints_*` MCP tool in the catalog. For "list / show / export complaints with filter X" point the user to the **[Complaints](/complaint-management/complaints)** list page (search, **All assignees** / **All statuses** filters, column export). Master data lives at **[Root Causes](/complaint-management/complaint-root-causes)** and **[Resolutions](/complaint-management/complaint-resolutions)**.

When asked a record-level question you can't run, say so plainly and hand off to the list page rather than guessing.

## See also

* [Complaint lifecycle and next actions](../technical-team/complaint-lifecycle-and-next-actions.md)
* [Set root cause and resolution](../technical-team/set-root-cause-and-resolution.md)
* [Respond to a complaint](../technical-team/respond-to-complaint.md)
* [Approve or reject a complaint](../technical-team/approve-or-reject-complaint.md)
* [SLA — Data analysis (form SLA scope)](../sla/data-analysis.md)
