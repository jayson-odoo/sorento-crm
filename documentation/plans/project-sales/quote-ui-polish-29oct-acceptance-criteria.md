# UAC: quotation series default, product picker code only, projects list no underline (QUOTE-UI-POLISH)

Plan: `PLAN-quote-ui-polish-29oct.md` (same folder). Owner, 29 Oct ~10:00.

- AC-QUP-1: With exactly one active series, opening Edit scope on a scope with no series shows that series selected.
- AC-QUP-2: With exactly one active series, a scope that already has a series opens showing its own series.
- AC-QUP-3: With two or more active series (or none), a scope with no series opens on "No series".
- AC-QUP-4: Clearing the preselected series and saving saves the scope with no series.
- AC-QUP-5: With exactly one active series, a new quotation's first scope, and any scope added with "Add a scope",
  carries that series: the Edit scope dialog shows it and Save writes it.
- AC-QUP-6: A header-only save of a new quotation still leaves the untouched first scope out.
- AC-QUP-7: Quotation > Lines product picker shows each product code once, one column, never truncated (long codes
  wrap). Sets show their code once too.
- AC-QUP-8: Pipeline > Grid: the Code and Project cells show no underline, on hover or otherwise; clicking a row
  still opens the project.
- AC-QUP-10: No screen says "Mukim": the project form, the project overview, the staff and portal AI extract reviews
  and the portal registration form all say "Area"; the saved value is unchanged.
- AC-QUP-9: All of the above usable at 375px and 1280px.
