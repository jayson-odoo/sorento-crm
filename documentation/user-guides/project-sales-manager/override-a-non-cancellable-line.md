# Cancel or reduce a Non-cancellable line (manager override)

Use this when a customer asks to cancel or reduce a Non-cancellable item (for example a bathtub)
after the sales order is confirmed, and you agree to it.

## Who can

Users with **Override a non-cancellable item**: sales managers, directors and admins. Anyone else
who tries is refused with a message saying a sales manager can override it.

## What is blocked

Once a published sales order uses a Non-cancellable line, the CRM refuses to cut it:

* publishing a sales order amendment that lowers or cancels the line;
* **Transfer to Cancel SO** on the line in Fulfilment Planning;
* removing the line from its proposal, lowering its quantity, turning it into a heading or
  swapping its product.

Before the sales order is confirmed, quoting is free. Moving a delivery date is never blocked.

## Steps

1. Do the action as usual (Publish, Confirm, or Save). The CRM refuses and opens
   **Non-cancellable lines**, listing each line and its quantity change.
2. Type the **Reason** (for example "Customer pays the storage charge") and select **Override**.
3. The action goes through. To keep the item instead, select **Cancel**; on an amendment you can
   also decline that row and publish the rest.

## What's captured

* Each override is written to the history of the proposal line or the sales order, with your
  name, the reason, and the quantity before and after.

## How you'll be notified

* AutoCount owns sales order cancels, so a cancel or reduction made directly in AutoCount cannot
  be stopped. When one reaches the CRM (order book update, ESB or a Cancel SO document),
  everyone with the override permission gets a bell notification and an email:
  **Non-cancellable item cancelled in AutoCount** (or **reduced**), naming the SO, the line and
  the quantity change. The change on the Fulfilment Planning board is marked as Non-cancellable.
* A line AutoCount already cancelled can still be transferred to Cancel SO on the board without
  an override.

## See also

* [Mark items Non-cancellable](../project-sales-admin/mark-non-cancellable-items.md)
