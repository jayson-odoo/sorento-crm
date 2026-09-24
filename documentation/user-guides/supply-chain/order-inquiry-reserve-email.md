# Supply Chain - Reserve request and reserved-stock emails

Explains the two emails a "Request CS to reserve" exchange sends, how to manage who receives
them, the default pool location the Reserve dialog opens on, and the permission needed to
reserve stock. The actions that trigger these emails are described in [Ask CS to reserve
stock](order-inquiry-documents.md#ask-cs-to-reserve-stock) and [Reserve for
purchasing](order-inquiry-documents.md#reserve-for-purchasing-cs).

## What purchasing sends, and what CS sends back

One email each way, never one per row inside a request.

**Reserve request mail** - sent the moment purchasing presses **Send request**. Subject `Reserve
request: <OI number> #<n> - <S/O number>`, for example `Reserve request: OI-2609-0678 #1 -
SO402757`. Body: who is asking, a table with **ITEM CODE**, **DELIVERY DATE**, **QTY**,
**REMAINING**, **REQUESTED**, **LOCATION**, the note if one was left, who requested it and when,
and an **Open in Order Inquiries** link straight to the order inquiry.

**Reserved mail** - sent once CS presses **Confirm reserved** on the last open row of that
request. Subject `Reserved: <OI number> #<n> - <S/O number>`. Body: who reserved it, a table with
**ITEM CODE**, **QTY**, **REQUESTED**, **RESERVED**, **BALANCE**, **LOCATION**, **REASON** -
**BALANCE** is what's left for purchasing to buy after this reserve - and the same link.

Cancelling a request and unreserving stock later never send an email either way.

## How to manage it

Open **System Management → Automation**. Two rows manage these emails:

* **Order inquiry: request CS to reserve** - who gets the request mail. It ships with no
  recipients under **Specific users**, so nothing sends until an admin adds the CS person (for
  example Eling) there. **Cc the person who raised it** Cc's the requester - the purchasing user
  who sent the request. **Cc the person who raised the inquiry** Cc's whoever originally raised
  the order inquiry. Both are ticked by default.
* **Order inquiry: reserved by CS** - who gets the reserved mail. **Cc the person who requested**
  Cc's the requester; **Cc the person who raised the inquiry** Cc's the order inquiry's own
  raiser. Both are ticked by default.

Both rows ship with **One email, everyone on the thread** on, so each exchange sends a single
mail with the first recipient in **To** and the rest in **Cc**, rather than a separate mail per
person. Untick a row's **Enabled** to stop that mail without changing anything else.

## Default location for the Reserve dialog

**User Management → Settings** carries **Reserve dialog default location** - a clearable pick of
any pool warehouse. Leave it empty and CS's Reserve dialog defaults each row's Location to that
row's own site pool; set a pool there and every row defaults to it instead, still changeable per
row.

## Who can reserve

Reserving stock needs the **Reserve Stock for Order Inquiries** permission
(`projects.order_inquiries.reserve`) - separate from **Acknowledge Order Inquiry Rows**, which is
what lets purchasing send a request in the first place. Grant it to the CS role from [Create or
edit a role](../user-management/manage-users-and-roles.md#create-or-edit-a-role-and-choose-its-permissions).
Anyone without it can still open a row's Reserve dialog to read **History**, but the **Reserve**
tab stays read-only and **Unreserve** doesn't show.

## See also

* [Order inquiries: the Documents view and the OI detail page](order-inquiry-documents.md) - Ask
  CS to reserve stock, Reserve for purchasing, History and Unreserve.
* [The order inquiry handover email](order-inquiry-handover-email.md)
* [Manage users and roles](../user-management/manage-users-and-roles.md)
