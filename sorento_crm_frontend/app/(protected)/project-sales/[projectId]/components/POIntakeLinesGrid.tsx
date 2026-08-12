'use client';

import * as React from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Ban, Filter, Loader2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
// The shared products `/select` mapper. Its name says "variant" because that screen needed
// it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import type { POLineUpdateBody, POVersionLine } from '../../_shared/types/poIntake.types';
import { formatMyrExact, formatQty, isDecimalString, multiplyMoney } from '../../_shared/lib/money';

export interface POIntakeLinesGridHandle {
  focusLine: (lineId: string) => void;
}

/**
 * Column preferences are keyed on this, not on the pathname DataGrid would fall back to:
 * the path carries the version id, so the fallback would write one preferences row per
 * uploaded document instead of one per person. `<perm_slug>::<stable_id>`, per
 * docs/LISTING-COLUMN-PREFERENCES.md.
 */
export const PO_INTAKE_LINES_LISTING_KEY = 'projects.projects.view::po-intake-lines';

interface Props {
  lines: POVersionLine[];
  readOnly: boolean;
  savingLineIds: string[];
  focusedLineId: string | null;
  onFocusLine: (line: POVersionLine) => void;
  onUpdateLine: (lineId: string, body: POLineUpdateBody) => Promise<void>;
}

/** A line our arithmetic disagrees with, one with no product, or one that was cancelled. */
export function isFlaggedLine(line: POVersionLine): boolean {
  return !line.arithmetic_ok || !line.resolved_product_id || line.is_cancelled;
}

/**
 * A line that wants a person to do something. A cancelled line is deliberately NOT one of
 * these: somebody already decided about it by accepting a card, so counting it as work
 * outstanding would mean accepting a cancellation ADDS to the pile.
 */
export function lineNeedsAttention(line: POVersionLine): boolean {
  return !line.is_cancelled && (!line.arithmetic_ok || !line.resolved_product_id);
}

/**
 * The 52 lines, editable in place.
 *
 * Cells are UNCONTROLLED and commit on blur. A controlled input would re-render the whole
 * grid on every keystroke, and a person correcting a misread quantity is typing into a table
 * of fifty-two rows. Escape puts the cell back to what the server holds.
 *
 * Numeric cells are text inputs, not `type="number"`: money and quantity are strings from
 * the API to the API, and a number input invites the float round trip the contract forbids.
 *
 * The real task on this document is three exceptions out of fifty-two rows, so the flagged
 * lines can be shown on their own. That filter starts OFF: somebody reconciling a total has
 * to see the whole document first, and a screen that hid rows before being asked would make
 * the totals at the top unverifiable.
 */
export const POIntakeLinesGrid = React.forwardRef<POIntakeLinesGridHandle, Props>(
  function POIntakeLinesGrid(
    { lines, readOnly, savingLineIds, focusedLineId, onFocusLine, onUpdateLine },
    ref,
  ) {
    const rowRefs = React.useRef<Record<string, HTMLElement | null>>({});
    const [confirming, setConfirming] = React.useState<{
      kind: 'cancel' | 'clear-product';
      line: POVersionLine;
    } | null>(null);
    const [flaggedOnly, setFlaggedOnly] = React.useState(false);
    // A row asked for while it is filtered out cannot be scrolled to until it mounts.
    const pendingFocusId = React.useRef<string | null>(null);

    const flagged = React.useMemo(() => lines.filter(isFlaggedLine), [lines]);
    const attentionCount = React.useMemo(
      () => lines.filter(lineNeedsAttention).length,
      [lines],
    );
    const cancelledCount = React.useMemo(
      () => lines.filter((line) => line.is_cancelled).length,
      [lines],
    );
    const visibleLines = flaggedOnly ? flagged : lines;
    const nothingLeftToShow = flaggedOnly && visibleLines.length === 0;
    // When the filter has emptied itself the way back lives in the all-clear panel, so the
    // toolbar toggle stands down rather than offering the same thing twice.
    const showFilterToggle = (flagged.length > 0 || flaggedOnly) && !nothingLeftToShow;

    const scrollToLine = React.useCallback((lineId: string) => {
      // jsdom implements no scrollIntoView, hence the optional call.
      rowRefs.current[lineId]?.scrollIntoView?.({
        block: 'center',
        behavior: 'smooth',
      });
    }, []);

    React.useImperativeHandle(ref, () => ({
      focusLine: (lineId: string) => {
        const line = lines.find((item) => item.id === lineId);
        if (!line) return;
        if (line) onFocusLine(line);
        // The banner and the handwriting cards both point at specific lines, and a card can
        // name a perfectly healthy one. Landing on it has to work with the filter on, so the
        // filter gives way rather than swallowing the jump.
        if (flaggedOnly && !isFlaggedLine(line)) {
          pendingFocusId.current = lineId;
          setFlaggedOnly(false);
          return;
        }
        scrollToLine(lineId);
      },
    }));

    React.useEffect(() => {
      const pending = pendingFocusId.current;
      if (!pending) return;
      pendingFocusId.current = null;
      scrollToLine(pending);
    }, [flaggedOnly, scrollToLine]);

    const fetchProducts = React.useCallback(async (query: string) => {
      const rows = await getProductsForVariantSelect(query || undefined);
      return rows.map((row) => ({
        value: row.id,
        label: row.product_code,
        description: row.product_name,
      }));
    }, []);

    const commit = React.useCallback(
      (line: POVersionLine, body: POLineUpdateBody) => {
        void onUpdateLine(line.id, body);
      },
      [onUpdateLine],
    );

    const columns = React.useMemo<ColumnDef<POVersionLine>[]>(() => {
      const cellWrap = (
        line: POVersionLine,
        children: React.ReactNode,
        first = false,
      ) => (
        <div
          ref={
            first
              ? (element) => {
                  rowRefs.current[line.id] = element;
                }
              : undefined
          }
          className="min-w-0"
          onFocusCapture={() => onFocusLine(line)}
          onClick={() => onFocusLine(line)}
        >
          {children}
        </div>
      );

      return [
        {
          accessorKey: 'line_no',
          header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <span className="flex items-center gap-1 text-sm tabular-nums">
                {row.original.line_no}
                {savingLineIds.includes(row.original.id) && (
                  <Loader2
                    className="size-3 animate-spin text-muted-foreground"
                    aria-hidden
                  />
                )}
              </span>,
              true,
            ),
          size: 64,
          minSize: 56,
          meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-6" /> },
        },
        {
          accessorKey: 'stock_code_raw',
          header: ({ column }) => (
            <DataGridColumnHeader title="Code on the PO" column={column} />
          ),
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="stock_code_raw"
                value={row.original.stock_code_raw ?? ''}
                readOnly={readOnly}
                label={`Code on line ${row.original.line_no}`}
                onCommit={(value) =>
                  commit(row.original, { stock_code_raw: value || null })
                }
              />,
            ),
          size: 160,
          minSize: 120,
          meta: {
            headerTitle: 'Code on the PO',
            skeleton: <Skeleton className="h-4 w-20" />,
          },
        },
        {
          accessorKey: 'description_raw',
          header: ({ column }) => (
            <DataGridColumnHeader title="Description" column={column} />
          ),
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="description_raw"
                value={row.original.description_raw ?? ''}
                readOnly={readOnly}
                label={`Description on line ${row.original.line_no}`}
                onCommit={(value) =>
                  commit(row.original, { description_raw: value || null })
                }
              />,
            ),
          size: 260,
          minSize: 160,
          meta: {
            headerTitle: 'Description',
            skeleton: <Skeleton className="h-4 w-40" />,
          },
        },
        {
          accessorKey: 'qty',
          header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="qty"
                value={row.original.qty}
                numeric
                readOnly={readOnly}
                label={`Quantity on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { qty: value })}
              />,
            ),
          size: 92,
          minSize: 72,
          meta: {
            headerTitle: 'Qty',
            skeleton: <Skeleton className="h-4 w-10" />,
          },
        },
        {
          accessorKey: 'uom_raw',
          header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="uom_raw"
                value={row.original.uom_raw ?? ''}
                readOnly={readOnly}
                label={`UOM on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { uom_raw: value || null })}
              />,
            ),
          size: 88,
          minSize: 72,
          meta: {
            headerTitle: 'UOM',
            skeleton: <Skeleton className="h-4 w-10" />,
          },
        },
        {
          accessorKey: 'unit_price',
          header: ({ column }) => (
            <DataGridColumnHeader title="Unit price" column={column} />
          ),
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="unit_price"
                value={row.original.unit_price}
                numeric
                readOnly={readOnly}
                label={`Unit price on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { unit_price: value })}
              />,
            ),
          size: 116,
          minSize: 96,
          meta: {
            headerTitle: 'Unit price',
            skeleton: <Skeleton className="h-4 w-14" />,
          },
        },
        {
          accessorKey: 'amount',
          header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
          cell: ({ row }) =>
            cellWrap(
              row.original,
              <CellInput
                line={row.original}
                field="amount"
                value={row.original.amount}
                numeric
                invalid={!row.original.arithmetic_ok}
                readOnly={readOnly}
                label={`Amount on line ${row.original.line_no}`}
                onCommit={(value) => commit(row.original, { amount: value })}
              />,
            ),
          size: 124,
          minSize: 100,
          meta: {
            headerTitle: 'Amount',
            skeleton: <Skeleton className="h-4 w-16" />,
          },
        },
        {
          id: 'check',
          header: ({ column }) => <DataGridColumnHeader title="Check" column={column} />,
          cell: ({ row }) => {
            const line = row.original;
            const expected = multiplyMoney(line.qty, line.unit_price);
            return cellWrap(
              line,
              <div className="flex flex-wrap items-center gap-1">
                {!line.arithmetic_ok && (
                  <Badge
                    variant="destructive"
                    className="text-[11px]"
                    title={
                      expected
                        ? `Quantity times unit price is ${formatMyrExact(expected)}`
                        : undefined
                    }
                  >
                    {expected
                      ? `Should be ${formatMyrExact(expected)}`
                      : 'Does not multiply out'}
                  </Badge>
                )}
                {line.is_cancelled && (
                  <Badge variant="secondary" className="text-[11px]">
                    Cancelled
                  </Badge>
                )}
                {!line.resolved_product_id && (
                  <Badge variant="outline" className="text-[11px]">
                    No product
                  </Badge>
                )}
                {line.resolution_source === 'manual' && (
                  <Badge variant="outline" className="text-[11px]">
                    Matched by hand
                  </Badge>
                )}
              </div>,
            );
          },
          size: 190,
          minSize: 130,
          meta: {
            headerTitle: 'Check',
            skeleton: <Skeleton className="h-4 w-20" />,
          },
        },
        {
          id: 'product',
          header: ({ column }) => (
            <DataGridColumnHeader title="Our product" column={column} />
          ),
          cell: ({ row }) => {
            const line = row.original;
            const selected = line.resolved_product_id
              ? {
                  value: line.resolved_product_id,
                  label: line.resolved_product_code ?? 'Matched product',
                }
              : undefined;
            return cellWrap(
              line,
              readOnly ? (
                <span
                  className="block truncate text-sm"
                  title={line.resolved_product_code ?? ''}
                >
                  {line.resolved_product_code ?? 'Not matched'}
                </span>
              ) : (
                <>
                  {/* SearchableSelect forwards `id`, not arbitrary aria props, so the
                      accessible name has to come from a real label. */}
                  <label
                    className="sr-only"
                    htmlFor={`po-line-${line.line_no}-product`}
                  >
                    {`Product on line ${line.line_no}`}
                  </label>
                  <SearchableSelect
                    id={`po-line-${line.line_no}-product`}
                    value={line.resolved_product_id ?? ''}
                    size="sm"
                    clearable
                    fetchOptions={fetchProducts}
                    selectedOption={selected}
                    placeholder="Not matched"
                    emptyMessage="No products match"
                    onChange={(value) => {
                      if (!value && line.resolved_product_id) {
                        setConfirming({ kind: 'clear-product', line });
                        return;
                      }
                      if (value !== (line.resolved_product_id ?? '')) {
                        commit(line, { resolved_product_id: value || null });
                      }
                    }}
                  />
                </>
              ),
            );
          },
          size: 210,
          minSize: 150,
          meta: {
            headerTitle: 'Our product',
            skeleton: <Skeleton className="h-4 w-24" />,
          },
        },
        {
          id: 'actions',
          header: () => <span className="sr-only">Actions</span>,
          cell: ({ row }) => {
            const line = row.original;
            if (readOnly) return null;
            return cellWrap(
              line,
              line.is_cancelled ? (
                <Button
                  type="button"
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  aria-label={`Restore line ${line.line_no}`}
                  onClick={() => commit(line, { is_cancelled: false })}
                >
                  <RotateCcw className="size-3.5" />
                </Button>
              ) : (
                <Button
                  type="button"
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  aria-label={`Cancel line ${line.line_no}`}
                  onClick={() => setConfirming({ kind: 'cancel', line })}
                >
                  <Ban className="size-3.5 text-destructive" />
                </Button>
              ),
            );
          },
          size: 68,
          minSize: 56,
          meta: {
            headerTitle: 'Actions',
            skeleton: <Skeleton className="h-4 w-6" />,
          },
        },
      ];
    }, [commit, fetchProducts, onFocusLine, readOnly, savingLineIds]);

    const table = useReactTable({
      columns,
      data: visibleLines,
      getRowId: (row) => row.id,
      getCoreRowModel: getCoreRowModel(),
      columnResizeMode: 'onChange',
    });

    return (
      <div className="min-w-0 space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="min-w-0 text-xs text-muted-foreground">
            {describeLineHealth(lines.length, attentionCount, cancelledCount)}
          </p>
          {showFilterToggle && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              aria-pressed={flaggedOnly}
              onClick={() => setFlaggedOnly((previous) => !previous)}
            >
              <Filter className="size-3.5" aria-hidden />
              {flaggedOnly
                ? `Show all ${lines.length} lines`
                : `Show only these ${flagged.length}`}
            </Button>
          )}
        </div>

        {nothingLeftToShow ? (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-50 px-6 py-10 text-center dark:bg-emerald-950/30">
            <h3 className="text-sm font-semibold text-emerald-900 dark:text-emerald-300">
              Nothing left to fix
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-emerald-900/80 dark:text-emerald-300/80">
              Every line adds up and resolves to a product.
            </p>
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={() => setFlaggedOnly(false)}
            >
              {`Show all ${lines.length} lines`}
            </Button>
          </div>
        ) : (
          <DataGrid
            table={table}
            recordCount={visibleLines.length}
            isLoading={false}
            listingKey={PO_INTAKE_LINES_LISTING_KEY}
            tableLayout={{
              width: 'fixed',
              columnsResizable: true,
              headerSticky: true,
            }}
          >
            <div className="min-w-0 rounded-lg border border-border">
              {/* The cap goes on the scrolling VIEWPORT, never on the box around it. Radix
                  gives the viewport `h-full`, and a percentage height against a parent
                  that only has a max-height resolves to auto: the viewport grew to all 51
                  rows and the root clipped it, so every row rendered and none below the
                  fold could be reached. `type="auto"` enables the overflow from the
                  content rather than from a pointer hover, so a wheel, a keyboard and a
                  jump from the banner all reach the last line. */}
              <ScrollArea
                type="auto"
                className="w-full"
                viewportClassName="max-h-[calc(100vh-14rem)]"
              >
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            </div>
          </DataGrid>
        )}

        <AlertDialog
          open={Boolean(confirming)}
          onOpenChange={(next) => !next && setConfirming(null)}
        >
          <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
            <AlertDialogHeader>
              <AlertDialogTitle>
                {confirming?.kind === 'cancel'
                  ? `Cancel line ${confirming.line.line_no}?`
                  : 'Remove the matched product?'}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {confirming?.kind === 'cancel'
                  ? `${describeLine(confirming.line)} stays on the record, marked cancelled, and is left out of our total. This action cannot be undone from the document.`
                  : confirming
                    ? `Line ${confirming.line.line_no} goes back to unmatched, and nothing on it will resolve to ${confirming.line.resolved_product_code ?? 'our catalogue'}.`
                    : ''}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                onClick={() => {
                  if (!confirming) return;
                  if (confirming.kind === 'cancel') {
                    commit(confirming.line, { is_cancelled: true });
                  } else {
                    commit(confirming.line, { resolved_product_id: null });
                  }
                  setConfirming(null);
                }}
              >
                {confirming?.kind === 'cancel' ? 'Cancel the line' : 'Remove it'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {focusedLineId && (
          <p className="sr-only" aria-live="polite">
            {`Line ${lines.find((line) => line.id === focusedLineId)?.line_no ?? ''} in focus`}
          </p>
        )}
      </div>
    );
  },
);

/**
 * How much of this document is actually work, as a sentence with numbers in it. A bare
 * toggle would leave "is this a clean read?" unanswered, which is the question.
 *
 * Cancelled lines are counted separately from lines needing attention: they are in the
 * filtered view because they are exceptions worth seeing, but they are not outstanding work.
 */
export function describeLineHealth(
  total: number,
  attention: number,
  cancelled: number,
): string {
  if (total === 0) return 'No lines';
  const cancelledClause =
    cancelled === 0
      ? ''
      : `${cancelled} ${cancelled === 1 ? 'is' : 'are'} cancelled`;

  if (attention === 0) {
    const clean = `All ${total} lines add up and resolve`;
    return cancelledClause ? `${clean}, ${cancelledClause}` : clean;
  }

  const head = `${attention} of ${total} lines need attention`;
  return cancelledClause ? `${head}, and ${cancelledClause}` : head;
}

function describeLine(line: POVersionLine): string {
  const parts = [
    `Line ${line.line_no}`,
    line.stock_code_raw ?? undefined,
    `${formatQty(line.qty)} ${line.uom_raw ?? ''}`.trim(),
    formatMyrExact(line.amount),
  ].filter(Boolean);
  return parts.join(', ');
}

function CellInput({
  line,
  field,
  value,
  numeric,
  invalid,
  readOnly,
  label,
  onCommit,
}: {
  line: POVersionLine;
  field: string;
  value: string;
  numeric?: boolean;
  invalid?: boolean;
  readOnly: boolean;
  label: string;
  onCommit: (value: string) => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  if (readOnly) {
    return (
      <span
        className={`block truncate text-sm ${numeric ? 'text-right tabular-nums' : ''} ${line.is_cancelled ? 'line-through' : ''}`}
        title={value}
      >
        {value || '-'}
      </span>
    );
  }

  return (
    <Input
      // Remount when the server's value changes, so an uncontrolled cell never shows a
      // stale reading after a card is applied or a save is refused.
      key={`${line.id}-${field}-${value}`}
      ref={inputRef}
      defaultValue={value}
      aria-label={label}
      title={value}
      inputMode={numeric ? 'decimal' : undefined}
      className={`h-8 ${numeric ? 'text-right tabular-nums' : ''} ${
        invalid ? 'border-destructive focus-visible:ring-destructive/30' : ''
      } ${line.is_cancelled ? 'line-through' : ''}`}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          inputRef.current?.blur();
        }
        if (event.key === 'Escape') {
          if (inputRef.current) inputRef.current.value = value;
          inputRef.current?.blur();
        }
      }}
      onBlur={(event) => {
        const next = event.target.value.trim();
        if (next === value) return;
        if (numeric && !isDecimalString(next)) {
          toast.error(`${label} must be a number`);
          event.target.value = value;
          return;
        }
        onCommit(next);
      }}
    />
  );
}
