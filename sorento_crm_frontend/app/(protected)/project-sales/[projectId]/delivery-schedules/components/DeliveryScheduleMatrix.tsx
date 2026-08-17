'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { DeliverySchedulePhase } from '../../../_shared/types/deliverySchedule.types';
import type { ColumnState } from '../lib/scheduleTotals';
import { phaseRowLabel } from '../lib/scheduleTotals';
import { DeliveryScheduleProductPicker } from './DeliveryScheduleProductPicker';

/**
 * A request to put the cursor in a column, with a nonce so pressing the same button twice
 * is two requests rather than one unchanged value the views would ignore.
 */
export type ColumnFocusRequest = { key: string; nonce: number } | null;

/**
 * The first cell of this column that can actually be typed into.
 *
 * Queried out of the DOM rather than tracked in a ref map because the answer depends on
 * document order, which is the one thing the DOM already knows. `data-column-key` carries a
 * product UUID or a `#2` placeholder; both are safe inside a quoted attribute selector.
 */
export function firstEditableCell(
  root: HTMLElement | null,
  columnKey: string,
): HTMLInputElement | null {
  if (!root) return null;
  const cells = root.querySelectorAll<HTMLInputElement>(
    `input[data-column-key="${columnKey}"]`,
  );
  for (const cell of Array.from(cells)) if (!cell.disabled) return cell;
  return null;
}

/**
 * Whether this view is the one the breakpoint is actually showing.
 *
 * `offsetParent` is null for anything a media query has hidden, which is exactly the shape of
 * the grid this width is not using. jsdom lays nothing out, so it is null there for both.
 */
export function isDisplayed(node: HTMLElement | null): boolean {
  return Boolean(node && node.offsetParent !== null);
}

/** Everything the two views of the grid need. Built once in the review client. */
export interface ScheduleGridController {
  columns: ColumnState[];
  phaseGroups: { area: string | null; phases: DeliverySchedulePhase[] }[];
  /** The quantity on screen for a cell: the reviewer's edit if there is one, else the stored value. */
  valueFor: (phaseId: string, columnKey: string) => string;
  setDraft: (phaseId: string, columnKey: string, value: string) => void;
  commit: (phaseId: string, column: ColumnState) => void;
  resolveProduct: (columnIndex: number, productId: string) => void;
  canEdit: boolean;
  /** Column indexes whose product was just identified, so the map note is shown once. */
  learnedColumns: number[];
  registerColumnRef: (columnKey: string, node: HTMLElement | null) => void;
  /**
   * A column the reviewer asked to be put inside, from the reconciliation list.
   *
   * Both views watch it. The matrix answers unconditionally because a browser refuses focus
   * to an element it is not rendering, so at phone width its attempt is a no-op; the phone
   * cards check they are on screen first, because answering there means EXPANDING a card,
   * which is a visible change and must not happen in a view nobody is looking at.
   */
  focusRequest: ColumnFocusRequest;
}

const PHASE_COL = 'w-[200px] min-w-[200px] max-w-[200px]';
const DATA_COL = 'w-[172px] min-w-[172px] max-w-[172px]';

/**
 * Two paint layers, and every pinned cell names the one it is on.
 *
 * A cell pinned on BOTH axes (the "Phase" heading, each totals label) has to beat a cell
 * pinned on one, because those are the only two that ever cover the same pixels, and with
 * equal z-index the winner is whichever the DOM happened to put last rather than whichever
 * a reader expects to see.
 */
const Z_PINNED = 'z-20';
const Z_CORNER = 'z-30';

/**
 * A pinned cell has to be OPAQUE, and this is the whole of the "stray number in the header"
 * report.
 *
 * `bg-destructive/10` is ninety percent transparent, so an unreconciled column's header and
 * totals band were tinted glass: a quantity scrolling underneath showed straight through
 * them and read as a number appearing in the header row. Nothing about the z-index was
 * wrong, the header simply had almost no paint on it. `color-mix` gives the same tint as a
 * solid colour, which is what a pinned cell needs. It is also the only way to tint these
 * tokens: the theme resolves them to `oklch(...)`, so `hsl(var(--destructive) / 0.1)` would
 * be dropped by the browser as invalid.
 */
const UNRECONCILED_BG = 'bg-[color-mix(in_oklab,var(--destructive)_12%,var(--muted))]';

/**
 * The schedule as the customer drew it: phase rows down, product columns across, grouped by
 * area, with the three totals at the foot of every column.
 *
 * NOT a DataGrid, because here the COLUMNS ARE DATA: there are as many of them as the customer
 * has products, and no column config, sort or resize applies. What DataGrid would otherwise
 * give us is solved explicitly: the whole table scrolls inside this container so the page body
 * never scrolls sideways, the phase column is sticky so a reviewer twenty columns in still
 * knows which phase they are on, and every cell carries a fixed width on a `w-max` table
 * (rather than `table-fixed`, which overlaps its columns the moment content exceeds the
 * declared width).
 *
 * A BLANK CELL IS NOT A ZERO. It means this phase does not take this product, so it renders
 * blank and stays blank.
 */
export function DeliveryScheduleMatrix({
  controller,
}: {
  controller: ScheduleGridController;
}) {
  const { columns, phaseGroups, focusRequest } = controller;
  const rootRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!focusRequest) return;
    const cell = firstEditableCell(rootRef.current, focusRequest.key);
    if (!cell) return;
    cell.focus();
    // jsdom implements no scrollIntoView, hence the optional call.
    cell.scrollIntoView?.({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [focusRequest]);

  return (
    <div
      ref={rootRef}
      data-testid="schedule-matrix"
      className="relative max-h-[70vh] w-full overflow-auto overscroll-x-contain rounded-lg border border-border"
    >
      <table className="w-max border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th
              scope="col"
              className={cn(
                PHASE_COL,
                Z_CORNER,
                'sticky left-0 top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
              )}
            >
              Phase
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                ref={(node) => controller.registerColumnRef(column.key, node)}
                className={cn(
                  DATA_COL,
                  Z_PINNED,
                  'sticky top-0 border-b border-e border-border px-2 py-2 text-start align-bottom font-medium',
                  column.reconciled ? 'bg-muted' : UNRECONCILED_BG,
                )}
              >
                <ColumnHeading column={column} controller={controller} />
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {phaseGroups.map((group) => (
            <React.Fragment key={group.area ?? '__none__'}>
              <tr>
                <th
                  scope="colgroup"
                  className={cn(
                    PHASE_COL,
                    Z_PINNED,
                    'sticky left-0 border-b border-e border-border bg-accent px-2 py-1.5 text-start text-[11px] font-semibold uppercase tracking-wide',
                  )}
                >
                  {group.area ?? 'Ungrouped'}
                </th>
                <td
                  colSpan={columns.length}
                  className="border-b border-border bg-accent px-2 py-1.5"
                />
              </tr>

              {group.phases.map((phase) => (
                <tr key={phase.id}>
                  <th
                    scope="row"
                    className={cn(
                      PHASE_COL,
                      Z_PINNED,
                      'sticky left-0 border-b border-e border-border bg-background px-2 py-1.5 text-start font-normal',
                    )}
                  >
                    <span
                      className="block truncate font-medium"
                      title={phaseRowLabel(phase)}
                    >
                      {phaseRowLabel(phase)}
                    </span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {phase.delivery_date
                        ? formatDateInMalaysia(phase.delivery_date)
                        : 'No date'}
                    </span>
                  </th>

                  {columns.map((column) => {
                    const editable = controller.canEdit && Boolean(column.productId);
                    const value = controller.valueFor(phase.id, column.key);
                    return (
                      <td
                        key={column.key}
                        className={cn(
                          DATA_COL,
                          'border-b border-e border-border p-0',
                          column.reconciled ? '' : 'bg-destructive/5',
                        )}
                      >
                        <input
                          type="text"
                          inputMode="decimal"
                          data-column-key={column.key}
                          // Quantities stay strings end to end (contract convention): the
                          // value is never parsed here, only echoed back to the API.
                          value={value}
                          disabled={!editable}
                          aria-label={`${phaseRowLabel(phase)}, ${
                            column.productCode ?? column.customerCode ?? 'unidentified column'
                          }`}
                          onChange={(event) =>
                            controller.setDraft(phase.id, column.key, event.target.value)
                          }
                          onBlur={() => controller.commit(phase.id, column)}
                          className="h-8 w-full bg-transparent px-2 text-end tabular-nums outline-none focus:bg-primary/5 focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:text-muted-foreground"
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>

        {/* The comparison, at the foot of every column, all three numbers side by side. */}
        <tfoot>
          <TotalsRow
            label="Our total"
            columns={columns}
            valueOf={(column) => column.ourTotal}
            emphasise
          />
          <TotalsRow
            label="Schedule TOTAL QTY"
            columns={columns}
            valueOf={(column) => column.reportedTotal}
            missingLabel="Not printed"
            wrongWhen={(column) =>
              column.blockers.some((blocker) => blocker.code === 'reported_mismatch')
            }
          />
          <TotalsRow
            label="PO quantity"
            columns={columns}
            valueOf={(column) => column.poQty}
            missingLabel="Not on the PO"
            wrongWhen={(column) =>
              column.blockers.some(
                (blocker) =>
                  blocker.code === 'po_mismatch' || blocker.code === 'not_on_po',
              )
            }
          />
        </tfoot>
      </table>
    </div>
  );
}

function ColumnHeading({
  column,
  controller,
}: {
  column: ColumnState;
  controller: ScheduleGridController;
}) {
  return (
    <div className="space-y-1">
      <span
        className="block truncate"
        title={column.productCode ?? 'Not identified'}
      >
        {column.productCode ?? 'Not identified'}
      </span>
      {column.customerCode && (
        <span
          className="block truncate text-[11px] font-normal text-muted-foreground"
          title={column.customerCode}
        >
          {column.customerCode}
        </span>
      )}

      {column.reconciled ? (
        <Badge variant="success" appearance="light" size="sm">
          Reconciled
        </Badge>
      ) : (
        <Badge variant="destructive" appearance="light" size="sm">
          {column.blockers.length === 1
            ? '1 to fix'
            : `${column.blockers.length} to fix`}
        </Badge>
      )}

      {column.fromRememberedMap && (
        <Badge variant="secondary" size="sm" className="font-normal">
          Remembered code
        </Badge>
      )}

      {/**
       * A column that HAS a product can still have the wrong one, and that is the usual
       * reason a PO looks like it never ordered the item. Offering the picker only to the
       * unidentified columns made a wrong match unfixable without deleting something. So:
       * no product, a field to fill; wrong product, a quiet "Change the product" that does
       * not spend a 172px header on a select box. A reconciled column is left alone.
       */}
      {controller.canEdit && !column.reconciled && (
        <div className="pt-0.5 font-normal">
          <DeliveryScheduleProductPicker
            idPrefix="schedule-matrix"
            columnIndex={column.index}
            customerCode={column.customerCode}
            action={column.productId ? 'Change the product' : 'Pick the product'}
            variant={column.productId ? 'compact' : 'field'}
            onPick={(productId) => controller.resolveProduct(column.index, productId)}
          />
        </div>
      )}

      {controller.learnedColumns.includes(column.index) && column.customerCode && (
        <p className="whitespace-normal pt-0.5 text-[11px] font-normal text-muted-foreground">
          {`${column.customerCode} will resolve to ${
            column.productCode ?? 'this product'
          } on this customer's next schedule.`}
        </p>
      )}
    </div>
  );
}

function TotalsRow({
  label,
  columns,
  valueOf,
  missingLabel,
  wrongWhen,
  emphasise,
}: {
  label: string;
  columns: ColumnState[];
  valueOf: (column: ColumnState) => string | null;
  missingLabel?: string;
  wrongWhen?: (column: ColumnState) => boolean;
  emphasise?: boolean;
}) {
  return (
    <tr>
      <th
        scope="row"
        className={cn(
          PHASE_COL,
          Z_CORNER,
          'sticky bottom-0 left-0 border-t border-e border-border bg-muted px-2 py-1.5 text-start text-[11px] font-semibold',
        )}
      >
        {label}
      </th>
      {columns.map((column) => {
        const value = valueOf(column);
        const wrong = wrongWhen?.(column) ?? false;
        return (
          <td
            key={column.key}
            className={cn(
              DATA_COL,
              Z_PINNED,
              'sticky bottom-0 border-t border-e border-border px-2 py-1.5 text-end tabular-nums',
              // One background class, never two to be resolved later: which of two
              // competing `bg-*` utilities wins is decided by stylesheet order, not by
              // the order they are listed here.
              column.reconciled ? 'bg-muted' : UNRECONCILED_BG,
              emphasise && 'font-semibold',
              wrong && 'text-destructive',
            )}
          >
            {value ?? (
              <span className="text-[11px] font-normal text-muted-foreground">
                {missingLabel ?? 'Not given'}
              </span>
            )}
          </td>
        );
      })}
    </tr>
  );
}
