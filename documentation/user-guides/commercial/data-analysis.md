# Commercial - Data reference for analysis & questions (AI assistant + power users)

This page documents the commercial data model so the assistant (and power users) can answer "list / filter / count" questions accurately. The commercial hierarchy is:

```
Customer (client) → Lead → Project → Tender → Master Quotation → Quotation Revision → Sales Order
```

Each entity below lists what it stores, the fields that matter for filtering/reporting, its date columns, its status/enum values, and example natural-language questions you can answer by listing/filtering that entity.

> **Reading notes for the assistant**
> * **Stages are configurable, not fixed enums.** Lead / project / tender / quotation "Status" comes from the tenant's workflow-stage list (domains `lead`, `project`, `tender`, `quotation`). Resolve stage names from the live stage list; don't assume a fixed set like "New / Won / Lost".
> * **Tender outcome and sales-order status ARE fixed enums** (listed below).
> * Codes (lead code, tender code, quotation code, sales-order number) are human-readable; show them, not internal UUIDs.
> * Money fields store an amount + a separate currency code - always pair them.

---

## Lead

The opportunity record: a client plus a qualification profile, moving through configurable **lead stages**.

**Key fields**

| Field | Meaning |
|-------|---------|
| `lead_code` | Human-readable reference ("Lead Ref"). |
| `title` | Lead title. |
| `customer_id` → client | The client/customer the lead is for ("Client Name"). |
| `owner_user_id` | Lead owner. |
| `lead_stage_id` → stage | Current lead stage (shown as **Status**). |
| `qualification` (JSON) | Profile: `property_type`, `property_status`, `property_value` (+ currency), `budget_range`, `sales_closure_confidence`, `referral`, `address_line_1/2`, `postcode`, `city`, `state`, `country`, `est_project_start`, `est_project_end`, `client_phone`. |
| `qualification_summary` | One-line summary (budget / confidence / referral). |
| `created_by_user_id`, `respond_workspace_id` | Creator; optional linked Respond.io workspace. |

**Date columns:** `created_at`, `updated_at`. (Qualification also carries estimated project start/end dates.)

**Status values:** configurable lead stages (workflow domain `lead`). Stages flagged **terminal** end the pipeline (e.g. Won / Lost equivalents).

**Available filters** (Leads list / API): client, owner, lead stage (by id or `stage_code`), free-text **search** (code/title/client), `without_project` (leads not yet attached to a project), `open_pipeline_only` (exclude terminal stages), `terminal_pipeline_only` (only terminal stages), `customer_active_only`, and **date range** `created_from` / `created_to`. Sortable by `created_at`, `updated_at`, `lead_code`, `title`, `customer_name`, `stage_name`.

**Example questions**

* "List leads created between January and March for client {X}."
* "Show open leads (not in a terminal stage) owned by {user}."
* "How many leads are in the {stage} stage?"
* "Which leads don't have a project yet?"
* "List leads with budget range {RM band} and high sales-closure confidence."
* "Show leads created this month, sorted by client name."
* "Which leads are linked to a Respond.io workspace?"

---

## Project

The delivery container under a lead; owned by a **developer** customer and grouping tenders.

**Key fields**

| Field | Meaning |
|-------|---------|
| `title` | Project title. |
| `developer_customer_id` → customer | The developer (required). |
| `owner_user_id`, `project_owner_user_ids` (JSON) | Owner + additional owners. |
| `lead_id` (+ linked `projects.leads`) | Originating lead and any additionally linked leads. |
| `project_stage_id` → stage | Project workflow stage (shown as **Status**). |
| `status` | Free-text lifecycle string (default `active`). |
| address fields | `address_line_1/2`, `postcode`, `city`, `state`, `country`. |
| `task_template_id` | Applied task-board template. |
| `brief`, `notes` | Free text. |

**Date columns:** `start_date`, `end_date`, `created_at`, `updated_at`.

**Status values:** configurable project stages (workflow domain `project`); plus the free-text `status` (defaults to `active`).

**Available filters** (Projects list / API): free-text **search**, owner, `status`, project stage id, lead id, customer id.

**Example questions**

* "List projects owned by {user}."
* "Show projects for developer {customer}."
* "How many active projects do we have?"
* "Which projects start after {date}?"
* "List projects linked to lead {lead_code}."
* "Show projects in the {stage} stage created this quarter."

---

## Tender

The competitive opportunity under a project; carries forecast value, lifecycle and outcome, and groups master quotations.

**Key fields**

| Field | Meaning |
|-------|---------|
| `tender_code` | Human-readable code. |
| `title` | Tender title. |
| `project_id` | Parent project. |
| `owner_user_id` | Owner. |
| `forecast_amount` + `forecast_currency` | Pipeline value. |
| `pipeline_stage` | Free-text pipeline stage label. |
| `tender_lifecycle` | **open** / **closed**. |
| `tender_outcome` | **pending** / **won** / **lost** / **withdrawn** / **no_award**. |
| `winning_master_quotation_id` | Set when won. |
| `outcome_notes` | Free text on close. |

**Date columns:** `expected_close_on`, `closed_at`, `created_at`, `updated_at`. (Tender **milestones** add `due_on` and `achieved_at`.)

**Status values (fixed enums):**
* `tender_lifecycle`: `open`, `closed`.
* `tender_outcome`: `pending`, `won`, `lost`, `withdrawn`, `no_award`. (`lost`, `withdrawn`, `no_award` are the "closed without an order" outcomes.)

**Available filters** (Tenders list / API): parent project (`project_id`). The **Tender vs Quotation Compare** view lists all master quotations on one tender with stage, owner, salesperson, amount and updated time.

**Example questions**

* "List open tenders." / "List tenders won this quarter."
* "Show tenders closing this month (by expected close date)."
* "How many tenders did we lose vs win this year?"
* "List tenders under project {X} with their forecast value."
* "Which tenders are withdrawn or no-award?"
* "Show the highest-value open tenders by forecast amount."
* "Which quotations are on tender {tender_code}, and which is the winner?"

---

## Master Quotation (Quotation)

The priced offer under a tender; has stages, an amount, validity, and one or more revisions.

**Key fields**

| Field | Meaning |
|-------|---------|
| `quotation_code` | Code (unique within its tender). |
| `title` | Quotation title. |
| `tender_id`, `customer_id`, `owner_user_id` | Parent tender, client, owner. |
| `quotation_stage_id` → stage | Quotation workflow stage (shown as **Status**). |
| `quoted_amount` + `quoted_currency` | Quoted value. |
| `valid_until` | Quote validity date (Overview shows **Valid** / **Expired**). |
| `payment_terms`, `commercial_details` (JSON) | Terms / details. |
| `pricing_approval_status` | Pricing-approval state (default `not_required`). |
| `pricing_approver_user_id`, `pricing_approval_action_by_user_id` | Approver / actor. |
| `path_role` | Role on the tender: `open`, `winner`, `closed_superseded`, `closed_unawarded`. |
| `current_working_revision_id`, `final_selected_revision_id` | Working vs final revision. |

**Date columns:** `valid_until`, `stage_updated_at`, `pricing_approval_action_at`, `created_at`, `updated_at`.

**Status values:** configurable quotation stages (workflow domain `quotation`). Fixed enum `path_role`: `open`, `winner`, `closed_superseded`, `closed_unawarded`.

**Available filters** (Quotations list / API): free-text **search**, owner, quotation **stage code**, and **scope** (`mine` / `all`). Per-tender and per-project listings also exist.

**Example questions**

* "List quotations for client {X} created between Jan and Mar."
* "Show quotations in the {stage} stage owned by {user}."
* "Which quotations are the winner on their tender (path_role = winner)?"
* "List quotations expiring (valid_until) before {date}."
* "What's the total quoted value of open quotations on tender {tender_code}?"
* "Show quotations awaiting pricing approval."
* "List my quotations updated this week."

---

## Quotation Revision

A versioned snapshot of a quotation's pricing/lines.

**Key fields:** `master_quotation_id` (parent), `revision_number`, `pricing_snapshot` (JSON), `revision_notes`.
**Date columns:** `superseded_at`, `final_selected_at`, `created_at`.

**Example questions**

* "How many revisions does quotation {code} have?"
* "Which revision is the final selected one for quotation {code}?"
* "List revisions created after {date}."

---

## Sales Order

Created when a tender is won, from the selected quotation revision.

**Key fields:** `sales_order_number` (unique), `tender_id`, `master_quotation_id`, `quotation_revision_id`.
**Status values (fixed enum):** `draft`, `confirmed`, `void`, `cancelled`. (A tender may have at most one active - `draft` or `confirmed` - sales order.)
**Date columns:** `created_at`, `updated_at`.

**Example questions**

* "List sales orders created this quarter."
* "How many confirmed sales orders do we have?"
* "Which sales order came from tender {tender_code}?"
* "Show void or cancelled sales orders."

---

## Cross-entity questions

Because the entities chain customer → lead → project → tender → quotation → sales order, you can roll questions up the chain:

* "Won vs lost tenders this quarter" - filter Tenders on `tender_outcome` and `closed_at` / quarter.
* "Pipeline value of open tenders by owner" - group open Tenders by `owner_user_id`, sum `forecast_amount`.
* "Quotations per tender for project {X}" - Project → its Tenders → each tender's master quotations.
* "Leads with no project yet" - Leads filtered by `without_project`.
* "Conversion: leads created this quarter that reached a quotation" - Leads by `created_from`/`created_to` joined to quotations via project/tender.

## See also

* [Create and manage leads (and lead stages)](leads-and-stages.md)
* [Create and progress projects](manage-projects.md)
* [Create, compare and close tenders](manage-tenders.md)
* [Create a quotation](create-quotation.md)
* [Process configuration](process-configuration.md)
