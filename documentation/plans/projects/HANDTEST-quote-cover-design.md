<!-- Branch copy of laneboard/scripts/2094.md (crew hand test script for PR #2094). The URL is filled in by crew per test copy. -->

# Hand test: PR 2094 QUOTE-COVER-DESIGN (cover page designer, Cover letter tab preview)

## URL
crew test copy

## Setup

- Log in as a project sales user who can edit Quotation Templates and can send a proposal (or have a manager login for an approval step).
- Pick a project under Project Sales > Projects that has a customer.
- Keep one proposal or quotation in mind that was already sent before this change (any project's Proposals tab, sent at least once). It is used in step 15.
- The copy may already have an active cover page design (for example "Standard cover page" from an earlier pass). That is fine: step 5 activates the new one, and only one design is active at a time.

## Steps

1. Open Project Sales > Configuration > Quotation Templates, click the Cover page tab, and click Add design.
2. Type Name: Hand test cover. Change Title to QUOTATION PROPOSAL. Turn Show company letterhead off.
3. In the row list: untick Email; drag Validity one row up, above Payment Terms, with the mouse. Then try the keyboard on Company: focus its handle, press Space, Arrow Up, Space. Then change the printed name of Attn to ATTENTION.
4. In Intro text type "Dear customer, here is our offer for " then click Insert field and choose the project title. In Closing text type "We look forward to your reply."
5. Look at the preview on the right, then Save. In the design list, click Activate on Hand test cover if it shows Inactive.
6. Open the chosen project, click the Proposals tab, click Add a proposal.
7. Click the Cover letter tab.
8. Click the Header tab, type a Purpose and an Attn name, then go back to the Cover letter tab.
9. Change the Intro text for this proposal only (add "Thank you." at the end). On the Lines tab, click the pencil next to Scope 1 and name it UNIT, add one catalogue line, and type the list price shown under its Rate box (a lower price asks for a manager's approval before sending). Save.
10. On the saved proposal, open the Cover letter tab (view mode).
11. Click Sign in the page header (Type tab, Apply signature), then the header button Send to Customer A, then WhatsApp. Click Copy link, then Close without sending. This sends revision A.
12. Download the revision A PDF from the gear menu, open it from the downloads button, and look at page 1 and the page with the total.
13. Open the sign link in a private window, at full width and narrow like a phone.
14. Go back to Quotation Templates > Cover page, edit Hand test cover, change Title to QUOTATION, Save. Then download the revision A PDF again and reopen its sign link.
15. Open the old proposal or quotation from Setup, download its PDF again and open its sign link.
16. Back in Quotation Templates > Cover page, click Deactivate on Hand test cover, then open the Cover letter tab of a new or draft proposal.
17. Optional, to put the copy back: click Activate on the design that was active before step 5.

## Expected

1. The page has two tabs, Terms and Cover page. Cover page lists designs like Terms lists templates, with an Add design button.
3. Each mouse drag of one row moves the row exactly one place, and the floating row stays under the pointer. Space, Arrow Up, Space moves Company exactly one place up (Arrow Down would move it one place down).
5. The preview shows page 1 with a sample: no letterhead, the title QUOTATION PROPOSAL, the intro with a sample project name, the rows without EMAIL, VALIDITY above PAYMENT TERMS, ATTENTION instead of ATTN, then the closing. After Activate, Hand test cover shows Active and the design that was active before shows Inactive.
7. The tab shows page 1 as it will print for this proposal (reference NEW-A and the project name before the first save), with the design's title, rows and intro and closing, the project name filled in (no {{ }} anywhere). Rows with nothing in them yet (for example Attn, Address, Purpose on a brand new proposal) are left out, as on the PDF.
8. Without saving, the preview now shows the Purpose you typed (labelled Proposal Purpose on a proposal) and the Attn name under ATTENTION.
10. The view shows the preview only, with "Thank you." in the intro, and the proposal's own number ending in -A.
12. Page 1 is upright with no letterhead, the title QUOTATION PROPOSAL, the intro with the project name and "Thank you.", the rows as designed (no EMAIL, VALIDITY above PAYMENT TERMS, the Attn name under ATTENTION), and the closing below. The intro does not appear again on the price pages. The price pages are sideways as before.
13. The sign page opens with the same card: the same title, rows, intro and closing, and no separate "from" line above it. At phone width each label sits above its value and nothing is cut off.
14. The revision A PDF and sign link still show QUOTATION PROPOSAL: a sent revision keeps the design it was sent with.
15. The old one looks exactly as before: same layout as when it was sent.
16. The design shows Inactive (its Actions column now offers Activate) and the cover page falls back to the standard cover: letterhead with PROPOSAL FROM above it (not QUOTATION FROM), all rows in the standard order, and the title PROPOSAL (QUOTATION on a quotation made from it). Revisions already sent keep their design.
