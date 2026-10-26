# UAC: HOTFIX-PO-NULL-WORKSPACE

Plan: `PLAN-hotfix-po-null-workspace.md`.

- **HPNW-1** A chat contact whose workspace is not set, asked by its Respond.io id and the
  workspace id, with no location policy, gets every open PO / SPO line of the product: the same
  lines a staff call gets, each naming its location.
- **HPNW-2** The same contact with a location list gets only the lines on those locations; the
  summary counts only those lines.
- **HPNW-3** A Respond.io id that matches no contact still gets no lines.
- **HPNW-4** A Respond.io id shared by two contacts with no workspace still gets no lines
  (never a guess between two people).
- **HPNW-5** Every existing placed-route behaviour (staff call, internal contact id, include /
  exclude lists, availability mode) is unchanged.
