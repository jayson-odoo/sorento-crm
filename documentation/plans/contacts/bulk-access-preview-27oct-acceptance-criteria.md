# UAC - BULK-ACCESS-PREVIEW (access-sheet preview shows every change; links follow each contact's row)

Status: APPROVED 27 Oct (owner on mock v2: approved, "make this into a new page [...] so I can scroll down, have
pagination"; card `CARD-bulk-access-preview-27oct.md` approved, edge cases as recommended). P8 settled by crew ruling 27 Oct
(b): Rows disagree cards are confirmed too.
Amends `bulk-contact-access-26oct-acceptance-criteria.md` U10, U11 (link fan-out) and U20 (dialog, truncation).

## Linking
- P1 A confirmed account is linked to a found contact of its block only when the account's company code is one
  of the companies on that contact's own row. An account whose company no row can tag links to nobody.
- P2 Apply stays add-only: a link the contact already holds is never removed.
- P3 Each account in the preview carries `links_to`: the names of the block's found contacts it would link to
  (every contact whose row tags its company, whether already linked or not). The page shows them while the
  account is ticked and "Nobody" when it is not (Apply links only ticked accounts).
- P4 Each found contact carries `outside_links`: labels of accounts it is already linked to whose company is not
  on its row (any dealer). Shown as an info line, never removed.

## Visibility
- P5 Each found contact shows every CHANGED facet as before -> after, one item per line, items added to a list
  facet marked "+" (a switch or the stock mode is replaced, no "+"); stock locations one location per item;
  unchanged facets are named in one "No change" line. Nothing in the contact panel truncates.
- P6 `holds_more` comes with `holds_more_items`: per facet (access types, companies, stock locations, brands), the
  items outside the contact's template, by the labels the changes use (access type and company codes, location
  codes, brand names). The preview and the result CSV list them, with `outside_links`.
- P7 The import is its own page, `/user-management/contacts/access-sheet` (Internal Users > Actions > Import access
  sheet): upload, then the preview with 20 dealer cards a page (Prev / Page X of Y / Next above and below the cards,
  every card open), then the result. Confirm all exact / Back / Apply access sit in a bar pinned to the bottom.
  Confirmations and picks survive paging. Usable at 375 px (facet rows stack: label, before, after) and 1280 px.

## Confirm all exact
- P8 [crew ruling 27 Oct, (b)] "Confirm all exact" confirms every `exact` block, `rows_disagree` included (per-row
  company linking makes rows tagging different companies the normal case); the "Rows disagree on companies" pill
  stays visible on the card.
