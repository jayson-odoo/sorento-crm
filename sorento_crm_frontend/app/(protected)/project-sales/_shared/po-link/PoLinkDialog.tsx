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
import { poLinkResultText, type PoLinkDialogMode, type PoLinkKind } from './poLinkWording';

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
  mode: PoLinkDialogMode;
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

/** One Link row's message: the typed qty against what the line still needs and the PO line has free,
 *  `totalOnPo` being everything ticked on that PO line (rows share its free stock). */
function linkRowError(
  line: PoLinkLine,
  po: PoLinkOption | undefined,
  typed: string | undefined,
  totalOnPo: number,
  capabilities: PoLinkCapabilities,
  cap: (line: PoLinkLine, po: PoLinkOption | undefined) => number = qtyCap,
): string | undefined {
  if (!po) return 'No PO line picked';
  const max = cap(line, po);
  const value = typed ?? String(max);
  const error = numberFieldError(value, { min: 1, max, integer: true });
  if (error) return error;
  if (Number(value) === po.po_qty && !capabilities.link_row.enabled) {
    return `Linking the whole PO line: ${capabilities.link_row.reason ?? 'Waiting for AutoCount'}`;
  }
  if (totalOnPo > po.free_qty) return `PO ${po.po_number} has ${po.free_qty.toLocaleString()} free in total`;
  return undefined;
}

/** One Change row's message: the new PO line must have the whole open balance free. */
function changeRowError(
  needs: number,
  po: PoLinkOption | undefined,
  totalOnPo: number,
  capabilities: PoLinkCapabilities,
): string | undefined {
  if (!po) return 'No PO line picked';
  if (needs >= po.po_qty && !capabilities.link_row.enabled) {
    return `Linking the whole PO line: ${capabilities.link_row.reason ?? 'Waiting for AutoCount'}`;
  }
  if (needs > po.free_qty || totalOnPo > po.free_qty) {
    return `PO ${po.po_number} has only ${po.free_qty.toLocaleString()} free`;
  }
  return undefined;
}

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
  onRetryChange,
}: {
  result: PoLinkResult;
  kind: PoLinkKind;
  target: PoLinkTarget;
  /** The one link this card was for: Try again sends exactly it through the target's link api. */
  retryItem?: { sales_order_line_id: string; po_line_id: string; qty: number } | null;
  /** Change PO, unlink half refused: Try again re-sends the whole change for that SO line. */
  onRetryChange?: (() => Promise<void>) | null;
}) {
  const { relocate, resume, link } = usePoLinkMutations(target);
  const [current, setCurrent] = React.useState(result);
  const text = poLinkResultText(current, kind);
  const busy = relocate.isPending || resume.isPending || link.isPending;
  const canRetryChange = Boolean(onRetryChange) && (current.outcome === 'refused' || current.outcome === 'vendor_error');
  const canRetry = Boolean(retryItem) && (current.outcome === 'refused' || current.outcome === 'vendor_error' || current.outcome === 'skipped');
  return (
    <div className={cn('space-y-1 rounded-md p-3 text-sm', TONE[text.tone])} data-testid="po-link-result">
      <p className="font-semibold">{text.title}</p>
      <p className="tabular-nums">{text.text}</p>
      {canRetryChange ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={async () => {
            try {
              await (onRetryChange as () => Promise<void>)();
            } catch {
              // The mutation hook already toasted the error; the card stays for another try.
            }
          }}
        >
          Try again
        </Button>
      ) : null}
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

function SingleModeDialog({
  mode,
  target: poTarget,
  lines,
  allLines,
  capabilities,
  poLines,
  soBooks,
  skipped,
  onClose,
}: PoLinkDialogProps & { mode: PoLinkKind }) {
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
    // Change PO on a line covered twice: only the PO line you pick a replacement for is sent.
    Object.fromEntries(
      rows.filter((row) => selectable(row) && (mode !== 'change' || rows.length === 1)).map((row) => [row.id, true]),
    ),
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
  const [sentChanges, setSentChanges] = React.useState<Array<{ sales_order_line_id: string; po_line_id: string; from_po_line_id: string }>>([]);
  const [resultsVersion, setResultsVersion] = React.useState(0);
  const [sentLinks, setSentLinks] = React.useState<Record<string, { sales_order_line_id: string; po_line_id: string; qty: number }>>({});

  function rowError(row: DialogRow): string | undefined {
    if (mode === 'relink') return target[row.id] ? undefined : 'Pick the sales order line';
    if (mode === 'change') {
      const po = poById.get(picked[row.id] ?? '');
      // Card 3a: the new PO line must have the whole linked qty free (shared across lines).
      const total = rows
        .filter((other) => rowSelection[other.id] && picked[other.id] === po?.po_line_id)
        .reduce((sum, other) => sum + (other.linkedQty ?? 0), 0);
      return changeRowError(row.linkedQty ?? 0, po, total, capabilities);
    }
    if (mode !== 'link') return undefined;
    const po = poById.get(picked[row.id] ?? '');
    // Two ticked lines on one PO line share its free stock.
    const total = rows
      .filter((other) => rowSelection[other.id] && picked[other.id] === po?.po_line_id)
      .reduce((sum, other) => sum + Number(qty[other.id] ?? String(qtyCap(other.line, po))), 0);
    return linkRowError(row.line, po, qty[row.id], total, capabilities);
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
                placeholder="Pick a PO line"
                clearable
                truncateTriggerLabel
                onChange={(value) => {
                  setPicked((prev) => ({ ...prev, [row.original.id]: value }));
                  setRowSelection((prev) => ({ ...prev, [row.original.id]: Boolean(value) }));
                }}
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

  const ticked = rows.filter((row) => rowSelection[row.id]);
  const sending = link.isPending || unlink.isPending || relink.isPending || change.isPending;

  /** Change PO Try again: the same change for exactly that SO line, its cards replaced by the new answer. */
  async function retryChange(item: { sales_order_line_id: string; po_line_id: string; from_po_line_id: string }) {
    const out = await change.mutateAsync([item]);
    setResults((prev) => {
      const kept = (prev ?? []).filter((r) => r.sales_order_line_id !== item.sales_order_line_id);
      return [...kept, ...out.results];
    });
    setResultsVersion((v) => v + 1);
  }

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
        const items = ticked.map((row) => ({
          sales_order_line_id: row.line.sales_order_line_id,
          po_line_id: picked[row.id],
          from_po_line_id: row.poLineId as string,
        }));
        setSentChanges(items);
        out = await change.mutateAsync(items);
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
                  key={`${result.sales_order_line_id}-${index}-${resultsVersion}`}
                  result={result}
                  kind={result.action ?? mode}
                  target={poTarget}
                  onRetryChange={(() => {
                    if (mode !== 'change' || result.action !== 'unlink') return null;
                    const item = sentChanges.find(
                      (c) => c.sales_order_line_id === result.sales_order_line_id && c.from_po_line_id === result.po_line_id,
                    );
                    return item ? () => retryChange(item) : null;
                  })()}
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
              <p className="text-sm font-semibold">No PO linked</p>
              <p className="mt-1 text-sm text-muted-foreground">
                The ticked lines have no PO line linked.
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


export function PoLinkDialog(props: PoLinkDialogProps) {
  if (props.mode === 'manage') return <ManageDialog {...props} />;
  return <SingleModeDialog {...(props as PoLinkDialogProps & { mode: PoLinkKind })} />;
}

/* ------------------------------------------------------------------------------------------
 * Link PO (owner, 13 Nov 18:55: "1 button ... then they can link or change link or unlink in the
 * popup"). One grid: a row per (ticked SO line, linked PO line) with an Action (Keep, Unlink,
 * Change to <PO line>), and a "new" row per line that still needs qty or has no PO. Save sends
 * unlink, then change, then link, through the target's own apis; answers come back in one list.
 * ---------------------------------------------------------------------------------------- */

/** A new row's qty cap: what the line still needs, never above its own outstanding. */
function manageCap(line: PoLinkLine, po: PoLinkOption | undefined): number {
  const needs = Math.min(stillNeeds(line), Math.floor(line.open_qty));
  return po ? Math.min(needs, Math.floor(po.free_qty)) : needs;
}

interface ManageRow {
  id: string;
  line: PoLinkLine;
  kind: 'linked' | 'new';
  /** linked rows: the PO line now covering the SO line. */
  poLineId: string | null;
  poLabel: string | null;
  /** The open balance Change PO would move. */
  linkedQty: number;
}

type Batch = 'unlink' | 'change' | 'link';
type TaggedResult = PoLinkResult & { _batch?: Batch };

function ManageDialog({
  target: poTarget,
  lines,
  capabilities,
  poLines,
  soBooks,
  skipped,
  onClose,
}: PoLinkDialogProps) {
  const { link, unlink, change } = usePoLinkMutations(poTarget);
  const rows = React.useMemo<ManageRow[]>(
    () =>
      lines.flatMap((line) => {
        const linked: ManageRow[] = (line.now?.po_links ?? []).map((po) => ({
          id: `${line.sales_order_line_id}:${po.po_line_id}`,
          line,
          kind: 'linked',
          poLineId: po.po_line_id,
          poLabel: `${po.po_number} · line ${po.po_line_no ?? '-'}`,
          linkedQty: po.open_qty ?? po.qty,
        }));
        const fresh: ManageRow[] =
          stillNeeds(line) > 0 || linked.length === 0
            ? [{ id: `${line.sales_order_line_id}:new`, line, kind: 'new', poLineId: null, poLabel: null, linkedQty: 0 }]
            : [];
        return [...linked, ...fresh];
      }),
    [lines],
  );

  const poById = React.useMemo(() => new Map(poLines.map((po) => [po.po_line_id, po])), [poLines]);
  const labelOf = React.useCallback(
    (po: PoLinkOption) => poOptionLabel(po, poLines.filter((other) => other.po_number === po.po_number).length > 1),
    [poLines],
  );
  const bookNote = React.useCallback(
    (line: PoLinkLine, po: PoLinkOption) => {
      const book = soBooks?.[line.sales_order_line_id];
      return book && po.book && po.book !== book ? OTHER_BOOK : undefined;
    },
    [soBooks],
  );
  /** Action of a linked row: '' is Keep, 'unlink', or `change:<po line id>`. */
  const [action, setAction] = React.useState<Record<string, string>>({});
  const [picked, setPicked] = React.useState<Record<string, string>>({});
  const [qty, setQty] = React.useState<Record<string, string>>({});
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [showErrors, setShowErrors] = React.useState(false);
  const [results, setResults] = React.useState<TaggedResult[] | null>(null);
  const [version, setVersion] = React.useState(0);
  const [sent, setSent] = React.useState<{
    changes: Array<{ sales_order_line_id: string; po_line_id: string; from_po_line_id: string }>;
    links: Record<string, { sales_order_line_id: string; po_line_id: string; qty: number }>;
  }>({ changes: [], links: {} });

  const chosenPo = (row: ManageRow): string | undefined =>
    row.kind === 'new'
      ? picked[row.id] || undefined
      : action[row.id]?.startsWith('change:')
        ? action[row.id].slice('change:'.length)
        : undefined;
  const isUnlink = (row: ManageRow) => row.kind === 'linked' && action[row.id] === 'unlink';
  const effective = (row: ManageRow) =>
    Boolean(rowSelection[row.id]) && (row.kind === 'new' ? Boolean(picked[row.id]) : Boolean(action[row.id]));

  function rowError(row: ManageRow): string | undefined {
    if (row.kind === 'linked') {
      if (isUnlink(row)) return undefined;
      const po = poById.get(chosenPo(row) ?? '');
      const total = rows
        .filter((o) => o.kind === 'linked' && effective(o) && chosenPo(o) === po?.po_line_id)
        .reduce((sum, o) => sum + o.linkedQty, 0);
      return changeRowError(row.linkedQty, po, total, capabilities);
    }
    const po = poById.get(picked[row.id] ?? '');
    const total = rows
      .filter((o) => o.kind === 'new' && effective(o) && picked[o.id] === po?.po_line_id)
      .reduce((sum, o) => sum + Number(qty[o.id] ?? String(manageCap(o.line, po))), 0);
    return linkRowError(row.line, po, qty[row.id], total, capabilities, manageCap);
  }

  const stateRef = React.useRef({ action, picked, qty, showErrors, rowError });
  stateRef.current = { action, picked, qty, showErrors, rowError };

  const tick = (rowId: string, on: boolean) => setRowSelection((prev) => ({ ...prev, [rowId]: on }));

  const columns = React.useMemo<ColumnDef<ManageRow>[]>(() => {
    const wrongBook = (row: ManageRow, po: PoLinkOption) => bookNote(row.line, po);
    const changeReason = !capabilities.split_link.enabled
      ? (capabilities.split_link.reason ?? 'Waiting for AutoCount')
      : !capabilities.unlink_row.enabled
        ? (capabilities.unlink_row.reason ?? 'Waiting for AutoCount')
        : null;
    return [
      buildSelectColumn<ManageRow>({
        rowLabel: (row) => `Select ${row.original.line.so_number} line ${soLine(row.original.line)}`,
      }),
      {
        id: 'so',
        header: 'Sales order',
        size: 120,
        cell: ({ row }) => <span className="font-medium">{row.original.line.so_number}</span>,
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
        cell: ({ row }) => <span className="tabular-nums">{row.original.line.open_qty.toLocaleString()}</span>,
      },
      {
        id: 'po',
        header: 'PO',
        size: 220,
        cell: ({ row }) => {
          const r = row.original;
          if (r.kind === 'linked') return <span className="tabular-nums">{r.poLabel}</span>;
          return (
            <>
              <Label htmlFor={`po-manage-po-${r.id}`} className="sr-only">
                PO
              </Label>
              <SearchableSelect
                id={`po-manage-po-${r.id}`}
                value={stateRef.current.picked[r.id] ?? ''}
                placeholder="Pick a PO line"
                clearable
                truncateTriggerLabel
                onChange={(value) => {
                  setPicked((prev) => ({ ...prev, [r.id]: value }));
                  tick(r.id, Boolean(value));
                }}
                options={poLines.map((po) => {
                  const note = wrongBook(r, po);
                  return { value: po.po_line_id, label: labelOf(po), ...(note ? { disabled: true, description: note } : {}) };
                })}
              />
            </>
          );
        },
      },
      {
        id: 'action',
        header: 'Action',
        size: 240,
        cell: ({ row }) => {
          const r = row.original;
          if (r.kind === 'new') {
            const po = poById.get(stateRef.current.picked[r.id] ?? '');
            const cap = manageCap(r.line, po);
            return (
              <>
                <Label htmlFor={`po-manage-qty-${r.id}`} className="sr-only">
                  Qty
                </Label>
                <NumberInput
                  id={`po-manage-qty-${r.id}`}
                  min={1}
                  max={cap}
                  disabled={!po}
                  value={stateRef.current.qty[r.id] ?? String(cap)}
                  error={stateRef.current.showErrors && effective(r) ? stateRef.current.rowError(r) : undefined}
                  onChange={(event) => {
                    const typed = event.target.value;
                    setQty((prev) => ({ ...prev, [r.id]: typed }));
                  }}
                />
              </>
            );
          }
          const options: SearchableSelectOption[] = [
            {
              value: 'unlink',
              label: 'Unlink',
              ...(capabilities.unlink_row.enabled
                ? {}
                : { disabled: true, description: capabilities.unlink_row.reason ?? 'Waiting for AutoCount' }),
            },
            ...poLines
              .filter((po) => po.po_line_id !== r.poLineId)
              .map((po) => {
                const note = changeReason ?? wrongBook(r, po);
                return {
                  value: `change:${po.po_line_id}`,
                  label: `Change to ${labelOf(po)}`,
                  ...(note ? { disabled: true, description: note } : {}),
                };
              }),
          ];
          return (
            <>
              <Label htmlFor={`po-manage-action-${r.id}`} className="sr-only">
                Action
              </Label>
              <SearchableSelect
                id={`po-manage-action-${r.id}`}
                value={stateRef.current.action[r.id] ?? ''}
                placeholder="Keep"
                truncateTriggerLabel
                onChange={(value) => {
                  setAction((prev) => ({ ...prev, [r.id]: value }));
                  tick(r.id, Boolean(value));
                }}
                options={options}
              />
              {stateRef.current.showErrors && effective(r) && stateRef.current.rowError(r) ? (
                <p className="mt-1 truncate text-xs text-destructive" role="alert">
                  {stateRef.current.rowError(r)}
                </p>
              ) : null}
            </>
          );
        },
      },
    ];
    // Cells read live values through `stateRef` (the RequestReserveDialog G6 lesson).
  }, [capabilities, poLines, poById, labelOf, bookNote]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: true,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const todo = rows.filter(effective);
  const sending = link.isPending || unlink.isPending || change.isPending;

  async function handleSave() {
    if (todo.some((row) => rowError(row))) {
      setShowErrors(true);
      return;
    }
    const unlinks = todo.filter(isUnlink);
    const changes = todo
      .filter((row) => row.kind === 'linked' && !isUnlink(row))
      .map((row) => ({
        sales_order_line_id: row.line.sales_order_line_id,
        po_line_id: chosenPo(row) as string,
        from_po_line_id: row.poLineId as string,
      }));
    const links = todo
      .filter((row) => row.kind === 'new')
      .map((row) => {
        const po = poById.get(picked[row.id]) as PoLinkOption;
        return {
          sales_order_line_id: row.line.sales_order_line_id,
          po_line_id: po.po_line_id,
          qty: Number(qty[row.id] ?? String(manageCap(row.line, po))),
        };
      });
    setSent({ changes, links: Object.fromEntries(links.map((item) => [item.sales_order_line_id, item])) });
    const collected: TaggedResult[] = [];
    try {
      if (unlinks.length) {
        const out = await unlink.mutateAsync(unlinks.map((row) => row.poLineId as string));
        collected.push(...out.results.map((r) => ({ ...r, action: r.action ?? 'unlink', _batch: 'unlink' as Batch })));
      }
      if (changes.length) {
        const out = await change.mutateAsync(changes);
        collected.push(...out.results.map((r) => ({ ...r, _batch: 'change' as Batch })));
      }
      if (links.length) {
        const out = await link.mutateAsync(links);
        collected.push(...out.results.map((r) => ({ ...r, action: r.action ?? 'link', _batch: 'link' as Batch })));
      }
    } catch {
      // The mutation hook already toasted the error; what was answered so far stays on screen.
    }
    if (collected.length) setResults(collected);
  }

  async function retryChange(item: { sales_order_line_id: string; po_line_id: string; from_po_line_id: string }) {
    const out = await change.mutateAsync([item]);
    setResults((prev) => [
      ...(prev ?? []).filter((r) => !(r._batch === 'change' && r.sales_order_line_id === item.sales_order_line_id)),
      ...out.results.map((r) => ({ ...r, _batch: 'change' as Batch })),
    ]);
    setVersion((v) => v + 1);
  }

  async function retryUnlink(poLineId: string) {
    const out = await unlink.mutateAsync([poLineId]);
    setResults((prev) =>
      (prev ?? []).flatMap((r) =>
        r._batch === 'unlink' && r.po_line_id === poLineId
          ? out.results.map((n) => ({ ...n, action: n.action ?? 'unlink', _batch: 'unlink' as Batch }))
          : [r],
      ),
    );
    setVersion((v) => v + 1);
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[85dvh] flex-col sm:max-w-5xl" data-testid="po-link-dialog">
        <DialogHeader>
          <DialogTitle>Link PO</DialogTitle>
          <DialogDescription>
            {results ? `${results.length} result${results.length === 1 ? '' : 's'}` : `${todo.length} of ${rows.length} lines`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="flex-1 space-y-3 overflow-y-auto">
          {results ? (
            results.map((result, index) => {
              const batch = result._batch;
              const item =
                batch === 'change' && result.action === 'unlink'
                  ? sent.changes.find(
                      (c) => c.sales_order_line_id === result.sales_order_line_id && c.from_po_line_id === result.po_line_id,
                    )
                  : null;
              return (
                <ResultCard
                  key={`${result.sales_order_line_id}-${result.action}-${index}-${version}`}
                  result={result}
                  kind={(result.action ?? 'link') as PoLinkKind}
                  target={poTarget}
                  onRetryChange={
                    item
                      ? () => retryChange(item)
                      : batch === 'unlink' && result.po_line_id
                        ? () => retryUnlink(result.po_line_id as string)
                        : null
                  }
                  retryItem={
                    batch === 'link' || (batch === 'change' && result.action === 'link')
                      ? (sent.links[result.sales_order_line_id ?? ''] ??
                        (result.sales_order_line_id && result.po_line_id && result.qty != null
                          ? { sales_order_line_id: result.sales_order_line_id, po_line_id: result.po_line_id, qty: result.qty }
                          : null))
                      : null
                  }
                />
              );
            })
          ) : rows.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">Nothing to link</p>
            </div>
          ) : (
            <DataGrid
              table={table}
              recordCount={rows.length}
              tableLayout={{ width: 'fixed', columnsResizable: true, columnsDraggable: false, scrollerMaxHeight: false }}
            >
              <DataGridTable />
            </DataGrid>
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
              <Button type="button" onClick={handleSave} disabled={sending || todo.length === 0}>
                {`Save (${todo.length})`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
