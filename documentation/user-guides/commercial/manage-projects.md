# Commercial - Create and manage projects

A **project** is the delivery container that sits between a lead and its tenders/quotations. It belongs to a **developer** (a customer), can be linked to one or more leads, carries an address and timeline, and groups the tenders raised under it. Use this guide to create projects and work the projects list.

## Where to find projects

Open [**Commercial → Projects**](/commercial-management/projects) (URL: `/commercial-management/projects`). The page header is **Projects**. It opens as a DataGrid with a **List / board** view toggle.

Columns:

| Column | Meaning |
|--------|---------|
| **Project** | Project title - links to the project detail page. |
| **Status** | The project's workflow stage (badge). |
| **No. of Leads** | Count of leads linked to the project; the info icon lists **Leads in this project**. |
| **No. of Clients** | Count of distinct clients across those leads; the info icon lists **Clients in this project**. |
| **Owner** | Project owner. |
| **Created** | Creation date. |

### Search and filter

* **Search projects…** - free-text search.
* **Owner** dropdown - **All owners** or a specific user.
* **Status** dropdown - **All statuses** or a specific project stage.

### Row actions

The `⋮` menu offers **Duplicate** and **Open**.

## Create a project

Click **+ New project** to open the **New project** dialog. Fields:

* **Project title** - required.
* **Developer** - required; pick the developer customer (searchable, shown as `code - name`).
* **Brief**, **Notes** - free text.
* **Address line 1**, **Address line 2**, **Postcode**, **City**, **State**, **Country**.
* **Start date**, **End date**.
* **Task template** - optional; applies a task-board template (configured under Process Configuration → Task Templates) to the new project.

Click **Create project**. **Project title** and **Developer** are mandatory - leaving either blank shows a validation toast (e.g. *"Project title is required."*).

> Projects can also be created mid-flow from the **Create New Quotation** dialog (via **+ Create project**) when no suitable project exists yet - see [Create a quotation](create-quotation.md).

## What's captured

A project row records: title, the **developer** customer, owner (plus an optional list of additional project owners/members), the optional originating lead and any additionally linked leads, the address fields, start/end dates, brief, notes, the chosen task template, the project workflow **stage**, and a free-text **status** (defaults to `active`). Tenders are created **under** a project.

## How you'll be notified

* Create / duplicate show an in-app toast (e.g. *"Project {title} copied successfully"*).
* From the project detail page you raise tenders and quotations and view linked leads and clients.

## See also

* [Create and manage leads](leads-and-stages.md)
* [Create, compare and close tenders](manage-tenders.md)
* [Create a quotation](create-quotation.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
