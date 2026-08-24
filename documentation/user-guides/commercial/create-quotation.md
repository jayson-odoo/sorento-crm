# Commercial - Create and work a quotation

A **master quotation** belongs to a tender (under a project) and carries pricing, terms and one or more **revisions**. You create the quotation, build its order lines in the revision workspace, move it through quotation stages, and print / email / progress it. This guide covers the Quotations list, creating a quotation, the revision workspace, and email templates.

## Where to find quotations

Open [**Commercial → Quotations**](/commercial-management/quotations) (URL: `/commercial-management/quotations`). Page header: **Quotations**. Opens as a DataGrid with a **List / board** view toggle. Columns:

| Column | Meaning |
|--------|---------|
| **Quotation** | Quotation display code (with title underneath) - opens the revision workspace. |
| **Status** | The quotation's workflow stage (badge). |
| **Project** | Parent project (links to the project). |
| **Lead** | Originating lead, if any. |
| **Client** | Customer name. |
| **Amount** | Quoted amount + currency. |
| **Owner** | Quotation owner. |
| **Created** | Creation date/time. |

### Search and filter

* **Search…** - free-text search.
* **Owner** dropdown - **All owners** or a user.
* **Status** dropdown - **All statuses** or a specific quotation stage.

### Row actions

The `⋮` menu offers **Duplicate** and **Open** (the revision workspace).

## Create a quotation

Click **New quotation** to open the **Create New Quotation** dialog.

* **Project title** (required) - pick the project the quotation belongs to. Use the search box (*"Search project..."*); if the project doesn't exist yet, click **+ Create project** to make one inline (see [Create a project](manage-projects.md)).
* When launched from a project (preset mode) the project is fixed and you instead pick a **Lead** (required) from the project's eligible leads.

Click **Create**. On success you see *"Quotation created"* and land in the **revision editor** to build the first revision's order lines (URL: `/commercial-management/quotation-revisions/edit?...`).

## The quotation revision workspace

Open [**Commercial → Quotation Revisions**](/commercial-management/quotation-revisions) (URL: `/commercial-management/quotation-revisions`) - or click any quotation row / **Workspace** link. This is the working surface for a single quotation, addressed by `?tender=…&quotation=…`. It has five tabs:

| Tab | Contents |
|-----|----------|
| **Overview** | Header facts: **Client**, **Project**, **Seller reference**, **Customer reference**, **Attention to**, **Client telephone**, **Client email**, **Quotation template**, **Order Date**, **Payment Term**, **Valid Until** (with **Valid** / **Expired** indicator), **Assigned Salesperson**, **Delivery Address**, plus internal notes and terms. |
| **Tasks** | The quotation's task board. |
| **Revisions** | **Revision History** - every revision; pick one to view its priced order lines. |
| **Documents** | **Upload Documents** - files linked to the selected revision. |
| **History** | **Audit Trail** - change log with **User**, **Action**, **Field**, **Date**. |

### Primary action and the Actions menu

The big primary button advances the quotation to its **next stage** (its label is the next stage's name). The adjacent menu (`⌄`) offers, depending on your permissions:

* **Duplicate quotation** - copy the quotation.
* **Back to {previous stage}** - move the stage back.
* **Edit quotation** - open the revision editor.
* **Revise** - create a new revision (the current one is superseded).
* **Preview PDF** / **Print PDF** - generate the quotation document.
* **Send email** - email the quotation to the client (opens the send dialog; uses a quotation email template).

## Quotation email templates

Open [**Commercial → Quotation Email Templates**](/commercial-management/quotation-email-templates) (URL: `/commercial-management/quotation-email-templates`). Page title: **Quotation email templates**. The table columns are **Name**, **Code**, **Status** (**Active** / **Inactive**) and **Actions**; the default template carries a **Default** badge.

* Click **New template** (or **Edit** on a row) to open the editor. Fields: **Code**, **Name**, **Subject template**, **Default template** (checkbox) and **Body (HTML)** (rich-text editor).
* Templates support placeholders such as `{{quotation_code}}` and `{{client_name}}` (the default subject is *"Quotation {{quotation_code}} - {{client_name}}"*).
* **Deactivate** soft-disables a template (confirmation: *"Deactivate template '{name}'?"*); it then shows **Inactive**.

These templates populate the **Send email** dialog in the revision workspace.

## What's captured

A master quotation records: quotation code, title, the parent tender, customer, owner, quotation **stage**, quoted amount/currency, valid-until date, payment terms, commercial details, pricing-approval status, the current working revision and the final selected revision, plus a task board. Each **revision** stores a pricing snapshot, revision notes and superseded/final-selected timestamps. A `path_role` (`open`, `winner`, `closed_superseded`, `closed_unawarded`) tracks the quotation's role on its tender.

## Progress to a sales order

When a quotation wins its tender, progress it to a sales order from [**Commercial → Sales Order Progression**](/commercial-management/sales-order-progression) - see [Create, compare and close tenders](manage-tenders.md).

## How you'll be notified

* Create / duplicate / revise / save show in-app toasts.
* **Send email** delivers the quotation document to the client via the configured email template.
* All field changes are recorded on the **History** (Audit Trail) tab.

## See also

* [Create and progress projects](manage-projects.md)
* [Create, compare and close tenders](manage-tenders.md)
* [Process configuration (stages, templates, reference data)](process-configuration.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
