'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import { StockDocumentsPanel } from './StockDocumentsPanel';
import type {
  BoardCellLocation,
  BoardLocationWhere,
} from '../../_shared/types/fulfilmentPlanning.types';

const CHEVRON_COL = 'w-[36px] min-w-[36px] max-w-[36px]';
/**
 * The column that takes the SLACK. `w-full` on one cell of an auto-layout table is what makes
 * that column absorb whatever the fixed ones did not, so the table reaches the edge of the
 * dialog instead of stopping two thirds across and leaving a blank band beside it. The floor
 * keeps a short code readable when the dialog is narrow.
 */
const LOCATION_COL = 'w-full min-w-[120px]';
/** A floor, not a fixed width: the numbers keep their room and never overlap. */
const NUMBER_COL = 'min-w-[100px]';
/** Wide enough for "Own location", which is the longest of the four tags. */
const WHERE_COL = 'min-w-[104px]';

/**
 * Where a location stands, in the order the reader walks it: this line's own first, then the
 * agent's group, then the pools the ladder drew on, then anything outside the group.
 *
 * The table lists every location the LADDER consulted, and unlabelled they all look the same:
 * on SO415472 the pool holding 1716 sat beside five group warehouses holding nothing, and the
 * Suggestion card quoted a figure that appeared to come from nowhere.
 */
const WHERE_ORDER: BoardLocationWhere[] = ['own', 'group', 'site_pool', 'other_group'];

const WHERE_LABELS: Record<BoardLocationWhere, string> = {
  own: 'Own location',
  group: 'Group',
  site_pool: 'Site pool',
  other_group: 'Other group',
};

/**
 * What is AT each location behind a cell, tabulated (captain, 18 August 2026).
 *
 * > "the representation of the BRW-BB on hand quantity, so quantity, PO quantity etc can be more
 * > tabulated and structured like AutoCount, with expandable details instead of clicking in"
 *
 * What this replaces was a pill per location reading
 * `BRW-BB · 316 owed · On hand 478 · SO qty 47009 · SPO qty 0 · Available -46531` - one long
 * sentence per location, which two locations turned into two sentences a reader had to parse
 * word by word to compare. The same facts as a row each, under AutoCount's own headers, are read
 * by running an eye down a column.
 *
 * RESERVED MOVED OUT OF A TOOLTIP AND INTO THE TABLE, unreachable as it was on a touch screen
 * and invisible to anyone who did not hover. Free came with it and has since gone again: it is
 * `On hand - Reserved`, both of which are columns, so it restated what the reader could already
 * see. The incoming legs were in that tooltip too, and they are SPO rows in the expansion, which
 * is where the document that carries them already lives.
 *
 * NOT a DataGrid, and this is the carve-out `FulfilmentBoardMatrix` documents and PLAN 13.10
 * states: this is a fixed matrix of eight named figures, not a listing - no column config, sort,
 * resize or pagination applies to it, and its expansion is the point rather than a row action.
 * The three obligations of that carve-out are met here as they are there: the table scrolls
 * INSIDE its own container so the dialog never scrolls sideways, it is `w-full` with a min-width
 * FLOOR per column and the Location column taking the slack (never `table-fixed`, which overlaps
 * its columns the moment content exceeds the declared width), and long text truncates with a
 * `title`.
 *
 * A NULL FIGURE IS "Not stated", NEVER 0. The two are opposite instructions - 0 free means do
 * not look here, nothing stated means nobody has said where to look - and a line whose sales
 * order names no location has every stock figure null by construction.
 */
export function CellStockTable({
  locations,
  itemCode,
  groupNote,
}: {
  locations: BoardCellLocation[];
  /** What the expansion calls the product. The cell's own label, never re-derived from a code. */
  itemCode: string;
  /**
   * Why this table is showing the line's own location and nothing else, when that is all there
   * is (`BoardCell.location_group_note`). The rows are normally the sales agent's whole
   * ownership group, so a single row with no explanation reads as "this product lives in
   * exactly one place" - which is the belief the group listing exists to correct.
   */
  groupNote?: string | null;
}) {
  /**
   * Which locations stand open. Several at once on purpose: a cell that draws on its own
   * location and on the shared pool is opened precisely to compare the two, and an accordion
   * that closes one to open the other makes that comparison a memory test.
   */
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});

  if (locations.length === 0) {
    // Rendered rather than hidden, per the CRUD standard. A pivoted cell holds several products,
    // so no single stock position is true of it - and saying nothing at all would read as a
    // position of zero.
    return (
      <div className="space-y-1">
        <div
          data-testid="cell-stock-table-empty"
          className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground"
        >
          No stock position for this cell
        </div>
        {groupNote ? (
          <p data-testid="cell-stock-group-note" className="text-xs text-muted-foreground">
            {groupNote}
          </p>
        ) : null}
      </div>
    );
  }

  const showTotals = locations.length > 1;
  /**
   * The rows grouped by where they stand, in `WHERE_ORDER`. A section of SEVERAL rows carries a
   * subtotal, and only while the table spans more than one section - with a single section the
   * subtotal is the Total, printed twice under two different words.
   */
  const sections = WHERE_ORDER.map((where) => ({
    where,
    rows: locations.filter((entry) => (entry.where ?? 'own') === where),
  })).filter((section) => section.rows.length > 0);
  const showSubtotals = sections.length > 1;

  return (
    <div className="space-y-1">
    <div
      data-testid="cell-stock-table"
      className="max-h-[50vh] w-full overflow-x-auto overflow-y-auto overscroll-x-contain rounded-lg border border-border"
    >
      {/* `w-full`, never `table-fixed`: the table fills the dialog (the captain's screenshot
          had it stopping at two thirds with an empty band on the right), the numeric columns
          hold a min-width floor, and the Location column above carries the slack. */}
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th scope="col" className={cn(CHEVRON_COL, HEAD_CELL)} />
            <th scope="col" className={cn(LOCATION_COL, HEAD_CELL)}>
              Location
            </th>
            <th scope="col" className={cn(WHERE_COL, HEAD_CELL)}>
              Where
            </th>
            {NUMERIC_COLUMNS.map((column) => (
              <th key={column.key} scope="col" className={cn(NUMBER_COL, HEAD_CELL, 'text-end')}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {sections.flatMap((section) => [
          ...section.rows.map((entry) => {
            const key = entry.location ?? '__none__';
            const testKey = entry.location ?? 'none';
            // Only a position the server ADDRESSED can be opened: two products share the code
            // B2155-NL-BLUE on the live book, so resolving one from the code would answer
            // confidently about the wrong product.
            const addressable = Boolean(entry.product_id && entry.warehouse_id);
            const isOpen = Boolean(expanded[key]);
            return (
              <React.Fragment key={key}>
                <tr data-testid={`cell-location-${testKey}`}>
                  <td className={cn(CHEVRON_COL, BODY_CELL, 'px-1')}>
                    {addressable ? (
                      <Button
                        type="button"
                        mode="icon"
                        variant="ghost"
                        size="sm"
                        className="size-5"
                        data-testid={`stock-expand-${testKey}`}
                        aria-label={`${isOpen ? 'Hide' : 'Show'} documents behind ${
                          entry.location ?? 'this location'
                        }`}
                        aria-expanded={isOpen}
                        onClick={() =>
                          setExpanded((current) => ({ ...current, [key]: !current[key] }))
                        }
                      >
                        {isOpen ? (
                          <ChevronDown className="size-3.5" aria-hidden />
                        ) : (
                          <ChevronRight className="size-3.5" aria-hidden />
                        )}
                      </Button>
                    ) : (
                      // The sales order named no warehouse, so there is no position to open.
                      <span className="inline-block size-4" title="Not addressable" />
                    )}
                  </td>
                  <td className={cn(LOCATION_COL, BODY_CELL)}>
                    <span
                      className={cn(
                        'block truncate font-medium',
                        !entry.location && 'text-destructive',
                      )}
                      title={entry.location ?? 'No location'}
                    >
                      {entry.location ?? 'No location'}
                    </span>
                  </td>
                  <td className={cn(WHERE_COL, BODY_CELL)}>
                    <span
                      className="block truncate text-muted-foreground"
                      title={WHERE_LABELS[entry.where ?? 'own']}
                    >
                      {WHERE_LABELS[entry.where ?? 'own']}
                    </span>
                  </td>
                  {NUMERIC_COLUMNS.map((column) => {
                    const value = column.of(entry);
                    // Signed and never clamped: a negative Available IS the shortfall, and the
                    // colour is what makes it the number the eye lands on.
                    const negative = column.signed && isNegative(value);
                    return (
                      <td key={column.key} className={cn(NUMBER_COL, BODY_CELL)}>
                        <span
                          data-testid={`stock-${column.key}-${testKey}`}
                          className={cn(
                            'block truncate text-end tabular-nums',
                            value === null && 'text-muted-foreground',
                            negative && 'text-destructive',
                          )}
                          title={value ?? 'Not stated'}
                        >
                          {value ?? 'Not stated'}
                        </span>
                      </td>
                    );
                  })}
                </tr>

                {isOpen && addressable && (
                  <tr data-testid={`stock-expansion-${testKey}`}>
                    {/* Under the row it belongs to, spanning the whole table: the documents are
                        this location's evidence, not a column of it. */}
                    <td colSpan={3 + NUMERIC_COLUMNS.length} className="border-b border-border p-0">
                      <StockDocumentsPanel
                        productId={entry.product_id as string}
                        warehouseId={entry.warehouse_id as string}
                        itemCode={itemCode}
                        locationCode={entry.location ?? ''}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          }),
          // What this section holds, added up: "Pool BRW has 1716 available" has to be the sum
          // of rows the reader can see, not a figure only the Suggestion card knows.
          ...(showSubtotals && section.rows.length > 1
            ? [
                <tr
                  key={`subtotal-${section.where}`}
                  data-testid={`stock-subtotal-${section.where}`}
                >
                  <td className={cn(CHEVRON_COL, FOOT_CELL)} />
                  <td className={cn(LOCATION_COL, FOOT_CELL, 'text-muted-foreground')}>
                    {`${WHERE_LABELS[section.where]} subtotal`}
                  </td>
                  <td className={cn(WHERE_COL, FOOT_CELL)} />
                  {NUMERIC_COLUMNS.map((column) => {
                    if (!column.total) {
                      return <td key={column.key} className={cn(NUMBER_COL, FOOT_CELL)} />;
                    }
                    const total = sumOf(section.rows, column.of);
                    return (
                      <td key={column.key} className={cn(NUMBER_COL, FOOT_CELL)}>
                        <span
                          className={cn(
                            'block truncate text-end tabular-nums',
                            total === null && 'font-normal text-muted-foreground',
                            column.signed && isNegative(total) && 'text-destructive',
                          )}
                        >
                          {total ?? 'Not stated'}
                        </span>
                      </td>
                    );
                  })}
                </tr>,
              ]
            : []),
          ])}
        </tbody>

        {showTotals && (
          // Only when there is something to add up. One location IS its own total, and a totals
          // row repeating it is a row that says nothing.
          <tfoot>
            <tr>
              <td className={cn(CHEVRON_COL, FOOT_CELL)} />
              <td className={cn(LOCATION_COL, FOOT_CELL, 'text-muted-foreground')}>Total</td>
              <td className={cn(WHERE_COL, FOOT_CELL)} />
              {NUMERIC_COLUMNS.map((column) => {
                if (!column.total) {
                  return <td key={column.key} className={cn(NUMBER_COL, FOOT_CELL)} />;
                }
                const total = sumOf(locations, column.of);
                return (
                  <td key={column.key} className={cn(NUMBER_COL, FOOT_CELL)}>
                    <span
                      className={cn(
                        'block truncate text-end tabular-nums',
                        total === null && 'font-normal text-muted-foreground',
                        column.signed && isNegative(total) && 'text-destructive',
                      )}
                    >
                      {total ?? 'Not stated'}
                    </span>
                  </td>
                );
              })}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
      {groupNote ? (
        // Muted and one line, under the table it explains. Stated rather than left silent: a
        // single row with nothing said about it reads as the whole answer.
        <p data-testid="cell-stock-group-note" className="text-xs text-muted-foreground">
          {groupNote}
        </p>
      ) : null}
    </div>
  );
}

const HEAD_CELL =
  'sticky top-0 z-10 border-b border-e border-border bg-muted px-2 py-1.5 text-start align-bottom font-medium';
const BODY_CELL = 'border-b border-e border-border px-2 py-1.5 align-middle';
const FOOT_CELL = 'border-b border-e border-border bg-muted/50 px-2 py-1.5 font-medium';

/**
 * The columns, in AutoCount's order, because this is the order the planner reads over there and
 * then comes here to reconcile.
 *
 * There is no demand column. It used to lead the row as "Owed here", and it said what the
 * Contributing lines table below already says line by line under Outstanding - the same figure
 * twice, in a word this screen no longer uses. What this table is for is what is AT each
 * location, which is the one thing that table cannot say.
 *
 * EVERY column totals. The rows are now a whole ownership group rather than the one warehouse
 * a line named, and "what does the group hold" is the question the group was listed to answer -
 * so Reserved is summed too. It was left out when a "total" could only ever add a location to
 * itself.
 */
const NUMERIC_COLUMNS: {
  key: string;
  label: string;
  of: (entry: BoardCellLocation) => string | null;
  /** Summed in the totals row. */
  total?: boolean;
  /** May legitimately be negative, and is coloured when it is. */
  signed?: boolean;
}[] = [
  { key: 'on-hand', label: 'On hand', of: (entry) => entry.qty_on_hand ?? null, total: true },
  { key: 'reserved', label: 'Reserved', of: (entry) => entry.qty_reserved ?? null, total: true },
  // No Free column. It is `On hand - Reserved` and the two columns beside it already state
  // both, so it was a third number saying what the reader can see - and on a table this wide
  // every column costs the ones that answer a question nothing else does.
  { key: 'so', label: 'SO qty', of: (entry) => entry.so_qty ?? null, total: true },
  { key: 'spo', label: 'SPO qty', of: (entry) => entry.spo_qty ?? null, total: true },
  {
    key: 'available',
    label: 'Available',
    of: (entry) => entry.available_qty ?? null,
    total: true,
    signed: true,
  },
];

/** Absent stays absent: a column no location stated is "Not stated", never a total of 0. */
function sumOf(
  locations: BoardCellLocation[],
  pick: (entry: BoardCellLocation) => string | null,
): string | null {
  const stated = locations.map(pick).filter((value): value is string => value !== null);
  if (stated.length === 0) return null;
  return fromMinor(stated.reduce((total, value) => total + toMinor(value), 0));
}

function isNegative(value: string | null): boolean {
  return value !== null && Number(value) < 0;
}
