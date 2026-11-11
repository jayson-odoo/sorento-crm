'use client';

import * as React from 'react';
import {
  type ColumnDef,
  getCoreRowModel,
  type RowSelectionState,
  useReactTable,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { NumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import { numberFieldError } from '@/lib/number-field';
import { cn } from '@/lib/utils';
import type {
  PoLinkCapabilities,
  PoLinkOption,
  PoLinkResult,
} from '../../stock-debt/types/stockDebtSnapshot.types';
import { usePoLinkMutations } from './usePoLink';
import type { PoLinkLine, PoLinkSkippedRow, PoLinkTarget } from './poLink.types';
import { poLinkResultText, type PoLinkKind } from './poLinkWording';

/**
 * AC-LINK-CRM-UI: the Decide menu's PO popup (mock v4, approved 4 Nov). The same shell as
 * `_shared/components/RequestReserveDialog.tsx`: one DataGrid, one row per ticked line, every
 * row opens ticked and only ticked rows are sent. Three modes:
 *
 * - `link`: pick a PO line per SO line and the qty (defaults to the line's outstanding, capped
 *   at the PO line's free). The Shared Service decides whole row versus part of a row.
 * - `unlink`: the PO lines linked to the ticked lines; each ticked one is unlinked.
 * - `relink`: the PO lines linked to the ticked lines, each moved to another line of the row.
 *
 * After Send the body turns into one result per line, in plain words, with Move location or
 * Resume where AutoCount left it part way. The CRM never re-sends a step itself.
 */
export interface PoLinkDialogProps {
  mode: PoLinkKind;
  /** Where this screen's PO link calls go (Stock Debt snapshot row, Order Inquiry rows). */
  target: PoLinkTarget;
  /** The ticked lines. */
  lines: PoLinkLine[];
  /** Every line of the group: the targets a PO can be moved to. */
  allLines: PoLinkLine[];
  capabilities: PoLinkCapabilities;
  poLines: PoLinkOption[];
  /** sales_order_line_id -> its AutoCount book: a PO line links only within its own book. */
  soBooks?: Record<string, string>;
  /** Order Inquiry: ticked rows left out, named with the reason. */
  skipped?: PoLinkSkippedRow[];
  onClose: () => void;
}

interface DialogRow {
  id: string;
  line: PoLinkLine;
  /** Unlink / relink: the PO line linked to `line`. */
  poLineId: string | null;
  poLabel: string | null;
  linkedQty: number | null;
}

const TITLE: Record<PoLinkKind, string> = {
  link: 'Link to PO',
  unlink: 'Unlink from PO',
  relink: 'Move PO to another sales order',
  change: 'Change PO',
};
const SEND: Record<PoLinkKind, string> = { link: 'Link', unlink: 'Unlink', relink: 'Move', change: 'Change' };

function soLine(line: PoLinkLine): string {
  return line.line_no != null ? String(line.line_no) : '-';
}

/** Owner, 5 Nov ("just show me the PO number"): the PO number alone; only when two lines of
 *  one PO are both offered does each carry its AutoCount line number in brackets. */
function poOptionLabel(po: PoLinkOption, ambiguous: boolean): string {
  return ambiguous ? `${po.po_number} (${po.po_line_no ?? '-'})` : po.po_number;
}

/** What the line still needs from a PO: outstanding now, less what POs already cover
 *  (crew round 3: the same line could be linked twice and over-allocated in AutoCount). */
export function stillNeeds(line: PoLinkLine): number {
  const outstanding = Math.floor(line.now?.open_qty ?? line.open_qty);
  const linked = (line.now?.po_links ?? []).reduce((sum, po) => sum + po.qty, 0);
  return Math.max(0, outstanding - linked);
}

/** "Already covered by PO X (10)" for a line POs fully cover, else null. */
export function coveredText(line: PoLinkLine): string | null {
  const links = line.now?.po_links ?? [];
  if (!links.length || stillNeeds(line) > 0) return null;
  return `Already covered by ${links.map((po) => `PO ${po.po_number} (${po.qty.toLocaleString()})`).join(', ')}`;
}

function qtyCap(line: PoLinkLine, po: PoLinkOption | undefined): number {
  const needs = stillNeeds(line);
  return po ? Math.min(needs, Math.floor(po.free_qty)) : needs;
}

const OTHER_BOOK = 'In another AutoCount book from this sales order';

const TONE = {
  ok: 'bg-emerald-100 text-emerald-800',
  warn: 'bg-amber-100 text-amber-800',
  error: 'bg-red-100 text-red-800',
};

function ResultCard({
  result,
  kind,
  target,
  retryItem,
}: {
  result: PoLinkResult;
  kind: PoLinkKind;
  target: PoLinkTarget;
  /** The one link this card was for: Try again sends exactly it through the target's link api. */
  retryItem?: { sales_order_line_id: string; po_line_id: string; qty: number } | null;
}) {
  const { relocate, resume, link } = usePoLinkMutations(target);
  const [current, setCurrent] = React.useState(result);
  const text = poLinkResultText(current, kind);
  const busy = relocate.isPending || resume.isPending || link.isPending;
  const canRetry = Boolean(retryItem) && (current.outcome === 'refused' || current.outcome === 'vendor_error');
  return (
    <div className={cn('space-y-1 rounded-md p-3 text-sm', TONE[text.tone])} data-testid="po-link-result">
      <p className="font-semibold">{text.title}</p>
      <p className="tabular-nums">{text.text}</p>
      {canRetry ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={async () => {
            try {
              const out = await link.mutateAsync([retryItem as NonNullable<typeof retryItem>]);
              const next = out.results[0];
              if (next) {
                setCurrent({ ...current, ...next, so_number: next.so_number ?? current.so_number, so_line_no: next.so_line_no ?? current.so_line_no });
              }
            } catch {
              // The mutation hook already toasted the error; the card stays for another try.
            }
          }}
        >
          Try again
        </Button>
      ) : null}
      {text.action === 'relocate' && current.po_line_id ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={async () => {
            const next = await relocate.mutateAsync(current.po_line_id as string);
            setCurrent({
              ...current,
              outcome: next.outcome,
              error_code: next.error_code,
              message: next.message,
              warnings: next.outcome === 'done' ? [] : current.warnings,
            });
          }}
        >
          Move to the sales order location
        </Button>
      ) : null}
      {text.action === 'resume' && current.operation_id && current.po_line_id ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={async () => {
            const next = await resume.mutateAsync({
              operationId: current.operation_id as string,
              poLineId: current.po_line_id as string,
              salesOrderLineId: current.sales_order_line_id,
            });
            setCurrent({ ...current, ...next, so_number: current.so_number, so_line_no: current.so_line_no });
          }}
        >
          Resume
        </Button>
      ) : null}
    </div>
  );
}

export function PoLinkDialog({
  mode,
  target: poTarget,
  lines,
  allLines,
  capabilities,
  poLines,
  soBooks,
  skipped,
  onClose,
}: PoLinkDialogProps) {
  const { link, unlink, relink, change } = usePoLinkMutations(poTarget);
  const rows = React.useMemo<DialogRow[]>(() => {
    if (mode === 'link') {
      return lines.map((line) => ({
        id: line.sales_order_line_id,
        line,
        poLineId: null,
        poLabel: null,
        linkedQty: null,
      }));
    }
    return lines.flatMap((line) =>
      (line.now?.po_links ?? [])
        // Change PO (owner, 11 Nov, card 1a): only a line covered by exactly one PO line.
        .filter(() => mode !== 'change' || (line.now?.po_links ?? []).length === 1)
        .map((po) => ({
        id: `${line.sales_order_line_id}:${po.po_line_id}`,
        line,
        poLineId: po.po_line_id,
        poLabel: `${po.po_number} · line ${po.po_line_no ?? '-'}`,
        // Change PO moves the open balance only (crew for the owner, 11 Nov).
        linkedQty: mode === 'change' ? (po.open_qty ?? po.qty) : po.qty,
      })),
    );
  }, [mode, lines]);

  const poById = React.useMemo(() => new Map(poLines.map((po) => [po.po_line_id, po])), [poLines]);
  const poOptions = React.useMemo<SearchableSelectOption[]>(
    () =>
      poLines.map((po) => ({
        value: po.po_line_id,
        label: poOptionLabel(
          po,
          poLines.filter((other) => other.po_number === po.po_number).length > 1,
        ),
      })),
    [poLines],
  );

  const [picked, setPicked] = React.useState<Record<string, string>>({});
  const [qty, setQty] = React.useState<Record<string, string>>({});
  const [target, setTarget] = React.useState<Record<string, string>>({});
  const selectable = React.useCallback(
    (row: DialogRow) => mode !== 'link' || coveredText(row.line) === null,
    [mode],
  );
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>(() =>
    Object.fromEntries(rows.filter(selectable).map((row) => [row.id, true])),
  );
  /** The PO choices for one SO line: a PO of another AutoCount book is greyed with why. */
  const optionsFor = React.useCallback(
    (line: PoLinkLine): SearchableSelectOption[] => {
      const book = soBooks?.[line.sales_order_line_id];
      return poOptions.map((option) => {
        const po = poById.get(option.value);
        return book && po?.book && po.book !== book
          ? { ...option, disabled: true, description: OTHER_BOOK }
          : option;
      });
    },
    [poOptions, poById, soBooks],
  );
  const [showErrors, setShowErrors] = React.useState(false);
  const [results, setResults] = React.useState<PoLinkResult[] | null>(null);
  const [sentLinks, setSentLinks] = React.useState<Record<string, { sales_order_line_id: string; po_line_id: string; qty: number }>>({});

  function rowError(row: DialogRow): string | undefined {
    if (mode === 'relink') return target[row.id] ? undefined : 'Pick the sales order line';
    if (mode === 'change') {
      const po = poById.get(picked[row.id] ?? '');
      if (!po) return 'No PO line picked';
      const needs = row.linkedQty ?? 0;
      if (needs >= po.po_qty && !capabilities.link_row.enabled) {
        return `Linking the whole PO line: ${capabilities.link_row.reason ?? 'Waiting for AutoCount'}`;
      }
      // Card 3a: the new PO line must have the whole linked qty free (shared across lines).
      const total = rows
        .filter((other) => rowSelection[other.id] && picked[other.id] === po.po_line_id)
        .reduce((sum, other) => sum + (other.linkedQty ?? 0), 0);
      if (needs > po.free_qty || total > po.free_qty) {
        return `PO ${po.po_number} has only ${po.free_qty.toLocaleString()} free`;
      }
      return undefined;
    }
    if (mode !== 'link') return undefined;
    const po = poById.get(picked[row.id] ?? '');
    if (!po) return 'No PO line picked';
    const typed = qty[row.id] ?? String(qtyCap(row.line, po));
    const max = qtyCap(row.line, po);
    const error = numberFieldError(typed, { min: 1, max, integer: true });
    if (error) return error;
    if (Number(typed) === po.po_qty && !capabilities.link_row.enabled) {
      return `Linking the whole PO line: ${capabilities.link_row.reason ?? 'Waiting for AutoCount'}`;
    }
    // Two ticked lines on one PO line share its free stock.
    const total = rows
      .filter((other) => rowSelection[other.id] && picked[other.id] === po.po_line_id)
      .reduce(
        (sum, other) => sum + Number(qty[other.id] ?? String(qtyCap(other.line, po))),
        0,
      );
    if (total > po.free_qty) return `PO ${po.po_number} has ${po.free_qty.toLocaleString()} free in total`;
    return undefined;
  }

  const stateRef = React.useRef({ picked, qty, target, showErrors, rowError });
  stateRef.current = { picked, qty, target, showErrors, rowError };

  const targetOptions = React.useMemo(
    () =>
      allLines.map((line) => ({
        value: line.sales_order_line_id,
        label: `${line.so_number} · line ${soLine(line)}`,
        description: line.warehouse_code ?? undefined,
      })),
    [allLines],
  );

  const columns = React.useMemo<ColumnDef<DialogRow>[]>(() => {
    const base: ColumnDef<DialogRow>[] = [
      buildSelectColumn<DialogRow>({
        selectAllRows: true,
        enableRow: (row) => selectable(row.original),
        disabledReason: (row) => (selectable(row.original) ? undefined : coveredText(row.original.line) ?? undefined),
        rowLabel: (row) => `Select ${row.original.line.so_number} line ${soLine(row.original.line)}`,
      }),
      {
        id: 'so',
        header: 'Sales order',
        size: 120,
        cell: ({ row }) => <span className="font-medium">{row.original.line.so_number}</span>,
      },
      {
        id: 'line',
        header: 'Line',
        size: 60,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => <span className="tabular-nums">{soLine(row.original.line)}</span>,
      },
      {
        id: 'location',
        header: 'Location',
        size: 100,
        cell: ({ row }) => <span>{row.original.line.warehouse_code ?? '-'}</span>,
      },
      {
        id: 'delivery_date',
        header: 'Delivery date',
        size: 110,
        cell: ({ row }) =>
          row.original.line.required_date ? (
            <span>{formatDateInMalaysia(row.original.line.required_date)}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
      },
      {
        id: 'outstanding',
        header: 'Outstanding',
        size: 100,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.line.open_qty.toLocaleString()}</span>
        ),
      },
    ];
    if (mode === 'link') {
      return [
        ...base,
        {
          id: 'po',
          header: 'PO',
          size: 240,
          cell: ({ row }) =>
            coveredText(row.original.line) ? (
              <span className="block truncate text-sm text-muted-foreground" title={coveredText(row.original.line) ?? undefined}>
                {coveredText(row.original.line)}
              </span>
            ) : (
            <>
              <Label htmlFor={`po-link-po-${row.original.id}`} className="sr-only">
                PO
              </Label>
              <SearchableSelect
                id={`po-link-po-${row.original.id}`}
                value={stateRef.current.picked[row.original.id] ?? ''}
                disabled={!row.getIsSelected()}
                placeholder="Pick a PO line"
                clearable
                truncateTriggerLabel
                onChange={(value) => setPicked((prev) => ({ ...prev, [row.original.id]: value }))}
                options={optionsFor(row.original.line)}
              />
            </>
          ),
        },
        {
          id: 'po_qty',
          header: 'PO qty',
          size: 80,
          meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
          cell: ({ row }) => {
            const po = poById.get(stateRef.current.picked[row.original.id] ?? '');
            return <span className="tabular-nums">{po ? po.po_qty.toLocaleString() : '-'}</span>;
          },
        },
        {
          id: 'free',
          header: 'Free',
          size: 80,
          meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
          cell: ({ row }) => {
            const po = poById.get(stateRef.current.picked[row.original.id] ?? '');
            return <span className="tabular-nums">{po ? po.free_qty.toLocaleString() : '-'}</span>;
          },
        },
        {
          id: 'qty',
          header: 'Qty',
          size: 110,
          cell: ({ row }) => {
            const po = poById.get(stateRef.current.picked[row.original.id] ?? '');
            const cap = qtyCap(row.original.line, po);
            const included = row.getIsSelected();
            return (
              <>
                <Label htmlFor={`po-link-qty-${row.original.id}`} className="sr-only">
                  Qty
                </Label>
                <NumberInput
                  id={`po-link-qty-${row.original.id}`}
                  min={1}
                  max={cap}
                  disabled={!included || !po}
                  value={stateRef.current.qty[row.original.id] ?? String(cap)}
                  error={
                    stateRef.current.showErrors && included
                      ? stateRef.current.rowError(row.original)
                      : undefined
                  }
                  onChange={(event) => {
                    const typed = event.target.value;
                    setQty((prev) => ({ ...prev, [row.original.id]: typed }));
                  }}
                />
              </>
            );
          },
        },
      ];
    }
    const linkedCols: ColumnDef<DialogRow>[] = [
      ...base,
      {
        id: 'po',
        header: 'PO',
        size: 200,
        cell: ({ row }) => <span className="tabular-nums">{row.original.poLabel}</span>,
      },
      {
        id: 'po_qty',
        header: mode === 'change' ? 'Open' : 'PO qty',
        size: 80,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
        cell: ({ row }) => (
          <span className="tabular-nums">{(row.original.linkedQty ?? 0).toLocaleString()}</span>
        ),
      },
    ];
    if (mode === 'unlink') return linkedCols;
    if (mode === 'change') {
      return [
        ...linkedCols,
        {
          id: 'change_to',
          header: 'Change to',
          size: 240,
          cell: ({ row }) => (
            <>
              <Label htmlFor={`po-link-change-${row.original.id}`} className="sr-only">
                Change to
              </Label>
              <SearchableSelect
                id={`po-link-change-${row.original.id}`}
                value={stateRef.current.picked[row.original.id] ?? ''}
                disabled={!row.getIsSelected()}
                placeholder="Pick a PO line"
                clearable
                truncateTriggerLabel
                onChange={(value) => setPicked((prev) => ({ ...prev, [row.original.id]: value }))}
                options={optionsFor(row.original.line).filter(
                  (option) => option.value !== row.original.poLineId,
                )}
              />
              {stateRef.current.showErrors && row.getIsSelected() && stateRef.current.rowError(row.original) ? (
                <p className="mt-1 truncate text-xs text-destructive" role="alert">
                  {stateRef.current.rowError(row.original)}
                </p>
              ) : null}
            </>
          ),
        },
        {
          id: 'free',
          header: 'Free',
          size: 80,
          meta: { headerClassName: 'text-end', cellClassName: 'text-end' },
          cell: ({ row }) => {
            const po = poById.get(stateRef.current.picked[row.original.id] ?? '');
            return <span className="tabular-nums">{po ? po.free_qty.toLocaleString() : '-'}</span>;
          },
        },
      ];
    }
    return [
      ...linkedCols,
      {
        id: 'target',
        header: 'Move to',
        size: 200,
        cell: ({ row }) => (
          <>
            <Label htmlFor={`po-link-target-${row.original.id}`} className="sr-only">
              Move to
            </Label>
            <SearchableSelect
              id={`po-link-target-${row.original.id}`}
              value={stateRef.current.target[row.original.id] ?? ''}
              disabled={!row.getIsSelected()}
              placeholder="Pick a sales order line"
              clearable
              truncateTriggerLabel
              onChange={(value) => setTarget((prev) => ({ ...prev, [row.original.id]: value }))}
              options={targetOptions.filter(
                (option) => option.value !== row.original.line.sales_order_line_id,
              )}
            />
          </>
        ),
      },
    ];
    // Cells read live values through `stateRef` (the RequestReserveDialog G6 lesson).
  }, [mode, poById, targetOptions, optionsFor, selectable]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: (row) => selectable(row.original),
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const coveredTwice = mode === 'change' && lines.some((line) => (line.now?.po_links ?? []).length > 1);
  const ticked = rows.filter((row) => rowSelection[row.id]);
  const sending = link.isPending || unlink.isPending || relink.isPending || change.isPending;

  async function handleSend() {
    if (ticked.some((row) => rowError(row))) {
      setShowErrors(true);
      return;
    }
    try {
      let out: { results: PoLinkResult[] };
      if (mode === 'link') {
        const items = ticked.map((row) => {
          const po = poById.get(picked[row.id]) as PoLinkOption;
          return {
            sales_order_line_id: row.line.sales_order_line_id,
            po_line_id: po.po_line_id,
            qty: Number(qty[row.id] ?? String(qtyCap(row.line, po))),
          };
        });
        setSentLinks(Object.fromEntries(items.map((item) => [item.sales_order_line_id, item])));
        out = await link.mutateAsync(items);
      } else if (mode === 'change') {
        out = await change.mutateAsync(
          ticked.map((row) => ({
            sales_order_line_id: row.line.sales_order_line_id,
            po_line_id: picked[row.id],
          })),
        );
      } else if (mode === 'unlink') {
        out = await unlink.mutateAsync(ticked.map((row) => row.poLineId as string));
      } else {
        out = await relink.mutateAsync(
          ticked.map((row) => ({
            po_line_id: row.poLineId as string,
            to_sales_order_line_id: target[row.id],
          })),
        );
      }
      setResults(out.results);
    } catch {
      // The mutation hook already toasted the error; the popup stays open to try again.
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[85dvh] flex-col sm:max-w-5xl" data-testid="po-link-dialog">
        <DialogHeader>
          <DialogTitle>{TITLE[mode]}</DialogTitle>
          <DialogDescription>
            {results ? `${results.length} result${results.length === 1 ? '' : 's'}` : `${ticked.length} of ${rows.length} lines`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="flex-1 space-y-3 overflow-y-auto">
          {results ? (
            results.length ? (
              results.map((result, index) => (
                <ResultCard
                  key={`${result.sales_order_line_id}-${index}`}
                  result={result}
                  kind={result.action ?? mode}
                  target={poTarget}
                  retryItem={
                    sentLinks[result.sales_order_line_id ?? ''] ??
                    (result.action === 'link' && result.sales_order_line_id && result.po_line_id && result.qty != null
                      ? { sales_order_line_id: result.sales_order_line_id, po_line_id: result.po_line_id, qty: result.qty }
                      : null)
                  }
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No PO was linked to those lines.</p>
            )
          ) : rows.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">{coveredTwice ? 'Covered by more than one PO line' : 'No PO linked'}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {coveredTwice ? 'Change PO needs a line covered by exactly one PO line.' : 'The ticked lines have no PO line linked.'}
              </p>
            </div>
          ) : (
            <>
              {mode === 'link' && poLines.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No PO line has stock free for this product.
                </p>
              ) : null}
              <DataGrid
                table={table}
                recordCount={rows.length}
                tableLayout={{
                  width: 'fixed',
                  columnsResizable: true,
                  columnsDraggable: false,
                  scrollerMaxHeight: false,
                }}
              >
                <DataGridTable />
              </DataGrid>
            </>
          )}
          {!results && skipped?.length ? (
            <ul className="space-y-0.5 text-xs text-muted-foreground" data-testid="po-link-skipped">
              {skipped.map((row, index) => (
                <li key={`${row.inquiry_no}-${row.item_code}-${index}`} className="truncate">
                  {`${row.inquiry_no ?? '-'} ${row.item_code ?? ''}: ${row.reason}`}
                </li>
              ))}
            </ul>
          ) : null}
        </DialogBody>
        <DialogFooter className="flex-wrap items-center gap-2">
          {results ? (
            <Button type="button" onClick={onClose}>
              Done
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={onClose} disabled={sending}>
                Cancel
              </Button>
              <Button type="button" onClick={handleSend} disabled={sending || ticked.length === 0}>
                {`${SEND[mode]} ${ticked.length} line${ticked.length === 1 ? '' : 's'}`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
