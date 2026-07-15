# Commercial — Create and manage leads (and lead stages)

A **lead** is the start of the commercial pipeline: a customer (client) plus a qualification profile (property, budget, confidence) that you progress through configurable **lead stages** until it converts into a project / tender / quotation. Use this guide to create a lead, work the list, and maintain the stage list.

## Where to find leads

Open [**Commercial → Leads**](/commercial/leads) (URL: `/commercial/leads`).

The list opens as a DataGrid with a **List / board** view toggle. Visible columns are **Lead Ref**, **Client Name**, **Property Type**, **Budget Range**, **Status**, **Created** and **Created By**. (The lead **Title** is searchable but hidden from the table by default; it shows on the detail page.) The **Status** column shows the lead's current stage.

### Search and filter

* **Search leads...** — free-text search across lead code, title and client; press Enter to apply.
* **Status** dropdown — **All statuses**, or pick a specific lead stage.
* **Pipeline** dropdown — **All pipeline** or **Open stages only** (hides leads sitting in a terminal stage such as Won / Lost).

### Row actions

The `⋮` menu on each row offers **Duplicate**, **View lead** and **View client**.

## Create a lead

Click **+ Create Lead** (top right) to open the **Create New Lead** wizard (URL: `/commercial/leads/new`). It has four steps shown in the stepper: **Select Client**, **Property Info**, **Lead Detail**, **Confirmation**.


1. **Select Client** — search and pick an existing client, or click **New client** to create one inline. A client is required to continue.
2. **Property Info** — optional property location and details:
   * **Property Address**: **Address Line 1**, **Address Line 2**, **Postcode**, **Area / City**, **State**, **Country**. Use **Open Maps** to look the address up in Google Maps.
   * **Property Details**: **Property Type**, **Property Status** (**Planning**, **Under construction**, **Completed**, **Operational**, **Other**) and **Property Value** (currency **MYR** / **SGD** / **USD**).
3. **Lead Detail** — the lead itself:
   * **Lead title** (required) and **Lead owner** (required).
   * **Respond workspace (optional)** — link the lead to a Respond.io workspace so its WhatsApp conversation threads through.
   * **Budget Range (RM)**, **Sales Closure Confidence**, **Referral**, **Est. Project Start Date**, **Est. Project End Date**.
4. **Confirmation** — review the **Client**, **Property Information** and **Lead Details** cards (each has an **Edit** shortcut back to its step), then click **Create Lead**.

The owner, title and client are mandatory; the property and qualification fields are stored together as the lead's **qualification** profile and surface in the list (Property Type, Budget Range) and on the detail page.

### What's captured

A lead row records: the auto-generated **Lead Ref** (lead code), title, client, owner, current stage, the qualification profile (address, property type/status/value, budget range, sales-closure confidence, referral, estimated start/end dates) and an optional linked Respond.io workspace. Creator and timestamps (**Created**, updated) are stored automatically.

## Maintain lead stages

Open [**Commercial → Lead Stages**](/commercial/lead-stages) (URL: `/commercial/lead-stages`). The page title is **Lead stages** and the table (card **Stages**) shows one row per stage:

| Column | Meaning |
|--------|---------|
| **Code** | Stable machine code for the stage. |
| **Name** | Display name shown in the Status column / filters. |
| **Order** | Sort position in the pipeline. |
| **Terminal** | Toggle — a terminal stage ends the pipeline (e.g. Won / Lost). "Open stages only" filters these out. |
| **Allows conversion** | Toggle — whether a lead in this stage may be converted onward (e.g. into a project). |

* The **Terminal** and **Allows conversion** switches save immediately (edit permission required).
* **Delete** removes a stage. The confirmation reads: *"Delete this stage? It must not be assigned to any lead."* — reassign any leads off the stage first.
* **Refresh** re-loads the list.

> Lead stages are **configurable per tenant**, not a fixed list. They live in the shared workflow-stage model (`domain = lead`). New installs seed a starter set; your administrator tailors the names, order and terminal flags. The same stage editor is also reachable from [**Commercial → Process Configuration**](/commercial-core/process-configuration) under the **Stages** tab.

## How you'll be notified

* Creating, duplicating or editing a lead shows an in-app toast (e.g. *"Lead {code} copied successfully"*).
* Lead-stage switch changes and deletes confirm with a toast.
* If a lead is linked to a Respond.io workspace, its WhatsApp conversation appears on the lead detail page's messages tab.

## See also

* [Manage the commercial pipeline (Kanban boards)](manage-pipeline.md)
* [Create and progress projects](manage-projects.md)
* [Create a quotation](create-quotation.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
