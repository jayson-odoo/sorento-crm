# Commercial — Work the pipeline (Kanban boards)

The **Pipeline** area gives you Kanban (drag-between-columns) and dashboard views of the commercial hierarchy so you can see where every lead, tender, quotation and task sits by stage. Use it to triage and move work, instead of reading the flat list pages.

## Where to find the pipeline

Open the [**Commercial → Pipeline**](/commercial-management/pipeline) group in the sidebar. The Pipeline area is made up of several boards, each on its own page:

| Board | URL | What it shows |
|-------|-----|---------------|
| **Commercial pipeline dashboard** | `/commercial-management/pipeline/dashboard` | Roll-up dashboard across the pipeline. |
| **Leads board** | `/commercial-management/pipeline/leads` | Leads grouped into columns by **lead stage**. |
| Tenders board | `/commercial-management/pipeline/tenders` | Tenders by pipeline stage. |
| Master quotations board | `/commercial-management/pipeline/master-quotations` | Quotations by quotation stage. |
| Tasks board | `/commercial-management/pipeline/tasks` | Pipeline tasks by status. |

The **Leads** and **Quotations** list pages also have a built-in **List / board** toggle that shows the same Kanban without leaving the list page — see [Leads](leads-and-stages.md) and [Quotations](create-quotation.md).

## Scope filter

Boards carry a scope filter so you can narrow to your own work:

* **All records** — everything you can see.
* **Assigned to me** — only items you own.

## Move an item between stages

Each column is a workflow stage (configured under [**Commercial → Process Configuration**](/commercial-core/process-configuration)). Drag a card from one column to another to change its stage. The same stage progression is also available from each record's detail page.

## What's captured

Moving a card updates the underlying record's stage (lead stage, quotation stage, tender pipeline stage, or task status) and timestamps. Boards are a view over the same data as the list pages — there's no separate "pipeline" record.

## How you'll be notified

* Stage moves apply immediately; the card re-renders in its new column.
* Errors (e.g. a move you don't have permission for) show an in-app toast.

## See also

* [Create and manage leads (and lead stages)](leads-and-stages.md)
* [Create and progress projects](manage-projects.md)
* [Create, compare and close tenders](manage-tenders.md)
* [Create a quotation](create-quotation.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
