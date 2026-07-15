# 8.4-Purchasing — Stock inquiry lifecycle & what to do at each stage

The map of how a stock inquiry moves from raised to decided, and **what you should do next at every status**. Open this when you're looking at a stock inquiry and aren't sure what the next step is. Detailed step guides are linked inline.

## Where

Open [**Procurement Management → Stock Inquiries**](/procurement-management/stock-inquiries) → click an inquiry. The status pill shows the current stage; the action bar shows the buttons for that stage.

## The lifecycle (process flow)

```
New ──Submit for project sales──▶ Pending project sales
                                    ├─Approve (send to purchasing)─▶ Pending purchasing ──reply──▶ Responded
                                    └─Reject (reason)──────────────▶ Rejected               (answered)
                                                                       ▲
                                       Reject (reason) ────────────────┘
                              Rejected ──Reopen──▶ back to the stage it was rejected from
```

Plain English:

1. An inquiry is raised as **New**.
2. Sales submits it for review → **Pending project sales**.
3. Project sales either approves it (passes it to purchasing → **Pending purchasing**) or rejects it (**Rejected**).
4. Purchasing answers it → **Responded**, or rejects it (**Rejected**).
5. **Responded** means purchasing has answered — the inquiry is handled; nothing more is required.
6. A **Rejected** inquiry can be **reopened** back to the stage it was rejected from.

## Status labels

| Status | What it means |
|--------|----------------|
| **New** | Just raised, not yet submitted. |
| **Pending project sales** | Waiting for project sales to review. |
| **Pending purchasing** | Approved by project sales; waiting on purchasing to answer. |
| **Responded** | Purchasing has answered — the inquiry is handled. Nothing more is required; you can send a further reply if needed. |
| **Rejected** | Turned down (by project sales or purchasing); can be reopened. |

## What should I do now — by status

**New**
Submit it for review with **Submit for project sales**. The status moves to **Pending project sales**.

**Pending project sales**
Project sales reviews. Either:
- **[Approve (send to purchasing)](#guide_target=procurement.stock-inquiries.approve-button)** — passes it to purchasing; status → **Pending purchasing**.
- **[Reject](#guide_target=procurement.stock-inquiries.reject-button)** — a reason is required; status → **Rejected**. Full steps: [Stock inquiry flow](../project-sales-manager/flow-stock-inquiry.md).

**Pending purchasing**
Purchasing handles it. Write the answer with **[Edit purchasing response](#guide_target=procurement.stock-inquiries.edit-purchasing-response-button)** and send it — the status moves to **Responded**. Or **[Reject](#guide_target=procurement.stock-inquiries.reject-button)** with a reason if it can't proceed. Full steps: [Review a stock inquiry](review-stock-inquiry.md).

**Responded**
Purchasing has answered the inquiry — **nothing more is required**. The answer and who sent it are recorded on the record. If something needs to change, you can send a further reply with **[Edit purchasing response](#guide_target=procurement.stock-inquiries.edit-purchasing-response-button)**; otherwise the inquiry is handled.

**Rejected**
Review the rejection reason shown on the record. If it should continue, **[Reopen](#guide_target=procurement.stock-inquiries.reopen-button)** — it goes back to the stage it was rejected from (project sales or purchasing). Reopening clears the rejection details (the change stays in the audit history).

## Notes

* Buttons are gated by status — if one is missing, check the status pill and your permissions.
* Rejections always require a reason; it's shown to the next handler.
