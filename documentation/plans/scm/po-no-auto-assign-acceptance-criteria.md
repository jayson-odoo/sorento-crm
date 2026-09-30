# UAC - Stock Debt must not distribute PO or SPO quantity across SOs by its own walk (PO-NO-AUTO-ASSIGN)

Plan: `PLAN-po-no-auto-assign.md`. Status: in progress, 30 Sep 2026.

## Journey

**Actor:** purchasing or CS planner on Supply Chain > Project Demand > Stock Debt, opening the
drawer for one product.

**Where they arrive from:** B2155-NL-BLUE. PO 202609-S0109 line 8 holds 15,000 with no S/O and
no placement. Today the drawer shows that 15,000 spread over SO373923 line 224 (36), SO382618
lines 2776 / 2864 / 3072 / 3168 (100 each) and more, as if the walk had linked them.

**Steps and the single decision each:**

1. Planner opens the cell for a month with SO lines the PO used to cover. Every line the PO alone
   was covering now reads Short for the quantity it lacks, Covered by names only on hand, a
   placement or a book-linked document.
2. Planner opens the Supply tab of the PO line's delivery month. The PO line is listed with
   Assigned to empty (or naming only its linked lines) and Free = its unlinked outstanding.
3. Planner reads the month cell. It still nets the PO's free quantity against the month's
   shortfalls (owner: "it should still contribute to the stock debt quantity").

**What they hold at the end:** a drawer that says what is linked and what is not, and a list of
SO lines that still need a link in AutoCount, instead of an allocation nobody decided.

## Acceptance criteria

- **AC-1 `[T]` An unlinked PO line covers nobody.** Given a BB line of 50 due in month M+2 and
  an open PO line of 80 (received 20) at the same bin with Delivery date in M+1, no S/O and no
  placement, when the view walks, then the line reads `short`, `assigned_qty 0`,
  `assigned_from []`, `short_qty 50`; the PO's month lists the PO row with
  `outstanding_qty 60`, `free_qty 60`, `assigned_to []`; month M+1 reads +60 and month M+2 reads
  -50 (the cell still foots with its drill).
- **AC-2 `[T]` An unlinked SPO line covers nobody either.** Same as AC-1 with an SPO allocation
  of 50 arriving in M+1 and no placement: the line is `short`, the SPO row is listed with
  `free_qty 50` and `assigned_to []`.
- **AC-3 `[T]` A placement still pins.** Given a placement of 50 on that PO line for the line,
  when the view walks, then the line reads `pinned`, `assigned_from` one `po` entry for 50, and
  the PO row's `assigned_to` names the line; the unplaced remainder is free. The same for a
  placement on an SPO allocation (`kind spo`).
- **AC-4 `[T]` The book S/O still pins, and now for an SPO too.** Given a PO line whose
  `from_so_line_ref` names the line's order, the line reads `pinned` from it (R42/R43 unchanged).
  Given an SPO allocation whose `from_so_line_ref` names the line's order and no placement, the
  line reads `pinned` with one `spo` entry and the SPO row's `assigned_to` names it.
- **AC-5 `[T]` A document never clears a shortfall.** Given a line due in M and an unlinked PO
  or SPO landing in M+1 at the same bin, when the view walks, then the line is `short`, never
  `late`, and the document is free in M+1.
- **AC-6 `[T]` On hand is unchanged.** Given 100 on hand at the bin and two lines of 60 and 60,
  the earlier line is `covered` from on hand and the later is `short 20`, exactly as before.
- **AC-7 `[T]` The board path is unchanged.** Given the same fixture as AC-1, when
  `assignments_for` runs, then the PO covers the line first-come (AC-PO-8 / AC-PO-15 still
  hold): `pin_only` is set on the view path only.
- **AC-8 `[T]` Pure.** `supply_assignment.assign` with a `pin_only` event: no line draws it,
  no shortfall is cleared by it, a pinned hold on it still takes from it, and its remainder is
  free in its own month.
- **AC-9 `[E2E]` Hand test** on the crew test copy with B2155-NL-BLUE / PO 202609-S0109 line 8:
  the SO lines it used to cover read Short, the PO row reads Free 15,000 (less anything linked
  by then) with Assigned to empty, and the month cells foot with their drills.

Superseded by this lane, for the Stock Debt view only: AC-PO-1's "a BB line due on or after D
draws it first-come by required date", AC-PO-4's "the remainder is free supply ... assigned
first-come", and `test_a_line_covered_only_by_a_free_po_reads_covered`. The board half of every
one of them stands.
