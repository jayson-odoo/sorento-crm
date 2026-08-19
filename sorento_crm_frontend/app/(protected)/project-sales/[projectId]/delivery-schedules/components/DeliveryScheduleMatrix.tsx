'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { DeliverySchedulePhase } from '../../../_shared/types/deliverySchedule.types';
import type { CellMeta, ColumnState } from '../lib/scheduleTotals';
import { phaseRowLabel, sumQty } from '../lib/scheduleTotals';
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
  /**
   * The products the PO this schedule is checked against orders, for the column pickers.
   * Empty when there is no PO version to read, which sends the pickers to the catalogue.
   */
  poOptions: SearchableSelectOption[];
  canEdit: boolean;
  /** Column indexes whose product was just identified, so the map note is shown once. */
  learnedColumns: number[];
  registerColumnRef: (columnKey: string, node: HTMLElement | null) => void;
  /**
   * What the document itself marked on one cell (section 9.7a/c): a tint, or a date this
   * cell now overrides ahead of the phase's own. Absent for the ordinary cell, which is
   * most of them.
   */
  metaFor: (phaseId: string, columnKey: string) => CellMeta | undefined;
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

/**
 * The identity column, and it is wide because it carries the picker as well as the code.
 */
const PRODUCT_COL = 'w-[240px] min-w-[240px] max-w-[240px]';
/** One per delivery phase, sized for a date plus the phase it belongs to. */
const DATE_COL = 'w-[136px] min-w-[136px] max-w-[136px]';
/** The three numbers that close every product row. */
const TOTAL_COL = 'w-[124px] min-w-[124px] max-w-[124px]';

/**
 * Two paint layers, and every pinned cell names the one it is on.
 *
 * A cell pinned on BOTH axes (the "Product" heading, the totals-row label) has to beat a cell
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
 * `bg-destructive/10` is ninety percent transparent, so an unreconciled product's pinned cells
 * were tinted glass: a quantity scrolling underneath showed straight through them and read as
 * a number appearing where it did not belong. Nothing about the z-index was wrong, the cell
 * simply had almost no paint on it. `color-mix` gives the same tint as a solid colour, which is
 * what a pinned cell needs. It is also the only way to tint these tokens: the theme resolves
 * them to `oklch(...)`, so `hsl(var(--destructive) / 0.1)` would be dropped as invalid.
 */
const UNRECONCILED_BG = 'bg-[color-mix(in_oklab,var(--destructive)_12%,var(--muted))]';

/**
 * The schedule, TRANSPOSED: dates across the top, products down the side.
 *
 * The customer's printed sheet runs the other way (a column per product, a row per delivery
 * phase) and this grid used to mirror it. It now reads the way people ask about it instead -
 * "what goes out on the first of July" is a column, "how much of this basin is scheduled" is a
 * row - which is the axis the captain asked for. Nothing about the DATA changed with it.
 *
 * A NOTE ON THE WORD "COLUMN", because it now means two things. In the reconciliation payload
 * and everywhere in this code, a `column` (`ColumnState`, `columnIndex`, `data-column-key`,
 * `registerColumnRef`) is a PRODUCT - it is the customer's own word for the vertical strip on
 * their sheet, and the API addresses products by `product_index` under exactly that name. On
 * screen that same thing is now a ROW. The domain word is deliberately left alone: renaming it
 * would put the UI's vocabulary at odds with the API's for a purely visual change.
 *
 * NOT a DataGrid, because here the COLUMNS ARE DATA: there is one per delivery phase, and no
 * column config, sort or resize applies to them. What DataGrid would otherwise give us is
 * solved explicitly: the whole table scrolls inside this container so the page body never
 * scrolls sideways, the product column is sticky so a reviewer eight dates in still knows which
 * product they are on, and every cell carries a fixed width on a `w-max` table (rather than
 * `table-fixed`, which overlaps its columns the moment content exceeds the declared width).
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

  /**
   * The dates, left to right, in the sheet's own order.
   *
   * Which is area group then sequence, and that is chronological WITHIN an area - the order
   * the customer wrote and the order the phase numbers follow. Sorting the whole row by date
   * instead would interleave TOWER with COMMON AREA and lose the grouping, so the area is
   * named on the first column of each group and the boundary is drawn there.
   */
  const dateColumns = React.useMemo(
    () =>
      phaseGroups.flatMap((group) =>
        group.phases.map((phase, index) => ({
          phase,
          area: group.area,
          startsGroup: index === 0,
        })),
      ),
    [phaseGroups],
  );

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
                PRODUCT_COL,
                Z_CORNER,
                'sticky left-0 top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
              )}
            >
              Product
            </th>

            {dateColumns.map(({ phase, area, startsGroup }) => (
              <th
                key={phase.id}
                scope="col"
                className={cn(
                  DATE_COL,
                  Z_PINNED,
                  'sticky top-0 border-b border-e border-border bg-muted px-2 py-2 text-start align-bottom font-medium',
                  // Where one area ends and the next begins, drawn once rather than repeated
                  // as a label on every column under it.
                  startsGroup && 'border-s border-s-border',
                )}
              >
                <span
                  className="block truncate text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
                  title={area ?? 'Ungrouped'}
                >
                  {startsGroup ? (area ?? 'Ungrouped') : ' '}
                </span>
                <span
                  className="block truncate"
                  title={
                    phase.delivery_date
                      ? formatDateInMalaysia(phase.delivery_date)
                      : 'No date'
                  }
                >
                  {phase.delivery_date
                    ? formatDateInMalaysia(phase.delivery_date)
                    : 'No date'}
                </span>
                <span
                  className="block truncate text-[11px] font-normal text-muted-foreground"
                  title={phaseRowLabel(phase)}
                >
                  {phaseRowLabel(phase)}
                </span>
              </th>
            ))}

            {/* The three numbers the reconciliation rests on, closing every row. Not pinned to
                the right: four sticky columns need hand-computed offsets, and these same three
                numbers are already side by side in the reconciliation table above. */}
            <TotalsHeading label="Our total" />
            <TotalsHeading label="Schedule TOTAL QTY" />
            <TotalsHeading label="PO quantity" />
          </tr>
        </thead>

        <tbody>
          {columns.map((column) => (
            /**
             * The ROW is what "go to this product" scrolls to, not the cell heading it.
             *
             * Chrome refuses to auto-scroll a `position: sticky` element and says so in the
             * console ("Skipping auto-scroll behavior due to position: sticky"), so pointing
             * the jump at the pinned identity cell made the reconciliation table's row links
             * silently do nothing. The row is not pinned, and it is the thing being gone to.
             */
            <tr key={column.key} ref={(node) => controller.registerColumnRef(column.key, node)}>
              <th
                scope="row"
                className={cn(
                  PRODUCT_COL,
                  Z_PINNED,
                  'sticky left-0 border-b border-e border-border px-2 py-2 text-start align-top font-normal',
                  column.reconciled ? 'bg-background' : UNRECONCILED_BG,
                )}
              >
                <ProductHeading column={column} controller={controller} />
              </th>

              {dateColumns.map(({ phase, startsGroup }) => {
                const editable = controller.canEdit && Boolean(column.productId);
                const value = controller.valueFor(phase.id, column.key);
                const meta = controller.metaFor(phase.id, column.key);
                return (
                  <td
                    key={phase.id}
                    // The highlight is an inline style, not a class: the colour is the
                    // document's own and cannot be a Tailwind token. `color-mix` gives a
                    // real tint at partial opacity.
                    style={
                      meta?.highlight
                        ? { backgroundColor: `color-mix(in oklab, ${meta.highlight} 35%, transparent)` }
                        : undefined
                    }
                    title={meta?.highlight ? 'Highlighted in the document' : undefined}
                    className={cn(
                      DATE_COL,
                      'border-b border-e border-border p-0',
                      startsGroup && 'border-s border-s-border',
                      !meta?.highlight && (column.reconciled ? '' : 'bg-destructive/5'),
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
                      // Unchanged, phase first: it is what every other view calls this cell,
                      // and the axis it is drawn on is not part of its name.
                      aria-label={`${phaseRowLabel(phase)}, ${
                        column.productCode ?? column.customerCode ?? 'unidentified column'
                      }`}
                      onChange={(event) =>
                        controller.setDraft(phase.id, column.key, event.target.value)
                      }
                      onBlur={() => controller.commit(phase.id, column)}
                      className="h-8 w-full bg-transparent px-2 text-end tabular-nums outline-none focus:bg-primary/5 focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:text-muted-foreground"
                    />
                    {/* The phase header above keeps the DOCUMENT's own date; this one
                        product's cell shows its own, was -> now, once a proposal covering
                        it was accepted. */}
                    {meta?.deliveryDateOverride && (
                      <p className="flex items-center gap-1 truncate px-2 pb-1 text-[10px] tabular-nums">
                        <span className="text-muted-foreground line-through">
                          {phase.delivery_date ? formatDateInMalaysia(phase.delivery_date) : '—'}
                        </span>
                        <span className="font-medium">
                          {formatDateInMalaysia(meta.deliveryDateOverride)}
                        </span>
                      </p>
                    )}
                  </td>
                );
              })}

              <TotalCell column={column} value={column.ourTotal} emphasise />
              <TotalCell
                column={column}
                value={column.reportedTotal}
                missingLabel="Not printed"
                wrong={column.blockers.some(
                  (blocker) => blocker.code === 'reported_mismatch',
                )}
              />
              <TotalCell
                column={column}
                value={column.poQty}
                missingLabel="Not on the PO"
                wrong={column.blockers.some(
                  (blocker) =>
                    blocker.code === 'po_mismatch' || blocker.code === 'not_on_po',
                )}
              />
            </tr>
          ))}
        </tbody>

        {/* What leaves the yard on each date, which is the question the horizontal axis now
            asks. Our sum of what is on screen, edits included - the sheet prints no such row,
            so it is labelled as ours. */}
        <tfoot>
          <tr>
            <th
              scope="row"
              className={cn(
                PRODUCT_COL,
                Z_CORNER,
                'sticky bottom-0 left-0 border-t border-e border-border bg-muted px-2 py-1.5 text-start text-[11px] font-semibold',
              )}
            >
              Our total for the date
            </th>
            {dateColumns.map(({ phase, startsGroup }) => (
              <td
                key={phase.id}
                className={cn(
                  DATE_COL,
                  Z_PINNED,
                  'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5 text-end font-semibold tabular-nums',
                  startsGroup && 'border-s border-s-border',
                )}
              >
                <DateTotal
                  values={columns.map((column) =>
                    controller.valueFor(phase.id, column.key),
                  )}
                />
              </td>
            ))}
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5 text-end font-semibold tabular-nums',
              )}
            >
              {sumQty(columns.map((column) => column.ourTotal))}
            </td>
            {/* Nothing to total: the schedule's own TOTAL QTY row and the PO quantity are
                per product, and adding them across products would invent a number. */}
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5',
              )}
            />
            <td
              className={cn(
                TOTAL_COL,
                Z_PINNED,
                'sticky bottom-0 border-t border-e border-border bg-muted px-2 py-1.5',
              )}
            />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

/**
 * What goes out on one date, or nothing at all.
 *
 * A blank is not a zero here either: a date nothing is scheduled against renders empty rather
 * than as `0`, which would read as a decision to deliver none of it.
 */
function DateTotal({ values }: { values: string[] }) {
  const scheduled = values.some((value) => value.trim() !== '');
  return <>{scheduled ? sumQty(values) : ''}</>;
}

function TotalsHeading({ label }: { label: string }) {
  return (
    <th
      scope="col"
      className={cn(
        TOTAL_COL,
        Z_PINNED,
        'sticky top-0 border-b border-e border-border bg-muted px-2 py-2 text-end align-bottom text-[11px] font-semibold',
      )}
    >
      {label}
    </th>
  );
}

function TotalCell({
  column,
  value,
  missingLabel,
  wrong,
  emphasise,
}: {
  column: ColumnState;
  value: string | null;
  missingLabel?: string;
  wrong?: boolean;
  emphasise?: boolean;
}) {
  return (
    <td
      className={cn(
        TOTAL_COL,
        'border-b border-e border-border px-2 py-1.5 text-end align-top tabular-nums',
        // One background class, never two to be resolved later: which of two competing
        // `bg-*` utilities wins is decided by stylesheet order, not by the order they are
        // listed here.
        column.reconciled ? 'bg-muted/40' : UNRECONCILED_BG,
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
}

/**
 * A product, as the head of its own row: what it is, whether it reconciles, and the way to
 * correct it when the code was matched to the wrong thing.
 */
function ProductHeading({
  column,
  controller,
}: {
  column: ColumnState;
  controller: ScheduleGridController;
}) {
  return (
    <div className="space-y-1">
      <span
        className="block truncate font-medium"
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

      <div className="flex flex-wrap items-center gap-1">
        {column.dismissed ? (
          <Badge variant="secondary" size="sm">
            Dismissed
          </Badge>
        ) : column.blockers.length > 0 ? (
          <Badge variant="destructive" appearance="light" size="sm">
            {column.blockers.length === 1
              ? '1 to fix'
              : `${column.blockers.length} to fix`}
          </Badge>
        ) : column.warning ? (
          <Badge variant="warning" appearance="light" size="sm">
            Warning
          </Badge>
        ) : (
          <Badge variant="success" appearance="light" size="sm">
            Reconciled
          </Badge>
        )}

        {column.fromRememberedMap && (
          <Badge variant="secondary" size="sm" className="font-normal">
            Remembered code
          </Badge>
        )}
      </div>

      {/**
       * A product that HAS a match can still have the wrong one, and that is the usual
       * reason a PO looks like it never ordered the item. Offering the picker only to the
       * unidentified rows made a wrong match unfixable without deleting something. So:
       * no product, a field to fill; wrong product, a quiet "Change the product". A row
       * that agrees with the PO is left alone.
       */}
      {controller.canEdit && !column.reconciled && (
        <div className="pt-0.5 font-normal">
          <DeliveryScheduleProductPicker
            idPrefix="schedule-matrix"
            columnIndex={column.index}
            customerCode={column.customerCode}
            action={column.productId ? 'Change the product' : 'Pick the product'}
            variant={column.productId ? 'compact' : 'field'}
            poOptions={controller.poOptions}
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
