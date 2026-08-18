'use client';

import * as React from 'react';
import Link from 'next/link';
import { ClipboardList, PackageSearch } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useAllocationCandidates } from '../../../../_shared/hooks/useProjectAllocations';
import type {
  AllocationCandidate,
  AllocationLineRow,
} from '../../../../_shared/types/projectAllocation.types';
import { ALLOCATION_SOURCE_LABEL } from '../../../../_shared/types/projectAllocation.types';
import { formatQty } from '../../../components/SalesOrderMoney';

/**
 * The ranked sources for one line, as evidence (AC-H1, AC-H2). A READ.
 *
 * It answers "what could this line come from, and who is holding it" - the same ranking
 * the supply sheet offers as Borrow candidates. Nothing is taken or asked for here: Stage
 * 1C composes and confirms a whole sales order's supply in one transaction in Fulfilment
 * Planning, and a cross-project Borrow is written already accepted by the CS actor who
 * confirms it, so a quantity box on this screen would be a decision with nowhere to go.
 *
 * The figures are fetched every time this opens and are never cached: they belong to other
 * people's stock and go stale the moment those people ship.
 */
export function AllocationSourceDialog({
  line,
  onDone,
}: {
  line: AllocationLineRow;
  onDone: () => void;
}) {
  const candidates = useAllocationCandidates(line.line_id);
  const data = candidates.data;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <span className="break-words">
              {`Line ${line.line_no}: ${line.product_code || 'Unresolved product'}`}
            </span>
            <Badge variant="secondary" appearance="light">
              {`${formatQty(line.qty)} ${line.uom || ''}`.trim()}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          {candidates.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {candidates.isError && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-6 text-center">
              <p className="text-sm font-semibold text-destructive">
                The ranked sources could not be loaded
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {candidates.error instanceof Error
                  ? candidates.error.message
                  : 'Try again in a moment.'}
              </p>
            </div>
          )}

          {data && data.candidates.length === 0 && (
            <div className="rounded-lg border border-dashed px-4 py-10 text-center">
              <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
              <p className="mt-2 text-sm font-semibold">No location holds this product</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
                It has to be bought. The Buy residual is decided in Fulfilment Planning.
              </p>
            </div>
          )}

          {data?.candidates.map((candidate) => (
            <CandidateCard
              key={candidate.warehouse_id ?? 'order'}
              candidate={candidate}
            />
          ))}
        </DialogBody>

        <DialogFooter className="flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Supply is composed in Fulfilment Planning.
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button asChild variant="outline">
              <Link href="/project-sales/fulfilment-planning">
                <ClipboardList className="size-4" aria-hidden />
                Open Fulfilment Planning
              </Link>
            </Button>
            <Button type="button" onClick={onDone}>
              Close
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CandidateCard({ candidate }: { candidate: AllocationCandidate }) {
  const held = candidate.source_type === 'other_project';
  const isOrder = candidate.source_type === 'order';

  return (
    <div className="rounded-lg border px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" appearance="light" size="sm">
              {candidate.rank}
            </Badge>
            <span className="truncate text-sm font-medium" title={candidate.warehouse_code ?? ''}>
              {candidate.warehouse_code || 'No location'}
            </span>
            <Badge
              variant={held ? 'warning' : isOrder ? 'secondary' : 'success'}
              appearance="light"
              size="sm"
            >
              {ALLOCATION_SOURCE_LABEL[candidate.source_type] ?? candidate.source_type}
            </Badge>
            {candidate.is_project_location && (
              <Badge variant="info" appearance="light" size="sm">
                This project
              </Badge>
            )}
          </div>

          {isOrder ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Nothing on the shelf covers this. Purchasing buys it.
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">
              {`On hand ${formatQty(candidate.on_hand)} · committed ${formatQty(
                candidate.committed,
              )} · free ${formatQty(candidate.available)}`}
            </p>
          )}

          {candidate.holders.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {candidate.holders.map((holder) => (
                <li key={holder.project_id} className="text-xs text-muted-foreground">
                  {`${formatQty(holder.qty)} held for ${holder.project_code}, ask ${
                    holder.cs_name || 'their CS'
                  }`}
                </li>
              ))}
            </ul>
          )}
        </div>

        {!isOrder && (
          <div className="shrink-0 text-sm tabular-nums sm:text-end">
            <span className="font-medium">{formatQty(candidate.allocatable)}</span>
            <span className="text-muted-foreground"> free to take</span>
          </div>
        )}
      </div>
    </div>
  );
}
