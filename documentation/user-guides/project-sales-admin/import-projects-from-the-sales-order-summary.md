# Import projects from the sales order summary

Use this to bring the year's projects and purchase orders from the sales order summary workbook into the CRM in one go, without typing them. You tell the CRM which column is which, and which existing customer, project, developer or person each name in the file means. Nothing is saved until you press **Import**.

## Who can use it

You need the **Run Project Imports** permission. Admins have it by default. Without it you cannot open **Project import**. Someone with only view access can read past imports and their History, but cannot create, change or revert one.

## Steps

1. Open **Project Sales**, then **Configuration**, then **Project import**. The list shows every earlier import with its run number, file, status and who uploaded it.
2. Select **Create**. In **New project import**, drop the workbook (an .xlsx file, up to 10 MB) on **Drop the workbook here**.
3. Tick the sheets to read. Each sheet shows its row count. A sheet with no PS numbers is marked **No PS numbers** and starts unticked.
4. Select **Next**. The import opens on the **Columns** step.
5. **Columns.** Match every heading in the file to a field (for example **Customer**, **Project name**, **Developer**, **Salesperson**, **Customer service**, **PO number**). PS number, Customer and PO number must each have a column. The page says **Still needed** until they do. Choose Ignore for a heading you do not want. Select **Next**. Your choices are remembered, so the next file with the same headings needs no matching.
6. **Values.** Use the tabs **Customers**, **Projects**, **Developers** and **People**. Each tab shows a **Value in file**, how many **Rows** use it, what it is **Linked to**, and **Set by** (who chose it and when). The tab shows how many are still **To do**.
   * Open a line's menu and pick **Link to…** an existing record, **Create new**, **Skip** or **None**. Not every choice is offered on every tab: customers can be linked or skipped, projects can be linked, created or skipped, developers can be linked, created or set to **None**, and people can be linked or set to **None**.
   * To set several at once, tick the lines and use **Set to**.
   * A line marked **From SO** is a customer the CRM already found from the sales order numbers on its rows. It needs nothing from you.
   * Your choices are remembered for the next file and show who set them. A choice saved by another company is never used for yours.
7. Select **Preview**. Nothing is saved. You see tiles for what **Will create**, what is **Already imported**, what is **Skipped**, what **Needs review** and any **Errors**, and a list of rows (sheet, row, PS no., customer, project, PO no., PO date, outcome and the reason). Use the **Outcome**, **Reason** and **Sheet** filters to narrow it.
8. Fix anything in **Needs review**. Select such a row to go to the line that blocks it, set it, then select **Preview again**. Rows still needing review are left out of the import.
9. Select **Import**. It runs in the background and the run's status updates when it is done.

## What gets created

For each new project in the file:

* The **project**, owned by the person you linked for the salesperson (or by you, if none was linked), with its customer and developer.
* The **purchase order**, in draft, with its PO number, date, amount, PS number and salesperson. Notes from the file (customer service, amended date, schedule, delivery, outstanding, waived transport charge, remarks) are added as lines in the PO's notes.
* The **sales orders** named on the row, linked to the project and the PO, when they are already in the CRM. If a sales order is not there yet, the PO is still imported, and a later file links it once it arrives.
* Lines set to **Create new** with the same new project name become ONE project. A line set to create a developer makes that developer once.

## Rules to know

* **Nothing is linked by a similar name.** A different spelling is a different line. A person always decides what a name in the file means.
* If you ask to create a developer whose name already exists, the rows go to **Needs review** and are not linked for you. Link the line to the existing developer instead.
* A new project that clashes with an existing registered project (same developer and title) goes to **Needs review** and names that project.
* **Skipped and listed, never imported:** rows with no project name, cancelled rows, blank pre-numbered rows (a PS number with no customer), and rows for other years (only PS26 numbers are read).
* **Existing projects and POs are never changed.** A later file only adds new PS numbers. A PS number already imported shows **Already imported**, even if the file now says something different, and nothing is overwritten. A blank cell never clears anything. The one exception: a sales order that has since reached the CRM is linked to a project that was imported earlier.
* A PS number that appears twice in the file is shown as an error on both rows.
* Importing the same file twice creates nothing the second time.
* An import sends no emails, WhatsApp messages or tasks.

## Results and revert

When the import finishes, the run page opens on **Results** with a breakdown by reason and the rows. It has three tabs:

* **Results** - what was created, skipped, left for review.
* **Values** - the choices used.
* **History** - every action on this run with who did it and when: uploaded, columns saved, value linked, previewed, imported, reverted.

To undo a run, open its gear menu and select **Revert**. A countdown starts with a **Cancel**, and there is no confirmation dialog. Revert removes what the run created. Anything edited since the import, or that now has something else attached (for example a quotation or another PO), is kept and listed under **Kept, changed since the import**. Reverting twice changes nothing. A run that was only previewed has nothing to revert.

## How you'll be notified

A toast appears when a step finishes or **Import reverted**. The run's status pill shows where it is. No email or WhatsApp is sent.

## See also

* [Register a project](../project-sales-rep/register-a-project.md)
* [Set the standard terms and conditions for quotations](set-standard-quotation-terms.md)
