# Owner standing rules: checklist

The owner's standing UI and product rulings, as one checklist. Every builder, reviewer and tester
checks every applicable line before a lane is called done; an unchecked applicable line is a FAIL.
A line that does not apply to the diff is skipped, not ticked.

## Lists & grids
- [ ] The list is the standard DataGrid with ONE toolbar row: Search, Filters, Columns and a button labelled just "Create" on the same row.
- [ ] Click every column header: each one sorts (asc, desc, off) and the order holds on page 2, so the sort runs on the server, not the loaded page.
- [ ] Every row is ONE line: no second line, no stacked badge + caption, no wrapped cell; long text is cut with "..." and shows in full on hover.
- [ ] One value per column: unit, line number, document number etc. are their own (sortable) columns, never stacked or joined in one cell.
- [ ] Open Columns: every column can be hidden, shown and reordered (only the last visible one is guarded); reload and the choice is kept for this user.
- [ ] Click a row: it opens the record (or expands the line's details in an editable line grid); there is no "Open"/"View" column.
- [ ] Right-click a row (long-press on touch): the row actions are there; rows have no action icon buttons and no dedicated "Remove" button (select + Delete or right-click instead).
- [ ] Ticking: Shift+click ticks a range, dragging down the tick column ticks or unticks, the header box ticks the page and then offers "Select all N".
- [ ] Bulk actions work rows-first: tick rows, then ONE action button or dropdown acts on them; no "choose action, then pick rows" flow.
- [ ] Open a record from a filtered, sorted list: prev/next is there, follows that filtered order, and is still there after every action on the page (save, dialog, status change, reload).
- [ ] The record header is the standard one: number + status pill on one line, one short subtitle, actions on the right (pager, gear, print, one main button).
- [ ] Long titles are clamped to 1-2 lines in headers, cards, lists and pickers, with the full text on hover / expand.
- [ ] Every action the system tracks on a record (status change, confirm/unconfirm, send, edit) shows in that record's History tab, built on the shared history component: who, on behalf of, when, plain action, old -> new.
- [ ] Every background or scheduled job is listed on Scheduled Tasks with last run, last error and Run now.
- [ ] Exports use the shared Excel style and contain the same rows and columns as the screen or email they mirror.
- [ ] Stored images show as thumbnails through the shared image component; opening one uses the shared image lightbox; the network tab never loads the full-size original on a list or editor.

## Filters & search
- [ ] Every dropdown filter is multi-select: tick two values and the list shows rows matching either; two different filters combine (both apply).
- [ ] Every list and every tab that lists rows has the standard search + filter + sort; the filter set is at least as strong as the equivalent list elsewhere (e.g. the portal list for the same form).
- [ ] Filters, sort and search survive prev/next on a record and the way back to the list; the page and its filters are in the address bar.
- [ ] A report scoped to selected locations (or any scope) fills EVERY derived column from that scope only; with no data in scope the cell is blank, never borrowed from another location.
- [ ] Every picker (customer, product, contact) is searchable by name and code.
- [ ] A count shown in a banner or badge ("N lines need approval") equals the rows its matching filter shows.

## Forms & dialogs
- [ ] Details, previews and secondary editors open in a centred lightbox popup, not as inline expansions or side panels; big previews sit behind a "Preview" button.
- [ ] The default view is minimal: no inline sub-forms, chips + inputs per row or extra visible icons; extra controls live in right-click or menus.
- [ ] Where there are two ways to do a step (upload OR add lines manually), the user picks one first and only that path's table appears; a linked list and its "add" picker live in ONE view, never separate tabs.
- [ ] Edit opens the same form as Create, with the same Preview -> Approve steps; editing your own record never asks for a revision reason.
- [ ] A new request or approval form copies the existing request-form layout: header fields on top, products in the shared line table (never per-product cards, even on a phone), searchable customer, shared attachments.
- [ ] Open the same form in the portal and in the CRM side by side: create, edit and view show the same fields, pickers and attachments.
- [ ] Approval flows: status chip in the header; rejected = amend and resubmit; approved = locked; an explicit "Revise" button unlocks (no silent reset on edit).
- [ ] Number fields: select "1", delete it, type "2" - the field stays empty while typing and never snaps back; limits are checked only on save, next to the field.
- [ ] Nothing hangs: every load, save and job ends in content, empty, no-access or an error with Try again; an expired session goes once to sign-in.
- [ ] Formatted text uses the shared rich-text editor (bold, colour, lists) and prints exactly as it shows on screen.

## Dates, numbers & money
- [ ] Every date reads dd/mm/yyyy (zero-padded) on screens, pickers, PDFs, emails, exports and chat; ranges read "dd/mm/yyyy - dd/mm/yyyy"; date-times read "dd/mm/yyyy, h:mm am/pm".
- [ ] Date fields are the shared date picker: typing "05/11/2026" is accepted; no browser-native date input (which shows the browser's own locale).
- [ ] A value that cannot be worked out (no cost, no receipt, no rate) shows "-", never a made-up number such as 0, -100 % or a value taken from another scope.
- [ ] A quantity the user enters is never capped by the CRM's stock figure; stock shows next to it as information only.

## Wording & CTAs
- [ ] Each page or step has ONE filled main button; the next step's button appears inside the popup it opens (e.g. Preview, then Approve inside the preview).
- [ ] Plain business words only: no internal states or tech terms (stage, staged, commit, internal keys, "would be", read-back); say "Location", not "Bin".
- [ ] No section heading above a table or drop zone that already explains itself, and no "how this feature works" text in the screen.
- [ ] No internal ids, UUIDs or raw codes in place of names; a product never shows a name that is just its code.
- [ ] An email keeps its existing layout (header table, then item lines); the confirm preview, the email body and the attachment show the same rows and columns; no invented headings or remark words.
- [ ] "Prepared By" on any document is the user who created it and cannot be edited.

## Data & logic rules
- [ ] Plain states only: late = past its date, incoming = not yet arrived; no invented windows, cut-offs, buckets, locked columns or extra refusals the owner did not ask for.
- [ ] No automatic joining by similar names: records link only through an explicit link a person set (or a reviewed list).
- [ ] Ledger records with the same trading name count as one customer / supplier: no "which account?" question, totals cover all of them.
- [ ] Quotation and sample lines are catalogue products only; there is no free-text product line anywhere.
- [ ] Every sales figure (report, dashboard, chat) comes from the one shared sales function and the same question gives the same total everywhere; nothing is hidden (unassigned shows as its own bucket); "channel" means the sales order's type.
- [ ] One bad line never fails a whole batch (confirm, import, send): the batch goes through and the skipped line is named in a clear notice.
- [ ] Features that write to the ERP sit behind an admin switch that is OFF by default; with it OFF the screen looks exactly as before; every ERP call is logged.
- [ ] A notification goes out only when the receiver has something to do; a new product-change notification copies the existing product-change notification (same channels, per-user settings, digest).
- [ ] A "customer" is a contact linked to a customer record; unlinked contacts never count as customers.

## AI/chatbot
- [ ] Understanding comes from the semantic parser: no keyword, regex or word-list rules, and no post-parse word "guards"; test with a greeting, a typo and a non-English phrasing.
- [ ] Every name list (customers, suppliers, brands, locations, salespeople) matches by meaning: a misspelt or translated name still finds the record.
- [ ] When the ask is unclear the bot asks one short question with real-name options; it never guesses, never asks for a code, never sends a guessed file type.
- [ ] The bot asks less when the context decides (sales or delivery = customer side), keeps the customer already in focus, and never asks which of several same-name accounts.
- [ ] Replies put one fact per line as "Label: value", product code on its own line, no "·" separators; a customer group shows by name without an account count.
- [ ] Replies and options never show internal ids, UUIDs or hidden codes.
- [ ] The bot states only what the data holds (no invented explanations or unconfigured fallbacks); a miss reads "Couldn't find X"; a failure is fixed at its cause, never covered by a generic apology.
- [ ] A capped list ends with one 'Reply "more" to see the next N.' line and "more" pages on.
- [ ] Every new list screen and record action can be read and done by the assistant (registry entry, action, two eval prompts).
- [ ] A chat fix is checked on varied real phrasings and follow-ups (refine, answer the bot's question, topic switch), not only the brief's example.
