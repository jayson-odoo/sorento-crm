# Commercial — Create, compare and close tenders

A **tender** belongs to a project and is the competitive opportunity you quote against. One tender can carry several **master quotations**; you compare them, and when the customer decides you either progress the winning quotation into a **sales order** or close the tender with a lost/withdrawn/no-award outcome. This guide covers the tender list, creating a tender, comparing quotations, and the win/close progression.

## Where to find tenders

Open [**Commercial → Tenders**](/commercial-management/tenders) (URL: `/commercial-management/tenders`). The list header reads **All tenders** (or **Project filter active** when opened scoped to a project). Columns:

| Column | Meaning |
|--------|---------|
| **Tender** | Tender code — click the row to open the tender detail page. |
| **Title** | Tender title. |
| **Stage** | Pipeline stage (free-text label on the tender). |
| **Lifecycle** | **open** or **closed** (badge). |
| **Pipeline value** | Forecast amount + currency. |

Click a row to open the tender by its code (URL: `/commercial-management/tenders/{tenderCode}`).

## Create a tender

Click **New tender** (URL: `/commercial-management/tenders/new`). The form card is **New tender**:

* **Project ID** — required. Placeholder: *"Paste project ID from project detail"*. (Tenders are always raised under a project; open the project to copy its ID, or use the **New tender** button on the project's own page, which pre-fills it.)
* **Tender code** — required.
* **Title** — required.
* **Pipeline stage** — optional.

Click **Create**. On success you see the toast *"Tender created"* and land on the new tender's detail page. A tender starts with **Lifecycle = open** and **Outcome = pending**.

## Compare quotations on a tender

Open [**Commercial → Tender vs Quotation Compare**](/commercial-management/tender-quotation-compare) (URL: `/commercial-management/tender-quotation-compare`). Page title: **Tender quotation comparison**.

1. Enter a **Tender code** (placeholder *"e.g. T-ABC12345"*) and click **Load**.
2. The table lists every master quotation on that tender with columns **Quotation**, **Title**, **Stage**, **Owner**, **Salesperson**, **Amount**, **Updated**, and **Open**.
3. Click **Workspace** in the **Open** column to jump to that quotation's revision workspace.

Use this side-by-side view to decide which quotation wins.

## Progress the winner or close the tender

Open [**Commercial → Sales Order Progression**](/commercial-management/sales-order-progression) (URL: `/commercial-management/sales-order-progression`). There are two cards:

### Winning path → sales order

Turns the chosen quotation revision into a sales order and marks the tender **won**.

1. Enter **Tender code**, **Quotation code** and **Revision number**.
2. Click **Progress to sales order**.
3. On success the result line confirms the tender outcome and the new sales-order number, e.g. *"Tender {code}: won. Sales order {number} ({quotation} rev {n})."*

### Close tender (no sales order)

Closes the tender without an order. (*"Uses the same tender code as on the left."*)

1. Pick an **Outcome**: **Lost**, **Withdrawn** or **No award**.
2. Optionally add **Notes**.
3. Click **Close tender**. The result line confirms, e.g. *"Tender {code} closed (lost)."*

## Tender status reference

| Field | Values | Meaning |
|-------|--------|---------|
| **Lifecycle** (`tender_lifecycle`) | `open`, `closed` | Whether the tender is still live. |
| **Outcome** (`tender_outcome`) | `pending`, `won`, `lost`, `withdrawn`, `no_award` | Result. `won` is set by the winning-path progression; `lost` / `withdrawn` / `no_award` by the close action. |
| **Stage** (`pipeline_stage`) | free text | Where the tender sits in your pipeline. |

When a tender is **won**, the winning master quotation is recorded on the tender and a sales order is created from the selected revision.

## What's captured

A tender row records: tender code, title, the parent project, owner, forecast amount/currency, pipeline stage, expected close date, lifecycle, outcome, the closed-at timestamp, outcome notes, and (when won) the winning master quotation. Sales orders created from a won tender record the source quotation revision, master quotation, tender and an auto-generated sales-order number.

## How you'll be notified

* Create / progress / close actions report inline (result line) or via toast.
* The tender's Lifecycle and Outcome update immediately and flow through to the Compare and pipeline views.

## See also

* [Create and progress projects](manage-projects.md)
* [Create a quotation](create-quotation.md)
* [Manage the commercial pipeline](manage-pipeline.md)
* [Commercial data: fields, filters & questions the assistant can answer](data-analysis.md)
