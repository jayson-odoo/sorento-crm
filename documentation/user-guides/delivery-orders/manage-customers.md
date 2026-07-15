# Customers — Create, edit & review

Use this flow to maintain the customer master used by delivery orders: add a customer, edit contact details, activate / deactivate, or open a customer to see how many delivery orders they have.

## Where to go

Open **[Delivery Order Management → Customers](/order-management/customers)** (URL: `/order-management/customers`). The page is titled **Customers**.

## The list

Each row is one customer. Default sort is newest first, 50 per page.

| Column | Meaning |
|----|----|
| **Customer Code** | The customer's code. A code can be shared across more than one customer name — uniqueness is enforced on the **code + name** pair, not the code alone. |
| **Customer Name** | The customer / debtor name. |
| **Email** | Contact email. |
| **Phone** | Contact phone number. |
| **Status** | **Active** / **Inactive** badge. |

### Search & filter

* **Search customers…** — free-text box. Matches **Customer Code** and **Customer Name**.
* **Filters → Status** — **All statuses** / **Active** / **Inactive**.

> Note: the **Status** filter is a UI control. The customer list search currently narrows on Customer Code and Customer Name only — if a Status filter appears not to change the result set, search by name / code or use the **Active** badge column to scan.

Click a row to open the customer's detail page.

## Detail page

The header shows the **Customer Name**. Two cards:

* **Contact Information** — Email, Phone.
* **Additional Information** — Status (**Active** / **Inactive**), **Total Delivery Orders** (count of orders linked to this customer), Created, and Last Updated.

From here you can **Edit** or **Delete** the customer.

## Create / edit a customer

* **Create Customer** (toolbar) → opens the form.
* **Edit** (detail page) → same form, pre-filled.

Fields:

| Field | Required | Notes |
|----|----|----|
| **Customer Code** | Yes | Unique customer identifier (alphanumeric, dashes, underscores only). Not editable after creation. |
| **Customer Name** | Yes | |
| **Email** | No | |
| **Phone Number** | No | |
| **Active Status** | — | Toggle to enable / disable this customer. |

Save with **Create Customer** / **Update Customer**.

## Delete

**Delete** is a hard delete with a confirmation dialog (cannot be undone). Orders that referenced the customer keep their debtor name / code — the order's customer link is simply cleared.

## How you'll be notified

* In-app toast confirming create / update / delete.

## See also

* [Track Delivery Orders](track-delivery-orders.md)
* [Delivery Order Statuses](order-statuses.md)
* [Ask the assistant about customers](data-analysis.md)
