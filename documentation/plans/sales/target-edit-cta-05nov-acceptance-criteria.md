# UAC: Target record, Edit as the primary button (TARGET-EDIT-CTA)

Plan: `PLAN-target-edit-cta-05nov.md`.

- **AC1** A user with `sales.targets.edit` sees one "Edit" button in the record card's action
  group, after the pager and the gear, and not inside the gear; clicking it opens the existing
  in-place edit view with Cancel and Save. Test: `TargetRecord.test.tsx` "shows Edit as the
  primary button in the action group, outside the gear, and it opens edit mode".
- **AC2** A user without `sales.targets.edit` sees no Edit. Test: "offers no Edit without
  sales.targets.edit".
- **AC3** While a delete counts down, the countdown stands in the primary slot and Edit is not
  shown. Test: "gives the primary slot back to the delete countdown".
- **AC4** At 375px the pager, gear and Edit fit without clipping or horizontal scroll (browser
  pass).
- **AC5** Back to targets and the Targets crumb on a dealer target open the list on the Dealers
  tab, with the list state from the row click. Test: `TargetPageHeader.test.tsx` "a dealer
  target opened from the list returns to the Dealers tab with the list state".
- **AC6** The same on an agent target opens the Agents tab, Team filter kept. Test: "an agent
  target returns to the Agents tab".
- **AC7** A dealer target opened straight from a link still returns to the Dealers tab. Test:
  "a dealer target opened straight from a link still returns to the Dealers tab".
- **AC8** The prev/next pager walks only the record's own kind (existing behaviour, browser
  pass: 1 / 2 on a dealer target, 1 / 4 on an agent target in the seeded data).
