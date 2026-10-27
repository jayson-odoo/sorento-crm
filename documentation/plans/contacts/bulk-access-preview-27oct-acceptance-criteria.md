# UAC - BULK-ACCESS-PREVIEW (access-sheet preview shows every change; links follow each contact's row)

Status: draft, pending owner approval of the mockup and card (`CARD-bulk-access-preview-27oct.md`).
Amends `bulk-contact-access-26oct-acceptance-criteria.md` U10, U11 (link fan-out) and U20 (truncation).

## Linking
- P1 A confirmed account is linked to a found contact of its block only when the account's company code is one
  of the companies on that contact's own row. An account whose company no row can tag links to nobody.
- P2 Apply stays add-only: a link the contact already holds is never removed.
- P3 Each account in the preview carries `links_to`: the names of the block's found contacts it would link to
  (every contact whose row tags its company, whether already linked or not).
- P4 Each found contact carries `outside_links`: labels of accounts it is already linked to whose company is not
  on its row (any dealer). Shown as an info line, never removed.

## Visibility
- P5 Each found contact shows every CHANGED facet as before -> after, one item per line, items added marked "+";
  unchanged facets are named in one "No change" line. Nothing in the contact panel truncates.
- P6 `holds_more` comes with `holds_more_items`: per facet (access types, companies, stock locations, brands), the
  items outside the contact's template, by display name. The preview lists them.
- P7 Usable at 375 px (facet rows stack: label, before, after) and 1280 px.

## Confirm all exact
- P8 (pending owner answer) "Confirm all exact" skips blocks with warning `rows_disagree`.
