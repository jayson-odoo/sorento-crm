# Supply Chain - A sales order's History

Read this when you want to see what happened to a sales order and its plan: who confirmed it,
what AutoCount changed, which order inquiry rows were confirmed or put back, and when.

## Where

* **[Procurement → Supply Chain → Sales Orders](/scm/sales-orders)**, open an order, then the
  **History** tab (the last tab).
* On a project, open the project's sales order, then the **History** tab.
* On **Fulfilment Planning**, open the gear menu and pick **History** followed by the order's
  number. The same list opens in a popup.

Anyone who can open the sales order sees its History.

## What it shows

One entry per thing that happened, newest first. Each entry is one sentence, then the date and
time (dd/mm/yyyy) and who did it. An entry with no person, such as an automatic change, reads
**Automatic**. An entry that touched several lines offers **Show N lines**; each line reads
`<item>: <before> → <after>`.

* **Plan confirmed, revision N**: someone confirmed the plan; the lines say which were ordered,
  ordered back or cancelled. **, no change** means the plan was confirmed again as it was.
* **Confirm refused**: a Confirm was pressed but nothing was written, with the reason.
* **AutoCount update: N lines changed**: a sales order book upload or an AutoCount change moved a
  date, quantity, product or location on lines that were already planned. It names the person
  who applied the change.
* **Handover email sent**: the order inquiry handover email went to purchasing.
* **Confirmed / Unconfirmed ... back to To confirm / Cancelled**: what happened to the order's
  order inquiry rows, the same entries as on the order inquiry's own History tab. One press is
  one entry, even when it covered several lines.
* **Split line N: 10 → 6 + 4**: a line's delivery was split.
* **Status: Draft → Published**: the project sales order's status changed.

When there are more than 10 entries a **Search history** box appears.

## What it does not show

Changes AutoCount makes to the sales order itself, outside planning, are not recorded, so they
do not appear here. The admin History drawer on Fulfilment Planning (with its filters) is still
there for planners.
