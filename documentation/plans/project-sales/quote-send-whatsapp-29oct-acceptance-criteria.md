# UAC: Send a quotation through the salesperson's own WhatsApp (QUOTE-SEND-WHATSAPP)

**Status:** DRAFT on the card's recommendations; final once the owner answers card Q1-Q5 and approves mock v1.
Plan: `PLAN-quote-send-whatsapp-29oct.md`. Card: `CARD-quote-send-whatsapp-29oct.md`. Mock:
`documentation/mockups/quote-send-whatsapp/index.html`.

## A. The action

- **AC-A1** A user with edit rights on a quotation sees "Send via WhatsApp" in the quotation actions, directly after
  "Copy counter-sign link", on the record gear and on the list row "...".
- **AC-A2** A user without edit rights does not see it (same as "Copy counter-sign link").
- **AC-A3** Before the first "Send to Customer", the item is disabled and reads "Send it to the customer first".
- **AC-A4** Pressing it opens the WhatsApp prompt for the LATEST revision of that quotation.

## B. The prompt

- **AC-B1** Title "Send R<n> via WhatsApp", where n is the latest revision number.
- **AC-B2** On open, the counter-sign link for that revision is minted or reused (the existing sign-link call); the
  link in the message is `<this screen's origin>/quotation-sign/<token>`.
- **AC-B3** While the link is being fetched, "Open WhatsApp" and "Copy link" are disabled; if it fails, the prompt
  says so and both stay disabled.
- **AC-B4** "To" is prefilled per section C and can be edited; an edited number is used for this send only and is not
  saved to the quotation.
- **AC-B5** The message box shows exactly the text WhatsApp will open with (section D).
- **AC-B6** "Open WhatsApp" is a link to `https://wa.me/<digits>?text=<url-encoded message>` opening in a new tab;
  with an empty "To" it is `https://wa.me/?text=<url-encoded message>`.
- **AC-B7** "Copy link" copies the counter-sign link (same behaviour as the gear's copy action).
- **AC-B8** Usable at 375 px and 1280 px: nothing clipped, buttons reachable without horizontal scroll.

## C. The number

- **AC-C1** Uses the quotation's recipient number field; when it holds several numbers (lines, `/`, `,`, `;`), the
  first one that is a mobile is used.
- **AC-C2** MY local mobile `01x...` becomes `601x...` (leading 0 replaced by 60); `+60 1x...` / `60 1x...` stays
  `601x...`; spaces, dashes, brackets and `+` are dropped.
- **AC-C3** A number written with another country code (`+65...`, `0065...`) is kept as given (digits only, `00`
  prefix dropped).
- **AC-C4** A MY landline (`03-...`, `+603...`, `04-...`, etc.), a field with no mobile, or an empty field leaves "To"
  empty.

## D. The message (EN, Q1 (a), Q2 (a) pending owner)

- **AC-D1** Text:
  ```
  Hi <Attn>,

  Here is our quotation <number label> for <subject>.
  You can view and accept it here:
  <link>

  Thank you,
  <name of the user pressing the button>
  ```
- **AC-D2** No Attn -> first line "Hi,". No subject -> " for <subject>" is left out.
- **AC-D3** Number label: today's printed `our_ref_text` (e.g. "PRJQ-2026-0003 (R1)") until QUOTE-SIGN-PAGE merges,
  then its label "PRJQ-2026-0003-R1".

## E. After "Send to Customer R<n>" (Q5 (a) pending owner)

- **AC-E1** When "Send to Customer R<n>" succeeds, the prompt opens on its own for revision n.
- **AC-E2** When it fails, no prompt opens.
- **AC-E3** Close dismisses it; nothing else changes.

## F. Log (Q4 (a) pending owner)

- **AC-F1** Pressing "Open WhatsApp" writes one project activity line "Quotation <number label> link opened in
  WhatsApp by <user>".
- **AC-F2** That line does not clear the project's Unattended badge (not on `MEANINGFUL_TEMPLATES`).
- **AC-F3** A failed log call does not stop WhatsApp opening and shows no error.
- **AC-F4** The log route needs the same edit right as the sign-link route.

## G. Out of scope

Any system-sent message (respond.io), templates, saving a typed number, other languages.
