# Supply Chain - Reserve request and reserved-stock emails

Explains the two emails a "Request CS to reserve" exchange sends, how to manage who receives
them, the default pool location the Reserve dialog opens on, and the permission needed to
reserve stock. The actions that trigger these emails are described in [Ask CS to reserve
stock](order-inquiry-documents.md#ask-cs-to-reserve-stock) and [Reserve for
purchasing](order-inquiry-documents.md#reserve-for-purchasing-cs).

## What purchasing sends, and what CS sends back

Both emails show every line in the body, so you can read the whole request without opening the
system. There is no limit on the number of lines or order inquiries.

**Reserve request mail** - sent when purchasing presses **Send request**, or when parked requests
are sent with **Send all parked requests to CS**. The table has these columns:

**OI NO**, **SO DATE**, **S/O NO**, **ITEM CODE**, **QTY**, **REQUESTED RESERVE**, **DELIVERY DATE**,
**PROJECT/CUSTOMER**

**Reserved mail** - sent when CS presses **Reserve**, or when parked reserves are sent with **Send
all parked reserves to purchasing**. It shows only the lines CS answered or amended, with **STATUS**
after **REQUESTED RESERVE**, and **REASON** as the last column when a line has one:

| The answer on the line | STATUS | REASON |
| --- | --- | --- |
| Reserved what was asked, or more | `Reserved 80` | Empty, unless documents were released |
| Reserved part of what was asked | `Partial 150 of 212` | CS's reason |
| Reserved nothing (the line reads **Not reserved** on the order inquiry) | `Rejected` | CS's reason |

A partial or rejected line with no reason on file reads `No reason given`. If some lines of a request
are still waiting for CS, the mail adds a line, for example `1 line still to reserve.`

In both emails, lines are sorted by item code, then delivery date. To see what is still left to buy
on a line, take the reserved figure in **STATUS** away from **QTY**.

The column names and their order follow the order inquiry Excel download, except that **OI NO** comes
first and **STATUS** takes the place of **RESERVED**. The download itself has no **OI NO**, **STATUS** or
**REASON** column.

Cancelling a request never sends an email either way.

### Who gets which email

Each person who raised an order inquiry gets their own email, so they see only the order inquiries
they raised. A batch of order inquiries raised by three people becomes three request emails, and three
reserved emails coming back. The other two people are never on the Cc.

Order inquiries raised by the same person go together in one email, and several requests on one order
inquiry also go together in one email. An order inquiry with nobody recorded as its raiser gets its own
email with no raiser on the Cc.

The subject says who raised the order inquiries and how the answers went, for example:

* `Reserve requests: 2 order inquiries raised by CS ONE (PURCHASER A)`
* `Reserved: OI-2609-0678 - SO402757, raised by CS ONE (CS HEAD)`
* `Reserved: OI-2609-0678 - SO402757, raised by CS ONE, 1 rejected (CS HEAD)`
* `Rejected: OI-2609-0678 - SO402757, raised by CS ONE (CS HEAD)`, when every line was rejected

### The button in the email

* An email about one order inquiry opens that order inquiry.
* An email about several opens the order inquiry list showing exactly those order inquiries, whatever
  their state. Remove the **OI NO** filter on the list to see all order inquiries again.

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

Both rows ship with **One email, everyone on the thread** on, so each email goes to the first
recipient in **To** and the rest in **Cc**, rather than a separate mail per person. Untick a row's
**Enabled** to stop that mail without changing anything else.

An admin who edited one of these email templates keeps their own text: the new table only replaces a
template still on its original wording.

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
Without it, the Lines tab shows no reserve icons and no **Reserve** button at all - a line only
shows its plain state pill (**Request to reserve**, **Reserved** or **Not reserved**) and its
**History** icon, whose **Reserve** tab anyone can read.

## See also

* [Order inquiries: the Documents view and the OI detail page](order-inquiry-documents.md) - Ask
  CS to reserve stock, Reserve for purchasing, Amend reserve and History.
* [The order inquiry handover email](order-inquiry-handover-email.md)
* [Manage users and roles](../user-management/manage-users-and-roles.md)
