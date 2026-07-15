# Commercial — Process configuration

**Process Configuration** is the admin hub for the commercial module: the workflow **stages** every record moves through, the **task templates** applied to projects and quotations, quotation **settings**, and the **reference data** (dropdown lists) used when creating leads. Changes here shape what users see across Leads, Projects, Tenders and Quotations.

## Where

Open [**Commercial → Process Configuration**](/commercial-core/process-configuration) (URL: `/commercial-core/process-configuration`). Page heading: **Configuration**. It has four tabs:

| Tab | What it configures |
|-----|--------------------|
| **Stages** | The workflow stages for each domain (lead / project / tender / quotation): name, code, order, terminal flag, "allows conversion", colour. |
| **Task Templates** | Reusable task-board templates applied to projects and quotation workspaces. |
| **Quotations** | Quotation-related settings and package templates. |
| **Reference Data** | The dropdown lists used in the Create Lead wizard. |

## Stages

The **Stages** tab manages the configurable stages that appear as the **Status** column / Kanban columns on each record type. Stages are grouped by **domain** — `lead`, `project`, `tender`, `quotation` (the platform also has `task` and `order` domains). Each stage has a **Code**, **Name** (label), **Order**, a **Terminal** flag (ends the pipeline, e.g. Won / Lost), an **Allows conversion** flag, and an optional colour.

> Lead stages specifically also have a dedicated editor at [**Commercial → Lead Stages**](/commercial/lead-stages) — see [Create and manage leads (and lead stages)](leads-and-stages.md). The same stage data backs both screens.

Related configuration reachable from this area includes **lead stages**, **workflow stages**, **tender checkpoint templates**, **activity templates**, **reminder defaults** and quotation **settings**.

## Task Templates

Define task-board templates (sets of tasks with order and categories) that can be applied to a project at creation time (**Task template** field in the New project dialog) or to a quotation workspace, so delivery checklists start populated instead of empty.

## Quotations

Quotation-side settings and package/line templates used when building quotation revisions.

## Reference Data

The **Reference Data** tab maintains the option lists shown in the **Create New Lead** wizard. Sub-tabs:

| Sub-tab | Drives the lead field |
|---------|------------------------|
| **Countries** | Country |
| **States** | State |
| **Budget Range** | Budget Range (RM) |
| **Closure Confidence** | Sales Closure Confidence |
| **Property Types** | Property Type |
| **Lead Sources** | Lead source / Referral options |
| **Contact Methods** | Contact method |

Each entry can be marked **Active** / **Inactive** so retired options stop appearing in the wizard without deleting historical data.

## What's captured

This area writes configuration rows (workflow stages, task/activity templates, reminder defaults, quotation settings, and lead reference-data entries) that the rest of the commercial module reads. It does not hold business records (leads, tenders, quotations) itself.

## How you'll be notified

* Edits save with an in-app toast.
* Changes take effect immediately for new and existing records (e.g. renaming a stage updates the Status column everywhere).

## See also

* [Create and manage leads (and lead stages)](leads-and-stages.md)
* [Create and progress projects](manage-projects.md)
* [Create a quotation](create-quotation.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
