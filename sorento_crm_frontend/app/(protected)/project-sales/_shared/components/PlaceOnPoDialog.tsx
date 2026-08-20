'use client';

import * as React from 'react';
import { PackageSearch } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import {
  useOrderInquiryPlacementMutations,
  useOrderInquiryPoCandidates,
} from '../hooks/useOrderInquiry';
import { formatInquiryQty } from '../lib/orderInquiryWorklist';
import type { OrderInquiryPoCandidate } from '../types/orderInquiry.types';

const PO_COL = 'w-[150px] min-w-[150px] max-w-[150px]';
const SUPPLIER_COL = 'w-[160px] min-w-[160px] max-w-[160px]';
const DATE_COL = 'w-[110px] min-w-[110px] max-w-[110px]';
const NUMBER_COL = 'w-[100px] min-w-[100px] max-w-[100px]';

const HEAD_CELL =
  'sticky top-0 z-10 border-b border-e border-border bg-muted px-2 py-1.5 text-start align-bottom font-medium';
const BODY_CELL = 'border-b border-e border-border px-2 py-1.5 align-middle';

/**
 * "Identify which outstanding PO has quantity to fulfil this order inquiry, tag it, and
 * the quantity to be ordered is deducted" (the captain, 20 Aug - PLAN-demo-followups-19aug
 * -ladder-v2.md section G).
 *
 * A candidate covers the row's WHOLE quantity or it does not - there is no partial tag,
 * matching the backend's own 409 when a chosen line's remaining balance falls short. A
 * non-covering candidate is still shown (never hidden - the CRUD standard's "an empty
 * state names why"), just disabled with the shortfall named beside it.
 *
 * NOT a DataGrid, the same carve-out `BorrowAddDialog` and `CellStockTable` document: a
 * small fixed table inside a dialog, no column config, sort, resize or pagination.
 */
export function PlaceOnPoDialog({
  rowId,
  itemCode,
  qty,
  onDone,
}: {
  rowId: string;
  itemCode?: string | null;
  qty: string;
  onDone: () => void;
}) {
  const candidatesQuery = useOrderInquiryPoCandidates(rowId);
  const { place } = useOrderInquiryPlacementMutations();
  const candidates = candidatesQuery.data ?? [];

  const recommended = candidates.find((candidate) => candidate.recommended);
  const firstSelectable = recommended ?? candidates.find((candidate) => candidate.covers);
  const [selectedId, setSelectedId] = React.useState<string>(firstSelectable?.po_line_id ?? '');

  // The recommendation only exists once the answer is back; pick it up the first time it
  // is - the effect runs once nothing was already chosen by hand.
  React.useEffect(() => {
    if (selectedId) return;
    if (firstSelectable) setSelectedId(firstSelectable.po_line_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstSelectable?.po_line_id]);

  const selected = candidates.find((candidate) => candidate.po_line_id === selectedId);
  const valid = Boolean(selected) && selected!.covers;

  function handleConfirm() {
    if (!valid || !selected) return;
    place.mutate(
      { rowId, poLineId: selected.po_line_id },
      { onSuccess: onDone },
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-3xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>Place on a purchase order</DialogTitle>
          <DialogDescription>
            {itemCode ?? 'This item'} - {formatInquiryQty(qty)} needed
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-3 overflow-y-auto">
          {candidatesQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : candidatesQuery.isError ? (
            <Alert variant="destructive" appearance="light">
              <AlertIcon>
                <PackageSearch />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>Could not load purchase order lines</AlertTitle>
                <AlertDescription>
                  {candidatesQuery.error instanceof Error
                    ? candidatesQuery.error.message
                    : 'Try again in a moment.'}
                </AlertDescription>
              </AlertContent>
            </Alert>
          ) : candidates.length === 0 ? (
            <div
              data-testid="po-candidates-empty"
              className="rounded-lg border border-border px-3 py-6 text-center text-sm text-muted-foreground"
            >
              No outstanding purchase order line holds this item.
            </div>
          ) : (
            <div
              data-testid="po-candidates-table"
              className="max-h-[45vh] w-full overflow-x-auto overflow-y-auto overscroll-x-contain rounded-lg border border-border"
            >
              <table className="w-max border-separate border-spacing-0 text-xs">
                <thead>
                  <tr>
                    <th scope="col" className={cn(PO_COL, HEAD_CELL)}>
                      PO no
                    </th>
                    <th scope="col" className={cn(SUPPLIER_COL, HEAD_CELL)}>
                      Supplier
                    </th>
                    <th scope="col" className={cn(DATE_COL, HEAD_CELL)}>
                      Expected
                    </th>
                    <th scope="col" className={cn(NUMBER_COL, HEAD_CELL, 'text-end')}>
                      Remaining
                    </th>
                    <th scope="col" className={cn(NUMBER_COL, HEAD_CELL, 'text-end')}>
                      After tag
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate) => (
                    <CandidateRow
                      key={candidate.po_line_id}
                      candidate={candidate}
                      qty={qty}
                      selected={candidate.po_line_id === selectedId}
                      onSelect={() => setSelectedId(candidate.po_line_id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DialogBody>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onDone} disabled={place.isPending}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={!valid || place.isPending}>
            {place.isPending ? 'Placing…' : 'Place on PO'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CandidateRow({
  candidate,
  qty,
  selected,
  onSelect,
}: {
  candidate: OrderInquiryPoCandidate;
  qty: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const disabled = !candidate.covers;
  const need = Number.parseFloat(qty);
  const remaining = Number.parseFloat(candidate.remaining);
  const shortfall =
    Number.isFinite(need) && Number.isFinite(remaining) ? need - remaining : null;
  const afterTag =
    !disabled && Number.isFinite(need) && Number.isFinite(remaining)
      ? formatInquiryQty(String(remaining - need))
      : null;

  return (
    <tr
      data-testid={`po-candidate-${candidate.po_line_id}`}
      className={disabled ? 'opacity-60' : undefined}
    >
      <td className={cn(PO_COL, BODY_CELL)}>
        <label
          htmlFor={`po-candidate-${candidate.po_line_id}`}
          className={cn('flex items-start gap-2', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}
        >
          <input
            id={`po-candidate-${candidate.po_line_id}`}
            type="radio"
            name="po-candidate"
            className="mt-0.5"
            checked={selected}
            disabled={disabled}
            onChange={onSelect}
          />
          <span className="min-w-0">
            <span className="block truncate font-medium tabular-nums" title={candidate.po_number}>
              {candidate.po_number}
            </span>
            {candidate.recommended && (
              <span className="mt-0.5 inline-block rounded-sm bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                Recommended
              </span>
            )}
          </span>
        </label>
      </td>
      <td className={cn(SUPPLIER_COL, BODY_CELL)}>
        <span
          className="block truncate"
          title={candidate.supplier_name ?? 'Not stated'}
        >
          {candidate.supplier_name ?? <span className="text-muted-foreground">Not stated</span>}
        </span>
      </td>
      <td className={cn(DATE_COL, BODY_CELL)}>
        <span className="block truncate">
          {candidate.expected_date ? (
            formatDateInMalaysia(candidate.expected_date)
          ) : (
            <span className="text-muted-foreground">No date</span>
          )}
        </span>
      </td>
      <td className={cn(NUMBER_COL, BODY_CELL)}>
        <span className="block truncate text-end tabular-nums">
          {formatInquiryQty(candidate.remaining)}
        </span>
      </td>
      <td className={cn(NUMBER_COL, BODY_CELL)}>
        {disabled ? (
          <span
            data-testid={`po-candidate-shortfall-${candidate.po_line_id}`}
            className="block truncate text-end text-2xs text-destructive"
            title={
              shortfall !== null
                ? `${formatInquiryQty(String(shortfall))} short of the ${formatInquiryQty(qty)} needed`
                : 'Not enough left on this line'
            }
          >
            {shortfall !== null
              ? `${formatInquiryQty(String(shortfall))} short`
              : 'Not enough left'}
          </span>
        ) : (
          <span className="block truncate text-end tabular-nums">{afterTag}</span>
        )}
      </td>
    </tr>
  );
}
