# UAC: Duplicate for another party (QUOTE-DUPLICATE-PARTY)

- D1 A user who can edit the document sees "Duplicate for another party" in the gear and in the list row's "...". A
  reader does not.
- D2 The action opens one small popup: Party (the header's picker, the project's parties first) and Attn ("Choose
  contacts"). Duplicate is disabled until a party is picked. Cancel closes it with nothing created.
- D3 Duplicate creates a new document with the next number, the picked party as To and its Attn, today's date, no
  Your Ref, and lands on it. Prepared By is the person who duplicated it.
- D4 The copy holds every area, line, quantity and price of the source as it stands, plus its letter, closing,
  terms, payment term, validity, spec sheet settings and certificate choices.
- D5 The source is unchanged.
- D6 Source approved (or sent while approved and unchanged since): the copy opens approved with no request, and its
  History reads "Approval carried from <source ref>".
- D7 Source needed approval but it is pending, rejected, or its lines changed since the approved send: the copy is a
  draft and asks for approval through the normal flow.
- D8 The copy's header shows "Copied from <source ref>" linking to the source; the source's History reads
  "Duplicated for <party> as <new no>".
- D9 The project's Proposals list shows the copy as its own row with its own Recipient.
- D10 A source with unsaved autosave edits refuses: "Save or discard the open edits first."
- D11 Duplicating the project's quotation makes a proposal (one quotation per project).
