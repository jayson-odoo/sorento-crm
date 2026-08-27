'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight, PackageSearch } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import {
  useOrderInquiryPlacementMutations,
  useOrderInquiryPoCandidates,
} from '../hooks/useOrderInquiry';
import { formatInquiryQty } from '../lib/orderInquiryWorklist';
import type { OrderInquiryPoAllocation, OrderInquiryPoCandidate } from '../types/orderInquiry.types';

const CHEVRON_COL = 'w-[28px] min-w-[28px] max-w-[28px]';
const PO_COL = 'w-[170px] min-w-[170px] max-w-[170px]';
const WHERE_COL = 'w-[130px] min-w-[130px] max-w-[130px]';
const SUPPLIER_COL = 'w-[160px] min-w-[160px] max-w-[160px]';
const DATE_COL = 'w-[110px] min-w-[110px] max-w-[110px]';
const NUMBER_COL = 'w-[100px] min-w-[100px] max-w-[100px]';
const TAKE_COL = 'w-[110px] min-w-[110px] max-w-[110px]';

const HEAD_CELL =
  'sticky top-0 z-10 border-b border-e border-border bg-muted px-2 py-1.5 text-start align-bottom font-medium';
const BODY_CELL = 'border-b border-e border-border px-2 py-1.5 align-middle';

/**
 * How a candidate is addressed. Exactly one of the two ids is set - the same rule the
 * link row's own CHECK constraint holds - so this is total, never a coalesce that could
 * silently key two different documents the same way.
 */
function candidateKey(candidate: OrderInquiryPoCandidate): string {
  return candidate.kind === 'spo'
    ? `spo:${candidate.spo_allocation_id ?? ''}`
    : `po:${candidate.po_line_id ?? ''}`;
}

/**
 * How well this document line's location fits the row's own (Q5). Named, not numbered:
 * "tier 3" says nothing to a buyer, "Site pool" says which split to key into AutoCount.
 */
const TIER_LABEL: Record<number, string> = {
  1: 'Same location',
  2: 'Same group',
  3: 'Site pool',
  4: 'Sibling location',
  5: 'Elsewhere',
};

function toNumber(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** `12.50` -> `MYR 12.50`; blank when the PO line carries no price. Not a guess at what
 *  a supplier would charge - only what the line already holds. */
function formatCandidateUnitPrice(
  unitCost?: string | null,
  currency?: string | null,
): string | null {
  if (unitCost === null || unitCost === undefined || unitCost === '') return null;
  const value = Number.parseFloat(unitCost);
  if (!Number.isFinite(value)) return null;
  return `${currency ?? 'MYR'} ${value.toFixed(2)}`;
}

/**
 * Link PO / Link SPO (PLAN-scm-cs-planning-uat.md section 3.I, AC-I1/AC-I2/AC-I10).
 *
 * Linking happens AUTOMATICALLY on confirm, on PO import and on PO confirm, so this
 * dialog is OVERRIDE + AUDIT rather than the workflow. It opens showing what the cascade
 * would take off each candidate (`default_take`), lets that be adjusted per line -
 * clearing a line to `0` drops it - and posts the whole set in one call. The row keeps
 * its FULL quantity whatever is taken: what is not linked stays demand, and the row reads
 * partly linked.
 *
 * Candidates arrive in the walk's own order and are NEVER filtered by location, only
 * ranked by it (Q5): tier 1 is the row's own location, 2 the same group at another site,
 * 3 a site pool, 4 a sibling at the site. An SPO allocation is a candidate for an ORDER
 * BACK row and for nothing else (captain, 25 Aug), and the document CS cited comes first.
 *
 * NOT a DataGrid, the same carve-out `BorrowAddDialog` and `CellStockTable` document: a
 * small fixed table inside a dialog, no column config, sort, resize or pagination.
 */
export function LinkDocumentDialog({
  rowId,
  itemCode,
  qty,
  linkedQty,
  onDone,
}: {
  rowId: string;
  itemCode?: string | null;
  qty: string;
  /**
   * What the row already has on documents. The dialog is looking for the REMAINDER: a row
   * linked 5 of 8 opens needing 3, and offering it 8 would let a person compose an
   * allocation the backend refuses as over-allocated.
   */
  linkedQty?: string | null;
  onDone: () => void;
}) {
  const candidatesQuery = useOrderInquiryPoCandidates(rowId);
  const { placeAllocations } = useOrderInquiryPlacementMutations();
  const candidates = candidatesQuery.data ?? [];
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set());
  const [takes, setTakes] = React.useState<Record<string, string>>({});
  const initialised = React.useRef(false);

  // The cascade's own preview is the starting point (server-computed, so it can never
  // disagree with what auto-place itself would do) - picked up once, the first time the
  // candidates answer, so a hand edit is never clobbered by a background refetch.
  React.useEffect(() => {
    if (initialised.current || candidates.length === 0) return;
    initialised.current = true;
    setTakes(
      Object.fromEntries(
        candidates
          .filter((candidate) => toNumber(candidate.default_take) > 0)
          .map((candidate) => [candidateKey(candidate), candidate.default_take]),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates.length]);

  function toggleExpanded(key: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function setTake(key: string, value: string) {
    setTakes((prev) => ({ ...prev, [key]: value }));
  }

  const need = Math.max(toNumber(qty) - toNumber(linkedQty ?? '0'), 0);
  const totalTaken = candidates.reduce(
    (sum, candidate) => sum + toNumber(takes[candidateKey(candidate)] ?? '0'),
    0,
  );
  const overTaken = totalTaken > need;
  const lineErrors = candidates.some((candidate) => {
    const take = toNumber(takes[candidateKey(candidate)] ?? '0');
    return take > toNumber(candidate.remaining);
  });
  const remainder = Math.max(need - totalTaken, 0);
  const valid = totalTaken > 0 && !overTaken && !lineErrors;

  function handleConfirm() {
    if (!valid) return;
    const allocations: OrderInquiryPoAllocation[] = candidates
      .map((candidate) =>
        candidate.kind === 'spo'
          ? {
              spo_allocation_id: candidate.spo_allocation_id ?? undefined,
              qty: takes[candidateKey(candidate)] ?? '0',
            }
          : {
              po_line_id: candidate.po_line_id ?? undefined,
              qty: takes[candidateKey(candidate)] ?? '0',
            },
      )
      .filter((allocation) => toNumber(allocation.qty) > 0);
    if (allocations.length === 0) return;
    placeAllocations.mutate({ rowId, allocations }, { onSuccess: onDone });
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-3xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>Link to a document</DialogTitle>
          <DialogDescription>
            {itemCode ?? 'This item'} - {formatInquiryQty(String(need))} still to link of{' '}
            {formatInquiryQty(qty)}. Adjust the take on any line; whatever is left unlinked
            stays demand.
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
                <AlertTitle>Could not load candidate lines</AlertTitle>
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
              No outstanding purchase order line or SPO allocation holds this item.
            </div>
          ) : (
            <>
              <div
                data-testid="po-candidates-table"
                className="max-h-[45vh] w-full overflow-x-auto overflow-y-auto overscroll-x-contain rounded-lg border border-border"
              >
                <table className="w-max border-separate border-spacing-0 text-xs">
                  <thead>
                    <tr>
                      <th scope="col" className={cn(CHEVRON_COL, HEAD_CELL)}>
                        <span className="sr-only">Expand</span>
                      </th>
                      <th scope="col" className={cn(PO_COL, HEAD_CELL)}>
                        Document
                      </th>
                      <th scope="col" className={cn(WHERE_COL, HEAD_CELL)}>
                        Where
                      </th>
                      <th scope="col" className={cn(SUPPLIER_COL, HEAD_CELL)}>
                        Supplier
                      </th>
                      <th scope="col" className={cn(DATE_COL, HEAD_CELL)}>
                        Issued
                      </th>
                      <th scope="col" className={cn(DATE_COL, HEAD_CELL)}>
                        Expected
                      </th>
                      <th scope="col" className={cn(NUMBER_COL, HEAD_CELL, 'text-end')}>
                        Remaining
                      </th>
                      <th scope="col" className={cn(TAKE_COL, HEAD_CELL, 'text-end')}>
                        Take
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((candidate) => (
                      <CandidateRow
                        key={candidateKey(candidate)}
                        candidate={candidate}
                        take={takes[candidateKey(candidate)] ?? ''}
                        onTakeChange={(value) => setTake(candidateKey(candidate), value)}
                        expanded={expandedIds.has(candidateKey(candidate))}
                        onToggleExpand={() => toggleExpanded(candidateKey(candidate))}
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              <div
                data-testid="po-allocation-summary"
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs"
              >
                <span>
                  {formatInquiryQty(String(totalTaken))} of {formatInquiryQty(String(need))}
                  {' '}linked
                  {remainder > 0 && !overTaken
                    ? ` - ${formatInquiryQty(String(remainder))} stays demand`
                    : ''}
                </span>
                {overTaken && (
                  <span className="font-medium text-destructive">
                    {formatInquiryQty(String(totalTaken - need))} more than this row needs
                  </span>
                )}
                {!overTaken && lineErrors && (
                  <span className="font-medium text-destructive">
                    A line's take is more than it has left
                  </span>
                )}
              </div>
            </>
          )}
        </DialogBody>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onDone}
            disabled={placeAllocations.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={!valid || placeAllocations.isPending}
          >
            {placeAllocations.isPending ? 'Linking…' : 'Link'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CandidateRow({
  candidate,
  take,
  onTakeChange,
  expanded,
  onToggleExpand,
}: {
  candidate: OrderInquiryPoCandidate;
  take: string;
  onTakeChange: (value: string) => void;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const remaining = toNumber(candidate.remaining);
  const taken = toNumber(take);
  const overLine = taken > remaining;

  return (
    <>
      <tr data-testid={`po-candidate-${candidateKey(candidate)}`}>
        <td className={cn(CHEVRON_COL, BODY_CELL)}>
          <button
            type="button"
            className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted"
            onClick={onToggleExpand}
            aria-label={expanded ? 'Collapse' : 'Expand'}
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronDown className="size-3.5" aria-hidden />
            ) : (
              <ChevronRight className="size-3.5" aria-hidden />
            )}
          </button>
        </td>
        <td className={cn(PO_COL, BODY_CELL)}>
          <span className="min-w-0">
            <span className="flex min-w-0 items-center gap-1">
              <span
                className="block truncate font-medium tabular-nums"
                title={candidate.po_number}
              >
                {candidate.po_number}
                {candidate.line_label ? ` ${candidate.line_label}` : ''}
              </span>
              <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                {candidate.kind}
              </span>
            </span>
            {candidate.cited && (
              <span className="mt-0.5 me-1 inline-block rounded-sm bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                Cited
              </span>
            )}
            {toNumber(candidate.default_take) > 0 && (
              <span className="mt-0.5 inline-block rounded-sm bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                Cascade take {formatInquiryQty(candidate.default_take)}
              </span>
            )}
          </span>
        </td>
        <td className={cn(WHERE_COL, BODY_CELL)}>
          <span className="min-w-0">
            <span className="block truncate" title={candidate.location ?? 'Not stated'}>
              {candidate.location ?? (
                <span className="text-muted-foreground">Not stated</span>
              )}
            </span>
            <span className="block truncate text-[10px] text-muted-foreground">
              {TIER_LABEL[candidate.tier] ?? 'Elsewhere'}
            </span>
          </span>
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
            {candidate.issue_date ? (
              formatDateInMalaysia(candidate.issue_date)
            ) : (
              <span className="text-muted-foreground">No date</span>
            )}
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
        <td className={cn(TAKE_COL, BODY_CELL)}>
          <Input
            type="number"
            min={0}
            step="any"
            value={take}
            onChange={(event) => onTakeChange(event.target.value)}
            aria-label={`Take off ${candidate.po_number}`}
            className={cn('h-7 text-end text-xs', overLine && 'border-destructive')}
          />
        </td>
      </tr>
      {expanded && (
        <tr data-testid={`po-candidate-expand-${candidateKey(candidate)}`}>
          <td colSpan={8} className="border-b border-e border-border bg-muted/30 p-0">
            <CandidateExpandPanel candidate={candidate} />
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * The candidate's expand (the captain, 20 Aug): the PO line's OWN figures, and every
 * OTHER row already tagged to it - the evidence behind `already_tagged` / `remaining`,
 * not just their totals. Same visual pattern as `GroupMembersPanel`'s drills elsewhere
 * (`scm/reorder`) - a small nested table under the row, no page-wide overflow.
 */
function CandidateExpandPanel({ candidate }: { candidate: OrderInquiryPoCandidate }) {
  const unitPrice = formatCandidateUnitPrice(candidate.unit_cost, candidate.currency);

  return (
    <div className="px-4 py-3">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-2xs sm:grid-cols-5">
        <ExpandField label="Qty ordered" value={formatInquiryQty(candidate.qty_ordered)} />
        <ExpandField label="Qty received" value={formatInquiryQty(candidate.qty_received)} />
        <ExpandField label="Remaining" value={formatInquiryQty(candidate.remaining)} />
        <ExpandField
          label="Expected"
          value={
            candidate.expected_date ? formatDateInMalaysia(candidate.expected_date) : 'No date'
          }
        />
        <ExpandField label="Where" value={candidate.location ?? 'Not stated'} />
        <ExpandField
          label="Location fit"
          value={TIER_LABEL[candidate.tier] ?? 'Elsewhere'}
        />
        <ExpandField label="Unit price" value={unitPrice ?? 'No price on file'} />
      </dl>

      <div className="mt-3">
        <p className="mb-1 text-2xs font-medium text-muted-foreground">
          Already linked on this line
        </p>
        {candidate.claims.length === 0 ? (
          <p className="text-2xs text-muted-foreground">
            No other row is linked to this line yet.
          </p>
        ) : (
          <div className="overflow-x-auto overscroll-x-contain">
            <table className="w-max border-separate border-spacing-0 text-2xs">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="px-2 py-1 text-start font-medium">SO number</th>
                  <th className="px-2 py-1 text-start font-medium">Item code</th>
                  <th className="px-2 py-1 text-end font-medium">Qty</th>
                  <th className="px-2 py-1 text-start font-medium">Linked on</th>
                </tr>
              </thead>
              <tbody>
                {candidate.claims.map((claim, index) => (
                  <tr key={`${claim.so_number ?? ''}-${index}`} className="border-t border-border/60">
                    <td className="px-2 py-1">{claim.so_number ?? '-'}</td>
                    <td className="px-2 py-1">{claim.item_code ?? '-'}</td>
                    <td className="px-2 py-1 text-end tabular-nums">
                      {formatInquiryQty(claim.qty)}
                    </td>
                    <td className="px-2 py-1">
                      {claim.placed_date ? formatDateInMalaysia(claim.placed_date) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ExpandField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate font-medium tabular-nums">{value}</dd>
    </div>
  );
}
