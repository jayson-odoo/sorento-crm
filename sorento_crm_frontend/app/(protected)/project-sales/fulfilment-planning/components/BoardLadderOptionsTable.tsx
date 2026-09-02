'use client';

import { formatDateInMalaysia } from '@/lib/helpers';
import { statusPillClass } from '@/lib/status-pill';
import type { BoardLadderOption } from '../../_shared/types/fulfilmentPlanning.types';

/**
 * EVERY STEP OF THE LADDER, WITH THE DATE IT WOULD FULFIL THE UNIT (R36, AC-S3-14).
 *
 * The trail answers "what was checked". This answers the question a planner asks next, and
 * which the trail cannot: "so what would the other answers have cost me?" The captain, on
 * round 6 of the plan review, wanted every step listed with the date it would fulfil the unit
 * and the days late - because a Buy that lands in November is a different decision when an SPO
 * arriving in September was on the table, and the old trail said only that the SPO rung gave
 * nothing to the composition.
 *
 * ONE COMPONENT, TWO SURFACES: the trail popover renders it under the five questions, and the
 * decision panel renders it above the editor. AC-S3-14 asks for both, and two copies of a
 * six-column table would be two things to keep in step.
 *
 * DISPLAY ONLY, for now. The chosen row is the engine's proposal; changing it is Amend, in the
 * editor below. Nothing on screen says so - the screen is not the place to explain the feature
 * (PRINCIPLES, "no feature explanations inside the UI").
 *
 * A real `<table>` rather than the shared DataGrid, on the carve-out `BoardTrailPopover` and
 * `CellStockTable` already document: at most five fixed rows inside a popover or an expanded
 * row, with no sort, paging, resize or column preference to apply to it. Its obligations are
 * met the same way - it scrolls inside its own container and long text truncates with a
 * `title`.
 *
 * LADDER v8 (S2, `PLAN-scm-fulfilment-feedback-2sep.md`, R-A/R-B): rows arrive in `options`
 * in the WALK order, and the walk now asks the site pool FIRST - "Use BRW stock", the pool's
 * share allowance, then "Use our locations", the two borrows and Buy. The table renders
 * whatever order it is given; it never re-sorts. The "Gives" column exists because that
 * first step is the one that may cover PART of the unit (R-B) rather than whole-or-nothing
 * like every other step - `option.gives_qty`, blank where the step does not state one.
 */
export function BoardLadderOptionsTable({
  options,
  contributionKey,
}: {
  options: BoardLadderOption[];
  /** Test-id key. The two surfaces render the same table under the same line's key. */
  contributionKey: string;
}) {
  if (options.length === 0) return null;
  return (
    <div
      data-testid={`ladder-options-${contributionKey}`}
      className="overflow-x-auto"
    >
      <table className="w-full min-w-[520px] text-xs">
        <thead>
          <tr className="border-b text-2xs uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-1.5 text-start font-medium">Option</th>
            <th className="px-2 py-1.5 text-end font-medium">Gives</th>
            <th className="px-2 py-1.5 text-start font-medium">Whole</th>
            <th className="px-2 py-1.5 text-start font-medium">Fulfilled</th>
            <th className="px-2 py-1.5 text-end font-medium">Days late</th>
            <th className="px-2 py-1.5 text-start font-medium">Debt</th>
            <th className="px-3 py-1.5 text-start font-medium" />
          </tr>
        </thead>
        <tbody>
          {options.map((option) => (
            <tr
              key={option.step}
              data-testid={`ladder-option-${contributionKey}-${option.step}`}
              // The chosen row is EMPHASISED rather than coloured: the pill in the last
              // column already names it, and a second colour would compete with the days-late
              // figure, which is the number the eye should land on.
              className={`border-b last:border-b-0 ${
                option.chosen ? 'bg-muted/60 font-medium' : ''
              }`}
            >
              <td className="max-w-[220px] px-3 py-1.5">
                <span className="block truncate" title={option.label}>
                  {option.label}
                </span>
              </td>
              {/* R-B, S2: the ONE step that may cover PART of the unit rather than
                  whole-or-nothing (`pool_share`, "Use BRW stock") states how much it can
                  give; every other step is already whole-or-nothing, so a repeated number
                  here would say nothing `Whole` does not. `0` renders as `0`, never blank
                  (R-K) - it is the answer, not an absence. */}
              <td
                data-testid={`ladder-option-gives-${contributionKey}-${option.step}`}
                className="px-2 py-1.5 text-end tabular-nums"
              >
                {option.gives_qty ?? ''}
              </td>
              <td className="px-2 py-1.5">
                <span
                  data-testid={`ladder-option-whole-${contributionKey}-${option.step}`}
                  className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium ${
                    option.whole
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {option.whole ? 'Yes' : 'No'}
                </span>
              </td>
              <td
                data-testid={`ladder-option-date-${contributionKey}-${option.step}`}
                className="px-2 py-1.5 tabular-nums"
              >
                {option.fulfil_date
                  ? formatDateInMalaysia(option.fulfil_date)
                  : '-'}
              </td>
              {/* BLANK ON ZERO. On time is the ordinary case, and a column of noughts reads as
                  arithmetic the reader has to check rather than as the exception it exists to
                  show. Null is the same blank: a step that gives nothing has no date to be
                  late against. */}
              <td
                data-testid={`ladder-option-late-${contributionKey}-${option.step}`}
                className={`px-2 py-1.5 text-end tabular-nums ${
                  (option.days_late ?? 0) > 0 ? 'text-destructive' : ''
                }`}
              >
                {option.days_late ? option.days_late.toLocaleString() : ''}
              </td>
              <td
                data-testid={`ladder-option-debt-${contributionKey}-${option.step}`}
                className="max-w-[180px] px-2 py-1.5"
              >
                <span className="block truncate" title={debtText(option)}>
                  {debtText(option)}
                </span>
              </td>
              <td className="px-3 py-1.5">
                {option.chosen && (
                  <span
                    data-testid={`ladder-option-chosen-${contributionKey}`}
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium ${statusPillClass(
                      'approved',
                    )}`}
                  >
                    Chosen
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * WHO PAYS FOR IT: the donor's order and the month the debt lands in.
 *
 * A dash, never a blank, because "this option owes nobody" is the answer for `use` and `buy`
 * and is worth reading as one. The donor is named by its DOCUMENT NUMBER, never an id.
 */
function debtText(option: BoardLadderOption): string {
  if (!option.debt_so_number && !option.debt_month) return '-';
  const month = option.debt_month ? debtMonthLabel(option.debt_month) : null;
  if (!option.debt_so_number) return month ?? '-';
  return month ? `${option.debt_so_number} · ${month}` : option.debt_so_number;
}

const MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/**
 * `2026-11` -> `Nov 2026`. The FULL year, unlike the Stock Debt board's own `Nov 26`: there
 * fifteen columns share one width, here the month sits beside a borrow sentence that already
 * says "its debt lands in Nov 2026" and the two must read as the same fact.
 *
 * Exported because the drawer's borrow row states the same month off the donor's own date
 * (`SupplyLineCard`), and one spelling of a month is the whole point of this helper.
 */
export function debtMonthLabel(key: string): string {
  const [year, month] = key.split('-');
  return `${MONTH_NAMES[Number(month) - 1] ?? month} ${year ?? ''}`.trim();
}

export default BoardLadderOptionsTable;
