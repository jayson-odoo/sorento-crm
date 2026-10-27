# CARD: access-sheet account links follow each contact's own row (BULK-ACCESS-PREVIEW)

Status: APPROVED 27 Oct (rule and edge cases as recommended); Confirm all exact: crew ruling 27 Oct (b), it
confirms Rows disagree cards too (the browser pass showed the owner's own example card is one). Mockup: `documentation/mockups/BULK-ACCESS-PREVIEW/index.html`.

## Rule (owner ruling 27 Oct)
An account in a confirmed dealer card is linked to a contact only when that contact's OWN sheet row tags the
account's company (Sorento Sdn Bhd -> SRT, Mocha Sdn Bhd -> MCH). Apply stays add-only: links a contact already
holds are never removed. The preview lists, per contact, linked accounts whose company is not on the contact's
row ("Linked outside this row's companies (kept, not removed)").

## Examples (card Y** L***** H****: MCH 300-Y055/56/57, SRT 300-Y065/66/67)
1. Sh*** row: `..., Sorento Sdn Bhd, <agent>, Business Owner` -> gets 300-Y065/66/67 only.
2. Wo*** row: SRT + MCH -> gets all six.
3. An employee row tagging only Mocha -> gets 300-Y055/56/57 only (and end_user access, as today).
4. Sh*** already linked to 300-Y055 (MCH) from the first import -> stays linked; the preview shows it under
   "Linked outside this row's companies". Apply adds the SRT three, removes nothing.
5. Admin unticks 300-Y066 -> nobody gets it; the rest follow the rule.

## Edge cases, each with a recommendation
- E1 Row with no company tag: already a row error ("No Sorento or Mocha company tag.",
  `contact_access_sheet_service.py:162`), never applied. Recommendation: keep.
- E2 Account of a company that is not SRT or MCH (an exact match in a third company, or one found by search):
  no row can tag that company, so it links to nobody. The accounts table shows "Links to: nobody". Recommendation:
  link to nobody (follows the rule; the alternative, link to every contact, is the behaviour being removed).
- E3 Inactive account: listed, not pre-ticked (unchanged). If the admin ticks it, it follows the same company
  rule. Recommendation: keep.
- E4 Contact whose row is SRT but the card has no SRT account ticked: gets no new links; access still applies.
  Recommendation: keep.
- Q "Confirm all exact" and cards flagged "Rows disagree on companies": today it confirms them (`lib/accessSheet.ts:24-27`).
  With the per-row rule the disagreement is now harmless for links, but it still often means a wrong tag.
  Recommendation (crew): skip them; the admin confirms each by hand after reading the contacts.
